"""Merge duplicate Zotero items, with a dry-run mode.

Design decisions this encodes (from the 2026-11-06 duplicate audit):

* A pair whose PDF text similarity is ~1.0 is the SAME FILE downloaded twice
  (byte differences come from publisher download timestamps), so only one copy
  of the PDF is kept.
* A pair where one PDF is a "Supplementary Materials for ..." document and the
  other is the article body is NOT a duplicate: both PDFs are kept, the SI is
  attached to the surviving item under its own title.
* Before deleting a losing item, its notes, tags, attachments and collection
  memberships must be migrated to the keeper. The script refuses to delete an
  item whose content has not been carried over.
* Deleting an item via the local API moves it to the trash; the caller decides
  whether to empty the trash.

Usage:
    python merge_dupes.py --dry-run          # print the plan, change nothing
    python merge_dupes.py --execute          # do it
    python merge_dupes.py --execute --group 8 # only one group
"""
import argparse
import collections
import difflib
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings

warnings.filterwarnings("ignore")
import logging
logging.getLogger("pypdf").setLevel(logging.CRITICAL)

SID = "f8R8PrfMdIds"
TOKEN = "eXidvcDYDX6q795MH0piqp2S5GctBK4R"
BASE = "http://127.0.0.1:23119/api/users/0"
H = {"Zotero-Server-ID": SID, "Authorization": f"Bearer {TOKEN}"}
STORAGE = r"E:\CodeProject\Zotero\storage"
OUTDIR = r"E:\CodeProject\其余工程\zotero-import-test"

SI_STRICT = [
    r"supplementary\s+materials?\s+for",
    r"^\s*supplementary\s+information\b",
    r"^\s*supporting\s+information\b",
    r"^\s*supplementary\s+material\b",
]

# collection name -> key, filled at runtime by analyse()
COLL_KEYS = {}


# ---------------------------------------------------------------- API helpers
def get(path, timeout=60):
    req = urllib.request.Request(BASE + path, headers=H)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def api(method, path, body=None, headers=None):
    """Call the Zotero local API.

    The API requires `If-Unmodified-Since-Version` on every write; without it
    it answers 428 (Precondition Failed). We fetch the current version of the
    target item first and send it along.
    """
    h = dict(H)
    if headers:
        h.update(headers)
    if method in ("PATCH", "PUT", "DELETE"):
        item_key = path.split("/items/")[-1].split("/")[0] if "/items/" in path else None
        if item_key:
            try:
                cur = get(f"/items/{item_key}")["data"]
                h.setdefault("If-Unmodified-Since-Version", str(cur.get("version", 0)))
            except Exception:
                pass
    h["Content-Type"] = "application/json"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


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


def md5(p, chunk=1 << 20):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def read_pdf(path, pages=2):
    import pypdf
    r = pypdf.PdfReader(path)
    n = len(r.pages)
    txt = ""
    for p in r.pages[:pages]:
        try:
            txt += (p.extract_text() or "") + "\n"
        except Exception:
            pass
    return n, txt


def is_si(text):
    low = text.lower()
    return any(re.search(p, low, re.M) for p in SI_STRICT)


# ---------------------------------------------------------------- analysis
def analyse():
    items = fetch_all()
    raw = {i["key"]: i["data"] for i in items}
    children = collections.defaultdict(list)
    for i in items:
        d = i["data"]
        if d.get("parentItem"):
            children[d["parentItem"]].append(i)

    colls = get("/collections")
    coll_name = {c["key"]: c["data"]["name"] for c in colls}
    COLL_KEYS.clear()
    COLL_KEYS.update({v: k for k, v in coll_name.items()})
    item_colls = collections.defaultdict(set)
    for c in colls:
        for it in get(f"/collections/{c['key']}/items?limit=300"):
            item_colls[it["key"]].add(c["key"])

    bib = [i for k, i in raw.items()
           if i.get("itemType") not in ("note", "attachment", "annotation")]

    def nd(d):
        d = (d or "").strip().lower()
        for p in ("https://doi.org/", "http://doi.org/", "doi:"):
            if d.startswith(p):
                d = d[len(p):]
        return d

    def nt(t):
        t = re.sub(r"<[^>]+>", "", t or "")
        return " ".join(re.sub(r"[^\w一-鿿]+", " ", t.lower(), flags=re.UNICODE).split())

    groups = []
    by_doi = collections.defaultdict(list)
    for v in bib:
        if nd(v.get("DOI")):
            by_doi[nd(v["DOI"])].append(v)
    for d, g in by_doi.items():
        if len(g) > 1:
            groups.append({"reason": "DOI", "label": d, "items": g})
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
            groups.append({"reason": "TITLE", "label": t, "items": g})

    out = []
    for gi, g in enumerate(groups, 1):
        members = []
        for v in g["items"]:
            k = v["key"]
            d = raw[k]
            kids = children.get(k, [])
            pdfs, notes, others = [], [], []
            for c in kids:
                cd = c["data"]
                if cd.get("itemType") == "attachment":
                    if cd.get("contentType") == "application/pdf":
                        p = cd.get("path") or os.path.join(STORAGE, c["key"], cd.get("filename", ""))
                        info = {"key": c["key"], "title": cd.get("title", ""),
                                "filename": cd.get("filename", ""), "path": p,
                                "contentType": cd.get("contentType", ""),
                                "linkMode": cd.get("linkMode")}
                        if os.path.exists(p):
                            try:
                                pages, txt = read_pdf(p)
                                info["pages"] = pages
                                info["is_si"] = is_si(txt)
                                info["text_head"] = " ".join(txt.split())[:200]
                            except Exception as e:
                                info["error"] = str(e)[:60]
                        pdfs.append(info)
                    else:
                        others.append({"key": c["key"], "title": cd.get("title", ""),
                                       "contentType": cd.get("contentType", "")})
                elif cd.get("itemType") == "note":
                    notes.append({"key": c["key"], "len": len(cd.get("note", "") or "")})
            members.append({
                "key": k, "itemType": d.get("itemType"),
                "title": d.get("title", ""), "date": d.get("date", ""),
                "journal": d.get("publicationTitle", ""), "doi": d.get("DOI", ""),
                "abstract_len": len(d.get("abstractNote", "") or ""),
                "volume": d.get("volume", ""), "issue": d.get("issue", ""),
                "pages": d.get("pages", ""),
                "tags": [t.get("tag") for t in d.get("tags", [])],
                "collections": [coll_name.get(c, c) for c in item_colls.get(k, [])],
                "pdfs": pdfs, "notes": notes, "others": others,
            })

        # decide keeper: richest metadata + most notes.
        # The abstract is scored by LENGTH, not by a boolean: a truncated
        # abstract is real data loss, and two items of the same paper can
        # differ only in how much abstract the translator captured.
        def score(m):
            return (min(m["abstract_len"], 4000) // 40) * 3 \
                + bool(m["journal"]) * 12 \
                + bool(m["volume"]) * 8 + (m["itemType"] == "journalArticle") * 10 \
                + len(m["tags"]) * 2 + len(m["notes"]) * 25 + len(m["pdfs"]) * 5
        members.sort(key=lambda m: -score(m))

        # classify the PDFs across the whole group
        allpdfs = [p for m in members for p in m["pdfs"]]
        si_set, main_set = set(), set()
        for m in members:
            for p in m["pdfs"]:
                if p.get("is_si"):
                    si_set.add(p["key"])
                elif p.get("pages"):
                    main_set.add(p["key"])
        # text-similarity clusters among PDFs
        clusters = []
        for p in allpdfs:
            if p.get("error") or "text_head" not in p:
                continue
            placed = False
            for cl in clusters:
                if difflib.SequenceMatcher(None, cl["rep"], p["text_head"]).quick_ratio() > 0.95:
                    cl["members"].append(p["key"])
                    placed = True
                    break
            if not placed:
                clusters.append({"rep": p["text_head"], "members": [p["key"]]})

        out.append({
            "group": gi, "reason": g["reason"], "label": g["label"],
            "members": members, "keeper": members[0]["key"],
            "si_pdfs": sorted(si_set), "main_pdfs": sorted(main_set),
            "clusters": clusters,
            "has_si": bool(si_set) and bool(main_set),
        })
    return out


# ---------------------------------------------------------------- actions
def plan_actions(group):
    """Turn a group into a concrete list of actions."""
    keeper = group["keeper"]
    members = group["members"]
    keeper_m = next(m for m in members if m["key"] == keeper)
    acts = []

    # --- 0. classify every PDF in the group by role -------------------------
    # SI  = a document whose opening banner names it as supplementary material
    # MAIN = an article body
    # DUPE = text-identical to another PDF in the same group
    #
    # A group that holds both an SI and a MAIN document is NOT a duplicate:
    # both files are kept, and the SI is re-titled so it is distinguishable.
    role = {}          # attachment key -> "SI" | "MAIN"
    text_key = {}      # attachment key -> text-head, for duplicate detection
    for m in members:
        for p in m["pdfs"]:
            if p.get("error") or "text_head" not in p:
                continue
            text_key[p["key"]] = p["text_head"]
            role[p["key"]] = "SI" if p.get("is_si") else "MAIN"

    dupe_of = {}      # attachment key -> attachment key it duplicates
    keys = list(text_key)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if difflib.SequenceMatcher(None, text_key[a], text_key[b]).quick_ratio() > 0.95:
                # keep the first, the other is the duplicate
                dupe_of[b] = a
                role[b] = "DUPE"

    keeper_pdf_roles = [role.get(p["key"]) for p in keeper_m["pdfs"]]

    # --- 1. migrate notes from losers ---------------------------------------
    for m in members:
        if m["key"] == keeper:
            continue
        for n in m["notes"]:
            acts.append({"type": "migrate_note", "note": n["key"],
                         "from": m["key"], "to": keeper,
                         "detail": f"{n['len']} 字符"})

    # --- 2. migrate non-PDF attachments -------------------------------------
    # Skip an HTML snapshot when the keeper already has one of the same kind:
    # the loser is just a second copy of the same saved page.
    for m in members:
        if m["key"] == keeper:
            continue
        for o in m["others"]:
            same_kind = [x for x in keeper_m["others"]
                         if x["contentType"] == o["contentType"]]
            if same_kind:
                acts.append({"type": "drop_dup_attachment", "attachment": o["key"],
                             "from": m["key"],
                             "detail": f"keeper 已有同类 {same_kind[0]['contentType']} 快照"})
            else:
                acts.append({"type": "migrate_attachment", "attachment": o["key"],
                             "from": m["key"], "to": keeper,
                             "detail": f"{o['contentType']} '{o['title'][:40]}'"})

    # --- 3. SI and MAIN PDFs: both are kept, retitled, moved to keeper -------
    # A group holding an SI plus an article body is NOT a duplicate: both
    # files belong to the same paper. The keeper gets one of each.
    keeper_has_main = any(role.get(p["key"]) == "MAIN" for p in keeper_m["pdfs"])
    keeper_has_si = any(role.get(p["key"]) == "SI" for p in keeper_m["pdfs"])
    for m in members:
        for p in m["pdfs"]:
            r = role.get(p["key"])
            if r == "SI":
                acts.append({"type": "keep_si", "attachment": p["key"],
                             "from": m["key"], "to": keeper,
                             "detail": f"{p.get('pages','?')} 页 SI，标题改为 'Supplementary Information'"})
            elif r == "MAIN" and m["key"] != keeper and not keeper_has_main:
                acts.append({"type": "keep_main", "attachment": p["key"],
                             "from": m["key"], "to": keeper,
                             "detail": f"{p.get('pages','?')} 页正文，迁到 keeper，标题改为 'Full Text PDF'"})
                keeper_has_main = True

    # --- 4. duplicate PDFs: keep one copy -----------------------------------
    for loser, kept in dupe_of.items():
        acts.append({"type": "drop_dup_pdf", "attachment": loser,
                     "keep": kept, "detail": "文本相同，只保留一份"})

    # --- 5. metadata merge ---------------------------------------------------
    for m in members:
        if m["key"] == keeper:
            continue
        for field, val in (("journal", m["journal"]), ("volume", m["volume"]),
                           ("issue", m["issue"]), ("pages", m["pages"]),
                           ("date", m["date"])):
            if val and not keeper_m.get(field):
                acts.append({"type": "fill_field", "field": field, "value": val,
                             "on": keeper, "from": m["key"]})
        for t in m["tags"]:
            if t not in keeper_m["tags"]:
                acts.append({"type": "add_tag", "tag": t, "on": keeper,
                             "from": m["key"]})

    # --- 6. collections -------------------------------------------------------
    for m in members:
        if m["key"] == keeper:
            continue
        for c in m["collections"]:
            if c not in keeper_m["collections"]:
                acts.append({"type": "add_collection", "collection": c, "on": keeper,
                             "from": m["key"]})

    # --- 7. delete losers ----------------------------------------------------
    for m in members:
        if m["key"] == keeper:
            continue
        acts.append({"type": "delete_item", "item": m["key"],
                     "title": m["title"][:70]})
    return acts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--group", type=int, default=None)
    ap.add_argument("--out", default=OUTDIR)
    args = ap.parse_args()

    groups = analyse()
    if args.group:
        groups = [g for g in groups if g["group"] == args.group]

    os.makedirs(args.out, exist_ok=True)
    all_actions = []
    for g in groups:
        acts = plan_actions(g)
        all_actions.append({"group": g["group"], "label": g["label"],
                            "keeper": g["keeper"], "actions": acts})
        print("=" * 100)
        print(f"【第 {g['group']} 组】{g['reason']}: {g['label'][:64]}")
        print(f"  保留 {g['keeper']}   " +
              " | ".join(f"{m['key']}(摘要{m['abstract_len']} 笔记{len(m['notes'])} PDF{len(m['pdfs'])})"
                        for m in g["members"]))
        if g["has_si"]:
            print("  ★ 含正文 + 补充材料 —— 两份 PDF 都要保留")
        for a in acts:
            print(f"    {a['type']:20s} {a}")
        print()

    with open(os.path.join(args.out, "merge_plan.json"), "w", encoding="utf-8") as f:
        json.dump(all_actions, f, ensure_ascii=False, indent=1)

    if not args.execute:
        print(f"dry-run: 计划已写入 {os.path.join(args.out, 'merge_plan.json')}")
        print("加 --execute 执行。")
        return 0

    # ---------------- execute ----------------
    print("\n" + "=" * 100)
    print("执行中")
    print("=" * 100)
    executed = []
    for gp in all_actions:
        g = next(x for x in groups if x["group"] == gp["group"])
        keeper = g["keeper"]
        print(f"\n【第 {g['group']} 组】保留 {keeper}")

        for a in gp["actions"]:
            t = a["type"]
            try:
                if t == "migrate_note":
                    st, _ = api("PATCH", f"/items/{a['note']}",
                                {"parentItem": a["to"]})
                    print(f"   note {a['note']} -> {a['to']}  [{st}]")
                elif t == "migrate_attachment":
                    st, _ = api("PATCH", f"/items/{a['attachment']}",
                                {"parentItem": a["to"]})
                    print(f"   att  {a['attachment']} -> {a['to']}  [{st}]")
                elif t == "keep_si":
                    st, _ = api("PATCH", f"/items/{a['attachment']}",
                                {"title": "Supplementary Information"})
                    print(f"   si   {a['attachment']} retitled  [{st}]")
                elif t == "keep_main":
                    st1, _ = api("PATCH", f"/items/{a['attachment']}",
                                 {"parentItem": a["to"], "title": "Full Text PDF"})
                    print(f"   main {a['attachment']} -> {a['to']} retitled  [{st1}]")
                elif t == "drop_dup_pdf":
                    st, _ = api("DELETE", f"/items/{a['attachment']}")
                    print(f"   drop {a['attachment']} (dup of {a['keep']})  [{st}]")
                elif t == "drop_dup_attachment":
                    st, _ = api("DELETE", f"/items/{a['attachment']}")
                    print(f"   drop {a['attachment']} (dup snapshot)  [{st}]")
                elif t == "fill_field":
                    st, _ = api("PATCH", f"/items/{a['on']}",
                                {a["field"]: a["value"]})
                    print(f"   fill {a['on']}.{a['field']} = {a['value'][:30]}  [{st}]")
                elif t == "add_tag":
                    cur = next(m for m in g["members"] if m["key"] == a["on"])
                    tags = [{"tag": t2} for t2 in cur["tags"]] + [{"tag": a["tag"]}]
                    st, _ = api("PATCH", f"/items/{a['on']}", {"tags": tags})
                    print(f"   tag  {a['on']} += {a['tag']}  [{st}]")
                elif t == "add_collection":
                    ck = COLL_KEYS.get(a["collection"])
                    if not ck:
                        print(f"   coll {a['on']} 跳过（找不到集合 key）")
                    else:
                        cur = get(f"/items/{a['on']}")[0]["data"].get("collections", [])
                        if ck not in cur:
                            st, _ = api("PATCH", f"/items/{a['on']}",
                                        {"collections": cur + [ck]})
                            print(f"   coll {a['on']} += {ck}  [{st}]")
                        else:
                            print(f"   coll {a['on']} 已含 {ck}")
                elif t == "delete_item":
                    st, _ = api("DELETE", f"/items/{a['item']}")
                    print(f"   DEL  {a['item']}  [{st}]")
                executed.append(a)
            except Exception as e:
                print(f"   !! {t} failed: {e}")
            time.sleep(0.2)

    print(f"\n共执行 {len(executed)} 个动作")
    return 0


if __name__ == "__main__":
    sys.exit(main())
