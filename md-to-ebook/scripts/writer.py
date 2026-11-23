"""
Writer — 根据书籍配置逐章生成 Markdown
"""
import sys
import re
from pathlib import Path
from api import LLM

# Windows 控制台 GBK 遇到 emoji 会崩，统一转 UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class Writer:
    """AI 逐章写作引擎"""

    def __init__(self, llm: LLM = None):
        self.llm = llm or LLM()
        # 默认系统提示词 = 教科书式分段叙事体
        self.default_system = (
            "你是一位技术图书作者。你在写一本面向零基础读者的教科书。\n\n"
            "排版铁律：\n"
            "1. 像教科书一样分段叙事，每段3-6句话。不用列表符号当主体内容。\n"
            "2. 章节开头用2-3段引入文字。\n"
            "3. 术语解释融入段落，不要'术语：解释'这种字典格式。\n"
            "4. 用'你'和'我'对话体讲课。\n"
            "5. 代码放```块内，代码前后必须有段落解释。\n"
            "6. 章节结尾有2-3段小结。\n"
            "7. 不要emoji，不要引用块(>)，不要用###三级标题碎。\n"
            "8. 仅用##做小节标题。内容靠段落组织。\n"
        )

    def write_chapter(
        self, prompt: str, system: str = None, temperature: float = 0.55
    ) -> str:
        """写一章，返回 Markdown 正文（不含章节标题）"""
        return self.llm.call(
            system=system or self.default_system,
            prompt=prompt,
            temperature=temperature,
        )

    def write_book(self, book_cfg: dict, output_dir: Path) -> Path:
        """
        根据书籍配置写全书。

        book_cfg 格式:
        {
            "meta": {"title": "...", "author": "...", "language": "zh-CN"},
            "source": "素材文本...",
            "system_prompt": "自定义系统提示词（可选）",
            "chapters": [
                {"file": "ch01.md", "title": "第1章 xxx",
                 "prompt": "写第一章...", "target_words": 4000},
                ...
            ]
        }
        """
        meta = book_cfg.get("meta", {})
        source = book_cfg.get("source", "")
        chapters = book_cfg.get("chapters", [])
        system = book_cfg.get("system_prompt", self.default_system)

        output_dir.mkdir(parents=True, exist_ok=True)
        total_words = 0

        for i, ch in enumerate(chapters):
            title = ch["title"]
            target = ch.get("target_words", 4000)
            prompt = ch["prompt"]

            # 注入素材
            if source and "{SRC}" in prompt:
                prompt = prompt.replace("{SRC}", source)

            print(f"  [{i+1}/{len(chapters)}] {title[:30]}...", end=" ", flush=True)
            try:
                content = self.write_chapter(prompt=prompt, system=system)
                # 写入文件（不含 H1，由 Builder 统一加）
                file_path = output_dir / ch["file"]
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                wc = len(content.replace(" ", "").replace("\n", ""))
                total_words += wc
                print(f"✅ {wc}字")
            except Exception as e:
                print(f"❌ {e}")

        print(f"\n📖 全书完成: ~{total_words//1000}k字 | {output_dir}")
        return output_dir
