#!/usr/bin/env python3
"""docx_pages.py — 在 .docx 里按「整页」替换内容，常用于把空白表格页换成扫描件。

只依赖标准库（zipfile + re + struct）；有 Pillow 时用 Pillow 读图片尺寸，
没有就自己解析 PNG / JPEG 头。不装 python-docx，也不改原文件。

三个子命令

  list    结构清单：正文里每个段落 / 表格的顺序与开头文字，表格还能展开到行
  replace 按文本锚点删掉一段正文（段落或表格行），在原位插入「一图一页」的图片
  check   包结构校验：zip / XML / 关系引用 / 图片尺寸是否落在版心内

为什么按文本锚点而不是序号：删掉几行之后序号就变了，而「四、实践单位考核」
这种标题不会变。锚点必须唯一命中，命中 0 个或 2 个都直接拒绝——宁可报错，
不要猜着删。

    python docx_pages.py list report.docx
    python docx_pages.py list report.docx --table 2 --rows
    python docx_pages.py replace report.docx --out new.docx \\
        --start "四、实践单位考核" --end "附件1：" \\
        --images p16.jpg p17.jpg
    python docx_pages.py check new.docx
"""

from __future__ import annotations

import argparse
import re
import shutil
import struct
import sys
import zipfile
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


# ---------------------------------------------------------------------------
# 包读写
# ---------------------------------------------------------------------------
class Docx:
    def __init__(self, path: Path):
        self.path = Path(path)
        if not self.path.exists():
            raise SystemExit(f"找不到文件: {self.path}")
        with zipfile.ZipFile(self.path) as z:
            self.names = z.namelist()
            self.parts = {n: z.read(n) for n in self.names}
        self.xml = self.parts["word/document.xml"].decode("utf-8")
        self.rels_name = "word/_rels/document.xml.rels"
        self.rels = self.parts[self.rels_name].decode("utf-8")

    def save(self, dest: Path):
        dest = Path(dest)
        if dest.resolve() == self.path.resolve():
            raise SystemExit("拒绝覆盖原文件：--out 指向了输入文件")
        self.parts["word/document.xml"] = self.xml.encode("utf-8")
        self.parts[self.rels_name] = self.rels.encode("utf-8")
        if dest.exists():
            dest.unlink()
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for name in self.names:
                z.writestr(name, self.parts[name])
        return dest


def text_of(xml_fragment: str) -> str:
    """把一段 XML 里的可见文字取出来（w:t 的内容，忽略制表/换行标记）。"""
    out = []
    for m in re.finditer(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", xml_fragment, re.S):
        out.append(m.group(1))
    s = "".join(out)
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&apos;", "'"))


# ---------------------------------------------------------------------------
# body 切分
# ---------------------------------------------------------------------------
def body_spans(xml: str):
    """正文里每个顶层 <w:p> / <w:tbl> 的 (kind, start, end)。

    顶层 = 直接挂在 <w:body> 下的；表格里的段落不算（它们在表格 span 内部）。
    用深度计数处理嵌套表格。
    """
    body_start = xml.find("<w:body>")
    body_end = xml.rfind("</w:body>")
    if body_start < 0 or body_end < 0:
        raise SystemExit("这不是 Word 文档：找不到 w:body")
    spans, depth, cur = [], 0, None
    for m in re.finditer(r"<w:tbl(?:\s[^>]*)?>|</w:tbl>|<w:p(?:\s[^>]*)?>|</w:p>", xml):
        tok = m.group(0)
        if tok.startswith("<w:tbl"):
            if depth == 0:
                cur = ("tbl", m.start())
            depth += 1
        elif tok == "</w:tbl>":
            depth -= 1
            if depth == 0 and cur and cur[0] == "tbl":
                spans.append(("tbl", cur[1], m.end()))
                cur = None
        elif tok.startswith("<w:p"):
            if depth == 0:
                cur = ("p", m.start())
        elif tok == "</w:p>":
            if depth == 0 and cur and cur[0] == "p":
                spans.append(("p", cur[1], m.end()))
                cur = None
    return [s for s in spans if s[1] >= body_start]


def row_spans(table_xml: str):
    """表内每个 <w:tr> 的 (start, end)（相对该表 XML）。"""
    rows, depth, cur = [], 0, None
    for m in re.finditer(r"<w:tr(?:\s[^>]*)?>|</w:tr>", table_xml):
        tok = m.group(0)
        if tok.startswith("<w:tr"):
            if depth == 0:
                cur = m.start()
            depth += 1
        else:
            depth -= 1
            if depth == 0 and cur is not None:
                rows.append((cur, m.end()))
                cur = None
    return rows


# ---------------------------------------------------------------------------
# 图片尺寸 + 版心
# ---------------------------------------------------------------------------
def image_size(path: Path):
    """(宽, 高) 像素。PNG / JPEG 自己解析，其它格式交给 Pillow。"""
    data = Path(path).read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return int(w), int(h)
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return int(w), int(h)
            i += 2 + seg_len
        raise SystemExit(f"JPEG 里找不到 SOF: {path}")
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.size
    except Exception:
        raise SystemExit(f"读不出图片尺寸（装 Pillow 或转成 PNG/JPEG）: {path}")


def section_geometry(xml: str):
    """最后一节的九宫格：返回 (版心宽, 版心高)，单位 twip。"""
    sect = re.findall(r"<w:sectPr\b.*?</w:sectPr>", xml, re.S)
    if not sect:
        return 11906 - 1800 * 2, 16838 - 1440 * 2  # A4 + 常见页边距
    s = sect[-1]

    def attr(tag, name, default):
        m = re.search(rf'<w:{tag}\b[^>]*\bw:{name}="(-?\d+)"', s)
        return int(m.group(1)) if m else default

    w = attr("pgSz", "w", 11906) - attr("pgMar", "left", 1800) - attr("pgMar", "right", 1800)
    h = attr("pgSz", "h", 16838) - attr("pgMar", "top", 1440) - attr("pgMar", "bottom", 1440)
    return w, h


# ---------------------------------------------------------------------------
# 插入整页图片
# ---------------------------------------------------------------------------
EMU_PER_TWIP = 635


def image_paragraph(rid: str, name: str, px_w: int, px_h: int, usable_w: int, usable_h: int,
                    fit: float, doc_id: int):
    """一张图占一行段落的 DrawingML。

    命名空间声明在 <w:drawing> 上：a: 和 pic: 在 document.xml 的根节点里没有声明，
    只挂在各个 <a:graphic> 上；插入的元素如果不自带 xmlns，Word 打开会直接报
    「unreadable content」，python 侧则报 unbound prefix。
    """
    w_tw = int(min(usable_w * fit, usable_h * px_w / px_h))
    h_tw = int(w_tw * px_h / px_w)
    cx, cy = w_tw * EMU_PER_TWIP, h_tw * EMU_PER_TWIP
    return (
        '<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
        '<w:snapToGrid w:val="0"/><w:jc w:val="center"/></w:pPr>'
        f'<w:r><w:drawing xmlns:a="{NS_A}" xmlns:pic="{NS_PIC}">'
        '<wp:inline distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
        f'<wp:docPr id="{doc_id}" name="Picture {doc_id}"/>'
        '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
        f'<a:graphic xmlns:a="{NS_A}"><a:graphicData uri="{NS_PIC}">'
        f'<pic:pic xmlns:pic="{NS_PIC}"><pic:nvPicPr>'
        f'<pic:cNvPr id="{doc_id}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="{rid}"/>'
        '<a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
    )


PAGE_BREAK = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def add_images(doc: Docx, images, fit: float, break_before=True, break_after=True):
    """把图片登记成 media + relationship，返回一段可直接插进 body 的 XML。"""
    usable_w, usable_h = section_geometry(doc.xml)
    used = [int(x) for x in re.findall(r'Id="rId(\d+)"', doc.rels)]
    next_id = (max(used) + 1) if used else 1
    have = set(doc.names)
    parts, rels = [], []
    if break_before:
        parts.append(PAGE_BREAK)
    for i, src in enumerate(images):
        src = Path(src)
        px_w, px_h = image_size(src)
        ext = src.suffix.lower() if src.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".bmp") else ".png"
        media = f"media/page_{next_id}{ext}"
        while f"word/{media}" in have:
            next_id += 1
            media = f"media/page_{next_id}{ext}"
        rid = f"rId{next_id}"
        doc.parts[f"word/{media}"] = src.read_bytes()
        doc.names.append(f"word/{media}")
        have.add(f"word/{media}")
        rels.append(
            f'<Relationship Id="{rid}" Type="{NS_R}/image" Target="{media}"/>'
        )
        parts.append(image_paragraph(rid, src.name, px_w, px_h, usable_w, usable_h, fit, 4001 + i))
        parts.append(PAGE_BREAK)
        next_id += 1
    if not break_after and parts:
        parts.pop()
    doc.rels = doc.rels.replace("</Relationships>", "".join(rels) + "</Relationships>")
    return "".join(parts), usable_w, usable_h


def ensure_content_types(doc: Docx, exts):
    name = "[Content_Types].xml"
    xml = doc.parts[name].decode("utf-8")
    for ext in sorted(exts):
        e = ext.lstrip(".").lower()
        if f'Extension="{e}"' in xml:
            continue
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "bmp": "image/bmp"}[e]
        xml = xml.replace("</Types>", f'<Default Extension="{e}" ContentType="{mime}"/></Types>')
    doc.parts[name] = xml.encode("utf-8")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------
def cmd_list(args):
    doc = Docx(Path(args.docx))
    spans = body_spans(doc.xml)
    print(f"正文块 {len(spans)} 个（正文段落与表格）：")
    for i, (kind, s, e) in enumerate(spans):
        frag = doc.xml[s:e]
        txt = re.sub(r"\s+", " ", text_of(frag)).strip()
        if kind == "p":
            print(f"  [{i:02d}] P    {txt[:70]}")
        else:
            rows = row_spans(frag)
            print(f"  [{i:02d}] TBL  rows={len(rows)}  {txt[:60]}")
            if args.rows:
                for j, (rs, re_) in enumerate(rows):
                    rt = re.sub(r"\s+", " ", text_of(frag[rs:re_])).strip()
                    print(f"        r{j:02d} {rt[:80]}")
    return 0


# ---------------------------------------------------------------------------
# replace
# ---------------------------------------------------------------------------
def locate(doc: Docx, anchor: str, after: int = -1):
    """找出唯一命中 anchor 的正文块；返回 (index, kind, start, end, 行偏移或 None)。"""
    spans = body_spans(doc.xml)
    hits = []
    for i, (kind, s, e) in enumerate(spans):
        if i <= after:
            continue
        if anchor in text_of(doc.xml[s:e]):
            hits.append((i, kind, s, e))
    if not hits:
        raise SystemExit(f'锚点未命中: "{anchor}"（先用 list 看看正文里到底写了什么）')
    if len(hits) > 1:
        where = "、".join(f"#{h[0]}" for h in hits)
        raise SystemExit(f'锚点 "{anchor}" 命中 {len(hits)} 处（{where}）——请写更长更独特的一段')
    i, kind, s, e = hits[0]
    return i, kind, s, e


def cmd_replace(args):
    doc = Docx(Path(args.docx))
    spans = body_spans(doc.xml)

    i0, k0, s0, e0 = locate(doc, args.start)
    frag0 = doc.xml[s0:e0]

    # 结束锚点：不删它本身，只删它之前
    if args.end:
        i1, k1, s1, e1 = locate(doc, args.end, after=i0 - 1)
        end_off = s1
    else:
        i1, s1 = None, len(doc.xml)
        m = re.search(r"<w:sectPr\b", doc.xml[s0:])
        end_off = s0 + m.start() if m else s0 + len(doc.xml) - s0

    # 起点在表格里 → 行级：从该行截到表尾（表格本身保留前面的行）
    if k0 == "tbl":
        rows = row_spans(frag0)
        hit = [j for j, (rs, re_) in enumerate(rows) if args.start in text_of(frag0[rs:re_])]
        if not hit:
            raise SystemExit("起点在表格里，但定位不到具体是哪一行")
        r = hit[0]
        keep_rows, drop_rows = len(rows) - r, r
        if r == 0:
            # 删到表首 = 整张表都没了。留一个 `<w:tbl>` 只有 tblPr 没有行，
            # Word 会判定结构非法（"unreadable content"），所以整块删掉。
            new0 = ""
            what = f"表格 #{i0} 整张（{keep_rows} 行）"
        else:
            new0 = frag0[: rows[r][0]] + "</w:tbl>"
            what = f"表格 #{i0} 的第 {r} 行起（保留 {drop_rows} 行 / 删 {keep_rows} 行）"
    else:
        new0 = ""
        what = f"段落 #{i0}"

    images = [Path(p) for p in (args.images or [])]
    block = ""
    if images:
        block, uw, uh = add_images(doc, images, args.width,
                                   break_before=not args.no_break_before,
                                   break_after=not args.no_break_after)
        ensure_content_types(doc, {p.suffix for p in images})
        print(f"版心 {uw}×{uh} twip，图片宽度取 {args.width:.0%}")

    tail = doc.xml[end_off:]
    if images:
        block = block + ("<w:p/>" if tail.startswith("<w:tbl") else "")
    doc.xml = doc.xml[:s0] + new0 + block + tail

    out = doc.save(Path(args.out) if args.out else Path(args.docx).with_name(
        Path(args.docx).stem + "_edited.docx"))
    print(f"删除：{what}" + (f" → 直到 {args.end!r} 之前" if args.end else " → 直到文末"))
    print(f"插入：{len(images)} 页图片" if images else "插入：无")
    print(f"输出：{out}")
    return 0


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
def cmd_check(args):
    path = Path(args.docx)
    ok = True
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        print(f"zip: {'ok' if bad is None else '损坏: ' + str(bad)}")
        names = set(z.namelist())
        doc = z.read("word/document.xml").decode("utf-8")
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8")

    try:
        import xml.etree.ElementTree as ET

        ET.fromstring(doc)
        ET.fromstring(rels)
        print("XML: document.xml / rels 均良构")
    except Exception as e:
        ok = False
        print(f"XML: 解析失败 → {e}")

    rel_map = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels))
    refs = set(re.findall(r'r:(?:embed|id)="(rId\d+)"', doc))
    missing = sorted(r for r in refs if r not in rel_map)
    if missing:
        ok = False
        print(f"关系引用: 有 {len(missing)} 个 rId 在 rels 里找不到 → {missing[:5]}")
    else:
        print(f"关系引用: {len(refs)} 个 rId 全部可解析")

    gone = [t for t in rel_map.values() if t.startswith("media/") and f"word/{t}" not in names]
    if gone:
        ok = False
        print(f"图片: 有 {len(gone)} 个 Target 指向包里不存在的文件 → {gone[:5]}")
    else:
        print("图片: media 文件都在")

    usable_w, usable_h = section_geometry(doc)
    toolarge = []
    for m in re.finditer(r'<wp:extent cx="(\d+)" cy="(\d+)"/>', doc):
        cx, cy = int(m.group(1)), int(m.group(2))
        if cx > usable_w * EMU_PER_TWIP + 1000 or cy > usable_h * EMU_PER_TWIP + 1000:
            toolarge.append((round(cx / EMU_PER_TWIP), round(cy / EMU_PER_TWIP)))
    print(f"版心 {usable_w}×{usable_h} twip；超出版心的图: {toolarge or '没有'}")
    if toolarge:
        print("  （超出不一定会坏，但会挤到下一页，出现半页空白）")

    print("结论:", "通过" if ok else "有问题")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="docx 整页替换：按文本锚点删内容、插整页图片")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="列出正文块（段落/表格）与文本开头")
    p.add_argument("docx")
    p.add_argument("--table", type=int, help="只看第 N 个表格")
    p.add_argument("--rows", action="store_true", help="展开表格的每一行")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("replace", help="删掉一段正文并在原位插入整页图片")
    p.add_argument("docx")
    p.add_argument("--out", help="输出路径（默认 <原名>_edited.docx，绝不覆盖输入）")
    p.add_argument("--start", required=True, help="起点锚点文本（必须唯一命中）")
    p.add_argument("--end", help="终点锚点文本（不删它本身；省略则删到文末）")
    p.add_argument("--images", nargs="*", help="要插入的图片，一图一页，按顺序")
    p.add_argument("--width", type=float, default=0.92,
                   help="图片宽度占版心的比例，默认 0.92（贴满容易多挤出一页）")
    p.add_argument("--no-break-before", action="store_true", help="第一张图不先分页")
    p.add_argument("--no-break-after", action="store_true", help="最后一张图后不加分页")
    p.set_defaults(func=cmd_replace)

    p = sub.add_parser("check", help="校验包结构与图片尺寸")
    p.add_argument("docx")
    p.set_defaults(func=cmd_check)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
