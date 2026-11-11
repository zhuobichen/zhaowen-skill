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

### Passing a query with quoted phrases (PowerShell)

PowerShell splits an argument containing quotes, so
`"data products" OR intercomparison` arrives as three separate arguments and
argparse rejects it. Use either form:

```bash
# write the query to a file, then:
python scripts/zotero_search.py --query-file q.txt --limit 10
python scripts/zotero_search.py @q.txt --limit 10
```

Both read the file as UTF-8 with BOM tolerated. A single-term query
(`MDA8`, `fusion`) needs none of this and can be passed positionally.

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

## Reading a paper for a note: read the method section, don't grep for it

A hard-won rule from a real failure. Writing a note on Dharmalingam et al.
(2022, *Environ. Res.* 207:112207), a keyword search over the extracted PDF
text found no mention of cross-validation near the results, so the note
asserted "**this paper did no leave-one-out cross-validation**" — and that
false claim went into advice about the user's manuscript.

The paper's Method §2.2.5 says, verbatim:

> "We also performed leave-one-out cross-validation when feasible. In
> cross-validation, we first excluded observational data from a single
> monitor, and then estimated pollutant concentrations at the corresponding
> monitor location..."

and the Fig. 5/Fig. 6 captions list the methods evaluated that way.

**Why the search missed it:** the phrase lived in a paragraph whose extracted
text was broken across page columns, so a sentence-level regex on the joined
text did not surface it. Keyword hits are evidence of presence, never
evidence of absence.

**The rule:**

- For any claim of the form "this paper does **not** do X", read the whole
  method section first. Absence claims require full reading; presence claims
  do not.
- Before writing "未涉及" / "did not" / "no cross-validation" into a note,
  grep the PDF for **each name of the thing**, not the phenomenon:
  `leave-one-out`, `LOO`, `cross-validation`, `CV`, `holdout`,
  `out-of-sample`, `validation`, `split`.
- When a number appears in multiple places, check every one. This paper
  states "nine methods" in the abstract but "a total of 10 methods" in
  Method §2.2, and shows 11 fields in Fig. 2 (10 + a RF-AOD variant). A note
  that quotes only one figure will contradict the paper's own text.

### Note-writing checklist

Before `write_note`:

1. Read abstract → method → results → discussion → conclusion. Not just the
   abstract and a keyword scan.
2. For every quantitative claim, note **where** it came from (which table,
   which section). If a number appears twice and differs, say so.
3. Distinguish **"the paper did not do X"** from **"X is not reported in the
   section I read"**. Only the first is a finding.
4. If the paper feeds a specific claim in the user's manuscript, check that
   the claim is actually supported *there* and not in a sister publication.
   (Here: "coarse spatial gradient" traced to Yu et al. 2018, not
   Dharmalingam 2022 — the latter only describes it qualitatively.)
5. Check for existing notes before writing, and never overwrite a note the
   user clearly wrote by hand (look for their own shorthand, a date-tagged
   prefix, or a conversational voice). Add a second note instead.

### Verifying a note really landed

`write_note` returns `contentLength`; re-read the item's `notes` array and
compare. A model may accidentally pass a placeholder string as the content —
after writing, read the note key back and confirm the body is longer than a
few thousand characters for a full note.

## Auditing coverage against a manuscript

`scripts/check_refs.py` answers, in one pass: does the library hold every
reference the manuscript cites, which of them still carry only a stub note,
and which have a real five-section reading note.

```bash
# Per-reference audit against a manuscript's reference list.
python scripts/check_refs.py <manuscript.md>
python scripts/check_refs.py <manuscript.md> --json refs.json

# Note ages across the whole library (machine-generated vs human-edited).
python scripts/check_refs.py --timestamps
```

A note counts as a **full reading note** when it is at least 2000 characters
and contains all of `核心摘要 / 方法要点 / 主要结果 / 存疑`. Anything under 600
characters, or carrying two or more of the stub markers (`待补`, `自动初稿`,
`摘要级`, `未经全文核对`), is reported as a stub.

`--timestamps` distinguishes machine output from human work: a note whose
`dateModified` is within two minutes of `dateAdded` was written in one shot,
while a gap of hours or days means someone edited it. This library's 2026-11-11
batch (81 notes) was all created within a two-minute window at 01:42–01:43,
which is the signature of an automated pass — and several of those were
coverage notes generated from abstracts. Use the timestamps before deciding
what to overwrite.

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
