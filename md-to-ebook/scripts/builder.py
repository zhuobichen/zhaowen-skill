"""
Builder — 合并章节 + 去重标题 + 编译 PDF
"""
import sys
import re
import os
import glob
import shutil
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Preformatted
from reportlab.pdfbase import pdfmetrics, ttfonts

# Windows 控制台 GBK 遇到 emoji 会崩，统一转 UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


CN_NUMS = "一二三四五六七八九十"


CN_NUMS = "一二三四五六七八九十"


class Builder:
    """章节合并 + 标题去重 + PDF 编译"""

    def __init__(self, output_root: Path = None):
        # None = 跟随 work_dir（在 build() 里定），避免把产物复制到意料之外的目录
        self.output_root = Path(output_root) if output_root else None
        self._init_fonts()

    @staticmethod
    def _is_chapter_title(line: str) -> bool:
        """只有含'第X章'的行才算真正的章标题"""
        return bool(re.search(r"第[" + CN_NUMS + r"0-9]+章", line))

    def _init_fonts(self):
        """注册中英文等宽字体。优先 simhei.ttf（单文件，CJK兼容性最好）"""
        font = None
        for f in (
            [p for p in glob.glob("C:/Windows/Fonts/simhei.ttf")]
            + glob.glob("C:/Windows/Fonts/simfang.ttf")
            + glob.glob("C:/Windows/Fonts/simkai.ttf")
            + glob.glob("C:/Windows/Fonts/msyh*.ttc")
        ):
            font = f
            break
        if not font:
            raise RuntimeError("找不到中文字体")
        pdfmetrics.registerFont(ttfonts.TTFont("CN", font))
        if os.path.exists("C:/Windows/Fonts/consola.ttf"):
            pdfmetrics.registerFont(ttfonts.TTFont("Mono", "C:/Windows/Fonts/consola.ttf"))
        else:
            pdfmetrics.registerFont(ttfonts.TTFont("Mono", font))

        # 样式 — 使用 CJK 文字间距，避免中文断行异常
        self._body_style = ParagraphStyle(
            "B", fontName="CN", fontSize=10.5, leading=19, spaceAfter=8,
            firstLineIndent=20, wordSpace="CJK",
        )
        self._h1_style = ParagraphStyle(
            "H1", fontName="CN", fontSize=18, leading=26, spaceBefore=24, spaceAfter=12
        )
        self._h2_style = ParagraphStyle(
            "H2", fontName="CN", fontSize=13, leading=20, spaceBefore=16, spaceAfter=8
        )
        self._h3_style = ParagraphStyle(
            "H3", fontName="CN", fontSize=11, leading=17, spaceBefore=12, spaceAfter=6
        )
        self._code_style = ParagraphStyle(
            "CD",
            fontName="Mono",
            fontSize=7.5,
            leading=11,
            leftIndent=14,
            spaceAfter=6,
            backColor="#f5f5f5",
        )

    def merge_and_dedup(
        self, chapter_files: list, titles: dict, output_path: Path
    ) -> str:
        """
        合并章节文件并去重标题。

        chapter_files: [Path, ...]  按顺序的章节文件
        titles:        {0: "第1章 xxx", 1: "第2章 xxx", ...}
        output_path:   合并后的 .md 输出路径
        """
        parts = []
        for i, ch_path in enumerate(chapter_files):
            with open(ch_path, "r", encoding="utf-8") as f:
                raw = f.read()

            # 清除 AI 额外加的各种标题
            lines = raw.split("\n")
            while lines and (
                lines[0].strip().startswith("#") or not lines[0].strip()
            ):
                lines.pop(0)
            while lines and re.match(r"^#{1,2}\s", lines[0].strip()):
                lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)

            body = "\n".join(lines).strip()
            # 删除正文中散落的 `## 第X章：xxx` 中文标题
            body = re.sub(
                rf"\n##\s*第[{CN_NUMS}]+章[：:][^\n]*\n?", "\n", body
            )
            # 删除 `## 第一章：xxx` 等
            body = re.sub(
                rf"^##\s*第[{CN_NUMS}]+章[：:][^\n]*\n?", "", body,
                flags=re.MULTILINE,
            )
            title = titles.get(i, f"# 第{i+1}章")
            parts.append(f"{title}\n\n{body}")

        book = parts[0] if parts else ""
        for p in parts[1:]:
            book += "\n\n" + p

        # 加 YAML frontmatter
        book = (
            "---\ntitle: 未命名\nauthor: 陈卓\nlang: zh-CN\n---\n\n" + book
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(book)

        print(f"✅ 合并: {os.path.basename(str(output_path))}")
        return book

    def markdown_to_pdf(self, md_path: Path, pdf_path: Path) -> float:
        """将 Markdown 编译为 PDF，返回文件大小(MB)"""
        with open(md_path, "r", encoding="utf-8") as f:
            text = f.read()

        lines = text.split("\n")
        story = []
        in_code = False
        code_buf = []
        in_yaml = False

        for raw in lines:
            if raw.strip() == "---":
                in_yaml = not in_yaml
                continue
            if in_yaml:
                continue
            if raw.startswith("```"):
                if in_code and code_buf:
                    story.append(Preformatted("\n".join(code_buf), self._code_style))
                    code_buf = []
                in_code = not in_code
                continue
            if in_code:
                code_buf.append(raw)
                continue

            l = raw
            l = re.sub(r"\*\*(.+?)\*\*", r"\1", l)
            l = re.sub(r"\*(.+?)\*", r"\1", l)
            l = re.sub(r"`([^`]+)`", r"\1", l)
            l = re.sub(r"<[^>]+>", "", l)
            l = l.replace("$$", "").replace("$", "")

            if not l.strip():
                continue

            if raw.startswith("# ") and not raw.startswith("## "):
                # 只有含「第X章」的才算 H1，其余降为 H2
                if self._is_chapter_title(l):
                    story.append(Paragraph(l[2:], self._h1_style))
                else:
                    story.append(Paragraph(l[2:], self._h2_style))
            elif raw.startswith("## ") and not raw.startswith("### "):
                story.append(Paragraph(l[3:], self._h2_style))
            elif raw.startswith("### "):
                story.append(Paragraph(l[3:], self._h3_style))
            else:
                story.append(Paragraph(l, self._body_style))

        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            leftMargin=22 * mm,
            rightMargin=22 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
        )
        doc.build(story)
        return os.path.getsize(pdf_path) / 1024 / 1024

    def build(
        self,
        book_cfg: dict,
        work_dir: Path,
        md_filename: str,
        push_to_root: bool = True,
    ) -> dict:
        """
        一键构建：合并 → 去重 → PDF → 推到根目录

        返回 {"md": Path, "pdf": Path, "pdf_mb": float, "words": int}
        """
        chapters = book_cfg.get("chapters", [])
        meta = book_cfg.get("meta", {})

        # output_root 默认跟随 work_dir，不再往"当前目录"或硬编码路径复制
        if self.output_root is None:
            self.output_root = Path(work_dir)

        # 收集章节文件
        chapter_files = [work_dir / ch["file"] for ch in chapters]
        titles = {i: ch["title"] for i, ch in enumerate(chapters)}

        # 合并
        md_path = work_dir / md_filename
        book_text = self.merge_and_dedup(chapter_files, titles, md_path)

        # PDF
        pdf_basename = md_filename.replace(".md", ".pdf")
        pdf_path = work_dir / pdf_basename
        mb = self.markdown_to_pdf(md_path, pdf_path)
        print(f"✅ PDF: {pdf_basename} ({mb:.1f}MB)")

        # 推到根目录
        if push_to_root:
            if str(md_path.resolve()) != str((self.output_root / md_filename).resolve()):
                shutil.copy2(md_path, self.output_root / md_filename)
            if str(pdf_path.resolve()) != str((self.output_root / pdf_basename).resolve()):
                shutil.copy2(pdf_path, self.output_root / pdf_basename)
            print(f"📂 → {self.output_root}")

        # 清理中间章节文件
        for cf in chapter_files:
            if cf.exists():
                cf.unlink()

        words = len(book_text.replace(" ", "").replace("\n", ""))
        return {"md": md_path, "pdf": pdf_path, "pdf_mb": mb, "words": words}
