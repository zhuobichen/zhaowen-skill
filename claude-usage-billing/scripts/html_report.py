# -*- coding: utf-8 -*-
"""Claude Code 用量分析报告生成器（按天，按任务归并，含子Agent 内容）。

用法：
    python html_report.py2026-10-14
    python html_report.py 2026-10-14 --csv-dir ~/Downloads --out ~/Desktop/report.html

数据源：
  1) 会话日志  ~/.claude/projects/<项目>/**.jsonl（主会话 + subagents/agent-*.jsonl）
  2) 账单 CSV  amount-*.csv / cost-*.csv（one-hub 导出，含每类 token 单价）

CSV 查找顺序：--csv / --csv-dir → 环境变量 DS_USAGE_CSV_DIR → ~/Downloads → <skill>/data
"""
import json, os, sys, glob, csv, collections, html, re, argparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)


def find_csv(explicit, explicit_dir):
    cands = []
    if explicit:
        if os.path.isdir(explicit):
            cands += glob.glob(os.path.join(explicit, "amount-*.csv"))
        elif os.path.isfile(explicit):
            cands.append(explicit)
    if not cands and explicit_dir:
        cands += glob.glob(os.path.join(explicit_dir, "amount-*.csv"))
    if not cands:
        for d in (os.environ.get("DS_USAGE_CSV_DIR"),
                  os.path.expanduser("~/Downloads"),
                  os.path.join(SKILL, "data")):
            if d and os.path.isdir(d):
                cands += glob.glob(os.path.join(d, "amount-*.csv"))
    cands = [c for c in cands if os.path.isfile(c)]
    if not cands:
        sys.exit("找不到账单 CSV（amount-*.csv）。用 --csv <文件> 或 --csv-dir <目录> 指定，"
                 "或解压 one-hub 用量 zip 后放到 ~/Downloads。")
    return max(cands, key=os.path.getmtime)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("day", nargs="?", default=None, help="YYYY-MM-DD，默认昨天")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--csv-dir", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"),
                    help="Claude Code 会话日志根目录")
    a = ap.parse_args()

    import datetime
    DAY = a.day or (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    CSV = find_csv(a.csv, a.csv_dir)
    OUT = a.out or os.path.abspath(f"claude-usage-{DAY}.html")
    TPL = os.path.join(SKILL, "assets", "report_template.html")

    # ---------- 1. 单价（按账单 CSV 加权平均） ----------
    tok = collections.Counter()
    cny = collections.Counter()
    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
    for r in rows:
        if not r["start_time_iso"].startswith(DAY):
            continue
        t = r["type"]
        if t == "request_count" or not r["price"]:
            continue
        n = float(r["amount"])
        tok[t] += n
        cny[t] += n * float(r["price"])
    if not tok:
        sys.exit(f"账单 CSV 里没有 {DAY} 的记录：{CSV}")
    PRICE = {t: cny[t] / tok[t] for t in tok}
    ALIAS = {"input_cache_hit_tokens": "hit", "input_cache_miss_tokens": "miss",
             "output_tokens": "out"}
    PRICE = {ALIAS.get(k, k): v for k, v in PRICE.items()}
    for k in ("hit", "miss", "out"):
        PRICE.setdefault(k, 0)
    BILL = sum(cny.values())

    def blocks(c):
        if isinstance(c, str):
            return [{"type": "text", "text": c}]
        return [b for b in (c or []) if isinstance(b, dict)]

    def realtext(c):
        return " ".join(b.get("text", "") for b in blocks(c)
                        if b.get("type") == "text").strip()

    BOILER = (
        "<task-notification", "<system-reminder", "<command-name",
        "This session is being continued", "Another Claude session sent a message",
        "Base directory for this skill", "[Your previous response had no visible output",
        "[Request interrupted", "Caveat: The messages below", "Please continue",
    )

    def is_boiler(s):
        return any(s.lstrip().startswith(p) for p in BOILER)

    def esc(s, n=None):
        s = s or ""
        if n and len(s) > n:
            s = s[:n] + "\n…（截断，全文见 exports/）"
        return html.escape(s)

    # ---------- 2. 扫描一个 jsonl ----------
    def scan(path, kind, sess):
        t = collections.Counter()
        ntool = 0
        last = None
        turns = []
        tools = collections.Counter()
        instr = ""
        final = ""
        nrec = 0
        cands = []
        cur = None
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            ts = o.get("timestamp")
            if not (ts and ts[:10] == DAY):
                continue
            nrec += 1
            last = ts
            m = o.get("message") or {}
            c = m.get("content")
            typ = o.get("type")
            u = m.get("usage")
            if u:
                t["hit"] += u.get("cache_read_input_tokens") or 0
                t["miss"] += (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
                t["out"] += u.get("output_tokens") or 0
            for b in blocks(c):
                if b.get("type") == "tool_use":
                    ntool += 1
                    tools[b.get("name") or "?"] += 1
                    if cur is not None:
                        cur["ntool"] += 1
            if u and cur is not None:
                cu = cur["u"]
                cu[0] += u.get("cache_read_input_tokens") or 0
                cu[1] += (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
                cu[2] += u.get("output_tokens") or 0
            if typ == "user" and not any(b.get("type") == "tool_result" for b in blocks(c)):
                s = realtext(c)
                if s and "Request interrupted" not in s:
                    cands.append(s)
                    if not instr and not is_boiler(s):
                        instr = s
                    if not is_boiler(s) or s.startswith("<task-notification"):
                        cur = dict(time=(ts or "")[11:19], text=s, u=[0, 0, 0], ntool=0)
                        turns.append(cur)
            if typ == "assistant":
                s = realtext(c)
                if s:
                    final = s
        if not (t["hit"] or t["miss"] or t["out"]):
            return None
        real = [s for s in cands if not is_boiler(s)]
        good = [s for s in real if len(s) >= 12]
        if good:
            title = max(good, key=len)
        elif len(real) > 1:
            title = " / ".join(s.strip() for s in real[-3:])
        elif real:
            title = real[-1]
        elif cands:
            title = "(当日只有系统/子Agent回传消息，无真人输入)"
        cost = sum(t[k] * PRICE.get(k, 0) for k in ("hit", "miss", "out"))
        for tr in turns:
            tr["cost"] = tr["u"][0] * PRICE["hit"] + tr["u"][1] * PRICE["miss"] + tr["u"][2] * PRICE["out"]
        return dict(kind=kind, sess=sess, cost=cost, t=t, ntool=ntool, title=title,
                    last=last, turns=turns, tools=tools, instr=instr, final=final, nrec=nrec)

    # ---------- 3. 遍历 ----------
    R = []
    for proj in os.listdir(a.root):
        pdir = os.path.join(a.root, proj)
        if not os.path.isdir(pdir):
            continue
        for sid in os.listdir(pdir):
            sp = os.path.join(pdir, sid)
            if os.path.isfile(sp) and sp.endswith(".jsonl"):
                r = scan(sp, "main", (proj, sid))
                if r:
                    R.append(r)
            elif os.path.isdir(sp):
                for f in glob.glob(os.path.join(sp, "**", "*.jsonl"), recursive=True):
                    x = scan(f, "sub", (proj, sid, os.path.relpath(f, sp)))
                    if x:
                        R.append(x)
    if not R:
        sys.exit(f"{a.root} 下没有 {DAY} 的会话记录。")
    R.sort(key=lambda r: -r["cost"])
    GT = sum(r["cost"] for r in R)
    SCALE = BILL / GT if GT else 1

    def taskkey(sess):
        s = sess[1]
        return (sess[0], s[:-6] if s.endswith(".jsonl") else s)

    # ---------- 4. 汇总卡片 ----------
    nsess = len(R)
    nmain = sum(1 for r in R if r["kind"] == "main")
    nsub = nsess - nmain
    subcost = sum(r["cost"] for r in R if r["kind"] == "sub") * SCALE
    subpct = subcost / BILL * 100 if BILL else 0
    tasks = collections.OrderedDict()
    for r in R:
        tasks.setdefault(taskkey(r["sess"]), []).append(r)
    tot_turns = sum(len(r["turns"]) for r in R if r["kind"] == "main")
    top = max(tasks.items(), key=lambda kv: sum(x["cost"] for x in kv[1]))
    top_cost = sum(x["cost"] for x in top[1]) * SCALE
    cards = [
        ("账单总额", f"{BILL:.2f} CNY", True),
        ("会话数", f"{nsess}", False),
        ("  其中主会话", f"{nmain}", False),
        ("  其中子Agent", f"{nsub}", False),
        ("任务数", f"{len(tasks)}", False),
        ("子Agent占比", f"{subpct:.0f}%", False),
        ("最大任务", f"{top_cost:.2f} CNY", True),
        ("主会话总轮次", f"{tot_turns}", False),
    ]
    summary_html = "".join(
        f'<div class="card{" big" if big else ""}"><div class="k">{k}</div><div class="v">{v}</div></div>'
        for k, v, big in cards)

    # ---------- 5. 按项目 ----------
    byproj = collections.Counter()
    for r in R:
        byproj[r["sess"][0]] += r["cost"]
    mx = max(byproj.values()) if byproj else 1
    proj_rows = "".join(
        f'<tr><td>{esc(k)}</td><td class="num">{v*SCALE:.2f}</td>'
        f'<td class="num">{v/GT*100:.1f}%</td>'
        f'<td><div class="bar"><i style="width:{v/mx*100:.0f}%"></i></div></td></tr>'
        for k, v in byproj.most_common())

    # ---------- 6. 任务抽屉 ----------
    def bar_span(v, mx_):
        return f'<div class="bar" style="width:120px"><i style="width:{v/mx_*100:.0f}%"></i></div>'

    def turn_html(tr):
        txt = tr["text"]
        is_sys = txt.lstrip().startswith("<")
        badge = '<span class="badge sys">系统/转发</span>' if is_sys else '<span class="badge you">你</span>'
        preview = re.sub(r"\s+", " ", txt)[:180]
        return (
            f'<details class="turn"><summary>{badge}<span class="mono">{tr["time"]}</span>'
            f'<span class="cny">{tr["cost"]*SCALE:.2f}</span>'
            f'<span class="pct">{tr["ntool"]} 工具</span>'
            f'<span class="muted">{esc(preview)}</span></summary>'
            f'<div style="padding:8px 12px"><div class="lbl">原文</div>'
            f'<pre class="pre">{esc(txt, 3000)}</pre></div></details>')

    def sub_html(r):
        tools = "".join(f'<span class="chip">{esc(n)}×{c}</span>' for n, c in r["tools"].most_common(8))
        body = (f'<div class="kv"><span>记录 <b>{r["nrec"]}</b> 条</span>'
                f'<span>工具 <b>{r["ntool"]}</b> 次</span>'
                f'<span>cache-hit <b>{r["t"]["hit"]/1e6:.1f}M</b></span>'
                f'<span>miss <b>{r["t"]["miss"]/1e6:.1f}M</b></span>'
                f'<span>output <b>{r["t"]["out"]/1e3:.0f}K</b></span></div>')
        if tools:
            body += f"<div>{tools}</div>"
        body += ('<div class="lbl" style="margin-top:8px">任务指令（首条用户消息）</div>'
                 f'<pre class="pre">{esc(r["instr"], 2500) or "（未捕获）"}</pre>')
        body += ('<div class="lbl" style="margin-top:8px">最终产出（末条助手文本）</div>'
                 f'<pre class="pre">{esc(r["final"], 4000) or "（无文本产出）"}</pre>')
        return (
            f'<details class="sub"><summary>'
            f'<span class="mono">{esc(os.path.basename(r["sess"][2]).replace("agent-","").replace(".jsonl","")[:12])}</span>'
            f'<span class="cny">{r["cost"]*SCALE:.2f} CNY</span>'
            f'<span class="muted">{r["ntool"]} 次工具 · {r["nrec"]} 条记录</span>'
            f'</summary><div class="sbody">{body}</div></details>')

    tasks_html = []
    mx_task = max(sum(x["cost"] for x in v) for v in tasks.values())
    for i, (key, members) in enumerate(
            sorted(tasks.items(), key=lambda kv: -sum(x["cost"] for x in kv[1])), 1):
        tc = sum(x["cost"] for x in members) * SCALE
        main = [m for m in members if m["kind"] == "main"]
        subs = [m for m in members if m["kind"] == "sub"]
        title = (main[0]["title"] if main else (subs[0]["instr"] if subs else "")) or "(无标题)"
        title = re.sub(r"\s+", " ", title)[:140]
        proj, sid = key
        parts = [f'<details class="task"><summary><span class="rk">#{i}</span>'
                 f'<span class="ttl">{esc(title)}</span>'
                 f'<span class="cny">{tc:.2f} CNY</span>'
                 f'<span class="pct">{tc/BILL*100:.1f}%</span>'
                 f'{bar_span(sum(x["cost"] for x in members), mx_task)}'
                 f'<span class="pct">{len(members)} 会话（{len(subs)} 子）· {esc(proj)}</span>'
                 f'</summary><div class="body">']
        if main:
            m0 = main[0]
            parts.append(f'<h3>主会话 <span class="mono">{sid[:8]}</span></h3>')
            parts.append(f'<div class="kv"><span>最后活动 <b>{esc((m0["last"] or "")[:19])}</b></span>'
                         f'<span>cache-hit <b>{m0["t"]["hit"]/1e6:.0f}M</b></span>'
                         f'<span>miss <b>{m0["t"]["miss"]/1e6:.1f}M</b></span>'
                         f'<span>output <b>{m0["t"]["out"]/1e3:.0f}K</b></span>'
                         f'<span>工具 <b>{m0["ntool"]}</b> 次</span>'
                         f'<span>折算 <b>{m0["cost"]*SCALE:.2f} CNY</b></span></div>')
            parts.append('<div class="lbl">逐轮对话（当天）</div>')
            parts.extend(turn_html(t) for t in m0["turns"])
        if subs:
            parts.append(f'<h3>子 Agent × {len(subs)}（当天合计 '
                         f'{sum(s["cost"] for s in subs)*SCALE:.2f} CNY）</h3>')
            parts.extend(sub_html(s) for s in sorted(subs, key=lambda x: -x["cost"]))
        parts.append("</div></details>")
        tasks_html.append("".join(parts))

    # ---------- 7. 输出 ----------
    tpl = open(TPL, encoding="utf-8").read()
    page = (tpl.replace("__SUMMARY__", summary_html)
               .replace("__PROJ__", proj_rows)
               .replace("__TASKS__", "".join(tasks_html))
               .replace("__DAY__", DAY)
               .replace("__BILL__", f"{BILL:.2f}"))
    os.makedirs(os.path.dirname(os.path.abspath(OUT)) or ".", exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(page)
    print(f"账单 CSV : {CSV}")
    print(f"任务 {len(tasks)} · 会话 {nsess} · 折算合计 {BILL:.2f}")
    print(f"最大任务 {top[0][1][:8]} {top_cost:.2f} CNY · 子Agent {nsub} 个占 {subpct:.0f}%")
    print("已写出:", OUT)


if __name__ == "__main__":
    main()
