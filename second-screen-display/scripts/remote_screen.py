# Keep the secondary monitor showing the /remote view:
#   * an Edge app window parked fullscreen on the secondary
#   * the ToDesk session window restored (PrintWindow returns black when minimized)
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import time

user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

EDGE_CANDIDATES = [
    os.environ.get("EDGE", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
URL = "http://127.0.0.1:8080/remote"
PROFILE = os.environ.get("REMOTE_PROFILE", os.path.join(os.path.expanduser("~"), ".second-screen", "edge-remote"))
# x, y, w, h of the secondary monitor (see the DPI note in SKILL.md)
SECOND = tuple(int(v) for v in os.environ.get("SECOND_MON", "2560,0,1920,1280").split(","))
SW_RESTORE, SW_SHOWNA = 9, 8
SWP_SHOWWINDOW = 0x0040


def windows():
    rows = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        n = user32.GetWindowTextLengthW(h)
        if n:
            b = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, b, n + 1)
            cn = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, cn, 256)
            rows.append((h, b.value, cn.value))
        return True

    user32.EnumWindows(cb, 0)
    return rows


def find_remote():
    for h, t, c in windows():
        if t.strip() == "remote" and "Chrome" in c:
            return h
    return None


def todesk_session():
    import re
    host = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,30}$")
    skip = {"todesk", "cclipboardthread", "dropfilewindowtitle", "dragfilewindowtitle"}
    for h, t, c in windows():
        low = t.strip().lower()
        if low in skip or "ime" in low or "gdi+" in low:
            continue
        if host.match(t.strip()) and not user32.IsWindowVisible(h) is False:
            return h
    return None


def launch_edge():
    exe = next((p for p in EDGE_CANDIDATES if os.path.exists(p)), None)
    if not exe:
        return False
    subprocess.Popen([exe, "--app=" + URL, "--user-data-dir=" + PROFILE, "--no-first-run",
                      "--no-default-browser-check", "--disable-sync",
                      "--disable-features=SigninPromo", "--disable-session-crashed-bubble",
                      "--window-position=%d,%d" % (SECOND[0], SECOND[1]),
                      "--window-size=%d,%d" % (SECOND[2], SECOND[3])],
                     creationflags=0x08000000)
    return True


def main():
    while True:
        try:
            h = find_remote()
            if h is None:
                if launch_edge():
                    time.sleep(8)
                h = find_remote()
            if h:
                r = wt.RECT()
                user32.GetWindowRect(h, ctypes.byref(r))
                if (r.left, r.top, r.right - r.left, r.bottom - r.top) != SECOND:
                    user32.SetWindowPos(h, 0, *SECOND, SWP_SHOWWINDOW)
            # ToDesk must stay restorable or PrintWindow yields black
            t = todesk_session()
            if t and user32.IsIconic(t):
                user32.ShowWindow(t, SW_RESTORE)
        except Exception:
            pass
        time.sleep(15)


if __name__ == "__main__":
    main()
