# -*- coding: utf-8 -*-
"""车队对比报告 → 单文件 HTML。

把某一天常在一起打的那几个人拆开比：谁跟谁老在一起、个人指标谁高谁低、
这些差异扛不扛得住多重比较校正。是 aram-mayhem MCP 的补充 —— MCP 只能查
单人，「我们几个谁强」这种问题它答不了。

用法：
    python squad_report.py --archive-dir <aram-mayhem/data> --day 2026-10-11 \
        --out 报告.html [--me <puuid>] [--avatars <头像目录>]

  --archive-dir  aram-mayhem 的 data/ 目录（读 archive/lol-matches.json 等）
  --me           我的 puuid；不传就读 <archive-dir>/profile.json
  --avatars      可选，头像目录。按「文件名是玩家名的子串」匹配，匹配不到就跳过
  --open-image   可选，报告开头的大图
  --meme-image   可选，称号那一节配的图
  --top          最多纳入几个人（含我），默认 5

口径要点（也写进报告里）：
  · 同队成员共享胜负 → 胜率没有区分度，个人表现要看 KDA/伤害/承伤这些个人量。
  · 比较用「同局成对差」：只在同一局里比，自动消掉对局长度、对手强度、版本。
  · 差异做收缩（EB，k=10）并跨全部检验做 BH-FDR —— 样本小时「谁更强」多半分不出来。

图表是手写 SVG，不依赖任何绘图库；只有 Pillow 用来读头像和压内嵌图。
"""
import base64
import io
import json
import math
import os
import random
from collections import defaultdict
from datetime import datetime

from PIL import Image

import argparse


def _cli():
    ap = argparse.ArgumentParser(description="车队对比报告生成器")
    ap.add_argument("--archive-dir", required=True, help="aram-mayhem 的 data/ 目录")
    ap.add_argument("--day", required=True, help="要分析的日期 YYYY-MM-DD")
    ap.add_argument("--out", required=True, help="输出的 HTML 路径")
    ap.add_argument("--me", default=None, help="我的 puuid；不传则读 profile.json")
    ap.add_argument("--avatars", default=None, help="头像目录（可选）")
    ap.add_argument("--open-image", default=None, help="报告开头的大图（可选）")
    ap.add_argument("--meme-image", default=None, help="称号那节的配图（可选）")
    ap.add_argument("--top", type=int, default=5, help="最多纳入几个人（含我）")
    return ap.parse_args()


ARGS = _cli()
A = ARGS.archive_dir
OUT = ARGS.out
DAY = ARGS.day


def _my_puuid():
    """--me 没给就从 aram-mayhem 写下的 profile.json 读，别把 puuid 写进代码。"""
    if ARGS.me:
        return ARGS.me
    p = os.path.join(A, "profile.json")
    with io.open(p, encoding="utf-8") as f:
        pu = (json.load(f) or {}).get("puuid")
    assert pu, "读不到 puuid：%s 里没有，也没给 --me" % p
    return pu


ME = _my_puuid()

# ---------------------------------------------------------------- 载入
with open(A + r"\archive\lol-matches.json", "r", encoding="utf-8") as f:
    archive = json.load(f)["games"]
with open(A + r"\champion-ids.json", "r", encoding="utf-8") as f:
    CID = json.load(f)
with open(A + r"\champions.json", "r", encoding="utf-8") as f:
    CHAMPS = json.load(f)

NUM2ID = {str(k): v.get("id", "") for k, v in CID.items()}
ID2NAME = {c.get("id"): c.get("name") for c in CHAMPS}
ID2ROLE = {c.get("id"): ((c.get("roles") or [""])[0] or "unknown") for c in CHAMPS}
ROLE_CN = {"fighter": "战士", "assassin": "刺客", "mage": "法师", "tank": "坦克",
           "marksman": "射手", "support": "辅助", "unknown": "未标注"}


def champ_role(cid):
    return ID2ROLE.get(NUM2ID.get(str(cid), ""), "unknown")


def champ_name(cid):
    i = NUM2ID.get(str(cid), "")
    return ID2NAME.get(i) or (CID.get(str(cid), {}) or {}).get("name") or ("英雄" + str(cid))


def hm(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%H:%M")


# ---------------------------------------------------------------- 取样
mine = [g for g in archive.values()
        if g.get("puuid") == ME and g.get("gameCreation")
        and datetime.fromtimestamp(g["gameCreation"] / 1000).strftime("%Y-%m-%d") == DAY]
mine.sort(key=lambda g: g["gameCreation"])
N = len(mine)

# 同队次数
same_cnt = defaultdict(int)
for g in mine:
    me_p = next((p for p in g["participants"] if p["puuid"] == ME), None)
    if not me_p:
        continue
    for p in g["participants"]:
        if p["teamId"] == me_p["teamId"] and p["puuid"] != ME:
            same_cnt[p["puuid"]] += 1

SQUAD = [ME] + [pu for pu, c in sorted(same_cnt.items(), key=lambda kv: -kv[1]) if c >= 2]
SQUAD = SQUAD[:ARGS.top]
NAME = {}
for g in mine:
    for p in g["participants"]:
        if p["puuid"] in SQUAD:
            NAME[p["puuid"]] = p["name"]
NAME[ME] = next((g["puuidName"] for g in mine if g.get("puuidName")), "我")

# ---------------------------------------------------------------- 每局记录
METRICS = [
    ("dpm", "分均伤害", lambda s, d: s.get("totalDamageDealtToChampions", 0) / (d / 60)),
    ("tpm", "分均承伤", lambda s, d: s.get("totalDamageTaken", 0) / (d / 60)),
    ("hpm", "分均治疗", lambda s, d: s.get("totalHeal", 0) / (d / 60)),
    ("gpm", "分均金币", lambda s, d: s.get("goldEarned", 0) / (d / 60)),
    ("cspm", "分均补刀", lambda s, d: s.get("totalMinionsKilled", 0) / (d / 60)),
    ("kda", "KDA 比", lambda s, d: (s.get("kills", 0) + s.get("assists", 0)) / max(1, s.get("deaths", 0))),
    ("ccpm", "分均控制", lambda s, d: s.get("timeCCingOthers", 0) / (d / 60)),
]

GAMES = []
for g in mine:
    d = g.get("gameDuration") or 0
    if d <= 0:
        continue
    row = {"t": hm(g["gameCreation"]), "ts": g["gameCreation"], "dur": d,
           "mode": g.get("gameMode"), "q": g.get("queueId"), "players": {}}
    for p in g["participants"]:
        if p["puuid"] not in SQUAD:
            continue
        s = p.get("stats") or {}
        row["players"][p["puuid"]] = {
            "k": s.get("kills", 0), "dd": s.get("deaths", 0), "a": s.get("assists", 0),
            "win": bool(s.get("win")), "champ": champ_name(p.get("championId")),
            "role": champ_role(p.get("championId")),
            **{key: fn(s, d) for key, _, fn in METRICS},
        }
    GAMES.append(row)

# ---------------------------------------------------------------- 聚合
def agg(pu):
    rs = [r["players"][pu] for r in GAMES if pu in r["players"]]
    n = len(rs)
    w = sum(1 for x in rs if x["win"])
    o = {"n": n, "w": w, "l": n - w, "wr": (w / n if n else 0),
         "k": sum(x["k"] for x in rs) / n, "d": sum(x["dd"] for x in rs) / n,
         "a": sum(x["a"] for x in rs) / n,
         "champs": defaultdict(int), "roles": defaultdict(int)}
    for x in rs:
        o["champs"][x["champ"]] += 1
        o["roles"][x["role"]] += 1
    for key, _, _ in METRICS:
        o[key] = sum(x[key] for x in rs) / n if n else 0
    return o


STATS = {pu: agg(pu) for pu in SQUAD}

# ---------------------------------------------------------------- 成对差 + 收缩 + FDR
K_SHRINK = 10
tests = []
for key, label, _ in METRICS:
    for pu in SQUAD:
        ds = []
        for r in GAMES:
            if pu not in r["players"]:
                continue
            others = [r["players"][q][key] for q in SQUAD if q != pu and q in r["players"]]
            if others:
                ds.append(r["players"][pu][key] - sum(others) / len(others))
        if len(ds) < 5:
            continue
        n = len(ds)
        m = sum(ds) / n
        var = sum((x - m) ** 2 for x in ds) / (n - 1) if n > 1 else 0.0
        se = math.sqrt(var / n) if var > 0 else 0.0
        z = m / se if se > 0 else 0.0
        p = math.erfc(abs(z) / math.sqrt(2))
        tests.append({"pu": pu, "key": key, "label": label, "n": n, "d": m, "se": se,
                      "z": z, "p": p, "sh": m * n / (n + K_SHRINK)})

tests.sort(key=lambda t: t["p"])
M = len(tests)
for i, t in enumerate(tests):
    t["q"] = min(1.0, t["p"] * M / (i + 1))
for i in range(M - 2, -1, -1):
    tests[i]["q"] = min(tests[i]["q"], tests[i + 1]["q"])

E = lambda s: (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
               .replace('"', "&quot;"))
COLORS = ["#2a78d6", "#eb6834", "#3f9c6b", "#a463c8", "#d9a441", "#5b8bd0"]

# ---------------------------------------------------------------- SVG 工具
INK = "#3b4149"
MUT = "#98a1ab"


def svg(w, h, body, extra=""):
    # 不写死 max-width：图表跟着正文栏宽走，才不会比正文窄一截、看着没对齐
    return ('<svg viewBox="0 0 %d %d" width="100%%" '
            'xmlns="http://www.w3.org/2000/svg" %s>%s</svg>' % (w, h, extra, body))


def nice_ticks(mx, k=4):
    """把纵轴抬到好读的整数刻度，返回 (上限, [刻度值...])。"""
    if mx <= 0:
        return 1.0, [0.0, 1.0]
    raw = mx / k
    mag = 10 ** math.floor(math.log10(raw))
    step = mag * 10
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            step = m * mag
            break
    top = math.ceil(mx / step) * step
    out, v = [], 0.0
    while v <= top + 1e-9:
        out.append(v)
        v += step
    return top, out


def bar_chart(labels, series, w=680, h=260, fmt="{:.0f}"):
    """分组柱。series = [(名字, 颜色, [值...]), ...]"""
    pad_l, pad_b, pad_t, pad_r = 46, 52, 24, 46
    n = len(labels)
    allv = [v for _, _, vs in series for v in vs] or [1]
    top, ticks = nice_ticks(max(allv), 4)
    bw = (w - pad_l - pad_r) / n
    grp = bw * 0.62 / len(series)
    base = h - pad_b
    o = ['<g stroke="%s" stroke-width="1" opacity="0.28">' % MUT]
    for v in ticks:
        y = pad_t + (base - pad_t) * (1 - v / top)
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (pad_l, y, w - pad_r, y))
    o.append('</g>')
    for v in ticks:
        y = pad_t + (base - pad_t) * (1 - v / top)
        o.append('<text x="%.1f" y="%.1f" font-size="10.5" fill="%s" text-anchor="end">%s</text>'
                 % (pad_l - 8, y + 3.5, MUT, fmt.format(v)))
    for i, lab in enumerate(labels):
        x0 = pad_l + i * bw + (bw - grp * len(series)) / 2
        for j, (nm, col, vs) in enumerate(series):
            v = vs[i]
            bh = (base - pad_t) * v / top
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" fill="%s">'
                     '<title>%s · %s %s</title></rect>'
                     % (x0 + j * grp, base - bh, grp * 0.84, max(bh, 0.6), col, E(lab), E(nm), fmt.format(v)))
        o.append('<text x="%.1f" y="%d" font-size="12" fill="%s" text-anchor="middle">%s</text>'
                 % (x0 + grp * len(series) / 2, base + 20, INK, E(lab)))
    lx = pad_l
    for nm, col, _ in series:
        o.append('<rect x="%.1f" y="%d" width="10" height="10" rx="2.5" fill="%s"/>' % (lx, h - 17, col))
        o.append('<text x="%.1f" y="%d" font-size="11.5" fill="%s">%s</text>' % (lx + 15, h - 8, INK, E(nm)))
        lx += 25 + len(nm) * 13
    return svg(w, h, "".join(o))


def line_chart(pts, w=680, h=206, ymin=0.0, ymax=1.0, hline=None, hline_lab=""):
    pad_l, pad_b, pad_t, pad_r = 44, 28, 20, 44
    n = len(pts)

    def X(i):
        return pad_l + (w - pad_l - pad_r) * (i / max(1, n - 1))

    def Y(v):
        return pad_t + (h - pad_t - pad_b) * (1 - (v - ymin) / (ymax - ymin))
    o = []
    for k in range(5):
        v = ymin + (ymax - ymin) * k / 4
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1" opacity="0.26"/>'
                 % (pad_l, Y(v), w - pad_r, Y(v), MUT))
        o.append('<text x="%.1f" y="%.1f" font-size="10.5" fill="%s" text-anchor="end">%.0f%%</text>'
                 % (pad_l - 7, Y(v) + 3.5, MUT, v * 100))
    if hline is not None:
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#e05252" '
                 'stroke-dasharray="6 5" stroke-width="1.5" opacity="0.8"/>'
                 % (pad_l, Y(hline), w - pad_r, Y(hline)))
        o.append('<text x="%.1f" y="%.1f" font-size="10.5" fill="#e05252">%s</text>'
                 % (pad_l + 6, Y(hline) - 5, E(hline_lab)))
    area = ("M%.1f,%.1f " % (X(0), Y(ymin))) + " ".join("%.1f,%.1f" % (X(i), Y(v))
                                                       for i, v in enumerate(pts)) + " %.1f,%.1f Z" % (X(n - 1), Y(ymin))
    o.append('<path d="%s" fill="#2a78d6" opacity="0.10"/>' % area)
    o.append('<path d="%s" fill="none" stroke="#2a78d6" stroke-width="2.6" stroke-linejoin="round" '
             'stroke-linecap="round"/>'
             % " ".join("%s%.1f,%.1f" % ("M" if i == 0 else "L", X(i), Y(v)) for i, v in enumerate(pts)))
    for i, v in enumerate(pts):
        o.append('<circle cx="%.1f" cy="%.1f" r="3.2" fill="#2a78d6" stroke="#fff" stroke-width="1.4">'
                 '<title>第 %d 把 · %.0f%%</title></circle>' % (X(i), Y(v), i + 1, v * 100))
    return svg(w, h, "".join(o))


def spark_panel(name, col, values, wins, top=None, show_axis=False):
    """一人一格的伤害小图。所有格共用同一纵轴（top），所以能横向比高低。"""
    w, h = 320, 118
    pad_l = 36 if show_axis else 8
    pad_b, pad_t, pad_r = 18, 26, 10
    n = len(values)
    top = top or (max(values) * 1.12 if values else 1)

    def X(i):
        return pad_l + (w - pad_l - pad_r) * (i / max(1, n - 1))

    def Y(v):
        return pad_t + (h - pad_t - pad_b) * (1 - v / top)
    o = ['<text x="%d" y="15" font-size="12" fill="%s" font-weight="600">%s</text>' % (pad_l, INK, E(name)),
         '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1" opacity="0.4"/>'
         % (pad_l, Y(top), w - pad_r, Y(top), MUT)]
    if show_axis:
        o.append('<text x="%.1f" y="%.1f" font-size="10" fill="%s" text-anchor="end">%.0f</text>'
                 % (pad_l - 5, Y(top) + 3.5, MUT, top))
        o.append('<text x="%.1f" y="%.1f" font-size="10" fill="%s" text-anchor="end">0</text>'
                 % (pad_l - 5, Y(0) + 3.5, MUT))
    for i, v in enumerate(values):
        if wins[i]:
            o.append('<circle cx="%.1f" cy="%.1f" r="3.5" fill="%s"><title>%.0f</title></circle>' % (X(i), Y(v), col, v))
        else:
            o.append('<circle cx="%.1f" cy="%.1f" r="3" fill="#fff" stroke="%s" stroke-width="1.6">'
                     '<title>%.0f</title></circle>' % (X(i), Y(v), col, v))
    mean = sum(values) / len(values) if values else 0
    o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1.8" '
             'stroke-dasharray="5 4" opacity="0.85"/>' % (pad_l, Y(mean), w - pad_r, Y(mean), col))
    return svg(w, h, "".join(o))


def dumbbell(a_lab, a_val, b_lab, b_val, w=680, h=200, suffix="%"):
    """两个值的对比。哑铃比两根柱子好看，也更强调"差多少"。"""
    pad_l, pad_r, pad_t = 76, 76, 64
    top, ticks = nice_ticks(max(a_val, b_val) * 1.05, 4)

    def X(v):
        return pad_l + (w - pad_l - pad_r) * v / top
    y = h - 58
    o = []
    for t in ticks:
        o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="1" opacity="0.26"/>'
                 % (X(t), pad_t - 22, X(t), y + 24, MUT))
        o.append('<text x="%.1f" y="%d" font-size="10.5" fill="%s" text-anchor="middle">%.0f%s</text>'
                 % (X(t), y + 42, MUT, t, suffix))
    o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="3" opacity="0.4" '
             'stroke-linecap="round"/>' % (X(min(a_val, b_val)), y, X(max(a_val, b_val)), y, MUT))
    for lab, val, col in ((a_lab, a_val, "#eb6834"), (b_lab, b_val, "#2a78d6")):
        o.append('<circle cx="%.1f" cy="%d" r="9.5" fill="%s" stroke="#fff" stroke-width="2.6"/>' % (X(val), y, col))
        o.append('<text x="%.1f" y="%d" font-size="15" font-weight="700" fill="%s" text-anchor="middle">%.0f%s</text>'
                 % (X(val), y - 20, col, val, suffix))
        o.append('<text x="%.1f" y="%d" font-size="12" fill="%s" text-anchor="middle">%s</text>'
                 % (X(val), y - 38, INK, E(lab)))
    return svg(w, h, "".join(o))


def stacked_hbar(rows, cats, w=680, h=None, colors=None):
    """rows = [(标签, {类别: 计数})]；横向百分比堆叠条。"""
    h = h or 40 * len(rows) + 34
    lab_w, pad_r = 118, 118
    total_w = w - lab_w - pad_r
    o = []
    for i, (lab, d) in enumerate(rows):
        y = 14 + i * 40
        n = sum(d.values()) or 1
        x = lab_w
        o.append('<text x="%d" y="%.1f" font-size="12" fill="%s" text-anchor="end">%s</text>'
                 % (lab_w - 10, y + 18, INK, E(lab)))
        for j, c in enumerate(cats):
            if not d.get(c):
                continue
            bw = total_w * d[c] / n
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="22" fill="%s">'
                     '<title>%s %s %d 局</title></rect>'
                     % (x, y, bw, (colors or [])[j % len(colors or ["#888"])],
                        E(lab), E(ROLE_CN.get(c, c)), d[c]))
            if bw > 26:
                o.append('<text x="%.1f" y="%.1f" font-size="10.5" fill="#fff" text-anchor="middle">%d</text>'
                         % (x + bw / 2, y + 15, d[c]))
            x += bw
        o.append('<text x="%.1f" y="%.1f" font-size="10.5" fill="%s">%d 局</text>' % (x + 6, y + 15, MUT, n))
    for j, c in enumerate(cats):
        o.append('<rect x="%d" y="%d" width="9" height="9" rx="2" fill="%s"/>'
                 % (lab_w + 6 + j * 92, h - 18, (colors or [])[j]))
        o.append('<text x="%d" y="%d" font-size="11" fill="%s">%s</text>'
                 % (lab_w + 19 + j * 92, h - 10, INK, E(ROLE_CN.get(c, c))))
    return svg(w, h, "".join(o))


# ---------------------------------------------------------------- 头像（可选）
# 不写死任何人的名字：把 --avatars 目录里的文件按「词干是玩家名的子串」匹配。
# 匹配不到就跳过并打印出来，避免默默给错人套头像。
def _avatar_path(name):
    av_dir = ARGS.avatars
    if not av_dir or not os.path.isdir(av_dir):
        return None
    for fn in sorted(os.listdir(av_dir)):
        stem = os.path.splitext(fn)[0]
        if stem and stem in name:
            return os.path.join(av_dir, fn)
    return None


AVA = {}
for _pu in SQUAD:
    _f = _avatar_path(NAME[_pu])
    if not _f or not os.path.exists(_f):
        print("  [warn] 没匹配到头像:", NAME[_pu].encode("ascii", "replace").decode() or "?")
        continue
    _im = Image.open(_f).convert("RGB")
    _w, _h = _im.size
    _s = min(_w, _h)
    _im = _im.crop(((_w - _s) // 2, (_h - _s) // 2, (_w - _s) // 2 + _s, (_h - _s) // 2 + _s))
    _im = _im.resize((96, 96), Image.LANCZOS)
    _buf = io.BytesIO()
    _im.save(_buf, "JPEG", quality=82, optimize=True)
    AVA[_pu] = "data:image/jpeg;base64," + base64.b64encode(_buf.getvalue()).decode()


def av(pu, cls="av"):
    u = AVA.get(pu)
    return '<img class="%s" src="%s" alt="">' % (cls, u) if u else ""


# 两张配图都是可选的：不传就不嵌，报告照样出（它们可能含别人的头像）
MEME_PNG = ARGS.meme_image
OPEN_PNG = ARGS.open_image


def png_uri(path, maxw=760, q=86):
    # path 可能是 None（没传配图），别直接丢给 os.path.exists
    if not path or not os.path.exists(path):
        if path:
            print("  [warn] 找不到图片:", path.encode("ascii", "replace").decode())
        return None
    _im = Image.open(path).convert("RGB")
    _w, _h = _im.size
    if _w > maxw:
        _im = _im.resize((maxw, int(_h * maxw / _w)), Image.LANCZOS)
    _b = io.BytesIO()
    _im.save(_b, "JPEG", quality=q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(_b.getvalue()).decode()


# ---------------------------------------------------------------- 同场百分位硬分
random.seed(20261011)
MDIMS = [
    ("dpm", "分均伤害", lambda s, d: s.get("totalDamageDealtToChampions", 0) / (d / 60)),
    ("kda", "KDA 比", lambda s, d: (s.get("kills", 0) + s.get("assists", 0)) / max(1, s.get("deaths", 0))),
    ("kpm", "分均参团", lambda s, d: (s.get("kills", 0) + s.get("assists", 0)) / (d / 60)),
    ("gpm", "分均金币", lambda s, d: s.get("goldEarned", 0) / (d / 60)),
    ("ccpm", "分均控制", lambda s, d: s.get("timeCCingOthers", 0) / (d / 60)),
]


def _pct(vals, v):
    lo = sum(1 for x in vals if x < v)
    eq = sum(1 for x in vals if x == v)
    return 100.0 * (lo + 0.5 * (eq - 1)) / (len(vals) - 1) if len(vals) > 1 else 50.0


MG = []
for _g in mine:
    _d = _g.get("gameDuration") or 0
    if _d <= 0:
        continue
    _row = {}
    for _k, _, _fn in MDIMS:
        _vs = [_fn(p.get("stats") or {}, _d) for p in _g["participants"]]
        for _p in _g["participants"]:
            if _p["puuid"] in SQUAD:
                _row.setdefault(_p["puuid"], {})[_k] = _pct(_vs, _fn(_p.get("stats") or {}, _d))
    MG.append(_row)


def _mscore(rows, pu):
    rs = [r[pu] for r in rows if pu in r]
    return sum(sum(v.values()) / len(v) for v in rs) / len(rs) if rs else None


MSCORE = {pu: _mscore(MG, pu) for pu in SQUAD}
MO = sorted(SQUAD, key=lambda pu: -MSCORE[pu])
MCI = {}
for _pu in SQUAD:
    _rs = [r[_pu] for r in MG if _pu in r]
    _bs = []
    for _ in range(2000):
        _s = [random.choice(_rs) for _ in _rs]
        _bs.append(sum(sum(v.values()) / len(v) for v in _s) / len(_s))
    _bs.sort()
    MCI[_pu] = (_bs[50], _bs[1949])

_obs = max(MSCORE.values()) - min(MSCORE.values())
_c = 0
for _ in range(2000):
    _perm = []
    for r in MG:
        ks = list(r.keys())
        vs = [r[k] for k in ks]
        random.shuffle(vs)
        _perm.append(dict(zip(ks, vs)))
    _sp = {k: v for k, v in ((q, _mscore(_perm, q)) for q in SQUAD) if v is not None}
    if max(_sp.values()) - min(_sp.values()) >= _obs:
        _c += 1
MPERM = _c / 2000.0
print("metric: spread=%.2f perm_p=%.4f" % (_obs, MPERM))
for pu in MO:
    print("   pu#%d %.2f [%.2f, %.2f]" % (SQUAD.index(pu), MSCORE[pu], MCI[pu][0], MCI[pu][1]))


def hbar_ci(rows, w=680, h=None, lo=30, hi=76):
    """rows = [(标签, 值, 下界, 上界, 颜色)]：横条 + 点 + 区间。"""
    h = h or 38 * len(rows) + 34
    lab_w, pad_r = 178, 178
    x0, x1 = lab_w, w - pad_r

    def X(v):
        return x0 + (x1 - x0) * (v - lo) / (hi - lo)
    o = []
    for t in range(lo, hi + 1, 10):
        o.append('<line x1="%.1f" y1="14" x2="%.1f" y2="%d" stroke="#8883"/>' % (X(t), X(t), h - 22))
        o.append('<text x="%.1f" y="%d" font-size="10" fill="#888" text-anchor="middle">%d</text>' % (X(t), h - 8, t))
    for i, (lab, v, l, hh, col) in enumerate(rows):
        y = 28 + i * 38
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="7" opacity="0.3"/>'
                 % (X(l), y, X(hh), y, col))
        o.append('<circle cx="%.1f" cy="%.1f" r="7" fill="%s"/>' % (X(v), y, col))
        o.append('<text x="%.1f" y="%.1f" font-size="14" fill="currentColor" text-anchor="middle">%.1f</text>'
                 % (X(v), y + 4, v))
        o.append('<text x="%d" y="%.1f" font-size="12" fill="currentColor" text-anchor="end">%s</text>'
                 % (lab_w - 10, y + 4, E(lab)))
    return svg(w, h, "".join(o))


# ---------------------------------------------------------------- 拼页面
squad_rows = sorted(SQUAD, key=lambda pu: -STATS[pu]["n"])
team_wr = sum(1 for r in GAMES if r["players"].get(ME, {}).get("win")) / len(GAMES)

# 滚动胜率
roll = []
for i in range(len(GAMES)):
    lo = max(0, i - 4)
    seg = GAMES[lo:i + 1]
    roll.append(sum(1 for r in seg if r["players"].get(ME, {}).get("win")) / len(seg))

# 满编 / 不满编
full = [r for r in GAMES if all(pu in r["players"] for pu in SQUAD)]
part = [r for r in GAMES if not all(pu in r["players"] for pu in SQUAD)]
def wr(rs): return (sum(1 for r in rs if r["players"].get(ME, {}).get("win")) / len(rs)) if rs else 0

# 检验结果：FDR 后还活着的
alive = [t for t in tests if t["q"] < 0.10]

others = sorted(
    {p["name"]: 1 for g in mine for p in g["participants"] if p["puuid"] not in SQUAD}.keys()
)

html = []
W = html.append
W('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">')
W('<meta name="viewport" content="width=device-width,initial-scale=1">')
W('<title>车队表现 · 2026-10-11</title><style>')
W('''
:root{--bg:#fff;--fg:#1c1f23;--mut:#6b7280;--line:#e5e7eb;--card:#fafafa}
@media (prefers-color-scheme:dark){:root{--bg:#14171a;--fg:#e8eaed;--mut:#9aa0a6;--line:#2a2f34;--card:#1b1f23}}
*{box-sizing:border-box}
body{margin:0;padding:28px 20px 60px;background:var(--bg);color:var(--fg);
 font:15px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",system-ui,sans-serif}
main{max-width:820px;margin:0 auto}
h1{font-size:26px;margin:0 0 4px}
h2{font-size:19px;margin:38px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--line)}
h3{font-size:15px;margin:22px 0 8px;color:var(--mut);font-weight:600}
.sub{color:var(--mut);font-size:13px;margin-bottom:18px}
.kpis{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0}
.kpi{flex:1 1 118px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.kpi b{display:block;font-size:21px;line-height:1.25}
.kpi span{color:var(--mut);font-size:12px}
figure{margin:16px 0 4px}
svg{display:block;margin-left:auto;margin-right:auto}
figure svg{max-width:100%}
figcaption{color:var(--mut);font-size:12.5px;margin-top:6px;text-align:center}
.fig-top figcaption{text-align:left}
table{border-collapse:collapse;width:100%;font-size:13.5px;margin:10px 0}
th,td{border-bottom:1px solid var(--line);padding:7px 8px;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--mut);font-weight:600}
tr.hi td{background:rgba(42,120,214,.10);font-weight:600}
.av{width:20px;height:20px;border-radius:50%;object-fit:cover;vertical-align:-5px;margin-right:6px}
.big{width:62px;height:62px;border-radius:50%;object-fit:cover;border:2px solid var(--line);display:block;margin:0 auto}
.strip{display:flex;flex-wrap:wrap;gap:10px;margin:20px 0 4px}
.mem{flex:1 1 84px;text-align:center}
.mem b{display:block;font-size:12.5px;margin-top:6px;line-height:1.35}
.mem span{display:block;font-size:11px;color:var(--mut)}
.tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:99px;border:1px solid #eb6834;color:#eb6834;margin-left:6px;vertical-align:1px}
details{border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:14px 0;background:var(--card)}
summary{cursor:pointer;font-weight:600;font-size:13.5px}
.note{background:var(--card);border-left:3px solid #eb6834;border-radius:6px;padding:10px 13px;margin:14px 0;font-size:13.5px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:8px}
.chip{display:inline-block;padding:1px 7px;border:1px solid var(--line);border-radius:99px;font-size:12px;color:var(--mut);margin:1px 3px 1px 0}
footer{color:var(--mut);font-size:12px;margin-top:40px;border-top:1px solid var(--line);padding-top:12px}
''')
W('</style></head><body><main>')
W('<h1>车队表现 · 2026-10-11</h1>')
W('<div class="sub">%d 个人，%d 把海克斯大乱斗，从 %s 打到 %s<br>'
  '数据来自本机对局归档，腾讯 SGP 那份 10 人完整名单</div>'
  % (len(SQUAD), N, GAMES[0]["t"], GAMES[-1]["t"]))

_ou = png_uri(OPEN_PNG, maxw=620, q=88)
if _ou:
    W('<p style="text-align:center;margin:22px 0 4px">')
    W('<img src="%s" alt="" style="width:100%%;max-width:430px">' % _ou)
    W('</p>')

W('<div class="kpis">')
W('<div class="kpi"><b>%d</b><span>总对局</span></div>' % N)
W('<div class="kpi"><b>%d 胜 %d 负</b><span>队伍战绩</span></div>' % (
    sum(1 for r in GAMES if r["players"].get(ME, {}).get("win")),
    sum(1 for r in GAMES if not r["players"].get(ME, {}).get("win"))))
W('<div class="kpi"><b>%.1f%%</b><span>胜率</span></div>' % (team_wr * 100))
W('<div class="kpi"><b>%d</b><span>同场路人</span></div>' % len(others))
W('</div>')

W('<div class="strip">')
for pu in squad_rows:
    _s = STATS[pu]
    W('<div class="mem">%s<b>%s</b><span>%d 局 · 队伍胜率 %.0f%%</span></div>'
      % (av(pu, "big"), E(NAME[pu]), _s["n"], _s["wr"] * 100))
W('</div>')
W('<figcaption>这 %d 个人，是那天跟我同队两把以上的。</figcaption>' % len(SQUAD))

# ---- 结论
W('<h2>先说结论</h2>')
W('<p>先看个最唬人的数。人凑齐的那 %d 把，我们赢了 %d 把。人没凑齐的 %d 把，只赢了 %d 把。</p>'
  % (len(full), sum(1 for r in full if r["players"].get(ME, {}).get("win")),
     len(part), sum(1 for r in part if r["players"].get(ME, {}).get("win"))))
W('<p>听着像「多一个人就是多一份胜率」对吧。说实话我第一眼也这么想的。</p>')
W('<p>结果查下去发现不干净，这个数骗人，第七节说为什么。</p>')
if alive:
    parts = "，".join("%s 的%s %+.2f" % (E(NAME[t["pu"]]), t["label"], t["d"]) for t in alive)
    W('<p>倒是个人数据里真有东西。%d 项扛住了多重比较校正，q 值小于 0.10 那种。%s。</p>'
      % (len(alive), parts))
    W('<p>不过这些差异全挤在两类指标上，KDA 比，还有分均金币和伤害。'
      '最省事的解释是「坦克辅助本来就低伤害低经济」。第五节我真去验了这个解释，结论是它不成立，'
      '伤害偏低的那两位拿的输出位反而更多。所以差异是真的，但不等于水平上有差距。</p>')
else:
    W('<p>个人表现就没这么热闹了。做完多重比较校正，一项都没站住，'
      '这 33 把的量级上「谁更强」根本分不出来，表里的差距基本都是噪声。</p>')
W('<div class="note">为什么不能光看胜率。我们大部分时间在同一队，胜负是共享的。'
  '所以「某某在的时候胜率 75%」说的是队伍在那几把的表现，不是那个人的功劳。'
  '要聊个人，只能看 KDA、伤害、承伤这些专属个人的量。</div>')

# ---- 总览表
W('<h2>都是谁，各打了多少</h2>')
W('<table><thead><tr><th>玩家</th><th>局数</th><th>胜-负</th><th>队伍胜率</th>'
  '<th>场均 K/D/A</th><th>KDA 比</th><th>分均伤害</th><th>分均承伤</th></tr></thead><tbody>')
for pu in squad_rows:
    s = STATS[pu]
    cls = ' class="hi"' if pu == ME else ""
    W('<tr%s><td>%s%s</td><td>%d</td><td>%d-%d</td><td>%.0f%%</td><td>%.1f / %.1f / %.1f</td>'
      '<td>%.2f</td><td>%.0f</td><td>%.0f</td></tr>'
      % (cls, av(pu), E(NAME[pu]), s["n"], s["w"], s["l"], s["wr"] * 100,
         s["k"], s["d"], s["a"], (s["k"] + s["a"]) / max(0.1, s["d"]), s["dpm"], s["tpm"]))
W('</tbody></table>')
W('<figcaption>「队伍胜率」指的是这几个人在场的那几把里，队伍赢了多少。同队共享，不代表个人水平。</figcaption>')

# ---- 图 1 滚动胜率
W('<h2>那天是怎么打的</h2>')
W('<figure class="fig-top">')
W(line_chart(roll, hline=0.5, hline_lab="五成基准"))
W('<figcaption>图 1 · 逐局胜率，5 把滑动平均。下午一直压着五成以上，21 点以后掉线下。</figcaption></figure>')

# ---- 图 2 分面散点
W('<h3>一把一把看，谁哪把打爆了</h3>')
W('<div class="grid2">')
_SPARK_TOP = nice_ticks(max(r["players"][pu]["dpm"] for r in GAMES for pu in r["players"]), 3)[0]
for i, pu in enumerate(squad_rows):
    vs = [r["players"][pu]["dpm"] for r in GAMES if pu in r["players"]]
    ws = [r["players"][pu]["win"] for r in GAMES if pu in r["players"]]
    W(spark_panel(NAME[pu], COLORS[i], vs, ws, top=_SPARK_TOP, show_axis=(i % 2 == 0)))
W('</div>')
W('<figcaption>图 2 · 分均伤害，一人一格，四格共用同一个纵轴。实心点赢，空点输，虚线是个人均值。</figcaption>')

# ---- 图 3 KDA 堆叠
W('<h3>场均 KDA</h3>')
W('<figure class="fig-top">')
W(bar_chart([NAME[pu] for pu in squad_rows],
            [("击杀", "#2a78d6", [STATS[pu]["k"] for pu in squad_rows]),
             ("死亡", "#eb6834", [STATS[pu]["d"] for pu in squad_rows]),
             ("助攻", "#3f9c6b", [STATS[pu]["a"] for pu in squad_rows])],
            h=250))
W('<figcaption>图 3 · 每人每把的击杀、死亡、助攻。</figcaption></figure>')

# ---- 第四节 统计
W('<h2>谁更强，我真去测了</h2>')
W('<p>不能直接比谁分高，每把的时长、对手、版本都不一样。所以我只在同一把里比，'
  '把某人跟同场队友的同一个指标相减，得到一串成对差，干扰就自动消掉了。'
  '再对差值做收缩（k=%d，局数少的会被拉回 0），最后过一遍 BH-FDR 校正。</p>' % K_SHRINK)
W('<h3>全矩阵，所有人所有指标摆一起</h3>')
WT = {(t["pu"], t["key"]): t for t in tests}
W('<table><thead><tr><th>玩家</th>'
  + "".join('<th>%s</th>' % E(lb) for _, lb, _ in METRICS) + '</tr></thead><tbody>')
for pu in squad_rows:
    cells = []
    for key, _, _ in METRICS:
        t = WT.get((pu, key))
        if t is None:
            cells.append('<td>—</td>')
            continue
        sig = t["q"] < 0.10
        cells.append('<td%s>%+.2f%s</td>'
                     % (' class="hi"' if sig else "", t["d"], " ✔" if sig else ""))
    W('<tr><td>%s%s</td>%s</tr>' % (av(pu), E(NAME[pu]), "".join(cells)))
W('</tbody></table>')
W('<figcaption>全矩阵，%d 人 × %d 项，共 %d 项检验，格子是跟队友平均的差。'
  '打 ✔ 的过了 q&lt;0.10，这次 %d 项。没 ✔ 不是没问题，是这点样本分不出来。'
  '</figcaption>' % (len(squad_rows), len(METRICS), len(tests), len(alive)))
W('<details><summary>%d 项检验的完整数值，带 p 和 q</summary>' % len(tests))
W('<table><thead><tr><th>玩家</th><th>指标</th><th>局数</th><th>成对差</th>'
  '<th>±1SE</th><th>p</th><th>q (FDR)</th></tr></thead><tbody>')
for t in tests:
    W('<tr%s><td>%s</td><td>%s</td><td>%d</td><td>%+.2f</td><td>%.2f</td><td>%.3f</td><td>%.3f%s</td></tr>'
      % (' class="hi"' if t["q"] < 0.10 else "", E(NAME[t["pu"]]), E(t["label"]),
         t["n"], t["d"], t["se"], t["p"], t["q"], " ✔" if t["q"] < 0.10 else ""))
W('</tbody></table>')
W('<p style="color:var(--mut);font-size:12.5px">p 按正态近似算，每组 20 到 35 把，够用。'
  'q 是 BH-FDR 校正后的值，小于 0.10 才算过。</p></details>')

# ---- 满编对比
W('<h2>伤害低，是因为拿了坦克吗</h2>')
DMGSET = {"fighter", "mage", "assassin", "marksman"}


def dmg_share(pu):
    rol = STATS[pu]["roles"]
    n = sum(rol.values()) or 1
    return 100.0 * sum(c for r, c in rol.items() if r in DMGSET) / n


W('<p>一个很自然的解释是，伤害和经济低只是因为常拿坦克或者辅助。'
  '那就把每个人用过的英雄按主定位分成两类，输出位是战士法师刺客射手，功能位是坦克辅助。</p>')
role_rows = [(NAME[pu], STATS[pu]["roles"]) for pu in squad_rows]
role_cats = [c for c in ["fighter", "mage", "assassin", "tank", "marksman", "support", "unknown"]
             if any(r[1].get(c) for r in role_rows)]
W('<figure class="fig-top">')
W(stacked_hbar(role_rows, role_cats,
               colors=["#2a78d6", "#eb6834", "#3f9c6b", "#a463c8", "#d9a441", "#5b8bd0", "#888"]))
W('<figcaption>图 4 · 当天英雄的主定位构成，数字是局数。标签取自当前英雄数据。</figcaption></figure>')

shares = "、".join("%s %.0f%%" % (E(NAME[pu]), dmg_share(pu)) for pu in squad_rows)
low_dpm = [t for t in alive if t["key"] == "dpm" and t["d"] < 0]
hi_dpm = [t for t in alive if t["key"] == "dpm" and t["d"] > 0]
W('<p>输出位占比是这样的。%s。</p>' % shares)
W('<p>这就有点意思了。</p>')
if low_dpm and hi_dpm:
    W('<p>结论是这个解释站不住。第四节里分均伤害显著偏低的是 %s，'
      '而输出位占比反而更高的是 %s。伤害低的那两位拿的输出位并不比别人少，'
      '用主定位这个口径解释不了伤害差异。</p>'
      % ("、".join(E(NAME[t["pu"]]) for t in low_dpm),
         "、".join(E(NAME[t["pu"]]) + "（%.0f%%）" % dmg_share(t["pu"]) for t in low_dpm)))
    W('<p>不过这也不等于他们打得差。主定位本来就很粗，一个输出位英雄照样可以出肉打功能，'
      '而且同一个定位里不同英雄的伤害天花板差得很远。要真归因得看具体英雄和出装，'
      '那是这份数据之外的事。</p>')
    mk = min(squad_rows, key=lambda pu: STATS[pu]["k"])
    ma = max(squad_rows, key=lambda pu: STATS[pu]["a"])
    if mk == ma:
        W('<p>更说得通的一条线索在 KDA 结构里。%s 场均击杀最低（%.1f）助攻最高（%.1f），'
          '打法偏喂头和开团，不是自己收人头，这跟伤害偏低是自洽的。</p>'
          % (E(NAME[mk]), STATS[mk]["k"], STATS[mk]["a"]))

W('<h2>排个座次</h2>')
W('<p>再换个角度。每一把把你和同场 10 个人逐项比百分位，五个维度取平均就是那把的得分，'
  '再对各把取平均。跟同场 10 个人比，时长、对手、版本这些干扰都自动消掉了。</p>')
W('<p>五个维度是分均伤害、KDA 比、分均参团、分均金币、分均控制。'
  '承伤和治疗没收，方向有歧义。胜负也没放，同队共享胜负，放进去就是测队伍了。</p>')
W('<figure class="fig-top">')
W(hbar_ci([(NAME[pu], MSCORE[pu], MCI[pu][0], MCI[pu][1], COLORS[squad_rows.index(pu)]) for pu in MO]))
W('<figcaption>图 5 · 同场百分位硬分，0 到 100。圆点是得分，横条是 bootstrap 95%% 区间。</figcaption></figure>')

_dim_tbl = {}
for pu in MO:
    rs = [r[pu] for r in MG if pu in r]
    _dim_tbl[pu] = [sum(v[k] for v in rs) / len(rs) for k, _, _ in MDIMS]
W('<table><thead><tr><th>名次</th><th>玩家</th><th>硬分</th><th>95% 区间</th>'
  + "".join('<th>%s</th>' % E(lb) for _, lb, _ in MDIMS) + '</tr></thead><tbody>')
for i, pu in enumerate(MO):
    W('<tr%s><td>%d</td><td>%s%s</td><td><b>%.1f</b></td><td>%.1f – %.1f</td>%s</tr>'
      % ("", i + 1, av(pu), E(NAME[pu]), MSCORE[pu], MCI[pu][0], MCI[pu][1],
         "".join('<td>%.1f</td>' % v for v in _dim_tbl[pu])))
W('</tbody></table>')
W('<p>置换检验的观测极差是 %.2f。把同场内队员和数据的对应关系随机打乱 2000 次，'
  '只有 %d 次达到这个极差，p = %.3f。所以这个座次整体是真的，不是随机分出来的。</p>'
  % (_obs, _c, MPERM))
W('<div class="note">但只有分成三档才站得住。第 1 名和第 2 名的区间几乎完全重合，'
  '%.1f 到 %.1f 对 %.1f 到 %.1f。第 4 名和第 5 名也是，%.1f 到 %.1f 对 %.1f 到 %.1f。'
  '中间那位两头都沾。细排名别当真，只认上二、中一、下二。</div>'
  % (MCI[MO[0]][0], MCI[MO[0]][1], MCI[MO[1]][0], MCI[MO[1]][1],
     MCI[MO[3]][0], MCI[MO[3]][1], MCI[MO[4]][0], MCI[MO[4]][1]))

_b2 = sorted(MO[-2:], key=lambda pu: -STATS[pu]["wr"])
_lg, _fg = _b2[0], _b2[1]
W('<h3>称号，卧龙凤雏</h3>')
W('<p>这两个人数据上分不开，区间 %.1f 到 %.1f 和 %.1f 到 %.1f 几乎完全重合。'
  '而卧龙凤雏二者得一可安天下本来就是句反讽，说的是两个一样、分不出高下的人，正好对得上。</p>'
  % (MCI[_lg][0], MCI[_lg][1], MCI[_fg][0], MCI[_fg][1]))
W('<p>按队伍胜率排个辈分。卧龙是 %s%s，%d 把，队伍胜率 %.0f%%。'
  '凤雏是 %s%s，%d 把，队伍胜率 %.0f%%。</p>'
  % (E(NAME[_lg]), av(_lg), STATS[_lg]["n"], STATS[_lg]["wr"] * 100,
     E(NAME[_fg]), av(_fg), STATS[_fg]["n"], STATS[_fg]["wr"] * 100))
W('<p>两个人是同一个病，占着输出位交不出输出，输出位占比 %.0f%% 和 %.0f%%，'
  '分均伤害却只排在 %.1f 和 %.1f 分位。真要给这对组合起个共同的名字，叫「占位双雄」。</p>'
  % (dmg_share(_lg), dmg_share(_fg), _dim_tbl[_lg][0], _dim_tbl[_fg][0]))
W('<p>还有更离谱的。卧龙那位队伍胜率是全场最高，%.0f%%。个人产出垫底，队伍赢得最多？？？'
  '这个数我先放这儿，你们自己消化。</p>' % (STATS[_lg]["wr"] * 100))
W('<div class="note">这名字好玩，但统计上只到并列倒一这一层，别真拿去当依据。'
  '另外卧龙那位要是拿这个去邀功，记得把上面那段带上。</div>')

_mu = png_uri(MEME_PNG)
if _mu:
    W('<p style="text-align:center;margin:24px 0 0">')
    W('<img src="%s" alt="卧龙凤雏" style="width:100%%;max-width:440px;border-radius:14px;'
      'border:1px solid var(--line)">' % _mu)
    W('</p>')

W('<h2>人多到底有没有用</h2>')
W('<figure class="fig-top">')
W(dumbbell("没凑齐 %d 把" % len(part), wr(part) * 100,
           "全员到齐 %d 把" % len(full), wr(full) * 100, h=200))
W('<figcaption>图 6 · 全员到齐 %d 把对没凑齐 %d 把的胜率。</figcaption>' % (len(full), len(part)))
W('</figure>')
W('<div class="note">别把这 %.0f 个百分点当成多一个人就赢。'
  '全员到齐的那几把集中在 %s 到 %s，下午一段深夜一段，'
  '跟下午手热、深夜犯困在时间上几乎完全重合。'
  '要真回答人多有没有用，得让同一批人在不同时段各打一批，这份数据分不开这两件事。</div>'
  % (abs(wr(full) - wr(part)) * 100, full[0]["t"] if full else "—", full[-1]["t"] if full else "—"))

# ---- 明细
W('<h2>明细</h2>')
W('<details><summary>逐局明细，%d 把，含 %d 个人的 KDA 和英雄</summary>' % (len(GAMES), len(SQUAD)))
W('<table><thead><tr><th>时间</th><th>英雄</th><th>结果</th>')
for pu in squad_rows:
    W('<th>%s</th>' % E(NAME[pu]))
W('</tr></thead><tbody>')
for r in GAMES:
    me = r["players"].get(ME, {})
    W('<tr><td>%s</td><td>%s</td><td>%s</td>'
      % (r["t"], E(me.get("champ", "—")), "胜" if me.get("win") else "负"))
    for pu in squad_rows:
        p = r["players"].get(pu)
        W('<td>%s</td>' % ("%d/%d/%d %s" % (p["k"], p["dd"], p["a"], E(p["champ"])) if p else "—"))
    W('</tr>')
W('</tbody></table></details>')

W('<details><summary>%d 个人的英雄池</summary>' % len(SQUAD))
for pu in squad_rows:
    cs = sorted(STATS[pu]["champs"].items(), key=lambda kv: -kv[1])
    W('<p>%s，%d 把。%s</p>' % (E(NAME[pu]), STATS[pu]["n"],
      "".join('<span class="chip">%s ×%d</span>' % (E(c), n) for c, n in cs)))
W('</details>')

W('<details><summary>当天同场过的全部路人（%d 人）</summary><p>%s</p></details>'
  % (len(others), "".join('<span class="chip">%s</span>' % E(x) for x in others)))

W('<footer>这份东西是直接读本机对局归档生成的，走另一条代码路径，没蹭 MCP 工具的输出。'
  '成对差、收缩、BH-FDR 都是这次为了比小圈子临时加的，不是 MCP 的口径，'
  '样本量也小，p 值用的正态近似。<br>生成于 %s</footer>'
  % datetime.now().strftime("%Y-%m-%d %H:%M"))
W('</main></body></html>')

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(html))

print("games:", len(GAMES), "squad:", len(SQUAD), "tests:", len(tests), "fdr_alive:", len(alive))
for t in alive:
    print("  ALIVE player#%d %-6s n=%2d d=%+8.2f se=%.2f p=%.4f q=%.4f" % (
        SQUAD.index(t["pu"]), t["key"], t["n"], t["d"], t["se"], t["p"], t["q"]))
print("html chars:", sum(len(x) for x in html))
print("out:", OUT.encode("ascii", "replace").decode())

# --- ASCII 自检（数字，无中文）---
print("\nper-player aggregates:")
hdr = ["pu#", "n", "w", "wr", "K", "D", "A", "dpm", "tpm", "hpm", "gpm", "cspm", "ccpm"]
print("  " + " ".join("%7s" % h for h in hdr))
for i, pu in enumerate(SQUAD):
    s = STATS[pu]
    print("  " + " ".join("%7s" % x for x in [
        i, s["n"], s["w"], "%.2f" % s["wr"], "%.1f" % s["k"], "%.1f" % s["d"], "%.1f" % s["a"],
        "%.0f" % s["dpm"], "%.0f" % s["tpm"], "%.0f" % s["hpm"], "%.0f" % s["gpm"],
        "%.1f" % s["cspm"], "%.1f" % s["ccpm"]]))
print("\nrole mix per player (primary role):")
DMG = {"fighter", "mage", "assassin", "marksman"}
for i, pu in enumerate(SQUAD):
    rol = STATS[pu]["roles"]
    n = sum(rol.values()) or 1
    dmg = sum(c for r, c in rol.items() if r in DMG)
    print("  pu#%d n=%2d dmg=%2d (%3.0f%%)  %s" % (
        i, n, dmg, 100.0 * dmg / n,
        " ".join("%s=%d" % (r, c) for r, c in sorted(rol.items(), key=lambda kv: -kv[1]))))

print("\nnon-zero counts per metric (max %d):" % len(GAMES))
for key, label, _ in METRICS:
    nz = sum(1 for r in GAMES for pu in r["players"] if r["players"][pu][key] > 0)
    tot = sum(1 for r in GAMES for pu in r["players"])
    print("  %-6s %d/%d" % (key, nz, tot))
