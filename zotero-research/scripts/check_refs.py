"""Audit note coverage against a manuscript's reference list.

Answers three questions in one pass:
  1. Does the library hold every reference the manuscript cites?
  2. Which references still have only a stub note (auto-generated, abstract-only)?
  3. Which notes are real (long + five-section structure)?

Also reports per-note timestamps, because a note created and modified within
the same two minutes is machine-generated, while a gap of hours or days is
evidence a human edited it.

Usage:
    python check_refs.py <manuscript.md>
    python check_refs.py <manuscript.md> --json out.json
    python check_refs.py --timestamps            # whole-library note ages

The manuscript is expected to end with a reference list whose entries look
like `[12] AUTHOR ... DOI:10.xxxx/yyy.`
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile

ZOTERO_DIR = r"E:\CodeProject\Zotero"

# A note counts as a full reading note when it has all of these headings.
SECTIONS = ("核心摘要", "方法要点", "主要结果", "存疑")
MIN_FULL_NOTE = 2000


def snapshot(zotero_dir, tmpdir):
    """Copy zotero.sqlite (+wal/shm) so it can be read while Zotero runs."""
    dst = os.path.join(tmpdir, "z.sqlite")
    src = os.path.join(zotero_dir, "zotero.sqlite")
    for ext in ("", "-wal", "-shm"):
        s = src + ext
        if os.path.exists(s):
            shutil.copy2(s, dst + ext)
    return dst


def open_db(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def parse_refs(text):
    refs = {}
    for m in re.finditer(r"^\[(\d+)\]\s+(.+?)$", text, re.M):
        num = int(m.group(1))
        body = m.group(2).strip()
        dm = re.search(r"DOI:\s*([^\s\]]+?)\.?$", body)
        refs[num] = {"raw": body, "doi": (dm.group(1).rstrip(".").lower() if dm else "")}
    return refs


def parse_ts(s):
    if not s:
        return None
    t = str(s).replace("T", " ").rstrip("Z")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.datetime.strptime(t[:26], fmt)
        except ValueError:
            continue
    return None


def is_stub(body):
    flat = " ".join(re.sub(r"<[^>]+>", " ", body or "").split())
    if len(flat) < 400:
        return True
    markers = ("待补", "自动初稿", "摘要级", "未经全文核对", "auto-generated")
    return sum(1 for m in markers if m in body) >= 2


def load_library(z):
    fname = {fid: n for fid, n in z.execute("SELECT fieldID, fieldName FROM fields")}
    items = {int(i): {"key": k} for i, k in z.execute("SELECT itemID, key FROM items")}
    for iid, fid, v in z.execute(
            "SELECT id.itemID, id.fieldID, idv.value FROM itemData id "
            "JOIN itemDataValues idv ON id.valueID = idv.valueID"):
        n = fname.get(fid)
        if n in ("DOI", "title", "publicationTitle", "date") and int(iid) in items:
            items[int(iid)][n] = v
    deleted = {r[0] for r in z.execute("SELECT itemID FROM deletedItems")}
    pdf = {pid for pid, ct in z.execute(
        "SELECT parentItemID, contentType FROM itemAttachments WHERE contentType='application/pdf'"
    ) if pid}
    notes = {}
    for nid, pid, body in z.execute("SELECT itemID, parentItemID, note FROM itemNotes"):
        if pid:
            notes.setdefault(int(pid), []).append((int(nid), body or ""))
    meta = {i: {"key": v["key"], "title": v.get("title", ""),
                "doi": (v.get("DOI") or "").strip().lower(),
                "journal": v.get("publicationTitle", ""),
                "year": (v.get("date", "") or "")[:4]}
            for i, v in items.items() if i not in deleted}
    return meta, pdf, notes


def cmd_refs(md_path, as_json):
    text = open(md_path, encoding="utf-8").read()
    body = text.split("## 参考文献")[0] if "## 参考文献" in text else text
    cited = sorted({int(x) for grp in re.findall(r"\[(\d+(?:,\d+)*)\]", body)
                    for x in grp.split(",")})
    refs = parse_refs(text)

    print(f"正文引用 {len(cited)} 个编号；参考文献 {len(refs)} 条")
    missing = [c for c in cited if c not in refs]
    unused = [r for r in refs if r not in cited]
    print(f"  引用但无条目: {missing or '无'}")
    print(f"  有条目但未引用: {unused or '无'}")

    tmp = tempfile.mkdtemp(prefix="refchk-")
    try:
        z = open_db(snapshot(ZOTERO_DIR, tmp))
        meta, pdf, notes = load_library(z)
        by_doi = {v["doi"]: i for i, v in meta.items() if v["doi"]}

        rows, full, short, stub = [], 0, 0, []
        for num in sorted(refs):
            iid = by_doi.get(refs[num]["doi"])
            rec = {"num": num, "doi": refs[num]["doi"], "in_lib": bool(iid)}
            if iid:
                rec["key"] = meta[iid]["key"]
                rec["title"] = meta[iid]["title"]
                rec["has_pdf"] = iid in pdf
                bodies = [b for _, b in notes.get(iid, [])]
                rec["n_notes"] = len(bodies)
                rec["max_len"] = max((len(b) for b in bodies), default=0)
                rec["full"] = any(all(s in b for s in SECTIONS) and len(b) >= MIN_FULL_NOTE
                                  for b in bodies)
                rec["stub_only"] = (not bodies) or all(is_stub(b) for b in bodies)
                if rec["full"]:
                    full += 1
                elif rec["max_len"] >= 600:
                    short += 1
                else:
                    stub.append(num)
            else:
                stub.append(num)
            rows.append(rec)

        print(f"\n{'编号':>4} {'itemKey':10} {'笔记':>4} {'最长':>7} {'五节':>4}  状态")
        print("-" * 62)
        for r in rows:
            state = ("精读" if r.get("full") else
                     "较短" if r.get("max_len", 0) >= 600 else "初稿")
            if not r["in_lib"]:
                state = "库中缺失"
            print(f"[{r['num']:2d}] {r.get('key','—'):10} {r.get('n_notes',0):>4} "
                  f"{r.get('max_len',0):>7} {'Y' if r.get('full') else 'N':>4}  {state}")
        print("-" * 62)
        print(f"精读 {full}/{len(refs)}   较短 {short}   初稿或缺失 {len(stub)}")
        if stub:
            print(f"  需补: {stub}")

        if as_json:
            json.dump(rows, open(as_json, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            print(f"\n明细: {as_json}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_timestamps():
    tmp = tempfile.mkdtemp(prefix="ts-")
    try:
        z = open_db(snapshot(ZOTERO_DIR, tmp))
        rows = []
        for nid, pid, body in z.execute(
                "SELECT itemID, parentItemID, note FROM itemNotes"):
            r = z.execute("SELECT key, dateAdded, dateModified FROM items WHERE itemID=?",
                          (nid,)).fetchone()
            if not r:
                continue
            key, added, modified = r
            a, m = parse_ts(added), parse_ts(modified)
            rows.append({
                "note": key, "parent": pid, "len": len(body or ""),
                "added": added, "modified": modified,
                "edited": bool(a and m and (m - a).total_seconds() > 120),
                "stub": is_stub(body),
            })
        rows.sort(key=lambda x: x["added"] or "")
        days = {}
        for r in rows:
            d = (r["added"] or "")[:10]
            days.setdefault(d, [0, 0])
            days[d][0] += 1
            days[d][1] += 1 if r["stub"] else 0
        print("按创建日期：")
        for d in sorted(days):
            print(f"  {d}  {days[d][0]:3d} 条  初稿 {days[d][1]}")
        edited = [r for r in rows if r["edited"]]
        print(f"\n创建后被修改过（人工编辑痕迹）：{len(edited)}/{len(rows)}")
        for r in edited[:15]:
            print(f"  {r['note']}  {r['len']:6d}字符  {r['added'][:16]} -> {r['modified'][:16]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manuscript", nargs="?", help="manuscript .md with a reference list")
    ap.add_argument("--json", default=None, help="write the per-reference table to JSON")
    ap.add_argument("--timestamps", action="store_true", help="report note ages instead")
    args = ap.parse_args()

    if args.timestamps:
        return cmd_timestamps()
    if not args.manuscript:
        ap.print_help()
        return 1
    return cmd_refs(args.manuscript, args.json)


if __name__ == "__main__":
    sys.exit(main() or 0)
