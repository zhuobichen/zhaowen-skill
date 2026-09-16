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
    'name': 'blue',
    'primary': '#0F4C81',        # 主色（藏青蓝）
    'primary_soft': '#E8F0F7',   # 浅底
    'link': '#576b95',           # 微信官方链接蓝
    'text': '#3f3f3f',
    'caption': '#888888',
    'divider': '#E5E7EB',
    'font_size': 16,
    'line_height': 1.75,
}

# 首尾空行占位（借鉴 doocs/md）：保住微信编辑器首尾空行
EMPTY_NODE = '<p style="font-size:0;line-height:0;margin:0;padding:0;"><br></p>'


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
def render_block(b, theme, img_dir, embed, strip_brackets):
    t = b['type']

    if t == 'title':
        # 标题单独交给微信「标题」字段，正文默认不重复（避免与平台标题打架）
        return ''

    if t == 'heading':
        return (
            '<p style="margin:36px 0 24px;padding:11px 0;background:%s;'
            'color:#ffffff;font-size:17px;font-weight:bold;text-align:center;'
            'letter-spacing:2px;border-radius:4px;">%s</p>'
            % (theme['primary'], esc(b['text']))
        )

    if t == 'para':
        return (
            '<p style="margin:0 0 22px;font-size:%dpx;line-height:%s;color:%s;'
            'text-align:justify;letter-spacing:0.5px;">%s</p>'
            % (theme['font_size'], theme['line_height'], theme['text'], esc(b['text']))
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
        if cap:
            # figure/figcaption 已实测可在微信编辑器中存活并持久化
            return (
                '<figure style="margin:24px 0 28px;">%s'
                '<figcaption style="margin-top:10px;font-size:13px;color:%s;'
                'text-align:center;line-height:1.6;letter-spacing:0.5px;">%s</figcaption>'
                '</figure>' % (img_tag, theme['caption'], esc(cap))
            )
        return '<figure style="margin:24px 0 28px;">%s</figure>' % img_tag

    return ''


def render(content, theme, img_dir, embed=False, strip_brackets=False):
    parts = [EMPTY_NODE]
    for b in content['blocks']:
        html = render_block(b, theme, img_dir, embed, strip_brackets)
        if html:
            parts.append(html)
    parts.append(EMPTY_NODE)
    # 整体包一层 section（比 div 更被微信友好）
    body = ''.join(parts)
    return (
        '<section style="font-size:%dpx;line-height:%s;color:%s;'
        'word-break:break-word;">%s</section>'
        % (theme['font_size'], theme['line_height'], theme['text'], body)
    )


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
