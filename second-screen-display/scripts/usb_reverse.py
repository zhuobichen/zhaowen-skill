# Keep the USB reverse tunnel alive: whenever the phone is plugged in, re-establish
# `adb reverse tcp:8080 tcp:8080` and (once per connection) open the panel page.
import os
import subprocess
import time

ADB = os.environ.get("ADB", "adb")
PORT = 8080
URL = os.environ.get("PANEL_URL", "http://127.0.0.1:%d/panel" % PORT)
NO_WINDOW = 0x08000000


def run(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=15,
                              creationflags=NO_WINDOW).stdout
    except Exception:
        return ""


def devices():
    out = run([ADB, "devices"])
    found = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line or "\t" not in line:
            continue
        serial, state = line.split("\t")[:2]
        if state.strip() == "device" and ":" not in serial:   # USB serials have no colon
            found.append(serial)
    return found


def focus_ok(serial):
    out = run([ADB, "-s", serial, "shell", "dumpsys", "window"])
    for line in out.splitlines():
        if "mCurrentFocus" in line:
            return "com.android.browser" in line
    return True


def main():
    served = set()
    last_open = 0.0
    while True:
        for serial in devices():
            run([ADB, "-s", serial, "reverse", "tcp:%d" % PORT, "tcp:%d" % PORT])
            now = time.time()
            # open the page on (re)connect, and put it back if something else took the foreground
            if serial not in served or (not focus_ok(serial) and now - last_open > 30):
                time.sleep(0.8)
                run([ADB, "-s", serial, "shell", "am", "start", "-a", "android.intent.action.VIEW",
                     "-d", URL])
                served.add(serial)
                last_open = now
        # forget devices that went away so a replug re-opens the page
        for serial in list(served):
            if serial not in devices():
                served.discard(serial)
        time.sleep(5)


if __name__ == "__main__":
    main()
