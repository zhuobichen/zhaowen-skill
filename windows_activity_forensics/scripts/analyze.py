# -*- coding: utf-8 -*-
"""Build a self-contained HTML report of local QQ / WeChat execution traces.

Console output is deliberately ASCII-only (a GBK console crashes on printing
non-ASCII, and that crash happens *after* the file has already been written, so
it looks like a generation failure when it is not).

Everything the report asserts about the machine is collected at run time; there
are no hand-copied verdicts baked into the text.
"""
import os, sys, json, glob, struct, datetime, html, re, shutil, sqlite3, argparse, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prefetch_parse          # 同目录，解 MAM 压缩的 Prefetch（见该文件顶部说明）

_ap = argparse.ArgumentParser(description='Local activity / remote-access forensics report')
_ap.add_argument('--days', type=int, default=2,
                 help='window length in days ending at --to (default 2 = yesterday + today)')
_ap.add_argument('--to', dest='dto', default=None,
                 help='last day of the window, YYYY-MM-DD (default today)')
_ap.add_argument('--from', dest='dfrom', default=None,
                 help='first day of the window (overrides --days), YYYY-MM-DD')
_ap.add_argument('--work', default=None,
                 help='directory holding the collector JSON (default %%TEMP%%\\activity_forensics)')
_ap.add_argument('--out', default=None,
                 help='output HTML path (default: Desktop\\activity_report.html)')
_ARGS = _ap.parse_args()

HOME = os.environ.get('USERPROFILE') or os.path.expanduser('~')
WORK = _ARGS.work or os.path.join(tempfile.gettempdir(), 'activity_forensics')
PF   = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'Prefetch')
OUT  = _ARGS.out or os.path.join(HOME, 'Desktop', 'activity_report.html')

def fixed_drives():
    """所有固定盘（排除可移动/光驱/网络盘）。

    「只看 C 盘」是这类工具最常见的静默漏检来源：回收站、下载目录都可能
    在别的盘上。宁可多扫，也不要因为没列全而报一个假的 0。
    """
    out = []
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(512)
        n = ctypes.windll.kernel32.GetLogicalDriveStringsW(512, buf)
        for d in buf[:n].split('\x00'):
            if d and ctypes.windll.kernel32.GetDriveTypeW(d) == 3:
                out.append(d)
    except Exception:
        out = ['C:\\']
    return out


KEYS = ('qq', 'weixin', 'wechat', 'tencent', 'napcat', 'multiw')
# WeGame / LoL family. WeGame 通常就装在 LoL 的安装目录下（同一个父目录）。
# 具体路径由 collect.ps1 按固定盘扫出并写进 app_roots.json，这里只认名字。
GAME_KEYS = ('wegame', 'tcls', 'taslogin', 'crossproxy', 'riotclient',
             'league', 'pallas', 'tenio', 'lolai')
TRACE_KEYS = KEYS + GAME_KEYS
# Strict pattern: an actual QQ / WeChat client executable or the multi-open tool.
STRICT = re.compile(r'(?i)(qq\.exe|qq\.lnk|weixin|wechat|wechatappex|xwechat|multi_wechat|napcat|tencent\\qq|tencent\\wechat)')


def load(name, default=None):
    try:
        with open(os.path.join(WORK, name), 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        return default if default is not None else []


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def ft_to_dt(v):
    """Windows FILETIME -> naive LOCAL datetime.

    FILETIME counts 100ns ticks since 1601-01-01 **UTC**. Building the datetime
    with `1601-01-01 + timedelta` therefore yields UTC, which on a UTC+8 machine
    lands 8 hours off every other timestamp in this report (Prefetch mtimes and
    event-log times are both local). Convert through epoch seconds instead and
    let fromtimestamp() apply the local offset.
    """
    if not v or v <= 0:
        return None
    try:
        return datetime.datetime.fromtimestamp(v / 10000000.0 - 11644473600)
    except (OSError, OverflowError, ValueError):
        return None


def parse_s(s):
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s)
    except Exception:
        return None


def rot13(s):
    out = []
    for ch in s:
        o = ord(ch)
        if 65 <= o <= 90:
            out.append(chr((o - 65 + 13) % 26 + 65))
        elif 97 <= o <= 122:
            out.append(chr((o - 97 + 13) % 26 + 97))
        else:
            out.append(ch)
    return ''.join(out)


# ---------------- collectors ----------------

def collect_prefetch(detail=None):
    """QQ/微信/WeGame 家族的最后运行时刻。

    **优先用 .pf 里记录的运行历史，mtime 只作退路。**
    只看 mtime 会漏：某程序若在目标时段跑过、之后又跑过，mtime 会被顶到后面，
    那次在目标时段里的运行就整个看不见了 —— 而报告看起来完全正常。
    （这正是本工具踩过并写进陷阱清单的坑。）
    """
    res = []
    for p in glob.glob(os.path.join(PF, '*.pf')):
        b = os.path.basename(p)
        if not any(k in b.lower() for k in TRACE_KEYS):
            continue
        exe = b.split('.EXE-')[0].upper() if '.EXE-' in b.upper() else b.split('.')[0].upper()
        d = (detail or {}).get(exe) or {}
        runs = [t for t in d.get('last8', []) if t]
        if runs:
            res.append((max(runs), b, d.get('runs', 0), 'Prefetch 运行历史'))
        else:
            res.append((datetime.datetime.fromtimestamp(os.path.getmtime(p)), b,
                        0, '.pf 文件时间（无运行历史，退路）'))
    res.sort(reverse=True)
    return res


def collect_userassist():
    """Return (total_entries, entries_with_lastrun, max_count_field, list).

    total_entries counts every UserAssist value of >=68 bytes; the list holds
    only those carrying a non-zero last-run FILETIME (many entries, e.g. the
    Tencent.WMPF.* ones, are recorded with a zero timestamp). max_count_field is
    the largest run-count value seen anywhere -- if it is tiny, this Windows
    build simply does not persist run counts and we must not report them.
    """
    import winreg
    res = []
    total = 0
    maxcnt = 0
    base = r'Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist'
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, base)
    except OSError:
        return 0, 0, 0, res
    i = 0
    while True:
        try:
            g = winreg.EnumKey(k, i)
        except OSError:
            break
        i += 1
        try:
            ck = winreg.OpenKey(k, g + r'\Count')
        except OSError:
            continue
        j = 0
        while True:
            try:
                name, data, typ = winreg.EnumValue(ck, j)
            except FileNotFoundError:
                break
            except OSError as e:
                # EnumValue raises OSError both at end-of-list and on values it
                # cannot decode. Only the former means stop; otherwise skip the
                # bad value -- breaking here would silently drop the rest.
                if getattr(e, 'winerror', None) == 259:
                    break
                j += 1
                continue
            j += 1
            if not isinstance(data, bytes) or len(data) < 68:
                continue
            total += 1
            cnt = struct.unpack_from('<I', data, 4)[0]
            if cnt > maxcnt:
                maxcnt = cnt
            dt = ft_to_dt(struct.unpack_from('<Q', data, 60)[0])
            if dt is None:
                continue
            res.append((dt, rot13(name)))
    res.sort(reverse=True)
    return total, len(res), maxcnt, res


def qq_accounts():
    root = os.path.join(HOME, 'Documents', 'Tencent Files')
    out = []
    if not os.path.isdir(root):
        return out
    for e in os.listdir(root):
        d = os.path.join(root, e)
        if not os.path.isdir(d):
            continue
        dbs = glob.glob(os.path.join(d, 'nt_qq', 'nt_db', '*.db'))
        newest, newest_name = None, ''
        for f in dbs:
            m = datetime.datetime.fromtimestamp(os.path.getmtime(f))
            if newest is None or m > newest:
                newest, newest_name = m, os.path.basename(f)
        out.append({
            'account': e,
            'dir_mtime': datetime.datetime.fromtimestamp(os.path.getmtime(d)),
            'db_count': len(dbs),
            'newest': newest,
            'newest_name': newest_name,
        })
    out.sort(key=lambda x: (x['newest'] or datetime.datetime.min), reverse=True)
    return out


def wechat_logs():
    """One entry per day. WeChat writes several log families (mm_*.xlog,
    mm1_*.xlog, ...); they share a date, so keep the latest write per day."""
    d = os.path.join(os.environ.get('APPDATA', ''), 'Tencent', 'xwechat', 'log')
    best = {}
    for p in glob.glob(os.path.join(d, '*.xlog')):
        b = os.path.basename(p)
        m = re.match(r'^mm\d*_(\d{8})\.xlog$', b)
        if not m:
            continue
        day = m.group(1)
        t = datetime.datetime.fromtimestamp(os.path.getmtime(p))
        if day not in best or t > best[day][0]:
            best[day] = (t, b)
    return sorted((day, t, b) for day, (t, b) in best.items())


def find_install_dirs(hint, extra=()):
    """按卸载注册表里的显示名找安装目录 —— 不写死某台机器的盘符。

    hint 是显示名里出现的关键字（如 'todesk'）。extra 是兜底候选（通常是
    "%ProgramFiles%\\<名字>" 这类**与盘符无关**的标准位置）。
    找不到就返回空列表 —— 调用方必须把「找不到」当成 UNKNOWN，不要当成「没装」。
    """
    out = []
    try:
        import winreg
    except ImportError:
        winreg = None
    if winreg is not None:
        entries = (
            (winreg.HKEY_LOCAL_MACHINE,
             r'Software\Microsoft\Windows\CurrentVersion\Uninstall'),
            (winreg.HKEY_LOCAL_MACHINE,
             r'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'),
            (winreg.HKEY_CURRENT_USER,
             r'Software\Microsoft\Windows\CurrentVersion\Uninstall'),
        )
        for hive, path in entries:
            try:
                key = winreg.OpenKey(hive, path)
            except OSError:
                continue
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, i)
                except OSError:
                    break          # 枚举结束（或读不动）→ 停止，不静默丢后面的
                i += 1
                try:
                    sk = winreg.OpenKey(key, sub)
                    disp = str(winreg.QueryValueEx(sk, 'DisplayName')[0])
                except OSError:
                    continue
                if hint.lower() not in disp.lower():
                    continue
                loc = ''
                # InstallLocation 常常是空的（实测 ToDesk 就是），只看它会**漏掉整个程序**。
                # 退到 UninstallString / DisplayIcon：它们指向程序所在目录里的某个文件。
                for val_name in ('InstallLocation', 'UninstallString', 'DisplayIcon'):
                    try:
                        raw = str(winreg.QueryValueEx(sk, val_name)[0]).strip()
                    except OSError:
                        continue
                    if raw.startswith('"'):
                        raw = raw[1:].split('"', 1)[0]
                    else:
                        raw = raw.split(',')[0].strip()   # DisplayIcon 常见 "x.exe,0"
                    if not raw:
                        continue
                    cand = raw if os.path.isdir(raw) else os.path.dirname(raw)
                    if cand and os.path.isdir(cand):
                        loc = cand
                        break
                if loc:
                    out.append(loc)
    for c in extra:
        if os.path.isdir(c):
            out.append(c)
    return list(dict.fromkeys(out))


def wechat_data_dirs():
    """WeChat 4.x account data roots and the direct children of the account dir.

    数据目录的位置**从客户端自己的配置里读**，不写死盘符 —— 每台机器的安装盘
    和自定义目录都不同，写死了只对一台机器成立，而且那条路径本身就是机器指纹。
    4.x 把它记在 %APPDATA%\\Tencent\\xwechat\\config\\*.ini（一行一个路径）；
    3.x 的默认位置是「文档\\WeChat Files」。
    """
    found = []
    bases = []

    cfg = os.path.join(os.environ.get('APPDATA', ''), 'Tencent', 'xwechat', 'config')
    if os.path.isdir(cfg):
        for f in glob.glob(os.path.join(cfg, '*.ini')):
            try:
                with open(f, encoding='utf-8', errors='ignore') as fh:
                    for line in fh:
                        p = line.strip().strip('"')
                        if p and os.path.isdir(p) and p not in bases:
                            bases.append(p)
            except OSError:
                pass
    legacy = os.path.join(HOME, 'Documents', 'WeChat Files')
    if os.path.isdir(legacy):
        bases.append(legacy)

    for base in bases:
        root = os.path.join(base, 'xwechat_files')
        if not os.path.isdir(root):
            continue
        for e in os.listdir(root):
            full = os.path.join(root, e)
            if not os.path.isdir(full):
                continue
            kids = []
            try:
                for c in os.listdir(full):
                    cp = os.path.join(full, c)
                    kids.append((c, os.path.isdir(cp),
                                 datetime.datetime.fromtimestamp(os.path.getmtime(cp))))
            except OSError:
                pass
            kids.sort(key=lambda x: x[2], reverse=True)
            found.append({'root': root, 'account': e, 'mtime':
                          datetime.datetime.fromtimestamp(os.path.getmtime(full)),
                          'children': kids})
    return found


def wechat_login_dirs():
    d = os.path.join(os.environ.get('APPDATA', ''), 'Tencent', 'xwechat', 'login')
    out = []
    if os.path.isdir(d):
        for e in os.listdir(d):
            p = os.path.join(d, e)
            out.append((e, datetime.datetime.fromtimestamp(os.path.getmtime(p))))
    return out


def tencent_install_paths():
    import winreg
    out = []
    for sub in ('Weixin', 'WeChat', 'QQ', 'QQNT'):
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Tencent\\' + sub)
        except OSError:
            continue
        vals = {}
        j = 0
        while True:
            try:
                n, v, t = winreg.EnumValue(k, j)
            except OSError:
                break
            j += 1
            vals[n] = v
        if vals:
            out.append((sub, vals))
    return out


CHROME_OFF = 11644473600          # seconds between 1601-01-01 and 1970-01-01


def chrome_ts_to_dt(v):
    """Chromium timestamps = microseconds since 1601-01-01 **UTC**."""
    try:
        return datetime.datetime.fromtimestamp(v / 1000000.0 - CHROME_OFF)
    except (OSError, OverflowError, ValueError):
        return None


def dt_to_chrome_ts(d):
    """Inverse of chrome_ts_to_dt — must round-trip.

    Two traps here, and they pull in opposite directions:

    * `(d - 1601-01-01).total_seconds()` already includes the 1601->1970 offset.
      Adding CHROME_OFF on top of it shifts the bound by 369 years and every
      query returns zero rows, which reads as "no activity that day".
    * But `d` is a **naive local** datetime while the Chromium timestamp is
      **UTC**-based. Using the subtraction alone quietly shifts the window by
      the timezone offset (+8h here): the query then misses everything between
      local midnight and 08:00 and silently includes the day after the window.

    Going through `d.timestamp()` (which applies the local offset) and then
    adding CHROME_OFF keeps this the exact inverse of chrome_ts_to_dt.
    """
    return int((d.timestamp() + CHROME_OFF) * 1000000)


def _check_timebase():
    """Fail loudly if the two conversion helpers stop being inverses.

    This pair has already gone wrong twice, both silently:
      * adding the 1601->1970 offset twice -> bounds 369 years off -> 0 rows,
        which reads as "nobody browsed that day";
      * mixing a local naive datetime with the UTC-based Chromium stamp ->
        window shifted one timezone -> the first 8 hours of each day dropped
        and the day after the window included.
    Neither shows up as an error -- only as missing data. So assert it.
    """
    probes = [datetime.datetime(2026, 1, 1),
              datetime.datetime(2026, 6, 15, 13, 37, 5),
              datetime.datetime.now().replace(microsecond=0),
              datetime.datetime.combine(datetime.date.today(), datetime.time())]
    for p in probes:
        back = chrome_ts_to_dt(dt_to_chrome_ts(p))
        if back != p:
            raise SystemExit('TIMEBASE SELFTEST FAILED: %r -> %r (local offset %s)'
                             % (p, back, datetime.datetime.now().astimezone().utcoffset()))
    print('timebase roundtrip: OK (%d probes)' % len(probes))


_check_timebase()
prefetch_parse._selftest()     # 解压器错一个移位就输出垃圾而不报错，必须锚定
print('prefetch selftest: OK (MAM decompressor anchors)')


def _sqlite_copy(src):
    """Chrome/Edge hold History open while running; query a private copy."""
    tmp = os.path.join(WORK, '_c_%d_%s' % (abs(hash(src)) % 1000000, os.path.basename(src)))
    try:
        shutil.copy2(src, tmp)
        return tmp
    except Exception:
        return None


BROWSER_ROOTS = [
    ('Edge', r'Microsoft\Edge\User Data'),
    ('Chrome', r'Google\Chrome\User Data'),
    ('Brave', r'BraveSoftware\Brave-Browser\User Data'),
    ('QQBrowser', r'Tencent\QQBrowser\User Data'),
    ('360SE', r'360se6\User Data'),
]
# Apps that embed a Chromium profile of their own.
EMBEDDED_ROOTS = [
    ('豆包(Doubao)', r'Doubao\User Data'),
    ('ima.copilot', r'ima.copilot\User Data'),
    ('zero', r'zero\User Data'),
]


def collect_browser_history(d1, d2):
    L = os.environ.get('LOCALAPPDATA', '')
    R = os.environ.get('APPDATA', '')
    cands = []
    for name, rel in BROWSER_ROOTS:
        for base in (os.path.join(L, rel), os.path.join(R, rel)):
            if os.path.isdir(base):
                for pr in ['Default'] + ['Profile %d' % i for i in range(1, 6)]:
                    h = os.path.join(base, pr, 'History')
                    if os.path.isfile(h):
                        cands.append((name + '/' + pr, h))
    for name, rel in EMBEDDED_ROOTS:
        base = os.path.join(L, rel)
        if os.path.isdir(base):
            for pr in ['Default'] + ['Profile %d' % i for i in range(1, 4)]:
                h = os.path.join(base, pr, 'History')
                if os.path.isfile(h):
                    cands.append((name + '/' + pr, h))
    lo = dt_to_chrome_ts(datetime.datetime.combine(d1, datetime.time()))
    hi = dt_to_chrome_ts(datetime.datetime.combine(d2 + datetime.timedelta(days=1), datetime.time()))
    out, dls, stats = [], [], {}
    for name, h in cands:
        tmp = _sqlite_copy(h)
        if not tmp:
            continue
        got = 0
        try:
            con = sqlite3.connect(tmp)
            cur = con.cursor()
            for url, title, vt in cur.execute(
                    'SELECT u.url, u.title, v.visit_time FROM visits v '
                    'JOIN urls u ON u.id=v.url WHERE v.visit_time>=? AND v.visit_time<? '
                    'ORDER BY v.visit_time', (lo, hi)):
                out.append((name, chrome_ts_to_dt(vt), url or '', title or ''))
                got += 1
            try:
                for tp, st in cur.execute(
                        'SELECT target_path, start_time FROM downloads WHERE start_time>=? AND start_time<?',
                        (lo, hi)):
                    dls.append((name, chrome_ts_to_dt(st), tp or ''))
            except Exception:
                pass
            con.close()
        except Exception as e:
            stats[name] = 'ERR:%s' % type(e).__name__
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass
        if name not in stats:
            stats[name] = got
    out.sort(key=lambda x: x[1] or datetime.datetime.min)
    dls.sort(key=lambda x: x[1] or datetime.datetime.min)
    return out, dls, stats


def collect_timeline(d1, d2):
    """Windows Timeline (ActivitiesCache.db). StartTime is a Unix epoch second."""
    out = []
    lo = int(datetime.datetime.combine(d1, datetime.time()).timestamp())
    hi = int(datetime.datetime.combine(d2 + datetime.timedelta(days=1), datetime.time()).timestamp())
    for db in glob.glob(os.path.join(os.environ.get('LOCALAPPDATA', ''),
                                     'ConnectedDevicesPlatform', '*', 'ActivitiesCache.db')):
        tmp = _sqlite_copy(db)
        if not tmp:
            continue
        try:
            con = sqlite3.connect(tmp)
            cur = con.cursor()
            for aid, st, et, at in cur.execute(
                    'SELECT AppId, StartTime, EndTime, ActivityType FROM Activity '
                    'WHERE StartTime>=? AND StartTime<? ORDER BY StartTime', (lo, hi)):
                t = None
                if isinstance(st, (int, float)):
                    t = datetime.datetime.fromtimestamp(st)
                elif isinstance(st, str):
                    t = parse_s(st.replace('Z', ''))
                app = '?'
                try:
                    app = json.loads(aid)[0].get('application') or '?'
                except Exception:
                    app = str(aid)[:50]
                out.append((t, app, at))
            con.close()
        except Exception:
            pass
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass
    out.sort(key=lambda x: x[0] or datetime.datetime.min)
    return out


def collect_recycle(d1, d2):
    """$I metadata files: original path + deletion time.

    Layout (version 2, Windows 10+):
      0..7   version
      8..15  original size
      16..23 deletion FILETIME
      24..27 original path length in UTF-16 characters
      28..   original path, UTF-16LE

    Reading the path at offset 24 instead of 28 shifts it by 4 bytes and every
    recovered name comes out as a single junk character.
    """
    inwin, allrows = [], []
    # 每个固定盘都有自己的回收站；只看 C 盘会漏掉别的盘上的删除记录。
    _recyc = []
    for _drv in fixed_drives():
        _recyc += glob.glob(os.path.join(_drv, '$Recycle.Bin', '*'))
    for root in _recyc:
        for f in glob.glob(os.path.join(root, '$I*')):
            try:
                with open(f, 'rb') as fh:
                    d = fh.read(4000)
            except Exception:
                continue
            if len(d) < 28:
                continue
            ver = struct.unpack_from('<Q', d, 0)[0]
            size = struct.unpack_from('<Q', d, 8)[0]
            when = ft_to_dt(struct.unpack_from('<Q', d, 16)[0])
            if ver == 2:
                nlen = struct.unpack_from('<I', d, 24)[0]
                if nlen <= 0 or nlen > 1000:
                    nlen = 260
                body = d[28:28 + nlen * 2]
            else:
                body = d[24:24 + 260 * 2]
            name = body.decode('utf-16-le', 'ignore').split('\x00')[0]
            if when:
                allrows.append((when, size, name))
                if d1 <= when.date() <= d2:
                    inwin.append((when, size, name))
    inwin.sort(reverse=True)
    allrows.sort(reverse=True)
    return inwin, allrows


def collect_downloads(d1, d2):
    out = []
    for base in (os.path.join(HOME, 'Downloads'), os.path.join(HOME, 'Desktop')):
        if not os.path.isdir(base):
            continue
        for f in glob.glob(os.path.join(base, '*')):
            try:
                m = datetime.datetime.fromtimestamp(os.path.getmtime(f))
            except Exception:
                continue
            if d1 <= m.date() <= d2:
                try:
                    s = os.path.getsize(f) if os.path.isfile(f) else -1
                except Exception:
                    s = -1
                out.append((m, f, s))
    out.sort(reverse=True)
    return out


APP_CATS = [
    ('远程控制', ('teamviewer', 'anydesk', 'sunlogin', 'todesk', 'rustdesk', 'winvnc', 'vnc',
                  'mstsc', 'splashtop', 'gotohttp', 'netviewer', 'ammyy', 'radmin', 'aweray')),
    ('录屏 / 截图', ('obs', 'bandicam', 'fraps', 'snipaste', 'sharex', 'camtasia', 'evcapture',
                     'snippingtool', 'screensket', 'screenclip', 'gamebar', 'faststone',
                     'picpick', 'huiying')),
    ('浏览器', ('chrome', 'msedge', 'firefox', 'iexplore', 'qqbrowser', '360se6', '360chrome',
                'sogouexplorer', 'maxthon', 'brave', 'opera', 'theworld', 'quark', 'centbrowser',
                'browser.exe', 'liebao')),
    ('即时通讯 / 会议', ('qq.exe', 'qqex', 'timwp', 'wechat', 'weixin', 'dingtalk', 'telegram',
                         'discord', 'skype', 'feishu', 'lark', 'wemeet', 'wxwork', 'zoom',
                         'tcls', 'weflow')),
    ('网盘 / 同步', ('baidunetdisk', 'baiduyunguanjia', 'onedrive', 'dropbox', 'googledrive',
                     'aliyundrive', 'weiyun', 'thunder', 'xunlei', '115')),
    ('密码 / 凭据', ('keepass', '1password', 'bitwarden', 'enpass', 'lastpass', 'roboform')),
    ('输入法', ('sogouinput', 'qqpinyin', 'baiduime', 'chsime', 'rime', 'weasel', 'sgim',
                'sgtool', 'imewdbld', 'textinputhost')),
    ('安全 / 杀软', ('360tray', '360safe', 'huorong', 'qqpcmgr', 'kaspersky', 'msmpeng',
                     'zsaservice', 'safesvr', 'securityhealth', 'avast', 'eset', 'norton')),
    ('下载工具', ('idm', 'aria2', 'motrix', 'qbittorrent', 'transmission', 'flashget')),
    ('开发 / 终端', ('code.exe', 'devenv', 'pycharm', 'goland', 'webstorm', 'idea', 'git.exe',
                     'bash.exe', 'ssh.exe', 'cmd.exe', 'powershell', 'windowsterminal',
                     'python', 'node.exe', 'conda', 'claude', 'gh.exe', 'vim')),
    ('办公 / 文档', ('winword', 'excel', 'powerpnt', 'wps', 'et.exe', 'wpp', 'onenote',
                     'acrobat', 'foxit', 'pdf', 'notepad', 'typora', 'obsidian')),
    ('游戏', ('league', 'wegame', 'steam', 'riot', 'pallas', 'crossproxy', 'taslogin',
              'genshin', 'dnf', 'yysls')),
    ('媒体 / 播放', ('potplayer', 'vlc', 'mpc-hc', 'kmplayer', 'cloudmusic', 'qqmusic',
                     'kugou', 'kuwo', 'bilibili', 'douyin', 'huya', 'douyu', 'iqiyi',
                     'tencentvideo', 'qqlive')),
    ('虚拟机 / 容器', ('vmware', 'virtualbox', 'vbox', 'vmmem', 'docker', 'wsl', 'qemu')),
]
# Categories where an unexpected run is the thing worth looking at.
PRIVACY_CATS = ('远程控制', '录屏 / 截图', '密码 / 凭据', '网盘 / 同步', '浏览器', '即时通讯 / 会议')


def app_cat(name):
    l = str(name).lower()
    for cat, keys in APP_CATS:
        if any(k in l for k in keys):
            return cat
    return '其它'


def collect_prefetch_all():
    res = []
    for p in glob.glob(os.path.join(PF, '*.pf')):
        b = os.path.basename(p)
        exe = b.split('-')[0]
        res.append((datetime.datetime.fromtimestamp(os.path.getmtime(p)),
                    exe[:-4] if exe.upper().endswith('.EXE') else exe))
    res.sort(reverse=True)
    return res


def collect_prefetch_detail():
    """可执行名(大写) -> {runs, version, compressed, last8}

    Windows 8 起 Prefetch 默认压缩（文件头 `MAM\\x04`），只看文件 mtime 只能得到
    "最后一次运行"。用 prefetch_parse 解开之后能拿到**运行次数**和**最近 8 次运行时间** ——
    这才看得见"某程序在那次开机时启动过、但之后又被运行过所以 mtime 被顶掉"。
    """
    out = {}
    for p in glob.glob(os.path.join(PF, '*.pf')):
        try:
            r = prefetch_parse.parse(open(p, 'rb').read())
        except Exception:
            continue
        exe = os.path.basename(p).split('-')[0]
        if exe.upper().endswith('.EXE'):
            exe = exe[:-4]
        key = exe.upper()
        # 同一个可执行文件可能有多个 .pf（不同安装路径各一个），
        # **必须合并**：只留其中一个是错的 —— 豆包有好几个路径，
        # 只留次数最多的那个会把它在别的路径上的启动时刻全丢掉。
        cur = out.setdefault(key, {'runs': 0, 'version': r['version'],
                                   'compressed': r['compressed'], 'last8': [],
                                   'paths': 0})
        cur['runs'] += r['run_count']
        cur['paths'] += 1
        cur['last8'] = sorted(
            {t for t in cur['last8'] + [prefetch_parse.filetime_to_dt(x) for x in r['last_runs']] if t},
            reverse=True)[:8]
    return out


def boot_started_programs(boot_times, detail, within_sec=240):
    """开机后 within_sec 内启动过的程序。

    这是"他登录后屏幕上本来就会出现什么"的依据：自启项不写任何日志，
    但它的运行时刻留在 Prefetch 的最近 8 次记录里。

    **分母只能用每个程序实际存下的记录数**（最多 8），不能用"机器开过多少次机" ——
    Prefetch 只保留最近 8 次运行，机器开过 20 次时用 20 当分母，永远显示 "7/20"，
    看起来像"偶尔启动"，其实可能每次开机都起。
    """
    rows = []
    for exe, d in detail.items():
        runs = [t for t in d.get('last8', []) if t]
        after = [t for t in runs
                 if any(datetime.timedelta(0) <= (t - bt) <= datetime.timedelta(seconds=within_sec)
                        for bt in boot_times)]
        if after:
            rows.append({'exe': exe, 'boot_runs': len(after), 'recorded': len(runs),
                         'total': d.get('runs', 0), 'last': max(after)})
    rows.sort(key=lambda r: (-r['boot_runs'], -r['total']))
    return rows



def collect_todesk():
    """ToDesk remote-control sessions, split by DIRECTION.

    'client recv connect request, myid=...' = this machine dials OUT to a peer.
    'host   recv connect request, myid=...' = this machine is the CONTROLLED
    end, i.e. somebody connected into it.  The two lines look almost identical
    and carry the same id pair, so the direction is the entire question; getting
    it backwards inverts the conclusion.
    """
    base = None
    for c in find_install_dirs('todesk', (
            os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'ToDesk'),
            os.path.join(os.environ.get('ProgramFiles(x86)',
                                        r'C:\Program Files (x86)'), 'ToDesk'))):
        if os.path.isdir(os.path.join(c, 'Logs')):
            base = c
            break
    if not base:
        return None
    logdir = os.path.join(base, 'Logs')
    info = {'base': base, 'host': [], 'client': [], 'files': 0, 'config': {},
            'sessions': [], 'earliest': None, 'latest': None, 'netstat': []}
    cfg = os.path.join(base, 'config.ini')
    if os.path.isfile(cfg):
        want = ('clientId', 'Version', 'LoginPhone', 'LoginType', 'IsFirstTimeConnect',
                'TfaForConn', 'autoLockScreen', 'PrivateScreenLockScreen',
                'FileCenterDownloadPath', 'updatePassTime', 'AuthMode')
        for l in open(cfg, encoding='utf-8', errors='ignore'):
            if '=' in l:
                k, v = l.split('=', 1)
                if k.strip() in want:
                    info['config'][k.strip()] = v.strip()
    dates = []
    for p in glob.glob(os.path.join(logdir, '*.log')):
        m = re.search(r'(\d{4})_(\d{2})_(\d{2})', os.path.basename(p))
        if m:
            dates.append('-'.join(m.groups()))
        info['files'] += 1
        try:
            fh = open(p, encoding='utf-8', errors='ignore')
        except Exception:
            continue
        for line in fh:
            s = line.strip()
            t = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', s)
            if not t:
                continue
            if 'host recv connect request, myid=' in s:
                info['host'].append((t.group(1), s))
            elif 'client recv connect request, myid=' in s:
                info['client'].append((t.group(1), s))
    dates.sort()
    info['earliest'] = dates[0] if dates else None
    info['latest'] = dates[-1] if dates else None
    for p in sorted(glob.glob(os.path.join(logdir, 'session*_*.log'))):
        try:
            ls = [x for x in open(p, encoding='utf-8', errors='ignore') if x.strip()]
        except Exception:
            continue
        if not ls:
            continue
        a = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', ls[0].strip())
        b = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', ls[-1].strip())
        info['sessions'].append((os.path.basename(p), a.group(1) if a else '?',
                                 b.group(1) if b else '?', len(ls)))
    info['sessions'].sort(key=lambda x: x[1])
    return info


REMOTE_TOOLS = (
    # 显示名, 卸载注册表关键字, 标准安装目录名
    ('ToDesk',        'todesk',       'ToDesk'),
    ('AnyDesk',       'anydesk',      'AnyDesk'),
    ('TeamViewer',    'teamviewer',   'TeamViewer'),
    ('向日葵 SunloginClient', 'sunlogin', 'SunloginClient'),
    ('向日葵 AweSun',  'awesun',       'AweSun'),
    ('RustDesk',      'rustdesk',     'RustDesk'),
    ('ScreenConnect', 'screenconnect', 'ScreenConnect'),
    ('LogMeIn',       'logmein',      'LogMeIn'),
    ('RealVNC / TightVNC', 'vnc',     'vnc'),
)


def collect_other_remote():
    """除 ToDesk 之外的远控途径。

    **只查一种远控软件会给出假的安全结论。** 报告若只写「未发现 ToDesk 日志目录」，
    读起来像「没人连进来过」—— 而对方完全可能用的是 AnyDesk / 向日葵 / TeamViewer。
    所以这里把已知的远控软件逐个查"装没装、有没有日志"，再叠上 mstsc（RDP 客户端）
    连过谁的历史。

    入站 RDP 不在这里查：安全日志的登录类型 10/3/8 已经在上面「登录与远程访问」一节
    统计过了，重复查会给出两个可能不一致的数字。
    """
    pf = os.environ.get('ProgramFiles', r'C:\Program Files')
    pf86 = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
    tools = []
    for label, hint, dirname in REMOTE_TOOLS:
        extra = ()
        if dirname:
            extra = (os.path.join(pf, dirname), os.path.join(pf86, dirname))
        dirs = find_install_dirs(hint, extra)
        logs = []
        for d in dirs:
            for pat in ('*.log', '*.txt', os.path.join('Logs', '*'),
                        os.path.join('logs', '*')):
                for f in glob.glob(os.path.join(d, pat))[:6]:
                    t = None
                    try:
                        t = datetime.datetime.fromtimestamp(os.path.getmtime(f))
                    except OSError:
                        pass
                    logs.append((t, f))
        logs = sorted({(t, f) for t, f in logs},
                      key=lambda x: x[0] or datetime.datetime.min, reverse=True)[:6]
        tools.append({'name': label, 'dirs': dirs, 'logs': logs,
                      'installed': bool(dirs) or bool(logs)})

    # mstsc：本机主动连出去过哪些地址（没有时间戳，只能给"连过谁"）
    mstsc = []
    try:
        import winreg
        for sub, val in ((r'Software\Microsoft\Terminal Server Client\Default', 'MRU'),
                         (r'Software\Microsoft\Terminal Server Client\Servers', '')):
            try:
                k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub)
            except OSError:
                continue
            i = 0
            while True:
                try:
                    n, v, _ = winreg.EnumValue(k, i)
                    i += 1
                except OSError:
                    break
                if str(n).startswith(val) or not val:
                    mstsc.append('%s = %s' % (n, v))
    except Exception:
        pass
    return {'tools': tools, 'mstsc': mstsc}


def prefetch_magic():
    rows = as_list(load('pfmagic.json'))
    rows = [r for r in rows if isinstance(r, dict)]
    rows.sort(key=lambda r: -int(r.get('count') or 0))
    return rows


def parse_ntqq_recents(recents):
    """QQ NT puts fuin=<account> and peerName=<peer> into the Recent .lnk name."""
    out = []
    for r in recents:
        n = str(r.get('name', ''))
        if 'fuin=' not in n:
            continue
        m_f = re.search(r'fuin=(\d+)', n)
        m_p = re.search(r'peerName=([^;]+)', n)
        m_t = re.search(r'chatType=(\d+)', n)
        out.append({
            'time': parse_s(r.get('time')),
            'fuin': m_f.group(1) if m_f else '?',
            'peer': m_p.group(1) if m_p else '?',
            'chattype': m_t.group(1) if m_t else '?',
        })
    out.sort(key=lambda x: x['time'] or datetime.datetime.min, reverse=True)
    return out


# ---------------- helpers ----------------

def esc(s):
    return html.escape(str(s if s is not None else ''))


def fmt(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else '-'


def fmt_t(dt):
    return dt.strftime('%H:%M:%S') if dt else '-'


def bar_row(label, value, total, colour, suffix=''):
    pct = (value / total * 100) if total else 0
    return (
        '<div class="bar-row">'
        '<div class="bar-label">%s</div>'
        '<div class="bar-track"><div class="bar-fill" style="width:%.2f%%;background:%s"></div></div>'
        '<div class="bar-val">%s%s</div>'
        '</div>' % (esc(label), pct, colour, value, suffix)
    )


# ---------------- load ----------------

env      = load('env.json', {}) or {}
logons   = [r for r in as_list(load('logons.json')) if isinstance(r, dict)]
failed   = [r for r in as_list(load('failed.json')) if isinstance(r, dict)]
session  = [r for r in as_list(load('session.json')) if isinstance(r, dict)]
boot     = [r for r in as_list(load('boot.json')) if isinstance(r, dict)]
audit    = load('audit4688.json', {}) or {}
tasks    = [r for r in as_list(load('tasks.json')) if isinstance(r, dict)]
autoruns = [r for r in as_list(load('autoruns.json')) if isinstance(r, dict)]
activity = [r for r in as_list(load('activity.json')) if isinstance(r, dict)]
prelogin = [r for r in as_list(load('prelogin.json')) if isinstance(r, dict)]
sdkdb    = [r for r in as_list(load('sdkdb.json')) if isinstance(r, dict)]
appevents= [r for r in as_list(load('appevents.json')) if isinstance(r, dict)]
software = [r for r in as_list(load('software.json')) if isinstance(r, dict)]
wgaccounts = [r for r in as_list(load('wegame_accounts.json')) if isinstance(r, dict)]
gamlogin = [r for r in as_list(load('gamlogin.json')) if isinstance(r, dict)]
sdkloc   = [r for r in as_list(load('sdkloc.json')) if isinstance(r, dict)]
sigs     = [r for r in as_list(load('signatures.json')) if isinstance(r, dict)]
recents  = [r for r in as_list(load('recent.json')) if isinstance(r, dict)]
procs    = [r for r in as_list(load('procs.json')) if isinstance(r, dict)]

pf_detail      = collect_prefetch_detail()   # 必须先于 pf —— 第五节按运行历史取时间
pf             = collect_prefetch(pf_detail)
ua_total, ua_n, ua_maxcnt, ua = collect_userassist()
ua_ten         = [(d, n) for (d, n) in ua if any(k in n.lower() for k in TRACE_KEYS)]
qq_accts       = qq_accounts()
wx_logs        = wechat_logs()
wx_data        = wechat_data_dirs()
wx_login       = wechat_login_dirs()
ten_installs   = tencent_install_paths()
magic          = prefetch_magic()
ntqq_recents   = parse_ntqq_recents(recents)

now      = datetime.datetime.now()
rdp_deny = env.get('rdp_deny')

lt_counts = {}
for r in logons:
    lt_counts[r.get('lt', '?')] = lt_counts.get(r.get('lt', '?'), 0) + 1
remote_lt = sum(v for k, v in lt_counts.items() if k in ('3', '8', '10'))
interactive = [r for r in logons if r.get('lt') == '2']

# autorun verdict, computed (not hardcoded)
ar_hits = [r for r in autoruns if STRICT.search(str(r.get('value', '')) + ' ' + str(r.get('name', '')))]
ar_ars  = [r for r in autoruns if 'Service' not in str(r.get('where', ''))]

# running tencent processes right now
# Match on the path too: WeGame/LoL run under generic names like browser.exe,
# so matching only the process name misses most of the game stack.
PATH_KEYS = GAME_KEYS + ('qq.exe', 'wechat', 'weixin', 'xwechat', 'qqnt', 'napcat', 'tencent')
run_ten = [p for p in procs
           if any(k in str(p.get('name', '')).lower() for k in KEYS)
           or any(k in str(p.get('path', '')).lower() for k in PATH_KEYS)]

# newest day that has any Tencent execution
day = pf[0][0].date() if pf else now.date()

if _ARGS.dfrom:
    d1 = datetime.date.fromisoformat(_ARGS.dfrom)
    d2 = datetime.date.fromisoformat(_ARGS.dto) if _ARGS.dto else datetime.date.today()
elif _ARGS.dto:
    d2 = datetime.date.fromisoformat(_ARGS.dto)
    d1 = d2 - datetime.timedelta(days=_ARGS.days - 1)
else:
    d2 = datetime.date.today()
    d1 = d2 - datetime.timedelta(days=_ARGS.days - 1)
FOCUS = (d1, d2)
day = d2        # the timeline section renders the last day of the window

# broad privacy sweep for the two focus days
pf_all            = collect_prefetch_all()
bhist, bdl, bstat = collect_browser_history(d1, d2)
timeline          = collect_timeline(d1, d2)
recycled, recycled_all = collect_recycle(d1, d2)
dlfiles           = collect_downloads(d1, d2)
todesk            = collect_todesk()
other_remote      = collect_other_remote()

tl = []


def add_tl(dt, kind, label, short=None):
    if dt and dt.date() == day:
        tl.append((dt, kind, label, short or label[:14]))


for r in boot:
    t = parse_s(r.get('time'))
    if t and t.date() == day and str(r.get('id')) == '6005':
        add_tl(t, 'boot', '开机（事件日志服务启动）', '开机')
for r in logons:
    t = parse_s(r.get('time'))
    if t and r.get('lt') == '2' and 'DWM' not in str(r.get('user')) and 'UMFD' not in str(r.get('user')):
        add_tl(t, 'logon', '交互式登录 ' + str(r.get('user')), '登录')
for dt, name, _cnt, _src in pf:
    exe = name.split('-')[0]
    if exe.upper().endswith('.EXE'):
        exe = exe[:-4]
    add_tl(dt, 'exec', exe + ' 运行', exe)
for r in tasks:
    t = parse_s(r.get('last'))
    nm = str(r.get('name', '')).lstrip('\\')
    if t and (nm.startswith('Lds') or 'Wechat' in nm or 'ComputerZ' in nm):
        add_tl(t, 'task', '计划任务 ' + nm + ' 触发', nm)
tl.sort()

# ---------------- HTML ----------------

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#eef1f5;color:#1b2430;font:14px/1.6 "Segoe UI","Microsoft YaHei",system-ui,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px 60px}
header{background:#16202b;color:#e8eef6;padding:26px 0 22px;margin-bottom:24px}
header .wrap{padding-bottom:0}
h1{margin:0 0 6px;font-size:23px;letter-spacing:.3px}
.meta{font-size:12.5px;color:#93a4b6;font-family:Consolas,monospace}
h2{font-size:16.5px;margin:34px 0 12px;padding-bottom:7px;border-bottom:2px solid #d3dae3}
h3{font-size:14px;margin:20px 0 8px;color:#2c3a4a}
h4{font-size:13px;margin:16px 0 6px;color:#40536a}
section{background:#fff;border:1px solid #dde3ea;border-radius:10px;padding:6px 22px 22px;margin-bottom:18px;box-shadow:0 1px 2px rgba(20,35,55,.05)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin:16px 0 4px}
.card{border-radius:8px;padding:13px 15px;border-left:5px solid #94a3b8;background:#f7f9fb}
.card .k{font-size:11.5px;letter-spacing:.6px;color:#6b7c90;text-transform:uppercase}
.card .v{font-size:15px;font-weight:600;margin-top:3px}
.card .d{font-size:12.5px;color:#5b6b7d;margin-top:4px}
.ok{border-left-color:#127d45;background:#f2faf5}.ok .v{color:#0d5c33}
.warn{border-left-color:#c07a06;background:#fdf9ef}.warn .v{color:#8a5800}
.bad{border-left-color:#c0392b;background:#fdf3f2}.bad .v{color:#a02a1e}
.info{border-left-color:#1a5fb4;background:#f2f6fd}.info .v{color:#144a8c}
table{width:100%;border-collapse:collapse;font-size:13px;margin:10px 0}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid #e6ebf1;vertical-align:top}
th{background:#f4f7fa;font-weight:600;color:#40536a;font-size:12.5px}
tr:hover td{background:#fafcfd}
code,.mono{font-family:Consolas,"Courier New",monospace;font-size:12.5px}
.tag{display:inline-block;padding:1px 7px;border-radius:20px;font-size:11.5px;font-weight:600}
.t-red{background:#fdecea;color:#a02a1e}.t-green{background:#e8f6ee;color:#0d5c33}
.t-amber{background:#fdf3e0;color:#8a5800}.t-grey{background:#eef1f5;color:#5b6b7d}
.bar-row{display:grid;grid-template-columns:180px 1fr 90px;align-items:center;gap:10px;margin:6px 0;font-size:13px}
.bar-track{background:#e9eef4;border-radius:4px;height:16px;overflow:hidden}
.bar-fill{height:100%;border-radius:4px}
.bar-val{text-align:right;color:#40536a;font-variant-numeric:tabular-nums}
.strip{display:flex;gap:5px;flex-wrap:wrap;margin:12px 0 4px}
.cell{width:52px;height:40px;border-radius:6px;display:flex;align-items:center;justify-content:center;
      font-size:11.5px;font-weight:600;font-family:Consolas,monospace;border:1px solid rgba(0,0,0,.07)}
.s-night{background:#1b3a5c;color:#dce8f5}.s-dawn{background:#4a6fa5;color:#eef4fb}
.s-day{background:#2e8b57;color:#eafaf1}.s-eve{background:#c98a1c;color:#fff8e8}
.legend{font-size:12px;color:#5b6b7d;display:flex;gap:16px;flex-wrap:wrap;margin:8px 0 0}
.legend i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;vertical-align:-1px}
details{border:1px solid #e2e8ef;border-radius:8px;padding:10px 14px;margin:10px 0;background:#fafcfe}
summary{cursor:pointer;font-weight:600;font-size:13px;color:#2c3a4a}
details pre{overflow:auto;max-height:420px;font-size:12px;background:#fff;border:1px solid #e6ebf1;border-radius:6px;padding:10px;margin:10px 0 4px}
.note{background:#fffdf5;border-left:4px solid #d9a441;padding:11px 15px;border-radius:0 6px 6px 0;margin:14px 0;font-size:13.2px}
.note b{color:#8a5800}
.cap{font-size:12.5px;color:#6b7c90;margin:6px 0 0}
svg{display:block;max-width:100%}
"""

P = []
A = P.append
A('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">')
A('<meta name="viewport" content="width=device-width,initial-scale=1">')
A('<title>本机活动痕迹与远程访问检查报告</title><style>%s</style></head><body>' % CSS)

A('<header><div class="wrap"><h1>本机活动痕迹与远程访问检查报告</h1>')
A('<div class="meta">主机 %s &nbsp;|&nbsp; 账户 %s &nbsp;|&nbsp; %s %s<br>'
  '报告生成 %s &nbsp;|&nbsp; 数据源：Prefetch / UserAssist / 安全日志 / 计划任务 / 自启动项 / '
  'Recent 快捷方式 / 数字签名 / 应用数据目录</div>'
  % (esc(env.get('hostname')), esc(env.get('user')), esc(env.get('os')), esc(env.get('build')),
     now.strftime('%Y-%m-%d %H:%M:%S')))
A('</div></header><div class="wrap">')

# ================= 1. verdict =================
A('<section><h2>一、结论</h2><div class="cards">')

if rdp_deny == 1:
    A('<div class="card ok"><div class="k">远程桌面</div><div class="v">已禁用</div>'
      '<div class="d">fDenyTSConnections=1；近 7 天远程登录类型事件 0 条</div></div>')
else:
    A('<div class="card bad"><div class="k">远程桌面</div><div class="v">已启用</div>'
      '<div class="d">fDenyTSConnections=%s —— 需进一步核查远程登录记录</div></div>' % esc(rdp_deny))

if remote_lt == 0:
    A('<div class="card ok"><div class="k">远程 / 网络登录</div><div class="v">0 条</div>'
      '<div class="d">近 7 天登录类型 10（RDP）/ 3（网络）/ 8（网络明文）均为 0</div></div>')
else:
    A('<div class="card bad"><div class="k">远程 / 网络登录</div><div class="v">%d 条</div>'
      '<div class="d">存在类型 10 / 3 / 8 登录，见登录章节明细</div></div>' % remote_lt)

A('<div class="card info"><div class="k">交互式登录（近 7 天）</div><div class="v">%d 条</div>'
  '<div class="d">全部为本地控制台会话</div></div>' % len(interactive))

if ar_hits:
    A('<div class="card bad"><div class="k">自启动中的腾讯项</div><div class="v">%d 条</div>'
      '<div class="d">QQ / 微信<b>存在</b>自动启动来源，见自启动章节</div></div>' % len(ar_hits))
else:
    A('<div class="card ok"><div class="k">自启动中的腾讯项</div><div class="v">0 条</div>'
      '<div class="d">在 %d 条自启动记录中，QQ 与微信<b>均不在其中</b>（本次实测）</div></div>' % len(autoruns))

if ua_maxcnt <= 20:
    A('<div class="card warn"><div class="k">UserAssist 次数</div><div class="v">取不到</div>'
      '<div class="d">UserAssist 计数字段最大仅 %d，该版本不落盘次数，这一路只能给"最后一次运行"。'
      '但 <b>Prefetch 的运行次数是可用的</b>，报告里的次数来自 Prefetch</div></div>' % ua_maxcnt)
else:
    A('<div class="card info"><div class="k">运行次数</div><div class="v">可用</div>'
      '<div class="d">UserAssist 计数最大 %d，报告中会给出次数</div></div>' % ua_maxcnt)

A('<div class="card warn"><div class="k">能否区分"谁"用的</div><div class="v">不能</div>'
  '<div class="d">本机只有一个 Windows 账户，同一会话内无法区分操作人</div></div>')

A('</div></section>')

# ================= 2. focus: the two most recent days =================
CATS = ['微信', 'QQ', 'WeGame / LoL', '鲁大师 / 多开', '其它腾讯', '系统 / 其它']


def categorise(s):
    t = str(s)
    l = t.lower()
    if 'xwechat' in l or 'weixin' in l or 'wechat' in l or '微信' in t:
        return '微信'
    if 'tencent files' in l or 'qq.exe' in l or 'qqnt' in l or re.search(r'\\qq\\', l):
        return 'QQ'
    if any(k in l for k in ('wegame', 'tcls', 'taslogin', 'crossproxy', 'riotclient',
                            'league', 'pallas', 'tenio', '英雄联盟')):
        return 'WeGame / LoL'
    if any(k in l for k in ('ludashi', 'computerz', 'multi_wechat', '\\lds', '鲁大师')):
        return '鲁大师 / 多开'
    if 'tencent' in l or 'qqntopensdk' in l:
        return '其它腾讯'
    return '系统 / 其它'


focus_events = []   # (dt, category, label, kind)  kind: 'event' | 'file'


def add_ev(dt, src, label, kind='event'):
    """kind='event' = a real happening (program ran, task fired, logon).
    kind='file'  = a file merely changed on disk. Only 'event' rows are listed
    individually; file churn is aggregated per category+hour, because WeChat
    alone rewrites hundreds of cache/profile files an hour and would otherwise
    bury every other row."""
    if dt and dt.date() in FOCUS:
        focus_events.append((dt, categorise(src), label, kind))


for e in activity:
    add_ev(parse_s(e.get('t')), e.get('p'), os.path.basename(str(e.get('p'))), 'file')
for r in recents:
    add_ev(parse_s(r.get('time')), str(r.get('name')), str(r.get('name'))[:70], 'file')
for dt, name, _cnt, _src in pf:
    add_ev(dt, name, name)
for dt, name in ua_ten:
    add_ev(dt, name, os.path.basename(name))
for r in tasks:
    add_ev(parse_s(r.get('last')), str(r.get('name')) + ' ' + str(r.get('act')),
           '任务 ' + str(r.get('name')).lstrip('\\'))
for r in boot:
    add_ev(parse_s(r.get('time')), 'system', '系统日志 id=%s' % r.get('id'))
for r in logons:
    if r.get('lt') == '2':
        add_ev(parse_s(r.get('time')), 'system', '登录 %s' % r.get('user'))
for r in session:
    add_ev(parse_s(r.get('time')), 'system', '会话事件 id=%s' % r.get('id'))
for r in wgaccounts:
    add_ev(parse_s(r.get('t')), 'wegame login_pic ' + str(r.get('n')),
           'WeGame 登录账号解析：%s%s' % (r.get('n'), '（.tmp 未完成）' if r.get('tmp') else ''))
for e in prelogin:
    add_ev(parse_s(e.get('t')), 'wegame qqntopensdk ' + str(e.get('app')),
           'QQ 登录 SDK 票据刷新：%s' % e.get('n'))
focus_events.sort(key=lambda x: x[0])

HOURS = (d2 - d1).days * 24 + 24
grid = {}
for dt, cat, label, kind in focus_events:
    hi = (dt.date() - d1).days * 24 + dt.hour
    grid[(cat, hi)] = grid.get((cat, hi), 0) + 1
mx = max(grid.values()) if grid else 0

A('<section><h2>二、日期聚焦：%s 与 %s</h2>' % (d1.strftime('%Y-%m-%d'), d2.strftime('%Y-%m-%d')))
A('<div class="note">这两天的可取证事件按小时归并。横轴 48 格 = 前一天 00:00 → 当天 23:00。'
  '<b>颜色按每一行各自归一化</b>（微信每小时改写几百个缓存文件，用统一色标会把其它行压成空白），'
  '所以颜色只在行内比较，跨行请看每行右侧的"峰值"。数据源：Prefetch 文件时间、计划任务上次运行、'
  '事件日志、Recent 快捷方式、腾讯/游戏目录下被改动文件的修改时间。'
  '<b>限制：Prefetch 只保留"最后一次运行"，所以同一程序在多天里只会出现在一个格子上。</b></div>')

if mx == 0:
    A('<p>这两天没有采集到事件。</p>')
else:
    CW2, cl2 = 1120, 122
    cellw = (CW2 - cl2 - 104) / float(HOURS)   # leave room for the per-row peak
    cellh = 20
    gy = 40
    CH2 = gy + len(CATS) * 26 + 14
    COLS = ['#dce9f7', '#a9c9ea', '#6ba0d8', '#2f6fb8', '#14488c']
    # Colour is normalised PER ROW. WeChat rewrites hundreds of cache files an
    # hour, so a single global scale flattens every other row to blank. The row
    # peak is printed at the right of each row so the normalisation stays
    # visible and rows are not compared by colour alone.
    rowmax = {}
    for (_c, _h), _v in grid.items():
        if _v > rowmax.get(_c, 0):
            rowmax[_c] = _v
    A('<svg viewBox="0 0 %d %d" role="img">' % (CW2, CH2))
    A('<rect x="0" y="0" width="%d" height="%d" fill="#fbfdff" rx="8"/>' % (CW2, CH2))
    A('<text x="%.1f" y="17" font-size="11.5" fill="#31415a" text-anchor="middle">%s</text>'
      % (cl2 + 12 * cellw, esc(d1.strftime('%Y-%m-%d'))))
    A('<text x="%.1f" y="17" font-size="11.5" fill="#31415a" text-anchor="middle">%s</text>'
      % (cl2 + 36 * cellw, esc(d2.strftime('%Y-%m-%d'))))
    for hh in range(0, 24, 3):
        for base in (0, 24):
            A('<text x="%.1f" y="31" font-size="9.5" fill="#8fa0b3" text-anchor="middle">%02d</text>'
              % (cl2 + (base + hh) * cellw, hh))
    A('<line x1="%.1f" y1="34" x2="%.1f" y2="%d" stroke="#c8d4e2" stroke-dasharray="3 3"/>'
      % (cl2 + 24 * cellw, cl2 + 24 * cellw, CH2 - 10))
    for ci, cat in enumerate(CATS):
        y = gy + ci * 26
        A('<text x="%d" y="%.1f" font-size="11.5" fill="#40536a" text-anchor="end">%s</text>'
          % (cl2 - 9, y + 15, esc(cat)))
        A('<text x="%.1f" y="%.1f" font-size="9.5" fill="#8fa0b3" text-anchor="end">峰值 %d/时</text>'
          % (CW2 - 8, y + 15, rowmax.get(cat, 0)))
        for hi in range(HOURS):
            v = grid.get((cat, hi), 0)
            if not v:
                continue
            dd = d1 + datetime.timedelta(hours=hi)
            step = min(4, int(v / float(rowmax.get(cat) or 1) * 4.999))
            A('<rect x="%.1f" y="%d" width="%.1f" height="%d" fill="%s" rx="2">'
              '<title>%s %s:00 — %d 次</title></rect>'
              % (cl2 + hi * cellw + 0.5, y, cellw - 1, cellh, COLS[step],
                 esc(cat), dd.strftime('%m-%d %H'), v))
    A('</svg>')
    A('<div class="legend"><span>颜色 = 该行<b>自身</b>活动量的相对高低（按行归一化）：</span>'
      '<span><i style="background:#dce9f7"></i>少</span>'
      '<span><i style="background:#a9c9ea"></i></span>'
      '<span><i style="background:#6ba0d8"></i></span>'
      '<span><i style="background:#2f6fb8"></i></span>'
      '<span><i style="background:#14488c"></i>多</span>'
      '<span class="cap">跨行比较请看每行右侧的"峰值"，不要直接比颜色。</span></div>')

    cat_tot = {}
    for (cat, hi), v in grid.items():
        cat_tot[cat] = cat_tot.get(cat, 0) + v
    tot_all = sum(cat_tot.values()) or 1
    A('<h3>2.1 分类合计</h3>')
    for cat in CATS:
        if cat in cat_tot:
            A(bar_row(cat, cat_tot[cat], tot_all, '#2f6fb8'))

    A('<h3>2.2 这两天的完整事件序列</h3>')
    A('<p class="cap"><b>事件</b>（程序运行、计划任务、开关机、登录、WeGame 账号解析）逐条列出；'
      '<b>文件变动</b>（微信等每小时会改写几百个缓存/配置/头像文件）不逐条列，'
      '按「分类 + 小时」聚合成一行并给出类别构成。想看某个具体文件请用第 8 节的目录清单。</p>')

    def _ext(name):
        b = os.path.basename(str(name))
        for e in ('.db-wal', '.db-shm'):
            if b.endswith(e):
                return e
        return (os.path.splitext(b)[1] or '(无扩展名)').lower()

    def _cls(name):
        e = _ext(name)
        if e in ('.db', '.db-wal', '.db-shm'):
            return '数据库'
        if e in ('.xlog', '.tlg', '.log'):
            return '日志'
        if e in ('.ini', '.info', '.dat', '.pb', '.json', '.cfg', '.txt', '.xml'):
            return '配置'
        if e == '.lnk':
            return '快捷方式'
        if e == '.exe':
            return '程序'
        return '其它'

    NOTABLE = ('.xlog', '.tlg', '.db', '.db-wal', '.hash', '.statistic', '.info')

    rows2 = []
    bulk = {}
    for dt, cat, label, kind in focus_events:
        if kind == 'file':
            k = (cat, dt.strftime('%m-%d %H'))
            b = bulk.setdefault(k, {'n': 0, 'dt': dt, 'names': []})
            b['n'] += 1
            b['names'].append(label)
        else:
            rows2.append((dt, cat, label))
    for (cat, hh), b in bulk.items():
        cls = {}
        for nm in b['names']:
            c = _cls(nm)
            cls[c] = cls.get(c, 0) + 1
        parts = '、'.join('%s %d' % (k, v) for k, v in sorted(cls.items(), key=lambda kv: -kv[1]))
        ex = [nm for nm in b['names'] if _ext(nm) in NOTABLE][:3] or b['names'][:2]
        rows2.append((b['dt'], cat, '该小时 %d 个文件变动（%s）%s'
                      % (b['n'], parts, '；如 ' + '、'.join(ex) if ex else '')))
    rows2.sort(key=lambda x: x[0])

    A('<table><thead><tr><th style="width:165px">时间</th><th style="width:120px">分类</th>'
      '<th>事件</th></tr></thead><tbody>')
    for dt, cat, label in rows2:
        A('<tr><td class="mono">%s</td><td>%s</td><td class="mono" style="word-break:break-all">%s</td></tr>'
          % (dt.strftime('%m-%d %H:%M:%S'), esc(cat), esc(label)))
    A('</tbody></table>')

A('<h3>2.3 WeGame 的 QQ 登录 SDK（QQNTOpenSDK）</h3>')
if sdkloc:
    A('<p class="cap">该 SDK 为其宿主客户端维护按小时刷新的登录票据日志：日志逐小时连续出现 = '
      '宿主客户端一直在运行（<b>不是</b>每小时都有人在登录）。'
      '<b>宿主已查实</b>：SDK 本体就在应用自己的安装目录里 ——</p>')
    A('<table><thead><tr><th style="width:190px">时间</th><th style="width:90px">大小</th>'
      '<th>SDK 文件</th></tr></thead><tbody>')
    for e in sdkloc:
        A('<tr><td class="mono">%s</td><td class="mono">%d</td>'
          '<td class="mono" style="word-break:break-all">%s</td></tr>'
          % (esc(e.get('t')), int(e.get('s') or 0), esc(e.get('p'))))
    A('</tbody></table>')
else:
    A('<p class="cap">该 SDK 为其宿主客户端维护按小时刷新的登录票据日志：日志逐小时连续出现 = '
      '宿主客户端一直在运行（<b>不是</b>每小时都有人在登录）。'
      '<b>未能在磁盘上定位到该 SDK 的宿主程序</b>，故其归属未查实。</p>')
A('<p class="cap">账号库在 <code>sdk_db\\login.db</code>。</p>')
if prelogin:
    foc = [e for e in prelogin if (parse_s(e.get('t')) or datetime.datetime.min).date() in FOCUS]
    A('<table><thead><tr><th style="width:180px">时间</th><th style="width:230px">日志文件</th>'
      '<th style="width:90px">大小</th><th>appid</th></tr></thead><tbody>')
    for e in sorted(foc, key=lambda x: str(x.get('t'))):
        A('<tr><td class="mono">%s</td><td class="mono">%s</td><td class="mono">%d</td>'
          '<td class="mono">%s</td></tr>'
          % (esc(e.get('t')), esc(e.get('n')), int(e.get('s') or 0), esc(e.get('app'))))
    A('</tbody></table>')
    A('<p class="cap">这两天 %d 条；全部历史 %d 条。</p>' % (len(foc), len(prelogin)))
if sdkdb:
    A('<table><thead><tr><th style="width:180px">最后改动</th><th style="width:90px">大小</th>'
      '<th>文件</th></tr></thead><tbody>')
    for e in sdkdb:
        A('<tr><td class="mono">%s</td><td class="mono">%d</td>'
          '<td class="mono" style="word-break:break-all">%s</td></tr>'
          % (esc(e.get('t')), int(e.get('s') or 0), esc(e.get('p'))))
    A('</tbody></table>')
A('<h3>2.4 WeGame 登录账号（登录界面解析过的账号）</h3>')
A('<p class="cap">WeGame 把每个走到登录流程的账号头像缓存到 '
  '<code>%APPDATA%\\Tencent\\WeGame\\login_pic\\</code>，<b>文件名就是账号号本身</b>。'
  '文件出现的时间 = 该账号在这一刻被 WeGame 登录流程解析。这是"哪个 QQ 号被用来登 WeGame"的直接痕迹。</p>')
if wgaccounts:
    A('<table><thead><tr><th style="width:150px">账号</th><th style="width:200px">时间</th>'
      '<th style="width:100px">大小</th><th>说明</th></tr></thead><tbody>')
    for e in sorted(wgaccounts, key=lambda x: str(x.get('t')), reverse=True):
        A('<tr><td class="mono"><b>%s</b></td><td class="mono">%s</td><td class="mono">%d</td>'
          '<td>%s</td></tr>'
          % (esc(e.get('n')), esc(e.get('t')), int(e.get('s') or 0),
             '写入未完成（.tmp）' if e.get('tmp') else ''))
    A('</tbody></table>')
    _accs = sorted(set(str(e.get('n')) for e in wgaccounts if not e.get('tmp')))
    A('<p class="cap">共 %d 个账号出现过：<b>%s</b>。</p>'
      % (len(_accs), '、'.join(esc(a) for a in _accs)))
else:
    A('<p>未读到。</p>')

if gamlogin:
    A('<details><summary>展开游戏登录票据目录（WGLogin / TCLSCore，%d 个文件）</summary>'
      '<table><tbody>' % len(gamlogin))
    for e in sorted(gamlogin, key=lambda x: str(x.get('t')), reverse=True)[:80]:
        A('<tr><td class="mono" style="width:190px">%s</td>'
          '<td class="mono" style="word-break:break-all">%s</td></tr>'
          % (esc(e.get('t')), esc(e.get('p'))))
    A('</tbody></table></details>')
# ---- 2.5 broad program-execution sweep ----
A('<h3>2.5 这两天运行过的全部程序（Prefetch 全量，按用途分类）</h3>')
# 判断"窗口内运行过"用**运行历史**（最多 8 次），不能只看 .pf 的 mtime ——
# 某程序若在窗口内跑过、之后又跑过，mtime 会被顶到后面，只看 mtime 会整个漏掉。
# （某程序在窗口内跑过、之后又跑过时，mtime 会被顶到后面，只看 mtime 会整个漏掉。）
_pf_focus = []
_no_hist = 0
for _x in pf_all:
    _exe = _x[1]
    _d = pf_detail.get(_exe.upper()) or {}
    _runs = [t for t in _d.get('last8', []) if t and d1 <= t.date() <= d2]
    if _runs:
        _pf_focus.append((max(_runs), _exe))
    elif d1 <= _x[0].date() <= d2:
        _pf_focus.append((_x[0], _exe))      # 没有运行历史时退回 mtime
        _no_hist += 1
_by_cat = {}
for _t, _exe in _pf_focus:
    _by_cat.setdefault(app_cat(_exe), []).append((_t, _exe))
_priv_hits = [c for c in _by_cat if c in PRIVACY_CATS]
A('<div class="note">这是本机能拿到的最全"程序被运行过"证据，覆盖全部 %d 个 Prefetch 条目。'
  '<b>已解开 Windows 8+ 的 MAM 压缩</b>，所以除了"最后一次运行"，'
  '还能给出<b>累计运行次数</b>与<b>最近 8 次运行时间</b>；'
  '本节判断"窗口内跑过"用的就是运行历史，能看见被后续运行顶掉的那些。'
  '次数少而时间集中的是偶尔手动打开，次数多而均匀的多为后台服务。'
  '（%d 个程序没有运行历史，只能用 mtime 近似。）</div>' % (len(pf_all), _no_hist))


def _runs_of(exe):
    return (pf_detail.get(exe.upper()) or {}).get('runs')


def _freq(exe):
    r = _runs_of(exe)
    return '' if r is None else '(%d次)' % r


if _priv_hits:
    A('<p class="cap"><b>隐私相关分类命中：%s</b></p>' % esc('、'.join(_priv_hits)))
    A('<table><thead><tr><th style="width:150px">分类</th><th style="width:170px">最后运行</th>'
      '<th style="width:90px">累计次数</th><th>程序</th></tr></thead><tbody>')
    for cat in PRIVACY_CATS:
        rows_c = sorted(_by_cat.get(cat, []), reverse=True)
        for t, exe in rows_c:
            A('<tr><td>%s</td><td class="mono">%s</td><td class="mono">%s</td>'
              '<td class="mono">%s</td></tr>'
              % (esc(cat), t.strftime('%m-%d %H:%M:%S'),
                 esc(_runs_of(exe)), esc(exe)))
    A('</tbody></table>')
A('<h4>全部 %d 个分类</h4>' % len(_by_cat))
A('<table><thead><tr><th style="width:170px">分类</th><th style="width:90px">程序数</th>'
  '<th style="width:170px">最近一次</th><th>程序</th></tr></thead><tbody>')
for cat in sorted(_by_cat, key=lambda c: (c not in PRIVACY_CATS, -len(_by_cat[c]))):
    rows_c = sorted(_by_cat[cat], reverse=True)
    names = '、'.join(e + _freq(e) for _, e in rows_c[:26])
    if len(rows_c) > 26:
        names += ' …(共 %d)' % len(rows_c)
    A('<tr><td>%s</td><td>%d</td><td class="mono">%s</td>'
      '<td class="mono" style="word-break:break-all">%s</td></tr>'
      % (esc(cat), len(rows_c), rows_c[0][0].strftime('%m-%d %H:%M'), esc(names)))
A('</tbody></table>')

# ---- 2.5b 每次开机都启动的程序（"本来就在眼前"的来源）----
_boots = sorted({parse_s(r.get('time')) for r in boot
                 if str(r.get('id')) == '6005' and parse_s(r.get('time'))})
_boot_rows = boot_started_programs(_boots, pf_detail)
A('<h3>2.5b 开机后自动启动的程序（= 他登录后屏幕上本来就会出现的）</h3>')
A('<div class="note">自启项不写任何日志，但<b>它的运行时刻留在 Prefetch 的最近 8 次记录里</b>。'
  '下表是"运行时刻落在某次开机后 4 分钟内"的程序 —— 这些与你在不在无关，'
  '是桌面上本来就会开的东西；其中会开窗口的，就是<b>"他可能看到的内容"</b>。'
  '<b>分母是每个程序实际留下的记录数（最多 8）</b>，不是机器开过多少次机。</div>')
if _boot_rows:
    A('<table><thead><tr><th style="width:280px">程序</th>'
      '<th style="width:180px">开机后启动 / 有记录</th><th style="width:110px">累计运行</th>'
      '<th>最近一次开机后启动</th></tr></thead><tbody>')
    for r in _boot_rows:
        every = (r['boot_runs'] == r['recorded'] and r['recorded'] >= 2)
        tag = ('<span class="tag t-red">每次都是</span>' if every
               else '%d / %d' % (r['boot_runs'], r['recorded']))
        A('<tr><td class="mono">%s</td><td>%s</td><td class="mono">%d</td>'
          '<td class="mono">%s</td></tr>'
          % (esc(r['exe']), tag, r['total'], esc(r['last'].strftime('%m-%d %H:%M:%S'))))
    A('</tbody></table>')
    A('<p class="cap">已取到的开机时刻：%s</p>'
      % esc('、'.join(t.strftime('%m-%d %H:%M') for t in _boots[-8:])))
else:
    A('<p>（Prefetch 里没有可用的运行历史，或没有取到开机事件）</p>')

# ---- 2.6 browser history ----
A('<h3>2.6 浏览器访问与下载记录</h3>')
if bhist:
    _byhour = {}
    _dom = {}
    _internal = 0
    for name, t, url, title in bhist:
        if not t:
            continue
        k = t.strftime('%m-%d %H')
        _byhour[k] = _byhour.get(k, 0) + 1
        # Only real web pages get into the domain ranking. chrome-extension://
        # and about: targets would otherwise be ranked as a "site", showing a
        # scary-looking 32-char extension id as if it were a domain.
        if url.startswith('http://') or url.startswith('https://'):
            try:
                _dom[url.split('/')[2]] = _dom.get(url.split('/')[2], 0) + 1
            except Exception:
                pass
        else:
            _internal += 1
    A('<p class="cap">共 <b>%d</b> 条访问记录（%s）。'
      '这是判断"某时刻有没有人在用这台机器"最直接的证据。</p>'
      % (len(bhist), '、'.join('%s %d 条' % (esc(k), v) for k, v in sorted(bstat.items())
                              if isinstance(v, int) and v)))
    _hours = sorted(_byhour)
    A('<div class="note"><b>有浏览记录的小时：%s</b>。'
      '这些小时里明显有人在操作浏览器 —— 请与你实际在 / 不在电脑前的时间对照。'
      '反过来说，<b>没有记录的小时也不能直接断定没人</b>（浏览器可能没开，但也可能有别的操作）。</div>'
      % esc('、'.join(_hours)))
    A('<h4>按小时分布</h4>')
    _mxh = max(_byhour.values()) if _byhour else 1
    for k in _hours:
        A(bar_row(k, _byhour[k], _mxh, '#2f6fb8'))
    A('<h4>访问最多的站点</h4>')
    if _internal:
        A('<p class="cap">另有 %d 条是浏览器内部页 / 扩展页（如新标签页扩展），'
          '不计入下面的域名统计。</p>' % _internal)
    _mxd = max(_dom.values()) if _dom else 1
    for d3, c in sorted(_dom.items(), key=lambda kv: -kv[1])[:25]:
        A(bar_row(d3, c, _mxd, '#6ba0d8'))
    A('<h4>逐条访问（前 150 条）</h4>')
    A('<table><thead><tr><th style="width:160px">时间</th><th style="width:110px">浏览器</th>'
      '<th>标题 / 网址</th></tr></thead><tbody>')
    for name, t, url, title in bhist[:150]:
        A('<tr><td class="mono">%s</td><td>%s</td>'
          '<td class="mono" style="word-break:break-all">%s<br><span style="color:#8fa0b3">%s</span></td></tr>'
          % (t.strftime('%m-%d %H:%M:%S') if t else '-', esc(name), esc(title[:110]), esc(url[:150])))
    A('</tbody></table>')
    if len(bhist) > 150:
        A('<details><summary>展开其余 %d 条</summary><table><tbody>' % (len(bhist) - 150))
        for name, t, url, title in bhist[150:]:
            A('<tr><td class="mono" style="width:160px">%s</td><td style="width:110px">%s</td>'
              '<td class="mono" style="word-break:break-all">%s<br>%s</td></tr>'
              % (t.strftime('%m-%d %H:%M:%S') if t else '-', esc(name), esc(title[:90]), esc(url[:130])))
        A('</tbody></table></details>')
    if bdl:
        A('<h4>下载记录</h4>')
        A('<table><thead><tr><th style="width:160px">时间</th><th style="width:110px">浏览器</th>'
          '<th>目标文件</th></tr></thead><tbody>')
        for name, t, tp in bdl:
            A('<tr><td class="mono">%s</td><td>%s</td>'
              '<td class="mono" style="word-break:break-all">%s</td></tr>'
              % (t.strftime('%m-%d %H:%M:%S') if t else '-', esc(name), esc(tp)))
        A('</tbody></table>')
else:
    A('<p>这两天没有读到浏览器访问记录（也可能浏览器在运行导致库被锁）。</p>')

# ---- 2.7 windows timeline ----
A('<h3>2.7 Windows 时间线活动</h3>')
if timeline:
    A('<p class="cap">共 %d 条。多数是系统自身的记录；应用使用记录若为空，说明时间线功能未在收集。</p>' % len(timeline))
    A('<table><thead><tr><th style="width:180px">时间</th><th>应用 / 活动</th></tr></thead><tbody>')
    for t, app, at in timeline[:80]:
        A('<tr><td class="mono">%s</td><td class="mono">%s</td></tr>'
          % (t.strftime('%m-%d %H:%M:%S') if t else '-', esc(app)))
    A('</tbody></table>')
else:
    A('<div class="note">这两天<b>没有</b>任何时间线记录。该功能在本机未在收集'
      '（时间线默认在部分版本/策略下关闭），因此它<b>不能</b>用来反证"没人用过"。</div>')

# ---- 2.8 recycle bin ----
A('<h3>2.8 回收站删除记录</h3>')
A('<p class="cap">回收站当前共 <b>%d</b> 个删除项（跨全部时间）；其中落在 '
  '9/30–10/1 窗口内的有 <b>%d</b> 个，列在下面。</p>' % (len(recycled_all), len(recycled)))
if recycled:
    _auto = sum(1 for t, s, n in recycled
                if '__PSScriptPolicyTest' in n or '\\Temp\\' in n or '\\temp\\' in n)
    A('<table><thead><tr><th style="width:180px">删除时间</th><th style="width:90px">大小</th>'
      '<th>原路径</th></tr></thead><tbody>')
    for t, s, name in recycled:
        A('<tr><td class="mono">%s</td><td class="mono">%d</td>'
          '<td class="mono" style="word-break:break-all">%s</td></tr>'
          % (t.strftime('%m-%d %H:%M:%S'), s, esc(name)))
    A('</tbody></table>')
    if _auto == len(recycled):
        A('<div class="note">这 %d 条<b>全部是程序自动删除的临时文件</b>'
          '（<code>__PSScriptPolicyTest_*.psm1</code>：PowerShell 每次启动都会在 '
          '<code>%%TEMP%%</code> 建一个再删掉，时间点与三次开机吻合）。'
          '<b>不是有人手动删除文件。</b></div>' % len(recycled))
else:
    A('<div class="note">窗口内没有删除记录。注意：清空回收站会把证据一并抹掉，'
      '所以这里<b>不能</b>反证"没删过"。</div>')
if recycled_all:
    A('<details><summary>展开最近 20 个删除项（不限窗口）</summary>'
      '<table><thead><tr><th style="width:180px">删除时间</th><th style="width:90px">大小</th>'
      '<th>原路径</th></tr></thead><tbody>')
    for t, s, name in recycled_all[:20]:
        A('<tr><td class="mono">%s</td><td class="mono">%d</td>'
          '<td class="mono" style="word-break:break-all">%s</td></tr>'
          % (t.strftime('%Y-%m-%d %H:%M:%S'), s, esc(name)))
    A('</tbody></table></details>')

# ---- 2.9 downloads / desktop ----
A('<h3>2.9 下载文件夹与桌面的新增 / 改动</h3>')
if dlfiles:
    A('<table><thead><tr><th style="width:180px">时间</th><th style="width:110px">大小</th>'
      '<th>文件</th></tr></thead><tbody>')
    for t, p, s in dlfiles[:120]:
        A('<tr><td class="mono">%s</td><td class="mono">%s</td>'
          '<td class="mono" style="word-break:break-all">%s</td></tr>'
          % (t.strftime('%m-%d %H:%M:%S'), (('%d' % s) if s >= 0 else '目录'), esc(p)))
    A('</tbody></table>')
else:
    A('<p>这两天没有新增或改动。</p>')

# ---- 2.10 remote control (ToDesk) ----
A('<h3>2.10 远程控制软件（ToDesk）—— 有没有人连进来</h3>')
if not todesk:
    A('<p>本机未发现 ToDesk 日志目录。</p>')
else:
    _td_host_in = [t for t, _ in todesk['host'] if d1 <= datetime.date.fromisoformat(t[:10]) <= d2]
    _td_host_all = todesk['host']
    A('<div class="note">ToDesk 日志里两种"连接请求"长得几乎一样，'
      '<b>方向才是关键</b>：<br>'
      '<code>client recv connect request, myid=…</code> = <b>本机主动连出去</b>控制别人；<br>'
      '<code>host&nbsp;&nbsp; recv connect request, myid=…</code> = <b>本机是被控端</b>，有人连进来了。'
      '搞反就会得出完全相反的结论。</div>')
    if _td_host_in:
        A('<div class="card bad"><div class="v">窗口内被连入 %d 次</div>'
          '<div class="d">9/30–10/1 期间有外部设备连入本机，见下表</div></div>' % len(_td_host_in))
    else:
        A('<div class="card ok"><div class="v">窗口内被连入 0 次</div>'
          '<div class="d">9/30–10/1 期间没有任何外部设备连入本机</div></div>')
    A('<h4>按日期统计（%s 起）</h4>' % esc(todesk['earliest'] or '?'))
    _hd, _cd = {}, {}
    for t, _ in todesk['host']:
        _hd[t[:10]] = _hd.get(t[:10], 0) + 1
    for t, _ in todesk['client']:
        _cd[t[:10]] = _cd.get(t[:10], 0) + 1
    A('<table><thead><tr><th style="width:150px">日期</th>'
      '<th style="width:170px">被连入（本机被控）</th><th>主动连出</th></tr></thead><tbody>')
    for _d in sorted(set(list(_hd) + list(_cd))):
        _h = _hd.get(_d, 0)
        A('<tr%s><td class="mono">%s</td><td>%s</td><td>%s</td></tr>'
          % (' style="background:#fdf3f2"' if _h else '', esc(_d),
             ('<b style="color:#a02a1e">%d 次</b>' % _h) if _h else '0',
             _cd.get(_d, 0)))
    A('</tbody></table>')
    A('<h4>全部被连入记录</h4>')
    if _td_host_all:
        A('<table><thead><tr><th style="width:180px">时间</th><th>日志行</th></tr></thead><tbody>')
        for t, l in _td_host_all:
            A('<tr><td class="mono">%s</td><td class="mono" style="word-break:break-all">%s</td></tr>'
              % (esc(t), esc(l[:170])))
        A('</tbody></table>')
    else:
        A('<p>无。</p>')
    A('<h4>实际会话进程（每次真实远程连接会拉起一个 session 进程）</h4>')
    if todesk['sessions']:
        A('<table><thead><tr><th style="width:300px">日志</th><th style="width:180px">开始</th>'
          '<th style="width:180px">结束</th><th>行数</th></tr></thead><tbody>')
        for nm, a, b, n in todesk['sessions']:
            A('<tr><td class="mono">%s</td><td class="mono">%s</td><td class="mono">%s</td>'
              '<td class="mono">%d</td></tr>' % (esc(nm), esc(a), esc(b), n))
        A('</tbody></table>')
    A('<h4>配置（config.ini）</h4>')
    if todesk['config']:
        A('<table><thead><tr><th style="width:250px">项</th><th>值</th></tr></thead><tbody>')
        for k, v in todesk['config'].items():
            A('<tr><td class="mono">%s</td><td class="mono" style="word-break:break-all">%s</td></tr>'
              % (esc(k), esc(v)))
        A('</tbody></table>')
    A('<div class="note"><b>能查到的范围有限</b>：ToDesk 日志在文件名上只到 <b>%s</b>，'
      '更早的记录已被清理（缓存文件可回溯到 5 月，但没有会话明细）。'
      '因此本节的结论<b>只对 %s 之后成立</b>。另：被连入需要密码或授权，'
      '本机 <code>TfaForConn=%s</code>（0 = 未启用连接双因素）。</div>'
      % (esc(todesk['earliest'] or '?'), esc(todesk['earliest'] or '?'),
         esc(todesk['config'].get('TfaForConn', '?'))))
# ---- 2.10b other remote-control tools ----
_or_inst = [t for t in other_remote['tools'] if t['installed']]
A('<h4>2.10b 其它远程控制软件 —— 只查 ToDesk 会给假的安全结论</h4>')
if not _or_inst:
    A('<p>已知的其它远控软件（AnyDesk / TeamViewer / 向日葵 / RustDesk / ScreenConnect / '
      'LogMeIn / VNC）<b>本机都没有安装</b>。所以"没有远程连入"这个结论，'
      '在远控软件这一路上是完整的，不是只看了 ToDesk 就下的。</p>')
else:
    A('<div class="note">这些是本机<b>装了的</b>其它远控软件。装了不等于被用过，'
      '但装了就有用过的可能，需要逐个看日志。</div>')
    A('<table><thead><tr><th style="width:200px">软件</th><th>安装目录 / 最近的日志</th>'
      '</tr></thead><tbody>')
    for t in _or_inst:
        cell = []
        for d in t['dirs'][:2]:
            cell.append('<div class="mono">%s</div>' % esc(d))
        for tm, f in t['logs'][:4]:
            cell.append('<div class="mono">%s  %s</div>'
                        % (tm.strftime('%m-%d %H:%M') if tm else '?', esc(f)))
        A('<tr><td><b>%s</b></td><td>%s</td></tr>'
          % (esc(t['name']), ''.join(cell) or '<span class="muted">已安装，未找到日志</span>'))
    A('</tbody></table>')
    A('<p class="cap">"已安装，未找到日志"不等于没被用过 —— 有些工具把会话记录放在别处或根本不落盘。</p>')

A('<h4>2.10c 本机主动连出去的 RDP 目标（mstsc 历史）</h4>')
if other_remote['mstsc']:
    A('<p class="cap">这是<b>本机作为客户端连出去</b>的目标，与"有人连进来"是反方向，'
      '只作背景参考。注册表里没有时间戳，所以给不出"什么时候连的"。</p>')
    A('<ul>%s</ul>' % ''.join('<li class="mono">%s</li>' % esc(x)
                              for x in other_remote['mstsc'][:10]))
else:
    A('<p>没有本机连出去的 RDP 历史。</p>')
A('</section>')

# ================= 3. limits =================
A('<section><h2>三、这份报告查不到什么（先说清楚）</h2>')
A('<div class="note">下面几条是本次排查的<b>硬缺口</b>。缺了它们，"某程序被运行过"能证明，'
  '"运行了几次 / 由谁启动"证明不了。请据此判断结论强度。</div>')
A('<table><thead><tr><th style="width:200px">缺口</th><th>实测状态</th><th style="width:110px">影响</th></tr></thead><tbody>')

if int(audit.get('count') or 0) <= 60:
    A('<tr><td><b>进程创建审计（4688）</b></td>'
      '<td>实际<b>关闭</b>：安全日志中 4688 仅 %s 条，跨度 %s → %s，全部是开机瞬间的系统进程。'
      '拿不到每次启动的精确时间、父进程与发起账户。</td><td><span class="tag t-red">高</span></td></tr>'
      % (esc(audit.get('count')), esc(audit.get('oldest')), esc(audit.get('newest'))))
else:
    A('<tr><td><b>进程创建审计（4688）</b></td><td>已开启，共 %s 条</td>'
      '<td><span class="tag t-green">可用</span></td></tr>' % esc(audit.get('count')))

mstr = '、'.join('<code>%s</code>（%d 个文件）' % (esc(r.get('magic')), int(r.get('count') or 0))
                 for r in magic[:3]) if magic else '未知'
_nohist = sum(1 for d in pf_detail.values() if not d.get('last8'))
A('<tr><td><b>Prefetch 运行历史</b></td>'
  '<td>本机 Prefetch 头为 %s。<code>53&nbsp;43&nbsp;43&nbsp;41</code> 是未压缩的 "SCCA"；'
  '<code>4d&nbsp;41&nbsp;4d&nbsp;04</code> 是 "MAM" —— <b>MAM 是压缩，不是新格式</b>，'
  '按 MS-XCA 的 LZ77+Huffman 解开后仍是标准 v30/v31 布局，'
  '<b>运行次数与最近 8 次运行时间都能读到</b>，本节判断"窗口内跑过"用的就是它们。'
  '真正剩下的缺口有两条：<b>Prefetch 会被清理</b>（系统维护与第三方"系统清理"都会删 .pf），'
  '而且<b>实测有执行根本没写进 Prefetch</b>。所以「Prefetch 里没有」不能当「没运行过」——'
  '另用 BAM 补差集（见隐私报告的「执行记录差集」一项）。'
  '本机有 <b>%d</b> 个程序没有运行历史，只能用 mtime 近似。</td>'
  '<td><span class="tag t-amber">中</span></td></tr>' % (mstr, _nohist))

A('<tr><td><b>UserAssist 运行次数</b></td>'
  '<td>本机共读到 %d 条 UserAssist 记录，其中 %d 条带有效"最后运行时间"（其余 %d 条时间戳为 0）。'
  '全部记录的运行次数字段最大仅 <b>%d</b>（连高频程序如 csrss.exe 也是同量级）——'
  '该版本不落盘运行次数。</td><td><span class="tag t-amber">中</span></td></tr>'
  % (ua_total, ua_n, ua_total - ua_n, ua_maxcnt))
A('</tbody></table>')
A('</section>')

# ================= 3. timeline =================
A('<section><h2>四、%s 事件时间线</h2>' % day.strftime('%Y-%m-%d'))
A('<p class="cap">开机、登录、程序运行、计划任务触发放在同一条轴上；'
  '若两条紧邻，说明后者很可能是前者引起的。这是判断"某次运行是否可解释"的第一现场。</p>')

kind_colour = {'boot': '#c0392b', 'logon': '#1a5fb4', 'exec': '#127d45', 'task': '#c07a06'}
kind_name = {'boot': '开机', 'logon': '登录', 'exec': '程序运行', 'task': '计划任务'}

# Merge events of the same kind that fired within 90s of each other. Several
# unrelated Lds* tasks all fire on the same second at logon; without merging
# they crowd out the labels of the QQ/WeChat launches, which are the point.
tlm = []
for dt, kind, label, short in tl:
    if tlm and tlm[-1]['kind'] == kind and (dt - tlm[-1]['dt']).total_seconds() <= 90:
        g = tlm[-1]
        g['labels'].append(label)
        g['counts'][short] = g['counts'].get(short, 0) + 1
        g['short'] = '、'.join(n if c == 1 else '%s×%d' % (n, c) for n, c in g['counts'].items())
    else:
        tlm.append({'dt': dt, 'kind': kind, 'labels': [label],
                    'counts': {short: 1}, 'short': short})

W, H = 1120, 250
pad_l, pad_r = 84, 30          # wide enough that "计划任务" is not clipped
x0, x1 = pad_l, W - pad_r


def xpos(dt):
    secs = dt.hour * 3600 + dt.minute * 60 + dt.second
    return x0 + (secs / 86400.0) * (x1 - x0)


def place_label(xx, yy, used):
    """Free vertical slot for a label, always inside the canvas.

    Tries above the lane first, then below. Returns None when every slot is
    taken -- the dot keeps its <title> tooltip, so the information stays
    reachable instead of being drawn off-canvas where it is invisible.
    """
    for dy in (-11, 15, -24, 28, -37, 41, -50, 54):
        ty = yy + dy
        if not (14 <= ty <= H - 32):
            continue
        if not any(abs(xx - ux) < 76 and abs(ty - uy) < 11 for ux, uy in used):
            return ty
    return None


A('<svg viewBox="0 0 %d %d" role="img">' % (W, H))
A('<rect x="0" y="0" width="%d" height="%d" fill="#fbfdff" rx="8"/>' % (W, H))
for h in range(0, 25, 2):
    xx = x0 + (h * 3600 / 86400.0) * (x1 - x0)
    A('<line x1="%.1f" y1="34" x2="%.1f" y2="%d" stroke="#e3e9f0"/>' % (xx, xx, H - 34))
    A('<text x="%.1f" y="24" font-size="11" fill="#7a8a9c" text-anchor="middle">%02d:00</text>' % (xx, h))
lane = {'boot': 64, 'logon': 100, 'task': 136, 'exec': 172}
for kind, yy in lane.items():
    A('<text x="%d" y="%d" font-size="11.5" fill="#5b6b7d" text-anchor="end">%s</text>'
      % (pad_l - 8, yy + 4, kind_name[kind]))
    A('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#eef2f7"/>' % (x0, yy, x1, yy))

# 1) draw the dots in chronological order
for g in tlm:
    xx = xpos(g['dt'])
    yy = lane[g['kind']]
    A('<circle cx="%.1f" cy="%.1f" r="5" fill="%s" opacity=".9"><title>%s %s</title></circle>'
      % (xx, yy, kind_colour[g['kind']], fmt_t(g['dt']), esc(' / '.join(g['labels']))))

# 2) place labels by priority, so the QQ/WeChat launches win the free slots
PRIO = {'exec': 0, 'boot': 1, 'logon': 1, 'task': 2}
used = []
dropped = 0
for g in sorted(tlm, key=lambda g: (PRIO[g['kind']], g['dt'])):
    xx = xpos(g['dt'])
    yy = lane[g['kind']]
    ty = place_label(xx, yy, used)
    if ty is None:
        dropped += 1
        continue
    used.append((xx, ty))
    A('<text x="%.1f" y="%.1f" font-size="10.5" fill="#31415a" text-anchor="middle">%s</text>'
      % (xx, ty, esc(g['short'])))
A('</svg>')
A('<p class="cap">同一泳道内 90 秒以内的同类事件已合并为一个标签（如登录时一同触发的多个鲁大师任务）。'
  '标签按重要性分配位置：程序运行优先于计划任务。%s</p>'
  % ('有 %d 个标签因空间不足未绘制，对应圆点仍可悬浮查看。' % dropped if dropped else ''))

A('<div class="legend">')
for k in ('boot', 'logon', 'task', 'exec'):
    A('<span><i style="background:%s"></i>%s</span>' % (kind_colour[k], kind_name[k]))
A('</div>')

if tl:
    A('<table><thead><tr><th style="width:110px">时间</th><th style="width:90px">类型</th><th>事件</th></tr></thead><tbody>')
    for dt, kind, label, short in tl:
        A('<tr><td class="mono">%s</td><td><span class="tag t-%s">%s</span></td><td>%s</td></tr>'
          % (fmt_t(dt), {'boot': 'red', 'logon': 'green', 'exec': 'grey', 'task': 'amber'}[kind],
             kind_name[kind], esc(label)))
    A('</tbody></table>')
A('</section>')

# ================= 4. launch times =================
A('<section><h2>五、QQ / 微信 / WeGame 最后运行时间</h2>')
A('<div class="note">两路互相印证：<b>5.1 Prefetch</b>（用 .pf 里记录的运行历史，'
  '不是文件修改时间 —— 见下）与 <b>5.2 UserAssist</b>。'
  '这里给的是<b>最后一次运行时刻与累计次数</b>。</div>')

A('<h3>5.1 Prefetch（运行历史 = 最后一次运行 + 累计次数）</h3>')
A('<p class="cap">时间取自 .pf 内部记录的运行历史，<b>不是 .pf 文件的修改时间</b>。'
  '某程序若在目标时段跑过、之后又跑过，mtime 会被顶到后面 —— 只看 mtime 会把那次运行整个漏掉，'
  '而报告看起来完全正常。没有运行历史的条目（新装、或历史被清理）才退回用文件时间，已在下表标出。</p>')
A('<table><thead><tr><th style="width:190px">最后运行</th><th>文件</th>'
  '<th style="width:90px">累计次数</th><th style="width:150px">来源</th></tr></thead><tbody>')
for dt, name, cnt, srcname in pf:
    delta = now - dt
    secs = delta.total_seconds()
    dd = ('%.1f 天前' % (secs / 86400)) if secs > 86400 else ('%.1f 小时前' % (secs / 3600))
    hot = ' style="background:#f2faf5"' if dt.date() == day else ''
    A('<tr%s><td class="mono">%s</td><td>%s</td><td class="mono">%s</td>'
      '<td class="mono" style="font-size:12px">%s</td></tr>'
      % (hot, fmt(dt), esc(name), (str(cnt) if cnt else '—'), esc(srcname)))
A('</tbody></table>')

A('<h3>5.2 UserAssist（记录"从资源管理器 / 开始菜单"发起的启动）</h3>')
A('<p class="cap">这一路比 Prefetch 更有意义：它记录的是<b>由用户界面操作触发</b>的启动，'
  '自动启动（Run 键、服务、计划任务）一般不会写进这里。</p>')
A('<table><thead><tr><th style="width:190px">最后运行</th><th>程序</th></tr></thead><tbody>')
for dt, name in ua_ten[:30]:
    hot = ' style="background:#f2faf5"' if dt.date() == day else ''
    A('<tr%s><td class="mono">%s</td><td class="mono" style="word-break:break-all">%s</td></tr>' % (hot, fmt(dt), esc(name)))
A('</tbody></table>')
if len(ua_ten) > 30:
    A('<details><summary>展开全部 %d 条 UserAssist 命中项</summary><table><tbody>' % len(ua_ten))
    for dt, name in ua_ten:
        A('<tr><td class="mono" style="width:190px">%s</td><td class="mono" style="word-break:break-all">%s</td></tr>' % (fmt(dt), esc(name)))
    A('</tbody></table></details>')
A('</section>')

# ================= 5. QQ chat window activity (NEW) =================
A('<section><h2>六、QQ 聊天窗口活动</h2>')
A('<div class="note">QQ NT 在 <code>%APPDATA%\\Microsoft\\Windows\\Recent</code> 下为每个被打开的聊天窗口'
  '写一个快捷方式，文件名里带着 <code>fuin=&lt;QQ号&gt;</code>（收到通知时登录着的账号）和 '
  '<code>peerName=&lt;对方/群名&gt;</code>。文件的修改时间≈该窗口被打开的时间。'
  '<b>这是"某个 QQ 号当时确实在线并与人对话"的直接痕迹。</b></div>')

if ntqq_recents:
    by_acct = {}
    for r in ntqq_recents:
        by_acct.setdefault(r['fuin'], []).append(r)
    A('<h3>6.1 按账号汇总</h3>')
    A('<table><thead><tr><th style="width:150px">QQ 号（fuin）</th><th style="width:100px">窗口记录</th>'
      '<th style="width:200px">最早</th><th style="width:200px">最晚</th><th>对应本地数据目录最新写入</th></tr></thead><tbody>')
    acct_map = {a['account']: a for a in qq_accts}
    for acct, rows in sorted(by_acct.items(), key=lambda kv: -(len(kv[1]))):
        ts = [r['time'] for r in rows if r['time']]
        lo, hi = (min(ts), max(ts)) if ts else (None, None)
        local = acct_map.get(acct)
        localtxt = fmt(local['newest']) if local else '<span class="tag t-amber">无对应数据目录</span>'
        A('<tr><td class="mono"><b>%s</b></td><td>%d</td><td class="mono">%s</td>'
          '<td class="mono">%s</td><td class="mono">%s</td></tr>'
          % (esc(acct), len(rows), fmt(lo), fmt(hi), localtxt))
    A('</tbody></table>')
    A('<p class="cap">若"窗口记录"的最晚时间<b>晚于</b>"本地数据目录最新写入"，说明该账号在近期还在线活动，'
      '但消息库没有新的落盘写入——通常是只收了通知、没同步消息，或库已被清理。</p>')

    A('<h3>6.2 逐条明细</h3>')
    A('<table><thead><tr><th style="width:170px">窗口打开时间</th><th style="width:140px">账号</th>'
      '<th style="width:70px">类型</th><th>对方 / 群</th></tr></thead><tbody>')
    for r in ntqq_recents[:60]:
        ct = {'1': '单聊', '2': '群聊'}.get(r['chattype'], r['chattype'])
        A('<tr><td class="mono">%s</td><td class="mono">%s</td><td>%s</td><td>%s</td></tr>'
          % (fmt(r['time']), esc(r['fuin']), esc(ct), esc(r['peer'])))
    A('</tbody></table>')
    if len(ntqq_recents) > 60:
        A('<details><summary>展开全部 %d 条</summary><table><tbody>' % len(ntqq_recents))
        for r in ntqq_recents:
            A('<tr><td class="mono" style="width:170px">%s</td><td class="mono" style="width:140px">%s</td><td>%s</td></tr>'
              % (fmt(r['time']), esc(r['fuin']), esc(r['peer'])))
        A('</tbody></table></details>')
else:
    A('<p>未在 Recent 中发现 QQ 聊天窗口记录。</p>')
A('</section>')

# ================= 6. logons =================
A('<section><h2>七、登录与远程访问</h2>')
A('<h3>7.1 近 7 天登录事件按类型分布</h3>')
LTNAME = {'0': '类型 0 未知', '2': '类型 2 交互式（本地键盘）', '3': '类型 3 网络',
          '4': '类型 4 批处理', '5': '类型 5 服务', '7': '类型 7 解锁',
          '8': '类型 8 网络明文', '10': '类型 10 远程桌面(RDP)', '11': '类型 11 缓存凭据'}
tot = sum(lt_counts.values())
for lt, c in sorted(lt_counts.items(), key=lambda kv: -kv[1]):
    col = '#c0392b' if lt in ('3', '8', '10') else ('#1a5fb4' if lt == '2' else '#94a3b8')
    A(bar_row(LTNAME.get(lt, '类型 ' + lt), c, tot, col))
A('<p class="cap">红色 = 远程 / 网络类登录（本机为 0）。蓝色 = 本地键盘交互登录。</p>')

A('<h3>7.2 交互式（本地控制台）登录明细</h3>')
A('<table><thead><tr><th style="width:170px">时间</th><th>账户</th><th>来源</th><th>发起进程</th></tr></thead><tbody>')
for r in interactive:
    A('<tr><td class="mono">%s</td><td>%s</td><td class="mono">%s</td><td class="mono" style="word-break:break-all">%s</td></tr>'
      % (esc(r.get('time')), esc(r.get('user')), esc(r.get('src')), esc(r.get('proc'))))
A('</tbody></table>')

A('<h3>7.3 锁屏 / 解锁 / 注销 / 会话重连（近 10 天）</h3>')
SN = {4800: '锁屏', 4801: '解锁', 4634: '注销', 4647: '用户主动注销', 4778: '会话重连', 4779: '会话断开'}
A('<table><thead><tr><th style="width:170px">时间</th><th style="width:140px">事件</th></tr></thead><tbody>')
for r in session:
    A('<tr><td class="mono">%s</td><td>%s</td></tr>' % (esc(r.get('time')), esc(SN.get(int(r.get('id') or 0), r.get('id')))))
A('</tbody></table>')
A('<p class="cap">若目标时间段内既无"锁屏"也无"注销"，说明那段时间会话一直开着、未上锁。</p>')

A('<h3>7.4 开机 / 关机</h3>')
BN = {6005: '事件日志服务启动（≈开机）', 6006: '事件日志服务停止（≈关机）',
      6008: '上次关机是意外的', 1074: '被进程发起关机', 41: '内核崩溃/断电'}
A('<table><thead><tr><th style="width:170px">时间</th><th>事件</th></tr></thead><tbody>')
for r in boot:
    A('<tr><td class="mono">%s</td><td>%s</td></tr>' % (esc(r.get('time')), esc(BN.get(int(r.get('id') or 0), r.get('id')))))
A('</tbody></table>')

if failed:
    A('<h3>7.5 登录失败（近 7 天，前 20 条）</h3>')
    A('<table><thead><tr><th style="width:170px">时间</th><th>账户</th><th>来源</th></tr></thead><tbody>')
    for r in failed[:20]:
        A('<tr><td class="mono">%s</td><td>%s</td><td class="mono">%s</td></tr>'
          % (esc(r.get('time')), esc(r.get('user')), esc(r.get('src'))))
    A('</tbody></table>')
A('</section>')

# ================= 7. accounts & local data =================
A('<section><h2>八、账号与本地数据</h2>')

A('<h3>8.1 QQ 账号目录（%s）</h3>' % esc(os.path.join(HOME, 'Documents', 'Tencent Files')))
A('<table><thead><tr><th style="width:150px">目录名</th><th style="width:200px">数据库最后写入</th>'
  '<th style="width:100px">库文件数</th><th>最新库</th></tr></thead><tbody>')
for a in qq_accts:
    A('<tr><td class="mono"><b>%s</b></td><td class="mono">%s</td><td>%s</td><td class="mono">%s</td></tr>'
      % (esc(a['account']), fmt(a['newest']), a['db_count'], esc(a['newest_name'])))
A('</tbody></table>')
A('<p class="cap">"数据库最后写入"是该账号下所有 <code>nt_db\\*.db</code> 中最新的一个 —— '
  '它反映该账号最后一次真正收发消息的时间；只启动客户端、停在登录界面不会改动这里。</p>')

A('<h3>8.2 微信每日日志（有当天文件 = 当天微信跑过）</h3>')
wx_strip = []
for day_s, mtime, _ in wx_logs:
    h = mtime.hour
    cls = 's-night' if (h >= 20 or h < 2) else ('s-dawn' if h < 8 else ('s-day' if h < 18 else 's-eve'))
    wx_strip.append('<div class="cell %s" title="%s 最后写入 %s">%s</div>'
                    % (cls, esc(day_s), mtime.strftime('%H:%M'), esc(day_s[4:6] + '/' + day_s[6:8])))
A('<div class="strip">%s</div>' % ''.join(wx_strip))
A('<div class="legend"><span><i class="s-day"></i>白天收尾</span><span><i class="s-eve"></i>傍晚(18–20)</span>'
  '<span><i class="s-night"></i>深夜(20–次日2)</span><span><i class="s-dawn"></i>凌晨(2–8)</span></div>')

# --- NEW: line chart of the last-write time-of-day per day ---
if len(wx_logs) >= 2:
    A('<h4>每日最后写入时刻</h4>')
    CW, CH = 1120, 250
    cl, cr, ct, cb = 62, 30, 26, 46
    px0, px1 = cl, CW - cr
    py0, py1 = ct, CH - cb

    def yh(hour):
        return py0 + (hour / 24.0) * (py1 - py0)

    A('<svg viewBox="0 0 %d %d" role="img">' % (CW, CH))
    A('<rect x="0" y="0" width="%d" height="%d" fill="#fbfdff" rx="8"/>' % (CW, CH))
    for hh in range(0, 25, 4):
        yy = yh(hh)
        A('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#e8edf3"/>' % (px0, yy, px1, yy))
        A('<text x="%d" y="%.1f" font-size="10.5" fill="#7a8a9c" text-anchor="end">%02d:00</text>'
          % (cl - 8, yy + 4, hh))
    n = len(wx_logs)
    step = (px1 - px0) / max(1, n - 1)
    # Data-driven anomaly rule: a day is flagged when its last write is more
    # than 3 hours away from the median across all days. Nothing is hardcoded
    # to a particular date or clock time.
    hours = sorted(t.hour + t.minute / 60.0 for _, t, _ in wx_logs)
    med = hours[len(hours) // 2] if hours else 0.0
    pts = []
    for i, (day_s, mtime, _) in enumerate(wx_logs):
        x = px0 + i * step
        y = yh(mtime.hour + mtime.minute / 60.0)
        pts.append((x, y, day_s, mtime))
    A('<polyline fill="none" stroke="#2e8b57" stroke-width="2" points="%s"/>'
      % ' '.join('%.1f,%.1f' % (x, y) for x, y, _, _ in pts))
    for x, y, day_s, mtime in pts:
        odd = abs((mtime.hour + mtime.minute / 60.0) - med) > 3
        col = '#c0392b' if odd else '#2e8b57'
        A('<circle cx="%.1f" cy="%.1f" r="4.5" fill="%s"><title>%s 最后写入 %s</title></circle>'
          % (x, y, col, esc(day_s), mtime.strftime('%H:%M')))
        if odd:
            A('<text x="%.1f" y="%.1f" font-size="10.5" fill="#a02a1e" text-anchor="middle">%s</text>'
              % (x, y - 10, mtime.strftime('%H:%M')))
        A('<text x="%.1f" y="%d" font-size="10" fill="#7a8a9c" text-anchor="middle">%s</text>'
          % (x, CH - 24, day_s[4:6] + '/' + day_s[6:8]))
    A('</svg>')
    A('<p class="cap">纵轴是"当天微信日志最后被写入的时刻"。红点 = 与所有天的中位时刻相差 3 小时以上的异常日'
      '（判据由数据算出，非写死）。常年接近午夜说明微信几乎整天开着；'
      '某天突然掉到下午通常对应崩溃或强制关机。</p>')

A('<h3>8.3 微信账号与数据目录</h3>')
if wx_login:
    A('<p class="cap">登录目录里的子目录名即登录过的微信账号 ID：</p>')
    A('<table><thead><tr><th>wxid</th><th style="width:200px">目录时间</th></tr></thead><tbody>')
    for e, m in wx_login:
        A('<tr><td class="mono">%s</td><td class="mono">%s</td></tr>' % (esc(e), fmt(m)))
    A('</tbody></table>')

for wd in wx_data:
    A('<h4>%s &nbsp;<span class="cap">（%s）</span></h4>' % (esc(wd['account']), esc(wd['root'])))
    A('<table><thead><tr><th style="width:200px">子目录</th><th style="width:90px">类型</th>'
      '<th style="width:200px">最后改动</th></tr></thead><tbody>')
    for cname, isdir, cm in wd['children'][:16]:
        A('<tr><td class="mono">%s</td><td>%s</td><td class="mono">%s</td></tr>'
          % (esc(cname), '目录' if isdir else '文件', fmt(cm)))
    A('</tbody></table>')
    if len(wd['children']) > 16:
        A('<details><summary>展开其余 %d 项</summary><table><tbody>' % (len(wd['children']) - 16))
        for cname, isdir, cm in wd['children'][16:]:
            A('<tr><td class="mono" style="width:220px">%s</td><td class="mono" style="width:200px">%s</td></tr>'
              % (esc(cname), fmt(cm)))
        A('</tbody></table></details>')

if ten_installs:
    A('<h4>注册表中的安装路径</h4>')
    A('<table><thead><tr><th style="width:130px">产品</th><th>值</th></tr></thead><tbody>')
    for sub, vals in ten_installs:
        for k2, v2 in vals.items():
            A('<tr><td class="mono">%s</td><td class="mono">%s = %s</td></tr>' % (esc(sub), esc(k2), esc(v2)))
    A('</tbody></table>')

A('<h3>8.4 已安装的腾讯 / 游戏软件（读自卸载注册表）</h3>')
if software:
    A('<table><thead><tr><th style="width:190px">名称</th><th style="width:120px">版本</th>'
      '<th style="width:210px">发行者</th><th>安装位置</th></tr></thead><tbody>')
    for r in software:
        A('<tr><td>%s</td><td class="mono">%s</td><td>%s</td>'
          '<td class="mono" style="word-break:break-all">%s</td></tr>'
          % (esc(r.get('name')), esc(r.get('ver')), esc(r.get('pub')), esc(r.get('loc'))))
    A('</tbody></table>')
else:
    A('<p>未读到。</p>')

A('<h3>8.5 近 4 天应用 / 系统错误与警告</h3>')
if appevents:
    _ae = sorted(appevents, key=lambda x: str(x.get('t')), reverse=True)
    A('<table><thead><tr><th style="width:150px">时间</th><th style="width:70px">日志</th>'
      '<th style="width:80px">级别</th><th style="width:190px">来源</th><th>消息</th></tr></thead><tbody>')
    for r in _ae[:60]:
        lvl = str(r.get('lvl'))
        cls = 't-red' if lvl in ('错误', '严重', 'Error', 'Critical') else 't-amber'
        A('<tr><td class="mono">%s</td><td>%s</td><td><span class="tag %s">%s</span></td>'
          '<td class="mono">%s</td><td class="mono" style="word-break:break-all">%s</td></tr>'
          % (esc(r.get('t')), esc(r.get('log')), cls, esc(lvl), esc(r.get('prov')), esc(r.get('msg'))))
    A('</tbody></table>')
    if len(_ae) > 60:
        A('<details><summary>展开其余 %d 条</summary><table><tbody>' % (len(_ae) - 60))
        for r in _ae[60:]:
            A('<tr><td class="mono" style="width:150px">%s</td><td>%s</td><td class="mono">%s</td>'
              '<td class="mono" style="word-break:break-all">%s</td></tr>'
              % (esc(r.get('t')), esc(r.get('log')), esc(r.get('prov')), esc(r.get('msg'))))
        A('</tbody></table></details>')
else:
    A('<p>未读到。</p>')
A('</section>')

# ================= 9. autoruns (now collected, not hardcoded) =================
A('<section><h2>九、自启动来源复查</h2>')
A('<div class="note">本节每次运行都会<b>重新读取</b>注册表 Run 键、启动文件夹、Winlogon 与服务表，'
  '而不是沿用上次结论。目的是回答：QQ / 微信有没有"不经过你操作就自动跑起来"的途径。</div>')
A('<table><thead><tr><th style="width:230px">检查位置</th><th style="width:110px">记录数</th><th>说明</th></tr></thead><tbody>')
bywhere = {}
for r in autoruns:
    bywhere.setdefault(str(r.get('where', '?')), []).append(r)
WHY = {
    'HKCU Run': '当前用户的登录自启',
    'HKLM Run': '所有用户的登录自启（64 位）',
    'HKLM Run (32-bit)': '所有用户的登录自启（32 位）',
    'HKCU RunOnce': '当前用户一次性自启',
    'HKLM RunOnce': '所有用户一次性自启',
    'Startup folder (user)': '当前用户启动文件夹',
    'Startup folder (all users)': '公共启动文件夹',
    'Winlogon': '登录外壳（Userinit / Shell）',
    'Service': '系统服务（自动/手动启动）',
}
for w, rows in bywhere.items():
    n_hit = len([r for r in rows if STRICT.search(str(r.get('value', '')) + ' ' + str(r.get('name', '')))])
    tag = ('<span class="tag t-red">命中 %d</span>' % n_hit) if n_hit else '<span class="tag t-green">无</span>'
    A('<tr><td><b>%s</b></td><td>%d</td><td>%s %s</td></tr>' % (esc(w), len(rows), tag, esc(WHY.get(w, ''))))
A('</tbody></table>')

A('<h3>9.1 自启动记录中命中腾讯 / 多开工具的条目</h3>')
if ar_hits:
    A('<table><thead><tr><th style="width:180px">位置</th><th style="width:200px">名称</th><th>命令 / 路径</th></tr></thead><tbody>')
    for r in ar_hits:
        A('<tr><td>%s</td><td class="mono">%s</td><td class="mono" style="word-break:break-all">%s</td></tr>'
          % (esc(r.get('where')), esc(r.get('name')), esc(r.get('value'))))
    A('</tbody></table>')
else:
    A('<div class="card ok"><div class="v">未命中</div>'
      '<div class="d">在 %d 条自启动记录中（含 %d 项服务），没有一条指向 QQ / 微信客户端或多开工具。'
      '即：<b>它们不是常规开机自启</b>——出现在时间线上的每次运行都需要另有解释。</div></div>'
      % (len(autoruns), len(bywhere.get('Service', []))))

A('<h3>9.2 会自行启动腾讯系程序的计划任务</h3>')
sus = [r for r in tasks if ('Lds' in str(r.get('name', ''))
                            or 'Wechat' in str(r.get('name', ''))
                            or 'multi_wechat' in str(r.get('act', '')).lower())]
if sus:
    A('<table><thead><tr><th style="width:190px">任务</th><th style="width:80px">状态</th>'
      '<th style="width:165px">上次运行</th><th style="width:130px">返回码</th><th>命令</th></tr></thead><tbody>')
    for r in sus:
        rc = r.get('rc')
        bad = (rc not in (0, None)) and str(rc) not in ('267009', '267011')
        A('<tr><td class="mono">%s</td><td>%s</td><td class="mono">%s</td>'
          '<td class="mono">%s%s</td><td class="mono" style="word-break:break-all">%s</td></tr>'
          % (esc(r.get('name')), esc(r.get('state')), esc(r.get('last')),
             esc(rc), ' <span class="tag t-red">失败</span>' if bad else '', esc(r.get('act'))))
    A('</tbody></table>')
    A('<p class="cap">返回码 <code>0x80070002</code> = 系统找不到指定的文件（启动失败）；'
      '<code>267009</code> = 任务正在运行（常驻进程）；<code>267011</code> = 尚未运行过。</p>')
else:
    A('<p>未发现。</p>')

A('<details><summary>全部 %d 个非微软计划任务（按上次运行倒序）</summary>'
  '<table><thead><tr><th style="width:190px">任务</th><th style="width:80px">状态</th>'
  '<th style="width:165px">上次运行</th><th style="width:110px">返回码</th><th style="width:110px">触发类型</th>'
  '</tr></thead><tbody>' % len(tasks))
for r in sorted([x for x in tasks if x.get('last')], key=lambda x: str(x.get('last')), reverse=True):
    trig = (str(r.get('trig')).replace('MSFT_TaskLogonTrigger', '登录时')
                               .replace('MSFT_TaskBootTrigger', '开机时')
                               .replace('MSFT_TaskTimeTrigger', '定时')
                               .replace('MSFT_TaskDailyTrigger', '每日')
                               .replace('MSFT_TaskRegistrationTrigger', '注册时')
                               .replace('MSFT_TaskIdleTrigger', '空闲时'))
    A('<tr><td class="mono">%s</td><td>%s</td><td class="mono">%s</td><td class="mono">%s</td><td class="mono">%s</td></tr>'
      % (esc(str(r.get('name')).lstrip('\\')), esc(r.get('state')), esc(r.get('last')),
         esc(r.get('rc')), esc(trig)))
A('</tbody></table></details>')

A('<h3>9.3 报告生成时正在运行的腾讯进程</h3>')
if run_ten:
    A('<table><thead><tr><th style="width:170px">进程</th><th style="width:80px">PID</th>'
      '<th style="width:190px">启动时间</th><th>路径</th></tr></thead><tbody>')
    for p in run_ten:
        A('<tr><td class="mono">%s</td><td class="mono">%s</td><td class="mono">%s</td>'
          '<td class="mono" style="word-break:break-all">%s</td></tr>'
          % (esc(p.get('name')), esc(p.get('id')), esc(p.get('start')), esc(p.get('path'))))
    A('</tbody></table>')
else:
    A('<p>无。</p>')
A('</section>')

# ================= 9. signatures (NEW) =================
A('<section><h2>十、相关二进制的数字签名</h2>')
A('<div class="note">"微信多开"这类工具需要注入或挂接微信进程才能工作，因此它本身的来源值得核实。'
  '下面列出报告涉及的所有可执行文件的签名状态与 SHA-256。</div>')
if sigs:
    A('<table><thead><tr><th>文件</th><th style="width:110px">签名状态</th><th style="width:230px">签发者</th>'
      '<th style="width:120px">文件时间</th></tr></thead><tbody>')
    for s in sigs:
        st = str(s.get('status'))
        cls = 't-green' if st == 'Valid' else ('t-red' if st in ('NotSigned', 'HashMismatch') else 't-amber')
        subj = str(s.get('signer') or '')
        m = re.search(r'O=([^,]+)', subj)
        short = m.group(1).strip() if m else (subj[:40] or '-')
        A('<tr><td class="mono" style="word-break:break-all">%s</td>'
          '<td><span class="tag %s">%s</span></td><td class="mono">%s</td><td class="mono">%s</td></tr>'
          % (esc(s.get('path')), cls, esc(st), esc(short), esc(s.get('mtime'))))
    A('</tbody></table>')
    A('<details><summary>展开 SHA-256 与完整签发者</summary><table><tbody>')
    for s in sigs:
        A('<tr><td class="mono" style="word-break:break-all">%s<br><span style="color:#6b7c90">%s</span><br>%s</td></tr>'
          % (esc(s.get('path')), esc(s.get('sha256')), esc(s.get('signer'))))
    A('</tbody></table></details>')
else:
    A('<p>未采集到。</p>')
A('</section>')

# ================= 10. next steps =================
A('<section><h2>十一、建议</h2>')
A('<table><thead><tr><th style="width:230px">目的</th><th>做法</th></tr></thead><tbody>')
A('<tr><td><b>以后能查到"谁启动的"</b></td><td>以管理员身份执行 '
  '<code>auditpol /set /subcategory:"进程创建" /success:enable</code><br>'
  '开启后每条进程启动都记录精确时间、父进程与发起账户 —— 这正是当前最大的缺口。</td></tr>')
A('<tr><td><b>区分"你"和"别人"</b></td><td>本机只有一个 Administrator 账户，痕迹是混的。'
  '给他人单独建 Windows 账户，或离开即 <code>Win+L</code> 锁屏（本机近 10 天锁屏记录很少）。</td></tr>')
A('<tr><td><b>查"我的号是否被别的设备登录"</b></td><td>本报告查不到，数据在腾讯服务器。'
  '微信：我 → 设置 → 账号与安全 → 登录设备管理；QQ：设置 → 账号安全 → 登录设备管理。</td></tr>')
A('<tr><td><b>排除自动启动干扰</b></td><td>处理第九节列出的鲁大师系列计划任务'
  '（尤其 <code>LdsMultiWechatA</code>：登录后 1 分钟自动拉微信多开）。</td></tr>')
A('<tr><td><b>保留证据</b></td><td>当前痕迹可被管理员权限清除（Prefetch / UserAssist / 应用目录均可删）。'
  '需要留证请尽快对 <code>C:\\Windows\\Prefetch</code>、<code>%APPDATA%\\Tencent</code>、'
  '<code>%APPDATA%\\Microsoft\\Windows\\Recent</code>、QQ/微信数据目录做只读副本。</td></tr>')
A('</tbody></table></section>')

# ================= appendix =================
A('<section><h2>附录：原始数据</h2>')
A('<details><summary>Prefetch 格式统计</summary><table><thead><tr><th>magic</th><th>文件数</th></tr></thead><tbody>')
for r in magic:
    A('<tr><td class="mono">%s</td><td>%d</td></tr>' % (esc(r.get('magic')), int(r.get('count') or 0)))
A('</tbody></table></details>')

A('<details><summary>全部 UserAssist 命中项（%d 条）</summary><pre>' % len(ua_ten))
for dt, name in ua_ten:
    A('%s  %s' % (fmt(dt), esc(name)))
A('</pre></details>')

A('<details><summary>Recent 目录全部条目（%d 条，按时间倒序）</summary><table><tbody>' % len(recents))
for r in sorted(recents, key=lambda x: str(x.get('time')), reverse=True)[:200]:
    A('<tr><td class="mono" style="width:170px">%s</td><td class="mono" style="word-break:break-all">%s</td></tr>'
      % (esc(r.get('time')), esc(r.get('name'))))
A('</tbody></table></details>')
A('</section>')

A('<p class="cap" style="text-align:center;margin-top:26px">'
  '本报告由本机脚本生成，数据未离开本机。所有"最后运行时间"均为文件系统 / 注册表时间戳，'
  '不含运行次数。</p>')

A('</div></body></html>')

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(''.join(P))

print('REPORT_WRITTEN')
print('  path        : ' + OUT)
print('  prefetch    : %d entries' % len(pf))
print('  userassist  : %d total, %d with last-run (max count field %d), %d tencent'
      % (ua_total, ua_n, ua_maxcnt, len(ua_ten)))
print('  logons      : %d (remote lt3/8/10 = %d)' % (len(logons), remote_lt))
print('  autoruns    : %d records, %d tencent hits' % (len(autoruns), len(ar_hits)))
print('  signatures  : %d files' % len(sigs))
print('  ntqq opens  : %d records across %d accounts'
      % (len(ntqq_recents), len(set(r['fuin'] for r in ntqq_recents))))
print('  qq accounts : %d' % len(qq_accts))
print('  wx logs     : %d days' % len(wx_logs))
print('  tasks       : %d (suspect %d)' % (len(tasks), len(sus)))
print('  pf_all      : %d total, %d last-ran on %s..%s'
      % (len(pf_all), len(_pf_focus), d1, d2))
print('  browser     : %d visits, %d downloads  %s'
      % (len(bhist), len(bdl), bstat))
print('  timeline    : %d rows in window' % len(timeline))
print('  recycle     : %d in window, %d total' % (len(recycled), len(recycled_all)))
print('  downloads   : %d files' % len(dlfiles))
print('  timeline    : %d events on %s' % (len(tl), day))
print('  bytes       : %d' % os.path.getsize(OUT))
# Cross-source time check: UserAssist and Prefetch for the same exe must agree.
# A timezone mistake in either reader shows up here as a constant hour offset.
pf_by_exe = {}
for dt, name, _cnt, _src in pf:
    pf_by_exe.setdefault(name.split('-')[0].upper(), []).append(dt)
print('  crosscheck  : userassist-last-run vs prefetch-last-run')
for dt, nm in ua_ten:
    base = os.path.basename(nm).upper()
    if base in pf_by_exe:
        p = pf_by_exe[base][0]
        gap = abs((dt - p).total_seconds())
        # A timezone bug lands on a near-exact multiple of an hour; two different
        # installs of the same exe legitimately differ by arbitrary amounts.
        tz_like = gap > 3600 and abs(gap - round(gap / 3600.0) * 3600) < 120
        flag = '  <-- SUSPECT TZ OFFSET' if tz_like else ''
        print('    %-14s ua=%s  pf=%s  gap=%.0fs%s'
              % (base, dt.strftime('%Y-%m-%d %H:%M'), p.strftime('%Y-%m-%d %H:%M'), gap, flag))
