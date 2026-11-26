# -*- coding: utf-8 -*-
"""session_hunt.py —— 按执行痕迹关键词，跨客户端统计会话命中数并排序（只读）。

用法:
  python session_hunt.py rank "whisper .m4a transcribe" --client all
  python session_hunt.py dump <id子串> --pattern "whisper" --client all
  python session_hunt.py paths

只做扫描和排序；找到目标后用 dsh-session-viewer / agent-dialog_management 完整查看。
"""
import os, sys, json, glob, re, argparse, datetime, io

try:
    import zstandard
except ImportError:
    zstandard = None

SKIP = {"node_modules", ".git", "EBWebView", "Cache_Data", "Code Cache", "__pycache__", ".tmp"}
USERNAME = os.environ.get("USERNAME", "Administrator")
HOME = os.path.expanduser("~")

def sources(client):
    roots = []
    if client in ("dsh", "all"):
        # 探测 DSH_HOME
        homes = []
        for c in [os.environ.get("DSH_HOME"),
                  os.path.join(HOME, ".dsh"),
                  r"D:\github_project\ZhaoWen_GitHub维护\dsh\home"]:
            if c and os.path.isdir(os.path.join(c, "sessions")) and c not in homes:
                homes.append(c)
        for h in homes:
            roots.append(("dsh", h, os.path.join(h, "sessions"), "session*.zstd"))
        # 备份/导入
        for p in glob.glob(r"D:\github_project\*\_dsh-backup-*\sessions"):
            roots.append(("dsh-backup", p, p, "session*.zstd"))
        imp = os.path.join(HOME, "Documents\\deepseek-harness\\default-workspace\\dsh-import\\_out")
        if os.path.isdir(imp):
            roots.append(("dsh-import", imp, imp, "session*.zstd"))
    if client in ("codex", "all"):
        for d in ["sessions", "archived_sessions"]:
            p = os.path.join(HOME, ".codex", d)
            if os.path.isdir(p):
                roots.append(("codex-"+d, p, p, "*.jsonl"))
    if client in ("claude", "all"):
        p = os.path.join(HOME, ".claude", "projects")
        if os.path.isdir(p):
            roots.append(("claude", p, p, "*.jsonl"))
    return roots

def read_text(path):
    if path.endswith(".zstd"):
        if zstandard is None:
            return ""
        try:
            with open(path, "rb") as f:
                return zstandard.ZstdDecompressor().stream_reader(f).read().decode("utf-8", "replace")
        except Exception:
            return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""

def events(text, kind):
    """产出 (type, text) 供搜索。"""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if kind.startswith("dsh"):
            t = o.get("type", "")
            d = o.get("data", {})
            if t == "user/message":
                if (d.get("source") or {}).get("kind") != "user":
                    continue
                s = "".join(x.get("text", "") for x in d.get("content", [])
                            if isinstance(x, dict) and x.get("type") == "text")
                yield ("user", s)
            elif t == "tool/call":
                yield ("tool", json.dumps(d.get("arguments", ""), ensure_ascii=False))
            elif t == "assistant/message":
                m = d.get("message") or {}
                for x in m.get("content", []):
                    if isinstance(x, dict) and x.get("type") == "text":
                        yield ("assistant", x.get("text", ""))
        else:
            # Codex / Claude: 递归取文本字段
            out = []
            for k in ("message", "payload", "text", "content", "input"):
                v = o.get(k)
                if isinstance(v, str):
                    out.append(v)
                elif isinstance(v, dict):
                    c = v.get("content") or v.get("text") or ""
                    if isinstance(c, str):
                        out.append(c)
                    elif isinstance(c, list):
                        for x in c:
                            if isinstance(x, dict) and isinstance(x.get("text"), str):
                                out.append(x["text"])
            if out:
                yield (o.get("type", "?"), " ".join(out))

def meta(text, kind, path):
    title, created = "", None
    if kind.startswith("dsh"):
        for line in text.splitlines():
            try:
                o = json.loads(line.strip())
            except Exception:
                continue
            if o.get("type") == "session":
                created = o.get("createdAt")
            if o.get("type") == "session/title":
                title = (o.get("data") or {}).get("title") or title
    else:
        m = re.search(r"20\d{2}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}", os.path.basename(path))
        if m:
            created = m.group(0)
    if isinstance(created, (int, float)):
        date = datetime.datetime.fromtimestamp(created/1000).strftime("%Y-%m-%d")
    elif isinstance(created, str):
        date = created[:10]
    else:
        date = "?"
    return title, date

def cmd_paths(args):
    for kind, label, root, pat in sources(args.client):
        n = len(glob.glob(os.path.join(root, "**", pat), recursive=True))
        print(f"{label:12} {n:5}  {root}")

def cmd_rank(args):
    pats = [p for p in re.split(r"\s+", args.pattern) if p]
    rows = []
    for kind, label, root, pat in sources(args.client):
        for p in glob.glob(os.path.join(root, "**", pat), recursive=True):
            text = read_text(p)
            if not text:
                continue
            counts = {}
            for ev_type, s in events(text, kind):
                low = s.lower()
                for pat_word in pats:
                    if pat_word.lower() in low:
                        counts[pat_word] = counts.get(pat_word, 0) + low.count(pat_word.lower())
            total = sum(counts.values())
            if total < (args.min_hits or 2):
                continue
            title, date = meta(text, kind, p)
            rows.append((total, counts, date, title, label, p))
    rows.sort(key=lambda x: -x[0])
    for total, counts, date, title, label, p in rows[:args.limit]:
        print(f"{total:5} | {date} | {label:12} | {(title or '')[:26]:26} | {p}")
        print(f"        {counts}")
    print(f"共 {len(rows)} 个会话命中（显示前 {args.limit}）")

def cmd_dump(args):
    pats = [p for p in re.split(r"\s+", args.pattern) if p] if args.pattern else []
    found = False
    for kind, label, root, pat in sources(args.client):
        for p in glob.glob(os.path.join(root, "**", pat), recursive=True):
            if args.id.lower() not in p.lower():
                continue
            found = True
            text = read_text(p)
            print(f"\n===== {p} =====")
            for ev_type, s in events(text, kind):
                if pats and not any(x.lower() in s.lower() for x in pats):
                    continue
                print(f"[{ev_type}] {s[:args.chars]}".replace("\n", " "))
    if not found:
        print("未找到 id 子串匹配的会话，先用 rank 找。")

def main():
    ap = argparse.ArgumentParser(description="跨客户端按执行痕迹搜索会话（只读）")
    sub = ap.add_subparsers(dest="cmd")
    def add_common(sp):
        sp.add_argument("--client", choices=["dsh", "codex", "claude", "all"], default="all")
    sp = sub.add_parser("paths"); add_common(sp); sp.set_defaults(fn=cmd_paths)
    sp = sub.add_parser("rank")
    add_common(sp)
    sp.add_argument("pattern", help="空格分隔的执行痕迹关键词")
    sp.add_argument("--min-hits", type=int, default=2)
    sp.add_argument("--limit", type=int, default=30)
    sp.set_defaults(fn=cmd_rank)
    sp = sub.add_parser("dump")
    add_common(sp)
    sp.add_argument("id", help="会话 id 或路径子串")
    sp.add_argument("--pattern", default="", help="只显示含这些词的消息")
    sp.add_argument("--chars", type=int, default=500)
    sp.set_defaults(fn=cmd_dump)
    args = ap.parse_args()
    if not getattr(args, "fn", None):
        ap.print_help(); return
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args.fn(args)

if __name__ == "__main__":
    main()
