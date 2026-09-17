# -*- coding: utf-8 -*-
"""
结构化 JSON → 微信兼容 HTML（公众号排版流水线第二步）

职责：把 parse_docx.py 产出的 content.json 渲染成「纯内联样式」的 HTML。

微信兼容性硬约束（已实测验证）：
    1. 微信编辑器会剥掉 <style> 块和 class 选择器 → 本脚本不产出任何 <style>，全部 inline
    2. 微信不认 var() 和 calc() → 本脚本只写死字面值，零变量
    3. 微信会剥 width/height 属性 → 图片尺寸一律走 style
    4. 不设置 font-family（有实测记录：带了字体设置会导致样式被丢弃）

用法：
    python render_wechat.py <build_dir> [--out article.html] [--embed] [--strip-brackets]
                            [--max-width 1080] [--no-gallery]

    <build_dir>  含 content.json / images/ 的目录（parse_docx.py 的产出）
    --embed      图片以 base64 内嵌，产出单文件 HTML（推送用）
    --strip-brackets  去掉题注外层的【】，视觉更干净（默认保留原文）
"""
import sys
import os
import io
import json
import base64
import argparse

# 仅在作为脚本直接运行时包装 stdout；被 import 时不碰，否则会导致
# 底层 buffer 被多次包装并在 GC 时关闭
if sys.platform == 'win32' and __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from PIL import Image  # noqa: E402

# ---------------------------------------------------------------- 主题（藏青蓝）
THEME = {
    'name': 'abaas2024',
    # —— 完全对齐 2024 年同系列会议文章（领导要求）——
    # 来源：mp.weixin.qq.com/s/NK6oHHieNbtPrSTAl3wBmg
    # 详见 references/template-2024-abaas.md
    #
    # 结构要点：**没有外层边框、没有整篇底色**；
    # 正文包在 #F4F8FC 浅蓝圆角卡片里，章节标题是「SVG 星形 + 蓝字 + 渐变下划线」。
    'primary': '#4F81BD',        # 主蓝（标题、星形图标）
    'bright': '#1D81E6',         # 亮蓝（渐变下划线起点）
    'teal': '#76C5CB',           # 青（装饰小竖条）
    'line_color': '#4E83BC',     # 细线
    # —— 正文卡片 ——
    'card_bg': '#F4F8FC',
    'card_radius': 10,
    'card_padding': 15,
    # —— 文本 ——
    'text': '#3F3F3F',
    'caption': '#888888',        # 图注 15px #888（模板原值）
    'caption_size': 15,
    'link': '#576b95',           # 微信官方链接蓝
    'font_family': "微软雅黑, 'Microsoft YaHei'",   # 模板设在最外层 section 上
    'font_size': 16,
    'line_height': 2,
    'letter_spacing': '1.5px',
    'text_indent': '2.1875em',   # 模板原值
}

# 首尾空行占位（借鉴 doocs/md）：保住微信编辑器首尾空行
EMPTY_NODE = '<p style="font-size:0;line-height:0;margin:0;padding:0;"><br></p>'

# 文末 END 装饰线。用 table 而不是 flex —— 微信对 flex 支持有限，table 最稳
# 文末收尾线 —— 2024 模板原样（不是「END」字样，是一条蓝线）
END_LINE = (
    '<section style="width:100%;height:3px;overflow:hidden;'
    'border-bottom:1px solid #4F81BD;margin-top:24px;"></section>'
)

# 相册下方的滑动提示 —— 2024 模板原样（相册的**后一个兄弟节点**）
GALLERY_HINT = (
    '<section><p style="text-align:center;vertical-align:inherit;font-size:15px;'
    'letter-spacing:2px;line-height:1.6em;">'
    '<span style="color:#888888;letter-spacing:1px;">◁ 左右滑动查看更多 ▷</span></p></section>'
)

# 分段装饰：两枚渐变小竖条 + 一条蓝细线（2024 模板用它在段与段之间做呼吸）
DIVIDER = (
    '<section style="margin:10px auto;padding:0 7px;">'
    '<section style="display:flex;align-items:center;">'
    '<section style="flex-shrink:0;padding-right:7px;">'
    '<section style="display:flex;">'
    '<section style="width:10px;height:26px;border-radius:25px;'
    'background-image:linear-gradient(#4F81BD,#ffffff);"></section>'
    '<section style="width:10px;height:26px;border-radius:25px;'
    'background-image:linear-gradient(#76C5CB,#ffffff);"></section>'
    '</section></section>'
    '<section style="width:100%;height:1px;overflow:hidden;'
    'border-top:1px solid #4E83BC;"></section>'
    '</section></section>'
)


def esc(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


# ---------------------------------------------------------------- 图片压缩
def compress_images(images_dir, out_dir, max_width=1080, quality=95, subsampling=0):
    """压缩图片到适合公众号的尺寸，返回 {原文件名: 新文件名}

    目标是「在微信的硬限制内，最大化保留原始画质」：

    - **宽度 1080**：微信正文图 >1080px 一律压到 1080（平台硬顶）。与其让微信缩
      （不可控），不如自己用 LANCZOS 缩好，且宽度 ≤1080 的图微信不再缩放。
    - **quality=95**：微信收到后还会重编码一次，输入质量给足才有余量。
    - **subsampling=0（4:4:4）**：**关键项**。JPEG 默认 4:2:0 会把色度分辨率砍半，
      是文字/图表发糊的主因。关掉它体积略增，但色彩与文字边缘明显更实。
    - `optimize=True` 无损瘦身，`progressive=True` 手机端渐进加载更友好。

    max_width<=0 表示不缩放（保留原尺寸交给微信处理）。
    """
    os.makedirs(out_dir, exist_ok=True)
    mapping = {}
    total_before = total_after = 0
    for name in sorted(os.listdir(images_dir)):
        src = os.path.join(images_dir, name)
        if not os.path.isfile(src):
            continue
        stem, _ = os.path.splitext(name)
        dst_name = stem + '.jpg'
        dst = os.path.join(out_dir, dst_name)
        try:
            im = Image.open(src)
            im = im.convert('RGB')
            w, h = im.size
            if max_width and w > max_width:
                im = im.resize((max_width, int(h * max_width / w)), Image.LANCZOS)
            im.save(dst, 'JPEG', quality=quality, subsampling=subsampling,
                    optimize=True, progressive=True)
            mapping[name] = dst_name
            total_before += os.path.getsize(src)
            total_after += os.path.getsize(dst)
        except Exception as e:
            print('  ⚠️ 压缩失败 %s: %s' % (name, e))
            mapping[name] = name
    return mapping, total_before, total_after


def to_data_uri(path):
    ext = os.path.splitext(path)[1].lower()
    mime = 'image/png' if ext == '.png' else 'image/jpeg'
    with open(path, 'rb') as f:
        return 'data:%s;base64,%s' % (mime, base64.b64encode(f.read()).decode())


# ---------------------------------------------------------------- 渲染
def render_block(b, theme, img_dir, embed, strip_brackets, heading_no=None):
    t = b['type']

    if t == 'title':
        # 标题单独交给微信「标题」字段，正文默认不重复（避免与平台标题打架）
        return ''

    if t == 'heading':
        # 2024 模板原样：内联 SVG 星形 + 蓝色加粗标题 + 向右渐隐的渐变下划线。
        # 星形用内联 SVG 而非图片——SVG 在微信里最稳（不受深色模式影响、不被压缩、不占图片额度）。
        # 模板里没有编号，这里也不加。
        return (
            '<section style="margin:20px auto 10px;">'
            '<section style="display:flex;justify-content:flex-start;align-items:center;">'
            '<section style="flex-shrink:0;"><section style="width:20px;">'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 35 33.01" '
            'style="display:block;"><path '
            'd="M35,12.31l-10.54,8L28,32.71l-10.71-7.2L6.39,33l3.92-12.48L0,12.79'
            'l13.13-.51L17.68,0l4.2,12.16Z" style="fill:__P__;fill-rule:evenodd;">'
            '</path></svg></section></section>'
            '<section style="font-size:16px;color:__P__;text-align:left;'
            'padding-right:10px;padding-left:10px;"><strong>__T__</strong></section>'
            '</section>'
            '<section style="width:100%;height:6px;overflow:hidden;'
            'background-image:linear-gradient(to right,__B__,transparent);"><br></section>'
            '</section>'
        ).replace('__P__', theme['primary']).replace('__B__', theme['bright']) \
         .replace('__T__', esc(b['text']))

    if t == 'para':
        # 只产出 <p>，外面那层浅蓝卡片由 render_blocks 把**连续的段落**合成一张
        # （2024 模板里一张卡片装多段，不是一段一张卡）
        return (
            '<p style="line-height:%sem;text-indent:%s;margin:0 0 0.5em;">'
            '<span style="font-size:%dpx;color:%s;letter-spacing:%s;">%s</span></p>'
            % (theme['line_height'], theme['text_indent'], theme['font_size'],
               theme['text'], theme['letter_spacing'], esc(b['text']))
        )

    if t == 'image':
        fname = b['file']
        path = os.path.join(img_dir, fname)
        if not os.path.exists(path):
            return ''
        src = to_data_uri(path) if embed else os.path.join(
            os.path.basename(img_dir), fname).replace('\\', '/')
        cap = b.get('caption')
        if cap and strip_brackets:
            c = cap.strip()
            if c.startswith('【') and c.endswith('】'):
                cap = c[1:-1]
        img_tag = (
            '<img src="%s" style="width:100%%;height:auto;display:block;'
            'vertical-align:baseline;">' % src
        )
        # 2024 模板：图片通栏，图注 15px #888 居中、字距 1px、下方留 10px
        if cap:
            return (
                '<figure style="margin:10px 0;text-align:center;">%s'
                '<figcaption style="margin-bottom:10px;line-height:1.6em;">'
                '<span style="font-size:%dpx;color:%s;letter-spacing:1px;">%s</span>'
                '</figcaption></figure>'
                % (img_tag, theme['caption_size'], theme['caption'], esc(cap))
            )
        return '<figure style="margin:10px 0;">%s</figure>' % img_tag

    return ''


GALLERY_RATIO = 1.5   # 相册统一比例（2024 模板的图都是 3:2）


def gallery_variant(path, target=GALLERY_RATIO):
    """把比例与 target 不符的图**居中裁**成 target，返回可用文件路径。

    为什么要裁：相册是 flex 行，行高由**最高的一项**决定。横竖混排时，
    竖图把行撑高，横图下方就会空出一大片（实测：26 张里混 2 张竖图，
    横图下方各空约 300px）。统一比例后行高才整齐。
    只裁进相册的图——平铺的图是纵向堆叠的，比例不同不影响观感。
    """
    try:
        im = Image.open(path)
    except Exception:
        return path
    w, h = im.size
    if not h:
        return path
    r = w / float(h)
    if abs(r - target) < 0.02:
        return path                      # 比例本来就对，不动它
    if r > target:                       # 太宽 → 裁左右
        nw = int(h * target)
        left = (w - nw) // 2
        im = im.crop((left, 0, left + nw, h))
    else:                                # 太高 → 裁上下（人物多在中间带，居中裁最稳）
        nh = int(w / target)
        top = (h - nh) // 2
        im = im.crop((0, top, w, top + nh))
    out = path[:-4] + '_gal.jpg'
    im.convert('RGB').save(out, 'JPEG', quality=95, subsampling=0,
                           optimize=True, progressive=True)
    return out


def render_gallery(items, theme, img_dir, embed, strip_brackets):
    """把一组图渲染成「横向可滑相册」。

    结构实测自 2024 年同系列会议文章（mp.weixin.qq.com/s/NK6oHHieNbtPrSTAl3wBmg）：

        [外层] width:100%; overflow:auto; scroll-snap-type:x mandatory;
          └ [行] width:{N*100}%; display:flex; flex-flow:row; max-width:{N*100}% !important;
               └ [项] width:{100/N}%; scroll-snap-align:center; max-width:{100/N}% !important;
                    └ <figure> 图片 + 图注

    关键点：**行宽 = 100% × 图片数**，**每项宽 = 100% ÷ 图片数**，两者必须配套，
    缺一个就滑不动或挤在一起。`overflow:auto`（不是 overflow-x）才对——实测微信认这个。
    """
    n = len(items)
    if n < 2:
        return None
    cells = []
    for b in items:
        # 进相册前统一裁成同一比例，否则行高被最高项撑开、矮图下方留大片空白
        p = os.path.join(img_dir, b['file'])
        if os.path.exists(p):
            v = gallery_variant(p)
            if v != p:
                b = dict(b, file=os.path.basename(v))
        fig = render_block(b, theme, img_dir, embed, strip_brackets)
        if fig:
            # ⚠️ 这里是字面量 '%'，不要写成 '%25'——Python 不会做百分号解码，
            #    写成 %25 会产出非法 CSS 值（width:3.84615%25），浏览器整条忽略，
            #    各项就按图片自然尺寸各算各的，宽度参差不齐（踩过）
            cells.append(('<section style="vertical-align:top;width:__W__%;'
                          'scroll-snap-align:center;max-width:__W__% !important;">'
                          '__FIG__</section>')
                         .replace('__W__', ('%g' % (100.0 / n)))
                         .replace('__FIG__', fig))
    if len(cells) < 2:
        return None
    # 滚动条美化：微信会剥掉 <style>，`::-webkit-scrollbar` 那套用不上，
    # 只能用**可内联设置的标准属性** `scrollbar-width` + `scrollbar-color`
    # （实测微信会原样保留这两个属性）。细条 + 主色滑块 + 浅底轨道。
    outer = ('<section style="width:100%;vertical-align:top;overflow:auto;'
             'scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;'
             'scrollbar-width:thin;scrollbar-color:' + theme['primary'] + ' '
             + theme['card_bg'] + ';">')
    inner = ('<section style="width:' + str(n * 100) + '%;display:flex;'
             'flex-flow:row;max-width:' + str(n * 100) + '% !important;">'
             + ''.join(cells) + '</section>')
    return outer + inner + '</section>'


def frame_wrap(html, theme, first=True, last=True):
    """给一段内容套上最外层容器。

    2024 模板的外层**没有边框、没有整篇底色**，只是在 `<section>` 上设了字体：

        <section style="font-family: 微软雅黑, "Microsoft YaHei";">

    注意字体设在**包裹用的 section** 上（不是文字节点）——设在文字元素上会被微信丢样式。
    推送分多批时每批各套一个同样的容器，视觉上仍是连续的一篇。

    ⚠️ `margin:0` 不能省：微信给 `<section>` 默认加了 `margin-bottom:24px`，
    不显式清零每批之间会出现 24px 的空隙（踩过）。
    """
    return (
        '<section style="margin:0;font-family:%s;font-size:%dpx;'
        'word-break:break-word;">%s</section>'
        % (theme['font_family'], theme['font_size'], html)
    )


def render_blocks(content, theme, img_dir, embed=False, strip_brackets=False,
                  gallery=False, gallery_anchor=None):
    """按顺序渲染所有 block，返回 HTML 片段列表（标题编号在这里统一分配）

    gallery=True 时的分组规则：
      **分组线之前**的图 → 逐张平铺（通稿里这段是「开幕式致辞」，
      读者要一眼看全每位致辞人，不该藏进相册）
      **分组线之后**连续的一组图 → 合成一个横向可滑相册

    分组线怎么定（两种稿子结构不同）：
      - 有分节标题的稿子 → 第一个 Heading 之后开始合组
      - **没有分节标题的稿子**（如 v6 稿）→ 用 `gallery_anchor` 指定一段文字，
        遇到含该文字的段落之后开始合组（默认「主旨报告」）
    """
    blocks = content['blocks']
    out, hno, gallery_on = [], 0, False
    i = 0
    while i < len(blocks):
        b = blocks[i]

        if b['type'] == 'heading':
            hno += 1
            gallery_on = True
            html = render_block(b, theme, img_dir, embed, strip_brackets, heading_no=hno)
            if html:
                out.append(html)
            i += 1
            continue

        if b['type'] == 'image':
            j = i
            while j < len(blocks) and blocks[j]['type'] == 'image':
                j += 1
            run = blocks[i:j]
            gal = render_gallery(run, theme, img_dir, embed, strip_brackets) \
                if (gallery and gallery_on and len(run) > 1) else None
            if gal:
                # 相册前放一枚模板自带的分段装饰件，替代分节标题的视觉呼吸作用。
                # 用装饰件而不是加标题——标题会引入原文没有的文字。
                out.append(DIVIDER)
                out.append(gal)
                out.append(GALLERY_HINT)   # 相册下方紧跟「◁ 左右滑动查看更多 ▷」
            else:
                for x in run:
                    h = render_block(x, theme, img_dir, embed, strip_brackets)
                    if h:
                        out.append(h)
            i = j
            continue

        # 连续段落 → 合进**同一张**浅蓝卡片（2024 模板是一卡多段，不是一段一张卡），
        # 同时在这里判定文锚点（无分节标题的稿子靠它开启相册合组）
        if b['type'] == 'para':
            j = i
            while j < len(blocks) and blocks[j]['type'] == 'para':
                j += 1
            run = blocks[i:j]
            if (not gallery_on) and gallery and gallery_anchor:
                for x in run:
                    if gallery_anchor in (x.get('text') or ''):
                        gallery_on = True
                        break
            inner = ''.join(render_block(x, theme, img_dir, embed, strip_brackets) for x in run)
            if inner:
                out.append(
                    '<section style="background-color:%s;padding:%dpx;'
                    'border-radius:%dpx;margin:4px 0;">'
                    '<section style="line-height:1.75em;letter-spacing:1.5px;'
                    'background-color:transparent;">%s</section></section>'
                    % (theme['card_bg'], theme['card_padding'],
                       theme['card_radius'], inner))
            i = j
            continue

        html = render_block(b, theme, img_dir, embed, strip_brackets)
        if html:
            out.append(html)
        i += 1
    return out


def render(content, theme, img_dir, embed=False, strip_brackets=False,
           gallery=False, gallery_anchor=None):
    parts = [EMPTY_NODE]
    parts.extend(render_blocks(content, theme, img_dir, embed, strip_brackets,
                                gallery=gallery, gallery_anchor=gallery_anchor))
    parts.append(END_LINE)
    parts.append(EMPTY_NODE)
    return frame_wrap(''.join(parts), theme)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('build_dir')
    ap.add_argument('--out', default=None)
    ap.add_argument('--embed', action='store_true')
    ap.add_argument('--keep-brackets', action='store_true',
                    help='保留题注外层的【】；默认去掉（对齐 2024 模板）')
    # 默认 1080 = 微信正文图宽度硬顶，超过必被它压（见 compress_images 注释）
    ap.add_argument('--max-width', type=int, default=1080)
    ap.add_argument('--no-gallery', action='store_true',
                    help='关闭横滑相册，所有图逐张平铺')
    ap.add_argument('--gallery-anchor', default='主旨报告',
                    help='无分节标题的稿子用：遇到含此文字的段落之后才开始合组相册')
    args = ap.parse_args()

    build = args.build_dir
    with open(os.path.join(build, 'content.json'), encoding='utf-8') as f:
        content = json.load(f)

    # 1) 压缩图片
    src_img_dir = os.path.join(build, content.get('images_dir', 'images'))
    web_img_dir = os.path.join(build, 'images_web')
    print('压缩图片 →', web_img_dir)
    mapping, before, after = compress_images(src_img_dir, web_img_dir, args.max_width)
    print('  %d 张：%.1f MB → %.1f MB' % (len(mapping), before / 1048576.0, after / 1048576.0))

    # 2) 用压缩后的文件名重写 blocks
    for b in content['blocks']:
        if b['type'] == 'image' and b['file'] in mapping:
            b['file'] = mapping[b['file']]

    # 3) 渲染
    html = render(content, THEME, web_img_dir, args.embed,
                  strip_brackets=not args.keep_brackets,
                  gallery=not args.no_gallery, gallery_anchor=args.gallery_anchor)

    out = args.out or os.path.join(build, 'article_embed.html' if args.embed else 'article.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)

    print('✅ 渲染完成')
    print('   输出:', out)
    print('   HTML 大小: %.2f MB' % (len(html.encode('utf-8')) / 1048576.0))
    print('   图片数:', sum(1 for b in content['blocks'] if b['type'] == 'image'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
