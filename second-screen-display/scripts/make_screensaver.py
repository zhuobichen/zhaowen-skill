# Build portrait e-ink images for the iReader screensaver folder.
import json
import os
import urllib.request

from PIL import Image, ImageDraw, ImageFont

W, H = 1264, 1680
PANEL_HOST = os.environ.get("PANEL_HOST", "127.0.0.1:8080")
OUT = os.environ.get("OUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
os.makedirs(OUT, exist_ok=True)


def font(size, bold=False):
    for name in (("msyhbd.ttc", "msyh.ttc") if bold else ("msyh.ttc", "simhei.ttf")):
        try:
            return ImageFont.truetype("C:/Windows/Fonts/" + name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def data():
    try:
        with urllib.request.urlopen("http://" + PANEL_HOST + "/panel.json", timeout=6) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return {}


def dashboard():
    d = data()
    img = Image.new("RGB", (W, H), (255, 255, 255))
    g = ImageDraw.Draw(img)
    P = 56

    f_clock = font(150, True)
    f_lbl = font(44)
    f_val = font(78, True)
    f_sub = font(36)

    clock = d.get("time", "--:--")
    g.text((P, P), clock, font=f_clock, fill=(0, 0, 0))
    g.text((P, P + 190), d.get("date", ""), font=f_sub, fill=(70, 70, 70))
    g.line((P, P + 260, W - P, P + 260), fill=(0, 0, 0), width=4)

    gpu = d.get("gpu") or {}
    disks = d.get("disks") or {}
    rows = [
        ("CPU", "%d%%" % d.get("cpu", 0)),
        ("GPU", "%d%%  %d°C" % (gpu.get("util", 0), gpu.get("temp", 0))),
        ("内存", "%d%%  %s/%s GB" % (d.get("mem", 0), d.get("mem_used", 0), d.get("mem_total", 0))),
        ("D 盘", "%d%%  剩 %s G" % (disks.get("D:", {}).get("pct", 0), disks.get("D:", {}).get("free", 0))),
        ("C 盘", "%d%%  剩 %s G" % (disks.get("C:", {}).get("pct", 0), disks.get("C:", {}).get("free", 0))),
    ]
    y = P + 320
    for label, val in rows:
        g.text((P, y), label, font=f_lbl, fill=(90, 90, 90))
        g.text((P + 220, y - 16), val, font=f_val, fill=(0, 0, 0))
        y += 150

    g.line((P, y + 20, W - P, y + 20), fill=(0, 0, 0), width=4)
    y += 70
    q = d.get("quota") or {}
    for label, item in (("DeepSeek", q.get("deepseek")), ("NewAPI", q.get("newapi")),
                        ("302.AI", q.get("ai302")), ("阿里云", q.get("aliyun"))):
        item = item or {}
        if item.get("ok") and item.get("value") is not None:
            txt = ("%s 元" % item["value"]) if item.get("unit") == "CNY" else ("$%s" % item["value"])
        elif item.get("used") is not None:
            txt = "已用 $%s" % item["used"]
        else:
            txt = item.get("note", "-")
        g.text((P, y), label, font=f_lbl, fill=(90, 90, 90))
        g.text((W - P, y), txt, font=f_lbl, fill=(0, 0, 0), anchor="ra")
        y += 66

    path = os.path.join(OUT, "dashboard.png")
    img.save(path)
    return path


def remote():
    try:
        with urllib.request.urlopen("http://" + PANEL_HOST + "/remote.png", timeout=8) as r:
            raw = r.read()
        p = os.path.join(OUT, "_tmp_remote.png")
        open(p, "wb").write(raw)
        src = Image.open(p).convert("L")
        src.thumbnail((W - 80, H - 120), Image.LANCZOS)
        canvas = Image.new("L", (W, H), 255)
        canvas.paste(src, ((W - src.width) // 2, (H - src.height) // 2))
        path = os.path.join(OUT, "remote-screen.png")
        canvas.save(path)
        os.remove(p)
        return path
    except Exception as e:
        return "remote failed: %s" % e


if __name__ == "__main__":
    print(dashboard())
    print(remote())
