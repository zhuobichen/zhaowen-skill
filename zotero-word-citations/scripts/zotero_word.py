# -*- coding: utf-8 -*-
"""把 Word 手稿里的 author-year 引用换成 **Zotero 活字段**，并可选生成可点击跳转的定稿版。

目的：投稿时不必手工插文献。

三个子命令
----------
    python zotero_word.py link      # 扫 refs.bib → 匹配 Zotero 库，产出 zotero_items.json
    python zotero_word.py build     # 读缓存，生成带 Zotero 活字段的 docx（写作期用）
    python zotero_word.py finalize  # 生成静态定稿版：引用 ↔ 参考文献 可点击跳转

为什么是两版：**域与跳转互斥**。域的结果文本是缓存，Zotero 一 Refresh 就整段重写，
埋在里面的书签/超链接会被冲掉。所以写作期用 `build`（能刷新），投稿前用 `finalize`
（能跳转但不再自动更新）。详见 SKILL.md。

字段格式的**依据**（全部挖自 Zotero 自身源码，不是推测）
--------------------------------------------------------
1. `chrome/content/zotero/xpcom/integration.js`（在 Zotero 安装目录的 `app/omni.ja` 内）
   - `Field.setCode()`：
         ITEM CSL_CITATION ${code}          # code = Citation.serialize()
         BIBL ${code} CSL_BIBLIOGRAPHY
     Word 插件 DLL 会在前面再加 `ADDIN ZOTERO_`，所以 instrText 实际是
         ADDIN ZOTERO_ITEM CSL_CITATION {json}
     ⚠️ 用 pywin32 的 `Fields.Add(rng, 81, text, True)` 时 **Word 自动加 "ADDIN "**，
        所以 text 要从 `ZOTERO_ITEM` 起写，自己别再加前缀（加了会变成 ADDIN ADDIN）。
     ⚠️ 但**直写 OOXML** 时没人替你补，必须自己写 ` ADDIN `。
   - `Citation.serialize()` = `JSON.stringify({citationID, citationItems, properties})`
   - 叙述式引用（作者写在正文里，如 "Alexeeff et al. (2015)"）：
       citationItems[i]["suppress-author"] = true
   - 参考文献域的数据只是 `{uncited:[], omitted:[], custom:[]}` —— 条目由 Zotero 扫全文推导
   - `Session.init` 里 `if (!data.prefs.fieldType) ... setDocPrefs()`：
     **文档首选项必须带 `prefs.fieldType`**（Word 是 "Field"），否则 Refresh 会弹对话框
2. 随 Zotero 安装的 `Zotero.dotm` 的 `docProps/custom.xml`：文档级样式偏好存成
   **自定义文档属性** `ZOTERO_PREF_1`，值是 XML（data-version 3）；
   `DocumentData.unserialize` 先试 `JSON.parse` 再回落到 XML。
3. ⚠️ **本机不要走 Word COM**：`Word.Application` 的 ProgID 被 **WPS 劫持**
   （`Name` 报 "Microsoft Word"、`Version` 12.0 就是破绽），`Fields.Add` 会静默不生效。
   所以这里**直接拼 OOXML**（复制壳 → 换 document.xml → 补 custom.xml）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path


# ── 可配置项 ────────────────────────────────────────────────────────────
# 所有路径都能用命令行参数或环境变量覆盖；下面的默认值只针对当前这台机器。
def _env_path(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or default)


# Zotero **数据目录**（`zotero.sqlite` 和 `styles/` 都在里面）。
# ⚠️ 不是 `~/Zotero`。真实位置看 Zotero 的 prefs.js:
#      extensions.zotero.dataDir
ZOTERO_DATA = _env_path("ZOTERO_DATA_DIR", r"E:/CodeProject/Zotero")
ZOTERO_DB = ZOTERO_DATA / "zotero.sqlite"
STYLES_DIR = ZOTERO_DATA / "styles"

BBT_RPC = "http://127.0.0.1:23119/better-bibtex/json-rpc"
ZOTERO_API = "http://127.0.0.1:23119/api/users/0/items"

# 手稿与期刊模板壳（`--md` / `--shell` 可覆盖）
MANUSCRIPT = _env_path(
    "ZOTERO_WORD_MD",
    r"E:/CodeProject/Agent_Papers/projects/O3_DataFusion_Policy/manuscript/Manuscript_Draft.md")
SHELLS = {
    "aaqr": _env_path("ZOTERO_WORD_SHELL_AAQR",
                      r"E:/CodeProject/Agent_Papers/templates/journal_papers/AAQR/template/aaqr_word_shell.docx"),
    "ae": _env_path("ZOTERO_WORD_SHELL_AE",
                    r"E:/CodeProject/Agent_Papers/templates/journal_papers/AE/template/ae_word_shell.docx"),
}
# 映射缓存默认放在手稿的 build/ 旁边，不写进 skill 目录
CACHE = Path(os.environ.get("ZOTERO_WORD_CACHE")
             or (MANUSCRIPT.parent / "build" / "zotero_items.json"))

STYLES = {
    "aaqr": "http://www.zotero.org/styles/aerosol-and-air-quality-research",
    "ae": "http://www.zotero.org/styles/atmospheric-environment",
}
# 期刊样式没装进 Zotero 时的退路（见 SKILL.md「样式必须装进 Zotero」一节）
FALLBACK_STYLE = "http://www.zotero.org/styles/elsevier-harvard"

WD_FIELD_ADDIN = 81


# ── 与 md2tex.py 完全一致的引用解析（保持两者产出同源）────────────────
CITE_RE = re.compile(
    r"\(((?<![\w.])[A-Z][A-Za-zÀ-ɏ'.-]*"
    # 多词机构作者（'U.S. EPA'）—— 照抄 md2tex.py 的 CITE_RE 会漏掉它们，
    # 导致正文里独立的 '(U.S. EPA, 2015)' 不被当成引用（实测踩到）。
    r"(?:\s+[A-Z][A-Za-zÀ-ɏ'.-]*)*"
    r"(?: et al\.| and [A-Z][A-Za-zÀ-ɏ'.-]+| & [A-Z][A-Za-zÀ-ɏ'.-]+)?"
    r",? \d{4}[a-z]?(?:;\s*[^()]*?\d{4}[a-z]?)*)\)"
)
PART_RE = re.compile(
    r"^((?<![\w.])[A-Z][A-Za-zÀ-ɏ'.-]*(?:\s+[A-Z][A-Za-zÀ-ɏ'.-]*)*"
    r"(?: et al\.| and [A-Z][A-Za-zÀ-ɏ'.-]+| & [A-Z][A-Za-zÀ-ɏ'.-]+)?)"
    r",\s*(\d{4}[a-z]?)$"
)
# 叙述式引用：作者名在正文，年份在括号里 —— "Alexeeff et al. (2015) 指出"
NARRATIVE_RE = re.compile(
    r"((?<![\w.])[A-Z][A-Za-zÀ-ɏ'.-]*(?:\s+[A-Z][A-Za-zÀ-ɏ'.-]*)*"
    r"(?: et al\.| and [A-Z][A-Za-zÀ-ɏ'.-]+| & [A-Z][A-Za-zÀ-ɏ'.-]+)?)"
    r"\s\((\d{4}[a-z]?(?:,\s*\d{4}[a-z]?)*)\)"
)
ORG_CITE_KEYS = {"U.S. EPA": "usepa"}


def cite_key(label: str) -> str:
    """`Skipper et al., 2021` → `skipper2021`（照抄 md2tex.py）。"""
    label = label.strip()
    m = re.match(r"^(.*?),\s*(\d{4}[a-z]?)$", label)
    if not m:
        return re.sub(r"[^a-zA-Z0-9]", "", label).lower()
    name, year = m.group(1), m.group(2)
    name = re.split(r"\s+et al\.|\s+and\s+|\s+&\s+", name)[0].strip()
    if name in ORG_CITE_KEYS:
        return f"{ORG_CITE_KEYS[name]}{year}"
    return f"{re.sub(r'[^a-zA-Z]', '', name).lower()}{year}"


def parse_bib(path: Path) -> dict[str, dict]:
    """refs.bib → {key: {type, 各字段}}。"""
    text = path.read_text(encoding="utf-8")
    out: dict[str, dict] = {}
    for blk in re.split(r"(?m)^(?=@)", text):
        m = re.match(r"@(\w+)\{([^,]+),", blk)
        if not m:
            continue
        fields = {}
        for fm in re.finditer(r"(\w+)\s*=\s*\{(.*?)\}\s*,?\s*$", blk, re.S | re.M):
            fields[fm.group(1).lower()] = re.sub(r"\s+", " ", fm.group(2)).strip()
        out[m.group(2).strip()] = {"_type": m.group(1).lower(), **fields}
    return out


# ── Zotero 通信 ─────────────────────────────────────────────────────────
def _curl(args: list[str], timeout: int = 30) -> str:
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout), *args],
                       capture_output=True, text=True, encoding="utf-8")
    return r.stdout


def bbt(method: str, params):
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1})
    try:
        return json.loads(_curl(["-X", "POST", BBT_RPC,
                                 "-H", "Content-Type: application/json", "-d", body]))
    except json.JSONDecodeError:
        return {}


def _search_pool(probe: str) -> dict:
    res = bbt("item.search", [probe]).get("result") or []
    return {it["id"]: it for it in res if isinstance(it, dict) and it.get("id")}


def _bbt_search_api(q: str) -> list[dict]:
    """BBT 的 /better-bibtex/search 端点（JSON-RPC 的 item.search 不认 `doi:` 前缀）。"""
    import urllib.parse
    url = ("http://127.0.0.1:23119/better-bibtex/search?format=json&q="
           + urllib.parse.quote(q))
    try:
        res = json.loads(_curl([url], timeout=25))
    except json.JSONDecodeError:
        return []
    if not isinstance(res, list):
        return []
    # 这个端点回的是 citekey/uri，不带 Zotero 的 id → 补上，统一成 item.search 的形状
    for it in res:
        if not isinstance(it, dict) or it.get("id"):
            continue
        ck = it.get("citekey")
        if not ck:
            continue
        zk = citekey_to_itemkey(ck)
        if zk:
            it["id"] = (f"http://zotero.org/users/{_user_id()}/items/{zk}")
    return [it for it in res if it.get("id")]


def citekey_to_itemkey(citekey: str) -> str | None:
    """BBT 的 citation key → Zotero item key（key 存在 itemData 的 citationKey 字段）。"""
    con = sqlite3.connect(f"file:{ZOTERO_DB.as_posix()}?immutable=1", uri=True)
    try:
        row = con.execute(
            "SELECT i.key FROM items i "
            "JOIN itemData d ON d.itemID = i.itemID "
            "JOIN itemDataValues v ON v.valueID = d.valueID "
            "JOIN fields f ON f.fieldID = d.fieldID "
            "WHERE f.fieldName = 'citationKey' AND v.value = ? LIMIT 1",
            (citekey,)).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def _user_id() -> str:
    """PDF/条目 URI 里的 userID（本地库固定）。"""
    global _UID
    try:
        return _UID
    except NameError:
        pass
    _UID = "0"
    try:
        con = sqlite3.connect(f"file:{ZOTERO_DB.as_posix()}?immutable=1", uri=True)
        row = con.execute("SELECT value FROM settings WHERE setting='account' "
                          "AND key='userID'").fetchone()
        con.close()
        if row and row[0]:
            _UID = str(row[0])
    except sqlite3.Error:
        pass
    return _UID


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", str(s).lower())


def _families(it: dict) -> str:
    """条目的作者姓氏串（可比较）。author 可能是 [{family,...}] 或字符串。"""
    au = it.get("author")
    if isinstance(au, list):
        return " ".join(_norm(a.get("family") or a.get("literal") or "")
                        for a in au if isinstance(a, dict))
    return _norm(au or "")


def _year_of(it: dict) -> str:
    """条目年份。⚠️ BBT 的 item.search 有时 `date` 为 None，年份只在 `issued` 里。"""
    d = it.get("date")
    if d:
        m = re.search(r"\d{4}", str(d))
        if m:
            return m.group(0)
    iss = it.get("issued")
    if isinstance(iss, dict):
        dp = iss.get("date-parts")
        if dp and dp[0] and dp[0][0]:
            return str(dp[0][0])
    return ""


def _tokens(title: str) -> list[str]:
    stop = {"the", "a", "an", "of", "for", "and", "in", "on", "to", "with",
            "from", "by", "as", "at", "using", "based"}
    return [w for w in _norm(title).split() if len(w) > 4 and w not in stop]


def match_items(bib: dict[str, dict]) -> tuple[dict[str, str], list[str]]:
    """每条 bib 条目在 Zotero 里找对应项：姓氏 + 标题词 + 年份三者打分。"""
    mapping: dict[str, str] = {}
    missing: list[str] = []
    for key, e in bib.items():
        surname = ""
        au = e.get("author", "")
        if au:
            first = re.split(r"\s+and\s+", au)[0]
            surname = first.split(",")[0].strip().split()[-1] if first else ""
        year = e.get("year", "")
        toks = _tokens(re.sub(r"[{}]", "", e.get("title", "")))
        if not toks:
            missing.append(key)
            continue
        pool: dict = {}
        for probe in toks[:3]:
            pool.update(_search_pool(probe))
        best, best_score = None, 0
        for it in pool.values():
            ts = _norm(it.get("title") or "")
            score = sum(1 for t in toks if t in ts)
            if surname and surname.lower() in _families(it):
                score += 2
            if year and _year_of(it) == year:
                score += 3
            if score > best_score:
                best, best_score = it, score
        need = max(4, 3 + (2 if surname else 0) + (3 if year else 0) - 1)
        if best and best_score >= need:
            mapping[key] = best["id"]
        else:
            missing.append(key)

    # 兜底：BBT 的 item.search 偶尔漏召回，改用「姓氏 + 年份」和「DOI」再查一遍
    still: list[str] = []
    for key in missing:
        e = bib[key]
        au = e.get("author", "")
        surname = ""
        if au:
            first = re.split(r"\s+and\s+", au)[0]
            surname = first.split(",")[0].strip().strip("{}").split()[-1] if first else ""
        year = e.get("year", "")
        hit, unknown_year = None, None
        if surname and len(surname) > 3:
            for it in (_search_pool(surname)).values():
                if surname.lower() not in _families(it):
                    continue
                iy = _year_of(it)
                if year and iy == year:
                    hit = it
                    break
                # 年份**取不到**才肯放宽；取到了但不同 → 是别人，否决
                # （放过会把 chang2017 误配到 2019 那篇 M³ Fusion）
                if not iy:
                    unknown_year = unknown_year or it
        hit = hit or unknown_year
        if not hit and e.get("doi"):
            res = _bbt_search_api("doi:" + e["doi"])
            if res:
                hit = res[0]
        if hit and hit.get("id"):
            mapping[key] = hit["id"]
            print(f"  ↩ 兜底命中 {key} ← {str(hit.get('title'))[:52]}")
        else:
            still.append(key)
    return mapping, still


def item_ids(keys: list[str]) -> dict[str, int]:
    """Zotero 数字 itemID（字段里的 `id` 用它）。库被占用，走 immutable 快照只读。"""
    con = sqlite3.connect(f"file:{ZOTERO_DB.as_posix()}?immutable=1", uri=True)
    try:
        out = {}
        for k in keys:
            row = con.execute("SELECT itemID FROM items WHERE key=?", (k,)).fetchone()
            if row:
                out[k] = row[0]
        return out
    finally:
        con.close()


def fetch_csl(zkey: str) -> dict | None:
    try:
        arr = json.loads(_curl([f"{ZOTERO_API}/{zkey}?format=csljson"], timeout=25))
        return arr[0] if arr else None
    except (json.JSONDecodeError, IndexError):
        return None


def cmd_link(args) -> int:
    bib = parse_bib(args.bib)
    print(f"refs.bib 条目：{len(bib)}")
    mapping, missing = match_items(bib)
    print(f"匹配到 Zotero：{len(mapping)}    未匹配：{len(missing)}")
    if missing:
        for k in missing:
            e = bib[k]
            print(f"  ✗ {k:<18} {e.get('author','')[:40]:<42} {e.get('year','')}")

    ids = item_ids([u.rsplit("/", 1)[-1] for u in mapping.values()])
    cache = {}
    for k, uri in mapping.items():
        zkey = uri.rsplit("/", 1)[-1]
        csl = fetch_csl(zkey)
        cache[k] = {
            "uri": uri,
            "zkey": zkey,
            "itemID": ids.get(zkey),
            "csl": csl,
            "bib_year": bib[k].get("year", ""),
            "bib_author": bib[k].get("author", ""),
            "bib_title": bib[k].get("title", ""),
        }
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {CACHE}  （{len(cache)} 条，含 CSL-JSON 与 itemID）")
    if args.mark_missing:
        mf = CACHE.with_name("zotero_missing.json")
        mf.write_text(json.dumps(
            {k: {kk: vv for kk, vv in bib[k].items()} for k in missing},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"→ {mf}  （未入库清单，需先加进 Zotero 才能程序化引用）")
    return 0


# ── 构建 Word ───────────────────────────────────────────────────────────
def _json_min(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _bare_csl(item: dict) -> dict:
    """CSL-JSON 去掉库内标识，留纯书目字段。"""
    drop = {"id", "citation-key", "note", "abstract", "accessed", "language",
            "license", "URL", "ISSN", "original-title", "source", "status"}
    return {k: v for k, v in item.items() if k not in drop and v not in (None, "", [])}


def build_citation_instr(entries: list[dict], display: str, cite_id: str,
                         suppress_author: bool = False) -> str:
    """一条 CSL_CITATION 字段指令（返回值不含 "ADDIN " —— Word 自己加）。"""
    cites = []
    for e in entries:
        ci: dict = {"uris": [e["uri"]], "itemData": _bare_csl(e["csl"])}
        if e["itemID"] is not None:
            ci["id"] = e["itemID"]
        if suppress_author:
            ci["suppress-author"] = True          # 叙述式引用：作者已在正文里
        cites.append(ci)
    payload = {
        "citationID": cite_id,
        "properties": {
            "formattedCitation": display,
            "plainCitation": display,
            "noteIndex": 0,
        },
        "citationItems": cites,
        "schema": ("https://github.com/citation-style-language/schema/raw/"
                   "master/csl-citation.json"),
    }
    return "ZOTERO_ITEM CSL_CITATION " + _json_min(payload)


def build_bibl_instr() -> str:
    """参考文献域。数据就是空的 uncited/omitted/custom，Zotero 自行汇集正文引用。"""
    return ("ZOTERO_BIBL " + _json_min({"uncited": [], "omitted": [], "custom": []})
            + " CSL_BIBLIOGRAPHY")


def doc_prefs_xml(style_id: str, session: str, version: str = "7.0",
                  has_bibliography: bool = True) -> str:
    """ZOTERO_PREF_1 的值 —— 照 Zotero.dotm 里那份的实际格式（XML, data-version 3）。

    ⚠️ `prefs.fieldType` 必须写。`Session.init` 里：
        if (!data.prefs.fieldType) { ... await this.setDocPrefs(); }
    缺了它，用户点 Refresh 会先弹「文档首选项」对话框。Word 的 primaryFieldType
    是 "Field"（Bookmark 是旧模式，见 zoteroWinWordIntegration.mjs 的
    primaryFieldType/secondaryFieldType）。
    """
    from xml.sax.saxutils import escape
    return (f'<data data-version="3" zotero-version="{escape(version)}">'
            f'<session id="{escape(session)}"/>'
            f'<style id="{escape(style_id)}" '
            f'hasBibliography="{1 if has_bibliography else 0}" '
            f'bibliographyStyleHasBeenSet="0"/>'
            f'<prefs><pref name="fieldType" value="Field"/></prefs></data>')


# 正文 token 类型
T_TEXT, T_CITE, T_NARR = "text", "cite", "narr"


def tokenize_paragraph(text: str, cache: dict, missing: list[str]) -> list[tuple]:
    """把一段正文切成 [('text', s) | ('cite', entries, 原文) | ('narr', 作者, entries, 年份)]。"""
    # 先标出所有引用位置（含叙述式），再按位置切段
    spans = []
    for m in NARRATIVE_RE.finditer(text):
        # 可能一年多个年份：'He et al. (2015, 2016)'
        ks = [cite_key(f"{m.group(1)}, {y.strip()}")
              for y in m.group(2).split(",") if y.strip()]
        ks = [k for k in ks if k in cache]
        if ks:
            spans.append((m.start(), m.end(), T_NARR, m.group(1), ks, m.group(2)))
    for m in CITE_RE.finditer(text):
        parts = []
        for part in m.group(1).split(";"):
            pm = PART_RE.match(part.strip())
            if pm:
                k = cite_key(f"{pm.group(1)}, {pm.group(2)}")
                if k in cache:
                    parts.append((k, part.strip()))
                else:
                    missing.append(k)
        if parts:
            # 若整段已被叙述式覆盖（同一起点），跳过避免重复
            if any(s[0] <= m.start() < s[1] for s in spans):
                continue
            spans.append((m.start(), m.end(), T_CITE, None, parts, m.group(0)))

    spans.sort(key=lambda s: s[0])
    out, pos = [], 0
    for start, end, kind, author, payload, raw in spans:
        if start < pos:          # 与上一个重叠，跳过
            continue
        if start > pos:
            out.append((T_TEXT, text[pos:start]))
        out.append((kind, author, payload, raw))
        pos = end
    if pos < len(text):
        out.append((T_TEXT, text[pos:]))
    return out


def strip_md(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"\1", s)
    return s.replace("`", "")


def read_manuscript(path: Path):
    """→ (title, [(kind, text)])，kind ∈ title/h1/h2/p/kw。"""
    lines = path.read_text(encoding="utf-8").split("\n")
    title, blocks = "", []
    for ln in lines:
        s = ln.rstrip()
        if s.startswith("# ") and not title:
            title = strip_md(s[2:]).strip()
        elif s.startswith("### "):
            blocks.append(("h2", strip_md(s[4:]).strip()))
        elif s.startswith("## "):
            blocks.append(("h1", strip_md(s[3:]).strip()))
        elif s.startswith("# "):
            blocks.append(("h1", strip_md(s[2:]).strip()))
        elif s.startswith("---") or s.startswith("**Manuscript Draft**"):
            continue
        elif re.match(r"^\*\*\(Word count", s) or not s.strip():
            continue
        elif s.startswith("**Keywords**"):
            blocks.append(("kw", strip_md(s).strip()))
        else:
            blocks.append(("p", s.strip()))
    return title, blocks


def xml_esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def field_xml(instr: str, display: str) -> str:
    """Word 域的标准五段式（begin / instrText / separate / 显示文本 / end）。

    ⚠️ 这里必须**自己**写 ` ADDIN ` 前缀 —— 走 COM 的 `Fields.Add(..., 81, ...)`
    是 Word 替你补的；直接写 XML 没人补，漏了就变成 Zotero 认不出的域。
    """
    return (
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        f'<w:r><w:instrText xml:space="preserve"> ADDIN {xml_esc(instr)}</w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        f'<w:r><w:t xml:space="preserve">{xml_esc(display)}</w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )


def para_xml(style: str, runs: str) -> str:
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{runs}</w:p>'


def text_run(s: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{xml_esc(s)}</w:t></w:r>'


def tokens_to_runs(tokens: list[tuple], cache: dict, counter: list) -> str:
    """一段正文的 token 序列 → runs XML；引用位置产出 Zotero 域。"""
    out = []
    for tk in tokens:
        kind = tk[0]
        if kind == T_TEXT:
            if tk[1]:
                out.append(text_run(tk[1]))
        elif kind == T_NARR:
            _, author, keys, years = tk
            out.append(text_run(f"{author} "))        # 作者留在正文
            entries = [cache[k] for k in keys]
            instr = build_citation_instr(entries, f"({years})",
                                         uuid.uuid4().hex[:8], suppress_author=True)
            out.append(field_xml(instr, f"({years})"))
            counter[0] += 1
        else:
            _, _, parts, raw = tk
            entries = [cache[k] for k, _ in parts]
            instr = build_citation_instr(entries, raw, uuid.uuid4().hex[:8])
            out.append(field_xml(instr, raw))
            counter[0] += 1
    return "".join(out)


def resolve_styles(shell: Path) -> dict:
    """从壳的 styles.xml 里认出实际样式名（AE 壳与 AAQR 壳的命名未必一致）。"""
    with zipfile.ZipFile(shell) as z:
        s = z.read("word/styles.xml").decode("utf-8")

    def ids():
        return set(re.findall(r'<w:style [^>]*w:styleId="([^"]+)"', s))

    have = ids()

    def pick(exact: list[str], contains: str, exclude: tuple = ()) -> str | None:
        for e in exact:
            if e in have:
                return e
        for i in sorted(have):
            if contains in i and not any(x in i for x in exclude):
                return i
        return None

    return {
        "title": pick(["AAQRTitle", "AETitle"], "Title", ("Subtitle",)),
        "h1": pick(["AAQRH1", "AEH1"], "H1", ("H2",)),
        "h2": pick(["AAQRH2", "AEH2"], "H2"),
        "body": pick(["AAQRBody", "AEBody"], "Body"),
    }


CUSTOM_PROP_FMTID = "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"


def cmd_build(args) -> int:
    if not CACHE.exists():
        print("先跑 `link` 生成 zotero_items.json", file=sys.stderr)
        return 2
    cache = json.loads(CACHE.read_text(encoding="utf-8"))

    shell = getattr(args, "shell", None) or SHELLS[args.journal]
    if not shell.exists():
        print(f"找不到壳：{shell}", file=sys.stderr)
        return 2

    title, blocks = read_manuscript(args.md)
    style_id = STYLES[args.journal]
    out_path = Path(args.out)
    S = resolve_styles(shell)
    if not all(S.values()):
        print(f"壳里样式认不全：{S}", file=sys.stderr)
        return 2

    counter, miss = [0], []
    body: list[str] = [
        para_xml(S["title"], text_run(title)),
        para_xml(S["body"], text_run("[First Author 1, Second Author 2]")),
        para_xml(S["body"], text_run("[1 Department, Institution, City, Postcode, Country]")),
        para_xml(S["body"], text_run("[* Correspondence: name@example.edu]")),
    ]
    for kind, text in blocks:
        if kind == "h1":
            m = re.match(r"^(\d+)\.\s*(.+)$", text)
            body.append(para_xml(S["h1"], text_run(
                f"{m.group(1)}  {m.group(2)}" if m else text)))
            if "Reference" in text:
                # 参考文献节：只放 Zotero 的参考文献域，条目由 Zotero 汇集正文引用生成
                body.append(para_xml(S["body"], field_xml(build_bibl_instr(), "")))
                counter[0] += 1
        elif kind == "h2":
            m = re.match(r"^(\d+\.\d+)\.?\s*(.+)$", text)
            body.append(para_xml(S["h2"], text_run(
                f"{m.group(1)}  {m.group(2)}" if m else text)))
        elif kind == "kw":
            body.append(para_xml(S["body"], text_run(text)))
        else:
            toks = tokenize_paragraph(strip_md(text), cache, miss)
            body.append(para_xml(S["body"], tokens_to_runs(toks, cache, counter)))

    # 复用壳的根标签与 sectPr —— 行号（w:lnNumType）和页脚页码都在 sectPr 里
    with zipfile.ZipFile(shell) as z:
        src = z.read("word/document.xml").decode("utf-8")
        parts = {n: z.read(n) for n in z.namelist()}
    root = src[: src.index("<w:body>") + len("<w:body>")]
    sect = re.search(r"<w:sectPr.*?</w:sectPr>", src, re.S).group(0)
    docxml = root + "".join(body) + sect + "</w:body></w:document>"

    # ZOTERO_PREF_1 —— 文档级样式偏好，存成自定义文档属性（照 Zotero.dotm 的实际格式）
    custom = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/'
        '2006/custom-properties" xmlns:vt="http://schemas.openxmlformats.org/'
        'officeDocument/2006/docPropsVTypes">'
        f'<property fmtid="{CUSTOM_PROP_FMTID}" pid="2" name="ZOTERO_PREF_1">'
        f'<vt:lpwstr>{xml_esc(doc_prefs_xml(style_id, uuid.uuid4().hex[:8]))}'
        '</vt:lpwstr></property></Properties>')

    ct = parts["[Content_Types].xml"].decode("utf-8").replace(
        "</Types>",
        '<Override PartName="/docProps/custom.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.custom-properties+xml"/></Types>')
    rels = parts["_rels/.rels"].decode("utf-8").replace(
        "</Relationships>",
        '<Relationship Id="rIdZoteroPref" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/custom-properties" '
        'Target="docProps/custom.xml"/></Relationships>')

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            if name == "word/document.xml":
                data = docxml.encode("utf-8")
            elif name == "[Content_Types].xml":
                data = ct.encode("utf-8")
            elif name == "_rels/.rels":
                data = rels.encode("utf-8")
            zout.writestr(name, data)
        zout.writestr("docProps/custom.xml", custom.encode("utf-8"))

    print(f"✓ 生成 {out_path}")
    print(f"  Zotero 域 {counter[0]} 个（引用 + 1 个参考文献域），样式 {style_id}")
    print(f"  壳 {shell.name}，段落 {len(body)}")
    if miss:
        print(f"  ⚠️ 未入库、留纯文本的引用 {len(set(miss))} 条：{sorted(set(miss))}")
    return 0


# ── 带跳转的定稿版（正文引用 ↔ 参考文献 内部超链接）────────────────────
# ⚠️ 两件事要先说清：
#   1. **Zotero 原生不做这个。** 官方明确说无法自动创建可点击链接；这是长期
#      未实现的需求（zotero/zotero#4263）。EndNote 有此功能，Zotero 没有。
#   2. **跳转与活字段互斥。** 引用和参考文献都是 Zotero 域，而域的结果文本在
#      每次 Refresh 时会被整段重写 —— 埋在域里的书签/超链接会被冲掉。
#    所以这一版是**静态定稿**：正文引用与参考文献条目都成纯文本，但互相可跳。
#    排版仍走 Zotero 自己的 CSL 引擎（`item.bibliography`），与期刊格式一致。
#    写作期间用带活字段的那版，投稿前跑这个生成定稿版。


def _citekey_of(zkeys: list[str]) -> dict[str, str]:
    """Zotero item key → BBT citation key。"""
    r = bbt("item.citationkey", [zkeys]).get("result")
    return r if isinstance(r, dict) else {}


def _render_bibliography(citekeys: list[str], style_id: str) -> tuple[list[str], str]:
    """用 Zotero 的 CSL 引擎渲染参考文献，返回 (逐条目文本, 实际用的样式)。

    ⚠️ 期刊样式**没装进 Zotero** 时会报 "CSL style not found"。BBT 不会像
    Zotero 界面那样自动去 CSL 仓库下载，所以要显式降级并如实报告用了哪个样式
    —— 编出来的参考文献格式会不一样，不能默默换掉。
    """
    for sid in (style_id, FALLBACK_STYLE):
        r = bbt("item.bibliography", [citekeys, {"id": sid}])
        res = r.get("result")
        if isinstance(res, str) and res.strip():
            return [e.strip() for e in res.split("\n") if e.strip()], sid
        msg = json.dumps(r.get("error") or {}, ensure_ascii=False)
        if sid == style_id:
            print(f"  ⚠️ 样式 {sid.rsplit('/', 1)[-1]} 不可用（{msg[:70]}），"
                  f"降级到 {FALLBACK_STYLE.rsplit('/', 1)[-1]}")
    return [], style_id


def _match_entry(entry: str, bibkeys: list[str], cache: dict) -> str | None:
    """渲染好的条目 → bib key。靠标题词 + 年份打分（顺序不与 bib 一一对应）。"""
    et = _norm(entry)
    best, score = None, 0
    for k in bibkeys:
        csl = cache[k].get("csl") or {}
        toks = _tokens(re.sub(r"<[^>]+>", "", str(csl.get("title") or "")))
        s = sum(1 for t in toks if t in et)
        y = _year_of(csl)
        if y and y in entry:
            s += 3
        if s > score:
            best, score = k, s
    return best if score >= 4 else None


def link_run(text: str, anchor: str | None) -> str:
    """一段文本；给了 anchor 就包成指向该书签的超链接。

    ⚠️ **故意不加 `Hyperlink` 字符样式** —— 加了会变蓝带下划线，投稿稿的正文
    引用不该是蓝色。不加样式照样能跳（Word 内部锚点点击即跳）。
    """
    r = text_run(text)
    if not anchor:
        return r
    return f'<w:hyperlink w:anchor="{anchor}" w:history="1">{r}</w:hyperlink>'


def cmd_finalize(args) -> int:
    if not CACHE.exists():
        print("先跑 `link` 生成 zotero_items.json", file=sys.stderr)
        return 2
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    shell = getattr(args, "shell", None) or SHELLS[args.journal]
    style_id = STYLES[args.journal]
    title, blocks = read_manuscript(args.md)
    S = resolve_styles(shell)
    out_path = Path(args.out)

    # 一遍：切 token，同时收集正文真正引用到的 key
    miss: list[str] = []
    parsed: list[tuple[str, object]] = []
    used: list[str] = []
    for kind, text in blocks:
        if kind in ("h1", "h2", "kw"):
            parsed.append((kind, text))
            continue
        toks = tokenize_paragraph(strip_md(text), cache, miss)
        parsed.append(("p", toks))
        for tk in toks:
            if tk[0] == T_CITE:
                used += [k for k, _ in tk[2]]
            elif tk[0] == T_NARR:
                used += list(tk[2])
    used = list(dict.fromkeys(used))               # 去重保序

    # 渲染参考文献（顺序按样式规定）
    z2c = _citekey_of([cache[k]["zkey"] for k in used])
    cks = [z2c[cache[k]["zkey"]] for k in used if cache[k]["zkey"] in z2c]
    entries, used_style = _render_bibliography(cks, style_id)
    print(f"参考文献：Zotero 渲染 {len(entries)} 条（正文引用 {len(used)} 个 key）"
          f"，样式 {used_style.rsplit('/', 1)[-1]}")
    if used_style != style_id:
        print(f"  ⚠️ 用的是退路样式，**格式与 {args.journal.upper()} 要求不同**，"
              f"投稿前须先装好期刊样式再重跑")

    # 条目 → bib key，并编号做书签
    ref_no: dict[str, int] = {}
    unmatched: list[str] = []
    for i, e in enumerate(entries, 1):
        k = _match_entry(e, used, cache)
        if k is None:
            unmatched.append(e[:70])
        elif k not in ref_no:
            ref_no[k] = i
    print(f"  条目↔key 对上 {len(ref_no)}/{len(used)}"
          + (f"，对不上 {len(unmatched)} 条" if unmatched else ""))
    for u in unmatched:
        print(f"     ✗ {u}")

    def anchor_of(keys: list[str]) -> str | None:
        """一组 key → 超链接锚点。只在该组所有条目都定位到时才建链接，宁缺勿错。"""
        nos = [ref_no.get(k) for k in keys]
        if not nos or any(n is None for n in nos):
            return None
        return f"_Ref{nos[0]}"

    counter, body = [0], [
        para_xml(S["title"], text_run(title)),
        para_xml(S["body"], text_run("[First Author 1, Second Author 2]")),
        para_xml(S["body"], text_run("[1 Department, Institution, City, Postcode, Country]")),
        para_xml(S["body"], text_run("[* Correspondence: name@example.edu]")),
    ]
    for kind, payload in parsed:
        if kind == "h1":
            m = re.match(r"^(\d+)\.\s*(.+)$", payload)
            body.append(para_xml(S["h1"], text_run(
                f"{m.group(1)}  {m.group(2)}" if m else payload)))
            if "Reference" in payload:
                # 参考文献：静态条目 + 每条一个书签，供正文引用跳转
                for e in entries:
                    k = _match_entry(e, used, cache)
                    n = ref_no.get(k) if k else None
                    txt = text_run(e)
                    if n is None:
                        body.append(para_xml(S["body"], txt))
                    else:
                        counter[0] += 1
                        bid = counter[0]
                        body.append(para_xml(
                            S["body"],
                            f'<w:bookmarkStart w:id="{bid}" w:name="_Ref{n}"/>'
                            f'{txt}<w:bookmarkEnd w:id="{bid}"/>'))
        elif kind == "h2":
            m = re.match(r"^(\d+\.\d+)\.?\s*(.+)$", payload)
            body.append(para_xml(S["h2"], text_run(
                f"{m.group(1)}  {m.group(2)}" if m else payload)))
        elif kind == "kw":
            body.append(para_xml(S["body"], text_run(payload)))
        else:
            runs = []
            for tk in payload:
                if tk[0] == T_TEXT:
                    if tk[1]:
                        runs.append(text_run(tk[1]))
                elif tk[0] == T_NARR:
                    _, author, keys, years = tk
                    runs.append(text_run(f"{author} "))
                    runs.append(link_run(f"({years})", anchor_of(keys)))
                else:
                    # 多篇同引**逐篇**建链接（如正式发表 PDF 那样），而不是整组指向第一篇。
                    # ⚠️ 文本要按 raw 还原全部片段 —— 只按 tokenize 的 parts 拼，
                    #    会把「没入库」那几篇的作者从正文里悄悄删掉。
                    _, _, parts, raw = tk
                    frags = [f.strip() for f in raw[1:-1].split(";")]
                    inner = []
                    for i, frag in enumerate(frags):
                        if i:
                            inner.append(text_run("; "))
                        pm = PART_RE.match(frag)
                        k = (cite_key(f"{pm.group(1)}, {pm.group(2)}")
                             if pm else None)
                        n = ref_no.get(k) if k else None
                        inner.append(link_run(frag, f"_Ref{n}") if n
                                     else text_run(frag))
                    runs.append(text_run("(") + "".join(inner) + text_run(")"))
            body.append(para_xml(S["body"], "".join(runs)))

    # 包壳（与 build 相同：复用根标签 + sectPr，保证行号/页码设置不丢）
    with zipfile.ZipFile(shell) as z:
        src = z.read("word/document.xml").decode("utf-8")
        parts = {n: z.read(n) for n in z.namelist()}
    root = src[: src.index("<w:body>") + len("<w:body>")]
    sect = re.search(r"<w:sectPr.*?</w:sectPr>", src, re.S).group(0)
    docxml = root + "".join(body) + sect + "</w:body></w:document>"

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            if name == "word/document.xml":
                data = docxml.encode("utf-8")
            zout.writestr(name, data)

    n_links = docxml.count("<w:hyperlink ")
    print(f"✓ 生成 {out_path}")
    print(f"  书签 {counter[0]} 个，超链接 {n_links} 处")
    if miss:
        print(f"  ⚠️ 未入库、无链接的引用 {len(set(miss))} 条：{sorted(set(miss))}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("link", help="refs.bib → Zotero 条目映射")
    pl.add_argument("--bib", type=Path,
                    default=MANUSCRIPT.parent / "build" / "refs.bib")
    pl.add_argument("--mark-missing", action="store_true", default=True)
    pl.set_defaults(func=cmd_link)

    pb = sub.add_parser("build", help="生成带 Zotero 字段的 docx")
    pb.add_argument("--md", type=Path, default=MANUSCRIPT)
    pb.add_argument("--journal", choices=["aaqr", "ae"], default="aaqr")
    pb.add_argument("--out", default="manuscript_zotero_fields.docx")
    pb.add_argument("--shell", type=Path, default=None)
    pb.add_argument("--title-style", default="AAQRTitle")
    pb.set_defaults(func=cmd_build)

    pf = sub.add_parser("finalize", help="出带「引用↔参考文献」跳转的静态定稿版")
    pf.add_argument("--md", type=Path, default=MANUSCRIPT)
    pf.add_argument("--journal", choices=["aaqr", "ae"], default="aaqr")
    pf.add_argument("--out", default="manuscript_linked.docx")
    pf.add_argument("--shell", type=Path, default=None)
    pf.set_defaults(func=cmd_finalize)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
