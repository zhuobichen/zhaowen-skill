# -*- coding: utf-8 -*-
"""把 PDF 逐页转成 PNG，用来「看一眼」验证渲染结果。

用法：
    python rasterize.py 报告.pdf [输出目录] [缩放]

为什么需要它：一份自包含的 HTML 报告，光看源码证明不了它渲染出来是对的
（图会不会空白、字会不会被切、被吃掉的标签会不会静默少一块）。
把 HTML 打成 PDF 再转图，是成本最低的"亲眼看一下"。

本机实测：Edge 无头模式打印 PDF 最省事
    msedge --headless=new --disable-gpu --no-pdf-header-footer \
           --print-to-pdf=out.pdf "file:///路径/report.html"
注意路径里有中文时，先把 HTML 复制成 ASCII 文件名再打印，省去编码问题。

中文 PDF 一定要用 PyMuPDF（pdf.js 抽不出汉字，加 cmaps 也没用）。
"""
import os
import sys

import pymupdf


def main(pdf, out_dir=None, zoom=1.35, prefix="pg"):
    out_dir = out_dir or os.path.dirname(os.path.abspath(pdf))
    os.makedirs(out_dir, exist_ok=True)
    doc = pymupdf.open(pdf)
    print("页数:", doc.page_count)
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        out = os.path.join(out_dir, "%s%d.png" % (prefix, i + 1))
        pix.save(out)
        print("  %s  %dx%d" % (os.path.basename(out), pix.width, pix.height))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("用法: python rasterize.py <pdf> [输出目录] [缩放]")
    a = sys.argv[1:]
    main(a[0], a[1] if len(a) > 1 else None, float(a[2]) if len(a) > 2 else 1.35)
