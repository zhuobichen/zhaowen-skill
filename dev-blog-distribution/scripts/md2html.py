# -*- coding: utf-8 -*-
"""零依赖 md -> HTML：给「复制到富文本编辑器」这一条路用。

覆盖：一级~六级标题、段落、围栏代码块、表格、无序列表、引用、分隔线、
行内代码 / 粗体 / 链接。刻意不支持嵌套列表与脚注 —— 目标平台里没有一个
需要它们，而多写一档就多一处分叉。

用法:
    python md2html.py in.md out.html            # 带一级标题
    python md2html.py in.md out.html --no-title # 去掉一级标题（各站标题另有输入框）
"""
import html
import re
import sys


def inline(text):
    codes = []

    def stash(m):
        codes.append(m.group(1))
        return '\x00%d\x00' % (len(codes) - 1)

    # 先把行内代码挖走（里面的 * 和 ` 不该被当语法），再转义，最后加粗/链接
    text = re.sub(r'`([^`]+)`', stash, text)
    text = html.escape(text, quote=False)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'<a href="\2">\1</a>', text)
    for i, c in enumerate(codes):
        text = text.replace('\x00%d\x00' % i, '<code>%s</code>' % html.escape(c, quote=False))
    return text


def convert(md, keep_title=True):
    out = []
    lines = md.replace('\r\n', '\n').split('\n')
    i, n = 0, len(lines)
    in_list = False
    seen_title = False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append('</ul>')
            in_list = False

    while i < n:
        line = lines[i].rstrip()

        if line.startswith('```'):
            close_list()
            lang = line[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].startswith('```'):
                buf.append(html.escape(lines[i], quote=False))
                i += 1
            i += 1
            cls = ' class="language-%s"' % lang if lang else ''
            out.append('<pre><code%s>%s</code></pre>' % (cls, '\n'.join(buf)))
            continue

        if not line.strip():
            close_list()
            i += 1
            continue

        if re.match(r'^\s*---+\s*$', line):
            close_list()
            out.append('<hr>')
            i += 1
            continue

        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            close_list()
            level = len(m.group(1))
            if level == 1 and not keep_title and not seen_title:
                seen_title = True
                i += 1
                continue
            out.append('<h%d>%s</h%d>' % (level, inline(m.group(2)), level))
            i += 1
            continue

        if line.strip().startswith('|') and i + 1 < n and re.match(r'^\s*\|[\s:|-]+\|\s*$', lines[i + 1]):
            close_list()
            header = [c.strip() for c in line.strip().strip('|').split('|')]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')])
                i += 1
            th = ''.join('<th>%s</th>' % inline(c) for c in header)
            body = ''.join('<tr>' + ''.join('<td>%s</td>' % inline(c) for c in r) + '</tr>' for r in rows)
            out.append('<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>' % (th, body))
            continue

        if line.startswith('> '):
            close_list()
            out.append('<blockquote><p>%s</p></blockquote>' % inline(line[2:].strip()))
            i += 1
            continue

        if re.match(r'^[-*]\s+', line):
            if not in_list:
                out.append('<ul>')
                in_list = True
            item = re.sub(r'^[-*]\s+', '', line)
            item = re.sub(r'^\[ \]\s*', '', item)          # 任务列表的复选框
            out.append('<li>%s</li>' % inline(item))
            i += 1
            continue

        close_list()
        buf = [line]
        i += 1
        while i < n and lines[i].strip() and not re.match(r'^(#{1,6}\s|```|>\s|[-*]\s|\||\s*---+\s*$)', lines[i]):
            buf.append(lines[i].rstrip())
            i += 1
        out.append('<p>%s</p>' % inline(' '.join(x.strip() for x in buf)))

    close_list()
    return '\n'.join(out)


CSS = (
    'body{max-width:760px;margin:40px auto;font:16px/1.8 -apple-system,"PingFang SC",'
    '"Microsoft YaHei",sans-serif;color:#333}'
    'pre{background:#f6f8fa;padding:12px;border-radius:6px;overflow:auto}'
    'code{background:#f2f2f2;padding:1px 4px;border-radius:3px;'
    'font-family:Consolas,Monaco,monospace;font-size:14px}'
    'pre code{background:none;padding:0}'
    'table{border-collapse:collapse;width:100%}'
    'th,td{border:1px solid #ddd;padding:6px 10px;text-align:left}'
    'blockquote{border-left:4px solid #ddd;margin:16px 0;padding:4px 16px;color:#666}'
)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    keep_title = '--no-title' not in sys.argv
    if len(args) < 2:
        print(__doc__)
        raise SystemExit(2)
    src, dst = args[0], args[1]
    md = open(src, encoding='utf-8').read()
    title = ''
    for ln in md.split('\n'):
        if ln.startswith('# '):
            title = ln[2:].strip()
            break
    body = convert(md, keep_title=keep_title)
    head = '<h1>%s</h1>' % html.escape(title) if (keep_title and title) else ''
    page = ('<!doctype html><html><head><meta charset="utf-8"><title>%s</title>'
            '<style>%s</style></head><body>%s%s</body></html>'
            % (html.escape(title), CSS, head, body))
    open(dst, 'w', encoding='utf-8').write(page)
    print('bytes=%d code=%d table=%d p=%d' % (len(page), body.count('<pre>'), body.count('<table>'), body.count('<p>')))


if __name__ == '__main__':
    main()
