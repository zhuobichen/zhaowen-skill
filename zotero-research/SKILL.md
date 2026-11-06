---
name: zotero-research
description: Search the user's Zotero library by full text, pull matching passages out of PDFs, and produce formatted citations for writing papers. Use when the user asks what their library says about a topic, wants to find papers they already own, needs a citation for a claim, is writing a paper and needs references from their own collection, or wants to compare what multiple Zotero items claim about the same subject.
argument-hint: "[query] [--passages] [--authors NAME] [--kind pdf|note|both] [--json]"
---

# Zotero Research

Find, quote and cite from the user's own Zotero library. Built for the
"write a paper without leaving Zotero" workflow: locate the papers they
already own, read the exact passages, and emit citations they can paste.

## Do NOT build a vector store

Zotero already maintains an **FTS5 full-text index** of every PDF and note it
has indexed (`fulltext.sqlite`). That index is the retrieval layer, and it is
already built, tokenised and current. Rebuilding it as RAG would mean
re-extracting ~280 PDFs, re-chunking them, embedding them and keeping a
second copy in sync with Zotero — and chunking damages exactly the content
this work depends on:

- chemical formulas get split (`PM2.5` → `PM2`, `5`)
- measurement units and subscripts are mangled
- DOIs and citations are broken across chunk boundaries
- a passage about a method ends up separated from its numbers

For "what does my library say about X", keyword retrieval over an existing
FTS5 index beats a naive chunk+embed pipeline. Reach for embeddings only if
the user asks for semantic similarity beyond keywords ("papers like this one").

## The tool

```bash
python scripts/zotero_search.py "MDA8"                      # find papers
python scripts/zotero_search.py "ozone AND trend" --limit 10
python scripts/zotero_search.py "data fusion" --passages    # with quotes
python scripts/zotero_search.py "MDA8" --authors "Di"      # filter
python scripts/zotero_search.py "MDA8" --year-from 2015 --year-to 2026
python scripts/zotero_search.py "MDA8" --kind pdf          # PDF bodies only
python scripts/zotero_search.py "MDA8" --kind note         # notes only
python scripts/zotero_search.py "MDA8" --json              # for further processing
python scripts/zotero_search.py --find-doi "10.1021/acs.est.5c16412"
python scripts/zotero_search.py --list-cites "10.1021/acs.est.5c16412"
```

Output per hit: title, authors, journal, year, DOI, Zotero item key, and
whether the match was in the PDF body or in a note. `--passages` adds the
matching sentences with page numbers, pulled from the PDF.

### Query syntax

FTS5 syntax is passed through, so `AND` / `OR` / `NOT` and `"exact phrase"`
work. Everything else is auto-quoted, so `PM2.5` and `MDA8` are safe as-is.

## The workflow for writing a paper

1. **Locate** — `zotero_search.py "<topic terms>" --limit 20 --passages`
   Read the passages to learn what the user's own papers actually claim.

2. **Expand** — a good first query is often too narrow. Re-run with
   synonyms: "MDA8" → "eight-hour" / "8-hour maximum" / "daily maximum";
   "MDA8" → "surface ozone" / "ground-level ozone".

3. **Cite** — `--list-cites <DOI>` gives a formatted citation including the
   Zotero citationKey (which is what a `.bib` or better-bibtex export uses).

4. **Read deeper** — with a Zotero item key in hand:
   - `mcp__zotero__get_content` with `{"itemKey": "<KEY>", "mode": "complete"}`
     returns the full text
   - `mcp__zotero__get_item_details` returns metadata plus attachments and notes
   - `mcp__zotero__get_annotations` returns the user's own PDF highlights
   - `mcp__zotero__write_note` (action `create`) attaches a note to the item

5. **Check the library's own notes first.** The user has 210 notes, many of
   them hand-written reading notes. `--kind note` searches them. A note the
   user wrote is often more useful than the paper text.

## Reporting back

When answering "what does my library say about X":

- lead with the **claim**, then the **citation** (authors, year, journal, DOI)
- quote the passage when the exact wording matters
- name the **Zotero item key** so the user can jump to it in Zotero
- say when the library **has nothing** on a sub-question — that is a finding
  (it tells the user where the gap is), not a failure to hide

## Machine-specific paths

The script defaults to this machine:
- Zotero data dir `E:\CodeProject\Zotero`
- local API `http://127.0.0.1:23119/api/users/0`
- token / server-id constants at the top of the script

Change them there for another machine. The script needs Zotero **running**
(local API) and the `fulltext` index populated (Zotero indexes PDFs
automatically; "Reindex" in the Advanced preferences forces it).

## Gotchas that cost time to find

- **`zotero.sqlite` is locked while Zotero runs.** The script copies the main
  file plus its `-wal`/`-shm` sidecars into a temp snapshot and reads that.
  Copying only the main file silently loses the WAL (recent transactions).
- **The local API exposes only the 8-character item key, but the FTS5 rowid is
  Zotero's internal numeric itemID.** The mapping comes from `zotero.sqlite`.
- **Chinese notes live in `fulltextNotesCJK`** (tokenizer=ascii); English notes
  in `fulltextNotes` (tokenizer=trigram). The script falls back to the CJK
  table when the English one returns nothing.
- **`search_library` in the Zotero MCP does not index child notes** — use
  `get_item_details(parentKey)` to check whether a note exists.
