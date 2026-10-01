#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""远程控制软件：把每一次真实会话摊开看「对方到底动了什么」。

服务日志只记录**连接建立**（`host/client recv connect request`）。要回答
「他连进来之后做了什么」，只能看每次会话拉起的 session 进程日志：
里面有逐周期的输入计数器

    session send <帧数> frame, recv <字节> mouse <鼠标事件> key <按键> text <文本>

`mouse / key / text` 是**从对端收到的输入事件**计数（ToDesk 未公开该字段定义，
按此理解；差异会体现在"有鼠标无键盘"这类形态上，可结合现场判断）。
计数器**只增不减**，所以"长时间停在同一个值"= 那段时间没人操作。

用法：
    python session_detail.py                    # 自动探测安装目录
    python session_detail.py --dir <ToDesk 安装目录>
    python session_detail.py --json out.json    # 供其他脚本消费
"""
import os, re, sys, glob, json, argparse, datetime

def _install_dirs():
    """ToDesk 装在哪**现找**，不写死盘符。

    写死盘符有两个问题：只对一台机器成立，而且那条路径本身就是那台机器的指纹。
    来源：卸载注册表的 DisplayName 里带 todesk 的项 + 标准 Program Files 位置
    （后者用环境变量拼，仍然与盘符无关）。
    """
    out, seen = [], set()

    def add(p):
        if p and p not in seen and os.path.isdir(p):
            seen.add(p)
            out.append(p)

    try:
        import winreg
        for path in (r'Software\Microsoft\Windows\CurrentVersion\Uninstall',
                     r'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'):
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
            except OSError:
                continue
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, i)
                except OSError:
                    break          # 枚举结束
                i += 1
                try:
                    sk = winreg.OpenKey(key, sub)
                    disp = str(winreg.QueryValueEx(sk, 'DisplayName')[0])
                except OSError:
                    continue
                if 'todesk' not in disp.lower():
                    continue
                # InstallLocation 常常是空的（实测 ToDesk 就是）—— 只看它会漏掉整个程序，
                # 而"没找到日志目录"读起来正好像"没人连进来过"。退到另外两个值。
                for val_name in ('InstallLocation', 'UninstallString', 'DisplayIcon'):
                    try:
                        raw = str(winreg.QueryValueEx(sk, val_name)[0]).strip()
                    except OSError:
                        continue
                    if raw.startswith('"'):
                        raw = raw[1:].split('"', 1)[0]
                    else:
                        raw = raw.split(',')[0].strip()
                    if not raw:
                        continue
                    add(raw if os.path.isdir(raw) else os.path.dirname(raw))
    except ImportError:
        pass

    for var in ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432'):
        base = os.environ.get(var)
        if base:
            add(os.path.join(base, 'ToDesk'))
    return out


CANDIDATE_DIRS = _install_dirs()
COUNTER = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+.*?'
    r'session send (-?\d+) frame, recv (-?\d+) mouse (-?\d+) key (-?\d+) text (-?\d+)')
STAMP = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')


def find_dir(explicit=None):
    if explicit:
        return explicit if os.path.isdir(explicit) else None
    for d in CANDIDATE_DIRS:
        if os.path.isdir(d):
            return d
    return None


def read_text(path):
    raw = open(path, 'rb').read()
    for enc in ('utf-8', 'gbk', 'utf-16-le'):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode('utf-8', 'ignore')


def parse_session(path):
    """Return start/end/counter samples and the input timeline of one session."""
    lines = [l for l in read_text(path).splitlines() if l.strip()]
    if not lines:
        return None
    start = STAMP.match(lines[0])
    end = STAMP.match(lines[-1])
    samples = []
    for l in lines:
        m = COUNTER.search(l)
        if m:
            samples.append({'t': m.group(1), 'send': int(m.group(2)),
                            'recv': int(m.group(3)), 'mouse': int(m.group(4)),
                            'key': int(m.group(5)), 'text': int(m.group(6))})
    # only the moments where an input counter actually moved
    changes, pm, pk, pt = [], None, None, None
    for s in samples:
        if pm is None or s['mouse'] != pm or s['key'] != pk or s['text'] != pt:
            changes.append(s)
            pm, pk, pt = s['mouse'], s['key'], s['text']
    last = samples[-1] if samples else None
    dur = None
    if start and end:
        try:
            dur = (datetime.datetime.fromisoformat(end.group(1))
                   - datetime.datetime.fromisoformat(start.group(1))).total_seconds()
        except Exception:
            pass
    return {'log': os.path.basename(path),
            'start': start.group(1) if start else None,
            'end': end.group(1) if end else None,
            'seconds': dur, 'samples': len(samples),
            'final': last, 'changes': changes}


def main():
    ap = argparse.ArgumentParser(description='remote-control session detail')
    ap.add_argument('--dir', default=None, help='install dir (auto-detected by default)')
    ap.add_argument('--json', default=None, help='also write the result as JSON')
    a = ap.parse_args()

    base = find_dir(a.dir)
    if not base:
        print('NOT_FOUND: no remote-control install dir detected')
        return 1
    logdir = os.path.join(base, 'Logs')
    if not os.path.isdir(logdir):
        print('NOT_FOUND: %s has no Logs dir' % base)
        return 1

    # 日志文件名里带日期（sessionXXXX_YYYY_MM_DD.log），据此排序
    sess = []
    for p in sorted(glob.glob(os.path.join(logdir, 'session*_*.log'))):
        r = parse_session(p)
        if r:
            sess.append(r)

    print('install dir : %s' % base)
    print('sessions    : %d' % len(sess))
    print()
    out = []
    for r in sess:
        f = r['final'] or {}
        print('-' * 70)
        print('%s   %s -> %s   (%s)' % (
            r['log'], r['start'], r['end'],
            '%dm%02ds' % (r['seconds'] // 60, r['seconds'] % 60) if r['seconds'] else '?'))
        print('  final counters : mouse=%s key=%s text=%s'
              % (f.get('mouse'), f.get('key'), f.get('text')))
        if not f.get('key') and not f.get('text'):
            print('  NOTE: no keyboard and no text input during this session.')
        print('  input timeline (only rows where a counter moved):')
        for c in r['changes']:
            print('    %s  mouse=%-7d key=%-5d text=%d' % (c['t'], c['mouse'], c['key'], c['text']))
        if r['changes']:
            last = r['changes'][-1]
            if r['end'] and last['t'] != r['end']:
                print('    ... unchanged from here until disconnect (%s -> %s idle)'
                      % (last['t'], r['end']))
        out.append(r)

    # 录制 / 文件传输产物
    print()
    print('artifacts (recording / file transfer):')
    hits = []
    for pat in ('*.mp4', '*.avi', '*.mkv', '*.tos', '*.rec'):
        hits += glob.glob(os.path.join(base, '**', pat), recursive=True)
    fc = os.path.join(os.environ.get('USERPROFILE', ''), 'Downloads', 'ToDesk')
    print('  video/rec files : %s' % (', '.join(hits) if hits else 'none'))
    print('  file-center dir : %s' % (fc if os.path.isdir(fc) else 'not present'))

    if a.json:
        with open(a.json, 'w', encoding='utf-8') as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        print('json written: %s' % a.json)
    return 0


if __name__ == '__main__':
    sys.exit(main())
