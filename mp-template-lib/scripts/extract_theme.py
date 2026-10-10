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

# 幂等：调用方（比如 import 本模块的脚本）可能已经把 stdout 包成 utf-8 了。
# 再包一层就是两个 TextIOWrapper 套同一个 buffer —— 先建的那个被 GC 时会把
# buffer 关掉，表现为后面第一句 print 报 "I/O operation on closed file"。
# 直接当 CLI 跑不会触发，但作为模块被 import 就会（2026-10-03 实测）。
if sys.platform == 'win32' and (getattr(sys.stdout, 'encoding', '') or '').lower() not in ('utf-8', 'utf8'):
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

# 判「这个颜色算不算彩色」的门槛：max(R,G,B) - min(R,G,B) 要够大。
# 取 24 是因为实测样本的两端离得很远：真强调色 rgb(0,179,139)/(66,133,244)/(250,83,89)
# 通道差都在 160 以上；而黑/近黑 rgb(15,17,21) 差 6、纯灰差 0。
# 阈值取 24 两边都不会误判（详见 2026-10-10 那次复核）。
CHROMA_MIN = 24

# 声明的值里可能含 HTML 实体，而**实体自带分号**（`&quot;`、`&#39;` …）。
# 用 `[^;]+` 取值会在实体的那个分号处断掉 —— 实测 `font-family: Optima, &quot;Microsoft YaHei&quot;, …`
# 被取成 `Optima, &quot`（缺陷 13）。所以取值时必须**先整体吃掉实体，再找真正的分号**。
# 两种写法都要覆盖：命名实体 `&quot;` 和数字实体 `&#39;` / `&#x27;`。
_ENTITY = r'&(?:[a-zA-Z][a-zA-Z0-9]*|#[0-9]+|#[xX][0-9a-fA-F]+);'


def _val(minlen, maxlen):
    """构造「取一个声明值」的正则片段：**允许值里含 HTML 实体**，长度界限照旧。

    原来各处直接写 `([^;"]{1,44})` —— 撞到 `&quot;` 里那个分号就断，
    实测 `structure.backgrounds` 里因此出现 `'url(&quot'` 这种残渣
    （aifrontline2026 ×5、graylist2026 ×3，2026-10-11 发现，是缺陷 13 的第三处副本）。
    统一走这里，就不会有一个地方修了、另一个地方还漏着。
    """
    return r'((?:%s|[^;"]){%d,%d})' % (_ENTITY, minlen, maxlen)

# 微信编辑器会在标签上留**样式副本**：`data-pm-slice`（一段 JSON，里面记着当时的 style）
# 和 `data-original-style`（该元素保存时的样式）。它们**不是生效样式** ——
# 生效的是 `style` 属性本身。扫全 HTML 的统计（配色、结构事实、bgimg_rule 的 all 池）
# 必须先去掉这两个属性的**值**，否则会把副本里的颜色/边框/尺寸算成模板的一部分。
# 实测：aifrontline 因此多出 `#3f3f3f` 这个假主色；papertoday 的 `rgba(0,0,0,0.4)`
# 计数被抬到 135（真实 83）；`data-original-style="width: 60px"` 还会让
# `style="` 的正则**匹配到副本**而不是真样式。
META_STYLE_ATTR_RE = re.compile(r'\sdata-(?:pm-slice|original-style)\s*=\s*"[^"]*"', re.I)


def strip_meta(html):
    """去掉编辑器留下的样式副本属性。**幂等**，重复调用无副作用。

    下沉到各个统计函数的入口，而不是只在 main() 里做一次 ——
    否则将来谁直接调 `parse_tokens(html)` / `analyze_structure(html)`，
    就会静默拿到被元数据污染的结果（这个库已经因为「判据静默错」栽过很多次）。
    """
    return META_STYLE_ATTR_RE.sub('', html)
# 强调色文字的元素级判据：先把整个标签取出来，再取它里面的 color 声明。
# ⚠️ 必须按「最后一个 color 声明」算：一个 style 里写了多次同属性时，**后写的生效**。
# 实测 aifrontline2026 有 4 个标签写的是 `color: rgb(255,255,255); … color: rgb(0,179,139)`
# —— 渲染出来是青绿，但只取第一个会判成白色而漏掉；反过来 papertoday2026 有 21 个
# 标签是 `color: 紫; … color: rgba(0,0,0,0.4)`，渲染出来是半黑，只取第一个会误报成紫色。
ACC_TAG_RE = re.compile(r'<(?:strong|span)\b[^>]*>', re.I)
# 只看**真正的 style 属性**。同样要挡后缀：`data-original-style="…"` 里也含 `style="`，
# 而那是编辑器存的样式副本，不是生效的样式。同时 `data-pm-slice` 这类属性里塞着编辑器
# 元数据 JSON（内含 &quot;style&quot;:&quot;…color: rgb(66,133,244);&quot;），
# 扫整个标签会把元数据里的颜色算进来 —— 实测 aifrontline2026 就多算了 1 个。
STYLE_ATTR_RE = re.compile(r'(?<![-\w])style\s*=\s*"([^"]*)"', re.I)
# 值停在 ; " ' 三处：style 里可能没有尾分号，而属性本身以引号收尾。
# ⚠️ `(?<![-\w])` 是必须的：不加的话 `color:` 会匹配到**别的属性的后缀**上 ——
# 实测 `border-color: rgba(0,0,0,0.4)`（papertoday2026，且同一条 style 里 border-style:none，
# 边框根本不画）和几乎所有 span 都带的 `-webkit-tap-highlight-color: rgba(0,0,0,0)`
# 都会被当成文字颜色。判据要匹配属性本身，不能匹配属性名的尾巴。
# （已知边界：真用 `-webkit-text-fill-color` 的模板，本判据看不到它，会按 color 算。
#   实测 9 个模板里出现 0 次。）
COL_DECL_RE = re.compile(r'(?<![-\w])color:\s*([^;"\']+)', re.I)


def is_chromatic(v):
    """color 的值是不是彩色。

    2026-10-10 前这里根本没有这个判据：只要文本里有 `color: rgb…` 就计入
    accent_text，于是「132 处纯黑 rgba(0, 0, 0, 0.9)」被报成「强调色文字 133 处」
    —— 判据的正则分支 `rgb` 会匹配上 `rgba(` 的开头，而且它从不检验颜色本身。
    所以现在必须真的把颜色解出来看通道差。
    """
    v = (v or '').strip().lower()
    m = re.match(r'rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)'
                 r'\s*(?:,\s*([\d.]+)\s*)?\)', v)
    if m:
        r, g, b = (float(m.group(i)) for i in (1, 2, 3))
        a = float(m.group(4)) if m.group(4) is not None else 1.0
        if a == 0:                      # 完全透明 = 看不见，不算强调
            return False
        return max(r, g, b) - min(r, g, b) >= CHROMA_MIN
    m = re.match(r'#([0-9a-f]{3}|[0-9a-f]{6})$', v)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = ''.join(c * 2 for c in h)
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return max(r, g, b) - min(r, g, b) >= CHROMA_MIN
    return False                        # 百分比写法/命名色等一律不算，宁可漏也不误报


def norm(s):
    """把 style 串规范化：压空白、统一 "a: b" → "a:b"、去尾分号。"""
    s = re.sub(r'\s+', ' ', s or '').strip().rstrip(';')
    s = re.sub(r'\s*:\s*', ':', s)
    s = re.sub(r'\s*;\s*', ';', s)
    return s


def decl(style, prop):
    """从 style 串里取某个属性的值（大小写不敏感，容忍空格）。

    值允许含 HTML 实体（见 `_ENTITY`）—— 否则 `url(&quot;…&quot;)` 和
    `font-family: A, &quot;B&quot;, sans-serif` 都会在实体的分号处被截断（缺陷 13）。
    """
    m = re.search(r'(?:^|;)\s*%s\s*:\s*((?:%s|[^;])+)' % (re.escape(prop), _ENTITY),
                  style, re.I)
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
    html = strip_meta(html)
    colors = collections.Counter(COLOR_RE.findall(html))
    ranked = [(c, n) for c, n in colors.most_common()
              if c.replace(' ', '').lower() not in
              {x.replace(' ', '').lower() for x in WECHAT_CHROME_COLORS}]
    return {
        'colors': [{'value': c, 'count': n} for c, n in ranked[:20]],
        # 上界从 90 提到 200：整条字体栈（含若干 &quot;引号名&quot;）本来就长过 90 字符
        'font_families': _top(
            re.findall(r'font-family:\s*((?:%s|[^;"\']){4,200})' % _ENTITY, html), 5),
        'font_sizes': _top(re.findall(r'font-size:\s*([\d.]+px)', html), 12),
        'line_heights': _top(re.findall(r'line-height:\s*([\d.]+(?:px|em)?)', html), 8),
        # 认 px / em / rem：只写 `([\d.]+px)` 会漏掉 em 写的字距（实测 damanguan2026
        # 的真实字距是 `0.034em`，而 line_heights 早就认了 em，这里漏了）
        'letter_spacing': _top(
            re.findall(r'letter-spacing:\s*([\d.]+(?:px|em|rem)?)', html), 6),
        'border_radius': _top(re.findall(r'border-radius:\s*' + _val(1, 40), html), 10),
        'box_shadow': _top(re.findall(r'box-shadow:\s*' + _val(6, 90), html), 6),
        'padding': _top(re.findall(r'padding:\s*' + _val(1, 30), html), 8),
        'margin': _top(re.findall(r'margin:\s*' + _val(1, 30), html), 8),
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
    html = strip_meta(html)
    return {
        'tags': dict(collections.Counter(
            re.findall(r'<([a-zA-Z][a-zA-Z0-9]*)\b', html)).most_common(18)),
        'borders': _top(re.findall(r'borders?:\s*' + _val(1, 44), html), 12),
        'border_sides': _top(re.findall(r'border-(?:left|right|top|bottom):\s*' + _val(1, 44), html), 12),
        'backgrounds': _top(re.findall(r'background(?:-color)?:\s*' + _val(2, 44), html), 12),
        'displays': _top(re.findall(r'display:\s*([a-z-]+)', html), 8),
        'flex_direction': _top(re.findall(r'flex-direction:\s*([a-z-]+)', html), 4),
        'text_align': _top(re.findall(r'text-align:\s*([a-z-]+)', html), 6),
        # 小尺寸元素（<=24px）：圆点、序号、图标、分隔条常在这里，容易被忽略
        'small_elements': _top(
            re.findall(r'(?:width|height):\s*(\d{1,2}px)', html), 12),
    }


def detect_components(html):
    """组件形态识别 —— 靠 style 签名，不靠 class（微信会剥 class）。"""
    html = strip_meta(html)
    sections = [norm(s) for s in SECTION_RE.findall(html)]
    spans = [norm(s) for s in re.findall(r'<span\b[^>]*style="([^"]*)"', html, re.I)]
    # 任何带 style 的标签。有些构件既不是 <section> 也不是 <span> —— 第六个模板
    # （AI前线）的章节标题横线挂在 <p> 上，只查前两个池必然整类漏掉。
    allstyles = [norm(s) for s in
                 re.findall(r'<[a-zA-Z][a-zA-Z0-9]*\b[^>]*?style="([^"]*)"', html)]
    comps = {}

    def add(key, label, sig, where='section'):
        # where: section / span / both / all —— 圆角胶囊、圆形序号这类常挂在 <span> 上，
        # 只看 <section> 会整类漏掉（2026-09-30 实测踩到：胶囊与圆点全漏）。
        if where == 'section':
            pool = sections
        elif where == 'span':
            pool = spans
        elif where == 'both':
            pool = sections + spans
        else:
            pool = allstyles
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

    def _bgurls(s):
        """取出 style 里所有 url(...) 的目标。

        ⚠️ 直接解析原始 style 串，**不要走 decl()** —— decl 用 `([^;]+)` 取值，
        而 `url(&quot;...&quot;)` 里的 HTML 实体 `&quot;` 自带一个分号，
        值会在 `&quot` 之后被截断（实测 decl 只返回 `'url(&quot'`）。
        这是 decl 的既有缺陷，凡是值里含实体的声明都取不全；
        所以判「有没有 URL」这类事，在原始串上用正则，别用 decl 的返回值。
        """
        return [m.group(1) for m in re.finditer(r'url\(\s*(.{0,400}?)\s*\)', s)]

    def _has_bgurl(s):
        """真有背景图吗 —— 空的 `url(&quot;&quot;)` 不算。

        实测见过 `background-image: url(&quot;&quot;); display: none;`：
        只判「串里有 url(」会把它数成一张背景图（AI前线因此虚高成 11，实际 10）。
        这类空 url 多是编辑器关掉某张图之后的残留。
        """
        return any(t.replace('&quot;', '').replace('&#39;', '').strip().strip('"\'')
                   for t in _bgurls(s))

    def _bgimg_rule(s):
        """背景图横线：拿一张图当分隔线 / 标题横线用。

        第六个模板（AI前线）的章节标题就是这么做的：
            background-image: url(同一张图，4 处相同)
            background-position: left 28px
            background-size: 100% 6px
        那条「绿粗线 + 小绿方块 + 浅灰长线」**整张是一幅栅格图** —— 既不是
        border 也不是 background-color。只看 CSS 数值的解析永远看不见它，
        但「一张被拉成 100% x 6px 的背景图」这个**形状**本身就是判据：
        正常的配图不会是细长条。

        判 background-size 而不是 background 简写：简写里的 `cover`（真配图）
        不该算进来，那个词根本解析不出 px。
        """
        if not _has_bgurl(s):
            return False
        parts = (decl(s, 'background-size') or '').split()
        if not parts:
            return False
        m = re.match(r'^([\d.]+)px$', parts[-1])
        return bool(m) and float(m.group(1)) <= 8

    add('bgimg_rule', '背景图横线（图被拉成细长条当分隔线）', _bgimg_rule, where='all')

    # 兜底用的**原始事实**：不判断用途，只数「有几个元素挂了背景图」。
    # 上面的 bgimg_rule 是模式识别，必然有覆盖边界；边界外的东西不会报错、
    # 只会静默消失。一句不依赖任何假设的计数能把这类漏报显示出来 ——
    # 这正是 analyze_structure() 存在的同一个理由。
    _bg_all = [s for s in allstyles if _has_bgurl(s)]
    # base64 data URI 单独数一下：实测里这类多是**空白占位图**（1x1 间隔图），
    # 不是构件。混在总数里会让人以为「这个模板用了 N 张背景图」。
    _bg_du = sum(1 for s in _bg_all
                 if 'data:' in (decl(s, 'background') or decl(s, 'background-image') or ''))
    comps['bgimg_any'] = {
        'label': '挂了背景图的元素（原始事实，未判断用途）',
        'count': len(_bg_all),
        'note': '其中被判为「横线」的 %d 个，base64 data URI %d 个（多为空白占位图，不是构件）；'
                '其余多为正常配图或平台家具' % (sum(1 for s in _bg_all if _bgimg_rule(s)), _bg_du),
    }

    # ⚠️ 别把 <svg> 当装饰件统计：微信编辑器会插一堆空占位符
    # `<svg viewBox="0 0 1 1" style="width:0" aria-label="插图"></svg>`，
    # 实测一篇里有 60 个，全是 width:0 的空壳。统计它会得出「这篇用了 60 个 SVG 图标」
    # 这种完全错误的结论。真要数 SVG 装饰，先过滤 width:0 / 无内容的。
    def _svg_placeholder(s):
        """微信编辑器插进正文、但没有装饰意义的 svg。见过两种：

        1. 空占位符 —— `<svg viewBox="0 0 1 1" style="width:0" aria-label="插图">`，
           实测一篇里 60 个，全是空壳。
        2. 圆角补角料 —— `<svg viewBox="0 0 2 2" width="4px" height="4px"
           class="border_filler border_filler_lefttop">`，编辑器画边框时四角各一块。
           第六个模板（AI前线）报出的「4 个真 SVG」**全是这个** —— 只看数字会
           得出「这篇用了 4 个 SVG 图标」，完全错误。

        判据用「尺寸/视框极小」这类**离散**特征，不用颜色粗细那类连续量。
        """
        if 'border_filler' in s:
            return True
        if re.search(r'width:\s*0(?:px)?\b', s):
            return True
        for attr in ('width', 'height'):
            m = re.search(r'\b%s\s*=\s*"([\d.]+)(?:px)?"' % attr, s, re.I)
            if m and float(m.group(1)) <= 6:
                return True
        vb = re.search(r'viewBox\s*=\s*"\s*0\s+0\s+([\d.]+)[\s,]+([\d.]+)\s*"', s, re.I)
        if vb and float(vb.group(1)) <= 4 and float(vb.group(2)) <= 4:
            return True
        return False

    svg_all = re.findall(r'<svg[^>]*>', html, re.I)
    svg_real = [s for s in svg_all if not _svg_placeholder(s)]
    if svg_all:                      # 一个 <svg> 都没有时不报这项
        comps['svg_real'] = {'label': 'SVG（已滤掉空占位符与圆角补角料）',
                             'count': len(svg_real),
                             'note': '原始 <svg> 共 %d 个，其中无装饰意义 %d 个'
                                     % (len(svg_all), len(svg_all) - len(svg_real))}
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
        # <mpcpc> 是**微信的 CPC 广告位**（class 含 js_cpc_area/cpc_iframe，style 里 display:none），
        # 属于平台家具，不是模板构件。2026-10-10 之前它被登记成 ('mp_article', '文章链接卡片') ——
        # 名字与实物无关，而真正的文章链接（<a class="…mp_article_text_link">）反而一个都没认出来。
        'mpcpc':               ('mp_cpc_ad', 'CPC 广告位（平台家具，display:none，不是模板构件）'),
    }
    mp_known = 0                      # 只累加**实际匹配到的 <mp*> 标签数**
    for tag, (key, label) in MP_KINDS.items():
        n = len(re.findall(r'<%s\b' % tag, html, re.I))
        if n:
            comps[key] = {'label': label, 'count': n}
            mp_known += n
    mp_all = len(re.findall(r'<mp[a-z-]*\b', html, re.I))
    # ⚠️ 这里曾写成 sum(... if k.startswith('mp_'))。那是**靠键名前缀猜「是不是 <mp*> 组件」**，
    # 只要新增一个以 mp_ 开头、但来源不是 <mp*> 的键（比如下面的文章链接），
    # 就会把它错算成已知组件，把 mp_other 的计数吃掉甚至算成负数。
    # 现在改成按标签精确累加，与键名叫什么无关。
    # 正文里的站内文章链接：**不是** <mp*> 组件，是普通 <a> 标签（文末「相关链接：」那类）。
    n_al = len(re.findall(r'<a\b[^>]*mp_article_text_link', html, re.I))
    if n_al:
        comps['article_link'] = {
            'label': '正文文章链接（纯文本站内链接）',
            'count': n_al,
            'note': 'class 含 mp_article_text_link；是文字链接，不是卡片',
        }
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

    # 图 + 图注（学术/技术文常见）
    n_fig, n_cap = len(re.findall(r'<figure\b', html, re.I)), len(re.findall(r'<figcaption\b', html, re.I))
    if n_fig or n_cap:
        comps['figure_caption'] = {
            'label': '图 + 图注 figure/figcaption',
            'count': max(n_fig, n_cap),
            'note': 'figure=%d figcaption=%d' % (n_fig, n_cap),
        }

    # 标题层级普查（微信公众号正文里 h1~h6 都不会被剥，是原生的）
    heads = {h: len(re.findall(r'<%s\b' % h, html, re.I)) for h in ('h1', 'h2', 'h3', 'h4')}
    if any(heads.values()):
        comps['headings'] = {
            'label': '标题元素 h1~h4',
            'count': sum(heads.values()),
            'note': ' '.join('%s=%d' % (k, v) for k, v in heads.items() if v),
        }

    # 网格/纹理背景：小尺寸平铺（repeat + 20px 之类）
    if re.search(r'(?:linear-gradient|url)[^;"]{0,120}\brepeat\b', html) and \
       re.search(r'/\s*(?:1[0-9]|2[0-9]|3[0-9])px\s+(?:1[0-9]|2[0-9]|3[0-9])px', html):
        comps['tiled_bg'] = {'label': '平铺网格/纹理背景（小尺寸 repeat）',
                             'count': len(re.findall(r'\brepeat\b', html))}

    # 强调色文字：strong/span 上带**彩色**的 color。
    # 两道都必须有：① 真去解析颜色（见 is_chromatic 的注释）—— 只看「有没有 color: rgb…」
    # 这个语法会把满篇黑字也算进来；② 按每个元素**最后一条** color 声明算（见 ACC_TAG_RE 的注释）。
    cands = []
    for m in ACC_TAG_RE.finditer(html):
        cols = []
        for sa in STYLE_ATTR_RE.findall(m.group(0)):   # 只认真正的 style 属性
            cols += COL_DECL_RE.findall(sa)
        if cols:
            cands.append(cols[-1].strip())      # 后写的生效
    chrom = [c for c in cands if is_chromatic(c)]
    if chrom:
        comps['accent_text'] = {
            'label': '强调色文字（strong/span 带彩色）',
            'count': len(chrom),
            'note': '%d 个 strong/span 带 color 声明，其中 %d 个最终是黑/灰/透明被剔除'
                    % (len(cands), len(cands) - len(chrom)),
        }
    elif cands:
        # 有候选但一个都不彩色 —— 这是个有信息量的 0，不能默默消失
        # （同缺陷 #12：读者要能分清「滤光了」和「检测器根本没跑」）。
        comps['accent_text'] = {
            'label': '强调色文字（strong/span 带彩色）',
            'count': 0,
            'note': '有 %d 个 strong/span 写了 color 声明，但最终全是黑/灰/透明 —— 这篇没有强调色文字'
                    % len(cands),
        }

    # 默认丢掉 count=0 的项（「没有卡片」不值得单独占一行）。
    # svg_real 例外：它的 0 是有信息量的 —— 「有 <svg> 标签，但没有一个是真的」。
    # 丢掉它，读者就分不清「滤光了」和「检测器根本没跑」，本次改动也就静默了
    # （2026-10-03 改过滤器后的回归里正是这么踩到的）。
    # accent_text 同理（2026-10-10 加）：它的 0 也可能是「有 color 声明但全是黑字」。
    KEEP_ZERO = ('svg_real', 'accent_text')
    return {k: v for k, v in comps.items() if v.get('count') or k in KEEP_ZERO}


def detect_generator(html):
    """识别这篇是用哪个排版工具生成的。

    实测发现这是**套模板的捷径**：很多公众号文章不是手写的，而是用排版工具
    （mdnice / 135editor 等）生成，它们会把自己的标记留在标签上：

        data-tool="mdnice编辑器"        ← PaperToday 那篇
        label="edit by 135editor"       ← 红色卡片那篇

    一旦知道是哪个工具 + 哪个主题，就不必逐条逆向了 ——
    直接去那个工具里选同名主题即可。所以这个字段比组件清单更值钱。
    """
    hits = []
    for pat in (r'data-tool="([^"]{2,30})"', r'label="edit by ([^"]{2,30})"',
                r'data-pluginname="([^"]{2,30})"'):
        hits += re.findall(pat, html)
    seen = []
    for h in hits:
        if h not in seen and h not in ('mpvideosnap', 'mpprofile'):
            seen.append(h)
    return seen


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

    # 统计一律跑在**去掉编辑器样式副本**的 HTML 上（见 META_STYLE_ATTR_RE）。
    # 写进 sample.html 的仍是原始 html —— 那份要留作对照，不能动。
    analysis_html = META_STYLE_ATTR_RE.sub('', html)
    if len(analysis_html) != len(html):
        print('  剔除编辑器元数据 %d 字符' % (len(html) - len(analysis_html)))

    tokens = parse_tokens(analysis_html)
    comps = detect_components(analysis_html)
    structure = analyze_structure(analysis_html)
    generator = detect_generator(html)      # 这个判的是「哪个编辑器生成的」，用原始 html

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
        'generator': generator,
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
