# Verify the secondary monitor is showing a live (changing) image.
import os
import hashlib
import time

import mss
from PIL import Image


def grab():
    with mss.mss() as s:
        raw = s.grab(s.monitors[2])
        return Image.frombytes("RGB", raw.size, raw.rgb)


a = grab()
time.sleep(2.2)
b = grab()
print("mon2 luma:", b.convert("L").getextrema())
print("frames differ (live):", hashlib.md5(a.tobytes()).hexdigest() != hashlib.md5(b.tobytes()).hexdigest())
b.save(os.environ.get("OUT", "m2_check.png"))
print("saved")
