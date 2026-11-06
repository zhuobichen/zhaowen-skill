"""Produce a clean, actionable duplicate report.

Two layers:
  A. ITEM level  — the same paper stored as two Zotero items (same DOI/title).
     Merging these is a Zotero operation; the report says which member should
     survive and what must be carried over first.
  B. FILE level  — byte-identical PDFs stored under two attachment keys.
     These only take real disk space; deleting the loser file is safe only
     after its Zotero attachment row is gone.

Writes a report and prints a summary.
"""
import collections
import hashlib
import json
import os
import re
import urllib.request

SID = "f8R8PrfMdIds"
TOKEN = "eXidvcDYDX6q795MH0piqp2S5GctBK4R"
BASE = "http://127.0.0.1:23119/api/users/0"
H = {"Zotero-Server-ID": SID, "Authorization": f"Bearer {TOKEN}"}
STORAGE = r"E:\CodeProject\Zotero\storage"
OUT = r"E:\CodeProject\其余工程\zotero-import-test"


def get(path, timeout=60):
    req = urllib.request.Request(BASE + path, headers=H)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def md5(p, chunk=1 << 20):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def fetch_all():
    items, start, seen = [], 0, set()
    while True:
        batch = get(f"/items?limit=100&start={start}")
        if not batch:
            break
        keys = {i["key"] for i in batch}
        if not keys - seen:
            break
        seen |= keys
        items.extend(batch)
        start += len(batch)
        if len(batch) < 100 or start > 3000:
            break
    return items


def nd(d):
    d = (d or "").strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    return d


def nt(t):
    t = re.sub(r"<[^>]+>", "", t or "")
    return " ".join(re.sub(r"[^\w一-鿿]+", " ", t.lower(), flags=re.UNICODE).split())


def main():
    items = fetch_all()
    raw = {i["key"]: i["data"] for i in items}

    children = collections.defaultdict(list)
    for i in items:
        d = i["data"]
        if d.get("parentItem"):
            children[d["parentItem"]].append(i)

    colls = get("/collections")
    coll_name = {c["key"]: c["data"]["name"] for c in colls}
    item_colls = collections.defaultdict(set)
    for c in colls:
        for it in get(f"/collections/{c['key']}/items?limit=300"):
            item_colls[it["key"]].add(c["key"])

    bib = [i for k, i in raw.items()
           if i.get("itemType") not in ("note", "attachment", "annotation")]

    # ---------- group by DOI, then by title ----------
    groups = []
    by_doi = collections.defaultdict(list)
    for v in bib:
        if nd(v.get("DOI")):
            by_doi[nd(v["DOI"])].append(v)
    for d, g in by_doi.items():
        if len(g) > 1:
            groups.append({"reason": "same DOI", "label": d, "items": g})

    covered = {v["key"] for g in groups for v in g["items"]}
    by_title = collections.defaultdict(list)
    for v in bib:
        if v["key"] in covered:
            continue
        t = nt(v.get("title"))
        if t:
            by_title[t].append(v)
    for t, g in by_title.items():
        if len(g) > 1:
            groups.append({"reason": "same title", "label": t, "items": g})

    # ---------- score each member: keeper has the richest metadata ----------
    def richness(v):
        d = raw[v["key"]]
        s = 0
        s += 40 if len(d.get("abstractNote", "") or "") > 100 else 0
        s += 10 if d.get("publicationTitle") else 0
        s += 10 if d.get("volume") else 0
        s += 5 if d.get("pages") else 0
        s += 10 if d.get("itemType") == "journalArticle" else 0
        s += 2 * len(d.get("tags", []))
        s += 5 * len(children.get(v["key"], []))
        return s

    out_groups = []
    for g in groups:
        members = []
        for v in g["items"]:
            k = v["key"]
            d = raw[k]
            kids = children.get(k, [])
            pdfs = [c for c in kids if c["data"].get("contentType") == "application/pdf"]
            notes = [c for c in kids if c["data"].get("itemType") == "note"]
            # md5 of its own PDFs, for cross-member comparison
            own = []
            for a in pdfs:
                p = a["data"].get("path")
                if p and os.path.exists(p):
                    own.append((a["key"], md5(p), os.path.getsize(p)))
            members.append({
                "key": k,
                "itemType": d.get("itemType"),
                "title": d.get("title", ""),
                "date": d.get("date", ""),
                "journal": d.get("publicationTitle", ""),
                "doi": d.get("DOI", ""),
                "abstract_len": len(d.get("abstractNote", "") or ""),
                "volume": d.get("volume", ""), "issue": d.get("issue", ""),
                "pages": d.get("pages", ""),
                "tags": [t.get("tag") for t in d.get("tags", [])],
                "collections": [coll_name.get(c, c) for c in item_colls.get(k, [])],
                "attachments": [{"key": a["key"], "type": a["data"].get("contentType", "")} for a in kids
                                if a["data"].get("itemType") == "attachment"],
                "notes": [{"key": n["key"], "len": len(n["data"].get("note", "") or "")}
                          for n in notes],
                "pdf_md5": own,
                "richness": richness(v),
            })
        members.sort(key=lambda m: -m["richness"])
        # identical PDFs across members
        allh = collections.defaultdict(list)
        for m in members:
            for ak, h, sz in m["pdf_md5"]:
                allh[h].append((m["key"], ak, sz))
        shared = {h: v for h, v in allh.items() if len(v) > 1}
        out_groups.append({
            "reason": g["reason"], "label": g["label"],
            "members": members,
            "keeper": members[0]["key"],
            "identical_pdf_across_members": {h: v for h, v in shared.items()},
        })

    # ---------- file-level duplicates inside storage ----------
    by_hash = collections.defaultdict(list)
    total_size = 0
    for d in sorted(os.listdir(STORAGE)):
        dp = os.path.join(STORAGE, d)
        if not os.path.isdir(dp):
            continue
        for f in os.listdir(dp):
            p = os.path.join(dp, f)
            if not os.path.isfile(p):
                continue
            try:
                sz = os.path.getsize(p)
                by_hash[(sz, md5(p))].append({"storage_key": d, "filename": f, "size": sz})
                total_size += sz
            except Exception:
                pass
    file_dupes = []
    for (sz, h), group in sorted(by_hash.items(), key=lambda kv: -kv[0][0] * (len(kv[1]) - 1)):
        if len(group) < 2:
            continue
        file_dupes.append({"md5": h, "size": sz, "copies": group,
                           "waste": sz * (len(group) - 1)})

    # map storage_key -> owning item, so we know which attachment each copy is
    att_owner = {}
    for k, d in raw.items():
        if d.get("itemType") == "attachment":
            att_owner[k] = d.get("parentItem")

    for fd in file_dupes:
        for c in fd["copies"]:
            c["attachment_key"] = c["storage_key"]
            c["parent_item"] = att_owner.get(c["storage_key"])

    report = {
        "item_groups": out_groups,
        "file_duplicates": file_dupes,
        "storage_total_files": sum(len(v) for v in by_hash.values()),
        "storage_total_bytes": total_size,
        "potential_waste_bytes": sum(f["waste"] for f in file_dupes),
    }
    os.makedirs(OUT, exist_ok=True)
    with open(OUT + r"\duplicate_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    # ---------- print ----------
    print(f"库内文献条目: {len(bib)}")
    print(f"\n{'='*96}\nA. 条目级重复（同一篇论文存了两条）: {len(out_groups)} 组\n{'='*96}")
    for gi, g in enumerate(out_groups, 1):
        print(f"\n【{gi}】{g['reason']}: {g['label'][:70]}")
        for m in g["members"]:
            mark = "★保留" if m["key"] == g["keeper"] else "  合并"
            print(f"  {mark} {m['key']}  {m['itemType']:14s} {m['date'] or '—':10s} {m['journal'][:38]}")
            print(f"      标题: {m['title'][:88]}")
            print(f"      摘要 {m['abstract_len']}字符 | 标签 {len(m['tags'])} | 集合 {m['collections'] or '无'}")
            print(f"      附件: {[a['key'] for a in m['attachments']]}")
            print(f"      笔记: {[(n['key'], str(n['len'])+'字符') for n in m['notes']] or '无'}")
        if g["identical_pdf_across_members"]:
            print(f"  !! 成员间有完全相同的 PDF:")
            for h, v in g["identical_pdf_across_members"].items():
                print(f"     md5 {h[:16]}: {v}")
        else:
            print(f"  (成员间 PDF 内容不同 —— 两个附件都要保留)")

    print(f"\n{'='*96}\nB. 文件级重复（storage 里同一份文件存了两遍）\n{'='*96}")
    print(f"storage 文件 {report['storage_total_files']} 个, "
          f"共 {report['storage_total_bytes']/1073741824:.2f} GB")
    print(f"重复组 {len(file_dupes)}, 可回收 "
          f"{report['potential_waste_bytes']/1048576:.1f} MB")
    for fd in file_dupes:
        names = [c["filename"] for c in fd["copies"]]
        is_ft = all(".zotero-ft-cache" in n for n in names)
        print(f"\n  {len(fd['copies'])} 份 × {fd['size']/1048576:.1f} MB  md5 {fd['md5'][:16]}"
              f"{'  [全文索引缓存]' if is_ft else ''}")
        for c in fd["copies"]:
            owner = c["parent_item"] or "(顶层)"
            print(f"     storage\\{c['storage_key']}  父条目 {owner}")
            print(f"        {c['filename'][:74]}")

    print(f"\n报告: {OUT}\\duplicate_report.json")


if __name__ == "__main__":
    main()
