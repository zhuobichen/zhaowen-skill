---
name: zotero-db
description: Directly operate Zotero local SQLite database for PDF import, citation key generation, fulltext indexing, and database cleanup. Use for batch import, orphan cleanup, or when Zotero API is unavailable.
argument-hint: "[action] [params...]"
---

# Zotero Database Skill

Directly manipulate Zotero's local SQLite database for advanced operations including PDF import, citation key generation, fulltext indexing, and database cleanup.

## When to use this skill vs the MCP plugin

This skill edits `zotero.sqlite` directly, which means **Zotero must be closed**.
That cost only pays off for bulk work. The full breakdown lives in the `zotero`
skill under "Three ways to touch the library"; the short version:

| Task | Channel |
|---|---|
| Read, search, single edits | `mcp__zotero__*` (Zotero running) |
| Bulk writes, > ~50 rows | **this skill** (Zotero closed, back up first) |
| A UI feature the user keeps | an add-on |

**Reads do not need Zotero closed** if you copy `zotero.sqlite` plus its
`-wal` and `-shm` to a temp directory and open the copy `mode=ro`. All the
diagnostics in this repo do that.

**Back up all three files, not just the base.** With a live `-wal` present the
base file alone is stale, and restoring it alone loses recent writes.

## Preferred path: use the MCP tools instead of direct SQLite writes

This skill describes **direct SQLite manipulation**, which is the last resort.
Whenever Zotero's own APIs are available, use them instead — they maintain
Zotero's internal bookkeeping (sync state, item versions, change tracking)
that raw SQL does not:

| Task | Preferred tool |
|------|----------------|
| Import by identifier (DOI / arXiv / ISBN / PMID) | `mcp__zotero__add_by_identifier` |
| Create an item + attach a local PDF | `mcp__zotero__write_item` (action `create` / `import`) |
| Edit metadata | `mcp__zotero__write_metadata` |
| Add / remove tags | `mcp__zotero__write_tag` |
| Collections | `mcp__zotero__create_collection` / `update_collection` / `delete_collection` / `add_items_to_collection` |
| Notes | `mcp__zotero__write_note` |
| Search + full text | `mcp__zotero__search_library` / `search_fulltext` / `get_content` |

Only fall back to the direct-SQL scripts below when the MCP server is
unreachable **and** the user explicitly asks for a database-level operation.

## Safety rules for direct SQLite writes

Direct SQL writes bypass Zotero's own bookkeeping and can corrupt the
library. When they are unavoidable:

- **Back up first** — run the backup Action below. A plain file copy is not
  enough; the script handles WAL correctly (see the traps it avoids).
- **Close Zotero** before any write — an open Zotero holds its own connection
  and will overwrite or conflict with your changes.
- **Never run these without explicit user confirmation:** import PDF, cleanup
  (deletes rows), fulltext index creation.
- Report exactly which rows were touched.

> Note: on this machine Zotero's live database **cannot be opened by another
> process at all** — a normal connection fails with `database is locked`, and
> `?immutable=1` reads a stale snapshot missing the WAL. This is why the
> backup script copies files rather than using the SQLite backup API, and why
> direct SQL writes require Zotero to be closed.

## Prerequisites

1. **Python libraries**:
   ```bash
   pip install PyPDF2
   ```

2. **Zotero closed** when writing to the database directly (to avoid corruption)

## Database Paths

- Database: `E:\CodeProject\Zotero\zotero.sqlite`
- Storage: `E:\CodeProject\Zotero\storage\`
- Backup script: `C:\Users\chenlizhuo\.agents\skills\zotero-db\scripts\zotero_backup.py`

---

## Action: Back up Zotero databases (RECOMMENDED before any risky operation)

Run this **before** any direct-SQL write, bulk edit, or cleanup. It is the only
safe way to snapshot a live Zotero.

### Usage
```bash
python "C:/Users/chenlizhuo/.agents/skills/zotero-db/scripts/zotero_backup.py" "E:/CodeProject/Zotero-backup/<timestamp>"
```

The script takes a destination directory, creates it if needed, and writes one
self-contained `.sqlite` per database plus `BACKUP_INFO.txt` (a manifest with
restore steps).

### What it copies

| Database | Contents |
|----------|----------|
| `zotero.sqlite` | **The library** — items, collections, creators, attachments metadata |
| `fulltext.sqlite` | PDF full-text index |
| `llm-for-zotero-index.sqlite` | LLM for Zotero plugin index |
| `zotero-mcp-vectors.sqlite` | zotero-mcp-plugin vector index |
| `zoplicate.sqlite` | Zoplicate plugin data |
| `beaver.sqlite` | Beaver plugin data |

The PDF files themselves live in `E:\CodeProject\Zotero\storage\`. Back them up
separately with `robocopy`:

```bash
robocopy "E:\CodeProject\Zotero\storage" "<dest>\storage" /E /R:1 /W:1 /MT:8
```

### Why the script is not a plain file copy — the traps it avoids

Zotero runs SQLite in **WAL mode**, and on this machine the live database
cannot be opened by another process at all. Three things follow, all of them
verified by testing on 2026-11-05:

1. **Copying `zotero.sqlite` alone silently loses recent changes.** Committed
   transactions that have not yet been checkpointed live in
   `zotero.sqlite-wal`. A main-file-only copy is stale.

2. **A normal connection reports `database is locked` — even for
   `PRAGMA journal_mode`.** SQLite needs to write the `-shm` (shared-memory
   index) sidecar to open a WAL database read-write, and Zotero owns that
   file. `?immutable=1` bypasses the lock but reads a **stale snapshot that
   excludes the WAL**.

3. **`VACUUM INTO` fails** with `database is locked` after ~20s, and a plain
   `sqlite3.Connection.backup()` blocked for 12 minutes producing 0 bytes,
   because the whole copy holds one read lock and Zotero's sync transaction
   never releases it.

### The method that works

Copy the main file **and** the `-wal` sidecar, delete the stale `-shm`, then
open the copy normally. SQLite replays the WAL into the copy and checkpoints
it, producing one self-contained database with everything Zotero had
committed.

Verification (2026-11-05, live Zotero running): the backup reported **783
items** while `?immutable=1` on the same live file reported **779** — the
difference is exactly the transactions still in the WAL. After the copy,
`PRAGMA integrity_check` returns `ok`.

### Restore

```
1. Close Zotero completely.
2. Replace the matching file in E:\CodeProject\Zotero\ with the backup copy.
3. Delete the stale *.sqlite-wal and *.sqlite-shm files.
4. Start Zotero and verify the library.
```

---

## Action: Import PDF to Zotero

> Prefer `mcp__zotero__write_item` (action `import`) for this — it goes
> through Zotero's own API, keeps sync bookkeeping correct, and creates the
> attachment + full-text index for you. Use `pdf_to_zotero.py` below only when
> the MCP server is unreachable.

### Usage
```bash
cd C:\Users\chenlizhuo\zotero\agent-harness
python pdf_to_zotero.py <pdf_path> [options]
```

### Options
| Flag | Description |
|------|-------------|
| `--type TYPE` | Item type (default: journalArticle) |
| `--title TITLE` | Paper title |
| `--authors AUTHORS` | Authors (separate with `\|`, e.g., "Last, First \| Last2, First2") |
| `--year YEAR` | Publication year |
| `--doi DOI` | DOI |
| `--journal JOURNAL` | Journal name |
| `--volume VOLUME` | Volume |
| `--pages PAGES` | Page range |
| `--index` | Create fulltext index (requires PyPDF2) |
| `--key KEY` | Custom citation key |

### Examples
```bash
# Basic import
python pdf_to_zotero.py "paper.pdf"

# Full metadata import
python pdf_to_zotero.py "paper.pdf" --title "My Paper" --authors "Smith, John | Doe, Jane" --year 2024 --journal "Nature" --index

# With DOI
python pdf_to_zotero.py "paper.pdf" --doi "10.1234/example"
```

### Output
Returns JSON with item_id, key, citation_key, attachment_id.

---

## Action: Cleanup Database

Remove orphan entries, ghost files, and unused storage folders.

### Usage
```python
import sqlite3
import os

ZOTERO_DB = os.path.expanduser("E:/CodeProject/Zotero/zotero.sqlite")
ZOTERO_STORAGE = os.path.expanduser("E:/CodeProject/Zotero/storage")

conn = sqlite3.connect(ZOTERO_DB)
cursor = conn.cursor()

# 1. Delete orphan main items (no itemData, no attachment reference)
cursor.execute('''
    DELETE FROM items WHERE itemTypeID != 3
    AND NOT EXISTS (SELECT 1 FROM itemData WHERE itemID = items.itemID)
    AND NOT EXISTS (SELECT 1 FROM itemAttachments WHERE parentItemID = items.itemID)
''')
print(f"Deleted orphan items: {cursor.rowcount}")

# 2. Delete orphan attachments
cursor.execute('''
    DELETE FROM itemAttachments WHERE parentItemID NOT IN (SELECT itemID FROM items)
''')
print(f"Deleted orphan attachments: {cursor.rowcount}")

# 3. Delete orphan creators
cursor.execute('''
    DELETE FROM creators WHERE creatorID NOT IN (SELECT creatorID FROM itemCreators)
''')
print(f"Deleted orphan creators: {cursor.rowcount}")

# 4. Clean unused storage folders
storage_key_set = set()
cursor.execute("SELECT key FROM items")
for row in cursor.fetchall():
    storage_key_set.add(row[0])
cursor.execute("SELECT key FROM itemAttachments")
for row in cursor.fetchall():
    storage_key_set.add(row[0])

for folder in os.listdir(ZOTERO_STORAGE):
    if folder not in storage_key_set:
        folder_path = os.path.join(ZOTERO_STORAGE, folder)
        if os.path.isdir(folder_path):
            import shutil
            shutil.rmtree(folder_path)
            print(f"Deleted storage folder: {folder}")

conn.commit()
conn.close()
print("Cleanup complete!")
```

### Important
- **Close Zotero before running cleanup** to avoid database corruption

---

## Action: Batch-create collections and file items (direct SQL)

Use this only when the MCP `create_collection` / `add_items_to_collection`
tools are unavailable **and** the user has confirmed. Zotero 10's local HTTP
API is read-only (`POST` → `428`), so a 283-item taxonomy has no API path.

Verified 2026-11-10: 12 collections, 283 memberships, 0 orphans, item count
unchanged. The full narrative and the decision-rule discussion live in the
`zotero` skill; this section is the SQL.

### Schema

```
collections      collectionID, collectionName, parentCollectionID,
                 clientDateModified, libraryID, key, version, synced,
                 clientVersion
collectionItems  collectionID, itemID, orderIndex
```

- A **top-level** collection has `parentCollectionID IS NULL` — not `0`, not
  `''`.
- `libraryID` for the personal library is `1`; read it
  (`SELECT libraryID FROM items LIMIT 1`) instead of hard-coding.
- `collectionItems` is the only membership table. There is no uniqueness
  constraint, so a reprinted row silently duplicates membership — guard with
  `SELECT 1 FROM collectionItems WHERE collectionID=? AND itemID=?` first.

### Insert pattern

```python
con.execute("BEGIN IMMEDIATE")
now = time.strftime("%Y-%m-%d %H:%M:%S")
cur.execute(
    "INSERT INTO collections (collectionName, parentCollectionID, "
    "clientDateModified, libraryID, key, version, synced) "
    "VALUES (?, ?, ?, ?, ?, 0, 0)",
    (name, parent_id, now, library_id, new_key))
cid = cur.lastrowid
cur.execute("INSERT INTO collectionItems (collectionID, itemID, orderIndex) "
            "VALUES (?, ?, 0)", (cid, item_id))
con.commit()
```

Set `synced = 0` and `version = 0` so Zotero's sync layer re-reads the object
rather than trusting a version it never issued.

### Keys: format and generation

Zotero keys are 8 characters from `A-Z` and `2-9` (no `0`, no `1`):

```python
alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ23456789"
rng = random.SystemRandom()
while True:
    key = "".join(rng.choice(alphabet) for _ in range(8))
    if key not in taken:      # taken = keys already in collections + items
        break
```

Do **not** derive keys from a counter. A first pass emitted `3OGAAAAA`,
`4OGAAAAA`, … — unique, but patterned, and collision-prone against Zotero's
own generator.

### Deleting a collection without deleting items

```sql
DELETE FROM collectionItems WHERE collectionID = ?;
DELETE FROM collections      WHERE collectionID = ?;
```

Deleting the collection row does **not** touch `items`. Confirm afterwards
that `SELECT COUNT(*) FROM items` is unchanged — that is the single most
useful assertion for "I reorganised, I did not lose anything".

### Verification queries (run every time)

```sql
-- planned vs actual, per collection
SELECT c.collectionName, COUNT(ci.itemID)
FROM collections c LEFT JOIN collectionItems ci ON ci.collectionID = c.collectionID
GROUP BY c.collectionID ORDER BY c.collectionID;

-- orphans: membership pointing at a dead item
SELECT COUNT(*) FROM collectionItems ci
LEFT JOIN items i ON i.itemID = ci.itemID WHERE i.itemID IS NULL;

-- duplicate membership in one collection
SELECT COUNT(*) FROM (SELECT collectionID, itemID, COUNT(*) c
  FROM collectionItems GROUP BY 1,2 HAVING c > 1);

-- how many bibliographic items are filed at all
SELECT COUNT(DISTINCT itemID) FROM collectionItems;
```

### Reading the library for classification

The field lookup is tedious but stable:

```sql
SELECT i.key, it.typeName, i.dateAdded, idv.value AS title
FROM items i
JOIN itemTypes it ON it.itemTypeID = i.itemTypeID
JOIN itemData id ON id.itemID = i.itemID
JOIN itemDataValues idv ON idv.valueID = id.valueID
JOIN fields f ON f.fieldID = id.fieldID
WHERE f.fieldName = 'title'
  AND it.typeName NOT IN ('attachment','note','annotation');
```

To tell whether an item already has a note or a readable PDF:

```sql
SELECT COUNT(*) FROM itemNotes        WHERE parentItemID = ?;   -- notes
SELECT i.key, a.path FROM itemAttachments a JOIN items i ON i.itemID = a.itemID
WHERE a.parentItemID = ?;                                        -- then stat
```

Check the PDF by reading the first four bytes (`%PDF`) from the file under
`storage/<attachmentKey>/`; a non-empty attachment row is not proof the file
exists.

**Note count caveat:** `itemNotes.parentItemID` is the right column, but an
item can have a note whose parent was since deleted. Report notes and PDFs
separately so "needs a note" and "has no PDF" stay distinguishable.

## Action: Generate better-bibtex style citation keys

Generate Better BibTeX format citation key.

### Usage
```python
import re
import uuid

def generate_citation_key(title, authors, year):
    """
    Format: [first_author_last][year][first_meaningful_word]
    Example: smith2020attention
    """
    # Extract first author last name
    first_author_last = ""
    if authors:
        author = authors[0] if isinstance(authors, list) else authors
        if "," in author:
            first_author_last = author.split(",")[0].strip()
        else:
            parts = author.strip().split()
            first_author_last = parts[-1] if parts else ""

    first_author_last = re.sub(r'[^a-zA-Z]', '', first_author_last).lower()

    # Year
    year_str = str(year) if year else ""

    # First meaningful word from title
    stop_words = {'a', 'an', 'the', 'of', 'in', 'on', 'for', 'to', 'and', 'or', 'with', 'by'}
    title_word = ""
    if title:
        words = re.findall(r'[a-zA-Z]+', title.lower())
        for word in words:
            if word not in stop_words and len(word) > 1:
                title_word = word
                break

    key = f"{first_author_last}{year_str}{title_word}"
    return key if key else "unknown"

# Example
key = generate_citation_key(
    "Attention Is All You Need",
    ["Vaswani, Ashish"],
    2017
)
print(key)  # Output: vaswani2017attention
```

---

## Action: Create Fulltext Index

Create fulltext index for an existing item.

### Usage
```python
import PyPDF2
import sqlite3
import os
import hashlib

ZOTERO_DB = os.path.expanduser("E:/CodeProject/Zotero/zotero.sqlite")

def get_next_id(conn, table, column):
    cursor = conn.cursor()
    cursor.execute(f"SELECT MAX({column}) FROM {table}")
    result = cursor.fetchone()[0]
    return 1 if result is None else result + 1

def create_fulltext_index(conn, item_id, pdf_path):
    """Create fulltext index for item"""
    try:
        # Read PDF
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            num_pages = len(reader.pages)
            text_content = []
            for page in reader.pages:
                try:
                    text = page.extract_text()
                    if text:
                        text_content.append(text)
                except:
                    continue

        full_text = " ".join(text_content)
        total_chars = len(full_text)

        cursor = conn.cursor()

        # Insert fulltextItems record
        cursor.execute("""
            INSERT INTO fulltextItems (itemID, indexedPages, totalPages, indexedChars, totalChars, version, synced)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (item_id, num_pages, num_pages, total_chars, total_chars, 13, 0))

        # Insert word index
        words = full_text.lower().split()
        word_inserted = set()

        for word in words:
            if len(word) < 3:
                continue
            clean_word = ''.join(c for c in word if c.isalnum())
            if len(clean_word) < 3 or clean_word in word_inserted:
                continue
            word_inserted.add(clean_word)

            # Get or create wordID
            cursor.execute("SELECT wordID FROM fulltextWords WHERE word = ?", (clean_word,))
            result = cursor.fetchone()
            if result:
                word_id = result[0]
            else:
                word_id = get_next_id(conn, "fulltextWords", "wordID")
                cursor.execute("INSERT INTO fulltextWords (wordID, word) VALUES (?, ?)", (word_id, clean_word))

            cursor.execute("INSERT INTO fulltextItemWords (itemID, wordID) VALUES (?, ?)", (item_id, word_id))

        print(f"Created index: {num_pages} pages, {total_chars} chars, {len(word_inserted)} words")
        return True

    except Exception as e:
        print(f"Error: {e}")
        return False

# Usage
conn = sqlite3.connect(ZOTERO_DB)
create_fulltext_index(conn, item_id=123, pdf_path="C:/path/to/file.pdf")
conn.commit()
conn.close()
```

---

## Zotero Database Schema

### Key Tables

| Table | Purpose |
|-------|---------|
| `items` | Main item records |
| `itemData` | Item field values (links to itemDataValues) |
| `itemDataValues` | Actual text values |
| `itemTypes` | Item type definitions |
| `creators` | Author/creator info |
| `itemCreators` | Links items to creators |
| `itemAttachments` | Attachment metadata |
| `fulltextItems` | Fulltext index metadata |
| `fulltextWords` | Word dictionary |
| `fulltextItemWords` | Word-item mappings |

### Important Field IDs

| fieldID | Meaning |
|---------|---------|
| 1 | Title |
| 2 | Abstract |
| 6 | Date |
| 8 | DOI |
| 9 | Citation Key |
| 19 | Extra |
| 21 | Publication |
| 22 | Volume |
| 35 | Pages |

### Storage Folder Rule
**CRITICAL**: Storage folders use the **attachment item's key**, not the main item's key.

---

## Action: Analyze Database

Check database health and find issues.

```python
import sqlite3
import os

ZOTERO_DB = os.path.expanduser("E:/CodeProject/Zotero/zotero.sqlite")
ZOTERO_STORAGE = os.path.expanduser("E:/CodeProject/Zotero/storage")

conn = sqlite3.connect(ZOTERO_DB)
cursor = conn.cursor()

# Basic stats
cursor.execute("SELECT COUNT(*) FROM items WHERE itemTypeID != 3")
print(f"Main items: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM items WHERE itemTypeID = 3")
print(f"Attachment items: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM itemAttachments")
print(f"Attachments in itemAttachments table: {cursor.fetchone()[0]}")

# Find orphan main items
cursor.execute('''
    SELECT i.itemID, i.key
    FROM items i
    WHERE i.itemTypeID != 3
    AND NOT EXISTS (SELECT 1 FROM itemData WHERE itemID = i.itemID)
    AND NOT EXISTS (SELECT 1 FROM itemAttachments WHERE parentItemID = i.itemID)
''')
orphans = cursor.fetchall()
print(f"\nOrphan main items (no data, no attachments): {len(orphans)}")

# Find orphan attachments
cursor.execute('''
    SELECT ia.itemID, ia.parentItemID
    FROM itemAttachments ia
    WHERE ia.parentItemID NOT IN (SELECT itemID FROM items)
''')
orphan_atts = cursor.fetchall()
print(f"Orphan attachments: {len(orphan_atts)}")

# Storage folder check
storage_folders = set(os.listdir(ZOTERO_STORAGE))
db_keys = set()
cursor.execute("SELECT key FROM items")
for row in cursor.fetchall():
    db_keys.add(row[0])
orphan_folders = storage_folders - db_keys
print(f"\nUnused storage folders: {len(orphan_folders)}")
for f in list(orphan_folders)[:5]:
    print(f"  {f}")

conn.close()
```
