# -*- coding: utf-8 -*-
"""生成「来时路」HTML：会话使用历史可视化。

输入：_extract_queue.json（会话元信息）+ knowledge raw/sessions-import/*.md
输出：knowledge raw/sessions-import/_TIMELINE.html（自带内联 CSS，无外部依赖）
"""
import glob, json, os, re, sys, html
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
OPS = os.path.join(os.path.dirname(os.path.abspath(__file__)))
KB_RAW = r"D:\github_project\ZhaoWen_KnowledgeBase\raw\sessions-import"
OUT = os.path.join(OPS, "_TIMELINE.html")   # 先写工作目录；再由 pwsh 复制到知识库 raw/

q = json.load(open(os.path.join(OPS, "_extract_queue.json"), encoding="utf-8"))

def safe_name(title, sid):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", (title or "").strip()).strip("_ .")[:40] or "(无标题)"
    # 子 Agent 实际命名：去掉 session- 前缀后取 UUID 前 8 位
    uid = sid[8:] if sid.startswith("session-") else sid
    return f"{s}-{uid[:8]}.md"

# 提取出的文件映射：优先按 md 头部记录的会话 ID 匹配（标题含特殊字符时文件名不统一）
extracted = {}
id_to_file = {}
for p in glob.glob(os.path.join(KB_RAW, "*.md")):
    try:
        head = open(p, encoding="utf-8", errors="replace").read(800)
        m = re.search(r"会话 ID `([^`]+)`", head)
        if m:
            id_to_file[m.group(1)] = os.path.basename(p)
    except Exception:
        pass
    extracted[os.path.basename(p)] = os.path.getsize(p)

# 按月分组
by_month = {}
for x in q:
    m = (x["mtime"] or "")[:7]
    by_month.setdefault(m, []).append(x)

css = """
<style>
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#f7f7f9;color:#222;margin:0;padding:24px}
.wrap{max-width:1100px;margin:0 auto}
h1{font-size:26px;margin:0 0 6px} .sub{color:#666;font-size:14px;margin-bottom:24px}
.m{background:#fff;border-radius:10px;padding:16px 20px;margin:14px 0;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.m h2{font-size:18px;margin:0 0 10px;color:#1a1a1a;border-bottom:1px solid #eee;padding-bottom:8px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #f0f0f0;vertical-align:top}
th{color:#888;font-weight:500}
a{color:#2563eb;text-decoration:none} a:hover{text-decoration:underline}
.tag{display:inline-block;padding:1px 7px;border-radius:9px;font-size:11px;margin-right:5px}
.arch{background:#f1f5f9;color:#64748b} .live{background:#dcfce7;color:#166534}
.sub{background:#fef3c7;color:#92400e} .main{background:#e0e7ff;color:#3730a3}
.stat{display:flex;gap:18px;margin-bottom:20px}
.stat div{background:#fff;padding:10px 18px;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.stat b{font-size:22px;display:block;color:#2563eb}
</style>
"""

L = ["<!DOCTYPE html>", '<html lang="zh-CN">', "<head>", '<meta charset="utf-8">',
     '<meta name="viewport" content="width=device-width,initial-scale=1">',
     "<title>会话来时路</title>", css, "</head>", "<body>", '<div class="wrap">',
     "<h1>会话来时路</h1>",
     f'<div class="sub">久未使用会话（≥14 天）· 生成 {datetime.now().strftime("%Y-%m-%d %H:%M")} · 来源：DSH 会话日志</div>']

stale = [x for x in q]
extracted_n = sum(1 for x in stale if x["id"] in id_to_file)
L += ['<div class="stat">',
      f'<div><b>{len(stale)}</b>会话</div>',
      f'<div><b>{extracted_n}</b>已提取 md</div>',
      f'<div><b>{sum(x["size_mb"] for x in stale):.0f} MB</b>体积</div>',
      f'<div><b>{max(x["age"] for x in stale)} 天</b>最久</div>',
      '</div>']

for m in sorted(by_month, reverse=True):
    items = sorted(by_month[m], key=lambda x: -x["age"])
    L.append(f'<div class="m"><h2>{m}（{len(items)} 个会话）</h2>')
    L.append("<table><tr><th>会话</th><th>最后活动</th><th>距今</th><th>体积</th><th>状态</th></tr>")
    for x in items:
        fn = id_to_file.get(x["id"]) or safe_name(x["title"], x["id"])
        st = '<span class="tag arch">归档</span>' if x["archived"] else '<span class="tag live">活跃</span>'
        tp = '<span class="tag sub">子Agent</span>' if x["is_sub"] else ''
        name = html.escape(x["title"])
        if fn in extracted:
            name = f'<a href="{html.escape(fn)}">{name}</a>'
        L.append(f'<tr><td>{name} {st}{tp}</td><td>{x["mtime"][:10]}</td>'
                 f'<td>{x["age"]}天</td><td>{x["size_mb"]:.2f}MB</td></tr>')
    L.append("</table></div>")

L += ["</div>", "</body>", "</html>"]
open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(L))
print(f"已写 {OUT}")
print(f"会话 {len(stale)}｜已提取 md {extracted_n}")
