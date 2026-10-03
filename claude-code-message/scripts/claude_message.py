#!/usr/bin/env python3
"""
claude_message.py - 向本机 Claude Code 会话发消息并获取回复

用法:
  python claude_message.py --list
  python claude_message.py --session <uuid> --message "内容"
  python claude_message.py --session <uuid> --message "内容" --fork
  python claude_message.py --session <uuid> --latest 5
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def get_claude_home():
    """获取 .claude 目录路径"""
    return Path(os.path.expanduser("~/.claude"))


def is_windows():
    return sys.platform == "win32"


def find_claude_binary():
    """查找 claude 可执行文件"""
    # 优先用 PATH 中的 claude
    from shutil import which
    binary = which("claude")
    if binary:
        return binary

    # Windows 常见路径
    if is_windows():
        candidates = [
            Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",
            Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe",
        ]
        for c in candidates:
            if c.exists():
                return str(c)

    return "claude"  # fallback, 让系统去找


def list_sessions():
    """列出当前运行的 Claude Code 会话"""
    sessions_dir = get_claude_home() / "sessions"
    if not sessions_dir.exists():
        print("未找到会话目录:", sessions_dir)
        return []

    sessions = []
    for f in sorted(sessions_dir.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            pid = data.get("pid")
            session_id = data.get("sessionId")
            cwd = data.get("cwd", "")
            name = data.get("name", "")
            status = data.get("status", "")
            updated_at = data.get("updatedAt", 0)

            # 转换时间戳
            if updated_at:
                updated_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(updated_at / 1000))
            else:
                updated_str = "?"

            sessions.append({
                "pid": pid,
                "sessionId": session_id,
                "cwd": cwd,
                "name": name,
                "status": status,
                "updatedAt": updated_str,
            })
        except Exception as e:
            print(f"读取 {f.name} 失败: {e}", file=sys.stderr)

    # 按最近活跃排序
    sessions.sort(key=lambda x: x.get("updatedAt", ""), reverse=True)
    return sessions


def print_sessions(sessions, ids_only=False):
    """打印会话列表"""
    if ids_only:
        for s in sessions:
            print(s["sessionId"])
        return

    if not sessions:
        print("没有找到活跃会话")
        return

    # 表头
    print(f"{'PID':<8} {'STATUS':<10} {'NAME':<28} {'LAST_ACTIVE':<18} CWD")
    print("-" * 120)
    for s in sessions:
        pid = str(s.get("pid", "?"))
        status = s.get("status", "?")
        name = (s.get("name", "") or "")[:26]
        updated = s.get("updatedAt", "?")
        cwd = s.get("cwd", "")
        print(f"{pid:<8} {status:<10} {name:<28} {updated:<18} {cwd}")

    print(f"\n共 {len(sessions)} 个会话")
    print("\n使用方式:")
    print("  python claude_message.py --session <SESSION_ID> --message \"你的消息\"")
    print("  python claude_message.py --session <SESSION_ID> --latest 10")


def find_session_jsonl(session_id):
    """查找指定会话的 jsonl 文件路径"""
    projects_dir = get_claude_home() / "projects"
    if not projects_dir.exists():
        return None

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        jsonl_path = project_dir / f"{session_id}.jsonl"
        if jsonl_path.exists():
            return jsonl_path
    return None


def read_latest_messages(session_id, n=5):
    """读取会话最近 n 条有意义的消息"""
    jsonl_path = find_session_jsonl(session_id)
    if not jsonl_path:
        print(f"未找到会话 {session_id} 的对话文件")
        return

    size_mb = jsonl_path.stat().st_size / (1024 * 1024)
    print(f"会话文件: {jsonl_path}")
    print(f"文件大小: {size_mb:.1f} MB")
    print()

    # 读取所有行（大文件可能慢，但只取最后 n 条有意义的）
    lines = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(line)

    print(f"总记录数: {len(lines)}")
    print()

    # 从后往前找 user 和 assistant 消息
    meaningful = []
    for line in reversed(lines):
        try:
            obj = json.loads(line)
            msg_type = obj.get("type", "")
            if msg_type not in ("user", "assistant"):
                continue

            msg = obj.get("message", {})
            content = msg.get("content", "") if isinstance(msg, dict) else msg

            text = extract_text(content)
            if not text or text.strip() == "":
                continue

            ts = obj.get("timestamp", "")
            meaningful.append({
                "type": msg_type,
                "timestamp": ts,
                "text": text,
            })

            if len(meaningful) >= n:
                break
        except Exception:
            continue

    # 反转回正序
    meaningful.reverse()

    for i, m in enumerate(meaningful):
        role = "你" if m["type"] == "user" else "Claude"
        ts = m["timestamp"][:19].replace("T", " ") if m["timestamp"] else "?"
        print(f"--- [{i+1}] {role} ({ts}) ---")
        print(m["text"][:1000])
        print()


def extract_text(content):
    """从 Claude Code 消息内容中提取纯文本"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if not isinstance(c, dict):
                continue
            t = c.get("type", "")
            if t == "text":
                parts.append(c.get("text", ""))
            elif t == "tool_use":
                name = c.get("name", "")
                inp = c.get("input", {})
                inp_str = json.dumps(inp, ensure_ascii=False)[:150]
                parts.append(f"[调用工具: {name}] {inp_str}")
            elif t == "tool_result":
                tc = c.get("content", "")
                if isinstance(tc, list):
                    tc = " ".join(
                        x.get("text", "") for x in tc
                        if isinstance(x, dict) and x.get("type") == "text"
                    )
                parts.append(f"[工具结果] {str(tc)[:300]}")
            elif t == "thinking":
                parts.append(f"[思考] {c.get('thinking', '')[:200]}")
        return "\n".join(parts)
    return str(content)


def send_message(session_id, message, fork=False, timeout=300, cwd=None, skip_permissions=True):
    """向指定会话发送消息并获取回复

    Args:
        session_id: 目标会话 UUID
        message: 消息内容
        fork: 是否创建分支会话（不污染原会话）
        timeout: 超时秒数
        cwd: 运行命令的工作目录（重要：应设为目标代码仓库根目录，
             否则 Claude 的工具权限会被限定在当前目录，导致读不到目标代码）
        skip_permissions: 是否添加 --dangerously-skip-permissions
             （重要：不加的话只有读权限，写文件/执行命令会被拦截。
              仅在你完全信任该会话且目标目录是你自己的代码时开启。）
    """
    binary = find_claude_binary()

    cmd = [binary, "--resume", session_id, "--print", message]
    if fork:
        cmd.insert(2, "--fork-session")
    if skip_permissions:
        cmd.insert(2, "--dangerously-skip-permissions")

    # Windows 下重定向 stdin 避免警告
    stdin = subprocess.DEVNULL

    # 切换工作目录
    original_cwd = os.getcwd()
    if cwd:
        cwd = os.path.abspath(os.path.expanduser(cwd))
        if not os.path.isdir(cwd):
            print(f"[错误] 工作目录不存在: {cwd}")
            return False
        os.chdir(cwd)

    print(f"执行: {' '.join(cmd[:5])} ...")
    print(f"工作目录: {os.getcwd()}")
    if fork:
        print("模式: 分支会话（不污染原会话）")
    else:
        print("模式: 直接写入原会话")
    if skip_permissions:
        print("权限: 跳过权限确认（可读写/执行）")
    else:
        print("权限: 默认（可能需要手动批准）")
    print(f"超时: {timeout} 秒")
    print()

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=stdin,
            timeout=timeout,
        )
        elapsed = time.time() - start

        print(f"[完成] 耗时 {elapsed:.1f} 秒, 退出码 {result.returncode}")
        print()

        if result.stdout:
            print("=== Claude 回复 ===")
            print(result.stdout.strip())
            print()

        if result.stderr:
            # 过滤掉 stdin 警告
            stderr_lines = [
                line for line in result.stderr.splitlines()
                if "no stdin data received" not in line
            ]
            if stderr_lines:
                print("=== 标准错误 ===")
                print("\n".join(stderr_lines))
                print()

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        print(f"[超时] {elapsed:.1f} 秒后仍未完成（超时设置 {timeout} 秒）")
        print("提示: 大会话恢复需要较长时间，可通过 --timeout 增加超时")
        return False
    except Exception as e:
        print(f"[错误] {e}")
        return False
    finally:
        # 恢复原工作目录
        if cwd:
            os.chdir(original_cwd)


def main():
    parser = argparse.ArgumentParser(
        description="向本机 Claude Code 会话发消息并获取回复",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --list
  %(prog)s --session <uuid> --message "你好" --cwd /path/to/repo
  %(prog)s --session <uuid> --message "测试" --fork
  %(prog)s --session <uuid> --message "写代码" --cwd E:\\CodeProject\\hcyx
  %(prog)s --session <uuid> --latest 10
        """,
    )
    parser.add_argument("--list", action="store_true", help="列出当前活跃会话")
    parser.add_argument("--session", type=str, help="目标会话 ID（UUID）")
    parser.add_argument("--message", type=str, help="要发送的消息内容")
    parser.add_argument("--fork", action="store_true", help="创建分支会话，不写入原会话")
    parser.add_argument("--latest", type=int, metavar="N", help="查看该会话最近 N 条对话")
    parser.add_argument("--timeout", type=int, default=300, help="等待回复超时秒数（默认 300）")
    parser.add_argument("--ids-only", action="store_true", help="--list 时只输出会话 ID")
    parser.add_argument("--cwd", type=str, default=None,
                        help="运行命令的工作目录（重要：应设为目标代码仓库根目录，"
                             "否则 Claude 读不到目标代码、也写不进去）")
    parser.add_argument("--no-skip-permissions", action="store_true",
                        help="不添加 --dangerously-skip-permissions（默认会添加，"
                             "不加的话只有读权限，写文件/执行命令会被拦截）")

    args = parser.parse_args()

    if args.list:
        sessions = list_sessions()
        print_sessions(sessions, ids_only=args.ids_only)
        return

    if not args.session:
        parser.print_help()
        print("\n错误: 请指定 --session 或 --list")
        sys.exit(1)

    if args.latest:
        read_latest_messages(args.session, n=args.latest)
        return

    if args.message:
        success = send_message(
            args.session,
            args.message,
            fork=args.fork,
            timeout=args.timeout,
            cwd=args.cwd,
            skip_permissions=not args.no_skip_permissions,
        )
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        print("\n错误: 请指定 --message 或 --latest")
        sys.exit(1)


if __name__ == "__main__":
    main()
