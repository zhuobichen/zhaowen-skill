"""Search a Zotero library by full text, using the index Zotero already built.

Why this exists
---------------
Zotero already maintains an FTS5 index of every PDF and note it has indexed
(`fulltext.sqlite`). That index IS the retrieval layer: already built,
already tokenised, already current. Rebuilding it as a vector store would
mean re-extracting ~280 PDFs, re-chunking them, embedding them, and keeping
a second copy in sync with Zotero — for a search-quality gain this library
does not need, and with a chunking strategy that would silently break
chemical formulas, DOIs and measurement units.

The pipeline:

    query -> FTS5 over fulltextContent (PDF bodies) + fulltextNotes (notes)
          -> Zotero numeric itemIDs
          -> itemID -> itemKey  (zotero.sqlite snapshot)
          -> bibliographic metadata + PDF attachment path
          -> optional matching passages pulled out of the PDF

Two implementation notes that cost real time to discover:

* The local API exposes only the 8-character item key, but the FTS5 rowid is
  Zotero's internal numeric itemID. The mapping lives in `zotero.sqlite`.
* `zotero.sqlite` is locked while Zotero runs. Copy the main file together
  with its `-wal`/`-shm` sidecars into a temp snapshot and read that.

Usage:
    python zotero_search.py "MDA8"                        # keyword search
    python zotero_search.py "ozone AND trend" --limit 10
    python zotero_search.py "data fusion" --kind pdf      # PDF bodies only
    python zotero_search.py "数据融合" --kind note         # notes only
    python zotero_search.py "MDA8" --passages             # show matching text
    python zotero_search.py "MDA8" --authors "Di"
    python zotero_search.py "MDA8" --year-from 2015 --year-to 2026
    python zotero_search.py "MDA8" --json
    python zotero_search.py --list-cites "10.1021/acs.est.5c16412"
    python zotero_search.py --find-doi "10.1021/acs.est.5c16412"
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import urllib.parse
import urllib.request

ZOTERO_DIR = r"E:\CodeProject\Zotero"
STORAGE = os.path.join(ZOTERO_DIR, "storage")
API = "http://127.0.0.1:23119/api/users/0"
SID = "f8R8PrfMdIds"
TOKEN = "eXidvcDYDX6q795MH0piqp2S5GctBK4R"
H = {"Zotero-Server-ID": SID, "Authorization": f"Bearer {TOKEN}"}


def api_get(path, timeout=60):
    req = urllib.request.Request(API + path, headers=H)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ro(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def snapshot_zotero(tmpdir):
    """Copy zotero.sqlite (+wal/shm) so it can be read while Zotero runs."""
    dst = os.path.join(tmpdir, "zot.sqlite")
    src = os.path.join(ZOTERO_DIR, "zotero.sqlite")
    for ext in ("", "-wal", "-shm"):
        s = src + ext
        if os.path.exists(s):
            shutil.copy2(s, dst + ext)
    return dst


# ------------------------------------------------------------------ metadata
def load_index(zot):
    """itemID -> key, key -> parent itemID, itemID -> attachment info."""
    id2key, key2id, parent, atts = {}, {}, {}, {}
    for iid, key in zot.execute("SELECT itemID, key FROM items"):
        id2key[int(iid)] = key
        key2id[key] = int(iid)
    for iid, pid in zot.execute("SELECT itemID, parentItemID FROM itemAttachments"):
        if pid:
            parent[int(iid)] = int(pid)
            atts[int(iid)] = True
    for iid, pid in zot.execute("SELECT itemID, parentItemID FROM itemNotes"):
        if pid:
            parent[int(iid)] = int(pid)
    return id2key, key2id, parent, atts


FIELD_NAMES = ("title", "DOI", "date", "publicationTitle", "url",
               "abstractNote", "citationKey", "extra", "volume", "issue", "pages")


def load_meta(zot, item_ids):
    """Bibliographic metadata for a set of numeric itemIDs."""
    if not item_ids:
        return {}
    ids = list(item_ids)
    marks = ",".join("?" * len(ids))

    fmap = {fid: name for fid, name in zot.execute(
        "SELECT fieldID, fieldName FROM fields WHERE fieldName IN (" +
        ",".join("?" * len(FIELD_NAMES)) + ")", list(FIELD_NAMES))}

    out = {}
    for iid, key, itype in zot.execute(
            f"SELECT itemID, key, itemTypeID FROM items WHERE itemID IN ({marks})", ids):
        out[int(iid)] = {"key": key, "itemTypeID": itype}

    # Items in the trash are flagged with deletedItems.deleted.
    deleted = set()
    try:
        for iid, in zot.execute("SELECT itemID FROM deletedItems"):
            deleted.add(int(iid))
    except sqlite3.OperationalError:
        pass

    for iid, fid, v in zot.execute(
            "SELECT id.itemID, id.fieldID, idv.value FROM itemData id "
            "JOIN itemDataValues idv ON id.valueID = idv.valueID"):
        name = fmap.get(fid)
        if name and int(iid) in out:
            out[int(iid)][name] = v

    creators = {}
    for iid, fn, ln, ct in zot.execute(
            "SELECT ic.itemID, c.firstName, c.lastName, ct.creatorType "
            "FROM itemCreators ic JOIN creators c ON ic.creatorID = c.creatorID "
            "JOIN creatorTypes ct ON ic.creatorTypeID = ct.creatorTypeID"):
        nm = " ".join(x for x in (fn, ln) if x).strip()
        if nm:
            creators.setdefault(int(iid), []).append(nm)

    tmap = {tid: name for tid, name in zot.execute(
        "SELECT itemTypeID, typeName FROM itemTypes")}

    for iid, rec in out.items():
        rec["itemType"] = tmap.get(rec.pop("itemTypeID"), "")
        rec["authors"] = creators.get(iid, [])
        rec["year"] = (rec.get("date", "") or "")[:4]
        rec["deleted"] = iid in deleted
    return out


def pdf_path_for(zot, item_id, id2key):
    """Storage path of the PDF attached to a bibliographic item."""
    for aid, pid, path, ctype in zot.execute(
            "SELECT itemID, parentItemID, path, contentType FROM itemAttachments "
            "WHERE parentItemID=?", (item_id,)):
        if ctype == "application/pdf":
            p = path
            if p and os.path.exists(p):
                return p
            # Fall back to the storage convention.
            alt = os.path.join(STORAGE, id2key.get(aid, ""), os.path.basename(p or ""))
            if os.path.exists(alt):
                return alt
    return None


# ------------------------------------------------------------------- search
def build_query(q):
    if re.match(r"^[A-Za-z0-9_]+$", q):
        return q
    parts = []
    for tok in re.findall(r'"[^"]+"|\bAND\b|\bOR\b|\bNOT\b|\S+', q):
        t = tok.strip()
        if t.upper() in ("AND", "OR", "NOT"):
            parts.append(t)
        elif t.startswith('"') and t.endswith('"'):
            parts.append(t)
        else:
            parts.append('"' + t.replace('"', '""') + '"')
    return " ".join(parts)


def fts_search(conn, query, table, limit):
    try:
        return [r[0] for r in conn.execute(
            f"SELECT rowid FROM {table} WHERE {table} MATCH ? ORDER BY rank LIMIT ?",
            (query, limit))]
    except sqlite3.OperationalError:
        return []


def passages(pdf_path, terms, ctx=300, max_hits=3):
    if not pdf_path or not os.path.exists(pdf_path):
        return []
    try:
        import pypdf
    except ImportError:
        try:
            import PyPDF2 as pypdf
        except ImportError:
            return []
    try:
        reader = pypdf.PdfReader(pdf_path)
    except Exception:
        return []
    low_terms = [t.lower() for t in terms if len(t) > 2]
    out = []
    for pno, page in enumerate(reader.pages[:40], 1):
        try:
            flat = " ".join((page.extract_text() or "").split())
        except Exception:
            continue
        low = flat.lower()
        for t in low_terms:
            i = low.find(t)
            if i < 0:
                continue
            s = max(0, i - ctx // 2)
            out.append({"page": pno, "term": t, "text": flat[s:i + ctx]})
            break
        if len(out) >= max_hits:
            break
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", default=None,
                    help="search terms (FTS5 syntax: AND/OR/NOT, \"exact phrase\")")
    ap.add_argument("--query", dest="query_opt", default=None,
                    help="same as the positional argument; also accepts @file "
                         "to read the query from a file")
    ap.add_argument("--query-file", default=None,
                    help="read the query from a file (one line). Safest way to "
                         "pass a query containing quoted phrases on any shell")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--kind", choices=["pdf", "note", "both"], default="both")
    ap.add_argument("--passages", action="store_true")
    ap.add_argument("--authors", default="")
    ap.add_argument("--year-from", default="")
    ap.add_argument("--year-to", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--list-cites", default=None, help="formatted citation for one DOI")
    ap.add_argument("--find-doi", default=None, help="locate one DOI in the library")
    args = ap.parse_args()
    # --query wins over the positional form; PowerShell splits a positional
    # argument that contains quoted phrases.
    if args.query_opt:
        args.query = args.query_opt
    if args.query_file:
        with open(args.query_file, encoding="utf-8-sig") as f:
            args.query = f.read().strip()
    if args.query and args.query.startswith("@"):
        with open(args.query[1:], encoding="utf-8-sig") as f:
            args.query = f.read().strip()

    tmpdir = tempfile.mkdtemp(prefix="zotsearch-")
    try:
        ft = ro(os.path.join(ZOTERO_DIR, "fulltext.sqlite"))
        zot = ro(snapshot_zotero(tmpdir))
        id2key, key2id, parent, is_att = load_index(zot)

        if args.find_doi:
            rows = zot.execute(
                "SELECT id.itemID FROM itemData id JOIN itemDataValues v "
                "ON id.valueID = v.valueID WHERE v.value = ?", (args.find_doi,)).fetchall()
            ids = [r[0] for r in rows]
            meta = load_meta(zot, ids)
            for iid in ids:
                m = meta.get(iid)
                if not m:
                    continue
                print(f"{m.get('citationKey','')}  [{m['key']}]")
                print(f"  {m.get('title','')}")
                print(f"  {', '.join(m.get('authors',[]))}")
                print(f"  {m.get('publicationTitle','')} {m.get('volume','')}({m.get('issue','')}):{m.get('pages','')} {m.get('date','')}")
                print(f"  DOI {m.get('DOI','')}")
            return 0

        if args.list_cites:
            ids = [r[0] for r in zot.execute(
                "SELECT id.itemID FROM itemData id JOIN itemDataValues v "
                "ON id.valueID = v.valueID WHERE v.value = ?", (args.list_cites,)).fetchall()]
            meta = load_meta(zot, ids)
            for iid in ids:
                m = meta.get(iid)
                if not m:
                    continue
                print(f"{m.get('citationKey') or '(无 citationKey)'}")
                print(f"  {m.get('title','')}")
                print(f"  {', '.join(m.get('authors',[]))}")
                print(f"  {m.get('publicationTitle','')} {m.get('volume','')}({m.get('issue','')}):{m.get('pages','')} {m.get('date','')}")
                print(f"  DOI: {m.get('DOI','')}")
            return 0

        if not args.query:
            ap.print_help()
            return 1

        match = build_query(args.query)
        hits = {}
        if args.kind in ("pdf", "both"):
            for rank, iid in enumerate(fts_search(ft, match, "fulltextContent", args.limit * 3)):
                hits.setdefault(int(iid), {})["pdf"] = rank
        if args.kind in ("note", "both"):
            for rank, iid in enumerate(fts_search(ft, match, "fulltextNotes", args.limit * 3)):
                hits.setdefault(int(iid), {})["note"] = rank
        if args.kind == "both" and not hits:
            for rank, iid in enumerate(fts_search(ft, match, "fulltextNotesCJK", args.limit * 3)):
                hits.setdefault(int(iid), {})["note"] = rank

        if not hits:
            print(f"无命中: {args.query!r}   (FTS5: {match})")
            return 0

        # map hit itemIDs -> parent bibliographic item
        parent_ids = {}
        for iid, flags in hits.items():
            pid = parent.get(iid, iid)
            parent_ids.setdefault(pid, set()).update(flags.keys())

        meta = load_meta(zot, list(parent_ids))
        results = []
        for pid, flags in parent_ids.items():
            m = meta.get(pid)
            if not m or not m.get("title"):
                continue
            # Skip items sitting in the Zotero trash: their attachments and
            # notes are still indexed, so a naive search resurrects them.
            if m.get("deleted"):
                continue
            if args.authors and not any(args.authors.lower() in a.lower() for a in m.get("authors", [])):
                continue
            y = m.get("year", "")
            if args.year_from and (not y or y < args.year_from):
                continue
            if args.year_to and (not y or y > args.year_to):
                continue
            p = pdf_path_for(zot, pid, id2key)
            r = dict(m)
            r["in_pdf"] = "pdf" in flags
            r["in_note"] = "note" in flags
            r["has_pdf"] = bool(p)
            r["pdf_path"] = p
            results.append(r)

        # Collapse duplicate entries for the same paper. The library can hold
        # the same DOI twice (e.g. 'Long-term' vs 'Long‐term' with a
        # different hyphen character), and both would otherwise be listed.
        by_doi = {}
        for r in results:
            d = (r.get("DOI") or "").strip().lower()
            key = d if d else ("t:" + re.sub(r"[^\w]+", "", (r.get("title") or "").lower()))
            prev = by_doi.get(key)
            if prev is None:
                by_doi[key] = r
            else:
                # keep the richer one, but remember the other key exists
                score_new = (len(r.get("authors", [])) * 2 + len(r.get("title", "")) // 40
                             + (10 if r.get("has_pdf") else 0)
                             + (5 if r.get("in_note") else 0))
                score_old = (len(prev.get("authors", [])) * 2 + len(prev.get("title", "")) // 40
                             + (10 if prev.get("has_pdf") else 0)
                             + (5 if prev.get("in_note") else 0))
                if score_new > score_old:
                    by_doi[key] = r
                by_doi[key].setdefault("duplicate_keys", []).append(
                    prev["key"] if score_new > score_old else r["key"])
        results = list(by_doi.values())

        results.sort(key=lambda r: (0 if r["in_pdf"] else 1,
                                    0 if r["has_pdf"] else 1,
                                    r.get("year", "") or ""))

        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
            return 0

        print(f"查询 {args.query!r}   FTS5: {match}   命中 {len(results)} 条\n")
        for i, r in enumerate(results[:args.limit], 1):
            au = ", ".join(r["authors"][:3]) + (" et al." if len(r["authors"]) > 3 else "")
            where = []
            if r["in_pdf"]: where.append("PDF正文")
            if r["in_note"]: where.append("笔记")
            if r["has_pdf"] and not r["in_pdf"]: where.append("有PDF")
            print(f"{i:2d}. {r['title'][:86]}")
            print(f"    {r.get('journal','')[:54]} ({r.get('year','')})   {au[:52]}")
            print(f"    DOI {r.get('DOI','') or '(无)'}   key {r['key']}   [{','.join(where)}]")
            if r.get("duplicate_keys"):
                print(f"      (库中另有重复条目: {', '.join(r['duplicate_keys'])})")
            if args.passages and r["pdf_path"]:
                terms = [t.strip('"') for t in match.split()
                         if t.strip('"') not in ("AND", "OR", "NOT")]
                for p in passages(r["pdf_path"], terms):
                    print(f"      [p.{p['page']}] …{p['text']}…")
            print()
        return 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
