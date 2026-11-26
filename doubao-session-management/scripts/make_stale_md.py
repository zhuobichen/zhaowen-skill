# -*- coding: utf-8 -*-
"""生成豆包「三周没动」会话的 HTML 来时路 + md 清单。"""
import json, os, html
from datetime import datetime

OPS = os.path.dirname(os.path.abspath(__file__))
KB_RAW = r"D:\github_project\ZhaoWen_KnowledgeBase\raw\sessions-import\doubao"
t = json.load(open(os.path.join(OPS, "_doubao_timeline.json"), encoding="utf-8"))
now = datetime.now()
def days(s):
    try: return (now - datetime.strptime(s, "%Y-%m-%d %H:%M")).days
    except: return -1

old = [(k, v) for k, v in t.items() if v.get("last") and days(v["last"]) >= 21]
old.sort(key=lambda x: -days(x[1]["last"]))

# md 清单
L = ["# 豆包会话 · 三周未动清单", "",
     f"> 生成 {now.strftime('%Y-%m-%d %H:%M')}｜从 DOM 时间标记 + 接口时间提取",
     f"> 共 **{len(old)}** 个会话超过 21 天没动。", "",
     "| 会话 | 最早消息 | 最近消息 | 距今 | 消息数 | 来源 |", "|---|---|---|---:|---:|---|"]
for k, v in old:
    L.append(f"| {v['title'][:44]} | {v.get('first','')} | {v['last']} | "
             f"{days(v['last'])}天 | {v.get('messages',0)} | {v.get('source','DOM')} |")
L.append("")
open(os.path.join(OPS, "DOUBAO_STALE_SESSIONS.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L))
print(f"md 清单: {len(old)} 个")

# HTML
css = """<style>
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#f7f7f9;color:#222;margin:0;padding:24px}
.wrap{max-width:1000px;margin:0 auto}h1{font-size:26px;margin:0 0 6px}
.sub{color:#666;font-size:14px;margin-bottom:24px}
.c{background:#fff;border-radius:10px;padding:18px 22px;margin:12px 0;box-shadow:0 1px 4px rgba(0,0,0,.06)}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid #f0f0f0}
th{color:#888;font-weight:500}.days{font-weight:600;color:#c2410c}
</style>"""
H = ["<!DOCTYPE html>", "<html lang='zh-CN'><head><meta charset='utf-8'>",
     "<meta name='viewport' content='width=device-width,initial-scale=1'>",
     "<title>豆包会话来时路</title>", css, "</head><body><div class='wrap'>",
     "<h1>豆包会话来时路</h1>",
     f"<div class='sub'>三周（21天）未动会话 · {now.strftime('%Y-%m-%d %H:%M')} · 来源：CDP DOM 时间 + 接口时间</div>",
     "<div class='c'><table><tr><th>会话</th><th>最早</th><th>最近</th><th>距今</th><th>消息</th></tr>"]
for k, v in old:
    H.append(f"<tr><td>{html.escape(v['title'][:50])}</td><td>{v.get('first','')}</td>"
             f"<td>{v['last']}</td><td class='days'>{days(v['last'])}天</td>"
             f"<td>{v.get('messages',0)}</td></tr>")
H += ["</table></div></div></body></html>"]
open(os.path.join(OPS, "_DOUBAO_TIMELINE.html"), "w", encoding="utf-8", newline="\n").write("\n".join(H))
print("HTML 已写 _DOUBAO_TIMELINE.html")
