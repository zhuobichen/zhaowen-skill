# -*- coding: utf-8 -*-
"""核验 `zotero_word.py build` 产出的 docx 是否真的能被 Zotero 认。

查七件事：
  1. 包结构完整
  2. 每个引用域是 begin/instrText/separate/显示文本/end 五段式
  3. 每条 instrText 带 ` ADDIN ZOTERO_` 前缀（漏了 Zotero 认不出）
  4. 每段 CSL_CITATION 的 JSON 可解析，且 citationItems 有 uris + itemData
  5. 显示文本 == properties.formattedCitation（不一致会导致 Refresh 后跳变）
  6. docProps/custom.xml 里有 ZOTERO_PREF_1，且其值是合法 XML
  7. document.xml 引用的样式名在 styles.xml 里都存在（否则 Word 会忽略样式）
另附：正文里还剩多少「(Xxx et al., 20xx)」形状的文字没转成域。
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CITE_SHAPE = re.compile(r"\([^()]*\b(?:19|20)\d{2}[a-z]?[^()]*\)")


def unesc(s: str) -> str:
    """XML 反转义 —— instrText 里的 JSON 引号存成 &quot;，Word 读时也是先反转义。"""
    return (s.replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1
                else r"E:/CodeProject/_refs/O3_manuscript_zotero_aaqr.docx")
    z = zipfile.ZipFile(path)
    fail: list[str] = []
    warn: list[str] = []

    # 1) 包结构
    print(f"文件 {path.name}  {path.stat().st_size/1024:.1f} KB")
    if z.testzip() is not None:
        fail.append("zip 损坏")
    for part in ("word/document.xml", "word/styles.xml", "[Content_Types].xml",
                 "_rels/.rels", "docProps/custom.xml"):
        if part not in z.namelist():
            fail.append(f"缺部件 {part}")
    print(f"  部件 {len(z.namelist())} 个")

    doc = z.read("word/document.xml").decode("utf-8")
    styles = z.read("word/styles.xml").decode("utf-8")

    # 2~5) 逐域检查
    paras = re.findall(r"<w:p[ >].*?</w:p>", doc, re.S)
    fields, n_bad_seq = [], 0
    for p in paras:
        runs = re.findall(r"<w:r[ >].*?</w:r>", p, re.S)
        i = 0
        while i < len(runs):
            if 'w:fldCharType="begin"' in runs[i]:
                instr = disp = None
                j = i + 1
                if j < len(runs) and "<w:instrText" in runs[j]:
                    instr = unesc("".join(re.findall(
                        r"<w:instrText[^>]*>(.*?)</w:instrText>", runs[j], re.S)))
                    j += 1
                if j < len(runs) and 'w:fldCharType="separate"' in runs[j]:
                    j += 1
                    if j < len(runs) and 'w:fldCharType="end"' not in runs[j]:
                        disp = unesc("".join(re.findall(
                            r"<w:t[^>]*>(.*?)</w:t>", runs[j], re.S)))
                        j += 1
                    if j < len(runs) and 'w:fldCharType="end"' in runs[j]:
                        fields.append((instr, disp))
                    else:
                        n_bad_seq += 1
                else:
                    n_bad_seq += 1
                i = j + 1
            else:
                i += 1
    print(f"  域 {len(fields)} 个（五段式不完整 {n_bad_seq} 个）")

    cites = bibls = 0
    for instr, disp in fields:
        if not instr.startswith(" ADDIN ZOTERO_"):
            fail.append(f"前缀不对：{instr[:40]!r}")
            continue
        if "CSL_CITATION" in instr:
            cites += 1
            try:
                data = json.loads(instr[instr.index("{"):])
            except json.JSONDecodeError as e:
                fail.append(f"CSL_CITATION JSON 坏：{e}")
                continue
            items = data.get("citationItems") or []
            if not items:
                fail.append("citationItems 为空")
            for ci in items:
                if not ci.get("uris"):
                    fail.append("citationItem 缺 uris")
                if not ci.get("itemData"):
                    fail.append("citationItem 缺 itemData")
            fc = (data.get("properties") or {}).get("formattedCitation")
            if fc != disp:
                warn.append(f"显示文本与 formattedCitation 不一致：{disp!r} vs {fc!r}")
        elif "CSL_BIBLIOGRAPHY" in instr:
            bibls += 1
        else:
            fail.append(f"未知域：{instr[:50]!r}")
    print(f"    引用域 {cites}   参考文献域 {bibls}")

    # 6) ZOTERO_PREF_1
    cust = z.read("docProps/custom.xml").decode("utf-8")
    m = re.search(r'name="ZOTERO_PREF_1"><vt:lpwstr>(.*?)</vt:lpwstr>', cust, re.S)
    if not m:
        fail.append("custom.xml 里没有 ZOTERO_PREF_1")
    else:
        pref = (m.group(1).replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&amp;", "&"))
        try:
            root = ElementTree.fromstring(pref)
            st = root.find("style")
            print(f"  ZOTERO_PREF_1 合法 XML：data-version={root.get('data-version')} "
                  f"style={st.get('id') if st is not None else '?'}")
        except ElementTree.ParseError as e:
            fail.append(f"ZOTERO_PREF_1 不是合法 XML：{e}")
    if "custom.xml" not in z.read("[Content_Types].xml").decode("utf-8"):
        fail.append("Content_Types 没声明 custom.xml")
    if "custom.xml" not in z.read("_rels/.rels").decode("utf-8"):
        fail.append(".rels 没挂 custom.xml")

    # 7) 样式名存在性
    have = set(re.findall(r'<w:style [^>]*w:styleId="([^"]+)"', styles))
    used = set(re.findall(r'<w:pStyle w:val="([^"]+)"/>', doc))
    missing = sorted(used - have)
    if missing:
        fail.append(f"用了不存在的样式：{missing}")
    print(f"  段落样式 {sorted(used)}")

    # 附：正文里还剩多少「引用形状」的文字
    # ⚠️ 必须**跳过域内部**的文字 —— 域的显示文本本身就是 "(Xxx et al., 20xx)"，
    #    不排除的话满屏都是假残留。
    plain: list[str] = []
    for p in paras:
        runs = re.findall(r"<w:r[ >].*?</w:r>", p, re.S)
        in_field = False
        for r in runs:
            if 'w:fldCharType="begin"' in r:
                in_field = True
                continue
            if 'w:fldCharType="end"' in r:
                in_field = False
                continue
            if in_field or "<w:instrText" in r:
                continue
            plain.append("".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", r, re.S)))
    raw = " ".join(plain)
    # 只保留真像“作者, 年”的（排除纯年份、(2003–2019) 这类区间）
    cand = sorted({s for s in CITE_SHAPE.findall(raw)
                   if re.search(r"[A-Za-z]{3,}[^()]*\b(?:19|20)\d{2}", s)})
    leftovers = cand
    print(f"  正文裸露的「作者-年」文字 {len(leftovers)} 处")
    for s in leftovers:
        print(f"     · {s}")

    print()
    for w in warn:
        print(f"  ⚠️  {w}")
    for f in fail:
        print(f"  ✗  {f}")
    print("结论：" + ("全部通过 ✓" if not fail else f"{len(fail)} 项不合格 ✗"))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
