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
    'name': 'blue-frame',
    # —— 结构：整篇一个边框容器 + 硬投影（对齐中国环境科学学会的真实排版）——
    # 参考：mp.weixin.qq.com/s/zm07cyQ2W0IDoXL2x9lAiQ
    #   border:1px solid 主色; box-shadow: 浅色 7px 7px 0px 0px  ← 硬投影，不是模糊阴影
    'frame_border': '#0F4C81',    # 边框色 = 主色
    'frame_shadow': '#C9DBEC',    # 硬投影色（浅蓝灰）
    'frame_offset': 7,            # 投影偏移 px（0 模糊 = 硬投影）
    # 框内「纸」色：偏白，只带一点蓝（深浅实测后按用户口径定）
    # 改这一个值就要连带检查下面的 primary_soft / caption 对比度
    'frame_bg': '#F0F6FC',
    'card_bg': '#FFFFFF',
    # —— 主色 ——
    'primary': '#0F4C81',        # 藏青蓝
    'primary_mid': '#2E5B9A',
    # 底色越白，胶囊要越「蓝」才能分得出来（不能比底色更白，否则糊成一片）
    'primary_soft': '#DEEBF8',
    'link': '#576b95',           # 微信官方链接蓝
    # —— 文本 ——
    'text': '#3e3e3e',
    # 图注：跟随底色调整。底色白 → 用中灰；底色蓝 → 必须加深
    'caption': '#6E7B89',
    'caption_size': 13,
    'divider': '#E5E7EB',
    'font_size': 16,
    'line_height': 2,            # 参考文章用 2，很透气
    'letter_spacing': '1px',
    'text_indent': '2.125em',    # 参考文章的首行缩进
}

# 首尾空行占位（借鉴 doocs/md）：保住微信编辑器首尾空行
EMPTY_NODE = '<p style="font-size:0;line-height:0;margin:0;padding:0;"><br></p>'

# 文末 END 装饰线。用 table 而不是 flex —— 微信对 flex 支持有限，table 最稳
END_LINE = (
    '<section style="margin:44px 0 30px;">'
    '<table style="width:100%;border-collapse:collapse;border:none;"'
    ' cellspacing="0" cellpadding="0" border="0"><tr>'
    '<td style="border:none;height:1px;line-height:1px;font-size:0;'
    'background:linear-gradient(to right,rgba(15,76,129,0),#0F4C81);">&nbsp;</td>'
    '<td style="border:none;width:76px;text-align:center;font-size:11px;'
    'color:#0F4C81;letter-spacing:4px;font-weight:bold;">END</td>'
    '<td style="border:none;height:1px;line-height:1px;font-size:0;'
    'background:linear-gradient(to left,rgba(15,76,129,0),#0F4C81);">&nbsp;</td>'
    '</tr></table></section>'
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
        # 参考文章的「胶囊标题条」：浅底 + 大圆角 + 居中主色字 + 菱形点缀
        # 编号 01/02 是纯装饰，不引入原文之外的内容
        # 编号与标题**同字号同字重同色**：之前用 13px + 半透明，视觉上「比旁边小一号」，
        # 看着像出错而不是设计。要突出就整体突出，不要靠缩字号。
        num = ('<span style="color:%s;font-size:16px;font-weight:bold;'
               'letter-spacing:2px;vertical-align:middle;margin-right:6px;">%02d</span>'
               % (theme['primary'], heading_no)) if heading_no else ''
        diamond = ('<span style="display:inline-block;width:8px;height:8px;'
                   'background-color:%s;transform:rotate(45deg);'
                   'vertical-align:middle;%s"></span>')
        return (
            '<section style="margin:30px 0 18px;padding:9px 6px;'
            'background-color:%s;border-radius:20px;text-align:center;">'
            '%s%s<span style="color:%s;font-size:16px;font-weight:bold;'
            'letter-spacing:2px;vertical-align:middle;">%s</span>%s</section>'
            % (theme['primary_soft'],
               diamond % (theme['primary'], 'margin-right:10px;'),
               num,
               theme['primary'], esc(b['text']),
               diamond % (theme['primary'], 'margin-left:10px;'))
        )

    if t == 'para':
        # 与参考文章一致：无卡片、首行缩进、行高 2、字距 1px，正文连续流淌
        return (
            '<p style="margin:0 0 0.9em;text-indent:%s;font-size:%dpx;'
            'line-height:%s;color:%s;text-align:justify;'
            'letter-spacing:%s;">%s</p>'
            % (theme['text_indent'], theme['font_size'], theme['line_height'],
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
            '<img src="%s" style="max-width:100%%;height:auto;display:block;'
            'margin:0 auto;border-radius:4px;">' % src
        )
        # 与参考文章一致：图片通栏、无卡片，让图文连续
        if cap:
            # figure/figcaption 已实测可在微信编辑器中存活并持久化
            return (
                '<figure style="margin:14px 0 18px;">%s'
                '<figcaption style="margin:8px 0 0;font-size:%dpx;color:%s;'
                'text-align:center;line-height:1.6;letter-spacing:0.5px;">%s</figcaption>'
                '</figure>'
                % (img_tag, theme['caption_size'], theme['caption'], esc(cap))
            )
        return '<figure style="margin:14px 0 18px;">%s</figure>' % img_tag

    return ''


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
        fig = render_block(b, theme, img_dir, embed, strip_brackets)
        if fig:
            cells.append(('<section style="vertical-align:top;width:__W__%25;'
                          'scroll-snap-align:center;max-width:__W__%25 !important;">'
                          '__FIG__</section>')
                         .replace('__W__', ('%g' % (100.0 / n)))
                         .replace('__FIG__', fig))
    if len(cells) < 2:
        return None
    return ('<section style="width:100%;vertical-align:top;overflow:auto;'
            'scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;">'
            '<section style="width:__ROW__%;display:flex;flex-flow:row;'
            'max-width:__ROW__% !important;">__CELLS__</section></section>'
            ).replace('__ROW__', str(n * 100)).replace('__CELLS__', ''.join(cells))


def frame_wrap(html, theme, first=True, last=True):
    """给一段内容套上「外框」的一段。

    对齐中国环境科学学会的真实排版（mp.weixin.qq.com/s/zm07cyQ2W0IDoXL2x9lAiQ）：
    整篇**只用一个边框容器**，内容在框内连续流淌——这是「连贯」的关键。
    之前「每个元素各一张卡片」会把文章切成一节一节。

    ⚠️ 推送要分多批 pasteHTML，而 `pasteHTML` 会自动闭合未闭合标签，
    跨批次的单个 <section> 是包不住的。所以改成：**每批各带框的左右边，
    首批加顶边、末批加底边与右下投影**，视觉上拼成完整的一个框。
    """
    b, s, o = theme['frame_border'], theme['frame_shadow'], theme['frame_offset']
    border = 'border-left:1px solid %s;border-right:1px solid %s;' % (b, b)
    if first:
        border += 'border-top:1px solid %s;' % b
    if last:
        border += 'border-bottom:1px solid %s;' % b
    # 批间接缝处只向右侧投影，末批才补右下角，拼起来才是一条连续的硬投影
    shadow = ('box-shadow:%dpx %dpx 0px 0px %s;' % (o, o, s) if last
              else 'box-shadow:%dpx 0px 0px 0px %s;' % (o, s))
    # ⚠️ `margin:0` 不能省：微信编辑器给 <section> 默认加了 margin-bottom:24px，
    # 不显式清零，每批之间就会出现 24px 的缝——框就「断」成一节一节了（实测踩过）。
    return (
        '<section style="margin:0;background-color:%s;padding:8px 12px;%s%s'
        'font-size:%dpx;line-height:%s;color:%s;letter-spacing:%s;'
        'word-break:break-word;text-align:justify;">%s</section>'
        % (theme['frame_bg'], border, shadow,
           theme['font_size'], theme['line_height'], theme['text'],
           theme['letter_spacing'], html)
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
                out.append(gal)
            else:
                for x in run:
                    h = render_block(x, theme, img_dir, embed, strip_brackets)
                    if h:
                        out.append(h)
            i = j
            continue

        # 没有分节标题的稿子：靠文锚点开启合组
        if (not gallery_on) and gallery and gallery_anchor and b['type'] == 'para'                 and gallery_anchor in (b.get('text') or ''):
            gallery_on = True

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
    ap.add_argument('--strip-brackets', action='store_true')
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
    html = render(content, THEME, web_img_dir, args.embed, args.strip_brackets,
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
