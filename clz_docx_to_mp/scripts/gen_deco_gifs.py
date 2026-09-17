# -*- coding: utf-8 -*-
"""
生成公众号正文的 GIF 动效装饰件（本 skill 原创，不引用第三方素材）

为什么要自己画：从别人的文章里扒 GIF 有授权风险（来源不明、可能来自付费模板库）。
自己生成的好处是**零授权问题**，且配色/形状能跟本 skill 的主题完全一致。

产出（存到 <skill>/assets/）：
    deco-star-pulse.gif    章节标题同款星形，呼吸式缩放 —— 内容块右上角
    deco-chevron-bounce.gif 三枚下箭头依次点亮 —— 分节之间的下滑引导

用法：
    python gen_deco_gifs.py            # 重新生成到 ../assets/
"""
import os
import io
import sys
import math

if sys.platform == 'win32' and __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from PIL import Image, ImageDraw  # noqa: E402

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets')

PRIMARY = (79, 129, 189)     # #4F81BD —— 与 THEME['primary'] 一致
TEAL = (118, 197, 203)       # #76C5CB —— 与 THEME['teal'] 一致
SS = 4                       # 超采样倍数：先画大图再缩小，边缘才干净


def _star_points(cx, cy, R, r, n=5, rot=-90):
    """n 角星的顶点坐标（rot 控制第一个尖角的方向）"""
    pts = []
    for i in range(n * 2):
        ang = math.radians(rot + i * 180.0 / n)
        rad = R if i % 2 == 0 else r
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts


def gen_star_pulse(size=60, frames=12, duration=90):
    """五角星呼吸式缩放。形状与章节标题的 SVG 星形同款，视觉上自成一套。"""
    out = []
    for i in range(frames):
        # 用余弦做无级往复：0 → 1 → 0
        t = (1 - math.cos(2 * math.pi * i / frames)) / 2.0
        scale = 0.82 + 0.18 * t
        W = size * SS
        im = Image.new('RGBA', (W, W), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        R = W * 0.46 * scale
        r = R * 0.42
        d.polygon(_star_points(W / 2, W / 2, R, r), fill=PRIMARY + (255,))
        # 内圈叠一层青色小星，做出层次
        R2 = R * 0.46
        d.polygon(_star_points(W / 2, W / 2, R2, R2 * 0.42), fill=TEAL + (255,))
        out.append(im.resize((size, size), Image.LANCZOS))
    path = os.path.join(ASSETS, 'deco-star-pulse.gif')
    out[0].save(path, save_all=True, append_images=out[1:],
                duration=duration, loop=0, disposal=2)
    return path


def gen_chevron_bounce(size=64, frames=12, duration=110):
    """三枚下箭头依次点亮，做出「往下滑」的引导感。

    不用位移而用明暗波，是因为微信里位移需要靠帧内坐标重画，
    明暗波在同一位置逐帧改颜色即可，视觉更稳、体积也更小。
    """
    out = []
    W = size * SS
    for i in range(frames):
        im = Image.new('RGBA', (W, W), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for k in range(3):
            # 亮起的箭头随时间从上往下移动
            phase = (i / float(frames) - k * 0.16) % 1.0
            alpha = int(60 + 195 * max(0.0, 1.0 - abs(phase - 0.25) * 4))
            alpha = max(40, min(255, alpha))
            cy = W * (0.30 + k * 0.20)
            half = W * 0.15
            thick = W * 0.055
            col = PRIMARY + (alpha,)
            d.line([(W / 2 - half, cy - half * 0.5), (W / 2, cy + half * 0.5)],
                   fill=col, width=int(thick), joint='curve')
            d.line([(W / 2, cy + half * 0.5), (W / 2 + half, cy - half * 0.5)],
                   fill=col, width=int(thick), joint='curve')
        out.append(im.resize((size, size), Image.LANCZOS))
    path = os.path.join(ASSETS, 'deco-chevron-bounce.gif')
    out[0].save(path, save_all=True, append_images=out[1:],
                duration=duration, loop=0, disposal=2)
    return path


def main():
    os.makedirs(ASSETS, exist_ok=True)
    for fn in (gen_star_pulse, gen_chevron_bounce):
        p = fn()
        im = Image.open(p)
        print('✅ %-28s %dx%d  %d 帧  %dKB'
              % (os.path.basename(p), im.size[0], im.size[1],
                 im.n_frames, os.path.getsize(p) // 1024))
    return 0


if __name__ == '__main__':
    sys.exit(main())
