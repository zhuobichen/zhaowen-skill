#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""某段时间内，本机的「隐私接触面」：有没有人主动去打开/翻看/拷走你的东西。

与 analyze.py 的分工
--------------------
analyze.py 回答「他做了什么」（程序运行、登录、远程控制）。
本脚本回答一个不同的问题：「他碰到了我什么」—— 文档、文件夹、浏览器隐私库、
外接存储、截图、运行框。两者证据源几乎不重叠。

设计原则：三态，且不容许把「没查成」混进「没有」
------------------------------------------------
每一项检查只允许给出三种结论之一：

  HIT      找到了接触证据（附时间与对象）
  CLEAR    检查确实跑到了、看到了正确的数据源、里面没有窗口内的记录
  UNKNOWN  检查没能完成（数据源缺失/读取失败/不适用）

报告顶部先给「N 项中 M 项未能完成」。CLEAR 与 UNKNOWN **分开统计**，
因为把 UNKNOWN 算成 CLEAR 正是这类排查最危险的错误 ——
它会把「我没查到」包装成「他没做过」。

另外每项都会打印**它实际看了哪个数据源**，以便人工复核。
"""
import os, io, sys, re, glob, json, shutil, sqlite3, argparse, datetime, subprocess, tempfile
try:
    import winreg
except ImportError:          # 非 Windows：所有依赖它的检查会报 UNKNOWN，不会崩
    winreg = None


def fixed_drives():
    """所有**固定**盘（排除可移动/光驱/网络盘）。

    「只看 C 盘」是这类工具最常见的静默漏检来源：回收站、临时目录、
    下载目录都可能在你另外的盘上。宁可多扫，也不要因为没列全而报一个假的 0。
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

W0 = W1 = None
HOME = os.environ.get('USERPROFILE', '')
L = os.environ.get('LOCALAPPDATA', '')
R = os.environ.get('APPDATA', '')
T = os.environ.get('TEMP', '')
CHROME_OFF = 11644473600

HIT, CLEAR, UNKNOWN = 'HIT', 'CLEAR', 'UNKNOWN'
results = []

# A GBK console raises UnicodeEncodeError on Chinese print -- and it does so
# *after* the report file has been written, which reads as "generation failed"
# when it did not. Never let console encoding abort the run.
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


# ---------------------------------------------------------------- helpers

def inw(t):
    return t is not None and W0 <= t <= W1


def _as_dt(s):
    """PowerShell 的 ToString('s') → datetime（2026-10-01T00:32:34）。"""
    try:
        return datetime.datetime.fromisoformat(str(s).strip())
    except (ValueError, TypeError):
        return None


def mtime(p):
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(p))
    except (OSError, OverflowError, ValueError):
        return None


def chrome_to_dt(v):
    try:
        return datetime.datetime.fromtimestamp(v / 1000000.0 - CHROME_OFF)
    except (OSError, OverflowError, ValueError):
        return None


def dt_to_chrome(d):
    """Must stay the exact inverse of chrome_to_dt (see analyze.py)."""
    return int((d.timestamp() + CHROME_OFF) * 1000000)


def filetime_to_dt(v):
    """Windows FILETIME (UTC, 100ns since 1601) -> naive LOCAL datetime.

    同一个坑在 analyze.py 里踩过一次：FILETIME 是 UTC，而 os.path.getmtime
    返回本地时间。用 datetime(1601,1,1)+timedelta 得到的是裸 UTC，
    和本地时间混在一起会整体差一个时区（UTC+8 上每天 00:00-08:00 全错）。
    统一走 fromtimestamp。
    """
    if not v:
        return None
    try:
        return datetime.datetime.fromtimestamp(v / 10000000.0 - CHROME_OFF)
    except (OSError, OverflowError, ValueError):
        return None


def _check_timebase():
    for p in (datetime.datetime(2026, 1, 1), datetime.datetime.now().replace(microsecond=0)):
        back = chrome_to_dt(dt_to_chrome(p))
        if back != p:
            raise SystemExit('TIMEBASE SELFTEST FAILED: %r -> %r' % (p, back))


def add(key, title, verdict, evidence, items=None, note='', source=''):
    results.append({'key': key, 'title': title, 'verdict': verdict,
                    'evidence': evidence, 'items': items or [], 'note': note,
                    'source': source})


def ps(cmd, timeout=180):
    r = subprocess.run(['powershell', '-NoProfile', '-Command', cmd],
                       capture_output=True, text=True, timeout=timeout,
                       encoding='utf-8', errors='replace')
    return r.stdout or '', r.stderr or ''


REG_HELPER = r"""
Add-Type -Namespace W32P -Name R -MemberDefinition @"
[DllImport("advapi32.dll", SetLastError=true)]
public static extern int RegQueryInfoKey(IntPtr hKey, System.Text.StringBuilder lpClass,
  ref uint lpcchClass, IntPtr lpReserved, out uint lpcSubKeys, out uint lpcbMaxSubKeyLen,
  out uint lpcbMaxClassLen, out uint lpcValues, out uint lpcbMaxValueNameLen,
  out uint lpcbMaxValueLen, out uint lpcbSecurityDescriptor, out long lpftLastWriteTime);
"@
function KT([string]$p){
  try {
    $sub = $p -replace '^HKCU:\\',''
    $rk = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($sub)
    if(-not $rk){ return '' }
    $a=0;$b=0;$c=0;$d=0;$e=0;$f=0;$g=0;$ft=0
    $sb = New-Object System.Text.StringBuilder 256; $cls=0
    [void][W32P.R]::RegQueryInfoKey($rk.Handle.DangerousGetHandle(), $sb, [ref]$cls,
      [IntPtr]::Zero, [ref]$a,[ref]$b,[ref]$c,[ref]$d,[ref]$e,[ref]$f,[ref]$g,[ref]$ft)
    $rk.Close()
    if($ft -le 0){ return '' }
    return ([datetime]::FromFileTime($ft)).ToString('s')
  } catch { return 'ERR' }
}
"""


def reg_key_times(paths):
    """Return {path: 'YYYY-MM-DDTHH:MM:SS' | '' | 'ERR'}. Registry LastWriteTime
    is not exposed by the PowerShell provider, hence the P/Invoke."""
    if not paths:
        return {}
    body = REG_HELPER + "\n"
    for i, p in enumerate(paths):
        body += "KT '%s'\n" % p.replace("'", "''")
    out, err = ps(body)
    vals = [l.strip() for l in out.splitlines() if l.strip()]
    res = {}
    for p, v in zip(paths, vals):
        res[p] = v
    return res


# ---------------------------------------------------------------- checks

def power_context():
    """窗口内机器实际开机多久。

    这不是一条 HIT/CLEAR/UNKNOWN 检查，而是所有检查的前提：如果机器整段是关着的，
    「12 项全部无记录」是必然的，跟「他很规矩」毫无关系。不先摆出来就会误读。
    """
    # Look back far enough to find the boot that was in progress when the window
    # opened. 7 days is NOT enough: a machine that has been up for a fortnight
    # has no 6005/6006 in that range, and the check then reports "unknown"
    # about a machine that is plainly running.
    look = W0 - datetime.timedelta(days=365)
    out, _ = ps(
        "$ErrorActionPreference='SilentlyContinue';"
        "Get-WinEvent -FilterHashtable @{LogName='System';Id=6005,6006;"
        "StartTime=[datetime]'%s';EndTime=[datetime]'%s'} -MaxEvents 3000 | "
        "Sort-Object TimeCreated | ForEach-Object { $_.TimeCreated.ToString('s')+'|'+$_.Id }"
        % (look.strftime('%Y-%m-%d %H:%M:%S'), W1.strftime('%Y-%m-%d %H:%M:%S')))
    evs = []
    for line in out.splitlines():
        p = line.strip().split('|')
        if len(p) == 2:
            try:
                evs.append((datetime.datetime.fromisoformat(p[0]), int(p[1])))
            except ValueError:
                pass
    if not evs:
        return {'ok': False, 'on_seconds': None, 'intervals': [],
                'note': '取不到开关机事件（6005/6006），无法判断窗口内机器是否在运行'}
    # 6005=开机, 6006=关机。窗口开始时若已开机，从窗口起点算。
    state = None
    intervals = []
    start = None
    for t, eid in evs:
        if t < W0:
            state = 'on' if eid == 6005 else 'off'
            continue
        if eid == 6005 and state != 'on':
            state, start = 'on', t
        elif eid == 6006 and state == 'on':
            intervals.append((max(start or W0, W0), t))
            state, start = 'off', None
    if state == 'on':
        # start is None when the machine was already up before the window opened
        # -- max(None, W0) would raise TypeError.
        intervals.append((start or W0, W1))
    total = sum((b - a).total_seconds() for a, b in intervals)
    return {'ok': True, 'on_seconds': total, 'intervals': intervals,
            'window_seconds': (W1 - W0).total_seconds()}


_APPIDS = None


def resolve_appid(appid):
    """跳转列表 AppID（散列）-> 应用名。

    表来自 EricZimmerman/JumpList 的 AppIDs.txt（733 条，`"HASH"|"名称"`）。
    **查不到就返回 None，不要猜** —— 猜错会给出错误的应用名，比"未知"更坏。
    注意该表只覆盖经典应用：实测命中率约三成，未命中不等于可疑
    （VS Code、Game Bar 这类新版应用常不在表内）。
    """
    global _APPIDS
    if _APPIDS is None:
        _APPIDS = {}
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         '..', 'references', 'AppIDs.txt')
        try:
            for line in open(p, encoding='utf-8', errors='ignore'):
                if '|' in line:
                    a, b = line.split('|', 1)
                    _APPIDS[a.strip().strip('"').upper()] = b.strip().strip('"')
        except OSError:
            pass
    return _APPIDS.get(str(appid).upper())


def chk_external_storage():
    """有没有插 U 盘/移动硬盘 —— 拷走东西的第一步。"""
    items = []
    src = []
    log = r'C:\Windows\INF\setupapi.dev.log'
    hits = 0
    if os.path.isfile(log):
        src.append(log)
        try:
            txt = open(log, 'rb').read().decode('utf-8', 'ignore')
            for blk in txt.split('>>>  [Device Install'):
                m = re.search(r'(\d{4}/\d\d/\d\d \d\d:\d\d:\d\d)', blk)
                if not m:
                    continue
                try:
                    t = datetime.datetime.strptime(m.group(1), '%Y/%m/%d %H:%M:%S')
                except ValueError:
                    continue
                if inw(t) and re.search(r'(?i)usbstor|usb\\|wpd|mass storage|removable', blk):
                    hits += 1
                    items.append('%s  %s' % (t.strftime('%m-%d %H:%M:%S'),
                                             blk.strip().splitlines()[0][:110]))
        except Exception as e:
            return dict(verdict=UNKNOWN, evidence='读取 setupapi.dev.log 失败: %s' % e, items=[])
    else:
        return dict(verdict=UNKNOWN, evidence='缺少 C:\\Windows\\INF\\setupapi.dev.log', items=[])

    src.append(r'HKLM\SYSTEM\CurrentControlSet\Enum\USBSTOR')
    out, _ = ps("$ErrorActionPreference='SilentlyContinue';"
                "Get-ChildItem 'HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\USBSTOR' | "
                "ForEach-Object { $_.PSChildName }")
    known = [l.strip() for l in out.splitlines() if l.strip()]
    ev = 'setupapi: 窗口内 USB 安装 %d 条；USBSTOR 已登记设备 %d 个' % (hits, len(known))
    if known:
        items += ['历史登记过的 USB 存储设备: ' + ', '.join(known[:10])]
    return dict(verdict=HIT if hits else CLEAR, evidence=ev, items=items,
                source=' | '.join(src))


def _sid():
    """当前用户的 SID（BAM 的键按 SID 分）。"""
    try:
        out, _ = ps('[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value')
        return out.strip().splitlines()[-1].strip() if out.strip() else None
    except Exception:
        return None


def bam_entries():
    """BAM/DAM：每个程序**最后一次执行**的时刻。

    位置 HKLM\\SYSTEM\\CurrentControlSet\\Services\\bam\\State\\UserSettings\\<SID>，
    值名是程序完整路径，数据前 8 字节是 FILETIME。

    为什么必须有这个源：Prefetch **会被清理**（实测本机在一次会话里少了一半以上），
    而且**实测有些执行根本没写进 Prefetch**（同一台机器上 BAM 有、对应 .pf 里没有，
    已用两个源都记到的程序做对照确认 BAM 读数本身是对的）。
    所以「Prefetch 里没有」不能当「没运行过」，BAM 是这个缺口的补丁。

    返回 [(naive local datetime, 路径)]，读不到返回 None。
    """
    s = _sid()
    if not s:
        return None
    base = (r'SYSTEM\CurrentControlSet\Services\bam\State\UserSettings\\' + s)
    out = []
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
    except Exception:
        return None
    i = 0
    while True:
        try:
            name, data, _typ = winreg.EnumValue(k, i)
            i += 1
        except OSError:
            break
        if not isinstance(data, (bytes, bytearray)) or len(data) < 8:
            continue
        t = filetime_to_dt(int.from_bytes(bytes(data[:8]), 'little'))
        if t:
            out.append((t, name))
    out.sort()
    return out


def prefetch_last_runs(exe):
    """某个可执行文件（不含扩展名，大写）在 Prefetch 里记录的全部运行时刻。

    返回 (最后一次, 全部次数, 是否有 .pf)，读不到时最后一次为 None。
    """
    pf = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'Prefetch')
    hits = glob.glob(os.path.join(pf, exe.upper() + '.EXE-*.pf'))
    if not hits:
        return None, 0, False
    best = None
    total = 0
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import prefetch_parse as pp
    except Exception:
        pp = None
    for p in hits:
        if pp is not None:
            try:
                r = pp.parse(open(p, 'rb').read())
                total += r['run_count']
                for v in r['last_runs']:
                    t = pp.filetime_to_dt(v)
                    if t and (best is None or t > best):
                        best = t
                continue
            except Exception:
                pass
        t = mtime(p)                 # 退路：.pf 的修改时间
        if t and (best is None or t > best):
            best = t
    return best, total, True


def chk_documents():
    """有没有打开过文档 —— 按扩展名的 MRU 子键时间。

    **不能只看 RecentDocs。** 实测：RecentDocs 在窗口内 0 条，但同一窗口里
    `OpenWith.exe`（"你要用什么打开这个文件"对话框）真的被运行过 —— 也就是
    确实有人去打开了一个文件，只是那次动作没写进 RecentDocs。
    所以这里再叠一层**执行证据**（Prefetch + BAM 两个源取并集）。
    只看 MRU 会给出一个假的 CLEAR，而这正是这套工具最要避免的错。
    """
    base = r'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\RecentDocs'
    exts = ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.txt', '.md',
            '.jpg', '.jpeg', '.png', '.mp4', '.zip', '.one', '.html']
    paths = [base] + [base + '\\' + e for e in exts]
    times = reg_key_times(paths)
    if not times or times.get(base) == 'ERR':
        return dict(verdict=UNKNOWN, evidence='RecentDocs 键读取失败', items=[])
    items, hits = [], 0
    for e in exts:
        v = times.get(base + '\\' + e, '')
        if v == 'ERR':
            items.append('%-8s 读取错误' % e)
            continue
        if not v:
            continue
        try:
            t = datetime.datetime.fromisoformat(v)
        except ValueError:
            continue
        if inw(t):
            hits += 1
            items.append('%s  <== 窗口内' % t.strftime('%m-%d %H:%M:%S'))
        else:
            items.append('%s  %s  （窗口外）' % (t.strftime('%m-%d %H:%M'), e))
    # 叠加执行证据：OpenWith.exe = "你要用什么打开这个文件" 对话框，
    # 是"有人试图打开一个文件"的直接痕迹，而且它不一定写进 RecentDocs
    # （实测窗口内 RecentDocs 0 条，OpenWith 却真的跑了）。
    ow_pre, _n, ow_has = prefetch_last_runs('OPENWITH')
    ow_bam = [t for t, p in (bam_entries() or []) if p.lower().endswith('\\openwith.exe')]
    ow = sorted(t for t in ([ow_pre] if ow_pre else []) + ow_bam if t)
    ow = _merge_times(ow)            # 两个源对同一次执行的时间要合成一个
    ow_in = [t for t in ow if inw(t)]
    for t in ow_in:
        items.append('%s  <== 窗口内运行过「打开方式」对话框 '
                     '(OpenWith.exe：有人试图打开一个文件)'
                     % t.strftime('%m-%d %H:%M:%S'))
    src = base + ' | OpenWith.exe 执行时刻 (Prefetch + BAM)'
    if ow:
        _ow_txt = '、'.join('%s%s' % (x.strftime('%m-%d %H:%M'),
                                      '' if inw(x) else '（窗口外）') for x in ow[-6:])
        items.append('OpenWith.exe 其他已知执行时刻（对照）：%s' % (_ow_txt or '无'))
    tot = times.get(base, '')
    # 注意：RecentDocs 的更新次数与 OpenWith 的运行次数**必须分开计数** ——
    # 混在一起会把"文档 MRU 被更新 0 个"报成 2 个，看着像有两条证据。
    return dict(verdict=HIT if (hits or ow_in) else CLEAR,
                evidence='RecentDocs 各类型子键共 %d 个，窗口内被更新 %d 个；总键=%s%s'
                         % (len([x for x in times if x != base and times[x] not in ('', 'ERR')]),
                            hits, tot or '?',
                            '；另：OpenWith.exe 窗口内运行 %d 次' % len(ow_in) if ow_in else ''),
                items=items, source=src)


def chk_file_dialogs():
    """文件对话框（打开/保存）用过的文件。"""
    paths = [r'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\ComDlg32\OpenSavePidlMRU',
             r'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\ComDlg32\LastVisitedPidlMRU']
    times = reg_key_times(paths)
    if not times:
        return dict(verdict=UNKNOWN, evidence='无法读取 ComDlg32', items=[])
    items, hits = [], 0
    for p, v in times.items():
        if v in ('', 'ERR'):
            items.append('%s  %s' % (p.split('\\')[-1], '不可读' if v == 'ERR' else '不存在'))
            continue
        t = datetime.datetime.fromisoformat(v)
        if inw(t):
            hits += 1
            items.append('%s  <== 窗口内  %s' % (t.strftime('%m-%d %H:%M:%S'), p.split('\\')[-1]))
        else:
            items.append('%s  %s  （窗口外）'
                         % (t.strftime('%m-%d %H:%M'), p.split('\\')[-1]))
    return dict(verdict=HIT if hits else CLEAR,
                evidence='OpenSavePidlMRU / LastVisitedPidlMRU 窗口内更新 %d 个' % hits,
                items=items, source=' / '.join(paths))


def chk_office():
    """Office 各应用的最近文档。"""
    paths = []
    for ver in ('16.0', '15.0', '14.0', '12.0'):
        for app in ('Word', 'Excel', 'PowerPoint', 'Outlook'):
            paths.append(r'HKCU:\Software\Microsoft\Office\%s\%s\File MRU' % (ver, app))
    times = reg_key_times(paths)
    items, hits, real = [], 0, 0
    for p, v in times.items():
        if v in ('', 'ERR'):
            continue
        real += 1
        t = datetime.datetime.fromisoformat(v)
        name = p.split('\\')[-3] + ' ' + p.split('\\')[-2]
        if inw(t):
            hits += 1
            items.append('%s  <== 窗口内  %s' % (t.strftime('%m-%d %H:%M:%S'), name))
        else:
            items.append('%s  %s  （窗口外）' % (t.strftime('%Y-%m-%d'), name))
    if real == 0:
        return dict(verdict=UNKNOWN, evidence='本机未发现 Office File MRU 记录（可能未装 Office）', items=[])
    return dict(verdict=HIT if hits else CLEAR,
                evidence='Office File MRU 存在 %d 个，窗口内更新 %d 个' % (real, hits),
                items=items, source='HKCU\\Software\\Microsoft\\Office\\*\\*\\File MRU')


def chk_folder_browsing():
    """资源管理器里翻过哪些文件夹（shellbags）。"""
    roots = [r'HKCU:\Software\Microsoft\Windows\Shell\BagMRU',
             r'HKCU:\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\BagMRU']
    paths = []
    for rt in roots:
        paths.append(rt)
        for i in range(0, 24):
            paths.append(rt + '\\' + str(i))
    times = reg_key_times(paths)
    if not times:
        return dict(verdict=UNKNOWN, evidence='shellbags 读取失败', items=[])
    items, hits, real = [], 0, 0
    for p, v in times.items():
        if v in ('', 'ERR'):
            continue
        real += 1
        t = datetime.datetime.fromisoformat(v)
        if inw(t):
            hits += 1
            items.append('%s  <== 窗口内  %s' % (t.strftime('%m-%d %H:%M:%S'),
                                               p.replace('HKCU:\\Software\\', '')))
    if real == 0:
        return dict(verdict=UNKNOWN, evidence='shellbags 无有效键', items=[])
    return dict(verdict=HIT if hits else CLEAR,
                evidence='shellbag 键 %d 个，窗口内更新 %d 个' % (real, hits),
                items=items, source=' / '.join(roots))


_NAMED_BROWSER_FRAG = (
    ('Edge', 'microsoft\\edge\\user data'),
    ('QQBrowser', 'qqbrowser'),
    ('豆包(Doubao)', 'doubao'),
    ('ima.copilot', 'ima.copilot'),
    ('zero', '\\roaming\\zero\\user data'),
    ('360Chrome', '360chrome'),
    ('360SE', '360se6'),
)


def _browser_label(path):
    low = path.lower()
    for name, frag in _NAMED_BROWSER_FRAG:
        if frag in low:
            return name
    return None


def _chromium_history_dbs():
    """机器上**全部** Chromium 系历史库，含各种内嵌 WebView2。

    为什么必须全量扫：实测本机有 **130 多个** —— Office / OneDrive / Steam / NVIDIA /
    各大游戏启动器 / 装机软件的 WebView2 各有一个自己的 History。
    只查清单里那 4-8 个，报告却写"检查了 4 个历史库"，读起来像"浏览器查过了"，
    实际上漏掉的是绝大多数 —— 这属于「查不到却说得像查过了」。
    """
    out = {}
    for root in (L, R):
        if not root or not os.path.isdir(root):
            continue
        for p in glob.glob(os.path.join(root, '**', 'History'), recursive=True):
            if os.path.isfile(p) and p not in out:
                out[p] = _browser_label(p) or ('(%s)' % p.replace(root, '…'))
    return out


def _visits_in_window(h):
    """某个 Chromium 历史库里窗口内的访问数。读不动抛异常。"""
    tmp = os.path.join(T or tempfile.gettempdir(), '_pc_bh.db')
    try:
        shutil.copy2(h, tmp)
        for ext in ('-wal', '-shm'):      # 少了它们会漏掉尚未落盘的最新记录
            if os.path.isfile(h + ext):
                shutil.copy2(h + ext, tmp + ext)
        con = sqlite3.connect(tmp)
        n = list(con.execute(
            'SELECT COUNT(*) FROM visits WHERE visit_time>=? AND visit_time<=?',
            (dt_to_chrome(W0), dt_to_chrome(W1))))[0][0]
        con.close()
        return n
    finally:
        for ext in ('', '-wal', '-shm'):
            try:
                os.remove(tmp + ext)
            except OSError:
                pass


def chk_browsing():
    """上网痕迹 —— 全量扫所有 Chromium 系历史库。"""
    dbs = _chromium_history_dbs()
    if not dbs:
        return dict(verdict=UNKNOWN, evidence='未发现任何 Chromium 系历史库', items=[])

    hits_named = 0
    hits_embed = 0
    scan_fail = 0
    hot, named = [], []
    for h, label in sorted(dbs.items(), key=lambda kv: kv[1]):
        n = None
        try:
            n = _visits_in_window(h)
        except Exception:
            scan_fail += 1
        if label.startswith('('):
            if n:                          # 只有有命中的内嵌浏览器才值得列出来
                hot.append('%s  窗口内访问 %d 条' % (label, n))
                hits_embed += n
        else:
            named.append('%s  窗口内 %s 条  (库最后写入 %s)'
                         % (label, n if n is not None else '读取失败',
                            (mtime(h) or datetime.datetime.min).strftime('%m-%d %H:%M')))
            if n:
                hits_named += n

    out, _ = ps("(Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\Shell\\Associations\\"
                "UrlAssociations\\https\\UserChoice').ProgId")
    note = '默认浏览器 ProgId = %s' % (out.strip() or '(未设置)')
    note += ('\n注意：edge:// / chrome:// 内部页（历史、密码、书签页）不写入历史库，'
             '所以这里 0 条不能排除"他打开浏览器翻过设置页"。')
    note += ('\n内嵌浏览器（应用自带的 WebView2）也一并扫了 —— 它们平时不在"浏览器"这个印象里，'
             '但确实各自记历史。有命中的会单独列出。')

    note += ('\n判定口径：常见浏览器（Edge/QQ浏览器/豆包/ima/zero/360）有访问才算「上网」；'
             '内嵌 WebView2 的命中单独列出、不并进结论 —— 那些绝大多数是预装软件自己的本地界面'
             '（file:// 或 localhost），把它算成"他上网了"会失真。'
             '但要留意：内嵌浏览器也能打开真实网页，所以有命中时请逐条看上面列出的 URL。')

    if scan_fail and not (hits_named or hits_embed):
        return dict(verdict=UNKNOWN,
                    evidence='扫描 %d 个历史库中有 %d 个读不动，且未发现窗口内访问 —— '
                             '读不动的那几个无法排除' % (len(dbs), scan_fail),
                    items=named + hot, note=note)
    ev = ('全量扫描 %d 个 Chromium 系历史库（含内嵌 WebView2）：'
          '常见浏览器窗口内 %d 条' % (len(dbs), hits_named))
    if hits_embed:
        ev += '；内嵌浏览器 %d 条（多为应用自身界面，逐条列在下面）' % hits_embed
    if scan_fail:
        ev += '；%d 个库读不动' % scan_fail
    return dict(verdict=HIT if hits_named else CLEAR,
                evidence=ev,
                items=named + hot, note=note,
                source='; '.join(named))


def chk_screenshots():
    """截图 / 录屏。"""
    items, hits = [], 0
    src = []
    recent = os.path.join(R, 'Microsoft', 'Windows', 'Recent')
    src.append(recent)
    for p in glob.glob(os.path.join(recent, 'ms-screenclip*')):
        t = mtime(p)
        if t and inw(t):
            hits += 1
            items.append('%s  <== 窗口内  %s' % (t.strftime('%m-%d %H:%M:%S'), os.path.basename(p)))
    for d in (os.path.join(HOME, 'Videos', 'Captures'), os.path.join(HOME, 'Pictures', 'Screenshots')):
        if os.path.isdir(d):
            src.append(d)
            # 递归：截图可能被存进子目录，只扫一层会漏
            for f in glob.glob(os.path.join(d, '**', '*'), recursive=True):
                if not os.path.isfile(f):
                    continue
                t = mtime(f)
                if t and inw(t):
                    hits += 1
                    items.append('%s  <== 窗口内  %s' % (t.strftime('%m-%d %H:%M:%S'), f[-70:]))
    sk = glob.glob(os.path.join(L, 'Packages', 'Microsoft.ScreenSketch*', 'TempState', '*'))
    for f in sk:
        t = mtime(f)
        if t and inw(t):
            hits += 1
            items.append('%s  <== 窗口内  截图工具临时态' % t.strftime('%m-%d %H:%M:%S'))
    return dict(verdict=HIT if hits else CLEAR,
                evidence='截图相关痕迹窗口内 %d 条' % hits,
                items=items, source=' | '.join(src),
                note='Game Bar 截图若未落盘（如只复制到剪贴板）不会在这里出现。')


def chk_browser_secrets():
    """浏览器里的密码库 / 自动填充 / 书签有没有被碰。"""
    names = ['Login Data', 'Web Data', 'Bookmarks', 'Preferences', 'Shortcuts', 'Top Sites']
    items, hits, seen = [], 0, 0
    for base, who in ((os.path.join(L, 'Microsoft', 'Edge', 'User Data', 'Default'), 'Edge'),
                      (os.path.join(L, 'Doubao', 'User Data', 'Default'), '豆包'),
                      (os.path.join(L, 'ima.copilot', 'User Data', 'Default'), 'ima.copilot')):
        for n in names:
            p = os.path.join(base, n)
            if not os.path.isfile(p):
                continue
            seen += 1
            t = mtime(p)
            if t and inw(t):
                hits += 1
                items.append('%s  <== 窗口内被改  %s / %s' % (t.strftime('%m-%d %H:%M:%S'), who, n))
            elif t:
                items.append('%s  %s / %s  （窗口外）'
                             % (t.strftime('%m-%d %H:%M'), who, n))
    if seen == 0:
        return dict(verdict=UNKNOWN, evidence='未发现浏览器敏感库文件', items=[])
    return dict(verdict=HIT if hits else CLEAR,
                evidence='检查 %d 个敏感库文件，窗口内被改动 %d 个' % (seen, hits),
                items=items,
                note='这是间接旁证：浏览器读密码库时不一定会改文件，所以"未改动"弱于"没看过"。')


def chk_run_dialog():
    """Win+R 运行框用过什么。"""
    p = r'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\RunMRU'
    times = reg_key_times([p])
    v = times.get(p, '')
    if v in ('', 'ERR'):
        return dict(verdict=UNKNOWN if v == 'ERR' else CLEAR,
                    evidence='RunMRU %s' % ('读取失败' if v == 'ERR' else '不存在（从未用过运行框）'),
                    items=[])
    t = datetime.datetime.fromisoformat(v)
    out, _ = ps("$ErrorActionPreference='SilentlyContinue';"
                "$k=Get-Item 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\RunMRU';"
                "$k.GetValueNames() | ForEach-Object { $_ + ' = ' + [string]$k.GetValue($_) }")
    items = [l.strip() for l in out.splitlines() if l.strip()]
    return dict(verdict=HIT if inw(t) else CLEAR,
                evidence='RunMRU 最后写入 %s%s' % (t.strftime('%Y-%m-%d %H:%M:%S'),
                                                 '  <== 窗口内' if inw(t) else ''),
                items=items, source=p)


def chk_jumplists():
    """跳转列表：哪个应用在窗口内被用过（会写它自己的最近文件列表）。"""
    ad = os.path.join(R, 'Microsoft', 'Windows', 'Recent', 'AutomaticDestinations')
    cd = os.path.join(R, 'Microsoft', 'Windows', 'Recent', 'CustomDestinations')
    items, hits, total = [], 0, 0
    for d, tag in ((ad, 'auto'), (cd, 'custom')):
        if not os.path.isdir(d):
            continue
        for p in glob.glob(os.path.join(d, '*')):
            total += 1
            t = mtime(p)
            if t and inw(t):
                hits += 1
                appid = os.path.basename(p).split('.')[0]
                name = resolve_appid(appid)
                items.append('%s  <== 窗口内  %s%s (%s)'
                             % (t.strftime('%m-%d %H:%M:%S'),
                                '' if name else 'AppID=%s ' % appid,
                                name or '（表里没有）', tag))
    if total == 0:
        return dict(verdict=UNKNOWN, evidence='未发现跳转列表目录', items=[])
    known = sum(1 for p in glob.glob(os.path.join(ad, '*'))
                if resolve_appid(os.path.basename(p).split('.')[0]))
    return dict(verdict=HIT if hits else CLEAR,
                evidence='跳转列表 %d 个（表内认出 %d 个），窗口内被更新 %d 个'
                         % (total, known, hits),
                items=items, source=ad,
                note='应用名来自 EricZimmerman/JumpList 的 AppIDs.txt，'
                     '未命中不等于可疑 —— 该表只覆盖经典应用，新版应用常不在表内。'
                     '表里没有的只报 AppID 与时间，不猜。')


def chk_recycle():
    """窗口内的删除记录。

    **每个固定盘都有自己的回收站。** 只看 `C:\\$Recycle.Bin` 会在别的盘上
    漏掉删除记录 —— 实测本机 D 盘就有一个。所以要遍历所有固定盘。
    """
    hits, items, total = 0, [], 0
    recyc = []
    for drv in fixed_drives():
        recyc += glob.glob(os.path.join(drv, '$Recycle.Bin', '*'))
    for root in recyc:
        for f in glob.glob(os.path.join(root, '$I*')):
            try:
                d = open(f, 'rb').read(4000)
            except OSError:
                continue
            if len(d) < 28:
                continue
            ver = int.from_bytes(d[0:8], 'little')
            ft = int.from_bytes(d[16:24], 'little')
            try:
                t = datetime.datetime.fromtimestamp(ft / 10000000.0 - CHROME_OFF)
            except (OSError, OverflowError, ValueError):
                continue
            total += 1
            if ver == 2:
                nlen = int.from_bytes(d[24:28], 'little')
                if not (0 < nlen <= 1000):
                    nlen = 260
                body = d[28:28 + nlen * 2]
            else:
                body = d[24:24 + 520]
            name = body.decode('utf-16-le', 'ignore').split('\x00')[0]
            if inw(t):
                hits += 1
                items.append('%s  %s' % (t.strftime('%m-%d %H:%M:%S'), name[:110]))
    return dict(verdict=HIT if hits else CLEAR,
                evidence='回收站共 %d 项（%d 个盘），窗口内删除 %d 项'
                         % (total, len(recyc), hits),
                items=items, source='; '.join(recyc[:8]) or '(无)',
                note='清空回收站会一并抹掉证据 —— 这里 0 条不能反证"没删过"。')


def chk_chat_clients():
    """聊天客户端在窗口内是否运行过（决定聊天记录有没有可能被看到）。"""
    items = []
    hit = False
    checks = []
    pf = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'Prefetch')
    for exe in ('WEIXIN.EXE', 'WECHATAPPEX.EXE', 'QQ.EXE'):
        for p in glob.glob(os.path.join(pf, exe.replace('.EXE', '') + '.EXE-*.pf')) or \
                 glob.glob(os.path.join(pf, exe + '-*.pf')):
            t = mtime(p)
            checks.append((exe, t))
    if not checks:
        return dict(verdict=UNKNOWN, evidence='未找到微信/QQ 的 Prefetch 记录', items=[])
    for exe, t in checks:
        if t and inw(t):
            hit = True
            items.append('%s  <== 窗口内运行  %s' % (t.strftime('%m-%d %H:%M:%S'), exe))
        elif t:
            items.append('%s  最后运行 %s（窗口外）' % (exe, t.strftime('%m-%d %H:%M')))
    wx = glob.glob(os.path.join(R, 'Tencent', 'xwechat', 'log', 'mm_*.xlog'))
    for p in wx:
        t = mtime(p)
        if t and inw(t):
            hit = True
            items.append('%s  <== 窗口内微信日志被写  %s' % (t.strftime('%m-%d %H:%M:%S'), os.path.basename(p)))
    return dict(verdict=HIT if hit else CLEAR,
                evidence='微信/QQ 在窗口内%s运行' % ('有' if hit else '未'),
                items=items,
                note='客户端没开 = 聊天记录不可能被界面看到；但直接读本地数据库文件不会留下这里能查的痕迹。')


def _toast_text(payload):
    """从 toast 的 XML 里抽出"出现在屏幕上的那行字"（发件人 / 标题 / 正文首句）。"""
    if not payload:
        return '(无正文)'
    s = payload.decode('utf-8', 'replace')
    parts = re.findall(r'<text[^>]*>(.*?)</text>', s, re.S)
    txt = ' | '.join(re.sub(r'<[^>]+>', '', p).strip() for p in parts if p.strip())
    txt = re.sub(r'\s+', ' ', txt)
    txt = txt.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    return txt[:160] or '(无正文)'


def chk_notifications():
    """窗口内有没有通知弹出来过。

    这是整套检查里**唯一可能装着"实际显示在屏幕上的文字"**的证据源 ——
    通知里带的是发件人和主题，是内容本身，不是"他点过什么"。

    判据是 **ArrivalTime**（通知到达时刻）。**不要用 ExpiryTime**：
    实测 ExpiryTime = ArrivalTime + 30 天（保留期），拿它当"弹窗时间"会得出完全错的结论。

    方向性（必须看懂）：本项只能证明"窗口内没有通知**到达**"，
    不能单独证明"屏幕上一个字都没出现过"。所以 CLEAR 还要求一个前提 ——
    库里同时有窗口**之前和之后**的记录，否则就是"已被清空"而不是"没发生"。
    """
    db = os.path.join(L, 'Microsoft', 'Windows', 'Notifications', 'wpndatabase.db')
    if not os.path.isfile(db):
        return dict(verdict=UNKNOWN,
                    evidence='未找到 %s' % db, items=[],
                    note='没有通知库 = 这一项没查成，不等于"当时没有通知"。')

    tmp = os.path.join(T or tempfile.gettempdir(), '_pc_wpn.db')
    con = None
    try:
        # 连带 -wal / -shm 一起复制，否则可能漏掉尚未落盘的最新记录
        for ext in ('', '-wal', '-shm'):
            if os.path.isfile(db + ext):
                shutil.copy2(db + ext, tmp + ext)
        con = sqlite3.connect(tmp)
        rows = list(con.execute('SELECT Id, Type, Payload, ArrivalTime FROM Notification'))
    except Exception as e:
        return dict(verdict=UNKNOWN,
                    evidence='通知库读取失败：%s' % type(e).__name__, items=[],
                    note='读不动不等于没有 —— 这是"没查成"。')
    finally:
        if con is not None:
            con.close()
        for ext in ('', '-wal', '-shm'):
            try:
                os.remove(tmp + ext)
            except OSError:
                pass

    arrivals = [(filetime_to_dt(a), p, i) for i, t, p, a in rows]
    arrivals = [(t, p, i) for t, p, i in arrivals if t is not None]
    if not arrivals:
        return dict(verdict=UNKNOWN,
                    evidence='通知库有 %d 条记录但读不出到达时刻' % len(rows), items=[])

    arrivals.sort()
    inside = [x for x in arrivals if inw(x[0])]

    if inside:
        items = ['%s  %s' % (t.strftime('%m-%d %H:%M:%S'), _toast_text(p))
                 for t, p, _ in inside]
        return dict(verdict=HIT,
                    evidence='窗口内有 %d 条通知到达' % len(inside),
                    items=items,
                    note='这些是通知栏里出现过的内容本身（发件人 / 主题），'
                         '不是"他点过什么"。屏幕上是否真的可见，取决于当时显示器状态，文件层面判断不了。')

    before = [t for t, _, _ in arrivals if t < W0]
    after = [t for t, _, _ in arrivals if t > W1]
    if before and after:
        return dict(verdict=CLEAR,
                    evidence='通知库共 %d 条，窗口内到达 0 条 —— '
                             '且库里同时有窗口前后的记录（窗口前最近 %s，窗口后最近 %s），'
                             '说明这个库确实覆盖了该时段、不是被清空过'
                             % (len(rows), before[-1].strftime('%m-%d %H:%M'),
                                after[0].strftime('%m-%d %H:%M')),
                    items=['窗口前两天内的历史通知（全部在窗口外，仅作对照 —— '
                           '它们的存在说明这个库在连续记录、没被清空过）：'] +
                          ['%s  %s  （窗口外）' % (t.strftime('%m-%d %H:%M:%S'), _toast_text(p))
                           for t, p, _ in arrivals[-6:]],
                    note='通知库只保留最近约 30 天，更早的会被系统清掉。'
                         '另外：手动点掉或"清除全部"会删掉记录 —— 本项的 CLEAR 已排除这种情况'
                         '（依据是窗口前后的记录都还在）。')
    return dict(verdict=UNKNOWN,
                evidence='窗口内到达 0 条，但库里没有同时覆盖窗口前后的记录，'
                         '无法区分"没到达"和"已被清空"',
                items=[], note='这一项没查成，不要读成"没有通知"。')


def _merge_times(times, tol=120):
    """把两个源对同一次执行记录的时刻合并成一个。

    Prefetch 与 BAM 记的是同一次运行的两个时间点，相差几秒（实测 4 秒）。
    直接相加会把"一次执行"报成"两次"—— 数字看着更严重，但它是假的。
    """
    out = []
    for t in sorted(x for x in times if x):
        if out and (t - out[-1]).total_seconds() <= tol:
            continue
        out.append(t)
    return out


def _short_path(p):
    """\\Device\\HarddiskVolume3\\Users\\x\\a.exe -> C:?\\Users\\x\\a.exe 之外的干净形式。

    不猜盘符（那是另一台机器上会静默猜错的事），只把设备前缀去掉。
    """
    p = re.sub(r'^\\Device\\HarddiskVolume\d+', '', p or '')
    return p or '(未知路径)'


def chk_bam_missing():
    """窗口内执行过、但 **Prefetch 里没有** 的程序 —— 专补会被漏掉的那部分。

    为什么单列这一项：Prefetch **会被清理**（实测本机在一次会话里少了一半以上），
    而且**实测有执行根本没写进 Prefetch**（同一台机器上 BAM 记到了某次执行，
    对应的 .pf 完全没有 —— BAM 的读数本身是对的，已用两个源都能对上的程序做过对照）。
    这些被漏掉的执行如果落在窗口内，只看 Prefetch 就是看不见的。

    所以这里列的是**两个源的差集**，不重复列"运行过的程序"（那在主报告 2.5 节）。
    差集非空才报 HIT —— 差集为空说明 Prefetch 在窗口内没有漏东西。
    """
    ent = bam_entries()
    if ent is None:
        return dict(verdict=UNKNOWN,
                    evidence='读不到 BAM（HKLM\\SYSTEM\\...\\bam\\State\\UserSettings\\<SID>）',
                    items=[], note='读不到不等于没有 —— 这是"没查成"，不要读成"没有"。')
    inside = [(t, p) for t, p in ent if inw(t)]
    src = r'HKLM\SYSTEM\CurrentControlSet\Services\bam\State\UserSettings'
    if not inside:
        return dict(verdict=CLEAR,
                    evidence='BAM 共 %d 条记录，窗口内执行 0 条' % len(ent),
                    items=[], source=src)

    items, missed = [], []
    for t, path in inside:
        exe = os.path.basename(path)
        if exe.lower().endswith('.exe'):
            exe = exe[:-4]
        last, _cnt, has = prefetch_last_runs(exe)
        gap = (not has) or last is None or not inw(last)
        if gap:
            missed.append((t, path))
        items.append('%s  %s%s' % (
            t.strftime('%m-%d %H:%M:%S'), _short_path(path),
            '   <== Prefetch 里没有这次（%s）'
            % ('无 .pf' if not has else
               '它记的最后一次是 %s' % last.strftime('%m-%d %H:%M')) if gap else ''))

    if not missed:
        return dict(verdict=CLEAR,
                    evidence='窗口内执行 %d 个程序，全部在 Prefetch 里也有记录（无差集）'
                             % len(inside),
                    items=items, source=src)
    return dict(verdict=HIT,
                evidence='窗口内执行 %d 个程序，其中 %d 个 Prefetch 里没有 '
                         '（只看 Prefetch 会整个漏掉）' % (len(inside), len(missed)),
                items=items, source=src,
                note='Prefetch 里没有有两种解释，本项无法区分：(a) 那次执行没写 .pf，'
                     '(b) .pf 事后被清理掉了。两者都意味着：不能拿「Prefetch 没有」当「没运行过」。'
                     '主报告的程序清单若以 Prefetch 为准，需要拿这里的差集补一下。')


_LOL_LOG_RE = re.compile(
    r'CurrentSummoner:\s*\{"accountId":(\d+),.*?"gameName":"([^"]*)".*?'
    r'"summonerLevel":(\d+).*?"tagLine":"([^"]*)"')


def _lol_log_dirs():
    """英雄联盟客户端日志目录 —— 按固定盘扫名字找，不写死盘符。"""
    out = []
    try:
        import ctypes
        drives = []
        buf = ctypes.create_unicode_buffer(512)
        n = ctypes.windll.kernel32.GetLogicalDriveStringsW(512, buf)
        for d in buf[:n].split('\x00'):
            if d and ctypes.windll.kernel32.GetDriveTypeW(d) == 3:
                drives.append(d)
    except Exception:
        drives = []
    for dr in drives:
        try:
            entries = os.listdir(dr)
        except OSError:
            continue
        for e in entries:
            if not re.search(r'英雄联盟|League of Legends|Riot Games', e, re.I):
                continue
            for sub in glob.glob(os.path.join(dr, e, '**', 'LeagueClient Logs'),
                                 recursive=True):
                if os.path.isdir(sub):
                    out.append(sub)
    return out


def chk_logged_accounts():
    """窗口内这台机器上登录过哪些账号。

    最直接的证据是**客户端自己记的"当前登录身份"**：
    英雄联盟客户端的 `LeagueClient.log` 里有 `CurrentSummoner: {...}`，
    那是客户端认定的本人身份，**不会和同局的其他玩家混淆**（这点很重要 ——
    日志里绝大多数名字是别人的，只有这一行写的是"我是谁"）。

    还能顺手拿到一条硬证据：如果这台机器常用的账号和窗口内登录的不是同一个，
    客户端会打印 `local file belongs to another player, resetting file A B`
    —— 它自己就说明了"A 的配置被 B 顶掉了"。
    """
    dirs = _lol_log_dirs()
    if not dirs:
        return dict(verdict=UNKNOWN,
                    evidence='没找到英雄联盟客户端日志目录（本机可能没装）', items=[],
                    note='没装 = 不适用；但如果确实装了却找不到，那是"没查成"，不是"没有"。')
    sessions = []
    for d in dirs:
        for f in glob.glob(os.path.join(d, '*LeagueClient.log')):
            b = os.path.basename(f)
            m = re.match(r'(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})', b)
            if not m:
                continue
            try:
                started = datetime.datetime.strptime(
                    '%s %s:%s:%s' % m.groups(), '%Y-%m-%d %H:%M:%S')
            except ValueError:
                continue
            try:
                txt = open(f, 'rb').read().decode('utf-8', 'ignore')
            except OSError:
                continue
            cm = _LOL_LOG_RE.search(txt)
            if not cm:
                continue
            swap = re.findall(r'belongs to another player, resetting file (\d+) (\d+)', txt)
            sessions.append(dict(t=started, file=b, acct=cm.group(1),
                                 name=cm.group(2), lvl=cm.group(3),
                                 tag=cm.group(4), swap=swap))
    if not sessions:
        return dict(verdict=UNKNOWN,
                    evidence='找到了客户端日志目录，但没有解析出"当前登录身份"', items=[])

    sessions.sort(key=lambda s: s['t'])
    inside = [s for s in sessions if inw(s['t'])]
    items = []
    for s in sessions:
        mark = '  <== 窗口内' if inw(s['t']) else '  （窗口外，仅作对照）'
        items.append('%s  %s#%s（等级 %s）%s'
                     % (s['t'].strftime('%m-%d %H:%M'), s['name'], s['tag'], s['lvl'], mark))
    if not inside:
        return dict(verdict=CLEAR,
                    evidence='窗口内没有客户端登录会话；本机共 %d 次登录记录' % len(sessions),
                    items=items)
    names = {s['name'] for s in inside}
    note = ('日志里绝大多数名字是同一局的其他玩家，这里只取 CurrentSummoner 一行 —— '
            '那是客户端自己认定的登录身份。')
    swaps = [x for s in inside for x in s['swap']]
    if swaps:
        note += (' 另外客户端自己打印了 "local file belongs to another player, '
                 'resetting file <A> <B>"：说明这台机器上原本属于账号 A 的本地配置'
                 '被账号 B 顶掉了 —— 这是"A 不是这次的登录者"的硬证据。')
    return dict(verdict=HIT,
                evidence='窗口内有 %d 次客户端登录，登录身份是 %s'
                         % (len(inside), '、'.join(sorted(names))),
                items=items, note=note)


def chk_camera_mic():
    """摄像头 / 麦克风有没有被用过。

    这是「他有没有开你的摄像头、录你的声音」**唯一**的证据源 ——
    Windows 把每个应用的最近一次启停时刻记在
    `...\\CapabilityAccessManager\\ConsentStore\\<webcam|microphone>\\<应用>` 的
    LastUsedTimeStart / LastUsedTimeStop 里。

    **判定要按"区间重叠"**，不是"起点落在窗口内"：摄像头常常是窗口开始前就开着、
    一直开到窗口内。只看起点会把这种情况整个漏掉。
    """
    if winreg is None:
        return dict(verdict=UNKNOWN, evidence='非 Windows 或无 winreg 模块', items=[])
    items = []
    hits = 0
    checked = 0
    sub = (r'Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager'
           r'\ConsentStore\\')
    for kind, label in (('webcam', '摄像头'), ('microphone', '麦克风')):
        rows = []
        for hive, hn in ((winreg.HKEY_CURRENT_USER, 'HKCU'),
                         (winreg.HKEY_LOCAL_MACHINE, 'HKLM')):
            path = sub + kind
            try:
                k = winreg.OpenKey(hive, path)
            except OSError:
                continue
            checked += 1
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(k, i)
                    i += 1
                except OSError:
                    break
                try:
                    sk = winreg.OpenKey(k, name)
                    s = winreg.QueryValueEx(sk, 'LastUsedTimeStart')[0]
                    e = winreg.QueryValueEx(sk, 'LastUsedTimeStop')[0]
                except OSError:
                    continue
                rows.append((filetime_to_dt(s), filetime_to_dt(e), hn, name))
        rows.sort(key=lambda r: r[0] or datetime.datetime.min, reverse=True)
        for s, e, hn, name in rows[:8]:
            # 区间重叠：开始 <= 窗口结束 且 （结束为空 或 结束 >= 窗口开始）
            overlaps = bool(s) and s <= W1 and (e is None or e >= W0)
            if overlaps:
                hits += 1
                items.append('%s  %s 在窗口内使用过（%s → %s）'
                             % (label, name[:44],
                                s.strftime('%m-%d %H:%M:%S'),
                                e.strftime('%m-%d %H:%M:%S') if e else '未记录结束'))
            else:
                items.append('%s  %s  最近一次 %s → %s（窗口外）'
                             % (label, name[:44],
                                s.strftime('%m-%d %H:%M') if s else '?',
                                e.strftime('%m-%d %H:%M') if e else '?'))
    if not checked:
        return dict(verdict=UNKNOWN,
                    evidence='读不到 ConsentStore（该账户/系统版本无此键）', items=[],
                    note='读不到不等于没被用过 —— 这是"没查成"。')
    return dict(verdict=HIT if hits else CLEAR,
                evidence='窗口内使用过 %d 次（摄像头/麦克风合计）' % hits
                         if hits else '窗口内摄像头与麦克风都没有使用记录',
                items=items,
                source=sub + 'webcam|microphone 的 LastUsedTimeStart/Stop',
                note='判定按时间区间重叠，不是"起点落在窗口内"——'
                     '设备可能在窗口开始前就开着、一直持续到窗口内。')


def chk_downloads():
    """窗口内有没有下载过文件 —— 扫所有 Chromium 系的 downloads 表。

    这和"下载文件夹里多了什么"是两件事：文件夹只能看到**结果**，
    浏览器的 downloads 表还记着**来源 URL**（谁给的、从哪个站下的）。
    """
    dbs = _chromium_history_dbs()
    if not dbs:
        return dict(verdict=UNKNOWN, evidence='未发现任何 Chromium 系历史库', items=[])
    hits, rows, failed = 0, [], 0
    for h, label in sorted(dbs.items(), key=lambda kv: kv[1]):
        tmp = os.path.join(T or tempfile.gettempdir(), '_pc_dl.db')
        try:
            shutil.copy2(h, tmp)
            for ext in ('-wal', '-shm'):
                if os.path.isfile(h + ext):
                    shutil.copy2(h + ext, tmp + ext)
            con = sqlite3.connect(tmp)
            got = list(con.execute(
                'SELECT start_time, target_path, tab_url FROM downloads '
                'WHERE start_time>=? AND start_time<=?',
                (dt_to_chrome(W0), dt_to_chrome(W1))))
            con.close()
            for ts, tp, url in got:
                hits += 1
                rows.append('%-44s  %s\n        来自 %s'
                            % (label, str(tp)[:110], str(url)[:110]))
        except Exception:
            failed += 1
        finally:
            for ext in ('', '-wal', '-shm'):
                try:
                    os.remove(tmp + ext)
                except OSError:
                    pass
    if failed and not hits:
        return dict(verdict=UNKNOWN,
                    evidence='扫描 %d 个库中有 %d 个读不到 downloads 表，且窗口内无下载'
                             % (len(dbs), failed), items=[],
                    note='读不动的那些无法排除 —— 这是"没查成"，不是"没下载"。')
    return dict(verdict=HIT if hits else CLEAR,
                evidence='扫描 %d 个库，窗口内下载 %d 个文件' % (len(dbs), hits),
                items=rows,
                source='; '.join(sorted(dbs.values())) + ' 的 downloads 表',
                note='浏览器下载只是一条路：直接用 U 盘 / 资源管理器复制不写这里，'
                     '要配合「外部存储」那一项一起看。')


def chk_console_history():
    """窗口内有没有人敲过命令行。

    `ConsoleHost_history.txt` 只有"整个文件最后一次被写"的时间，**没有逐条时间戳**。
    所以能得出的只有一条：**文件 mtime 落在窗口内 = 那段时间有人在这个会话里敲过命令**。
    反过来说不成立 —— 窗口内没敲过，文件 mtime 也可能因为别的原因更新。
    """
    paths = [os.path.join(R, 'Microsoft', 'Windows', 'PowerShell', 'PSReadLine',
                          'ConsoleHost_history.txt')]
    items, hits, found = [], 0, 0
    for p in paths:
        if not os.path.isfile(p):
            continue
        found += 1
        t = mtime(p)
        if t and inw(t):
            hits += 1
            items.append('%s  <== 窗口内被写  %s' % (t.strftime('%m-%d %H:%M:%S'), p))
        else:
            items.append('%s  最后写入 %s（窗口外）' % (p, t.strftime('%m-%d %H:%M') if t else '?'))
    if not found:
        return dict(verdict=UNKNOWN,
                    evidence='没有 PowerShell 历史文件（该会话从未用过 PS，或已被删）',
                    items=[], source=' | '.join(paths),
                    note='文件不存在本身也可能意味着"被删过"—— 但没法区分，所以记 UNKNOWN。')
    return dict(verdict=HIT if hits else CLEAR,
                evidence='窗口内命令行历史文件%s被写' % ('有' if hits else '未'),
                items=items, source=' | '.join(paths),
                note='这个文件没有逐条时间戳，只能靠文件 mtime 判断"那段时间敲过没有"，'
                     '不能还原敲了什么、也不能按条定时刻。')


def chk_tampering():
    """痕迹有没有被人动过 —— 决定"查不到"到底是"没发生"还是"被清掉了"。

    这一项不是找"他做了什么"，而是给**其它所有项的结论定强度**：
    如果日志被清、审计被关、Prefetch 被停、系统时间被改，
    那么别处的"没有记录"就不能读成"没发生过"。
    """
    items = []
    bad, unknown = 0, 0

    def ev(log, eid, label):
        nonlocal bad, unknown
        cmd = ("$ErrorActionPreference='SilentlyContinue';"
               "Get-WinEvent -FilterHashtable @{LogName='%s';Id=%d} -MaxEvents 3 "
               "| ForEach-Object { $_.TimeCreated.ToString('s') }" % (log, eid))
        out, err = ps(cmd)
        times = [x.strip() for x in out.splitlines() if x.strip()]
        if not times and err:
            unknown += 1
            items.append('%s：查询失败（%s）' % (label, err.strip().splitlines()[0][:70]))
            return
        inw_t = [t for t in times if _as_dt(t) and inw(_as_dt(t))]
        if inw_t:
            bad += 1
            items.append('%s  <== 窗口内发生：%s' % (label, '、'.join(inw_t)))
        elif times:
            items.append('%s：最近一次 %s（窗口外）' % (label, times[0]))
        else:
            items.append('%s：无此事件' % label)

    ev('Security', 1102, '安全日志被清空')
    ev('System', 104, '系统日志被清空')
    ev('System', 1, '系统时间被修改(Kernel-General)')

    # Prefetch / SysMain 是否被关 —— 关了就再也不写 .pf，会让别处"没记录"
    if winreg is not None:
        try:
            k = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r'SYSTEM\CurrentControlSet\Control\Session Manager'
                r'\Memory Management\PrefetchParameters')
            v = winreg.QueryValueEx(k, 'EnablePrefetcher')[0]
            if int(v) == 0:
                bad += 1
                items.append('Prefetch 已被关闭（EnablePrefetcher=0）'
                             '  <== 之后的程序运行不会再留下 .pf')
            else:
                items.append('Prefetch 处于开启状态（EnablePrefetcher=%s）' % v)
        except OSError:
            unknown += 1
            items.append('读不到 EnablePrefetcher')

    # BAM 是否为空 —— 正常机器不会空
    ent = bam_entries()
    if ent is None:
        unknown += 1
        items.append('读不到 BAM')
    elif len(ent) == 0:
        bad += 1
        items.append('BAM 是空的  <== 正常机器不会空，可能被清过')
    else:
        items.append('BAM 有 %d 条记录（正常）' % len(ent))

    src = 'Security/System 事件日志 1102/104/1 | ' \
          r'HKLM\SYSTEM\...\PrefetchParameters | BAM'
    if bad:
        return dict(verdict=HIT,
                    evidence='发现 %d 条"痕迹被抹"的迹象' % bad, items=items, source=src,
                    note='这一项命中不会告诉你"他做了什么"，但它会让别处的'
                         '"没有记录"失去说服力 —— 报告里别处那些 CLEAR 要打折看。')
    if unknown:
        return dict(verdict=UNKNOWN,
                    evidence='有 %d 项没能查成，其余正常' % unknown, items=items, source=src,
                    note='没查成的那几项无法排除 —— 不要当成"没问题"。'
                         '（查安全日志需要管理员权限。）')
    return dict(verdict=CLEAR,
                evidence='没有发现痕迹被抹的迹象（日志未被清、Prefetch 开启、BAM 正常）',
                items=items, source=src)


_REMOTE_TOOLS = (
    ('ToDesk', 'todesk', 'ToDesk'),
    ('AnyDesk', 'anydesk', 'AnyDesk'),
    ('TeamViewer', 'teamviewer', 'TeamViewer'),
    ('向日葵 SunloginClient', 'sunlogin', 'SunloginClient'),
    ('向日葵 AweSun', 'awesun', 'AweSun'),
    ('RustDesk', 'rustdesk', 'RustDesk'),
    ('ScreenConnect', 'screenconnect', 'ScreenConnect'),
    ('LogMeIn', 'logmein', 'LogMeIn'),
    ('RealVNC / TightVNC', 'vnc', 'vnc'),
)


def _installed_dirs(hint, extra=()):
    """按卸载注册表显示名找安装目录。InstallLocation 常为空，要退到另两个值。"""
    out = []
    if winreg is not None:
        for hive, path in (
                (winreg.HKEY_LOCAL_MACHINE,
                 r'Software\Microsoft\Windows\CurrentVersion\Uninstall'),
                (winreg.HKEY_LOCAL_MACHINE,
                 r'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'),
                (winreg.HKEY_CURRENT_USER,
                 r'Software\Microsoft\Windows\CurrentVersion\Uninstall')):
            try:
                k = winreg.OpenKey(hive, path)
            except OSError:
                continue
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                    i += 1
                except OSError:
                    break
                try:
                    sk = winreg.OpenKey(k, sub)
                    disp = str(winreg.QueryValueEx(sk, 'DisplayName')[0])
                except OSError:
                    continue
                if hint.lower() not in disp.lower():
                    continue
                for vn in ('InstallLocation', 'UninstallString', 'DisplayIcon'):
                    try:
                        raw = str(winreg.QueryValueEx(sk, vn)[0]).strip()
                    except OSError:
                        continue
                    if raw.startswith('"'):
                        raw = raw[1:].split('"', 1)[0]
                    else:
                        raw = raw.split(',')[0].strip()
                    if not raw:
                        continue
                    c = raw if os.path.isdir(raw) else os.path.dirname(raw)
                    if c and os.path.isdir(c):
                        out.append(c)
                        break
    for c in extra:
        if os.path.isdir(c):
            out.append(c)
    return list(dict.fromkeys(out))


def chk_remote_access():
    """有没有人**远程连进来**过。

    这一项问的和别的项不是同一件事：对方可以根本不坐在你电脑前，而是通过 RDP
    或远控软件连进来操作 —— 那样"没人开机登录""没人翻你文件"可以同时成立，
    但屏幕照样被看到了。**只查本机活动会整条漏掉。**

    两种方向必须分开，两行日志长得几乎一样：
      `host   recv connect request, myid=…` = 本机是**被控端**（有人连进来）
      `client recv connect request, myid=…` = 本机**主动连出去**
    搞反了，结论就完全相反。
    """
    items = []
    hits = 0
    failed = []

    # 1) RDP 是否被允许 + 窗口内有没有 RDP 登录（4624 类型 10 = RemoteInteractive）
    if winreg is not None:
        try:
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                               r'SYSTEM\CurrentControlSet\Control\Terminal Server')
            deny = int(winreg.QueryValueEx(k, 'fDenyTSConnections')[0])
            items.append('远程桌面（RDP）：%s（fDenyTSConnections=%d）'
                         % ('已禁用' if deny else '允许连入', deny))
        except (OSError, ValueError):
            failed.append('fDenyTSConnections')
    else:
        failed.append('winreg')

    cmd = ("$ErrorActionPreference='SilentlyContinue';"
           "Get-WinEvent -FilterHashtable @{LogName='Security';Id=4624;"
           "StartTime='%s';EndTime='%s'} | ForEach-Object {"
           " $x=[xml]$_.ToXml(); $d=@{};"
           " foreach($n in $x.Event.EventData.Data){$d[[string]$n.Name]=[string]$n.'#text'};"
           " \"$($_.TimeCreated.ToString('s'))`t$($d['LogonType'])`t"
           "$($d['TargetUserName'])`t$($d['IpAddress'])\" }"
           % (W0.strftime('%Y-%m-%dT%H:%M:%S'), W1.strftime('%Y-%m-%dT%H:%M:%S')))
    out, err = ps(cmd)
    rdp_rows = []
    for line in out.splitlines():
        parts = line.strip().split('\t')
        if len(parts) >= 4:
            rdp_rows.append(parts)
    if not out.strip() and err:
        failed.append('4624 查询')
        items.append('窗口内 4624 登录事件：查询失败（需要管理员权限）')
    else:
        rdp_in = [r for r in rdp_rows if r[1] == '10']
        net_in = [r for r in rdp_rows if r[1] in ('3', '8')]
        items.append('窗口内登录事件：RDP 类型10 %d 条、网络类型3/8 %d 条、合计 %d 条'
                     % (len(rdp_in), len(net_in), len(rdp_rows)))
        for r in rdp_in[:6]:
            hits += 1
            items.append('%s  <== 窗口内 RDP 登录：%s 来自 %s'
                         % (r[0], r[2], r[3] or '(本机)'))
        for r in net_in[:6]:
            items.append('%s  网络登录：%s 来自 %s' % (r[0], r[2], r[3] or '(本机)'))

    # 2) 远控软件的会话日志（方向是关键）
    pf = os.environ.get('ProgramFiles', r'C:\Program Files')
    pf86 = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
    tdirs = _installed_dirs('todesk', (os.path.join(pf, 'ToDesk'),
                                       os.path.join(pf86, 'ToDesk')))
    logdir = None
    for d in tdirs:
        if os.path.isdir(os.path.join(d, 'Logs')):
            logdir = os.path.join(d, 'Logs')
            break
    if logdir:
        host_in, client_in, span = [], [], []
        for p in glob.glob(os.path.join(logdir, '*.log')):
            try:
                for line in open(p, encoding='utf-8', errors='ignore'):
                    s = line.strip()
                    m = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', s)
                    if not m:
                        continue
                    t = _as_dt(m.group(1))
                    span.append(t)
                    if 'host recv connect request, myid=' in s:
                        if t and inw(t):
                            host_in.append(t)
                    elif 'client recv connect request, myid=' in s:
                        if t and inw(t):
                            client_in.append(t)
            except OSError:
                continue
        if span:
            items.append('ToDesk 日志可回溯到 %s（窗口前最近的记录对比用）'
                         % min(x for x in span if x).strftime('%m-%d %H:%M'))
        if host_in:
            for t in host_in[:8]:
                hits += 1
                items.append('%s  <== 有人连进本机（host recv connect request）'
                             % t.strftime('%m-%d %H:%M:%S'))
        else:
            items.append('窗口内没有被控端连接请求（host recv connect request）')
        if client_in:
            items.append('窗口内有 %d 次本机主动连出去（client，方向相反，不算命中）'
                         % len(client_in))
    else:
        items.append('未发现 ToDesk 日志目录')

    # 3) 其它远控软件装没装 —— 只查 ToDesk 会给出假的安全结论
    installed = []
    for label, hint, dirname in _REMOTE_TOOLS:
        if label.startswith('ToDesk'):
            continue
        extra = ()
        if dirname:
            extra = (os.path.join(pf, dirname), os.path.join(pf86, dirname))
        if _installed_dirs(hint, extra):
            installed.append(label)
    items.append('其它已知远控软件：%s'
                 % ('、'.join(installed) + '  <== 装了，需单独看它的日志'
                    if installed else '本机都没有安装'))

    # 4) mstsc 出站历史（反方向，仅背景）
    mstsc = []
    if winreg is not None:
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r'Software\Microsoft\Terminal Server Client\Default')
            i = 0
            while True:
                try:
                    n, v, _ = winreg.EnumValue(k, i)
                    i += 1
                except OSError:
                    break
                if str(n).startswith('MRU'):
                    mstsc.append('%s = %s' % (n, v))
        except OSError:
            pass
    if mstsc:
        items.append('本机作为客户端连出去的 RDP 目标（无时间戳，仅背景）：%s'
                     % '、'.join(mstsc[:4]))

    src = ('HKLM\\SYSTEM\\...\\Terminal Server\\fDenyTSConnections | '
           'Security 4624（类型10/3/8） | ToDesk Logs | 各远控软件安装目录')
    note = ('两种方向必须分看：`host recv connect request` = 有人连进来，'
            '`client recv ...` = 本机连出去。这一项只看前者。')
    if hits:
        return dict(verdict=HIT,
                    evidence='窗口内发现 %d 条远程连入的证据' % hits,
                    items=items, source=src, note=note)
    if failed:
        return dict(verdict=UNKNOWN,
                    evidence='没能查成：%s —— 其余部分未发现远程连入'
                             % '、'.join(failed),
                    items=items, source=src,
                    note=note + ' 查不到不等于没有，别读成"没被连过"。')
    return dict(verdict=CLEAR,
                evidence='窗口内没有远程连入的证据（RDP 关闭 / 无类型10登录 / '
                         '无被控端连接请求 / 其它远控软件均未安装）',
                items=items, source=src, note=note)


def chk_file_search():
    """按文件名全盘搜索的痕迹（Everything）。

    为什么单列一项：Everything 这类工具**输入即列出全盘文件名**，
    是"不打开任何文件就能通览你硬盘里有什么"的最有效手段，而它**几乎不留痕**。
    两个开关决定了能查到什么，必须分别看：

      search_history_enabled  —— 搜过什么关键字。**关掉就完全没有记录。**
      run_history_enabled     —— 从结果里**打开**过什么文件（`Run History.csv`）。

    只报"没打开过文件"就把这一项写成 CLEAR 是错的：**搜到文件名本身**就是泄露，
    而那条路在被关掉时无迹可查。
    """
    base = os.path.join(R, 'Everything')
    if not os.path.isdir(base):
        return dict(verdict=UNKNOWN,
                    evidence='本机没有 Everything 的配置目录（可能没装/没用过）',
                    items=[], source=base,
                    note='没装 = 不适用。但装了却读不到配置才是"没查成"。')

    ini = os.path.join(base, 'Everything.ini')
    cfg = {}
    if os.path.isfile(ini):
        for line in open(ini, encoding='utf-8', errors='ignore'):
            if '=' in line:
                k, v = line.split('=', 1)
                cfg[k.strip()] = v.strip()

    items = []
    if cfg:
        items.append('搜索历史记录开关 search_history_enabled=%s'
                     % cfg.get('search_history_enabled', '?'))
        items.append('打开历史记录开关 run_history_enabled=%s'
                     % cfg.get('run_history_enabled', '?'))

    # 从结果里打开过哪些文件（有逐条时间戳）
    hist = os.path.join(base, 'Run History.csv')
    opened_in = []
    total = 0
    if os.path.isfile(hist):
        for line in open(hist, encoding='utf-8-sig', errors='ignore'):
            line = line.strip()
            if not line or line.startswith('Filename'):
                continue
            try:
                path, _cnt, ft = line.rsplit(',', 2)
                t = filetime_to_dt(int(ft))
            except (ValueError, IndexError):
                continue
            if t is None:
                continue
            total += 1
            if inw(t):
                opened_in.append((t, path.strip().strip('"')))
        opened_in.sort()
        for t, pa in opened_in[:10]:
            items.append('%s  <== 窗口内从搜索结果打开  %s'
                         % (t.strftime('%m-%d %H:%M:%S'), pa[:110]))
        items.append('该记录共 %d 条（永久保留）；窗口内 %d 条' % (total, len(opened_in)))
    else:
        items.append('没有 Run History.csv（从未从搜索结果打开过文件，或该功能被关）')

    src = base + r'\Everything.ini 与 Run History.csv'
    if opened_in:
        return dict(verdict=HIT,
                    evidence='窗口内从搜索结果打开了 %d 个文件' % len(opened_in),
                    items=items, source=src)
    if cfg.get('search_history_enabled', '') == '0':
        return dict(verdict=UNKNOWN,
                    evidence='没有"从搜索结果打开文件"的记录，但搜索历史被关掉了 —— '
                             '"有没有人敲关键字搜过你的文件名"无迹可查',
                    items=items, source=src,
                    note='这一项只排除了"打开文件"，没有排除"搜到并看到文件名"。'
                         'Everything 输入即列全盘文件名，看一眼不留痕；'
                         '而 search_history_enabled=0 意味着那一步根本没记录。'
                         '不要把它读成"他没有按文件名翻过我的东西"。')
    return dict(verdict=CLEAR,
                evidence='没有从搜索结果打开文件的记录（搜索历史是开着的）',
                items=items, source=src)


def chk_printing():
    """有没有人打印过东西 —— 打印是"把内容带走"且**几乎不留文件**的一条路。

    **这里有个必须避开的坑**：`Microsoft-Windows-PrintService/Operational`
    在多数机器上**默认是关闭的**。日志关着时查询返回 0 条 —— 把它当成
    "没打印过"就是**用一个查不到的结果当成了否定证据**。所以必须先问日志
    是否启用：没启用就直接记 UNKNOWN。
    """
    items, hits = [], 0
    failed = []

    # 1) 日志是否启用 —— 决定"0 条"能不能算数
    out, _ = ps("(Get-WinEvent -ListLog 'Microsoft-Windows-PrintService/Operational' "
                "-ErrorAction SilentlyContinue).IsEnabled")
    enabled = out.strip().lower() in ('true', '1')
    items.append('打印服务事件日志已启用：%s' % ('是' if enabled else '否'))

    if enabled:
        cmd = ("$ErrorActionPreference='SilentlyContinue';"
               "Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-PrintService/Operational';"
               "StartTime='%s';EndTime='%s'} -MaxEvents 50 | ForEach-Object {"
               " $_.TimeCreated.ToString('s') + \"`t\" + $_.Id + \"`t\" + "
               "($_.Message -replace '\\s+',' ') }"
               % (W0.strftime('%Y-%m-%dT%H:%M:%S'), W1.strftime('%Y-%m-%dT%H:%M:%S')))
        out, err = ps(cmd)
        for line in out.splitlines():
            line = line.strip()
            if line:
                hits += 1
                items.append('%s  <== 窗口内打印事件  %s' % (line[:10], line[11:190]))
        if not out.strip():
            items.append('窗口内打印事件：0 条')
    else:
        failed.append('打印事件日志未启用')

    # 2) 打印队列里有没有留下的作业
    spool = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'),
                         'System32', 'spool', 'PRINTERS')
    if os.path.isdir(spool):
        left = [f for f in os.listdir(spool) if os.path.isfile(os.path.join(spool, f))]
        items.append('打印队列残留作业：%d 个' % len(left))

    # 3) 装了哪些"虚拟打印机" —— 决定了能不能"打印成 PDF 带走"
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r'Software\Microsoft\Windows NT\CurrentVersion\Windows')
        dev = str(winreg.QueryValueEx(k, 'Device')[0]).split(',')[0]
        items.append('默认打印机：%s' % dev)
    except (OSError, IndexError):
        items.append('读不到默认打印机')

    src = ('Microsoft-Windows-PrintService/Operational 事件日志 | '
           r'%SystemRoot%\System32\spool\PRINTERS | 默认打印机注册表')
    if hits:
        return dict(verdict=HIT, evidence='窗口内有 %d 条打印事件' % hits,
                    items=items, source=src)
    if failed:
        return dict(verdict=UNKNOWN,
                    evidence='打印事件日志%s —— 无法排除"打印过"' % failed[0],
                    items=items, source=src,
                    note='这一项没查成。打印日志默认关闭，要查得先手动打开。'
                         '别把这里读成"没打印过"。')
    return dict(verdict=CLEAR, evidence='窗口内没有打印事件，打印队列也没有残留',
                items=items, source=src,
                note='打印成 PDF 会落一个文件（在你自己选的目录），'
                     '那条路要配合「文档」「下载」一起看。')


def chk_cloud_sync():
    """有没有把文件同步 / 上传到云端 —— "把东西带走"的主要途径之一。

    **必须把"客户端自己的状态文件"和"同步的内容"分开算。**
    实测 OneDrive 每次登录都会写一串 `logs/…`、`settings/…`、`setup/logs/…`
    —— 把它们算成命中，就等于每台装了 OneDrive 的机器都"发现把文件传上云了"，
    真正的信号会被淹掉。所以：

      内容目录（`%USERPROFILE%\\OneDrive` 等）有动静  → HIT，这才是"文件被同步"
      只有客户端状态/日志被写                        → 只作背景列出，不算命中
    """
    # (显示名, 内容目录, 客户端状态目录)
    roots = (
        ('OneDrive',
         [os.path.join(HOME, 'OneDrive')] +
         glob.glob(os.path.join(HOME, 'OneDrive - *')),
         [os.path.join(L, 'Microsoft', 'OneDrive'), os.path.join(R, 'Microsoft', 'OneDrive')]),
        ('百度网盘', [os.path.join(HOME, 'BaiduNetdiskDownload')],
         [os.path.join(R, 'baidu'), os.path.join(L, 'baidu'),
          os.path.join(R, 'BaiduNetdisk'), os.path.join(L, 'BaiduNetdisk')]),
        ('阿里云盘', [], [os.path.join(R, 'aDrive'), os.path.join(L, 'aDrive'),
                          os.path.join(R, 'Alipan'), os.path.join(L, 'Alipan')]),
        ('夸克网盘', [], [os.path.join(R, 'Quark'), os.path.join(L, 'Quark'),
                          os.path.join(R, 'QuarkCloudDrive'), os.path.join(L, 'QuarkCloudDrive')]),
        ('天翼云盘', [], [os.path.join(R, 'CTYun'), os.path.join(L, 'CTYun')]),
        ('迅雷', [], [os.path.join(R, 'Thunder Network'), os.path.join(L, 'Thunder Network')]),
    )
    items, hits, present, ctx = [], 0, [], []

    def in_window_files(bases):
        rows = []
        for b in bases:
            if not os.path.isdir(b):
                continue
            for p in glob.glob(os.path.join(b, '**', '*'), recursive=True):
                if os.path.isfile(p):
                    t = mtime(p)
                    if t and inw(t):
                        rows.append((t, p))
        return sorted(rows)

    for label, content, state in roots:
        if not (any(os.path.isdir(b) for b in content) or
                any(os.path.isdir(b) for b in state)):
            continue
        present.append(label)
        for t, p in in_window_files(content)[:8]:
            hits += 1
            items.append('%s  %s  <== 窗口内内容目录被写  %s'
                         % (label, t.strftime('%m-%d %H:%M:%S'), p[-90:]))
        ctx += [(label, t, p) for t, p in in_window_files(state)[:4]]

    if not present:
        return dict(verdict=UNKNOWN,
                    evidence='本机没有检测到已知的云同步/网盘客户端',
                    items=[], source='OneDrive / 百度网盘 / 阿里云盘 / 夸克 / 天翼 / 迅雷',
                    note='也可能是装了但目录名不在清单里 —— 这是"没查到"，不是"没有"。')

    if ctx:
        items.append('（以下只是客户端自己的状态/日志，每次开机都会写，不算"传文件"）')
        for label, t, p in ctx[:8]:
            items.append('%s  %s  客户端状态  %s'
                         % (label, t.strftime('%m-%d %H:%M:%S'), p[-80:]))

    src = ' / '.join(present) + ' 的内容目录与客户端状态目录'
    if hits:
        return dict(verdict=HIT,
                    evidence='窗口内云同步的内容目录有 %d 个文件被改动' % hits,
                    items=items, source=src,
                    note='命中说明"有文件在同步目录里被动过"，不一定是有人手动上传 —— '
                         '后台同步也会动。要看上面具体是哪些文件。')
    return dict(verdict=CLEAR,
                evidence='窗口内云同步的内容目录没有文件被改动（本机装了：%s）'
                         % '、'.join(present),
                items=items, source=src,
                note='云端上传本身不在本机留记录；这里看的是同步目录的本地改动。'
                     '客户端自己的日志每次开机都会写，已单独列出、不计入结论。')


def _boot_events_in_window():
    """窗口内的开机事件（System 日志 6005=事件日志服务启动）。"""
    cmd = ("$ErrorActionPreference='SilentlyContinue';"
           "Get-WinEvent -FilterHashtable @{LogName='System';Id=6005;"
           "StartTime='%s';EndTime='%s'} | ForEach-Object { $_.TimeCreated.ToString('s') }"
           % (W0.strftime('%Y-%m-%dT%H:%M:%S'), W1.strftime('%Y-%m-%dT%H:%M:%S')))
    out, _ = ps(cmd)
    return [t for t in (_as_dt(s) for s in out.splitlines()) if t]


def chk_thumbcache():
    """有人用**缩略图**浏览过文件吗 —— "看到了图片内容"却不打开任何文件的旁证。

    Explorer 显示缩略图时会写 `%LOCALAPPDATA%\\Microsoft\\Windows\\Explorer\\thumbcache_*.db`。

    **必须把"开机时刷新"排除掉**：登录后 Explorer 会重建一轮缩略图，每次开机都写。
    把它算成命中，就等于每台机器都"发现有人翻过图片"。只有**远离开机时刻**的写入
    才说明"那段时间真的去浏览了以前没看过的图片/文件"。

    **方向**：没被写**不能**说明"没看过" —— 已缓存过的文件再看不会重写。
    所以命中很有意义，没命中只是弱证据。
    """
    base = os.path.join(L, 'Microsoft', 'Windows', 'Explorer')
    boots = _boot_events_in_window()
    items, files = [], 0
    quiet, near_boot = [], []
    for p in sorted(glob.glob(os.path.join(base, 'thumbcache_*.db'))):
        files += 1
        t = mtime(p)
        try:
            sz = os.path.getsize(p)
        except OSError:
            sz = 0
        if not (t and inw(t)):
            items.append('%s  最后写入 %s  (%.0f KB)  （窗口外）'
                         % (os.path.basename(p), t.strftime('%m-%d %H:%M') if t else '?',
                            sz / 1024))
            continue
        close = any(abs((t - b).total_seconds()) <= 180 for b in boots)
        line = '%s  %s  (%.0f KB)' % (os.path.basename(p),
                                      t.strftime('%m-%d %H:%M:%S'), sz / 1024)
        if close:
            near_boot.append(t)
            items.append(line + '  （开机后 3 分钟内，属登录时自动刷新）')
        else:
            quiet.append(t)
            items.append(line + '  <== 远离开机时刻，值得注意')
    if not files:
        return dict(verdict=UNKNOWN, evidence='没有 thumbcache 文件',
                    items=[], source=base)
    if not boots:
        items.append('（读不到窗口内的开机事件，无法把"登录时刷新"排除掉 —— 已按最保守方式计入）')
    return dict(verdict=HIT if (quiet or not boots) else CLEAR,
                evidence=('窗口内缩略图缓存被写 %d 次，其中 %d 次远离开机时刻'
                          % (len(quiet) + len(near_boot), len(quiet)))
                         if (quiet or near_boot) else
                         '窗口内缩略图缓存没有被写（= 没有生成新缩略图）',
                items=items, source=os.path.join(base, 'thumbcache_*.db'),
                note='只有远离开机时刻的写入才算"那段时间去浏览了新的图片/文件"；'
                     '开机后 3 分钟内的刷新是登录时自动发生的，不算。'
                     '没被写只是弱证据：已缓存过的文件再看不会重写。')


def _all_prefetch_runs():
    """全部 .pf 里记录的运行时刻 -> [(时间, 可执行名)]，读不到返回 []。"""
    pf = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'Prefetch')
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import prefetch_parse as pp
    except Exception:
        return []
    rows = []
    for p in glob.glob(os.path.join(pf, '*.pf')):
        try:
            r = pp.parse(open(p, 'rb').read())
        except Exception:
            continue
        for v in r['last_runs']:
            t = pp.filetime_to_dt(v)
            if t:
                rows.append((t, r['executable']))
    rows.sort()
    return rows


def chk_boot_screen():
    """开机时屏幕上会出现什么 —— 新开机的"初始态"。

    **为什么这一项能成立**：如果窗口内的机器是**新开机的**，它就没有"之前的状态"。
    屏幕上有什么 = **桌面** + **自己启动的程序**，两样都能列出来。
    （如果机器在窗口开始前就开着，那"之前的状态"确实无从得知 —— 所以先看开机时刻。）

    这里的窗口内只有一次开机（00:32:34），于是下面这张表就是当时的初始屏幕状态。
    """
    boots = _boot_events_in_window()
    items = []

    # 桌面：开机时就已经摆在那儿的图标
    for d in (os.path.join(HOME, 'Desktop'), r'C:\Users\Public\Desktop'):
        if os.path.isdir(d):
            n = len([x for x in os.listdir(d) if x != 'desktop.ini'])
            items.append('桌面 %s：%d 个图标' % (d, n))

    if not boots:
        return dict(verdict=UNKNOWN,
                    evidence='读不到窗口内的开机事件，无法确定"初始态"',
                    items=items, source='System 日志 6005 | 桌面目录',
                    note='机器在窗口开始时已经开着的话，"屏幕上有什么"就无从确定 —— '
                         '这是这一项真正的边界。')

    runs = _all_prefetch_runs()
    if not runs:
        return dict(verdict=UNKNOWN,
                    evidence='窗口内有 %d 次开机，但读不到程序运行历史' % len(boots),
                    items=items, source='System 日志 6005 | Prefetch',
                    note='Prefetch 被清理过就读不到，这一项会缺。')

    per_boot = []
    for b in boots:
        got = [(t, exe) for t, exe in runs
               if 0 <= (t - b).total_seconds() <= 300]
        per_boot.append((b, got))
    total = sum(len(g) for _, g in per_boot)
    for b, got in per_boot:
        items.append('开机 %s，之后 5 分钟内运行了 %d 个程序：'
                     % (b.strftime('%m-%d %H:%M:%S'), len(got)))
        for t, exe in got[:40]:
            items.append('    %s  %s' % (t.strftime('%H:%M:%S'), exe))
    return dict(verdict=CLEAR if total else UNKNOWN,
                evidence='窗口内 %d 次开机，开机后 5 分钟内共运行 %d 个程序 '
                         '（这就是当时的"初始屏幕"）' % (len(boots), total),
                items=items, source='System 日志 6005 | Prefetch 运行历史 | 桌面目录',
                note='新开机 = 没有"之前的状态"，所以屏幕上有什么基本可列。'
                     '前提是窗口内确实开机过；若机器在窗口开始前就开着，这一项不成立。')


def chk_session_restore():
    """上次没关掉的东西，有没有被**自动恢复到屏幕上**。

    这是"看一眼不留痕"最容易被忽略的一条路：浏览器"继续上次浏览"、WPS/Office
    文档恢复、编辑器的热退出还原 —— 都会在开机时把**上次的内容**重新摆到屏幕上，
    而且这个人**什么都没做**。

    查法是看这些"会话状态"文件在窗口内**有没有被写过**：
    被写 = 恢复发生过；没被写 = 没有内容被恢复出来。
    """
    targets = (
        ('浏览器标签页(Edge)',
         [os.path.join(L, 'Microsoft', 'Edge', 'User Data', p, 'Sessions', '*')
          for p in ('Default', 'Profile 1', 'Profile 2')]),
        ('浏览器标签页(Chrome)',
         [os.path.join(L, 'Google', 'Chrome', 'User Data', p, 'Sessions', '*')
          for p in ('Default', 'Profile 1')]),
        ('WPS 文档恢复',
         [os.path.join(R, 'kingsoft', 'office6', 'backup', '**', '*')]),
        ('VSCode 热退出',
         [os.path.join(R, 'Code', 'Backups', '*'),
          os.path.join(R, 'Code', 'User', 'workspaceStorage', '*')]),
        ('Notepad++ 会话',
         [os.path.join(R, 'Notepad++', 'session.xml')]),
        ('OneNote 缓存',
         [os.path.join(L, 'Microsoft', 'OneNote', '16.0', 'cache', '*')]),
    )
    items, hits, present = [], 0, []
    for label, pats in targets:
        allf = []
        for pat in pats:
            allf += glob.glob(pat, recursive=True)
        allf = [f for f in allf if os.path.isfile(f)]
        if not allf:
            continue
        present.append(label)
        inw_f = [(mtime(f), f) for f in allf if mtime(f) and inw(mtime(f))]
        if inw_f:
            hits += 1
            for t, f in sorted(inw_f)[:5]:
                items.append('%s  %s  <== 窗口内被写  %s'
                             % (label, t.strftime('%m-%d %H:%M:%S'), f[-80:]))
        else:
            newest = max(allf, key=lambda f: mtime(f) or datetime.datetime.min)
            items.append('%s：窗口内无变化（最近一次 %s，这期间没有内容被恢复出来）'
                         % (label, (mtime(newest) or datetime.datetime.min).strftime('%m-%d %H:%M')))
    if not present:
        return dict(verdict=UNKNOWN,
                    evidence='本机没有这些会话恢复文件（可能都没装/没用过）',
                    items=[], source='Edge/Chrome Sessions | WPS backup | VSCode Backups | …',
                    note='目录都不存在 = 不适用；装了却没有才是"没查成"。')
    return dict(verdict=HIT if hits else CLEAR,
                evidence=('窗口内有 %d 类程序写入了会话恢复文件 —— '
                          '可能有上次的内容被自动摆回屏幕' % hits) if hits
                         else '窗口内没有任何"会话恢复"被触发（上次的内容没有被自动摆回屏幕）',
                items=items,
                source='Edge/Chrome Sessions | WPS office6\backup | VSCode Backups | Notepad++ | OneNote',
                note='这一项回答的是"他什么都没做、屏幕上就有东西"那条路。'
                     '没被写 = 那一类内容没有被自动恢复出来。')


CHECKS = [
    ('开机初始态', '开机时屏幕上会出现什么', chk_boot_screen),
    ('会话恢复', '上次没关的东西有没有被自动摆回屏幕', chk_session_restore),
    ('远程连入', '有没有人远程连进来过', chk_remote_access),
    ('外部存储', '有没有插 U 盘 / 移动硬盘', chk_external_storage),
    ('文档', '有没有打开过文档', chk_documents),
    ('文件对话框', '打开/保存对话框用过的文件', chk_file_dialogs),
    ('Office', 'Office 最近文档', chk_office),
    ('文件夹', '资源管理器里翻过哪些文件夹', chk_folder_browsing),
    ('上网', '浏览器访问记录', chk_browsing),
    ('截图', '截图 / 录屏', chk_screenshots),
    ('缩略图', '有没有人用缩略图看过图片', chk_thumbcache),
    ('打印', '有没有人打印过东西', chk_printing),
    ('云同步', '有没有把文件同步到云端', chk_cloud_sync),
    ('浏览器敏感库', '密码库 / 自动填充 / 书签被碰过吗', chk_browser_secrets,
     '浏览器 User Data 下的 Login Data / Web Data / Bookmarks / Preferences / Shortcuts / Top Sites'),
    ('运行框', 'Win+R 用过什么', chk_run_dialog),
    ('跳转列表', '哪个应用被用过', chk_jumplists),
    ('回收站', '窗口内删了什么', chk_recycle),
    ('聊天客户端', '微信/QQ 当时开着吗', chk_chat_clients,
     r'%SystemRoot%\Prefetch\WEIXIN|WECHATAPPEX|QQ.EXE-*.pf + '
     r'%APPDATA%\Tencent\xwechat\log\mm_*.xlog'),
    ('通知中心', '屏幕上有没有弹出过消息预览', chk_notifications,
     r'%LOCALAPPDATA%\Microsoft\Windows\Notifications\wpndatabase.db 的 Notification 表'),
    ('执行记录差集', '窗口内跑过、但 Prefetch 漏掉的程序', chk_bam_missing),
    ('登录账号', '窗口内登录过哪些账号', chk_logged_accounts,
     r'<英雄联盟安装目录>\Game\Logs\LeagueClient Logs\*LeagueClient.log 的 CurrentSummoner'),
    ('摄像头/麦克风', '有没有开过摄像头、录过音', chk_camera_mic),
    ('下载', '窗口内下载过什么文件', chk_downloads),
    ('命令行', '窗口内有没有人敲过命令', chk_console_history),
    ('按名搜索', '有没有人用 Everything 搜过你的文件名', chk_file_search),
    ('痕迹是否被抹', '日志/审计/记录有没有被人动过', chk_tampering),
]

BLIND_SPOTS = [
    '屏幕内容：如果敏感内容当时就摆在桌面或某个窗口里，他"看一眼"不产生任何可查痕迹。'
    '这套方法只能查到"他主动去打开/搜索/复制"，查不到"他看到了本来就在那儿的东西"。',
    '浏览器内部页：edge:// / chrome:// 页面（历史、密码、书签设置页）不写入历史库。',
    '应用内自带浏览器：任何未列入检查清单的嵌入式 Chromium 都可能有自己的历史库。',
    '只读访问：多数检查靠"文件/注册表被改动"判断，纯读取可能不留痕。',
    '活动历史 / 时间线（ActivitiesCache.db）：本机有这个库，但它不含回答本问题所需的信息 '
    '—— 逐条查过，记录里没有应用名也没有文档标题（实测 1126 条全为空壳），'
    '所以它提供不了"当时前台是什么"。不要把它算成一项通过的检查：'
    '查这种空库得到的 0 条不带任何信息，却会让人以为"看过屏幕内容了"。',
    '剪贴板历史（Win+V）：系统默认关闭。未启用时，历史上复制过的内容根本没有被记录过 —— '
    '这里查不到既不能推出"没复制过"，也不代表"复制过但被清掉了"。'
    '判断是否启用：注册表 HKCU\\Software\\Microsoft\\Clipboard 的 EnableClipboardHistory，'
    '以及 %LOCALAPPDATA%\\Microsoft\\Windows\\Clipboard 目录是否存在；两者都没有就是从未启用。',
    '时间戳可被改写：有管理员权限的人可以篡改文件与注册表时间戳。本报告不是取证级证据。',
    '窗口之外：本报告只覆盖指定时间窗，窗口外发生的事不在范围内。',
]


def main():
    global W0, W1
    ap = argparse.ArgumentParser(description='本机隐私接触面检查（某段时间）')
    ap.add_argument('--from', dest='dfrom', required=True, help='起始时间 "YYYY-MM-DD HH:MM"')
    ap.add_argument('--to', dest='dto', required=True, help='结束时间 "YYYY-MM-DD HH:MM"')
    ap.add_argument('--out', default=None, help='HTML 输出路径')
    ap.add_argument('--json', default=None, help='同时输出 JSON')
    a = ap.parse_args()

    def parse_dt(s):
        for f in ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                return datetime.datetime.strptime(s, f)
            except ValueError:
                continue
        raise SystemExit('无法解析时间: %r（用 "YYYY-MM-DD HH:MM"）' % s)

    W0, W1 = parse_dt(a.dfrom), parse_dt(a.dto)
    if W1 <= W0:
        raise SystemExit('结束时间早于起始时间')
    _check_timebase()

    for entry in CHECKS:
        key, title, fn = entry[0], entry[1], entry[2]
        # 第 4 项是"兜底数据源"：检查函数自己没声明 source 时用它。
        # 这样"每一项都要打印数据源"这条纪律不会再因为某个函数忘了写而破掉。
        hint = entry[3] if len(entry) > 3 else ''
        try:
            r = fn()
            add(key, title, r.get('verdict', UNKNOWN), r.get('evidence', ''),
                r.get('items'), r.get('note', ''), r.get('source') or hint)
        except Exception as e:
            add(key, title, UNKNOWN, '检查过程抛异常: %s: %s' % (type(e).__name__, e),
                [], '', hint)

    pc = power_context()
    n_hit = sum(1 for r in results if r['verdict'] == HIT)
    n_clear = sum(1 for r in results if r['verdict'] == CLEAR)
    n_unk = sum(1 for r in results if r['verdict'] == UNKNOWN)

    print('WINDOW  %s -> %s' % (W0, W1))
    if pc['ok']:
        pct = pc['on_seconds'] / pc['window_seconds'] * 100 if pc['window_seconds'] else 0
        print('POWER   on %s of %s (%.0f%%)'
              % (str(datetime.timedelta(seconds=int(pc['on_seconds']))),
                 str(datetime.timedelta(seconds=int(pc['window_seconds']))), pct))
        for _s, _e in pc['intervals']:
            print('        ON  %s -> %s' % (_s.strftime('%m-%d %H:%M:%S'), _e.strftime('%m-%d %H:%M:%S')))
        if pct < 50:
            print('        NOTE 机器在窗口内大部分时间是关着的 —— 无记录是必然的，'
                  '不等于「他很规矩」')
    else:
        print('POWER   UNKNOWN  %s' % pc['note'])
    print('CHECKS  %d total: %d HIT / %d CLEAR / %d UNKNOWN'
          % (len(results), n_hit, n_clear, n_unk))
    print()
    for r in results:
        print('  [%-7s] %-14s %s' % (r['verdict'], r['key'], r['evidence']))
        for it in r['items'][:6]:
            print('              - %s' % it[:120])
        if r.get('source'):
            print('              源: %s' % str(r['source'])[:110])
    print()
    print('BLIND SPOTS: %d (see report)' % len(BLIND_SPOTS))

    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump({'window': [W0.isoformat(), W1.isoformat()], 'results': results,
                       'blind_spots': BLIND_SPOTS}, f, ensure_ascii=False, indent=2)
    if a.out:
        write_html(a.out, n_hit, n_clear, n_unk, pc)
    return 0


def write_html(path, n_hit, n_clear, n_unk, pc=None):
    import html as H
    e = lambda s: H.escape(str(s if s is not None else ''))
    col = {HIT: '#a02a1e', CLEAR: '#0d5c33', UNKNOWN: '#8a5800'}
    bg = {HIT: '#fdf3f2', CLEAR: '#f2faf5', UNKNOWN: '#fdf9ef'}
    lbl = {HIT: '发现接触', CLEAR: '已检查·无记录', UNKNOWN: '无法确认'}
    P = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
         '<title>隐私接触面检查</title><style>',
         'body{margin:0;background:#eef1f5;font:14px/1.7 "Microsoft YaHei",system-ui,sans-serif;color:#1b2430}',
         '.w{max-width:1000px;margin:0 auto;padding:0 20px 60px}',
         'header{background:#16202b;color:#e8eef6;padding:22px 0}header .w{padding-bottom:0}',
         'h1{margin:0 0 6px;font-size:21px}.m{font-size:12.5px;color:#93a4b6;font-family:Consolas,monospace}',
         'section{background:#fff;border:1px solid #dde3ea;border-radius:10px;padding:8px 20px 18px;margin:16px 0}',
         'h2{font-size:16px;border-bottom:2px solid #d3dae3;padding-bottom:6px;margin:18px 0 10px}',
         '.k{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0}',
         '.c{border-radius:8px;padding:10px 13px;border-left:5px solid #94a3b8;background:#f7f9fb}',
         '.c b{display:block;font-size:20px}.c span{font-size:12px;color:#5b6b7d}',
         '.r{border-left:5px solid #94a3b8;border-radius:0 8px 8px 0;padding:11px 15px;margin:9px 0}',
         '.r .t{font-weight:600;font-size:13.5px}.r .s{font-size:12.5px;color:#5b6b7d;margin-top:2px}',
         '.r ul{margin:6px 0 0 18px;padding:0;font-size:12.5px;font-family:Consolas,monospace}',
         '.r .n{font-size:12px;color:#8a5800;margin-top:6px;background:#fffdf5;padding:6px 9px;border-radius:5px}',
         '.bs{font-size:13px;color:#2c3a4a}.bs li{margin:7px 0}',
         'table{border-collapse:collapse;width:100%;font-size:12.5px}td,th{padding:6px 9px;border-bottom:1px solid #e6ebf1;text-align:left}',
         '</style></head><body>',
         '<header><div class="w"><h1>本机隐私接触面检查</h1><div class="m">窗口 %s → %s<br>'
         '方法：三态判定（发现接触 / 已检查无记录 / 无法确认）；「无法确认」不计入「无记录」</div></div></header>' % (
             e(W0.strftime('%Y-%m-%d %H:%M')), e(W1.strftime('%Y-%m-%d %H:%M')))]

    P.append('<div class="w">')
    if pc and pc.get('ok'):
        pct = pc['on_seconds'] / pc['window_seconds'] * 100 if pc['window_seconds'] else 0
        P.append('<section><h2>前提：窗口内机器开机多久</h2>')
        P.append('<p style="font-size:13.5px">窗口共 <b>%s</b>，其中<b>开机 %s（%.0f%%）</b>。</p>'
                 % (e(str(datetime.timedelta(seconds=int(pc['window_seconds'])))),
                    e(str(datetime.timedelta(seconds=int(pc['on_seconds'])))), pct))
        if pc['intervals']:
            P.append('<table><tr><th style="width:150px">开机时段</th><th>起</th><th>止</th></tr>')
            for i, (x, y) in enumerate(pc['intervals'], 1):
                P.append('<tr><td>第 %d 段</td><td>%s</td><td>%s</td></tr>'
                         % (i, e(x.strftime('%m-%d %H:%M:%S')), e(y.strftime('%m-%d %H:%M:%S'))))
            P.append('</table>')
        if pct < 50:
            P.append('<div class="r" style="border-left-color:#8a5800;background:#fdf9ef">'
                     '<div class="t">先读这一条</div><div class="s">机器在窗口内大部分时间是关着的。'
                     '下面的「无记录」有很大一部分只是因为没有开机 —— '
                     '<b>不能读成「这段时间他很规矩」</b>。请把下面的结论只看作'
                     '「开机时段内」的结论。</div></div>')
        P.append('</section>')
    elif pc:
        P.append('<section><h2>前提：窗口内机器开机多久</h2><p>%s</p></section>' % e(pc.get('note', '')))

    P.append('<section><h2>总览</h2><div class="k">')
    for v, n in ((HIT, n_hit), (CLEAR, n_clear), (UNKNOWN, n_unk)):
        P.append('<div class="c" style="border-left-color:%s;background:%s"><b style="color:%s">%d</b>'
                 '<span>%s</span></div>' % (col[v], bg[v], col[v], n, lbl[v]))
    P.append('</div>')
    if n_unk:
        P.append('<p style="font-size:13px;color:#8a5800">有 %d 项<b>无法确认</b> —— '
                 '这些项不能当作「没有」，报告下方列出了原因。</p>' % n_unk)
    P.append('</section>')

    # ---- 结论：先给一个不懂细节的人也能用的判断 ----
    # 全是按本次实际判定拼出来的句子，没有写死任何结论。
    _hits = [r for r in results if r['verdict'] == HIT]
    _clr = [r for r in results if r['verdict'] == CLEAR]
    _unk = [r for r in results if r['verdict'] == UNKNOWN]
    P.append('<section style="border-left:6px solid #1f7a4d;background:#f4fbf6">'
             '<h2>结论（先看这一节）</h2>')
    if pc['ok'] and pc['window_seconds']:
        _pct = pc['on_seconds'] / pc['window_seconds'] * 100
        P.append('<p style="font-size:14.5px">这个窗口一共 <b>%s</b>，'
                 '其中机器<b>开着 %s（%.0f%%）</b>。'
                 '下面所有的检查只覆盖<b>开着的那段时间</b> —— 关机时段的"没有记录"是必然的，'
                 '不能读成"那段时间很规矩"。</p>'
                 % (e(str(datetime.timedelta(seconds=int(pc['window_seconds'])))),
                    e(str(datetime.timedelta(seconds=int(pc['on_seconds'])))), _pct))
    else:
        P.append('<p style="font-size:14.5px">窗口内开机时长<b>无法确认</b>，'
                 '因此下面所有"没有记录"都不能下结论。</p>')
    if _hits:
        P.append('<p style="font-size:14.5px">开机的那段时间里，'
                 '<b>有 %d 项查到了接触痕迹：%s</b>。'
                 '这些是"确实发生过"的，逐条列在下面 —— 请自己判断每一条是否正常。</p>'
                 % (len(_hits), e('、'.join(r['key'] for r in _hits))))
    else:
        P.append('<p style="font-size:14.5px">开机的那段时间里，'
                 '<b>没有任何一项查到接触痕迹。</b></p>')
    if _clr:
        P.append('<p style="font-size:14.5px">另有 <b>%d 项</b>检查跑到了、'
                 '确认<b>没有</b>相关记录：%s。<br>'
                 '这些"没有"是有意义的 —— 它和"没查"不是一回事。</p>'
                 % (len(_clr), e('、'.join(r['key'] for r in _clr))))
    if _unk:
        P.append('<p style="font-size:14.5px;color:#8a5800">还有 <b>%d 项无法确认</b>：%s。<br>'
                 '这几项<b>不能</b>当作"没有"。</p>'
                 % (len(_unk), e('、'.join(r['key'] for r in _unk))))
    P.append('<p style="font-size:13px;color:#5a6672"><b>这份报告能回答什么、不能回答什么：</b>'
             '它能回答"他有没有主动去打开 / 搜索 / 复制 / 翻看"。'
             '它<b>不能</b>回答"屏幕上本来就在那儿的东西有没有被看到" —— '
             '看一眼不留任何痕迹，这一条任何本地检查都做不到。</p>')
    P.append('</section>')

    P.append('<section><h2>逐项结果</h2>')
    for r in results:
        v = r['verdict']
        P.append('<div class="r" style="border-left-color:%s;background:%s">' % (col[v], bg[v]))
        P.append('<div class="t">%s <span style="color:%s;font-size:12px">［%s］</span></div>'
                 % (e(r['title']), col[v], lbl[v]))
        P.append('<div class="s">%s</div>' % e(r['evidence']))
        if r.get('source'):
            # 技能里写着"每一项都要打印它实际看了哪个数据源，以便人工复核" ——
            # 这里必须真的打出来，否则那条纪律只存在于文档里。
            P.append('<div style="font-size:11.5px;color:#8b98a8;font-family:Consolas,monospace;'
                     'margin-top:5px;word-break:break-all">数据源 · %s</div>' % e(r['source']))
        if r['items']:
            P.append('<ul>')
            for it in r['items'][:40]:
                P.append('<li>%s</li>' % e(it))
            if len(r['items']) > 40:
                P.append('<li>…（共 %d 条）</li>' % len(r['items']))
            P.append('</ul>')
        if r['note']:
            P.append('<div class="n">注意：%s</div>' % e(r['note']).replace('\n', '<br>'))
        P.append('</div>')
    P.append('</section>')

    P.append('<section><h2>这套方法查不到什么（必读）</h2><ul class="bs">')
    for b in BLIND_SPOTS:
        P.append('<li>%s</li>' % e(b))
    P.append('</ul></section>')
    P.append('</div></body></html>')

    with open(path, 'w', encoding='utf-8') as f:
        f.write(''.join(P))
    print('HTML written: %s' % path)


if __name__ == '__main__':
    sys.exit(main())
