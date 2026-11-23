"""
CLI — 一键炼书入口
用法:
    python cli.py write <book.yaml> [work_dir]
    python cli.py build <book.yaml> [work_dir]
    python cli.py run   <book.yaml> [work_dir]    # write + build
"""
import sys
import os
import yaml
from pathlib import Path

from api import LLM
from writer import Writer
from builder import Builder

# Windows 控制台默认 GBK，遇到 emoji 会直接抛 UnicodeEncodeError 崩溃。
# 这里强制 stdout/stderr 用 UTF-8，非法字符替换掉而不是崩。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def load_book_config(yaml_path: str) -> dict:
    p = Path(yaml_path)
    if not p.exists():
        print(f"❌ 配置文件不存在: {yaml_path}")
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def cmd_write(cfg: dict, work_dir: Path):
    print(f"📖 开始写作: {cfg['meta']['title']}")
    print(f"   共 {len(cfg['chapters'])} 章\n")
    llm = LLM()
    writer = Writer(llm)
    writer.write_book(cfg, work_dir)


def cmd_build(cfg: dict, work_dir: Path):
    print(f"📦 编译: {cfg['meta']['title']}")
    builder = Builder()
    md_filename = cfg["meta"].get("output_file", "output.md")
    result = builder.build(cfg, work_dir, md_filename)
    print(f"\n✅ 完成: {result['pdf']} ({result['pdf_mb']:.1f}MB, ~{result['words']//1000}k字)")


def cmd_run(cfg: dict, work_dir: Path):
    cmd_write(cfg, work_dir)
    cmd_build(cfg, work_dir)


def main():
    if len(sys.argv) < 2:
        print("用法: python cli.py <write|build|run> <book.yaml> [work_dir]")
        print("  write   只生成章节 Markdown")
        print("  build   只编译已有章节为 PDF")
        print("  run     write + build 一键出书")
        print()
        print("work_dir 省略时依次取：$MD2BOOK_WORKDIR 环境变量 → 当前目录")
        sys.exit(1)

    action = sys.argv[1]
    if len(sys.argv) < 3:
        print("❌ 必须指定 book.yaml 路径")
        sys.exit(1)
    yaml_path = sys.argv[2]

    cfg = load_book_config(yaml_path)

    # 工作目录优先级：命令行参数 > 环境变量 > 当前目录
    # （不再硬编码 E:/CodeProject，换机器不会写错地方）
    if len(sys.argv) > 3:
        work_dir = Path(sys.argv[3])
    elif os.environ.get("MD2BOOK_WORKDIR"):
        work_dir = Path(os.environ["MD2BOOK_WORKDIR"])
    else:
        work_dir = Path.cwd()
    work_dir.mkdir(parents=True, exist_ok=True)
    print(f"📂 工作目录: {work_dir}")

    if action == "write":
        cmd_write(cfg, work_dir)
    elif action == "build":
        cmd_build(cfg, work_dir)
    elif action == "run":
        cmd_run(cfg, work_dir)
    else:
        print(f"❌ 未知命令: {action}")
        sys.exit(1)


if __name__ == "__main__":
    main()
