#!/usr/bin/env python3
"""dsh_sessions.py — 读取 / 搜索 / 导出 / 删除 DeepSeek Harness (DSH) 的本地会话记录。

默认只读：不联网、不启动 DSH、不改任何会话文件。
唯一例外是 `delete` 子命令——它是唯一的写操作，默认只 dry-run，必须显式 --apply 才动盘。

数据源（按其存在与否自动探测）：
  <DSH_HOME>/sessions/**/session.v4.jsonl.zstd     当前版本会话
  ~/.dsh/sessions/**/session.jsonl.zstd             旧版（0.1.0-rc.x）会话
  <DSH_HOME>/storages/workspace.json                侧栏分组（workspace）归属
  <DSH_HOME>/storages/session_projcache/sessions/*.json   标题 / 首条消息缓存

命令：
  list                      列出全部会话（含所在分组、标题、时间、消息数）
  search <关键词>            全文搜索（用户 / 助手 / 工具输出）
  show <id前缀>              按轮次打印对话
  export <id前缀> -o x.md    导出 Markdown
  where <id前缀>             打印文件路径与它在 GUI 侧栏里的分组
  paths                     打印探测到的数据源
  delete <id前缀> [--apply]  删除会话（默认 dry-run；--with-children 连子代理一起删）

几个必须知道的实现细节：
  1. 会话是 **多帧 zstd 追加写**的。必须用 stream_reader(read_across_frames=True)
     或反复 decompress，否则只能读到第一帧（症状：整份会话只剩 1 行）。
  2. 正文不在事件顶层，在 ev["data"] 里；assistant 的正文在
     data.message.content[] 中，按 type 区分 reasoning / text。
  3. 侧栏按会话的 cwd 分组，分组名取自 workspace.json 的 title。
     "会话不见了" 十有八九是它属于另一个分组，而不是被删了。
  4. 删除没有官方接口（seam 无 delete）：删盘不会自动从 sessionIds 摘掉，
     会留「点不开的空条目」。所以 delete 先备份、再清登记、再删目录、最后校验悬空。
     **改完 workspace.json 必须重启 dsh web**；重启前别在侧栏归档/置顶，
     否则宿主会用内存里的旧数组把改动整份覆盖。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import glob
import io
import json
import os
import re
import sys
from typing import Any, Iterable

try:
    import zstandard
except ImportError:  # pragma: no cover
    sys.exit("需要 zstandard：python -m pip install zstandard")


# ---------------------------------------------------------------- 数据源探测

def candidate_homes() -> list[str]:
    homes = []
    env = os.environ.get("DSH_HOME")
    if env:
        homes.append(env)
    legacy = os.path.join(os.path.expanduser("~"), ".dsh")
    if os.path.isdir(legacy):
        homes.append(legacy)
    # DSH_HOME 可能被改过多次：顺手把常见位置里带 sessions 的也收进来
    for guess in (
        os.path.join(os.getcwd(), "dsh", "home"),
        os.path.join(os.path.expanduser("~"), "Documents", "deepseek-harness"),
    ):
        if os.path.isdir(os.path.join(guess, "sessions")) and guess not in homes:
            homes.append(guess)
    # 去重：DSH_HOME 常常就是 ~/.dsh，重复会让每个会话被读两遍，
    # 进而让 resolve() 报「id 前缀不唯一」（show / export / where 全废）。
    out, seen = [], set()
    for h in homes:
        key = os.path.normcase(os.path.abspath(h))
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def iter_session_files(homes: Iterable[str]) -> list[str]:
    out = []
    for home in homes:
        root = os.path.join(home, "sessions")
        if not os.path.isdir(root):
            continue
        for path in glob.glob(os.path.join(root, "**", "session*.zstd"), recursive=True):
            out.append(path)
    return sorted(out)


def read_session_bytes(path: str) -> bytes:
    """读完整份会话 —— 关键是跨帧（DSH 是追加写，一次一个 frame）。"""
    data = open(path, "rb").read()
    if path.endswith(".zstd"):
        dctx = zstandard.ZstdDecompressor()
        with dctx.stream_reader(io.BytesIO(data), read_across_frames=True) as reader:
            return reader.read()
    return data


# ---------------------------------------------------------------- 文本抽取

def _walk_text(obj: Any, out: list[str], depth: int = 0) -> None:
    if depth > 12:
        return
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, list):
        for item in obj:
            _walk_text(item, out, depth + 1)
    elif isinstance(obj, dict):
        for key, value in obj.items():
            if key in ("id", "callId", "toolCallId", "sessionId", "path",
                       "type", "role", "kind", "source", "name"):
                continue
            _walk_text(value, out, depth + 1)


def user_text(ev: dict) -> str:
    data = ev.get("data") or {}
    out: list[str] = []
    _walk_text(data.get("content"), out)
    return "\n".join(out).strip()


# 注入类 user/message（不是用户打的字）：runtime-context / skill-catalog /
# time-context / user-approval / compact-checkpoint / tool-jobs …
INJECTED_KINDS = {"user-approval", "runtime-context", "skill-catalog", "time-context",
                  "compact-checkpoint", "tool-jobs", "goal", "reminder"}


def user_source(ev: dict) -> str:
    return ((ev.get("data") or {}).get("source") or {}).get("kind") or "user"


def is_real_user(ev: dict) -> bool:
    return user_source(ev) not in INJECTED_KINDS


def assistant_parts(ev: dict) -> tuple[str, str]:
    """返回 (reasoning, text)。"""
    msg = (ev.get("data") or {}).get("message") or {}
    reason, text = [], []
    for block in msg.get("content") or []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "reasoning":
            reason.append(block.get("text") or "")
        elif kind == "text":
            text.append(block.get("text") or "")
    return "\n".join(reason).strip(), "\n".join(text).strip()


def tool_result_text(ev: dict) -> str:
    msg = (ev.get("data") or {}).get("message") or {}
    out: list[str] = []
    _walk_text(msg.get("content"), out)
    return "\n".join(out).strip()


# ---------------------------------------------------------------- 会话解析

class Session:
    def __init__(self, path: str, home: str):
        self.path = path
        self.home = home
        self.events: list[dict] = []
        self.head: dict = {}
        self.title: str | None = None
        self.load()

    def load(self) -> None:
        raw = read_session_bytes(self.path)
        for line in raw.decode("utf-8", "replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            self.events.append(ev)
            kind = ev.get("type")
            if kind == "session":
                self.head = ev
            elif kind == "session/title":
                data = ev.get("data") or {}
                title = data.get("title") or data.get("value")
                # fallback 标题（截断的首句）先记着，被正式标题覆盖
                if title and (self.title is None or data.get("source", {}).get("kind") != "fallback"):
                    self.title = title

    # --- 元信息
    @property
    def id(self) -> str:
        return self.head.get("id") or os.path.basename(os.path.dirname(self.path))

    @property
    def cwd(self) -> str:
        return self.head.get("cwd") or "?"

    @property
    def created(self) -> float:
        return (self.head.get("createdAt") or 0) / 1000.0

    @property
    def updated(self) -> float:
        times = [ev.get("time") for ev in self.events if isinstance(ev.get("time"), (int, float))]
        return (max(times) / 1000.0) if times else self.created

    @property
    def user_messages(self) -> list[str]:
        """只算用户亲手打的字，不含 harness 注入的 runtime-context 等。"""
        return [t for t in (user_text(ev) for ev in self.events
                            if ev.get("type") == "user/message" and is_real_user(ev)) if t]

    @property
    def is_legacy(self) -> bool:
        return (self.head.get("version") or 0) < 4

    def plain_text(self) -> str:
        out = []
        for ev in self.events:
            kind = ev.get("type")
            if kind == "user/message":
                out.append(user_text(ev))
            elif kind == "assistant/message":
                _, text = assistant_parts(ev)
                out.append(text)
            elif kind == "tool/result":
                out.append(tool_result_text(ev))
        return "\n".join(x for x in out if x)


# ---------------------------------------------------------------- 侧栏分组

def workspace_map(homes: Iterable[str]) -> tuple[dict[str, str], dict[str, str]]:
    """返回 (sessionId -> 分组名, sessionId -> 分组路径)，以及归档集合。"""
    by_session: dict[str, str] = {}
    paths: dict[str, str] = {}
    for home in homes:
        wp = os.path.join(home, "storages", "workspace.json")
        if not os.path.isfile(wp):
            continue
        try:
            doc = json.load(open(wp, encoding="utf-8"))
        except Exception:
            continue
        for ws in (doc.get("tables") or {}).get("workspaces", {}).values():
            title = ws.get("title") or os.path.basename(str(ws.get("path") or "")) or "未命名分组"
            for sid in ws.get("sessionIds") or []:
                by_session.setdefault(sid, title)
                paths.setdefault(sid, str(ws.get("path") or ""))
    return by_session, paths


def archived_ids(homes: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for home in homes:
        wp = os.path.join(home, "storages", "workspace.json")
        if not os.path.isfile(wp):
            continue
        try:
            doc = json.load(open(wp, encoding="utf-8"))
        except Exception:
            continue
        out.update((doc.get("global") or {}).get("archivedSessionIds") or [])
    return out


def cached_titles(homes: Iterable[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for home in homes:
        for path in glob.glob(os.path.join(home, "storages", "session_projcache", "sessions", "*.json")):
            try:
                doc = json.load(open(path, encoding="utf-8"))
            except Exception:
                continue
            val = ((doc.get("record") or {}).get("rows") or {}).get("title") or {}
            title = (val.get("val") or {}).get("title") if isinstance(val.get("val"), dict) else val.get("val")
            sid = os.path.basename(path)[:-5]
            if title:
                out[sid] = title
    return out


# ---------------------------------------------------------------- 工具

def fmt_time(ts: float) -> str:
    if not ts:
        return "?"
    return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def load_all(homes: list[str]) -> list[Session]:
    sessions = []
    seen_paths: set[str] = set()
    for path in iter_session_files(homes):
        key = os.path.normcase(os.path.abspath(path))
        if key in seen_paths:       # 多个 home 覆盖同一目录时不要重复计数
            continue
        seen_paths.add(key)
        home = next((h for h in homes if os.path.abspath(path).startswith(os.path.abspath(h))), "")
        try:
            sessions.append(Session(path, home))
        except Exception as exc:
            print(f"!! 读取失败 {path}: {exc}", file=sys.stderr)
    sessions.sort(key=lambda s: s.created)
    return sessions


def _strip_session_prefix(sid: str) -> str:
    """只剥掉字面的 "session-" 前缀 —— 别用 lstrip(chars)，它会把 id 开头
    的 e/s/i/o/n 也一起吃掉（session-e221e301 会变成 221e301，前缀就找不到了）。"""
    sid = sid.lower()
    return sid[len("session-"):] if sid.startswith("session-") else sid


def resolve(sessions: list[Session], prefix: str) -> Session:
    key = _strip_session_prefix(prefix)
    hits = [s for s in sessions if _strip_session_prefix(s.id).startswith(key)]
    if not hits:
        sys.exit(f"没有匹配 {prefix!r} 的会话；先跑 list 看看 id")
    if len(hits) > 1:
        sys.exit("id 前缀不唯一：\n" + "\n".join(f"  {s.id}  {s.title}" for s in hits))
    return hits[0]


# ---------------------------------------------------------------- 命令

def cmd_list(args, homes, sessions):
    titles = cached_titles(homes)
    groups, _ = workspace_map(homes)
    archived = archived_ids(homes)
    rows = []
    for s in sessions:
        title = titles.get(s.id) or s.title or "(未命名)"
        group = groups.get(s.id, "未分组" if not s.is_legacy else "旧版 · 未分组")
        flag = " [归档]" if s.id in archived else ""
        if s.is_legacy:
            flag += " [旧版]"
        rows.append((s.created, group, title, s, flag))
    rows.sort(key=lambda r: r[0], reverse=not args.asc)
    if args.group:
        rows.sort(key=lambda r: r[1])
    limit = args.limit or len(rows)
    print(f"{'时间':<16} {'分组':<14} {'消息':>4}  标题")
    print("-" * 100)
    for created, group, title, s, flag in rows[:limit]:
        print(f"{fmt_time(created):<16} {group[:13]:<14} {len(s.user_messages):>4}  {title}{flag}")
        if args.verbose:
            print(f"{'':16} id={s.id}")
            print(f"{'':16} cwd={s.cwd}")
    print(f"\n共 {len(rows)} 个会话（{len(rows[:limit])} 条显示）")


def cmd_search(args, homes, sessions):
    pat = re.compile(args.pattern, re.IGNORECASE) if args.regex else None
    titles = cached_titles(homes)
    groups, _ = workspace_map(homes)
    total = 0
    for s in sessions:
        hits = []
        for idx, ev in enumerate(s.events):
            kind = ev.get("type")
            if kind == "user/message":
                text, where = user_text(ev), "user"
            elif kind == "assistant/message":
                reason, text = assistant_parts(ev)
                where = "assistant"
                if args.reasoning:
                    text = (reason + "\n" + text).strip()
            elif kind == "tool/result" and args.tools:
                text, where = tool_result_text(ev), "tool"
            else:
                continue
            if not text:
                continue
            if args.role and where != args.role:
                continue
            m = pat.search(text) if pat else (text.find(args.pattern) >= 0)
            if not m:
                continue
            pos = m.start() if pat else text.find(args.pattern)
            start = max(0, pos - args.context)
            end = min(len(text), pos + len(args.pattern) + args.context)
            snippet = " ".join(text[start:end].split())
            hits.append((fmt_time((ev.get("time") or 0) / 1000), where, snippet))
            if len(hits) >= args.per_session:
                break
        if not hits:
            continue
        total += len(hits)
        print("=" * 100)
        print(f"{titles.get(s.id) or s.title or '(未命名)'}   [{groups.get(s.id, '未分组')}]")
        print(f"  {s.id}  ·  {fmt_time(s.created)}  ·  {s.cwd}")
        for when, where, snippet in hits:
            print(f"  [{when}] ({where}) {snippet[:300]}")
    print(f"\n命中 {total} 处")


def cmd_show(args, homes, sessions):
    s = resolve(sessions, args.id)
    titles = cached_titles(homes)
    groups, paths = workspace_map(homes)
    print(f"标题: {titles.get(s.id) or s.title or '(未命名)'}")
    print(f"id  : {s.id}")
    print(f"分组: {groups.get(s.id, '未分组')}   ({paths.get(s.id, s.cwd)})")
    print(f"时间: {fmt_time(s.created)} → {fmt_time(s.updated)}   用户消息 {len(s.user_messages)} 条")
    print("=" * 100)
    turn = 0
    for ev in s.events:
        kind = ev.get("type")
        if kind == "turn/start":
            turn = (ev.get("data") or {}).get("turn") or turn + 1
        elif kind == "user/message":
            text = user_text(ev)
            if not text:
                continue
            if not is_real_user(ev):
                if args.injected and turn >= args.begin:
                    print(f"\n   [注入:{user_source(ev)}] " + trim(text, 160, indent="   "))
                continue
            if turn < args.begin or (args.end and turn > args.end):
                continue
            print(f"\n── 用户 (turn {turn}) " + "─" * 60)
            print(trim(text, args.chars))
        elif kind == "assistant/message":
            if args.user_only or turn < args.begin or (args.end and turn > args.end):
                continue
            reason, text = assistant_parts(ev)
            if args.reasoning and reason:
                print("\n   [reasoning] " + trim(reason, args.chars, indent="   "))
            if text:
                print(f"\n── 助手 (turn {turn}) " + "─" * 66)
                print(trim(text, args.chars))
        elif kind == "tool/call" and args.tools and turn >= args.begin:
            data = ev.get("data") or {}
            print(f"\n   → {data.get('name')} {trim(str(data.get('arguments'))[:400], 400)}")
        elif kind == "tool/result" and args.tools and turn >= args.begin:
            print("   ← " + trim(tool_result_text(ev), args.chars, indent="   "))


def trim(text: str, limit: int, indent: str = "") -> str:
    if limit and len(text) > limit:
        text = text[:limit] + f"\n…（截断，原长 {len(text)} 字符；用 --chars 0 看全文）"
    if indent:
        return "\n".join(indent + line for line in text.splitlines())
    return text


def cmd_export(args, homes, sessions):
    s = resolve(sessions, args.id)
    titles = cached_titles(homes)
    groups, paths = workspace_map(homes)
    lines = [
        f"# {titles.get(s.id) or s.title or '(未命名)'}",
        "",
        f"- id: `{s.id}`",
        f"- 分组: {groups.get(s.id, '未分组')}（{paths.get(s.id, s.cwd)}）",
        f"- 时间: {fmt_time(s.created)} → {fmt_time(s.updated)}",
        "",
    ]
    for ev in s.events:
        kind = ev.get("type")
        stamp = fmt_time((ev.get("time") or 0) / 1000)
        if kind == "user/message":
            if not is_real_user(ev):
                continue
            text = user_text(ev)
            if text:
                lines += [f"## 用户 · {stamp}", "", text, ""]
        elif kind == "assistant/message":
            _, text = assistant_parts(ev)
            if text:
                lines += [f"### 助手 · {stamp}", "", text, ""]
    out = args.out or f"dsh-{s.id}.md"
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    print(f"已写出 {out}（{len(lines)} 行）")


def cmd_where(args, homes, sessions):
    s = resolve(sessions, args.id)
    groups, paths = workspace_map(homes)
    print(f"id      : {s.id}")
    print(f"文件    : {s.path}")
    print(f"cwd     : {s.cwd}")
    print(f"侧栏分组: {groups.get(s.id, '未分组（没有登记在任何 workspace 里）')}")
    print(f"分组路径: {paths.get(s.id, s.cwd)}")
    print(f"格式    : {'旧版 (v0)' if s.is_legacy else 'v4'}")
    print("\nGUI 里怎么看：左侧侧栏切到上面那个分组，标题可能和内容对不上（标题是自动生成的），")
    print("按 id 或按内容找更快——或者直接 `search <关键词>`。")


def cmd_paths(args, homes, sessions):
    for home in homes:
        print(f"home     : {home}")
        print(f"  sessions : {'有，' + str(len(glob.glob(os.path.join(home, 'sessions', '**', 'session*.zstd'), recursive=True))) + ' 个文件' if os.path.isdir(os.path.join(home, 'sessions')) else '无'}")
        print(f"  workspace: {'有' if os.path.isfile(os.path.join(home, 'storages', 'workspace.json')) else '无'}")
        print(f"  projcache: {'有' if os.path.isdir(os.path.join(home, 'storages', 'session_projcache')) else '无'}")
    print(f"\n合计会话 {len(sessions)} 个")


# ---------------------------------------------------------------- 删除（唯一的写操作）

def _dir_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _children_of(sessions: list[Session], sid: str) -> list[Session]:
    """origin=subagent 的子会话挂在父会话的 head.parentSession 上。"""
    return [s for s in sessions if (s.head.get("parentSession") or "") == sid]


def _sessions_root(home: str) -> str:
    return os.path.abspath(os.path.join(home, "sessions"))


def _assert_inside_home(path: str, homes: Iterable[str]) -> None:
    """删除前的路径闸门：只允许删探测到的 home 下 sessions/ 里的目录。"""
    target = os.path.abspath(path)
    for home in homes:
        root = _sessions_root(home)
        try:
            if os.path.commonpath([target, root]) == root:
                return
        except ValueError:      # 不同盘符时 commonpath 会抛
            continue
    raise SystemExit(f"拒绝删除：{target} 不在任何已探测的 <DSH_HOME>/sessions 下")


def _backup(dirs: dict[str, str], dest: str) -> int:
    """把若干会话目录压成一个 zip（每个目录单独一个顶层条目）。"""
    import zipfile

    count = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in dirs:
            for root, _subs, files in os.walk(d):
                for name in files:
                    full = os.path.join(root, name)
                    rel = os.path.join(os.path.basename(d), os.path.relpath(full, d))
                    zf.write(full, rel)
                    count += 1
    return count


def cmd_delete(args, homes, sessions):
    # 1) 解析目标
    picked: dict[str, Session] = {}
    for prefix in args.id:
        s = resolve(sessions, prefix)
        picked[s.id] = s
    for s in list(picked.values()):
        if args.with_children:
            for c in _children_of(sessions, s.id):
                picked[c.id] = c

    plan: list[tuple[Session, str]] = []
    for s in picked.values():
        parent = s.head.get("parentSession")
        reason = f"子代理（父 {_strip_session_prefix(parent)[:8]}）" if parent else "主会话"
        plan.append((s, reason))

    groups, _paths = workspace_map(homes)
    arch = archived_ids(homes)

    # 2) 打印计划（dry-run 与 apply 都打）
    total = 0
    print(f"目标 {len(plan)} 个会话：")
    for s, reason in plan:
        d = os.path.dirname(s.path)
        size = _dir_size(d)
        total += size
        reg = groups.get(s.id, "未登记")
        extra = " [已归档]" if s.id in arch else ""
        print(f"  {s.id[:16]}  {size / 1048576:6.2f} MB  {reason}  分组={reg}{extra}")
    print(f"合计 {total / 1048576:.2f} MB")

    kids = [c for s in picked.values() for c in _children_of(sessions, s.id)
            if c.id not in picked]
    if kids:
        print(f"\n注意：这 {len(kids)} 个子代理会话不在删除范围内，父会话删掉后它们会变孤儿"
              f"（侧栏不可见、无入口）：")
        for c in kids[:10]:
            print(f"  {c.id[:16]}  {_dir_size(os.path.dirname(c.path)) / 1048576:.2f} MB")
        print("  要一起删就加 --with-children")

    if not args.apply:
        print("\n[dry-run] 没有改动任何文件。确认无误后加 --apply 执行。")
        print("提醒：DSH 无官方删除接口，本命令按「备份 → 清登记 → 删目录 → 清缓存 → 校验」的顺序做。")
        return

    # 3) 路径闸门
    for s, _ in plan:
        _assert_inside_home(os.path.dirname(s.path), homes)

    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    # 4) 备份会话目录
    if not args.no_backup:
        dest = os.path.join(args.backup_dir or os.path.expanduser("~"),
                            f"dsh-deleted-sessions-{stamp}.zip")
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        n = _backup([os.path.dirname(s.path) for s, _ in plan], dest)
        print(f"\n[1/5] 已备份 {n} 个文件 → {dest}")
    else:
        print("\n[1/5] 跳过备份（--no-backup）")

    # 5) 改 workspace.json（先备份原文件）
    ids = {s.id for s, _ in plan}
    touched = []
    for home in homes:
        wp = os.path.join(home, "storages", "workspace.json")
        if not os.path.isfile(wp):
            continue
        doc = json.load(open(wp, encoding="utf-8"))
        before = json.dumps(doc, sort_keys=True)
        if not args.no_backup:
            import shutil
            shutil.copy2(wp, f"{wp}.bak-{stamp}-delete")
        for ws in (doc.get("tables") or {}).get("workspaces", {}).values():
            ws["sessionIds"] = [x for x in (ws.get("sessionIds") or []) if x not in ids]
        for key in ("archivedSessionIds", "pinnedSessionIds"):
            if isinstance((doc.get("global") or {}).get(key), list):
                doc["global"][key] = [x for x in doc["global"][key] if x not in ids]
        if json.dumps(doc, sort_keys=True) != before:
            with open(wp, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)
                f.write("\n")
            touched.append(wp)
    print(f"[2/5] 登记表已更新：{len(touched)} 个 workspace.json")

    # 6) 删目录
    removed, failed = [], []
    for s, _ in plan:
        d = os.path.dirname(s.path)
        try:
            import shutil
            shutil.rmtree(d)
            removed.append(d)
        except Exception as exc:
            failed.append((d, str(exc)))
    print(f"[3/5] 已删除目录 {len(removed)} 个" + (f"，失败 {len(failed)} 个" if failed else ""))
    for d, err in failed:
        print(f"     !! {d}: {err}（DSH 可能正开着这个会话）")

    # 7) 删投影缓存
    cache_dirs = [os.path.join(h, "storages", "session_projcache", "sessions")
                  for h in homes]
    cache_dirs = [d for d in cache_dirs if os.path.isdir(d)]
    n_cache = 0
    for cd in cache_dirs:
        for sid in ids:
            for cand in (f"{sid}.json", f"session-{_strip_session_prefix(sid)}.json"):
                p = os.path.join(cd, cand)
                if os.path.isfile(p):
                    try:
                        os.remove(p)
                        n_cache += 1
                    except OSError:
                        pass
    print(f"[4/5] 已清理投影缓存 {n_cache} 个")

    # 8) 校验：登记表里不该再指向不存在的目录
    dangling = []
    for home in homes:
        wp = os.path.join(home, "storages", "workspace.json")
        if not os.path.isfile(wp):
            continue
        try:
            doc = json.load(open(wp, encoding="utf-8"))
        except Exception as exc:
            print(f"     !! workspace.json 解析失败：{exc}")
            continue
        root = _sessions_root(home)
        existing: set[str] = set()
        if os.path.isdir(root):
            for slug in os.listdir(root):
                sp = os.path.join(root, slug)
                if os.path.isdir(sp):
                    existing.update(os.listdir(sp))
        for ws in (doc.get("tables") or {}).get("workspaces", {}).values():
            for sid in ws.get("sessionIds") or []:
                if sid not in existing:
                    dangling.append(sid)
    print(f"[5/5] 校验：登记悬空条目 {len(dangling)} 个" + ("" if not dangling else " ← 需人工看"))
    for sid in dangling:
        print(f"     {sid}")
    if failed:
        sys.exit(1)

    print("\n完成。**必须重启 dsh web**，侧栏才会同步：")
    print("  · 重启前不要在侧栏做归档/置顶——宿主会用内存里的旧数组整份覆盖 workspace.json。")
    print("  · 想真正腾出磁盘，确认无误后删掉上面那个备份 zip。")


# ---------------------------------------------------------------- main

def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="读取 DSH 本地会话（只读）")
    p.add_argument("--home", action="append", default=[], help="额外/指定 DSH_HOME（可重复）")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="列出会话")
    pl.add_argument("--limit", type=int, default=0)
    pl.add_argument("--group", action="store_true", help="按分组排序")
    pl.add_argument("--asc", action="store_true", help="时间正序")
    pl.add_argument("-v", "--verbose", action="store_true", help="带 id / cwd")

    ps = sub.add_parser("search", help="全文搜索")
    ps.add_argument("pattern")
    ps.add_argument("--regex", action="store_true")
    ps.add_argument("--role", choices=["user", "assistant", "tool"])
    ps.add_argument("--reasoning", action="store_true", help="也搜推理过程")
    ps.add_argument("--tools", action="store_true", help="也搜工具输出")
    ps.add_argument("--context", type=int, default=60)
    ps.add_argument("--per-session", type=int, default=3)

    ph = sub.add_parser("show", help="打印对话")
    ph.add_argument("id")
    ph.add_argument("--tools", action="store_true")
    ph.add_argument("--reasoning", action="store_true")
    ph.add_argument("--injected", action="store_true", help="也显示 harness 注入的上下文消息")
    ph.add_argument("--user-only", action="store_true", help="只看用户说了什么")
    ph.add_argument("--from", dest="begin", type=int, default=0, help="从第 N 轮开始（跳过前面）")
    ph.add_argument("--to", dest="end", type=int, default=0, help="到第 N 轮为止")
    ph.add_argument("--chars", type=int, default=2000)

    pe = sub.add_parser("export", help="导出 Markdown")
    pe.add_argument("id")
    pe.add_argument("-o", "--out")

    pw = sub.add_parser("where", help="看某个会话在哪、属于哪个分组")
    pw.add_argument("id")

    sub.add_parser("paths", help="打印数据源")

    pd = sub.add_parser("delete", help="删除会话（默认只 dry-run）")
    pd.add_argument("id", nargs="+", help="会话 id 或前缀（可多个）")
    pd.add_argument("--apply", action="store_true", help="真的执行（不加只打印计划）")
    pd.add_argument("--with-children", action="store_true", help="连同子代理会话一起删")
    pd.add_argument("--backup-dir", help="备份 zip 放哪（默认用户主目录）")
    pd.add_argument("--no-backup", action="store_true", help="不备份（危险，不建议）")

    args = p.parse_args(argv)
    homes = args.home or candidate_homes()
    sessions = load_all(homes)
    if not sessions:
        sys.exit("没找到任何会话；用 `paths` 看看探测到哪些 home，或用 --home 指定。")
    {"list": cmd_list, "search": cmd_search, "show": cmd_show,
     "export": cmd_export, "where": cmd_where, "paths": cmd_paths,
     "delete": cmd_delete}[args.cmd](args, homes, sessions)


if __name__ == "__main__":
    try:
        main()
        sys.stdout.flush()
    except BrokenPipeError:
        # 被 `| head` / `| Select-Object -First N` 截断时别喷栈：
        # 把 stdout 换成 devnull，避免解释器退出时再 flush 一次
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
