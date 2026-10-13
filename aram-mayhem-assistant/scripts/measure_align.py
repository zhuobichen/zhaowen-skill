# -*- coding: utf-8 -*-
"""量一页（或一页的截图）里每块内容的左右边界，用来看图有没有居中、跟正文对不对齐。

用法：
    python measure_align.py 第几页.png

为什么需要它：眼睛判断十几像素的偏心是不可靠的。我自己就栽过两次 ——
一次说"图明显右偏"实际只差 2.5px，一次改了 CSS 却量出来数字没变，
才发现 svg() 里写的是**内联** style，把样式表里的规则压住了。

思路：逐行找最左/最右的非背景像素，再把连续的有内容行并成「块」，
每块打印 (y 范围, 左, 右, 宽)。把「图」那一块的中心和「正文段落」那一块的中心比一下。
"""
import sys

from PIL import Image


def bands(px, W, H, th=244, min_h=2):
    rows = []
    for y in range(H):
        xs = [x for x in range(W) if px[x, y] < th]
        rows.append((min(xs), max(xs)) if xs else None)

    out, cur = [], None
    for y, r in enumerate(rows):
        if r is None:
            if cur:
                out.append(cur)
                cur = None
            continue
        if cur is None:
            cur = [y, y, r[0], r[1]]
        else:
            cur[1], cur[2], cur[3] = y, min(cur[2], r[0]), max(cur[3], r[1])
    if cur:
        out.append(cur)
    return [b for b in out if b[1] - b[0] + 1 >= min_h]


def main(path):
    im = Image.open(path).convert("L")
    W, H = im.size
    px = im.load()
    bs = bands(px, W, H)
    print("页面 %dx%d，检出 %d 块" % (W, H, len(bs)))
    print("   y0    y1    高    左    右    宽   中心")
    for b in bs:
        y0, y1, x0, x1 = b
        print("  %4d  %4d  %4d  %4d  %4d  %4d  %5.1f"
              % (y0, y1, y1 - y0 + 1, x0, x1, x1 - x0 + 1, (x0 + x1) / 2))
    print("\n比较法：找到「图」那块的 y 区间和「正文段落」那块的 y 区间，比最后一列的中心。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("用法: python measure_align.py <页面 png>")
    main(sys.argv[1])
