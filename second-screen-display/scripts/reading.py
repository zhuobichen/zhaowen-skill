# Markdown/TXT -> e-ink friendly EPUB (no third-party deps).
# Usage: python reading.py <input.md|txt> [outdir]
import html
import os
import re
import sys
import uuid
import zipfile
from datetime import datetime, timezone

CSS = """\
body { margin: 0.6em 0.7em; line-height: 1.75; font-family: serif; }
h1 { font-size: 1.5em; margin: 1.2em 0 0.8em; page-break-before: always; }
h2 { font-size: 1.25em; margin: 1.1em 0 0.6em; }
h3 { font-size: 1.1em; margin: 1em 0 0.5em; }
p  { margin: 0 0 0.85em; text-indent: 2em; }
p.noindent { text-indent: 0; }
pre { font-family: monospace; font-size: 0.82em; line-height: 1.45; white-space: pre-wrap;
      background: #f2f2f2; padding: 0.6em; margin: 0.8em 0; }
code { font-family: monospace; font-size: 0.9em; }
blockquote { margin: 0.8em 0 0.8em 0.8em; padding-left: 0.8em; border-left: 2px solid #888; }
ul, ol { margin: 0 0 0.9em 1.2em; padding: 0; }
li { margin: 0 0 0.35em; }
hr { border: 0; border-top: 1px solid #999; margin: 1.4em 0; }
"""


def md_inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    return s


def md_to_html(md):
    """Very small markdown subset: headings, lists, quotes, fenced code, hr, paragraphs."""
    out, in_code, in_list = [], False, None
    for raw in md.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            if in_code:
                out.append("</pre>")
                in_code = False
            else:
                out.append("<pre>")
                in_code = True
            continue
        if in_code:
            out.append(html.escape(raw))
            continue
        if not line.strip():
            if in_list:
                out.append("</%s>" % in_list)
                in_list = None
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            if in_list:
                out.append("</%s>" % in_list)
                in_list = None
            lvl = min(len(m.group(1)), 3)
            out.append("<h%d>%s</h%d>" % (lvl, md_inline(m.group(2)), lvl))
            continue
        if re.match(r"^(\*\s*){3,}$|^(-\s*){3,}$", line):
            out.append("<hr/>")
            continue
        m = re.match(r"^\s*[-*+]\s+(.*)$", line)
        if m:
            if in_list != "ul":
                if in_list:
                    out.append("</%s>" % in_list)
                out.append("<ul>")
                in_list = "ul"
            out.append("<li>%s</li>" % md_inline(m.group(1)))
            continue
        m = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if m:
            if in_list != "ol":
                if in_list:
                    out.append("</%s>" % in_list)
                out.append("<ol>")
                in_list = "ol"
            out.append("<li>%s</li>" % md_inline(m.group(1)))
            continue
        m = re.match(r"^>\s?(.*)$", line)
        if m:
            if in_list:
                out.append("</%s>" % in_list)
                in_list = None
            out.append("<blockquote><p class=\"noindent\">%s</p></blockquote>" % md_inline(m.group(1)))
            continue
        if line.startswith("    ") or line.startswith("\t"):
            out.append("<pre>%s</pre>" % html.escape(line.strip()))
            continue
        out.append("<p>%s</p>" % md_inline(line))
    if in_list:
        out.append("</%s>" % in_list)
    if in_code:
        out.append("</pre>")
    return "\n".join(out)


def split_chapters(md, title):
    parts = re.split(r"(?m)^#\s+", md)
    chapters = []
    if parts and parts[0].strip():
        chapters.append((title, parts[0]))
    for p in parts[1:]:
        lines = p.splitlines()
        if not lines:
            continue
        chapters.append((lines[0].strip() or title, "\n".join(lines[1:])))
    if not chapters:
        chapters.append((title, md))
    return chapters


def build(src_path, outdir):
    raw = open(src_path, encoding="utf-8", errors="replace").read()
    title = os.path.splitext(os.path.basename(src_path))[0]
    chapters = split_chapters(raw, title)

    bookid = "urn:uuid:" + str(uuid.uuid4())
    mod = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    os.makedirs(outdir, exist_ok=True)
    out_path = os.path.join(outdir, title + ".epub")

    manifest, spine, navs, pages = [], [], [], {}
    for i, (ctitle, body) in enumerate(chapters, 1):
        fname = "chap%03d.xhtml" % i
        body_html = md_to_html(body) if src_path.lower().endswith(".md") else \
            "".join("<p>%s</p>" % html.escape(x) for x in body.splitlines() if x.strip())
        page = ('<?xml version="1.0" encoding="utf-8"?>\n'
                '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>%s</title>'
                '<link rel="stylesheet" type="text/css" href="style.css"/></head><body>'
                '<h1>%s</h1>\n%s\n</body></html>') % (html.escape(ctitle), html.escape(ctitle), body_html)
        manifest.append('<item id="c%d" href="%s" media-type="application/xhtml+xml"/>' % (i, fname))
        spine.append('<itemref idref="c%d"/>' % i)
        navs.append('<li><a href="%s">%s</a></li>' % (fname, html.escape(ctitle)))
        pages[fname] = page

    nav_xhtml = ('<?xml version="1.0" encoding="utf-8"?>\n'
                 '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
                 '<head><title>目录</title><link rel="stylesheet" type="text/css" href="style.css"/></head>'
                 '<body><h1>目录</h1><nav epub:type="toc"><ol>%s</ol></nav></body></html>') % "".join(navs)

    opf = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           '<dc:identifier id="bookid">%s</dc:identifier><dc:title>%s</dc:title>'
           '<dc:language>zh-CN</dc:language><dc:creator>本地生成</dc:creator>'
           '<meta property="dcterms:modified">%s</meta></metadata>'
           '<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
           '<item id="css" href="style.css" media-type="text/css"/>%s</manifest>'
           '<spine>%s</spine></package>') % (bookid, html.escape(title), mod, "".join(manifest), "".join(spine))

    with zipfile.ZipFile(out_path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0" encoding="utf-8"?>\n'
                   '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                   'media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav_xhtml)
        z.writestr("OEBPS/style.css", CSS)
        for fname, page in pages.items():
            z.writestr("OEBPS/" + fname, page)

    return out_path, len(chapters), os.path.getsize(out_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: reading.py <file.md|txt> [outdir]")
        sys.exit(2)
    src = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("OUT_DIR", ".")
    p, n, sz = build(src, outdir)
    print("OK %s chapters=%d bytes=%d" % (p, n, sz))
