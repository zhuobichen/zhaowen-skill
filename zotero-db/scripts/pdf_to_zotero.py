"""
PDF 转 Bib 并导入 Zotero 本地数据库（完全版）

与手动拖入 Zotero 完全一致的导入方式
"""
import sqlite3
import os
import sys
import hashlib
import shutil
import uuid
import re
from datetime import datetime

# Zotero 数据库路径
ZOTERO_DB = os.path.expanduser("~/Zotero/zotero.sqlite")
ZOTERO_STORAGE = os.path.expanduser("~/Zotero/storage")


def get_next_id(conn, table, column):
    """获取下一个 ID"""
    cursor = conn.cursor()
    cursor.execute(f"SELECT MAX({column}) FROM {table}")
    result = cursor.fetchone()[0]
    return 1 if result is None else result + 1


def create_value(conn, value):
    """创建或获取已存在的 valueID"""
    cursor = conn.cursor()
    cursor.execute("SELECT valueID FROM itemDataValues WHERE value = ?", (value,))
    result = cursor.fetchone()
    if result:
        return result[0]
    value_id = get_next_id(conn, "itemDataValues", "valueID")
    cursor.execute("INSERT INTO itemDataValues (valueID, value) VALUES (?, ?)", (value_id, value))
    return value_id


def add_item_data(conn, item_id, field_id, value):
    """添加 itemData"""
    cursor = conn.cursor()
    value_id = create_value(conn, value)
    cursor.execute(
        "INSERT INTO itemData (itemID, fieldID, valueID) VALUES (?, ?, ?)",
        (item_id, field_id, value_id)
    )


def add_creator(conn, item_id, first_name, last_name, creator_type_id=10):
    """添加作者/creator"""
    cursor = conn.cursor()

    # 先查找是否已存在该 creator
    cursor.execute(
        "SELECT creatorID FROM creators WHERE firstName = ? AND lastName = ? AND fieldMode = 1",
        (first_name, last_name)
    )
    result = cursor.fetchone()

    if result:
        creator_id = result[0]
    else:
        creator_id = get_next_id(conn, "creators", "creatorID")
        cursor.execute(
            "INSERT INTO creators (creatorID, firstName, lastName, fieldMode) VALUES (?, ?, ?, ?)",
            (creator_id, first_name, last_name, 1)
        )

    # 关联到 item
    cursor.execute("SELECT MAX(orderIndex) FROM itemCreators WHERE itemID = ?", (item_id,))
    order_index = cursor.fetchone()[0]
    order_index = 0 if order_index is None else order_index + 1

    cursor.execute(
        "INSERT INTO itemCreators (itemID, creatorID, creatorTypeID, orderIndex) VALUES (?, ?, ?, ?)",
        (item_id, creator_id, creator_type_id, order_index)
    )


def compute_file_hash(filepath):
    """计算文件 MD5 哈希"""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def generate_key():
    """生成 Zotero key (8个字符)"""
    return uuid.uuid4().hex[:8].upper()


def generate_citation_key(title, authors, year):
    """
    生成与 Better BibTeX 兼容的 Citation Key

    格式: [第一作者姓氏][年份][标题第一个词]
    例如: smith2020attention
    """
    # 提取第一作者姓氏
    first_author_last = ""
    if authors:
        if isinstance(authors, list):
            author = authors[0]
        else:
            author = authors

        # 解析 "Last, First" 或 "First Last" 格式
        if "," in author:
            first_author_last = author.split(",")[0].strip()
        else:
            parts = author.strip().split()
            first_author_last = parts[-1] if parts else ""

    # 清理姓氏
    first_author_last = re.sub(r'[^a-zA-Z]', '', first_author_last)
    first_author_last = first_author_last.lower()

    # 提取年份
    year_str = str(year) if year else ""

    # 提取标题第一个有意义的词（去掉冠词）
    stop_words = {'a', 'an', 'the', 'of', 'in', 'on', 'for', 'to', 'and', 'or', 'with', 'by'}
    title_word = ""
    if title:
        # 提取第一个字母开头的单词
        words = re.findall(r'[a-zA-Z]+', title.lower())
        for word in words:
            if word not in stop_words and len(word) > 1:
                title_word = word
                break

    # 组合
    key = f"{first_author_last}{year_str}{title_word}"
    return key if key else "unknown"


def create_fulltext_index(conn, item_id, pdf_path):
    """创建全文索引"""
    try:
        import PyPDF2
        cursor = conn.cursor()

        # 读取 PDF 并提取文本
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

        # 创建 fulltextItems 记录
        cursor.execute("""
            INSERT INTO fulltextItems (itemID, indexedPages, totalPages, indexedChars, totalChars, version, synced)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (item_id, num_pages, num_pages, total_chars, total_chars, 13, 0))

        # 创建全文单词表
        words = full_text.lower().split()
        word_inserted = set()

        for i, word in enumerate(words):
            if len(word) < 3:
                continue

            clean_word = ''.join(c for c in word if c.isalnum())
            if len(clean_word) < 3:
                continue

            if clean_word in word_inserted:
                continue
            word_inserted.add(clean_word)

            cursor.execute("SELECT wordID FROM fulltextWords WHERE word = ?", (clean_word,))
            result = cursor.fetchone()
            if result:
                word_id = result[0]
            else:
                word_id = get_next_id(conn, "fulltextWords", "wordID")
                cursor.execute("INSERT INTO fulltextWords (wordID, word) VALUES (?, ?)", (word_id, clean_word))

            cursor.execute("""
                INSERT INTO fulltextItemWords (itemID, wordID)
                VALUES (?, ?)
            """, (item_id, word_id))

        print(f"  创建全文索引: {num_pages} 页, {total_chars} 字符, {len(word_inserted)} 词")
        return True

    except ImportError:
        print("  警告: PyPDF2 未安装，跳过全文索引")
        return False
    except Exception as e:
        print(f"  警告: 全文索引创建失败: {e}")
        return False


def import_pdf_to_zotero(pdf_path, item_type="journalArticle", title=None, authors=None,
                        year=None, doi=None, journal=None, volume=None, pages=None,
                        abstract=None, create_index=False, citation_key=None):
    """
    将 PDF 导入 Zotero 本地数据库（完全版）

    参数：
        pdf_path: PDF 文件路径
        item_type: 文献类型
        title: 标题
        authors: 作者列表
        year: 年份
        doi: DOI
        journal: 期刊名
        volume: 卷
        pages: 页码
        abstract: 摘要
        create_index: 是否创建全文索引
        citation_key: Citation Key (如果不提供则自动生成)
    """

    if not os.path.exists(pdf_path):
        print(f"错误：文件不存在 {pdf_path}")
        return None

    if not os.path.exists(ZOTERO_DB):
        print(f"错误：Zotero 数据库不存在 {ZOTERO_DB}")
        return None

    # 从文件名提取标题
    if title is None:
        title = os.path.splitext(os.path.basename(pdf_path))[0]
        for suffix in [".pdf", "_PDF", "-PDF"]:
            title = title.replace(suffix, "")

    # 自动生成 citation key
    if citation_key is None:
        citation_key = generate_citation_key(title, authors, year)

    print(f"导入文献：{title}")
    print(f"  Citation Key: {citation_key}")

    conn = sqlite3.connect(ZOTERO_DB)
    cursor = conn.cursor()

    try:
        # 1. 创建主 items 条目
        item_id = get_next_id(conn, "items", "itemID")
        key = generate_key()
        item_type_id = cursor.execute(
            "SELECT itemTypeID FROM itemTypes WHERE typeName = ?", (item_type,)
        ).fetchone()[0]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            INSERT INTO items (itemID, itemTypeID, dateAdded, dateModified, clientDateModified, libraryID, key, version, synced)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (item_id, item_type_id, now, now, now, 1, key, 1, 1))
        print(f"  创建 item: itemID={item_id}, key={key}")

        # 2. 添加 itemData
        add_item_data(conn, item_id, 1, title)  # 标题
        if year:
            add_item_data(conn, item_id, 6, str(year))  # 日期
        if doi:
            add_item_data(conn, item_id, 8, doi)  # DOI
        if journal:
            add_item_data(conn, item_id, 21, journal)  # 期刊
        if volume:
            add_item_data(conn, item_id, 22, str(volume))  # 卷
        if pages:
            add_item_data(conn, item_id, 35, str(pages))  # 页码
        if abstract:
            add_item_data(conn, item_id, 2, abstract)  # 摘要

        # 3. 添加 Citation Key 到 Extra 字段 (fieldID=19)
        extra_value = f"Citation Key: {citation_key}"
        add_item_data(conn, item_id, 9, citation_key)  # fieldID=9 是 citationKey
        add_item_data(conn, item_id, 19, extra_value)  # fieldID=19 是 Extra

        # 4. 添加作者
        if authors:
            if isinstance(authors, str):
                authors = [authors]
            for author in authors:
                if "," in author:
                    last_name, first_name = [x.strip() for x in author.split(",", 1)]
                else:
                    parts = author.strip().split()
                    if len(parts) >= 2:
                        first_name = " ".join(parts[:-1])
                        last_name = parts[-1]
                    else:
                        first_name = ""
                        last_name = author
                add_creator(conn, item_id, first_name, last_name, 10)
        print(f"  添加 {len(authors) if authors else 0} 位作者")

        # 5. 先创建附件 item，获取附件的 key
        attachment_item_id = get_next_id(conn, "items", "itemID")
        attachment_key = generate_key()
        cursor.execute("""
            INSERT INTO items (itemID, itemTypeID, dateAdded, dateModified, clientDateModified, libraryID, key, version, synced)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (attachment_item_id, 3, now, now, now, 1, attachment_key, 1, 1))

        # 6. 用附件的 key 创建 storage 文件夹
        storage_folder = os.path.join(ZOTERO_STORAGE, attachment_key)
        os.makedirs(storage_folder, exist_ok=True)
        pdf_filename = os.path.basename(pdf_path)
        dest_pdf_path = os.path.join(storage_folder, pdf_filename)
        shutil.copy2(pdf_path, dest_pdf_path)
        print(f"  复制 PDF 到: {dest_pdf_path}")

        # 7. 计算文件信息
        file_hash = compute_file_hash(dest_pdf_path)
        file_size = os.path.getsize(dest_pdf_path)
        mod_time = int(os.path.getmtime(dest_pdf_path) * 1000)

        # 8. 创建 itemAttachments 条目
        cursor.execute("""
            INSERT INTO itemAttachments (itemID, parentItemID, linkMode, contentType, charsetID, path, syncState, storageModTime, storageHash, lastProcessedModificationTime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (attachment_item_id, item_id, 1, "application/pdf", None, f"storage:{pdf_filename}", 2, mod_time, file_hash, 0))
        print(f"  创建附件: attachmentItemID={attachment_item_id}, attachmentKey={attachment_key}")

        conn.commit()

        # 8. 创建全文索引
        if create_index:
            print("  创建全文索引...")
            create_fulltext_index(conn, item_id, dest_pdf_path)

        conn.commit()
        print(f"\n成功导入！")
        print(f"  itemID: {item_id}")
        print(f"  key: {key}")
        print(f"  Citation Key: {citation_key}")
        print(f"  PDF: {dest_pdf_path}")

        return {"item_id": item_id, "key": key, "citation_key": citation_key, "attachment_id": attachment_item_id}

    except Exception as e:
        conn.rollback()
        print(f"错误：{e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        conn.close()


def main():
    if len(sys.argv) < 2:
        print("""用法: python pdf_to_zotero.py <pdf_path> [选项]

选项:
  --type TYPE        文献类型 (默认: journalArticle)
  --title TITLE      标题
  --authors AUTHORS  作者 (多个用 | 分隔，如 "Last1, First1 | Last2, First2")
  --year YEAR        年份
  --doi DOI          DOI
  --journal JOURNAL  期刊名
  --volume VOLUME    卷
  --pages PAGES      页码
  --index           创建全文索引 (需要 PyPDF2)
  --key KEY         自定义 Citation Key

示例:
  python pdf_to_zotero.py "paper.pdf"
  python pdf_to_zotero.py "paper.pdf" --title "我的论文" --authors "李, 明 | 王, 红" --year 2024 --index
""")
        return

    pdf_path = sys.argv[1]

    # 解析参数
    kwargs = {"create_index": False, "pdf_path": pdf_path}
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--type":
            kwargs["item_type"] = sys.argv[i + 1]
        elif sys.argv[i] == "--title":
            kwargs["title"] = sys.argv[i + 1]
        elif sys.argv[i] == "--authors":
            kwargs["authors"] = sys.argv[i + 1].split("|")
        elif sys.argv[i] == "--year":
            kwargs["year"] = sys.argv[i + 1]
        elif sys.argv[i] == "--doi":
            kwargs["doi"] = sys.argv[i + 1]
        elif sys.argv[i] == "--journal":
            kwargs["journal"] = sys.argv[i + 1]
        elif sys.argv[i] == "--volume":
            kwargs["volume"] = sys.argv[i + 1]
        elif sys.argv[i] == "--pages":
            kwargs["pages"] = sys.argv[i + 1]
        elif sys.argv[i] == "--index":
            kwargs["create_index"] = True
        elif sys.argv[i] == "--key":
            kwargs["citation_key"] = sys.argv[i + 1]
        i += 2

    import_pdf_to_zotero(**kwargs)


if __name__ == "__main__":
    main()
