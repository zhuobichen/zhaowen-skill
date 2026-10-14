# -*- coding: utf-8 -*-
"""体检 html_report.py 产出的 HTML：结构完整性 + 内容异常。

用法：python check_html.py [html路径]   默认检查 ./claude-usage-<昨天>.html
"""
import re, os, sys, html as H
import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

day = datetime.date.today() - datetime.timedelta(days=1)
p = sys.argv[1] if len(sys.argv) > 1 else f"claude-usage-{day.isoformat()}.html"
if not os.path.isfile(p):
    sys.exit(f"找不到 {p}，先跑 html_report.py。")
h = open(p, encoding="utf-8").read()

print("== 结构 ==")
print("  文件:", os.path.abspath(p), f"({len(h)//1024} KB)")
print("  details 开合差:", h.count("<details") - h.count("</details>"))
print("  未替换占位符:", set(re.findall(r"__[A-Z]+__", h)) or "无")
print("  U+FFFD 乱码:", h.count("\ufffd"))
print("  空 pre:", len(re.findall(r'<pre class="pre"></pre>', h)))
print("  None:", "None" in h, "| nan:", bool(re.search(r"\bnan\b", h)))

print("\n== 任务（金额 | 会话/子 | 标题） ==")
tot = 0.0
for blk in h.split('<details class="task">')[1:]:
    t = H.unescape(re.search(r'<span class="ttl">(.*?)</span>', blk).group(1))[:80]
    c = float(re.search(r'<span class="cny">([\d.]+) CNY', blk).group(1))
    n = re.search(r"(\d+) 会话（(\d+) 子）", blk)
    tot += c
    print(f"  {c:>6.2f} | {n.group(1)}会话/{n.group(2)}子 | {t}")

print("\n== 内容异常检查 ==")
titles = [H.unescape(x) for x in re.findall(r'<span class="ttl">(.*?)</span>', h)]
pats = (r"^(<task-notification|Another Claude session|Base directory for this skill|"
        r"\[Your previous response|This session is being continued)")
bad = [t for t in titles if re.match(pats, t)]
print("  标题仍是系统/agent 消息:", bad or "无")
tn = len(re.findall(r'<details class="turn">', h))
zcny = len(re.findall(r'<details class="turn"><summary>.*?<span class="cny">', h))
print(f"  逐轮行 {tn}，其中带金额 {zcny}")
subs = len(re.findall(r'<details class="sub">', h))
instr = len(re.findall(r"任务指令（首条用户消息）", h))
fin = len(re.findall(r"最终产出（末条助手文本）", h))
print(f"  子Agent 卡片 {subs}，含任务指令 {instr}，含最终产出 {fin}，缺内容: {subs != instr or subs != fin}")
c0 = float(re.findall(r'<div class="v">([\d.]+) CNY</div>', h)[0])
print(f"  头部账单 {c0:.2f}，任务折算合计 {tot:.2f}，差 {tot-c0:+.2f}")
