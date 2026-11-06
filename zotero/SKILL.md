---
name: zotero
description: Use Zotero for bibliography management, PDF reading, reference generation, and thesis writing. Use when working with academic references, citations, PDFs from Zotero, or generating LaTeX documents with references.
argument-hint: "[action] [params...]"
---

# Zotero Skill

Manage Zotero library for bibliography management, PDF content reading, reference generation, and SCUT thesis writing with LaTeX.

## Tooling: prefer `mcp__zotero__*` over the legacy CLI

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

### Helper script

`scripts/zotero_batch.py` implements steps 1, 2 and 5 as one command:

```bash
# Build a de-duplication index of the current library.
python scripts/zotero_batch.py index --out <workdir>

# Crossref-check a DOI list, resolve each DOI to a direct PDF link, and
# flag anything already in the library.
python scripts/zotero_batch.py verify dois.txt --out <workdir>

# Match downloaded PDFs to their library items by the DOI inside the file.
python scripts/zotero_batch.py match <file.pdf> [...] --out <workdir>
```

It prints the `itemKey` for each matched PDF — that key is what
`write_item(action=import)` needs as `parentItemKey`.

## Safety rules for writes

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
