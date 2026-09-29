#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""北森（phoenix）表单的填表原语。这些子命令都是在真表单上试出来、并各自对应一个
"不这么做就会静默失败"的坑，合并成一个工具是为了下次不用再从头手写 JS。

用法（都要带 `--session`，默认 apply）：

    python formkit.py dump                      # 全表字段：标题/控件/当前值，并给每项挂 #wf-f<N>
    python formkit.py value "#wf-f19"            # 读一个控件的 value
    python formkit.py options                    # 当前打开的弹层里有哪些选项（挂 #wf-opt-N）
    python formkit.py pick 钦州市                 # 在弹层里选中一行（自动试落点，按"已选计数"判断）
    python formkit.py date 2024-09                # 在打开的日期面板里跳到该年月
    python formkit.py blocks                      # 列可重复块（项目经历/工作经历）的名称/职务/起止/描述长度
    python formkit.py block-fill --key AQMAT --name ... --role ... --start 2025-05 --end 2025-10 --desc ...
    python formkit.py block-text --key AQMAT --name ... --role ... --desc ...     # 只改文字，不碰日期
    python formkit.py block-now  --key weflow-cli  # 勾该块「结束时间」旁的「至今」
    python formkit.py click-text 确认投递           # 按文字点（唯一命中才点）
    python formkit.py collect                     # 把虚拟化列表滚一遍收集全部选项

设计上的三条硬规矩（都是从翻车里总结的）：

1. **能按"名称/文字"定位就不要按序号。** 序号在重渲染、尤其是页面重载后会全变；
   重复块还会**按结束时间自己重排**（实测：填完 2026-08 那条它跳到了第一位）。
2. **一次只动一个东西，动完立刻复读。** 受控组件"看着填上了、其实没进状态"是这类页面
   最常见的失败，只有读回来才看得见。
3. **不猜。** 命中 0 个或 ≥2 个一律停手，不去赌第一个是对的。
"""
import argparse
import json
import os
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from preflight import resolve_browser_act
except Exception:                                    # preflight 不在时退化成 PATH
    def resolve_browser_act():
        import shutil
        p = shutil.which('browser-act')
        return ([p], 'PATH') if p else (None, '没找到')

SESSION = 'apply'

# ---------------------------------------------------------------------------
# 在页面里执行的 JS。全部只做两类事：给元素挂临时 id（为了能用 --selector 点/填），
# 以及**读** DOM（读值不算"用 JS 改状态"，那条红线指的是 setValue）。
# ---------------------------------------------------------------------------

DUMP_JS = r'''
(() => {
  const items = [...document.querySelectorAll('.form-item--phoenix')];
  const title = it => ((it.querySelector('.form-item__title') || {}).innerText || '').replace(/\s+/g, '');
  const pad = (s, n) => (String(s) + ' '.repeat(n)).slice(0, n);
  const rows = items.map((it, i) => {
    const c = it.querySelector('.form-item__control') || it;
    const ctrl = c.querySelector('input, textarea, select');
    const t = title(it);
    if (ctrl) ctrl.id = 'wf-f' + i;
    const tag = ctrl ? ctrl.tagName.toLowerCase() : (c.querySelector('[class*=select]') ? 'div.select' : '(无控件)');
    let v = '';
    if (ctrl) v = String(ctrl.value == null ? '' : ctrl.value);
    else v = (c.innerText || '');
    v = v.replace(/\s+/g, ' ').trim();
    return pad(i, 4) + '| ' + pad(t, 14) + '| ' + pad(tag, 12) + '| ' + v.slice(0, 44);
  });
  return '共 ' + items.length + ' 个 form-item\n' + rows.join('\n');
})()
'''

# 弹层里的选项：北森有两套渲染，普通下拉是 li.phoenix-selectList__listItem，
# 地区/行业那种用 div.area-item-name —— **两套都要收**，只收一套会把
# "面板开了但选择器没匹配上"误判成"控件不响应"（实测栽过）。
OPTION_SELECTORS = [
    '.phoenix-selectList__listItem', '.area-item-name', '.area-text-label',
    '.phoenix-autocomplete__listItem', '.phoenix-cascader__listItem',
    '.list-item-container', '.area-item-container',
]

LIST_OPTIONS_JS = r'''
(() => {
  const sels = %s;
  const seen = new Set(); const out = [];
  for (const s of sels) {
    for (const e of document.querySelectorAll(s)) {
      if (e.offsetParent === null) continue;
      const t = (e.innerText || '').replace(/\s+/g, ' ').trim();
      if (!t || seen.has(t)) continue;
      seen.add(t); out.push(t);
    }
  }
  const all = [...document.querySelectorAll('li, .area-item-container')].filter(e => e.offsetParent !== null);
  all.forEach(e => { e.removeAttribute('data-wf-opt'); });
  const tagged = [...document.querySelectorAll('li, .area-item-container')]
      .filter(e => e.offsetParent !== null
                   && out.includes((e.innerText || '').replace(/\s+/g, ' ').trim()));
  tagged.forEach((e, i) => { e.id = 'wf-opt-' + i; e.setAttribute('data-wf-opt', out[i] || ''); });
  return out.length ? out.map((t, i) => i + ':' + t).join(' | ') : '(面板里没有可读的选项)';
})()
''' % json.dumps(OPTION_SELECTORS)

COUNT_JS = ('(() => { const m = document.body.innerText.match(/已选(?:地区)?\\s*(\\d+)\\s*\\/\\s*(\\d+)/);'
            ' return m ? m[1] + "/" + m[2] : "(无计数)"; })()')

# 可重复块：项目经历用「项目名称」，工作经历用「公司名称」。
BLOCKS_JS = r'''
(() => {
  const t = it => ((it.querySelector('.form-item__title') || {}).innerText || '').replace(/\s+/g, '');
  const items = [...document.querySelectorAll('.form-item--phoenix')];
  const val = k => { const c = k.querySelector('input, textarea'); return c ? String(c.value == null ? '' : c.value) : ''; };
  const out = [];
  items.forEach((it, i) => {
    const ti = t(it);
    if (ti !== '项目名称' && ti !== '公司名称') return;
    const kind = ti === '项目名称' ? '项目' : '工作';
    const fields = [];
    for (let k = 1; k < 5; k++) {
      const nx = items[i + k];
      if (!nx) break;
      const nt = t(nx);
      if (nt === '项目名称' || nt === '公司名称') break;
      fields.push([nt, val(nx)]);
    }
    const g = n => { const f = fields.find(f => f[0] === n); return f ? f[1] : ''; };
    out.push(kind + ' 块' + out.length + ' ｜ 名称=' + JSON.stringify(val(it).slice(0, 34))
             + ' ｜ 职务/职位=' + JSON.stringify(g('职务') || g('职位名称'))
             + ' ｜ 起=' + JSON.stringify(g('开始时间')) + ' 止=' + JSON.stringify(g('结束时间'))
             + ' ｜ 描述=' + (g('项目描述') || g('工作职责')).length + ' 字');
  });
  return out.length ? out.join('\n') : '(没有找到可重复块)';
})()
'''

# 日期面板：**按 state 序号操作，不用 --selector 点**。
#
# 为什么：面板里的 `<a class="phoenix-calendar-month-panel-prev-year">` 这类类名我在探针里
# 见过，但**从没用它们点过** —— 今天跑通的那条路是"读 state、按序号点"。而 --selector 点击
# 在弹层里**静默失败过**（.area-item-name 点了没反应也不报错）。所以这里照搬验过的做法：
# 日历块里有三个裸 `<a role=button />`，顺序是 上一年 / 年份 / 下一年，
# 用"它下一行是不是 4 位年份"认出年份那个，别按位置猜。
DATE_STATE_JS = r'''
(() => {
  const lines = %s;
  let start = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes('phoenix-calendar-month-calendar')) { start = i; break; }
  }
  if (start < 0) return JSON.stringify({ err: '面板不在 state 里（是不是被关掉了？）' });
  const arrows = [], years = {}, months = {};
  let cur = null;
  for (let i = start; i < start + 140 && i < lines.length; i++) {
    const ln = lines[i];
    let m = ln.match(/^\s*\[(\d+)\]<a role=button\s*\/>/);
    if (m) { arrows.push(parseInt(m[1], 10)); cur = ['arrow', parseInt(m[1], 10)]; continue; }
    m = ln.match(/^\s*\[(\d+)\]<a class=phoenix-calendar-month-panel-month\s*\/>/);
    if (m) { cur = ['month', parseInt(m[1], 10)]; continue; }
    const t = ln.trim();
    if (cur && t) {
      if (cur[0] === 'arrow' && /^\d{4}$/.test(t)) years[cur[1]] = parseInt(t, 10);
      else if (cur[0] === 'month' && /^\d{1,2}月$/.test(t)) months[t] = cur[1];
      cur = null;
    }
  }
  const ykeys = Object.keys(years);
  if (arrows.length < 3 || !ykeys.length) return JSON.stringify({ err: '没认出年份/箭头' });
  const yi = parseInt(ykeys[0], 10);
  const pos = arrows.indexOf(yi);
  return JSON.stringify({ cur: years[yi], prev: pos > 0 ? arrows[pos - 1] : null,
                          next: pos + 1 < arrows.length ? arrows[pos + 1] : null, months: months });
})()
'''

# 「至今」复选框**不在**结束时间 form-item 的子树里（按子树找过一次，落空）。
# 归属规则：它是"它之前最近的那个 项目名称/公司名称 输入框"所属的块。
OWNER_FN = r'''
  const t = it => ((it.querySelector('.form-item__title') || {}).innerText || '').replace(/\s+/g, '');
  const items = [...document.querySelectorAll('.form-item--phoenix')];
  const anchors = [];
  items.forEach(it => {
    const ti = t(it);
    if (ti === '项目名称' || ti === '公司名称') {
      const inp = it.querySelector('input, textarea');
      if (inp) anchors.push({ kind: ti, el: inp });
    }
  });
  const ownerOf = el => {
    let best = -1;
    anchors.forEach((a, ai) => {
      if (a.el.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) best = ai;
    });
    return best;
  };
'''

ZHI_JS = r'''
(() => {
{owner}
  const key = %s;
  const cbs = [...document.querySelectorAll('.phoenix-checkbox')]
      .filter(e => (e.innerText || '').replace(/\s+/g, '') === '至今');
  const hits = cbs.filter(cb => {
    const b = ownerOf(cb);
    return b >= 0 && String(anchors[b].el.value || '').includes(key);
  });
  if (hits.length !== 1) return '命中 ' + hits.length + ' 个「至今」，停手';
  hits[0].id = 'wf-zhi';
  return 'checked=' + (hits[0].querySelector('input[type=checkbox]') || {}).checked;
})()
'''

DEL_JS = r'''
(() => {
{owner}
  const key = %s;
  const dels = [...document.querySelectorAll('span, div, button')]
      .filter(e => (e.innerText || '').trim() === '删除' && e.children.length === 0);
  const hits = dels.filter(d => {
    const b = ownerOf(d);
    return b >= 0 && String(anchors[b].el.value || '').includes(key);
  });
  if (hits.length !== 1) return '命中 ' + hits.length + ' 个「删除」，停手';
  hits[0].id = 'wf-del';
  return 'ready';
})()
'''

# 按文字点：唯一命中才点（同 resolveUniqueTalker 的"只认唯一、不猜"）
CLICK_TEXT_JS = r'''
(() => {
  const want = %s;
  const els = [...document.querySelectorAll('button, span, div, a, label')]
      .filter(e => e.children.length === 0 && e.offsetParent !== null
                   && (e.innerText || '').replace(/\s+/g, ' ').trim() === want);
  if (els.length !== 1) return '命中 ' + els.length + ' 个「' + want + '」，停手';
  els[0].id = 'wf-click';
  return 'ready';
})()
'''

# 虚拟化列表：滚出视野的项会被回收，所以要**边滚边收集**再并集。
COLLECT_JS = r'''
(() => {
  const sels = %s;
  const seen = new Set(); const out = [];
  for (const s of sels) {
    for (const e of document.querySelectorAll(s)) {
      if (e.offsetParent === null) continue;
      const t = (e.innerText || '').replace(/\s+/g, ' ').trim();
      if (t && !seen.has(t)) { seen.add(t); out.push(t); }
    }
  }
  return out.join('\n');
})()
''' % json.dumps(OPTION_SELECTORS)


class Kit:
    def __init__(self, session, timeout=300):
        self.exe, self.how = resolve_browser_act()
        self.session = session
        self.timeout = timeout
        if not self.exe:
            raise SystemExit('找不到 browser-act —— 先跑 scripts/preflight.py 看怎么装/怎么调')

    def act(self, args, timeout=None):
        r = subprocess.run(self.exe + ['--session', self.session] + args,
                           capture_output=True, text=True, encoding='utf-8', errors='replace',
                           timeout=timeout or self.timeout)
        return ((r.stdout or '') + (r.stderr or '')).strip()

    def js(self, code):
        return self.act(['eval', code])

    def click(self, selector):
        return self.act(['click', '--selector', selector])

    def fill(self, selector, text):
        self.act(['input', '--selector', selector, '--text', text, '--mode', 'fill'])
        return self.js('(() => { const e = document.querySelector(%s); return e ? String(e.value) : "(读不到)"; })()'
                       % json.dumps(selector))

    def count(self):
        return self.js(COUNT_JS)


# --------------------------------- 子命令 ---------------------------------

def cmd_dump(kit, a):
    print(kit.js(DUMP_JS))


def cmd_value(kit, a):
    print(kit.js('(() => { const e = document.querySelector(%s); return e ? String(e.value) : "(找不到)"; })()'
                 % json.dumps(a.selector)))


def cmd_options(kit, a):
    print(kit.js(LIST_OPTIONS_JS))


def cmd_pick(kit, a):
    """在弹层里选中一行。

    坑：`.area-item-name` / `.area-item-container` 用 --selector 点下去**不报错也不选中**
    （计数纹丝不动），而点 `.icon-container`（那个单选圈/复选框的图标容器）是灵的。
    所以这里逐个候选落点试，用"已选计数变没变"当判据 —— 不然会得到"控件不响应"的错误结论。
    """
    before = kit.count()
    cands = ['.icon-container', '.area-item-name', '.item-text-label', '.area-item-container']
    for sel in cands:
        js = (r'''(() => {
          const want = %s;
          const rows = [...document.querySelectorAll('.area-item-container, .list-item-container')]
              .filter(e => e.offsetParent !== null && (e.innerText || '').includes(want));
          if (rows.length !== 1) return '行命中 ' + rows.length + ' 个，停手';
          const hits = [...rows[0].querySelectorAll(%s)].filter(e => e.offsetParent !== null);
          if (hits.length !== 1) return '落点 ' + %s + ' 命中 ' + hits.length + ' 个';
          hits[0].id = 'wf-pick';
          return 'ready';
        })()''' % (json.dumps(a.text), json.dumps(sel), json.dumps(sel)))
        if kit.js(js) != 'ready':
            continue
        kit.click('#wf-pick')
        time.sleep(1.0)
        now = kit.count()
        if now != before:
            print('选中了（落点 %s）｜计数 %s → %s' % (sel, before, now))
            return
    print('四个候选落点全都没反应（计数仍是 %s）' % before)


def cmd_date(kit, a):
    """在打开的日期面板里跳到 YYYY-MM。

    **每一跳都重新读一遍 state**：跳一次年面板就重渲染，旧序号全失效。
    """
    want_y, want_m = (int(x) for x in a.ym.split('-'))
    label = '%d月' % want_m
    for _ in range(14):
        lines = kit.act(['state']).split('\n')
        info = json.loads(kit.js(DATE_STATE_JS % json.dumps(lines)))
        if 'err' in info:
            print(info['err'])
            return
        cur = info['cur']
        if cur == want_y:
            if label not in info['months']:
                print('面板里没有 %s，实际有 %s' % (label, '/'.join(info['months'])))
                return
            print('点击月份序号', info['months'][label], '→', kit.act(['click', str(info['months'][label])]))
            time.sleep(0.6)
            return
        idx = info['prev'] if want_y < cur else info['next']
        if idx is None:
            print('找不到换年箭头（当前 %s，要 %s）' % (cur, want_y))
            return
        kit.act(['click', str(idx)])
        time.sleep(0.5)
    print('跳了 14 次还没到 %d 年' % want_y)


def cmd_blocks(kit, a):
    print(kit.js(BLOCKS_JS))


def _block_index(kit, key):
    """按"名称里含 key"定位块的序号；不唯一就返回 None。"""
    js = r'''(() => {
      const t = it => ((it.querySelector('.form-item__title') || {}).innerText || '').replace(/\s+/g, '');
      const items = [...document.querySelectorAll('.form-item--phoenix')];
      const out = [];
      items.forEach((it, i) => {
        if (t(it) !== '项目名称' && t(it) !== '公司名称') return;
        const c = it.querySelector('input, textarea');
        const v = c ? String(c.value || '') : '';
        if (v.includes(%s)) out.push([v, i]);
      });
      return JSON.stringify(out);
    })()''' % json.dumps(key)
    raw = kit.js(js)
    try:
        hits = json.loads(raw)
    except Exception:
        print('定位失败:', raw[:200])
        return None
    if len(hits) != 1:
        print('命中 %d 个块，停手（要么没有、要么多个，不猜）' % len(hits))
        return None
    return hits[0][1]


def _tag_block(kit, start):
    """给该块的五个字段挂 id（块 = 「项目名称/公司名称」及其后四项）。"""
    js = r'''(() => {
      const t = it => ((it.querySelector('.form-item__title') || {}).innerText || '').replace(/\s+/g, '');
      const items = [...document.querySelectorAll('.form-item--phoenix')];
      const ids = ['name', 'role', 'start', 'end', 'desc'];
      const got = [];
      for (let k = 0; k < 5; k++) {
        const it = items[%d + k];
        if (!it) return '块不完整，只到第 ' + k + ' 项';
        const c = it.querySelector('input, textarea, select');
        if (c) c.id = 'wf-b-' + ids[k];
        got.push(t(it));
      }
      return got.join('/');
    })()''' % start
    return kit.js(js)


def cmd_block_text(kit, a):
    """只改名称/职务/描述，**不碰日期**。

    改排版（比如去掉中英之间我多加的空格）时用这个：为了改一句话把起止时间重选一遍，
    既慢又容易选错。
    """
    idx = _block_index(kit, a.key)
    if idx is None:
        return
    print('块字段:', _tag_block(kit, idx))
    for sel, text in (('name', a.name), ('role', a.role), ('desc', a.desc)):
        if text is None:
            continue
        got = kit.fill('#wf-b-' + sel, text)
        print('  %s = %s' % (sel, got[:50]))


def cmd_block_fill(kit, a):
    idx = _block_index(kit, a.key)
    if idx is None:
        return
    print('块字段:', _tag_block(kit, idx))
    for sel, text in (('name', a.name), ('role', a.role), ('desc', a.desc)):
        if text is None:
            continue
        kit.fill('#wf-b-' + sel, text)
    for sel, ym in (('start', a.start), ('end', a.end)):
        if ym in (None, '-'):
            print('  %s 留空（调用方指定不填：简历上只有年份、或写的是「至今」时**不要编月份**）' % sel)
            continue
        kit.click('#wf-b-' + sel)
        time.sleep(1.2)
        cmd_date(kit, argparse.Namespace(ym=ym))
        print('  %s = %s' % (sel, kit.js('(() => { const e = document.getElementById("wf-b-%s");'
                                        ' return e ? e.value : "(读不到)"; })()' % sel)))
    print(kit.js(BLOCKS_JS))


def cmd_block_now(kit, a):
    """勾某块的「至今」。"""
    js = ZHI_JS.replace('{owner}', OWNER_FN) % json.dumps(a.key)
    print(kit.js(js))
    print('点击:', kit.click('#wf-zhi'))
    time.sleep(0.8)
    print('回读:', kit.js(js))


def cmd_block_delete(kit, a):
    js = DEL_JS.replace('{owner}', OWNER_FN) % json.dumps(a.key)
    r = kit.js(js)
    print(r)
    if r == 'ready':
        print('点击:', kit.click('#wf-del'))


def cmd_click_text(kit, a):
    r = kit.js(CLICK_TEXT_JS % json.dumps(a.text))
    print(r)
    if r == 'ready':
        print('点击:', kit.click('#wf-click'))


def cmd_collect(kit, a):
    """把虚拟化的选项列表滚一遍收集齐。

    列表滚出视野的项会被**回收**（DOM 里直接没了），所以必须边滚边取并集；
    而且 `scroll up --amount 4000` 一次滚不回顶部，要多次小幅滚。
    """
    seen, order = set(), []
    for _ in range(12):
        kit.act(['scroll', 'up', '--amount', '300'])
        time.sleep(0.25)
    time.sleep(0.6)
    stale = 0
    for _ in range(60):
        added = 0
        for t in kit.js(COLLECT_JS).split('\n'):
            t = t.strip()
            if t and t not in seen:
                seen.add(t)
                order.append(t)
                added += 1
        stale = stale + 1 if added == 0 else 0
        if stale >= 3:
            break
        kit.act(['scroll', 'down', '--amount', '400'])
        time.sleep(0.5)
    print('共收集 %d 项：' % len(order))
    print(' | '.join('%d:%s' % (i + 1, t) for i, t in enumerate(order)))


def main():
    ap = argparse.ArgumentParser(description='北森表单填表原语')
    ap.add_argument('--session', default=SESSION, help='browser-act 会话名（默认 apply）')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sub.add_parser('dump', help='全表字段').set_defaults(fn=cmd_dump)

    p = sub.add_parser('value', help='读一个控件的值')
    p.add_argument('selector')
    p.set_defaults(fn=cmd_value)

    sub.add_parser('options', help='列当前弹层的选项').set_defaults(fn=cmd_options)

    p = sub.add_parser('pick', help='在弹层里选中一行')
    p.add_argument('text')
    p.set_defaults(fn=cmd_pick)

    p = sub.add_parser('date', help='在打开的日期面板里选年月')
    p.add_argument('ym', help='YYYY-MM')
    p.set_defaults(fn=cmd_date)

    sub.add_parser('blocks', help='列可重复块').set_defaults(fn=cmd_blocks)

    p = sub.add_parser('block-fill', help='按名称定位并填一个块（含日期）')
    p.add_argument('--key', required=True, help='块名称的子串（唯一才动手）')
    p.add_argument('--name'); p.add_argument('--role')
    p.add_argument('--start'); p.add_argument('--end')
    p.add_argument('--desc')
    p.set_defaults(fn=cmd_block_fill)

    p = sub.add_parser('block-text', help='只改块的文字，不碰日期')
    p.add_argument('--key', required=True)
    p.add_argument('--name'); p.add_argument('--role'); p.add_argument('--desc')
    p.set_defaults(fn=cmd_block_text)

    p = sub.add_parser('block-now', help='勾某块的「至今」')
    p.add_argument('key')
    p.set_defaults(fn=cmd_block_now)

    p = sub.add_parser('block-delete', help='删掉某块（先确认它不是删不掉的必填段）')
    p.add_argument('key')
    p.set_defaults(fn=cmd_block_delete)

    p = sub.add_parser('click-text', help='按文字点（唯一命中才点）')
    p.add_argument('text')
    p.set_defaults(fn=cmd_click_text)

    sub.add_parser('collect', help='滚一遍收集虚拟化列表的全部选项').set_defaults(fn=cmd_collect)

    a = ap.parse_args()
    kit = Kit(a.session)
    a.fn(kit, a)
    return 0


if __name__ == '__main__':
    sys.exit(main())
