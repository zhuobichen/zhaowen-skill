---
name: zotero
description: Use Zotero for bibliography management, PDF reading, reference generation, and thesis writing. Use when working with academic references, citations, PDFs from Zotero, or generating LaTeX documents with references.
argument-hint: "[action] [params...]"
---

# Zotero Skill

Manage Zotero library for bibliography management, PDF content reading, reference generation, and SCUT thesis writing with LaTeX.

## Three ways to touch the library - pick deliberately

Every task reaches Zotero through one of three channels. They differ in what
they can do, what they cost, and what can go wrong. Choosing the wrong one is
the most common source of wasted turns.

| | MCP plugin | SQLite (offline) | An add-on of your own |
|---|---|---|---|
| Entry point | `mcp__zotero__*` over `http://127.0.0.1:23120/mcp` | `zotero.sqlite` on disk | `bootstrap.js` inside an `.xpi` |
| Zotero must be | **running** | **closed** | running |
| Exercise | whole-library reads, single edits | bulk writes, schema-level surgery | UI that must persist |
| Atomicity | per call, Zotero's own transaction | one `BEGIN IMMEDIATE` you control | whatever you write |
| Failure mode | typed error | silent corruption if a FK or `synced=0` is missed | bootstrap throws and the add-on vanishes |

### MCP - the default for reading and small edits

25 tools, no JavaScript evaluation, **no delete**. It uses Zotero's own
translators, so anything it creates has correct item types and field
normalisation. Reach for it first:

```
get_libraries / search_library / get_item_details / get_content
write_item / write_metadata / write_tag / write_note
create_collection / add_items_to_collection / remove_items_from_collection
```

`search_library` cannot find notes whose first line is a heading like
`# 分类索引：X` - it returns `total: 0` even though they exist. Detect them
through SQLite instead.

### SQLite - only when the volume justifies closing Zotero

Close Zotero first. A `-wal` file means writes are still buffered; editing
underneath a live process gives you a database the next launch may not read.

**Back up before every write.** `zotero.sqlite` sits next to `-wal` and `-shm`;
copy all three, because the base file alone is stale.

```python
import shutil, sqlite3, subprocess, tempfile
from pathlib import Path

ZOT = Path(r"E:\CodeProject\Zotero")
BACKUP = Path(tempfile.gettempdir()) / "zt_before_edit"
BACKUP.mkdir(exist_ok=True)

# 1. refuse to run against a live process
out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq zotero.exe"],
                     capture_output=True, text=True).stdout
assert "zotero.exe" not in out.lower(), "close Zotero first"

# 2. snapshot all three files
for suffix in ("", "-wal", "-shm"):
    src = ZOT / ("zotero.sqlite" + suffix)
    if src.exists():
        shutil.copy2(src, BACKUP / ("zotero.sqlite" + suffix))

# 3. one transaction, so a mid-way failure rolls back
con = sqlite3.connect(str(ZOT / "zotero.sqlite"))
try:
    con.execute("BEGIN IMMEDIATE")
    ...
    con.commit()
except Exception:
    con.rollback()
    raise
```

Tables you will actually touch, and the traps in each:

| Table | What it holds | Trap |
|---|---|---|
| `items` | every row, keyed by a 8-char base32 `key` | notes and attachments are items too |
| `itemData` + `itemDataValues` | field values, shared by value | reuse an identical `valueID` instead of inserting duplicates |
| `collectionItems` | membership | no unique constraint - inserting twice makes an item appear twice |
| `itemTags` + `tags` | tag assignment | `tags` has **no colour column**; colours live in `syncedSettings` |
| `itemNotes` | HTML note bodies | `parentItemID` NULL means a standalone note |
| `deletedItems` | the trash, by `itemID` | deleting a row from `items` is not how you trash something |
| `fields` | field name -> `fieldID` | look it up, never hard-code the id |

**Reads can run without closing Zotero** if you copy the three files to a temp
directory first and open that copy read-only. That is what every diagnostic in
this repo does:

```python
con = sqlite3.connect(f"file:{copy_path}?mode=ro", uri=True)
```

### An add-on - when the change has to survive

A column, a menu item, a toolbar button: anything the user must see on every
launch. Writing one is a separate discipline - see the twelve Zotero 10
pitfalls in `zotero-collection-tags/README.md`. The short version:

- register columns as the **first statement** in `startup()`, before any `await`
- no `importESModule` at module scope; one throw kills the whole bootstrap
- write files with `nsIFileOutputStream`, not `writer`/`TextEncoder` on strings
- pack with forward slashes; `.NET CreateFromDirectory` emits backslashes, which
  `nsIZipReader.getEntry` will not find

### The decision rule

```
read something                 -> MCP
edit one item                  -> MCP
add / move < ~20 items         -> MCP
bulk rewrite (> ~50 rows)      -> SQLite, Zotero closed, backup first
anything the user must SEE     -> an add-on
```

Why the volume threshold: an MCP round trip costs a request and a transaction
each, so 200 individual `write_tag` calls is minutes of wall clock and 200
chances to fail halfway. One `BEGIN IMMEDIATE` over 200 rows is milliseconds and
all-or-nothing.

### Verifying afterwards

Whichever channel wrote, read back through a **different** one. If SQLite wrote,
confirm via MCP; if MCP wrote, confirm via a SQLite snapshot. Same-channel
verification only proves the write was accepted, not that it landed where the
other readers look.

```python
# after a bulk SQLite write, re-open a fresh snapshot and count
con = sqlite3.connect(f"file:{fresh_copy}?mode=ro", uri=True)
n = con.execute("""SELECT COUNT(*) FROM itemData d
  JOIN itemDataValues v ON v.valueID = d.valueID
  JOIN fields f ON f.fieldID = d.fieldID
  WHERE f.fieldName = 'extra' AND v.value LIKE '%Citations:%'""").fetchone()[0]
```

### MCP tool reference

DSH and Claude Code sessions connect to Zotero's `zotero-mcp-plugin` over MCP.
Those tools are the primary path — they are typed, validated, and use Zotero's
own translators:

| Capability | MCP tool |
|------------|----------|
| Import by identifier (DOI / arXiv / ISBN / PMID / ADS bibcode) | `mcp__zotero__add_by_identifier` |
| Create an item, attach a local PDF | `mcp__zotero__write_item` |
| Edit title / abstract / date / DOI / creators | `mcp__zotero__write_metadata` |
| Add / remove tags | `mcp__zotero__write_tag` |
| Create / rename / delete a collection | `mcp__zotero__create_collection`, `update_collection`, `delete_collection` |
| Move items into a collection | `mcp__zotero__add_items_to_collection`, `remove_items_from_collection` |
| Read notes | `mcp__zotero__write_note` (action `create`/`update`/`append`) |
| Search the library | `mcp__zotero__search_library` |
| Read PDF full text | `mcp__zotero__get_content`, `search_fulltext` |
| Read annotations | `mcp__zotero__get_annotations`, `search_annotations` |

> **There is no delete-item tool.** `write_item` / `write_metadata` can only
> create and edit. To remove an item, use the Zotero local API — see
> "Two things that will bite you" below for the exact recipe.

**Import rule:** prefer `add_by_identifier` over `write_item` whenever an
identifier (DOI, arXiv ID, ISBN, PMID) exists — `add_by_identifier` runs
Zotero's own translators, so item type, venue, authors and date come out
correct, while `write_item` requires you to guess metadata by hand and often
picks the wrong item type. `write_item` is the fallback for sources with no
identifier (e.g. a local PDF with no metadata).

**Batch limit:** `add_by_identifier` runs as a background job above 3
identifiers; poll it with the `jobID` field it returns.

## Importing a paper with its PDF — the working recipe

Verified end-to-end on 2026-11-05. Three steps:

1. **Import the metadata** so Zotero's translator fills in the fields:
   ```json
   {"identifiers": ["arXiv:1706.03762"], "saveAttachments": false}
   ```
   → returns `results[0].item.itemKey` (e.g. `P3EE4V82`).

2. **Attach the local PDF** as a child of that item:
   ```json
   {"action": "import", "filePath": "<abs path>.pdf",
    "parentItemKey": "<itemKey>", "title": "Full Text PDF"}
   ```
   → returns `attachmentKey`. Zotero copies the file into
   `E:\CodeProject\Zotero\storage\<attachmentKey>\` and builds the full-text
   index automatically (`hasFulltext: true`).

3. **Verify** with `get_item_details` — check the attachment shows
   `contentType: application/pdf`, the expected `size`, and a `path` inside
   the storage directory.

### Two things that will bite you

- **`add_by_identifier` can time out but still succeed.** A timeout on the
  tool call does not mean the import failed. Before retrying, run
  `search_library` with the title — re-importing the same identifier returns
  status `exists` rather than creating a duplicate, so a blind retry is
  safe, but check first so you don't end up with two entries.

- **`write_item` / `write_metadata` cannot delete.** There is no delete tool
  in this MCP surface. To remove an item you need the Zotero local API:
  1. `POST http://127.0.0.1:23119/api/local/authorize` with
     `{"username":..., "password":..., "appName":"dsh", "scopes":["library","files"]}`
     and the `Zotero-Server-ID` header → returns a token (it is remembered,
     so later calls work without re-authorizing).
  2. Read `Zotero-Server-ID` from any response header, then
     `DELETE http://127.0.0.1:23119/api/users/0/items/<itemKey>` with
     `Authorization: Bearer <token>` and
     `If-Unmodified-Since-Version: <version>`. A `204` means deleted;
     verify with a follow-up GET (`404` = gone).

`zotero-cli` (the legacy `cli-anything-zotero` CLI) remains available for
scripts that need shell access, but prefer the MCP tools interactively.

## Importing many papers at once

When the task is "add these N papers", work in this order. Each step has a
trap that silently produces wrong results — the details are in the
**Batch import: pitfalls** section below.

1. **Verify every DOI against Crossref.** A DOI list can contain typos, or a
   DOI that points at a different paper than the one the title suggests.
   Compare the registered title with yours (normalise: strip HTML, lowercase,
   collapse non-alphanumerics; keep CJK so Chinese titles still match).
   Report title / year / journal / pages / authors per DOI — that report is
   what the user checks against.

2. **De-duplicate against the library.** Build an index of the existing
   library first, then match candidates on normalised DOI *and* normalised
   title. Check the first 6–10 significant title words too, for near-misses.

3. **Import** with `add_by_identifier` (dry-run first, batch above 3
   identifiers runs as a background job — poll the `jobID`).

4. **Get the PDFs.** Open-access ones come down automatically with
   `saveAttachments: true`. Paywalled ones need a direct link — see below.

5. **Attach the PDFs** to the right items.

### Elsevier: the PII is the key, and it is not derivable from the DOI

Elsevier's PDF URL needs an internal article id (the **PII**) such as
`S0306457325004157`. You cannot derive it from the DOI — `10.1016/j.ipm.2025.104474`
does not contain it, and guessing gives a 404.

Resolve it from the DOI redirect:

```
https://linkinghub.elsevier.com/retrieve/pii/<PII>   ->  Location: .../pii/<PII>
```

or follow `https://doi.org/<DOI>` and read the PII out of the final URL.
Then:

```
https://www.sciencedirect.com/science/article/pii/<PII>/pdfft
```

**Verified PIIs (2026-11-06):**

| DOI | PII |
|---|---|
| `10.1016/j.ipm.2025.104474` | `S0306457325004157` |
| `10.1016/j.envsoft.2025.106438` | `S1364815225001227` |
| `10.1016/j.jag.2025.104506` | `S1569843225001530` |
| `10.1016/j.resenv.2025.100219` | `S2666916125000313` |
| `10.1016/j.rsase.2025.101793` | `S2352938525003465` |
| `10.1016/j.acags.2026.100416` | `S259019742600100X` |
| `10.1016/j.atmosres.2025.108213` | `S0169809525003059` |
| `10.1016/j.apr.2026.103070` | `S1309104226001868` |

Other publishers:

| Publisher | PDF URL |
|---|---|
| Springer | `https://link.springer.com/content/pdf/<DOI>.pdf` |
| T&F | `https://www.tandfonline.com/doi/pdf/<DOI>?download=true` |
| ACS | `https://pubs.acs.org/doi/pdf/<DOI>` |
| Wiley | `https://onlinelibrary.wiley.com/doi/pdfdirect/<DOI>` |

### Cloudflare blocks scripts here — give the user the link

This machine's IP is rate-limited by Cloudflare. Elsevier, T&F and ACS serve a
"Are you a robot?" captcha to automated traffic, and the challenge endpoint
(`?crasolve=1`) answers 403.

The user's own Chrome, with their institutional session, passes it fine — the
article page shows *"Brought to you by: South China University of Technology"*.

**So: hand the user a table of DOI → direct PDF link → Zotero itemKey, plus
one folder to drop the files into. They download; you attach.** Five
automated approaches were tried and all failed: copying the Chrome profile
into Playwright, `context.request.get()`, in-page navigation with a route
handler, CDP `Browser.setDownloadBehavior`, and clicking the publisher's own
"View PDF" button. Even the signed URL the article page exposes
(`/pdfft?md5=<signature>&pid=1-s2.0-<PII>-main.pdf`) gets challenged —
200 `text/html`, then a redirect to `?crasolve=1`, then 403. Don't re-test
these; Springer PDFs do work from a script (no Cloudflare there).

## Batch import: pitfalls

Each of these produced wrong results in practice.
**The Zotero local API pages with `start`, not `offset`.** `offset` is a key
filter and returns the same page forever. Using it, a 239-item library
produced 988 rows containing only 76 unique keys and 66 unique DOIs — and
de-duplication then let papers through that were already in the library.
Always guard the loop against a repeated page.

**Match a downloaded PDF by the DOI printed inside it, never by filename.**
Elsevier writes `1-s2.0-S0306457325004157-main.pdf`, which says nothing about
the paper, and a stale file with the same name fools you. Extract with
`pypdf`/`PyPDF2` over the first 3 pages and regex for
`10\.\d{4,9}/[^\s"'<>,;)]+`; fall back to title-token overlap only if no
DOI is present.

**Crossref times out intermittently here.** Both `URLError: timed out` and
`SSL handshake timed out` occur. Retry 3–4 times before calling a DOI
invalid — a timeout is not the same as "DOI does not exist".

**`hasFulltext` is not populated in the `/children` response.** It always
reads as missing there. Use `get_item_details`, which reports it correctly.

**Python's PDF libraries are noisy.** `PyPDF2` on some publisher PDFs emits
thousands of "Ignoring wrong pointing object" warnings. Silence them with
`warnings.filterwarnings("ignore")` plus
`logging.getLogger("pypdf").setLevel(logging.CRITICAL)`.

**`add_by_identifier` can time out but still succeed.** See
"Two things that will bite you" above.

## Merging duplicate items

The library accumulates duplicates in three distinct layers, and conflating
them leads to data loss. Check each layer separately.

| Layer | What it is | How to detect |
|-------|-----------|----------------|
| **Item** | the same paper stored as two Zotero items | same normalised DOI, or same normalised title |
| **Attachment** | two PDF attachments under one item | identical bytes under two attachment keys |
| **Storage file** | one PDF file on disk under two keys | same md5 in two `storage/<key>/` folders |

### The API trap that breaks every write

**Every PATCH / PUT / DELETE against the local API must carry
`If-Unmodified-Since-Version`.** Without it the API answers **428
Precondition Failed** on every single call — reads work fine, so the failure
looks like a permissions problem rather than a missing header.

```python
cur = get(f"/items/{item_key}")["data"]["version"]
req = urllib.request.Request(
    f"{BASE}/items/{item_key}", data=body, method="PATCH",
    headers={**H, "Content-Type": "application/json",
             "If-Unmodified-Since-Version": str(cur)},
)
```

A 21-action merge run without this header returned 428 on all 21 calls. It
looked like it had worked until the response codes were read.

### "Same paper" is not the same as "same file"

Two PDFs of the same paper can differ in bytes — publishers embed a download
timestamp, so the same document fetched twice has different md5. Compare
**extracted text**, not bytes:

```python
import difflib
ratio = difflib.SequenceMatcher(None, text_a, text_b).quick_ratio()
```

Measured on this library: 7 of 8 duplicate groups had byte-different but
text-identical PDFs (one pair differed by 720 bytes and 67 KB respectively).

### Supplementary material is NOT a duplicate

A paper's supplementary file is a separate document that belongs on the
**same item**. Detect it from an anchored phrase on the first page — a loose
search for "supplement" hits ordinary body text and misclassifies articles:

```python
SI_STRICT = [
    r"supplementary\s+materials?\s+for",   # Science / Elsevier SI banner
    r"^\s*supplementary\s+information\b",
    r"^\s*supporting\s+information\b",
    r"^\s*supplementary\s+material\b",
]
```

Verified case: the Science paper "Fires reverse progress toward ozone air
quality standards" was stored as two items — a 29-page
*"Supplementary Materials for …"* file and the 6-page article body. Merging
them means keeping **both** PDFs on one item, the SI renamed
`Supplementary Information` and the body `Full Text PDF`.

### Pick the keeper by content, not by accident

Score candidates on metadata completeness. Weight abstract **length**, not
"has an abstract" — a boolean test makes a 1218-character abstract tie with a
3487-character one:

```python
def score(m):
    return (min(m["abstract_len"], 4000) // 40) * 3 \
        + bool(m["journal"]) * 12 + bool(m["volume"]) * 8 \
        + len(m["notes"]) * 25 + len(m["pdfs"]) * 5
```

Before deleting a losing item, migrate **notes, tags, attachments and
collections** to the keeper, and fill blank fields on the keeper from the
loser (a journal name, a volume). A 2317-character note lost to a
61-character one is the worst kind of silent loss.

### Deleting storage files: check the parent, not just the attachment

A `storage/<key>/` folder is orphaned if no attachment row points at it —
but verify by looking up **both** the attachment key and its `parentItem`:

```python
def in_library(key):
    try:
        get(f"/items/{key}")
        return True
    except Exception:
        return False
```

A pagination bug made four live attachments look orphaned (their parent
items were still in the library). Deleting those would have destroyed real
papers. A separate check found that one "orphan" was the **only** copy of a
document in the library — it was moved to the backup instead of deleted.

### Verify after merging

```python
# duplicate groups should be zero
by_doi = Counter(norm_doi(i["data"]["DOI"]) for i in bib if ...)
by_title = Counter(norm_title(i["data"]["title"]) for i in bib if ...)

# every note still has a live parent
for i in items:
    if i["data"]["itemType"] == "note" and i["data"].get("parentItem"):
        get(f"/items/{i['data']['parentItem']}")   # raises if orphaned
```

Deleting an item via the local API moves it to the **trash**, not out of the
library — recoverable from the Zotero trash, but the trashed item no longer
appears in its collection.

### Helper scripts

`scripts/` holds the pieces of this pipeline as standalone programs.

```bash
# Build a de-duplication index of the current library.
python scripts/zotero_batch.py index --out <workdir>

# Crossref-check a DOI list, resolve each DOI to a direct PDF link, and
# flag anything already in the library.
python scripts/zotero_batch.py verify dois.txt --out <workdir>

# Match downloaded PDFs to their library items by the DOI inside the file.
python scripts/zotero_batch.py match <file.pdf> [...] --out <workdir>
```

`zotero_batch.py match` prints the `itemKey` for each matched PDF — that key
is what `write_item(action=import)` needs as `parentItemKey`.

For de-duplication:

```bash
# Report every duplicate, at all three layers.
python scripts/duplicate_report.py

# Merge them. ALWAYS dry-run first and read the plan.
python scripts/merge_dupes.py --dry-run
python scripts/merge_dupes.py --execute
python scripts/merge_dupes.py --execute --group 8   # one group only
```

`merge_dupes.py --execute` migrates notes, tags, attachments and
collections to the keeper before deleting anything, and it handles the
supplementary-material case (both PDFs kept on one item). Back up the
database first — see the `zotero-db` skill.

The scripts carry machine-specific defaults (local API token, storage path).
Change the constants at the top to match another machine.

## Organising a library into collections (batch classification)

Turning a whole library into a navigable taxonomy. Verified on 2026-11-10 on a
283-item library: 12 collections created, 283 memberships written, zero
orphans, item count unchanged (903 → 903).

### Pick mutually exclusive buckets, not a tag cloud

Zotero collections are like tags — an item can sit in many — which makes it
tempting to file everything everywhere. Don't. A library where the same paper
appears in four places is not organised.

Decide the **decision rule first**, then apply it once per item. A rule that
worked:

| Top level | Test |
|---|---|
| **方法 / Method** | produces a reusable method/framework as its main output |
| **应用 / Application** | no reusable method product; the contribution is a result, a product comparison, or an applied analysis |

Borders that recur, and how they resolve:
- "compares N methods and recommends the best" → **application** (it yields
  selection advice, not a new method)
- "reimplements a classic method with a materially new framework" →
  **method** (a reusable implementation is a method product)
- "applies an existing method to a new scene/pollutant" → **application**
- the same author can publish one of each: a product paper goes to
  *application*, its companion uncertainty-framework paper to *method*

### Do not trust regex over titles

A keyword rule engine was tried first and mis-filed whole families: a genuine
deep-learning diffusion paper landed in statistics because the title mentioned
a kriging prior; an ensemble-model-averaging product landed in statistics
because "ensemble" was listed under a data-assimilation family. The failure
was not tuning — the rules cannot tell *what the contribution is*.

What works: read every title once, write the decision **as a table in a file**
(`KEY: (top, sub)` with a one-line note per item), and let the renderer produce
the CSV, the review document and the Zotero write from that single source.
Manual judgement on 283 items is ~30 minutes; the table is also what the user
edits when they disagree.

Ship the user a **review document before writing**: one table per bucket with
key / year / title / has-note, plus the counts. They will catch the two or
three calls you got wrong.

### Write path: MCP first, SQLite only when forced

`mcp__zotero__create_collection` + `add_items_to_collection` is the correct
path. It was unavailable here — **Zotero 10's local HTTP API is read-only**:
`POST /api/users/0/collections` answers `428 Precondition Failed` even with a
version header, and the MCP surface has no bulk-move primitive for 283 items.

Falling back to SQLite worked, but only with these guards:

1. **Back up first** (`zotero-db` skill's backup Action).
2. **Refuse to run while Zotero is open.** Check with `tasklist /FI
   "IMAGENAME eq zotero.exe"` and abort; an open Zotero holds the WAL and will
   overwrite the write on exit.
3. **One transaction** — `BEGIN IMMEDIATE` … `commit()`, rollback on any
   exception, so a partial taxonomy never lands.
4. **Dry run by default.** `--dry-run` prints the planned tree and counts;
   `--apply` is a separate explicit flag.
5. **Verify by count**: planned vs actual per collection, orphans
   (`collectionItems` → missing `items`), duplicate memberships, and the total
   `items` count before/after (must be unchanged — filing moves items, never
   creates them).

### Generate real keys, not sequential ones

Zotero object keys are 8 characters from `A-Z2-9` (Crocker base32: no `0`, no
`1`). A first pass produced `3OGAAAAA`, `4OGAAAAA`, … — unique and
well-formed as strings, but a conspicuously pattered key invites collisions
with Zotero's own generator and with sync. Rewrite them with
`random.SystemRandom` over the correct alphabet and re-verify
`re.fullmatch(r"[A-Z2-9]{8}", key)`.

Also note: `str.isalnum()` is **False** for `₃` (subscript three, category
`No`), so normalising `MLP-O₃` by "keep alnum" yields `MLPO`, not `MLPO3`.
Fold subscripts to digits explicitly
(`str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")`) before comparing filenames or
titles.

### Retiring the old layout

Users keep ad-hoc collections (`hp`, `其余文献`) from earlier sessions. Before
deleting them, check whether their contents are **already** in the new
taxonomy — in a 30-item case all 30 were, so the old collections were pure
duplication, and deleting the collection rows (not the items) removed the
visual clutter without losing anything. Always report
`items before == items after` after such a delete.

For genuinely off-topic records (a reviewer worksheet, an unrelated
experiment), create a top-level **垃圾箱 / Trash** collection rather than
deleting: the record stays searchable and recoverable. Keep it out of the main
tree.

### Describing the result to the user

The parent collections hold zero items by design — they are grouping
containers. Say so, or the user opens `方法` and concludes the classification
failed. Tell them to click the disclosure triangle.

## Filling a third-party plugin's field: read its parser first

When a plugin shows a column computed from a field (citation counts, citation
keys, reading status), write the value in **the exact shape that plugin
parses**, not the shape you would invent. Two rounds of guesswork are cheaper
to avoid than to debug: open the plugin's script and find the regex.

A worked example, Citation Tally:

```js
// content/scripts/citationtally.js
const patt0 = new RegExp(`^Citations: *(\\d+) *\\(${safeTag}\\) *\\[\\d{4}-\\d{1,2}-\\d{1,2}\\]`, "i");
const patt1 = new RegExp(`^Citations: *(\\d+) *\\(${safeTag}\\)`, "i");
```

So the stored line must be `Citations: 87 (Crossref) [2026-11-11]`, where the
tag is the plugin's own l10n display name (`Crossref`, `INSPIRE`,
`SemanticScholar`), not an internal id like `crossref` or `s2`. Writing
`citationCount: 87` renders nothing, with no error anywhere.

Three practical notes from that exercise:

- **Check the display format before writing.** With two sources enabled the
  plugin renders `12 | -` (pipe-separated, dashes for missing). That is by
  design; configure a single source if a bare number is wanted.
- **Preprints need their own source.** Crossref has no citation data for
  `10.48550/arXiv.*`, so a Crossref-only configuration leaves every preprint
  blank. Either keep the second source for display, or label the value with the
  source that actually produced it.
- **Reconcile two sources by max, not by first hit.** Semantic Scholar updates
  recent papers sooner; Crossref covers non-English venues better. Taking the
  larger value avoids reporting zero just because one index lags.

Fetch pattern that worked for 264 DOIs:

```python
crossref  = f"https://api.crossref.org/works/{doi}"                  -> is-referenced-by-count
semantic  = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=citationCount"
```

Six workers, a JSON cache keyed by DOI, and a 3 s back-off on HTTP 429. 264
lookups completed without a block.

## Organising by journal rank (中科院分区)

Pairing a taxonomy with a journal-tier column is cheap and immediately useful
("which buckets are mostly Q1?"). Build it from
`publicationTitle` + `ISSN`, not from item titles.

- **The CAS zone table is a paid, official database.** Free aggregator sites
  republish it; treat any scraped value as indicative and say so in the
  output. Note the edition: the **2025 upgraded edition** is what most
  institutions use. Some journals are absent from the upgrade and only carry a
  **basic-edition** zone — label which edition a number came from rather than
  silently mixing them.
- Page text often embeds structured JSON (`"cas_zone":1,"cas_top":1`), which
  is far more reliable to parse than the visible HTML. Journal slugs are
  lowercase-hyphenated but irregular (`Lancet Planetary Health` drops its
  leading "The"); try a short list of variants before giving up.
- **Separate preprints and unresolved journals from the statistics.** 62 of
  283 items were arXiv preprints with no journal at all — counting them as
  "unknown zone" halves the apparent resolution rate and distorts every
  percentage.


- **Always confirm with the user before a write** (import, create, delete,
  metadata edit, collection move). Say what will be written and where.
- **Never run the cleanup / import scripts that write `zotero.sqlite`
  directly** — see the `zotero-db` skill for details. Direct SQLite writes
  bypass Zotero's own bookkeeping and corrupt the library.
- Prefer `add_by_identifier` with `dryRun: true` first when the target
  collection or duplicates are unclear.
- `delete_collection` with `deleteItems: true` sends items to the trash —
  confirm before using it.
- **Back up the database before any risky write** — see the `zotero-db`
  skill's backup Action.

## Prerequisites

1. **Zotero running** with Local API enabled:
   - Edit → Preferences → Advanced → General → "启动浏览器连接" (Allow browser integration)
   - Port: 23119 (Connector API) / 23120 (MCP server, from `zotero-mcp-plugin`)

2. **MCP connected** (for `mcp__zotero__*` tools):
   - Zotero plugin `zotero-mcp-plugin` must be enabled
   - DSH: the `dsh-zotero-mcp` bundle provides the `mcp-zotero` row

3. **Python PDF library** (for reading PDFs):
   ```bash
   pip install PyPDF2
   ```

4. **MiKTeX installed** (for LaTeX compilation):
   - Path: `C:/Users/chenlizhuo/AppData/Local/Programs/MiKTeX/miktex/bin/x64/xelatex.exe`

## Quick Commands

### List all items in Zotero
```bash
zotero-cli item list
```

### Get item details
```bash
zotero-cli item get [item-key]
```

### List Zotero storage folders
```bash
ls E:/CodeProject/Zotero/storage/
```

## BibTeX File Location

Main BibTeX file for SCUT thesis:
```
C:\Users\chenlizhuo\SCUT_thesis\biblibrary\Zotero_References.bib
```

## Compile References (Multiple Formats)

### Method 1: Use compile_refs.py script
```bash
cd C:\Users\chenlizhuo\SCUT_thesis
python compile_refs.py              # GB/T 7714-2015 (默认)
python compile_refs.py apa          # APA格式
python compile_refs.py gb7714-2015b # GB/T 7714-2015 顺序编码制
```

Output: `test_zotero_refs.pdf`

### Method 2: Manual compilation (if script fails)

```bash
cd C:\Users\chenlizhuo\SCUT_thesis
xelatex -interaction=nonstopmode test_background.tex  # 1st pass
biber test_background                                      # process refs
xelatex -interaction=nonstopmode test_background.tex  # 2nd pass
xelatex -interaction=nonstopmode test_background.tex  # 3rd pass
```

Paths:
- XELATEX: `C:/Users/chenlizhuo/AppData/Local/Programs/MiKTeX/miktex/bin/x64/xelatex.exe`
- BIBER: `C:/Users/chenlizhuo/AppData/Local/Programs/MiKTeX/miktex/bin/x64/biber.exe`

## Read PDF Content from Zotero

```python
from PyPDF2 import PdfReader
import glob
import os

storage_path = 'E:/CodeProject/Zotero/storage/'

# List all available PDFs
for folder in sorted(os.listdir(storage_path)):
    pdfs = glob.glob(os.path.join(storage_path, folder, '*.pdf'))
    if pdfs:
        print(f"{folder}: {os.path.basename(pdfs[0])}")

# Read PDF content (example with first 2 pages)
pdfs = glob.glob(os.path.join(storage_path, '[item-key]', '*.pdf'))
reader = PdfReader(pdfs[0])
print(f"Pages: {len(reader.pages)}")
text = reader.pages[0].extract_text()  # first page
# Handle encoding issues
text = text.replace('\ufffd', '?').replace('\u2212', '-')
print(text[:1000])
```

## Write Thesis Section with References

### Template for test_background.tex
```latex
\documentclass[unicode,master]{scutthesis}

\usepackage[backend=biber,style=gb7714-2015,gbalign=gb7714-2015,gbpub=true,gbnamefmt=lowercase]{biblatex}
\addbibresource[location=local]{biblibrary/Zotero_References.bib}

\begin{document}

\title{论文标题}
\author{陈立卓}
\date{2026年}

\maketitle

\chapter{章节标题}

正文内容，引用文献用~\cite{key}，如~\cite{yu_2025}。

\printbibliography

\end{document}
```

### Compile thesis section
```bash
cd C:\Users\chenlizhuo\SCUT_thesis
rm -f test_background.*
xelatex -interaction=nonstopmode test_background.tex
biber test_background
xelatex -interaction=nonstopmode test_background.tex
xelatex -interaction=nonstopmode test_background.tex
```

Output: `test_background.pdf`

## Workflow: From Zotero to Thesis

### Step 1: List items
```bash
zotero-cli item list
```

### Step 2: Get details for key items
```bash
zotero-cli item get [item-key]
```

### Step 3: Read PDF content (if needed)
Use PyPDF2 to extract text from Zotero storage PDFs.

### Step 4: Update BibTeX
Edit: `C:\Users\chenlizhuo\SCUT_thesis\biblibrary\Zotero_References.bib`

Format:
```bibtex
@article{key_2025,
  title = {Article Title},
  author = {Author, First and Second, Third},
  year = {2025},
  journal = {Journal Name},
  volume = {1},
  number = {1},
  pages = {1-10},
}
```

### Step 5: Write content with citations
Use `\cite{key}` to cite references in LaTeX.

### Step 6: Compile
Use compile_refs.py or manual compilation.

## Common Issues

### "Cannot find .bcf" error
xelatex must run first to generate .bcf before biber:
```bash
xelatex file.tex  # generates .bcf
biber file         # then run biber
```

### "Device or resource busy" (PDF locked)
Close the PDF in your viewer before recompiling.

### Biber exit code 2 but succeeds
Check if .bbl was actually created:
```bash
ls -la file.bbl
```

### Encoding issues in PDF output
PyPDF2 may have encoding issues, common replacements:
```python
text = text.replace('\ufffd', '?').replace('\u2212', '-')
```

## Zotero Storage Structure

- Base path: `E:\CodeProject\Zotero\storage\`
- Each item has a folder named by its Zotero key
- PDFs are stored inside these folders
- Attachment keys differ from parent item keys

## File Paths Reference

| File | Path |
|------|------|
| BibTeX | `C:\Users\chenlizhuo\SCUT_thesis\biblibrary\Zotero_References.bib` |
| compile_refs.py | `C:\Users\chenlizhuo\SCUT_thesis\compile_refs.py` |
| Test thesis | `C:\Users\chenlizhuo\SCUT_thesis\test_background.tex` |
| Zotero database | `E:\CodeProject\Zotero\zotero.sqlite` |
| Zotero storage | `E:\CodeProject\Zotero\storage\` |
| XeLaTeX | `C:/Users/chenlizhuo/AppData/Local/Programs/MiKTeX/miktex/bin/x64/xelatex.exe` |
| Biber | `C:/Users/chenlizhuo/AppData/Local/Programs/MiKTeX/miktex/bin/x64/biber.exe` |
