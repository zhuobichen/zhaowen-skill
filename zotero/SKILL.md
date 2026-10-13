---
name: zotero
description: Use Zotero for bibliography management, PDF reading, reference generation, and thesis writing. Use when working with academic references, citations, PDFs from Zotero, or generating LaTeX documents with references.
argument-hint: "[action] [params...]"
---

# Zotero Skill

Manage Zotero library for bibliography management, PDF content reading, reference generation, and SCUT thesis writing with LaTeX.

## CRITICAL: Read-Only Restriction

**Zotero 文献库只读限制：严禁任何写入、修改、删除操作。**

| 允许 | 禁止 |
|------|------|
| `item list/find/get` 查询文献 | `note add` 添加笔记 |
| `item notes / note get` 读取笔记 | `import file/json` 导入文献 |
| `item children/attachments/file` 查看附件 | `collection create` 创建集合 |
| `item export/citation/bibliography` 导出引用 | `item add-to-collection / move-to-collection` 移动文献 |
| `item context` 构建LLM上下文 | 任何写入 `zotero.sqlite` 的操作 |
| `collection list/find/tree/items` 查看集合 | `item analyze` (调用外部API) |
| `app status/ping` 状态检查 | `pdf_to_zotero.py` 导入PDF |

**Why:** 用户明确要求 Zotero 文献库内容不可修改，防止误操作破坏数据。

**How to apply:** 涉及 Zotero 操作时只使用只读命令，遇到任何写入/修改类操作必须拒绝执行。

## Prerequisites

1. **Zotero running** with Local API enabled:
   - Edit → Preferences → Advanced → General → "启动浏览器连接" (Allow browser integration)
   - Port: 23119

2. **Zotero CLI installed**:
   ```bash
   pip install cli-anything-zotero
   ```

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

- Base path: `C:\Users\chenlizhuo\Zotero\storage\`
- Each item has a folder named by its Zotero key
- PDFs are stored inside these folders
- Attachment keys differ from parent item keys

## File Paths Reference

| File | Path |
|------|------|
| BibTeX | `C:\Users\chenlizhuo\SCUT_thesis\biblibrary\Zotero_References.bib` |
| compile_refs.py | `C:\Users\chenlizhuo\SCUT_thesis\compile_refs.py` |
| Test thesis | `C:\Users\chenlizhuo\SCUT_thesis\test_background.tex` |
| Zotero storage | `C:\Users\chenlizhuo\Zotero\storage\` |
| XeLaTeX | `C:/Users/chenlizhuo/AppData/Local/Programs/MiKTeX/miktex/bin/x64/xelatex.exe` |
| Biber | `C:/Users/chenlizhuo/AppData/Local/Programs/MiKTeX/miktex/bin/x64/biber.exe` |
