# Second-screen service: MJPEG desktop mirror + a PhoneBox-style dashboard panel.
# Runs headless (pythonw) and is started at logon by the HKCU Run key "SecondScreen".
import base64
import hashlib
import hmac
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote as _urlquote

import mss
from PIL import Image, ImageDraw, ImageFont

try:
    import psutil
except Exception:
    psutil = None

PORT = 8080
QUALITY = 55
TARGET_FPS = 30
SCALE_WIDTH = 1280

_lock = threading.Lock()
_frame = {"jpeg": b"", "n": 0, "w": 0, "h": 0}
_fps = {"count": 0, "value": 0.0}
_hist = {"cpu": [], "mem": []}
_stats = {"ping": -1}
_processes = {"top": []}
_quota = {
    "deepseek": {"ok": False, "note": "未检测"},
    "newapi":   {"ok": False, "note": "未检测"},
    "minimax":  {"ok": False, "note": "官方无余额接口"},
    "dashscope": {"ok": False, "note": "无余额接口"},
    "aliyun": {"ok": False, "note": "未检测"},
}
_panel = {"jpeg": b"", "t": 0}
_eink = {"png": b"", "t": 0}
_clients = {}          # ip -> last seen timestamp (who has requested the panel)
_wake = {"result": None, "t": 0}   # Screen Wake Lock report from the phone page

# DeepSeek has no usage API: we snapshot the balance and turn decreases into daily spend.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USAGE_FILE = os.environ.get("USAGE_FILE", os.path.join(BASE_DIR, "data", "deepseek_usage.json"))
_usage = {"daily": {}, "last": None}


def _load_usage():
    try:
        j = json.load(open(USAGE_FILE, encoding="utf-8"))
        _usage["daily"] = j.get("daily") or {}
        _usage["last"] = j.get("last")
    except Exception:
        pass


def _save_usage():
    try:
        os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump({"daily": _usage["daily"], "last": _usage["last"]}, f)
    except Exception:
        pass


def _record_balance(bal):
    try:
        cur = float(bal)
    except Exception:
        return
    today = date.today().isoformat()
    last = _usage.get("last")
    if last is not None:
        delta = round(float(last) - cur, 4)
        if 0 < delta < 100:          # only decreases; a jump upward means a top-up
            _usage["daily"][today] = round(_usage["daily"].get(today, 0) + delta, 4)
    _usage["last"] = cur
    _save_usage()


def _usage_summary():
    today = date.today()
    week = 0.0
    month = 0.0
    for k, v in _usage["daily"].items():
        try:
            d = date.fromisoformat(k)
        except Exception:
            continue
        if (today - d).days < 7:
            week += v
        if k[:7] == today.strftime("%Y-%m"):
            month += v
    return round(week, 2), round(month, 2)


# ---------- panel renderer (drawn as an image: immune to browser zoom) ----------
_ICONS = {}


def _make_icon(bg, glyph, fg=(255, 255, 255)):
    """64x64 rounded-square icon with a single glyph, used as the page favicon."""
    if bg in _ICONS:
        return _ICONS[bg]
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 61, 61), radius=15, fill=bg)
    try:
        f = _font(38, True)
        d.text((32, 33), glyph, font=f, fill=fg, anchor="mm")
    except Exception:
        pass
    buf = io.BytesIO()
    img.save(buf, "PNG")
    _ICONS[bg] = buf.getvalue()
    return _ICONS[bg]


def _font(size, bold=False):
    for name in (("msyhbd.ttc", "msyh.ttc") if bold else ("msyh.ttc", "simhei.ttf")):
        try:
            return ImageFont.truetype("C:/Windows/Fonts/" + name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _card(d, box, bg=(20, 24, 33), line=(35, 42, 55), r=26):
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, radius=r, fill=bg, outline=line, width=2)


def _spark(d, box, arr, color=(108, 201, 255), mx=100):
    x0, y0, x1, y1 = box
    n = len(arr)
    if n < 2:
        return
    pts = []
    for i, v in enumerate(arr):
        x = x0 + (x1 - x0) * i / (n - 1)
        y = y1 - (y1 - y0) * min(v, mx) / mx
        pts.append((x, y))
    d.line(pts, fill=color, width=4)


def gpu_loop():
    exe = os.environ.get("NVIDIA_SMI", "nvidia-smi.exe")
    while True:
        try:
            out = subprocess.run([exe, "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                                  "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=6,
                                 creationflags=0x08000000).stdout.strip()
            if out:
                parts = [p.strip() for p in out.split(",")]
                _stats["gpu"] = {"util": int(float(parts[0])), "mem_used": int(float(parts[1])),
                                 "mem_total": int(float(parts[2])), "temp": int(float(parts[3]))}
        except Exception:
            pass
        time.sleep(3)


def render_panel2():
    W, H = 2400, 1080
    img = Image.new("RGB", (W, H), (10, 12, 16))
    d = ImageDraw.Draw(img)
    P = 34

    f_lbl = _font(30)
    f_big = _font(88, True)
    f_mid = _font(56, True)
    f_small = _font(28)
    f_clock = _font(150, True)

    q = dict(_quota)
    s = dict(_stats)
    with _lock:
        hc = list(_hist["cpu"])
        hm = list(_hist["mem"])

    # ---- time card
    _card(d, (P, P, W - P, P + 300))
    d.text((P + 40, P + 34), "SYSTEM TIME", font=f_lbl, fill=(139, 151, 171))
    d.text((P + 40, P + 80), s.get("time", "--:--"), font=f_clock, fill=(232, 237, 246))
    d.text((P + 44, P + 240), s.get("date", ""), font=f_small, fill=(139, 151, 171))
    d.text((W - P - 40, P + 40), "0d %dh 在线" % (s.get("uptime", 0) // 60), font=f_small,
           fill=(120, 200, 140), anchor="ra")
    d.text((W - P - 40, P + 84), "ping %s" % ("%d ms" % s["ping"] if s.get("ping", -1) > 0 else "超时"),
           font=f_small, fill=(139, 151, 171), anchor="ra")

    # ---- four metric cards
    cw = (W - P * 2 - 36 * 3) // 4
    y = P + 300 + 24
    h2 = 380
    labels = [("CPU", str(s.get("cpu", 0)), "%"), ("MEMORY", str(s.get("mem", 0)), "%"),
              ("NETWORK", str(s.get("net_dn", 0)), "KB/s"), ("DISK", "", "")]
    for i, (lbl, val, unit) in enumerate(labels):
        x = P + i * (cw + 36)
        _card(d, (x, y, x + cw, y + h2))
        d.text((x + 26, y + 22), lbl, font=f_lbl, fill=(139, 151, 171))
        if i < 3:
            d.text((x + 26, y + 70), val, font=f_big, fill=(232, 237, 246))
            d.text((x + 26 + d.textlength(val, font=f_big), y + 120), unit, font=f_small, fill=(139, 151, 171))
        if i == 1:
            d.text((x + 26, y + 180), "%s / %s GB" % (s.get("mem_used", 0), s.get("mem_total", 0)),
                   font=f_small, fill=(139, 151, 171))
        if i == 2:
            d.text((x + 26, y + 180), "%d KB/s ↑" % s.get("net_up", 0), font=f_small, fill=(139, 151, 171))
        if i == 3:
            yy = y + 80
            for k, v in (s.get("disks") or {}).items():
                d.text((x + 26, yy), "%s  %d%%" % (k, v["pct"]), font=f_mid, fill=(232, 237, 246))
                d.text((x + 26, yy + 66), "剩 %s G" % v["free"], font=f_small, fill=(139, 151, 171))
                yy += 130
    _spark(d, (P + 40, y + 250, P + 40 + cw - 80, y + 340), hc)
    _spark(d, (P + (cw + 36) + 40, y + 250, P + (cw + 36) + cw - 80, y + 340), hm, (255, 196, 107))

    # ---- quota card (bottom-left) + processes (bottom-right)
    y3 = y + h2 + 24
    h3 = H - P - y3
    half = (W - P * 2 - 36) // 2
    _card(d, (P, y3, P + half, y3 + h3))
    d.text((P + 26, y3 + 18), "API 额度", font=f_lbl, fill=(139, 151, 171))
    yy = y3 + 66
    rows = [("DeepSeek", q.get("deepseek")), ("NewAPI 中转", q.get("newapi")),
            ("MiniMax", q.get("minimax")), ("阿里百炼", q.get("dashscope"))]
    for name, item in rows:
        item = item or {}
        if item.get("ok"):
            if name.startswith("DeepSeek"):
                txt = "%s 元" % item.get("value", "?")
            else:
                txt = ("已用 $%s" % item["used"]) if item.get("used") is not None else "额度未设上限"
        else:
            txt = item.get("note", "—")
        d.text((P + 26, yy), name, font=f_small, fill=(232, 237, 246))
        d.text((P + half - 26, yy), txt, font=f_small, fill=(108, 201, 255), anchor="ra")
        yy += 50

    _card(d, (P + half + 36, y3, W - P, y3 + h3))
    d.text((P + half + 62, y3 + 18), "TOP PROCESSES", font=f_lbl, fill=(139, 151, 171))
    yy = y3 + 66
    for p in (_processes.get("top") or [])[:5]:
        d.text((P + half + 62, yy), p["name"], font=f_small, fill=(232, 237, 246))
        d.text((W - P - 26, yy), "%s%%" % p["cpu"], font=f_small, fill=(108, 201, 255), anchor="ra")
        yy += 50

    out = img.rotate(-90, expand=True)          # 2400x1080 -> 1080x2400
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=82)
    _panel["jpeg"] = buf.getvalue()
    _panel["t"] = time.time()


def render_panel():
    """New layout: small clock strip, five big metric cards, small quota + process rows."""
    W, H = 2400, 1080
    img = Image.new("RGB", (W, H), (10, 12, 16))
    d = ImageDraw.Draw(img)
    P, GAP = 30, 22

    f_lbl = _font(46)
    f_big = _font(126, True)
    f_unit = _font(38)
    f_sub = _font(30)
    f_clock = _font(70, True)
    f_title = _font(34)
    f_row = _font(34)
    f_api_t = _font(38)
    f_api = _font(42)
    f_proc_t = _font(26)
    f_proc = _font(27)

    q = dict(_quota)
    s = dict(_stats)
    with _lock:
        hc = list(_hist["cpu"])
        hm = list(_hist["mem"])

    # ---------- header strip (small) ----------
    d.text((P + 4, P + 4), s.get("time", "--:--"), font=f_clock, fill=(232, 237, 246))
    tw = d.textlength(s.get("time", "--:--"), font=f_clock)
    d.text((P + tw + 22, P + 42), s.get("date", ""), font=f_sub, fill=(139, 151, 171))
    d.text((W - P - 4, P + 14), "0d %dh 在线   ping %s" %
           (s.get("uptime", 0) // 60, ("%d ms" % s["ping"]) if s.get("ping", -1) > 0 else "超时"),
           font=f_sub, fill=(139, 151, 171), anchor="ra")

    # ---------- five big cards ----------
    top = 150
    ch = 570
    cw = (W - P * 2 - GAP * 4) // 5
    gpu = s.get("gpu") or {}
    disks = s.get("disks") or {}
    c_pct = disks.get("C:", {}).get("pct", 0)
    c_free = disks.get("C:", {}).get("free", 0)
    d_pct = disks.get("D:", {}).get("pct", 0)
    d_free = disks.get("D:", {}).get("free", 0)

    cards = [
        ("CPU", "%d" % s.get("cpu", 0), "%", None),
        ("GPU", "%d" % gpu.get("util", 0), "%",
         ("显存 %d / %d MB" % (gpu.get("mem_used", 0), gpu.get("mem_total", 0))) if gpu else "未检测到 NVIDIA"),
        ("运行内存", "%d" % s.get("mem", 0), "%",
         "%s / %s GB" % (s.get("mem_used", 0), s.get("mem_total", 0))),
        ("空间", "%d" % d_pct, "%", "D 剩 %s G" % d_free),
        ("网络", "%d" % s.get("net_dn", 0), "KB/s", "↑ %d KB/s" % s.get("net_up", 0)),
    ]

    for i, (lbl, val, unit, sub) in enumerate(cards):
        x = P + i * (cw + GAP)
        _card(d, (x, top, x + cw, top + ch), r=24)
        d.text((x + 24, top + 20), lbl, font=f_lbl, fill=(139, 151, 171))
        d.text((x + 24, top + 70), val, font=f_big, fill=(232, 237, 246))
        vw = d.textlength(val, font=f_big)
        d.text((x + 24 + vw + 8, top + 148), unit, font=f_unit, fill=(139, 151, 171))
        yy = top + 250
        if sub:
            d.text((x + 24, yy), sub, font=f_sub, fill=(139, 151, 171))
            yy += 40
        if i == 0:
            _spark(d, (x + 30, top + 380, x + cw - 30, top + 500), hc)
        if i == 2:
            _spark(d, (x + 30, top + 380, x + cw - 30, top + 500), hm, (255, 196, 107))
        if i == 3:
            d.text((x + 24, yy), "C %d%% · 剩 %s G" % (c_pct, c_free), font=f_sub, fill=(255, 120, 120))
        if i == 1 and gpu:
            d.text((x + 24, yy), "%d °C" % gpu.get("temp", 0), font=f_sub, fill=(139, 151, 171))

    # ---------- bottom: quota (left) + processes (right) ----------
    y2 = top + ch + 22
    h2 = H - P - y2
    qw = 1500
    _card(d, (P, y2, P + qw, y2 + h2), r=22)
    d.text((P + 24, y2 + 10), "API 额度", font=f_api_t, fill=(139, 151, 171))
    yy = y2 + 56
    rows = [("DeepSeek", q.get("deepseek")), ("NewAPI 中转", q.get("newapi")),
            ("302.AI", q.get("ai302")), ("MiniMax", q.get("minimax")),
            ("阿里云余额", q.get("aliyun"))]
    wk, mo = _usage_summary()
    for name, item in rows:
        item = item or {}
        if item.get("ok"):
            if item.get("value") is not None:
                if item.get("unit") == "CNY":
                    txt = "%s 元" % item["value"]
                elif item.get("unit") == "USD":
                    txt = "$%s" % item["value"]
                else:
                    txt = "%s %s" % (item["value"], item.get("unit") or "")
            else:
                used = item.get("used")
                lim = item.get("limit")
                if used is None:
                    txt = "额度未设上限"
                elif lim and lim < 1e7:
                    txt = "已用 $%s / 上限 $%s" % (used, lim)
                else:
                    txt = "已用 $%s" % used
        else:
            txt = item.get("note", "—")
        d.text((P + 24, yy), name, font=f_api, fill=(232, 237, 246))
        d.text((P + qw - 24, yy), txt, font=f_api, fill=(108, 201, 255), anchor="ra")
        yy += 48

    px = P + qw + GAP
    _card(d, (px, y2, W - P, y2 + h2), r=22)
    d.text((px + 24, y2 + 14), "TOP 进程", font=f_proc_t, fill=(139, 151, 171))
    yy = y2 + 54
    for p in (_processes.get("top") or [])[:5]:
        d.text((px + 24, yy), p["name"], font=f_proc, fill=(200, 208, 220))
        d.text((W - P - 24, yy), "%s%%" % p["cpu"], font=f_proc, fill=(108, 201, 255), anchor="ra")
        yy += 38

    out = img.rotate(-90, expand=True)
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=82)
    _panel["jpeg"] = buf.getvalue()
    _panel["t"] = time.time()


def panel_loop():
    while True:
        try:
            render_panel()
        except Exception:
            pass
        time.sleep(1)



# ---------- api quota ----------
def _read_keys():
    keys = {}
    try:
        txt = open(os.environ.get("DSH_ENV_FILE", os.path.expanduser("~/.dsh/.env")), encoding="utf-8", errors="replace").read()
        m = re.search(r"NEWAPI_DEEPSEEK_API_KEY=([^\r\n]+)", txt)
        if m:
            keys["newapi"] = m.group(1).strip().strip('"').strip("'")
    except Exception:
        pass
    try:
        cfg = json.load(open(os.environ.get("WEFLOW_CONFIG", os.path.expanduser("~/.weflow-cli/config.json")), encoding="utf-8", errors="replace"))
        if cfg.get("deepseekApiKey"):
            keys["deepseek"] = cfg["deepseekApiKey"]
    except Exception:
        pass
    try:
        raw = open(os.environ.get("MINIMAX_CONFIG", ""), encoding="utf-8", errors="replace").read()
        m = re.search(r'"apiKey"\s*:\s*"([^"]+)"', raw)
        if m:
            keys["minimax"] = m.group(1)
    except Exception:
        pass
    for k, name in (("ALIYUN_AK_ID", "aliyun_id"), ("ALIYUN_AK_SECRET", "aliyun_secret")):
        try:
            txt = open(os.environ.get("DSH_ENV_FILE", os.path.expanduser("~/.dsh/.env")), encoding="utf-8", errors="replace").read()
            m = re.search(k + r"=([^\r\n]+)", txt)
            if m:
                keys[name] = m.group(1).strip().strip('"').strip("'")
        except Exception:
            pass
    return keys


def _aliyun_rpc(host, action, version, ak_id, ak_secret, extra=None):
    p = _urlquote
    params = {
        "Action": action, "Version": version, "Format": "JSON",
        "AccessKeyId": ak_id, "SignatureMethod": "HMAC-SHA1", "SignatureVersion": "1.0",
        "SignatureNonce": str(uuid.uuid4()),
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if extra:
        params.update(extra)
    canonical = "&".join("%s=%s" % (p(k, safe="~"), p(str(params[k]), safe="~")) for k in sorted(params))
    sts = "GET&%2F&" + p(canonical, safe="~")
    sig = base64.b64encode(hmac.new((ak_secret + "&").encode(), sts.encode(), hashlib.sha1).digest()).decode()
    url = "https://%s/?Signature=%s&%s" % (host, p(sig, safe="~"), canonical)
    with urllib.request.urlopen(urllib.request.Request(url), timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _read_302_key():
    """302.AI key lives encrypted (lock:) in the weflow config; decrypt once at startup."""
    try:
        sys.path.insert(0, os.environ.get("WEFLOW_SCRIPTS", ""))
        import _utils  # noqa
        cfg = json.load(open(os.path.expanduser("~/.weflow-cli/config.json"), encoding="utf-8", errors="replace"))
        locked = cfg.get("typesafeApiKey") or ""
        if locked.startswith("lock:"):
            return _utils.decrypt_lock(locked)
    except Exception:
        pass
    return None


def _get_json(url, token=None, timeout=12):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def quota_loop():
    keys = _read_keys()
    key302 = _read_302_key()
    _load_usage()
    while True:
        try:
            if keys.get("deepseek"):
                j = _get_json("https://api.deepseek.com/user/balance", keys["deepseek"])
                infos = j.get("balance_infos") or []
                if infos:
                    _quota["deepseek"] = {"ok": True, "value": infos[0].get("total_balance"), "unit": infos[0].get("currency", "CNY")}
                    _record_balance(infos[0].get("total_balance"))
                else:
                    _quota["deepseek"] = {"ok": True, "value": "?", "unit": "CNY"}
            else:
                _quota["deepseek"] = {"ok": False, "note": "未找到 key"}
        except Exception:
            _quota["deepseek"] = {"ok": False, "note": "查询失败"}

        try:
            if keys.get("newapi"):
                sub = _get_json("https://newapi.hycx-gd.cn/v1/dashboard/billing/subscription", keys["newapi"])
                used = None
                try:
                    usg = _get_json("https://newapi.hycx-gd.cn/v1/dashboard/billing/usage", keys["newapi"])
                    if isinstance(usg, dict) and "total_usage" in usg:
                        used = round(usg["total_usage"] / 100.0, 3)
                except Exception:
                    pass
                _quota["newapi"] = {"ok": True, "used": used, "limit": sub.get("hard_limit_usd")}
            else:
                _quota["newapi"] = {"ok": False, "note": "未找到 key"}
        except Exception:
            _quota["newapi"] = {"ok": False, "note": "查询失败"}

        try:
            if keys.get("minimax"):
                j = _get_json("https://api.minimaxi.com/v1/token_plan/remains", keys["minimax"])
                br = (j or {}).get("base_resp") or {}
                code = br.get("status_code")
                if code == 0:
                    rem = j.get("model_remains") or []
                    if rem:
                        m0 = rem[0] if isinstance(rem, list) else rem
                        pct_left = m0.get("remaining_percent") or m0.get("remain_percent")
                        if pct_left is not None:
                            _quota["minimax"] = {"ok": True, "note": "套餐剩 %s%%" % round(float(pct_left))}
                        else:
                            _quota["minimax"] = {"ok": True, "note": "套餐有效"}
                    else:
                        _quota["minimax"] = {"ok": True, "note": "套餐有效"}
                elif code == 2062:
                    _quota["minimax"] = {"ok": False, "note": "按量计费·额度看控制台"}
                elif code in (1004, 1008, 401, 403):
                    _quota["minimax"] = {"ok": False, "note": "key 类型不支持查询"}
                else:
                    _quota["minimax"] = {"ok": False, "note": str(br.get("status_msg") or "查询失败")[:26]}
            else:
                _quota["minimax"] = {"ok": False, "note": "未找到 key"}
        except Exception:
            _quota["minimax"] = {"ok": False, "note": "查询失败"}

        _quota["dashscope"] = {"ok": False, "note": "无余额接口·需控制台"}

        try:
            if keys.get("aliyun_id") and keys.get("aliyun_secret"):
                j = _aliyun_rpc("business.aliyuncs.com", "QueryAccountBalance", "2017-12-14",
                                keys["aliyun_id"], keys["aliyun_secret"])
                d = j.get("Data") or {}
                if d.get("AvailableAmount") is not None:
                    _quota["aliyun"] = {"ok": True, "value": d.get("AvailableAmount"),
                                        "unit": d.get("Currency", "CNY")}
                else:
                    _quota["aliyun"] = {"ok": False, "note": j.get("Message") or "无数据"}
            else:
                _quota["aliyun"] = {"ok": False, "note": "未找到 AK"}
        except Exception as e:
            _quota["aliyun"] = {"ok": False, "note": "查询失败"}

        try:
            if key302:
                j = _get_json("https://api.302ai.cn/dashboard/balance", key302)
                bal = (j.get("data") or {}).get("balance")
                if bal is not None:
                    _quota["ai302"] = {"ok": True, "value": bal, "unit": "USD"}
                else:
                    _quota["ai302"] = {"ok": False, "note": j.get("msg") or "无数据"}
            else:
                _quota["ai302"] = {"ok": False, "note": "未找到 key"}
        except Exception as e:
            note = "查询失败"
            s = str(e)
            if "403" in s:
                note = "key 未开管理权限"
            _quota["ai302"] = {"ok": False, "note": note}

        time.sleep(60)


# ---------- capture ----------
def capture_loop():
    with mss.mss() as sct:
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        last = time.time()
        while True:
            t0 = time.time()
            try:
                shot = sct.grab(mon)
                im = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                if SCALE_WIDTH and im.width > SCALE_WIDTH:
                    h = int(im.height * SCALE_WIDTH / im.width)
                    im = im.resize((SCALE_WIDTH, h), Image.BILINEAR)
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=QUALITY)
                data = buf.getvalue()
                with _lock:
                    _frame["jpeg"] = data
                    _frame["n"] += 1
                    _frame["w"], _frame["h"] = im.size
                    _fps["count"] += 1
            except Exception:
                time.sleep(0.2)
                continue

            now = time.time()
            if now - last >= 1.0:
                with _lock:
                    _fps["value"] = round(_fps["count"] / (now - last), 1)
                    _fps["count"] = 0
                last = now
            time.sleep(max(0.0, 1.0 / TARGET_FPS - (time.time() - t0)))


# ---------- metrics ----------
def metrics_loop():
    global _stats
    prev_net = None
    while True:
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            with _lock:
                _hist["cpu"].append(round(cpu))
                _hist["mem"].append(round(mem.percent))
                for k in ("cpu", "mem"):
                    if len(_hist[k]) > 60:
                        _hist[k].pop(0)

            net = psutil.net_io_counters()
            if prev_net is None:
                up = dn = 0
            else:
                up = int((net.bytes_sent - prev_net.bytes_sent) / 1024)
                dn = int((net.bytes_recv - prev_net.bytes_recv) / 1024)
            prev_net = net

            top = []
            for p in psutil.process_iter(["name", "cpu_percent"]):
                nm = (p.info.get("name") or "")
                if "Idle" in nm or nm in ("System", ""):
                    continue
                top.append({"name": nm[:18], "cpu": round(p.info.get("cpu_percent") or 0, 1),
                            "_v": p.info.get("cpu_percent") or 0})
            top.sort(key=lambda x: x["_v"], reverse=True)
            for t in top:
                t.pop("_v", None)
            top = top[:5]

            disks = {}
            for part in psutil.disk_partitions(all=False):
                try:
                    u = psutil.disk_usage(part.mountpoint)
                    disks[part.device.rstrip("\\")] = {"pct": round(u.percent), "free": round(u.free / 2**30, 1)}
                except Exception:
                    pass

            _stats.update({
                "cpu": round(cpu), "mem": round(mem.percent),
                "mem_used": round(mem.used / 2**30, 1), "mem_total": round(mem.total / 2**30, 1),
                "net_up": up, "net_dn": dn,
                "uptime": int((time.time() - psutil.boot_time()) // 60),
                "disks": disks,
                "time": time.strftime("%H:%M"), "date": time.strftime("%Y-%m-%d"),
            })
            _processes["top"] = top
        except Exception:
            pass
        time.sleep(1)


def ping_loop():
    import re
    targets = ["www.baidu.com", "223.5.5.5", "114.114.114.114"]
    while True:
        ms = -1
        for host in targets:
            try:
                out = subprocess.run(["ping", "-n", "1", "-w", "1000", host],
                                     capture_output=True, text=True, timeout=4,
                                     creationflags=0x08000000).stdout
                m = re.search(r"[=<]\s*(\d+)\s*ms", out)
                if m:
                    ms = int(m.group(1))
                    break
            except Exception:
                continue
        _stats["ping"] = ms
        time.sleep(5)


# ---------- pages ----------
MIRROR_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>本机镜像</title>
<link rel="icon" type="image/png" href="/icon-panel.png"><style>
html,body{margin:0;padding:0;background:#000;overflow:hidden;width:100%;height:100%}
#rot{position:absolute;top:0;left:0;transform-origin:0 0}
#rot img{display:block;width:100%;height:100%;object-fit:contain}</style></head>
<body><div id="rot"><img src="/stream"></div>
<script>(function(){var w=innerWidth,h=innerHeight,r=document.getElementById('rot');
r.style.width=h+'px';r.style.height=w+'px';r.style.transform='translateX('+w+'px) rotate(90deg)';})();</script></body></html>"""

PANEL_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>面板</title>
<link rel="icon" type="image/png" href="/icon-panel.png"><style>
:root{--bg:#0a0c10;--card:#141821;--line:#232a37;--fg:#e8edf6;--dim:#8b97ab;--acc:#6cc9ff;--warm:#ffc46b}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;background:var(--bg);color:var(--fg);
  font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
  width:100%;height:100%;overflow:hidden}
#rot{position:absolute;top:0;left:0;transform-origin:0 0}
.wrap{padding:12px 16px;box-sizing:border-box}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:9px 13px}
.card.wide{grid-column:span 2}
.lbl{font-size:12px;color:var(--dim);letter-spacing:.04em}
.big{font-size:32px;font-weight:700;line-height:1.1;margin-top:4px;font-variant-numeric:tabular-nums}
.unit{font-size:13px;color:var(--dim);font-weight:500;margin-left:2px}
.row{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.sub{font-size:11px;color:var(--dim);margin-top:4px}
.spark{display:block;width:100%;height:26px;margin-top:6px}
ul{margin:6px 0 0;padding:0;list-style:none}
li{display:flex;justify-content:space-between;font-size:12px;padding:3px 0;border-bottom:1px solid var(--line)}
li:last-child{border-bottom:0}
li span:last-child{color:var(--acc);font-variant-numeric:tabular-nums}
#clock{font-size:46px;font-weight:800;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.dot{width:8px;height:8px;border-radius:50%;background:#4ade80;display:inline-block;margin-right:6px}
</style></head><body><div id="rot"><div class="wrap">
  <div class="card wide" style="margin-bottom:12px">
    <div class="row"><div><div class="lbl">SYSTEM TIME</div><div id="clock">--:--</div>
      <div class="sub" id="date">—</div></div>
      <div style="text-align:right"><div class="sub"><span class="dot"></span><span id="up">—</span></div>
      <div class="sub" id="ping">ping —</div></div></div>
  </div>
  <div class="grid">
    <div class="card"><div class="lbl">CPU</div><div class="big"><span id="cpu">–</span><span class="unit">%</span></div>
      <svg class="spark" id="cpuSpark" preserveAspectRatio="none"></svg></div>
    <div class="card"><div class="lbl">MEMORY</div><div class="big"><span id="mem">–</span><span class="unit">%</span></div>
      <div class="sub" id="memSub">—</div><svg class="spark" id="memSpark" preserveAspectRatio="none"></svg></div>
    <div class="card"><div class="lbl">NETWORK</div>
      <div class="big" style="font-size:30px"><span id="dn">0</span><span class="unit">KB/s ↓</span></div>
      <div class="sub"><span id="upnet">0</span> KB/s ↑</div></div>
    <div class="card"><div class="lbl">DISK</div><div id="disks" class="sub" style="font-size:15px;color:var(--fg)">—</div></div>
    <div class="card wide"><div class="lbl">TOP PROCESSES</div><ul id="procs"><li><span>—</span><span></span></li></ul></div>
    <div class="card wide"><div class="lbl">API 额度</div>
      <ul id="quota">
        <li><span>DeepSeek</span><span id="q-deepseek">—</span></li>
        <li><span>NewAPI 中转</span><span id="q-newapi">—</span></li>
        <li><span>MiniMax</span><span id="q-minimax">—</span></li>
        <li><span>阿里百炼</span><span id="q-dashscope">—</span></li>
      </ul>
      <div class="sub"><a href="/" style="color:var(--acc);text-decoration:none">打开实时镜像 →</a></div></div>
  </div>
</div></div>
<script>
(function(){var w=innerWidth,h=innerHeight,r=document.getElementById('rot');
if(r){r.style.width=h+'px';r.style.height=w+'px';r.style.transform='translateX('+w+'px) rotate(90deg)';}})();
function spark(el, arr, color){
  var w=100,h=44,n=Math.max(arr.length,2),pts=[];
  for(var i=0;i<arr.length;i++){pts.push((i/(n-1)*w).toFixed(1)+','+(h-arr[i]/100*h).toFixed(1));}
  el.setAttribute('viewBox','0 0 '+w+' '+h);
  el.innerHTML='<polyline fill="none" stroke="'+color+'" stroke-width="1.6" points="'+pts.join(' ')+'"/>';
}
function fmtUptime(m){var d=Math.floor(m/1440),h=Math.floor(m%1440/60);return d+'d '+h+'h 在线';}
async function tick(){
  try{
    var j=await (await fetch('/panel.json',{cache:'no-store'})).json();
    document.getElementById('clock').textContent=j.time;
    document.getElementById('date').textContent=j.date;
    document.getElementById('cpu').textContent=j.cpu;
    document.getElementById('mem').textContent=j.mem;
    document.getElementById('memSub').textContent=j.mem_used+' / '+j.mem_total+' GB';
    document.getElementById('dn').textContent=j.net_dn;
    document.getElementById('upnet').textContent=j.net_up;
    document.getElementById('up').textContent=fmtUptime(j.uptime);
    document.getElementById('ping').textContent='ping '+(j.ping>0?j.ping+' ms':'超时');
    var q=j.quota||{};
    function qf(k){
      var x=q[k]||{};
      if(x.ok){
        if(k==='deepseek') return (x.value||'?')+(x.unit==='CNY'?' 元':' '+(x.unit||''));
        if(k==='newapi') return (x.used!=null? ('已用 $'+x.used) : '额度未设上限');
      }
      return x.note||'—';
    }
    ['deepseek','newapi','minimax','dashscope'].forEach(function(k){
      var el=document.getElementById('q-'+k); if(el) el.textContent=qf(k);
    });
    var d='';for(var k in j.disks){d+=k+' '+j.disks[k].pct+'% · 剩'+j.disks[k].free+'G<br>';}
    document.getElementById('disks').innerHTML=d||'—';
    var ul=document.getElementById('procs');ul.innerHTML='';
    (j.top||[]).forEach(function(p){var li=document.createElement('li');
      var a=document.createElement('span');a.textContent=p.name;
      var b=document.createElement('span');b.textContent=p.cpu+'%';
      li.appendChild(a);li.appendChild(b);ul.appendChild(li);});
    spark(document.getElementById('cpuSpark'), j.hist_cpu||[], '#6cc9ff');
    spark(document.getElementById('memSpark'), j.hist_mem||[], '#ffc46b');
  }catch(e){}
}
tick();setInterval(tick,1000);
</script></body></html>"""


PANEL_VIEW = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>面板</title>
<link rel="icon" type="image/png" href="/icon-panel.png"><style>
html,body{margin:0;background:#000;overflow:hidden;width:100%;height:100%;box-sizing:border-box}
body{padding-top:8vh}
img{display:block;width:100%;height:100%;object-fit:contain}
</style></head><body><img id="p" src="/panel.jpg">
<script>
var a=new Image(), el=document.getElementById('p');
a.onload=function(){ el.src=a.src; };
setInterval(function(){ a.src='/panel.jpg?t='+Date.now(); },1000);
(function(){function go(){var d=document.documentElement;if(d.requestFullscreen){d.requestFullscreen().catch(function(){});}else if(d.webkitRequestFullscreen){d.webkitRequestFullscreen();}}
document.addEventListener('click',go);document.addEventListener('touchstart',go,{passive:true});
if(location.hash==='#fs'){go();}})();
(function(){
function ping(r){try{new Image().src='/wakelock?r='+r+'&t='+Date.now();}catch(e){}}
var lock=null;
function keep(){
  if(!('wakeLock' in navigator)){ping('unsupported');return;}
  navigator.wakeLock.request('screen').then(function(l){
    lock=l; ping('ok');
    setInterval(function(){
      if(document.visibilityState==='visible' && l.released){
        navigator.wakeLock.request('screen').then(function(n){lock=n;ping('reok');}).catch(function(){ping('refail');});
      }
    },20000);
  }).catch(function(){ping('fail');});
}
keep();
document.addEventListener('visibilitychange',function(){ if(document.visibilityState==='visible'){keep();} });
})();
</script></body></html>"""


EINK_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>面板 墨水屏</title>
<link rel="icon" type="image/png" href="/icon-panel.png"><style>
html,body{margin:0;background:#fff;color:#000;overflow:hidden;width:100%;height:100%;box-sizing:border-box}
body{padding-top:8vh}
img{display:block;width:100%;height:100%;object-fit:contain;background:#fff}
</style></head><body><img id="p" src="/eink.jpg">
<script>
var a=new Image(), el=document.getElementById('p');
a.onload=function(){ el.src=a.src; };
setInterval(function(){ a.src='/eink.jpg?t='+Date.now(); }, 60000);
(function(){function go(){var d=document.documentElement;if(d.requestFullscreen){d.requestFullscreen().catch(function(){});}else if(d.webkitRequestFullscreen){d.webkitRequestFullscreen();}}
document.addEventListener('click',go);document.addEventListener('touchstart',go,{passive:true});
if(location.hash==='#fs'){go();}})();
</script></body></html>"""


def render_eink():
    """Black-on-white, large type, no charts: meant for an e-ink panel refreshing once a minute."""
    W, H = 1680, 1264
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    P = 40

    fb = _font(96, True)
    fm = _font(52, True)
    fs = _font(38)
    ft = _font(40)

    s = dict(_stats)
    q = dict(_quota)
    gpu = s.get("gpu") or {}
    disks = s.get("disks") or {}

    # header
    d.text((P, P), s.get("time", "--:--"), font=fb, fill=(0, 0, 0))
    d.text((P + 260, P + 30), s.get("date", ""), font=fs, fill=(60, 60, 60))
    d.text((W - P, P + 34), "ping %s" % (("%d ms" % s["ping"]) if s.get("ping", -1) > 0 else "超时"),
           font=fs, fill=(60, 60, 60), anchor="ra")
    d.line((P, P + 130, W - P, P + 130), fill=(0, 0, 0), width=3)

    # two columns of metrics
    def block(x, y, label, value, unit="", sub=""):
        d.text((x, y), label, font=ft, fill=(0, 0, 0))
        d.text((x, y + 64), value, font=fm, fill=(0, 0, 0))
        vw = d.textlength(value, font=fm)
        if unit:
            d.text((x + vw + 8, y + 84), unit, font=fs, fill=(60, 60, 60))
        if sub:
            d.text((x, y + 140), sub, font=fs, fill=(60, 60, 60))

    col_w = (W - P * 2) // 2
    y0 = P + 180
    block(P, y0, "CPU", "%d" % s.get("cpu", 0), "%")
    block(P + col_w, y0, "GPU", "%d" % gpu.get("util", 0), "%",
          ("%d MB / %d °C" % (gpu.get("mem_used", 0), gpu.get("temp", 0))) if gpu else "未检测")

    y1 = y0 + 230
    block(P, y1, "运行内存", "%d" % s.get("mem", 0), "%",
          "%s / %s GB" % (s.get("mem_used", 0), s.get("mem_total", 0)))
    block(P + col_w, y1, "空间 D", "%d" % (disks.get("D:", {}).get("pct", 0)), "%",
          "剩 %s G" % disks.get("D:", {}).get("free", 0))

    y2 = y1 + 230
    block(P, y2, "网络", "%d" % s.get("net_dn", 0), "KB/s", "↑ %d KB/s" % s.get("net_up", 0))
    block(P + col_w, y2, "C 盘", "%d" % (disks.get("C:", {}).get("pct", 0)), "%",
          "剩 %s G" % disks.get("C:", {}).get("free", 0))

    # quota rows
    y3 = y2 + 240
    d.line((P, y3, W - P, y3), fill=(0, 0, 0), width=3)
    yy = y3 + 26
    for name, item in (("DeepSeek", q.get("deepseek")), ("NewAPI", q.get("newapi")),
                       ("302.AI", q.get("ai302")), ("阿里云", q.get("aliyun"))):
        item = item or {}
        if item.get("ok"):
            if item.get("value") is not None:
                unit = item.get("unit")
                txt = ("%s 元" % item["value"]) if unit == "CNY" else ("$%s" % item["value"])
            else:
                txt = "已用 $%s" % item.get("used") if item.get("used") is not None else "—"
        else:
            txt = item.get("note", "—")
        d.text((P, yy), name, font=ft, fill=(0, 0, 0))
        d.text((W - P, yy), txt, font=ft, fill=(0, 0, 0), anchor="ra")
        yy += 56

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    _eink["png"] = buf.getvalue()
    _eink["t"] = time.time()


def eink_loop():
    time.sleep(8)
    while True:
        try:
            render_eink()
        except Exception:
            pass
        time.sleep(30)


REMOTE_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>ToDesk 远端</title>
<link rel="icon" type="image/png" href="/icon-remote.png">
<style>
html,body{margin:0;background:#000;overflow:hidden;width:100%;height:100%;box-sizing:border-box}
body{padding-top:8vh}
img{display:block;width:100%;height:100%;object-fit:contain}
</style></head><body><img id="p" src="/remote.jpg">
<script>
var a=new Image(), el=document.getElementById('p');
a.onload=function(){ el.src=a.src; };
setInterval(function(){ a.src='/remote.jpg?t='+Date.now(); }, 1000);
(function(){function go(){var d=document.documentElement;if(d.requestFullscreen){d.requestFullscreen().catch(function(){});}else if(d.webkitRequestFullscreen){d.webkitRequestFullscreen();}}
document.addEventListener('click',go);document.addEventListener('touchstart',go,{passive:true});
if(location.hash==='#fs'){go();}})();
</script></body></html>"""

_remote = {"jpg": b"", "png": b"", "t": 0, "hwnd": 0, "note": ""}


def _find_remote_hwnd():
    import ctypes
    import ctypes.wintypes as wt
    u = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        n = u.GetWindowTextLengthW(hwnd)
        if n:
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, b, n + 1)
            t = b.value
            low = t.lower()
            if "todesk" in low or "laptop-" in low or "desktop-" in low:
                found.append((hwnd, t))
        return True

    u.EnumWindows(cb, 0)
    # prefer the session window (its title is the remote machine name, not just "ToDesk")
    found.sort(key=lambda x: (x[1].strip().lower() == "todesk",))
    return (found[0][0], found[0][1]) if found else (None, "")


def _grab_window(hwnd):
    import ctypes
    import ctypes.wintypes as wt
    u = ctypes.windll.user32
    g = ctypes.windll.gdi32

    class WP(ctypes.Structure):
        _fields_ = [("length", wt.UINT), ("flags", wt.UINT), ("showCmd", wt.UINT),
                    ("ptMinPosition", wt.POINT), ("ptMaxPosition", wt.POINT),
                    ("rcNormalPosition", wt.RECT)]

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                    ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]

    wp = WP()
    wp.length = ctypes.sizeof(WP)
    u.GetWindowPlacement(hwnd, ctypes.byref(wp))
    r = wp.rcNormalPosition
    w, h = r.right - r.left, r.bottom - r.top
    if w < 200 or h < 200:
        return None

    hdc_screen = u.GetDC(0)
    hdc = g.CreateCompatibleDC(hdc_screen)
    hbmp = g.CreateCompatibleBitmap(hdc_screen, w, h)
    g.SelectObject(hdc, hbmp)
    u.PrintWindow(hwnd, hdc, 0x00000002)

    bi = BIH()
    bi.biSize = ctypes.sizeof(BIH)
    bi.biWidth, bi.biHeight = w, -h
    bi.biPlanes, bi.biBitCount, bi.biCompression = 1, 32, 0
    buf = ctypes.create_string_buffer(w * h * 4)
    g.GetDIBits(hdc, hbmp, 0, h, buf, ctypes.byref(bi), 0)

    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    g.DeleteObject(hbmp)
    g.DeleteDC(hdc)
    u.ReleaseDC(0, hdc_screen)
    return img


def remote_loop():
    import ctypes
    u = ctypes.windll.user32
    while True:
        try:
            hwnd, title = _find_remote_hwnd()
            if not hwnd:
                _remote["note"] = "未找到 ToDesk 窗口"
            else:
                _remote["hwnd"] = hwnd
                if u.IsIconic(hwnd):
                    # only restore when someone is actually watching, so it never pops up on its own
                    if time.time() - _remote.get("wanted", 0) < 120:
                        u.ShowWindow(hwnd, 4)      # SW_SHOWNOACTIVATE: restore without stealing focus
                        time.sleep(0.6)
                    else:
                        _remote["note"] = "窗口已最小化（打开 /remote 会自动还原）"
                        time.sleep(3)
                        continue
                img = _grab_window(hwnd)
                if img is None:
                    _remote["note"] = "窗口尺寸异常"
                else:
                    buf = io.BytesIO()
                    img.save(buf, "JPEG", quality=72)
                    _remote["jpg"] = buf.getvalue()

                    g = img.convert("L")
                    g.thumbnail((1680, 1264), Image.LANCZOS)
                    canvas = Image.new("L", (1680, 1264), 255)
                    canvas.paste(g, ((1680 - g.width) // 2, (1264 - g.height) // 2))
                    buf2 = io.BytesIO()
                    canvas.save(buf2, "PNG", optimize=True)
                    _remote["png"] = buf2.getvalue()
                    _remote["note"] = title
                    _remote["t"] = time.time()
        except Exception as e:
            _remote["note"] = "抓取失败"
        time.sleep(1)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send(self, body, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            with _lock:
                _clients[self.client_address[0]] = {"t": time.time(), "path": self.path[:80]}
        except Exception:
            pass
        path = self.path.split("?")[0]

        if path in ("/", "/index.html"):
            return self._send(MIRROR_PAGE.encode(), "text/html; charset=utf-8")

        if path in ("/panel", "/panel.html"):
            return self._send(PANEL_VIEW.encode(), "text/html; charset=utf-8")

        if path in ("/eink", "/eink.html"):
            return self._send(EINK_PAGE.encode(), "text/html; charset=utf-8")

        if path == "/eink.jpg":
            with _lock:
                data = _eink["png"]
            if not data:
                return self._send(b"", "image/png", 503)
            return self._send(data, "image/png")

        if path in ("/remote", "/remote.html"):
            _remote["wanted"] = time.time()
            return self._send(REMOTE_PAGE.encode(), "text/html; charset=utf-8")

        if path == "/remote.jpg":
            _remote["wanted"] = time.time()
            with _lock:
                data = _remote["jpg"]
            if not data:
                return self._send(b"", "image/jpeg", 503)
            return self._send(data, "image/jpeg")

        if path == "/remote.png":
            _remote["wanted"] = time.time()
            with _lock:
                data = _remote["png"]
            if not data:
                return self._send(b"", "image/png", 503)
            return self._send(data, "image/png")

        if path in ("/icon-remote.png", "/favicon.ico"):
            return self._send(_make_icon((15, 118, 110), "R"), "image/png")

        if path == "/icon-panel.png":
            return self._send(_make_icon((37, 99, 235), "P"), "image/png")

        if path == "/wakelock":
            try:
                q = self.path.split("?", 1)[1] if "?" in self.path else ""
                kv = dict(p.split("=", 1) for p in q.split("&") if "=" in p)
                _wake["result"] = kv.get("r", "?")
                _wake["t"] = time.time()
            except Exception:
                pass
            return self._send(b"", "image/gif", 204)

        if path == "/wakestatus":
            with _lock:
                snap = dict(_wake)
            return self._send(json.dumps(snap, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        if path == "/clients":
            with _lock:
                snap = {}
                for ip, rec in _clients.items():
                    if isinstance(rec, dict):
                        snap[ip] = {"ago": round(time.time() - rec["t"]), "path": rec.get("path", "")}
                    else:
                        snap[ip] = {"ago": round(time.time() - rec)}
            return self._send(json.dumps(snap, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        if path == "/panel.jpg":
            with _lock:
                data = _panel["jpeg"]
            if not data:
                return self._send(b"", "image/jpeg", 503)
            return self._send(data, "image/jpeg")

        if path == "/panel.json":
            with _lock:
                payload = dict(_stats)
                payload["hist_cpu"] = list(_hist["cpu"])
                payload["hist_mem"] = list(_hist["mem"])
                payload["fps"] = _fps["value"]
                payload["top"] = _processes["top"]
                payload["quota"] = dict(_quota)
                payload["usage"] = dict(zip(("week", "month"), _usage_summary()))
            return self._send(json.dumps(payload).encode(), "application/json")

        if path == "/frame.jpg":
            with _lock:
                data = _frame["jpeg"]
            if not data:
                return self._send(b"", "image/jpeg", 503)
            return self._send(data, "image/jpeg")

        if path == "/stats":
            return self._send(json.dumps({"fps": _fps["value"], "frames": _frame["n"]}).encode(), "application/json")

        if path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                last_n = -1
                while True:
                    with _lock:
                        data = _frame["jpeg"]
                        n = _frame["n"]
                    if data and n != last_n:
                        last_n = n
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(data)).encode() + b"\r\n\r\n")
                        self.wfile.write(data)
                        self.wfile.write(b"\r\n")
                    else:
                        time.sleep(0.005)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        return self._send(b"", "text/plain", 404)


if __name__ == "__main__":
    threading.Thread(target=capture_loop, daemon=True).start()
    threading.Thread(target=metrics_loop, daemon=True).start()
    threading.Thread(target=ping_loop, daemon=True).start()
    threading.Thread(target=quota_loop, daemon=True).start()
    threading.Thread(target=gpu_loop, daemon=True).start()
    threading.Thread(target=panel_loop, daemon=True).start()
    threading.Thread(target=eink_loop, daemon=True).start()
    threading.Thread(target=remote_loop, daemon=True).start()
    time.sleep(0.6)
    print("listening on %d" % PORT, flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
