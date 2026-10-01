#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公众号模板反推器 —— 给一篇已发表文章，吐出一套可复用的主题。

    输入：URL（走 browser-act 免登录打开）或本地 HTML（正文片段或整页都行）
    输出：templates/<name>/
            theme.json     设计令牌 + 组件形态（机器可读）
            reference.md   人读的反推记录 + 人工复核清单
            sample.html    抠下来的正文 HTML（对照用）
            preview.png    渲染截图（**最重要的对照物**，见下）

为什么必须有 preview.png —— 2026-09-30 实测教训：
    只解析 CSS 的「颜色/数值」是**推不出结构**的。那次反推一个红色卡片模板，
    数值全对，但结构错三处：章节标题条做成了左右两端（实为「红方块 + 英文小字 +
    中文标题」三件套）、引用块漏了 border-left 竖线、胶囊漏了内嵌小红圆点。
    这三条都不是「数值差一点」，是「少了个元素」—— 数值可以推理，缺元素只能看。
    所以每个模板都存一张渲染图，复核时必须人眼看它，不能只看 theme.json。

用法：
    python extract_theme.py --url "https://mp.weixin.qq.com/s/xxx" --name redcard2026
    python extract_theme.py --html ./body.html --name xxx
    python extract_theme.py --html ./body.html --name xxx --preview ./preview.png
    python extract_theme.py --url ... --name ... --no-preview
"""
import argparse
import collections
import io
import json
import os
import re
import subprocess
import sys
import tempfile

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(SKILL_DIR, 'templates')

# browser-act CLI 的常见位置（uv tool 装法）
BROWSER_ACT_CANDIDATES = [
    os.path.expanduser('~/.local/bin/browser-act.exe'),
    os.path.expanduser('~/.local/bin/browser-act'),
    'browser-act',
]

# 微信页面外壳自带的颜色，出现频率极高但不是模板的一部分 —— 统计时要排掉，
# 否则「微信绿」「链接蓝」这类会盖过模板主色。
WECHAT_CHROME_COLORS = {
    'rgb(7, 193, 96)', 'rgb(87, 107, 149)', 'rgb(250, 81, 81)', 'rgb(16, 174, 255)',
    '#07c160', '#576b95', '#fa5151', '#10aeff', '#ffffff', '#000000',
    'rgb(255, 255, 255)', 'rgb(0, 0, 0)',
}

COLOR_RE = re.compile(r'rgba?\([^)]{5,40}\)|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b')
STYLE_RE = re.compile(r'style="([^"]*)"')
SECTION_RE = re.compile(r'<section\b[^>]*style="([^"]*)"[^>]*>', re.I)


def norm(s):
    """把 style 串规范化：压空白、统一 "a: b" → "a:b"、去尾分号。"""
    s = re.sub(r'\s+', ' ', s or '').strip().rstrip(';')
    s = re.sub(r'\s*:\s*', ':', s)
    s = re.sub(r'\s*;\s*', ';', s)
    return s


def decl(style, prop):
    """从 style 串里取某个属性的值（大小写不敏感，容忍空格）。"""
    m = re.search(r'(?:^|;)\s*%s\s*:\s*([^;]+)' % re.escape(prop), style, re.I)
    return m.group(1).strip() if m else None


def find_browser_act():
    for p in BROWSER_ACT_CANDIDATES:
        if p == 'browser-act':
            return p
        if os.path.exists(p):
            return p
    return None


def pick_browser(ba):
    """从 browser list 里挑一个可用实例。

    不要写死 id —— 2026-09-30 实测：写死的那个实例被另一个 browser-act 会话占着时，
    `browser open` 会失败，而下游报出来的是「取正文失败，原始输出：」加一片空白，
    完全看不出真正原因。写死还有个更常见的坏处：换台机器 / 别人重建实例就失效。
    """
    try:
        out = subprocess.run([ba, 'browser', 'list'], capture_output=True, timeout=90)
        ids = re.findall(r'id=(\S+)', out.stdout.decode('utf-8', 'replace'))
        if ids:
            return ids[0]
    except Exception:
        pass
    return None


def fetch_body_via_browser(url, timeout=240):
    """用 browser-act 打开文章并抠出 #js_content 的 outerHTML（公开文章免登录）。"""
    ba = find_browser_act()
    if not ba:
        raise RuntimeError(
            '找不到 browser-act。装法：uv tool install browser-act-cli --python 3.12\n'
            '或改用 --html 传入本地文件。')

    bid = pick_browser(ba)
    if not bid:
        raise RuntimeError(
            '没有可用的浏览器实例。先建一个：\n'
            '  browser-act browser create --type chrome --name mp-template --desc "模板反推专用"')

    # 会话名带 pid，避免与用户正在跑的其它浏览器会话撞名。
    # 撞名时 browser open 会失败，且错误信息极具误导性（实测：报「取正文失败」+空输出）。
    session = 'tmlib%d' % os.getpid()
    js = ('(() => { const c = document.querySelector("#js_content") || '
          'document.querySelector(".rich_media_content"); '
          'return JSON.stringify({ok: !!c, html: c ? c.outerHTML : null, '
          'title: (document.querySelector("#activity-name")||{}).innerText || document.title}); })()')
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='ascii') as f:
        f.write(js)
        jsfile = f.name

    def run(args, **kw):
        return subprocess.run([ba, '--session', session] + args, capture_output=True, **kw)

    try:
        op = run(['browser', 'open', '--headed', bid, url], timeout=timeout)
        opened = op.stdout.decode('utf-8', 'replace')
        if 'session_name=' not in opened and 'url=' not in opened:
            err = (op.stderr.decode('utf-8', 'replace') or opened)[:300]
            live = subprocess.run([ba, 'session', 'list'], capture_output=True,
                                  timeout=60).stdout.decode('utf-8', 'replace')
            raise RuntimeError(
                '打开失败。原始输出：%s\n'
                '提示：若上面显示已有会话占着这个浏览器，先关掉它 ——\n'
                '  browser-act session list\n  browser-act session close <名字>\n'
                '当前活动会话：%s' % (err or '(空)', live[:200] or '(无)'))
        run(['wait', 'stable'], timeout=90)
        out = run(['eval', '--stdin'], stdin=open(jsfile, 'rb'), timeout=timeout)
        text = out.stdout.decode('utf-8', 'replace')
        m = re.search(r'\{"ok".*\}', text)
        if not m:
            raise RuntimeError('取正文失败（eval 无有效返回）。'
                               'stdout %d 字节 / stderr %d 字节。前 200 字：%s'
                               % (len(out.stdout), len(out.stderr), text[:200] or '(空)'))
        d = json.loads(m.group(0))
        if not d.get('ok'):
            raise RuntimeError('页面里没有 #js_content —— 可能不是图文页，或需要登录')
        return d['html'], d.get('title') or ''
    finally:
        subprocess.run([ba, 'session', 'close', session], capture_output=True)
        os.unlink(jsfile)


def parse_tokens(html):
    """设计令牌：配色、字体、字号、圆角、阴影、字距。"""
    colors = collections.Counter(COLOR_RE.findall(html))
    ranked = [(c, n) for c, n in colors.most_common()
              if c.replace(' ', '').lower() not in
              {x.replace(' ', '').lower() for x in WECHAT_CHROME_COLORS}]
    return {
        'colors': [{'value': c, 'count': n} for c, n in ranked[:20]],
        'font_families': _top(re.findall(r'font-family:\s*([^;"\']{4,90})', html), 5),
        'font_sizes': _top(re.findall(r'font-size:\s*([\d.]+px)', html), 12),
        'line_heights': _top(re.findall(r'line-height:\s*([\d.]+(?:px|em)?)', html), 8),
        'letter_spacing': _top(re.findall(r'letter-spacing:\s*([\d.]+px)', html), 6),
        'border_radius': _top(re.findall(r'border-radius:\s*([^;"]{1,40})', html), 10),
        'box_shadow': _top(re.findall(r'box-shadow:\s*([^;"]{6,90})', html), 6),
        'padding': _top(re.findall(r'padding:\s*([^;"]{1,30})', html), 8),
        'margin': _top(re.findall(r'margin:\s*([^;"]{1,30})', html), 8),
    }


def _top(items, n):
    return [{'value': v, 'count': c} for v, c in collections.Counter(items).most_common(n)]


def analyze_structure(html):
    """通用结构事实 —— **不预设组件签名**。

    为什么需要它：`detect_components` 里的签名是从「见过的模板」总结出来的，
    遇到没见过的写法会**整类漏掉**。2026-09-30 反推第二个模板时就撞上：
    它是双圆点列表 + 1px 描边盒 + 深色块，而我的签名全来自第一个（红色卡片），
    结果只认出 dot/images/table 三项，其余全丢。

    所以这里只**陈述事实**（有哪些标签、哪些边框、哪些背景、哪些 display），
    把「这算什么组件」的判断留给人 —— 事实不会因为我没猜到而漏。
    """
    return {
        'tags': dict(collections.Counter(
            re.findall(r'<([a-zA-Z][a-zA-Z0-9]*)\b', html)).most_common(18)),
        'borders': _top(re.findall(r'borders?:\s*([^;"]{1,44})', html), 12),
        'border_sides': _top(re.findall(r'border-(?:left|right|top|bottom):\s*([^;"]{1,44})', html), 12),
        'backgrounds': _top(re.findall(r'background(?:-color)?:\s*([^;"]{2,44})', html), 12),
        'displays': _top(re.findall(r'display:\s*([a-z-]+)', html), 8),
        'flex_direction': _top(re.findall(r'flex-direction:\s*([a-z-]+)', html), 4),
        'text_align': _top(re.findall(r'text-align:\s*([a-z-]+)', html), 6),
        # 小尺寸元素（<=24px）：圆点、序号、图标、分隔条常在这里，容易被忽略
        'small_elements': _top(
            re.findall(r'(?:width|height):\s*(\d{1,2}px)', html), 12),
    }


def detect_components(html):
    """组件形态识别 —— 靠 style 签名，不靠 class（微信会剥 class）。"""
    sections = [norm(s) for s in SECTION_RE.findall(html)]
    spans = [norm(s) for s in re.findall(r'<span\b[^>]*style="([^"]*)"', html, re.I)]
    comps = {}

    def add(key, label, sig, where='section'):
        # where: section / span / both —— 圆角胶囊、圆形序号这类常挂在 <span> 上，
        # 只看 <section> 会整类漏掉（2026-09-30 实测踩到：胶囊与圆点全漏）。
        pool = sections if where == 'section' else (spans if where == 'span' else sections + spans)
        hits = [s for s in pool if sig(s)]
        if hits:
            comps[key] = {
                'label': label,
                'count': len(hits),
                'sample_style': hits[0][:400],
                'variants': [{'style': s[:400], 'n': n}
                             for s, n in collections.Counter(hits).most_common(3)],
            }

    add('card', '卡片外层（圆角 + 阴影）', lambda s: 'box-shadow' in s and 'border-radius' in s)

    def _thick_bottom(s):
        """底部实线：宽度 >= 2px"""
        v = decl(s, 'border-bottom')
        if not v:
            return False
        m = re.match(r'\s*([\d.]+)px', v)
        return bool(m) and float(m.group(1)) >= 2

    # 靠**挂载位置**区分，不靠粗细 —— 实测里标题条 3px、行内高亮 2px，
    # 用「>=2px」会把两者混成一类（一开始就是这么错的）。位置是更稳的判据。
    add('section_header', '章节标题条（挂在 section 上的底部实线）', _thick_bottom)

    add('divider', '分隔线（渐变）', lambda s: 'linear-gradient' in s and 'height:1px' in s.replace(' ', ''))

    def _thin_bar(s):
        """细横条：高度 <= 4px 且带背景。

        与 divider（渐变式）是两种做法。第三种模板用的是
        `background-color: rgba(163,236,66,0.19); height: 2px` —— 纯色、2px、无渐变，
        按「渐变 + 1px」的签名整类认不出（实测 60 处）。
        """
        hs = decl(s, 'height') or ''
        m = re.match(r'\s*([\d.]+)px', hs)
        if not m or float(m.group(1)) > 4:
            return False
        bg = decl(s, 'background') or decl(s, 'background-color') or ''
        if not bg or bg.strip().lower() in ('none', 'transparent'):
            return False
        # 渐变式的归 divider —— 不排除的话同一批元素会被两个名字各数一遍
        # （2026-09-30 回归检查抓到：红色模板 divider 13 与 thin_bar 13 完全重合）
        return 'gradient(' not in bg

    add('thin_bar', '细横条（高<=4px + 纯色底）', _thin_bar)

    # ⚠️ 别把 <svg> 当装饰件统计：微信编辑器会插一堆空占位符
    # `<svg viewBox="0 0 1 1" style="width:0" aria-label="插图"></svg>`，
    # 实测一篇里有 60 个，全是 width:0 的空壳。统计它会得出「这篇用了 60 个 SVG 图标」
    # 这种完全错误的结论。真要数 SVG 装饰，先过滤 width:0 / 无内容的。
    svg_real = [s for s in re.findall(r'<svg[^>]*>', html, re.I)
                if not re.search(r'width:\s*0(?:px)?\b', s)]
    comps['svg_real'] = {'label': 'SVG（已滤掉 width:0 的编辑器占位符）',
                         'count': len(svg_real),
                         'note': '原始 <svg> 共 %d 个，其中空占位符 %d 个'
                                 % (len(re.findall(r'<svg\b', html, re.I)),
                                    len(re.findall(r'<svg\b', html, re.I)) - len(svg_real))}
    add('quote', '引用块（左侧竖线）', lambda s: bool(decl(s, 'border-left')))
    add('pill', '胶囊标签（大圆角）',
        lambda s: (decl(s, 'border-radius') or '') in ('999px', '9999px', '100px'),
        where='both')
    add('dot', '圆形元素（序号/圆点）',
        lambda s: (decl(s, 'border-radius') or '') in ('50%', '50% '),
        where='both')
    # 已经在 where='span' 里了，凡是 span 上的 border-bottom 就是行内高亮，
    # 不需要再判粗细（加了反而会把 2px 的实线全滤掉）。
    add('highlight', '行内高亮（span 上的下划线）',
        lambda s: 'border-bottom' in s, where='span')
    comps['tables'] = {'label': '表格', 'count': html.lower().count('<table')}
    comps['images'] = {'label': '图片', 'count': html.lower().count('<img')}

    # —— 通用签名（不绑定某个模板）——
    # 这几条是从第二个模板学到的：它是双圆点列表 + 1px 描边盒 + 深色块，
    # 而当时的签名全来自第一个（红色卡片），三项全漏。
    add('bordered_box', '描边盒（1-3px 实线边框）',
        lambda s: bool(re.search(r'(?:^|;)border:\s*[123]px\s+solid', s)))
    add('list_item', '列表项（flex + 小尺寸圆点/方块）',
        lambda s: bool(re.search(r'(?:^|;)display:\s*flex', s))
        and bool(re.search(r'(?:width|height):\s*(?:[4-9]|1\d|2[0-4])px', s)))

    def _filled_label(s):
        """底色式标题条/标签块：有实色底 + 内边距，且字号偏大或居中。

        与 section_header（下划线式）是**两种不同的做法**，实测都常见 ——
        2026-09-30 反推灰调模板时就漏了它：那篇的章节头是
        `background:#222222; color:#FFFFFF; text-align:center; font-size:18px; padding:0 3px`，
        一点 border 都没有，只看 border 的签名整类认不出。
        """
        bg = decl(s, 'background') or decl(s, 'background-color') or ''
        if not bg or 'linear-gradient' in bg:
            return False
        if re.match(r'\s*(transparent|none|#fff\b|#ffffff\b|rgba?\(255,\s*255,\s*255)', bg, re.I):
            return False
        fs = decl(s, 'font-size') or ''
        m = re.match(r'\s*([\d.]+)px', fs)
        big = bool(m) and float(m.group(1)) >= 17
        centered = (decl(s, 'text-align') or '').lower() == 'center'
        return (big or centered) and bool(decl(s, 'padding'))

    add('filled_label', '底色式标题条/标签块（实色底 + 内边距 + 大字号或居中）',
        _filled_label)
    comps['lists'] = {
        'label': '原生列表 ul/ol（含 li）',
        'count': len(re.findall(r'<li\b', html, re.I)),
        'note': 'ul=%d ol=%d li=%d' % (len(re.findall(r'<ul\b', html, re.I)),
                                      len(re.findall(r'<ol\b', html, re.I)),
                                      len(re.findall(r'<li\b', html, re.I))),
    }
    comps['strong'] = {'label': '粗体引词 strong', 'count': len(re.findall(r'<strong\b', html, re.I))}
    comps['code'] = {'label': '行内代码 code', 'count': len(re.findall(r'<code\b', html, re.I))}

    # —— 微信内置组件 <mp-*> ——
    # 逐个按**实际标签名**判定，别笼统数 <mp*。实测一篇里三个 <mp*> 是两种真组件
    # 加一个无意义的样式标记 <mp-style-type>；笼统数会得出「3 个嵌入组件」这种错结论。
    # （同 SKILL.md 缺陷 #6：加检测器前先看它到底长什么样。）
    MP_KINDS = {
        'mp-common-videosnap': ('mp_video', '视频号视频卡片'),
        'mp-common-profile':   ('mp_profile', '公众号名片'),
        'mp-common-mpaudio':   ('mp_audio', '音频卡片'),
        'mp-common-miniprogram': ('mp_miniprogram', '小程序卡片'),
        'mpcpc':               ('mp_article', '文章链接卡片'),
    }
    for tag, (key, label) in MP_KINDS.items():
        n = len(re.findall(r'<%s\b' % tag, html, re.I))
        if n:
            comps[key] = {'label': label, 'count': n}
    mp_all = len(re.findall(r'<mp[a-z-]*\b', html, re.I))
    mp_known = sum(v['count'] for k, v in comps.items() if k.startswith('mp_'))
    if mp_all - mp_known > 0:
        comps['mp_other'] = {
            'label': '其他 <mp*>（多为无意义标记，如 mp-style-type）',
            'count': mp_all - mp_known,
            'note': '原始 <mp*> 共 %d 个，其中已识别的嵌入组件 %d 个' % (mp_all, mp_known),
        }

    # 原生引用块（微信自己的 js_blockquote_wrap）
    n_bq = len(re.findall(r'<blockquote\b', html, re.I))
    if n_bq:
        comps['blockquote'] = {
            'label': '原生引用块 blockquote',
            'count': n_bq,
            'note': 'class 含 js_blockquote_wrap' if 'js_blockquote_wrap' in html else '',
        }
    return {k: v for k, v in comps.items() if v.get('count')}


MANUAL_CHECKLIST = """\
## ⚠️ 人工复核清单（**必做**）

`theme.json` 只描述**数值**。数值对 ≠ 模板对。2026-09-30 实测过一次：
颜色/圆角/字号全部解析正确，但**结构错三处**，而且这三处靠读 CSS 推不出来 ——

| 我推出来的 | 实际 | 怎么发现的 |
|---|---|---|
| 章节标题条 = 左标签 + 右胶囊（两端布局） | **红方块 + 英文小字 + 中文标题**（三件套） | 渲染后并排看 |
| 引用块 = 圆角浅底 | 还多一根 **`border-left` 红竖线** | 渲染后并排看 |
| 胶囊 = 纯文字 | 内嵌一个 **6px 小红圆点** | 渲染后并排看 |

**所以请打开 `preview.png`，并排对照原文，逐条确认：**

- [ ] 卡片：圆角多大？阴影是「淡色大扩散」还是「深色小硬边」？有没有边框？
- [ ] 章节标题：是左右两端、还是「色块 + 多行文字」？色块里是数字还是文字？
- [ ] 引用块：左侧有竖线吗？圆角是四角还是只圆右侧（`0 Xpx Xpx 0`）？
- [ ] 标签/胶囊：里面有圆点或图标吗？底色是浅色还是实色？
- [ ] 序号：是圆点、方块、还是数字？圆点里有内容吗？
- [ ] 正文：字号、行高、是否两端对齐（`text-align: justify`）？
- [ ] 有没有**只在少数位置出现**的组件（容易被"最常见值"统计盖掉）？

**优先看出现次数少的组件** —— 高频值会掩盖特例，而特例往往才是模板的辨识度所在。
"""


def build_reference(name, source, title, tokens, comps, structure):
    lines = ['# 模板反推记录：%s' % name, '']
    lines.append('**来源**：%s' % source)
    if title:
        lines.append('**原文标题**：%s' % title)
    lines.append('**产出**：`theme.json` · `sample.html` · `preview.png`')
    lines.append('')
    lines.append('> 数值来自对原文 HTML 的**实测抠取**，非推测。')
    lines.append('')
    lines.append('## 一、配色')
    lines.append('')
    lines.append('| 色值 | 出现次数 |')
    lines.append('|---|---|')
    for c in tokens['colors'][:14]:
        lines.append('| `%s` | %d |' % (c['value'], c['count']))
    lines.append('')
    lines.append('（微信外壳自带的颜色已剔除：微信绿 `#07C160`、链接蓝 `#576B95` 等）')
    lines.append('')
    lines.append('## 二、排版')
    lines.append('')
    for key, label in [('font_families', '字体'), ('font_sizes', '字号'),
                       ('line_heights', '行高'), ('letter_spacing', '字距'),
                       ('border_radius', '圆角'), ('box_shadow', '阴影'),
                       ('padding', '内边距'), ('margin', '外边距')]:
        if not tokens.get(key):
            continue
        vals = ' · '.join('`%s`×%d' % (v['value'][:60], v['count']) for v in tokens[key][:6])
        lines.append('- **%s**：%s' % (label, vals))
    lines.append('')
    lines.append('## 三、组件形态')
    lines.append('')
    if comps:
        lines.append('| 组件 | 出现次数 | 实测样式（首个样本） |')
        lines.append('|---|---|---|')
        for k, v in sorted(comps.items(), key=lambda x: -x[1]['count']):
            lines.append('| **%s** | %d | `%s` |'
                         % (v['label'], v['count'], (v.get('sample_style') or '')[:160]))
    else:
        lines.append('（没识别到已知组件签名）')
    lines.append('')
    lines.append('## 四、结构事实（未预设组件签名）')
    lines.append('')
    lines.append('> 上一节是「按见过的签名归类」；这一节是**原始事实**。')
    lines.append('> 遇到没见过的写法时，签名会整类漏掉，但事实不会 —— 优先看这一节。')
    lines.append('')
    lines.append('**标签普查**：' + ' · '.join('`%s`×%d' % (k, v) for k, v in list(structure['tags'].items())[:14]))
    lines.append('')
    for key, label in [('borders', '边框'), ('border_sides', '单边线'), ('backgrounds', '背景'),
                       ('displays', 'display'), ('text_align', '对齐'), ('small_elements', '小尺寸(<=24px)')]:
        if structure.get(key):
            lines.append('- **%s**：%s' % (label, ' · '.join('`%s`×%d' % (v['value'][:34], v['count'])
                                                          for v in structure[key][:6])))
    lines.append('')
    lines.append(MANUAL_CHECKLIST)
    return '\n'.join(lines)


def fingerprint(theme):
    """模板指纹：字体 + 主色（去掉透明和无彩色噪声）。

    为什么需要：同一个公众号**反复用同一个模板**。2026-09-30 连续收两个不同链接，
    它们字体、配色、字号完全一致，是同一套样式 —— 只是第二篇更长、多露出几个组件。
    不查重的话，库里会堆一堆「看起来不同、其实是同一个」的模板，
    而且每收一个都要人工复核一遍，纯浪费。
    """
    fams = [f['value'].strip().lower() for f in theme['tokens'].get('font_families', [])]
    fams = [f for f in fams if f and not f.startswith('&quot')][:2]
    # 主色只取「有彩色」的：滤掉透明、黑白灰
    cols = []
    for c in theme['tokens'].get('colors', []):
        v = c['value'].replace(' ', '').lower()
        if v in ('rgba(0,0,0,0)', 'rgb(0,0,0)', 'rgb(255,255,255)', '#fff', '#ffffff', '#000', '#000000'):
            continue
        if re.match(r'^rgba?\((\d+),(\d+),(\d+)', v):
            r, g, b = (int(x) for x in re.match(r'^rgba?\((\d+),(\d+),(\d+)', v).groups())
            if max(r, g, b) - min(r, g, b) < 12:      # 近灰，不算特征色
                continue
        cols.append(v)
        if len(cols) >= 3:
            break
    return {'fonts': fams, 'colors': cols}


def find_duplicate(fp, out_dir, exclude=None):
    """在已有模板里找指纹相近的，返回 (名字, 说明) 或 None。"""
    for name in os.listdir(out_dir):
        if name == exclude or name.startswith('_'):
            continue
        p = os.path.join(out_dir, name, 'theme.json')
        if not os.path.exists(p):
            continue
        try:
            other = fingerprint(json.load(open(p, encoding='utf-8')))
        except Exception:
            continue
        same_font = bool(fp['fonts']) and fp['fonts'][0] in other['fonts']
        shared = set(fp['colors']) & set(other['colors'])
        # 字体相同 + 至少一个特征色相同 → 判为同一套样式
        if same_font and shared:
            return name, '字体「%s」且共有主色 %s' % (fp['fonts'][0][:34], ', '.join(sorted(shared)))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url')
    ap.add_argument('--html')
    ap.add_argument('--name', required=True, help='模板名，作为 templates/<name>/ 目录名')
    ap.add_argument('--title', default='')
    ap.add_argument('--preview', default=None, help='已有渲染图的路径（可选）')
    ap.add_argument('--no-preview', action='store_true')
    ap.add_argument('--out', default=TEMPLATES_DIR)
    a = ap.parse_args()

    if bool(a.url) == bool(a.html):
        sys.exit('必须且只能给一个：--url 或 --html')

    if a.url:
        print('用 browser-act 打开：%s' % a.url)
        html, page_title = fetch_body_via_browser(a.url)
        source = a.url
        title = a.title or page_title
        print('  抠到正文 %d 字符' % len(html))
    else:
        html = open(a.html, encoding='utf-8', errors='replace').read()
        source = os.path.abspath(a.html)
        title = a.title
        print('读入本地 HTML：%d 字符' % len(html))

    tokens = parse_tokens(html)
    comps = detect_components(html)
    structure = analyze_structure(html)

    # 查重：同一个号反复用同一个模板，不查的话库里会堆重复项
    fp = fingerprint({'tokens': tokens})
    dup = find_duplicate(fp, a.out, exclude=a.name)

    outdir = os.path.join(a.out, a.name)
    os.makedirs(outdir, exist_ok=True)

    theme = {
        'name': a.name,
        'source': source,
        'title': title,
        'body_chars': len(html),
        'tokens': tokens,
        'components': comps,
        'structure': structure,
        'fingerprint': fp,
        'duplicate_of': (dup[0] if dup else None),
        'generated_by': 'mp-template-lib/extract_theme.py',
        'note': '数值经实测抠取；结构必须靠 preview.png 人工复核，见 reference.md',
    }
    with open(os.path.join(outdir, 'theme.json'), 'w', encoding='utf-8') as f:
        json.dump(theme, f, ensure_ascii=False, indent=2)
    with open(os.path.join(outdir, 'sample.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    with open(os.path.join(outdir, 'reference.md'), 'w', encoding='utf-8') as f:
        f.write(build_reference(a.name, source, title, tokens, comps, structure))

    if a.preview and os.path.exists(a.preview):
        import shutil
        shutil.copy(a.preview, os.path.join(outdir, 'preview.png'))
        print('  预览图已收录')
    elif a.no_preview:
        pass
    else:
        print('  ⚠️ 没给 --preview，模板缺对照图 —— 人工复核那一步会做不了')

    if dup:
        print('\n  ⚠️ 同款模板已存在：%s' % dup[0])
        print('     依据：%s' % dup[1])
        print('     → 这不是新模板。若本篇样本更长/组件更全，')
        print('       考虑用它替换 %s 的 sample.html + preview.png；' % dup[0])
        print('       否则直接删掉本次产出，别在库里留重复项。')
    print('\n产出 → %s' % outdir)
    for fn in sorted(os.listdir(outdir)):
        print('  %-16s %d 字节' % (fn, os.path.getsize(os.path.join(outdir, fn))))
    print('\n下一步：打开 reference.md 的「人工复核清单」，对照 preview.png 逐条核。')


if __name__ == '__main__':
    main()
