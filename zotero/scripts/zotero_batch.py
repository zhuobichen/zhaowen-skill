#!/usr/bin/env python3
"""Zotero batch-import helper: verify, de-duplicate, and attach PDFs.

Three subcommands, meant to be run in order:

  index    Build a de-duplication index of the current Zotero library.
           Writes library_index.json (key/title/doi/year/type/journal) plus
           normalised DOI and title sets.

  verify   Check a DOI list against Crossref: does each DOI resolve, and does
           the registered title match the one we recorded? Writes
           doi_verification.json and prints a report.
           Also resolves each DOI to a direct PDF URL, including the Elsevier
           PII lookup (the PII cannot be derived from the DOI).

  match    Match downloaded PDF files to library items by the DOI printed
           inside the PDF (never by filename) and print the itemKey needed
           for mcp__zotero__write_item(action=import).

Usage:
    python zotero_batch.py index  [--out DIR]
    python zotero_batch.py verify <dois.txt> [--out DIR]
    python zotero_batch.py match <pdf> [<pdf> ...] [--index DIR/library_index.json]
"""
import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import warnings

warnings.filterwarnings("ignore")

# --- machine-specific defaults (override with flags) ------------------------
ZOTERO_BASE = "http://127.0.0.1:23119/api/users/0"
ZOTERO_SID = "f8R8PrfMdIds"
ZOTERO_TOKEN = "eXidvcDYDX6q795MH0piqp2S5GctBK4R"
WORKDIR = r"E:\CodeProject\其余工程\zotero-import-test"
MAIL = "dsh-local@example.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


# --- helpers ---------------------------------------------------------------
def norm_doi(doi):
    if not doi:
        return ""
    d = doi.strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    return d


def norm_title(t):
    """Normalise a title for comparison. Keeps CJK so Chinese titles match."""
    if not t:
        return ""
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"[^\w一-鿿]+", " ", t.lower(), flags=re.UNICODE)
    return " ".join(t.split())


def zget(path, timeout=30):
    req = urllib.request.Request(
        ZOTERO_BASE + path,
        headers={"Zotero-Server-ID": ZOTERO_SID,
                 "Authorization": f"Bearer {ZOTERO_TOKEN}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def crossref(doi, tries=4):
    """Fetch a Crossref record, retrying on the transient timeouts seen here."""
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={MAIL}"
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": f"zotero-batch/1.0 (mailto:{MAIL})"})
            with urllib.request.urlopen(req, timeout=60, context=_ctx) as r:
                return json.loads(r.read().decode("utf-8"))["message"]
        except Exception as e:
            last = e
            time.sleep(3)
    raise last


def head(url, timeout=40, accept="application/pdf,*/*"):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": accept,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read(2048)
    except urllib.error.HTTPError as e:
        return e.code, (e.headers.get("Content-Type", "") if e.headers else ""), b""
    except Exception as e:
        return 0, type(e).__name__, b""


def resolve_landing(doi):
    """Follow doi.org and return the publisher landing URL (or the doi.org URL)."""
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(
            f"https://doi.org/{doi}", method=method,
            headers={"User-Agent": UA, "Accept": "text/html"})
        try:
            with urllib.request.urlopen(req, timeout=40, context=_ctx) as r:
                return r.geturl()
        except Exception:
            continue
    return ""


# --- subcommand: index -----------------------------------------------------
def cmd_index(args):
    """Page the whole library and write a de-duplication index.

    Uses `start` for paging, NOT `offset`: `offset` is a key filter in the
    Zotero local API and returns the same page forever, which silently
    produces a library full of duplicate rows and breaks de-duplication.
    """
    items, start, seen = [], 0, set()
    while True:
        batch = zget(f"/items?limit=100&start={start}&itemType=-attachment")
        if not batch:
            break
        keys = {i["key"] for i in batch}
        if not keys - seen:
            break
        seen |= keys
        items.extend(batch)
        start += len(batch)
        if len(batch) < 100 or start > 2000:
            break

    bib = [i for i in items if i["data"].get("itemType") not in ("note", "attachment")]
    rows, dois, titles, prefixes = [], set(), set(), set()
    for i in bib:
        d = i["data"]
        doi_raw = (d.get("DOI") or "").strip()
        nd = norm_doi(doi_raw)
        if nd:
            dois.add(nd)
        nt = norm_title(d.get("title", ""))
        if nt:
            titles.add(nt)
            parts = nt.split()
            for n in (6, 8, 10):
                if len(parts) >= n:
                    prefixes.add(" ".join(parts[:n]))
        rows.append({
            "key": i["key"], "title": d.get("title", ""), "doi": doi_raw,
            "year": (d.get("date", "") or "")[:4], "type": d.get("itemType", ""),
            "journal": d.get("publicationTitle", "") or d.get("proceedingsTitle", ""),
        })

    out = os.path.join(args.out, "library_index.json")
    os.makedirs(args.out, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"dois": sorted(dois), "rows": rows,
                   "title_prefixes": sorted(prefixes)}, f, ensure_ascii=False, indent=1)

    print(f"bibliographic items : {len(rows)}")
    print(f"items with DOI      : {len(dois)}")
    print(f"unique titles       : {len(titles)}")
    print(f"index               : {out}")


# --- subcommand: verify ----------------------------------------------------
def build_pdf_candidates(doi, landing):
    """Direct-PDF URL candidates for one DOI, best first."""
    out = []
    prefix = doi.split("/")[0] + "/"
    if prefix == "10.1016/":
        m = re.search(r"/pii/([A-Z0-9]{10,})", landing or "", re.I)
        pii = m.group(1) if m else None
        if pii:
            out.append((f"https://www.sciencedirect.com/science/article/pii/{pii}/pdfft",
                        f"Elsevier pdfft (PII {pii})"))
            out.append((f"https://www.sciencedirect.com/science/article/pii/{pii}/pdf",
                        f"Elsevier /pdf (PII {pii})"))
        out.append((f"https://doi.org/{doi}", "DOI 跳转"))
    elif prefix == "10.1021/":
        out.append((f"https://pubs.acs.org/doi/pdf/{doi}", "ACS PDF"))
        out.append((f"https://pubs.acs.org/doi/epdf/{doi}", "ACS ePDF"))
        out.append((f"https://doi.org/{doi}", "DOI 跳转"))
    elif prefix == "10.1080/":
        out.append((f"https://www.tandfonline.com/doi/pdf/{doi}?download=true", "T&F PDF"))
        out.append((f"https://www.tandfonline.com/doi/epdf/{doi}?needAccess=true", "T&F ePDF"))
        out.append((f"https://doi.org/{doi}", "DOI 跳转"))
    elif prefix == "10.1007/":
        out.append((f"https://link.springer.com/content/pdf/{doi}.pdf", "Springer PDF"))
        out.append((f"https://doi.org/{doi}", "DOI 跳转"))
    else:
        out.append((f"https://doi.org/{doi}", "DOI 跳转"))
    return out


def cmd_verify(args):
    dois = []
    for arg in args.dois:
        if os.path.isfile(arg):
            with open(arg, encoding="utf-8") as f:
                dois += [l.strip() for l in f if l.strip() and not l.startswith("#")]
        else:
            dois.append(arg)

    index = {}
    idx_path = os.path.join(args.out, "library_index.json")
    if os.path.exists(idx_path):
        with open(idx_path, encoding="utf-8") as f:
            index = json.load(f)
    lib_dois = {norm_doi(d) for d in index.get("dois", [])}
    lib_titles = {norm_title(r.get("title", "")) for r in index.get("rows", [])}
    lib_prefixes = set(index.get("title_prefixes", []))

    report = []
    for doi in dois:
        nd = norm_doi(doi)
        rec = {"doi": doi, "in_library": nd in lib_dois}
        try:
            m = crossref(doi)
        except Exception as e:
            rec["status"] = "RESOLVE_FAIL"
            rec["error"] = f"{type(e).__name__}: {e}"[:120]
            report.append(rec)
            print(f"[FAIL] {doi}\n       {rec['error']}")
            continue

        ct = re.sub(r"\s+", " ", " ".join(m.get("title") or [])).strip()
        year = None
        for k in ("published-print", "published-online", "published", "issued"):
            p = (m.get(k) or {}).get("date-parts", [])
            if p and p[0]:
                year = p[0][0]
                break
        rec.update({
            "status": "MATCH",
            "crossref_title": ct,
            "crossref_year": year,
            "crossref_journal": " ".join(m.get("container-title") or []),
            "crossref_pages": m.get("page", ""),
            "crossref_authors": [
                (a.get("given", "") + " " + a.get("family", "")).strip()
                for a in (m.get("author") or []) if a.get("family")],
        })

        landing = resolve_landing(doi)
        rec["landing"] = landing
        rec["pdf_candidates"] = []
        for url, label in build_pdf_candidates(doi, landing):
            status, ctype, body = head(url)
            rec["pdf_candidates"].append({
                "url": url, "label": label, "status": status,
                "content_type": ctype, "served_pdf": body[:5] == b"%PDF-"})

        dup_title = norm_title(ct) in lib_titles
        dup_prefix = any(p in lib_prefixes for p in
                         (" ".join(norm_title(ct).split()[:n]) for n in (6, 8, 10))
                         if len(norm_title(ct).split()) >= n)
        rec["duplicate_title"] = dup_title or dup_prefix

        report.append(rec)
        flag = "DUPLICATE" if rec["in_library"] or rec["duplicate_title"] else "NEW"
        print(f"[{flag}] {doi}")
        print(f"    {ct[:92]}")
        print(f"    {year} | {rec['crossref_journal'][:52]} | pp {rec['crossref_pages']}")
        print(f"    {', '.join(rec['crossref_authors'][:4])}")
        for c in rec["pdf_candidates"][:2]:
            mark = "PDF" if c["served_pdf"] else c["content_type"][:22] or "-"
            print(f"    [{c['status']:>3}] {mark:<24} {c['url'][:88]}")
        time.sleep(0.5)

    os.makedirs(args.out, exist_ok=True)
    out = os.path.join(args.out, "doi_verification.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    ok = [r for r in report if r.get("status") == "MATCH"]
    fail = [r for r in report if r.get("status") == "RESOLVE_FAIL"]
    dup = [r for r in report if r.get("in_library") or r.get("duplicate_title")]
    print(f"\nresolved : {len(ok)}   failed: {len(fail)}   duplicates: {len(dup)}")
    print(f"report   : {out}")
    for r in dup:
        print(f"  DUP {r['doi']}  (doi={r['in_library']}, title={r.get('duplicate_title')})")


# --- subcommand: match -----------------------------------------------------
def pdf_text(path, pages=3):
    for mod in ("pypdf", "PyPDF2"):
        try:
            m = __import__(mod)
            r = m.PdfReader(path)
            return "\n".join((p.extract_text() or "") for p in r.pages[:pages])
        except Exception:
            continue
    return ""


def cmd_match(args):
    idx_path = args.index or os.path.join(args.out, "library_index.json")
    index = {}
    if os.path.exists(idx_path):
        with open(idx_path, encoding="utf-8") as f:
            index = json.load(f)
    rows = index.get("rows", [])

    for f in args.pdfs:
        if not os.path.exists(f):
            print(f"MISSING: {f}")
            continue
        text = pdf_text(f, 3)
        ntext = norm_title(text)
        print(f"\n=== {os.path.basename(f)}  ({os.path.getsize(f)/1048576:.1f} MB)")
        print(f"    {' '.join(text.split())[:120]}")

        # Strongest signal: a DOI printed inside the PDF.
        found = [d.lower().rstrip(".") for d in
                 re.findall(r"10\.\d{4,9}/[^\s\"'<>,;)]+", text)]
        hit = next((d for d in found if any(norm_doi(r.get("doi", "")) == d for r in rows)), None)
        if hit:
            row = next(r for r in rows if norm_doi(r.get("doi", "")) == hit)
            print(f"    DOI -> {hit}")
            print(f"    itemKey {row['key']}   [{row['journal']}]")
            print(f"    {row['title'][:88]}")
            continue

        # Fallback: title-token overlap.
        best, score = None, 0.0
        for r in rows:
            toks = set(norm_title(r.get("title", "")).split())
            if len(toks) < 5:
                continue
            s = len(toks & set(ntext.split())) / len(toks)
            if s > score:
                best, score = r, s
        if best and score >= 0.5:
            print(f"    title match -> {best['key']}  (score {score:.2f})")
            print(f"    [{best['journal']}]  {best['title'][:80]}")
        else:
            print(f"    NO MATCH (best {score:.2f})")
            if found:
                print(f"    dois in text: {found[:4]}")


# --- cli -------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("index", help="build a de-duplication index of the library")
    p.add_argument("--out", default=WORKDIR)
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("verify", help="Crossref-check DOIs and resolve PDF links")
    p.add_argument("dois", nargs="+", help="DOIs or a file containing one per line")
    p.add_argument("--out", default=WORKDIR)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("match", help="match downloaded PDFs to library items")
    p.add_argument("pdfs", nargs="+")
    p.add_argument("--out", default=WORKDIR)
    p.add_argument("--index", default=None)
    p.set_defaults(func=cmd_match)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
