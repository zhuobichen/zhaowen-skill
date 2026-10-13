---
name: zotero-db
description: Directly operate Zotero local SQLite database for PDF import, citation key generation, fulltext indexing, and database cleanup. Use for batch import, orphan cleanup, or when Zotero API is unavailable.
argument-hint: "[action] [params...]"
---

# Zotero Database Skill

Directly manipulate Zotero's local SQLite database for advanced operations including PDF import, citation key generation, fulltext indexing, and database cleanup.

## CRITICAL: Read-Only Restriction

**Zotero 文献库只读限制：严禁任何写入、修改、删除操作。**

此 Skill 中的以下操作已被禁止：
- Action: Import PDF to Zotero — **禁止**（写入数据库）
- Action: Cleanup Database — **禁止**（删除数据）
- Action: Create Fulltext Index — **禁止**（写入数据库）
- Action: Generate Citation Key — **禁止**（写入数据库）

唯一允许的操作：
- Action: Analyze Database（只读查询，检查数据库健康状态）

**Why:** 用户明确要求 Zotero 文献库内容不可修改。

**How to apply:** 只使用 `mode=ro&immutable=1` 模式连接数据库进行查询，严禁任何 INSERT/UPDATE/DELETE 操作。

## Prerequisites

1. **Python libraries**:
   ```bash
   pip install PyPDF2
   ```

2. **Zotero closed** when doing database cleanup (to avoid corruption)

## Database Paths

- Database: `E:\CodeProject\Zotero\zotero.sqlite`
- Storage: `E:\CodeProject\Zotero\storage\`

---

## Action: Import PDF to Zotero

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

## Action: Generate Citation Key

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
