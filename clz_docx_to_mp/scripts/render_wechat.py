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
                            [--indent 2em|0] [--max-width 1440]

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
def compress_images(images_dir, out_dir, max_width=1440, quality=88):
    """压缩图片到适合公众号的尺寸，返回 {原文件名: 新文件名}"""
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
            if w > max_width:
                im = im.resize((max_width, int(h * max_width / w)), Image.LANCZOS)
            im.save(dst, 'JPEG', quality=quality, optimize=True, progressive=True)
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
        num = ('<span style="color:%s;font-size:13px;font-weight:bold;'
               'letter-spacing:1px;vertical-align:middle;margin-right:8px;'
               'opacity:0.75;">%02d</span>' % (theme['primary'], heading_no)) if heading_no else ''
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
    return (
        '<section style="background-color:%s;padding:8px 12px;%s%s'
        'font-size:%dpx;line-height:%s;color:%s;letter-spacing:%s;'
        'word-break:break-word;text-align:justify;">%s</section>'
        % (theme['frame_bg'], border, shadow,
           theme['font_size'], theme['line_height'], theme['text'],
           theme['letter_spacing'], html)
    )


def render_blocks(content, theme, img_dir, embed=False, strip_brackets=False):
    """按顺序渲染所有 block，返回 HTML 片段列表（标题编号在这里统一分配）"""
    out, hno = [], 0
    for b in content['blocks']:
        if b['type'] == 'heading':
            hno += 1
        html = render_block(b, theme, img_dir, embed, strip_brackets,
                            heading_no=hno if b['type'] == 'heading' else None)
        if html:
            out.append(html)
    return out


def render(content, theme, img_dir, embed=False, strip_brackets=False):
    parts = [EMPTY_NODE]
    parts.extend(render_blocks(content, theme, img_dir, embed, strip_brackets))
    parts.append(END_LINE)
    parts.append(EMPTY_NODE)
    return frame_wrap(''.join(parts), theme)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('build_dir')
    ap.add_argument('--out', default=None)
    ap.add_argument('--embed', action='store_true')
    ap.add_argument('--strip-brackets', action='store_true')
    ap.add_argument('--max-width', type=int, default=1440)
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
    html = render(content, THEME, web_img_dir, args.embed, args.strip_brackets)

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
