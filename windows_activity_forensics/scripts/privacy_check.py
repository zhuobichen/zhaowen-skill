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
import os, io, sys, re, glob, json, shutil, sqlite3, argparse, datetime, subprocess

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


def _check_timebase():
    for p in (datetime.datetime(2026, 1, 1), datetime.datetime.now().replace(microsecond=0)):
        back = chrome_to_dt(dt_to_chrome(p))
        if back != p:
            raise SystemExit('TIMEBASE SELFTEST FAILED: %r -> %r' % (p, back))


def add(key, title, verdict, evidence, items=None, note=''):
    results.append({'key': key, 'title': title, 'verdict': verdict,
                    'evidence': evidence, 'items': items or [], 'note': note})


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


def chk_documents():
    """有没有打开过文档 —— 按扩展名的 MRU 子键时间。"""
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
            items.append('%s  %s' % (t.strftime('%m-%d %H:%M'), e))
    tot = times.get(base, '')
    return dict(verdict=HIT if hits else CLEAR,
                evidence='RecentDocs 各类型子键共 %d 个，窗口内被更新 %d 个；总键=%s'
                         % (len([x for x in times if x != base and times[x] not in ('', 'ERR')]),
                            hits, tot or '?'),
                items=items, source=base)


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
            items.append('%s  %s' % (t.strftime('%m-%d %H:%M'), p.split('\\')[-1]))
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
            items.append('%s  %s' % (t.strftime('%Y-%m-%d'), name))
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


def chk_browsing():
    """上网痕迹（所有能找到的 Chromium 系历史库）。"""
    roots = [(os.path.join(L, 'Microsoft', 'Edge', 'User Data'), 'Edge'),
             (os.path.join(R, 'Tencent', 'QQBrowser', 'User Data'), 'QQBrowser'),
             (os.path.join(L, 'Tencent', 'QQBrowser', 'User Data'), 'QQBrowser'),
             (os.path.join(L, 'Doubao', 'User Data'), '豆包(Doubao)'),
             (os.path.join(L, 'ima.copilot', 'User Data'), 'ima.copilot'),
             (os.path.join(R, 'zero', 'User Data'), 'zero'),
             (os.path.join(L, '360Chrome', 'Chrome', 'User Data'), '360Chrome'),
             (os.path.join(R, '360se6', 'User Data'), '360SE')]
    found, items, hits = [], [], 0
    for base, name in roots:
        if not os.path.isdir(base):
            continue
        for prof in ['Default'] + ['Profile %d' % i for i in range(1, 6)]:
            h = os.path.join(base, prof, 'History')
            if not os.path.isfile(h):
                continue
            found.append(name)
            try:
                tmp = os.path.join(T or r'D:\tmp', '_pc_%s.db' % re.sub(r'\W', '', name + prof))
                shutil.copy2(h, tmp)
                con = sqlite3.connect(tmp)
                n = list(con.execute('SELECT COUNT(*) FROM visits WHERE visit_time>=? AND visit_time<=?',
                                     (dt_to_chrome(W0), dt_to_chrome(W1))))[0][0]
                con.close()
                os.remove(tmp)
                if n:
                    hits += n
                    items.append('%s/%s  窗口内访问 %d 条' % (name, prof, n))
                else:
                    items.append('%s/%s  0 条  (库最后写入 %s)' % (
                        name, prof, (mtime(h) or datetime.datetime.min).strftime('%m-%d %H:%M')))
            except Exception as e:
                return dict(verdict=UNKNOWN,
                            evidence='%s/%s 历史库读取失败: %s' % (name, prof, e), items=items)
    if not found:
        return dict(verdict=UNKNOWN, evidence='未发现任何 Chromium 系历史库', items=[])
    # 默认浏览器确认（避免"用别的浏览器所以我们漏了"）
    out, _ = ps("(Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\Shell\\Associations\\"
                "UrlAssociations\\https\\UserChoice').ProgId")
    note = '默认浏览器 ProgId = %s' % (out.strip() or '(未设置)')
    note += ('\n注意：edge:// / chrome:// 内部页（历史、密码、书签页）不写入历史库，'
             '所以这里 0 条不能排除"他打开浏览器翻过设置页"。')
    return dict(verdict=HIT if hits else CLEAR,
                evidence='检查了 %d 个历史库，窗口内访问合计 %d 条' % (len(found), hits),
                items=items, note=note, source='; '.join(found))


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
            for f in glob.glob(os.path.join(d, '*')):
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
                items.append('%s  %s / %s' % (t.strftime('%m-%d %H:%M'), who, n))
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
                items.append('%s  <== 窗口内  %s (%s)' % (t.strftime('%m-%d %H:%M:%S'),
                                                        os.path.basename(p), tag))
    if total == 0:
        return dict(verdict=UNKNOWN, evidence='未发现跳转列表目录', items=[])
    return dict(verdict=HIT if hits else CLEAR,
                evidence='跳转列表 %d 个，窗口内被更新 %d 个' % (total, hits),
                items=items, source=ad,
                note='AppID 未解析成应用名 —— 解析需要额外映射表，'
                     '硬猜会给出错误的应用名，所以这里只报文件名与时间。')


def chk_recycle():
    """窗口内的删除记录。"""
    hits, items, total = 0, [], 0
    for root in glob.glob(r'C:\$Recycle.Bin\*'):
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
                evidence='回收站共 %d 项，窗口内删除 %d 项' % (total, hits),
                items=items,
                note='清空回收站会一并抹掉证据 —— 这里 0 条不能反证"没删过"。')


def chk_chat_clients():
    """聊天客户端在窗口内是否运行过（决定聊天记录有没有可能被看到）。"""
    items = []
    hit = False
    checks = []
    pf = r'C:\Windows\Prefetch'
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


CHECKS = [
    ('外部存储', '有没有插 U 盘 / 移动硬盘', chk_external_storage),
    ('文档', '有没有打开过文档', chk_documents),
    ('文件对话框', '打开/保存对话框用过的文件', chk_file_dialogs),
    ('Office', 'Office 最近文档', chk_office),
    ('文件夹', '资源管理器里翻过哪些文件夹', chk_folder_browsing),
    ('上网', '浏览器访问记录', chk_browsing),
    ('截图', '截图 / 录屏', chk_screenshots),
    ('浏览器敏感库', '密码库 / 自动填充 / 书签被碰过吗', chk_browser_secrets),
    ('运行框', 'Win+R 用过什么', chk_run_dialog),
    ('跳转列表', '哪个应用被用过', chk_jumplists),
    ('回收站', '窗口内删了什么', chk_recycle),
    ('聊天客户端', '微信/QQ 当时开着吗', chk_chat_clients),
]

BLIND_SPOTS = [
    '屏幕内容：如果敏感内容当时就摆在桌面或某个窗口里，他"看一眼"不产生任何可查痕迹。'
    '这套方法只能查到"他主动去打开/搜索/复制"，查不到"他看到了本来就在那儿的东西"。',
    '浏览器内部页：edge:// / chrome:// 页面（历史、密码、书签设置页）不写入历史库。',
    '应用内自带浏览器：任何未列入检查清单的嵌入式 Chromium 都可能有自己的历史库。',
    '只读访问：多数检查靠"文件/注册表被改动"判断，纯读取可能不留痕。',
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

    for key, title, fn in CHECKS:
        try:
            r = fn()
            add(key, title, r.get('verdict', UNKNOWN), r.get('evidence', ''),
                r.get('items'), r.get('note', ''))
        except Exception as e:
            add(key, title, UNKNOWN, '检查过程抛异常: %s: %s' % (type(e).__name__, e), [])

    n_hit = sum(1 for r in results if r['verdict'] == HIT)
    n_clear = sum(1 for r in results if r['verdict'] == CLEAR)
    n_unk = sum(1 for r in results if r['verdict'] == UNKNOWN)

    print('WINDOW  %s -> %s' % (W0, W1))
    print('CHECKS  %d total: %d HIT / %d CLEAR / %d UNKNOWN'
          % (len(results), n_hit, n_clear, n_unk))
    print()
    for r in results:
        print('  [%-7s] %-14s %s' % (r['verdict'], r['key'], r['evidence']))
        for it in r['items'][:6]:
            print('              - %s' % it[:120])
    print()
    print('BLIND SPOTS: %d (see report)' % len(BLIND_SPOTS))

    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump({'window': [W0.isoformat(), W1.isoformat()], 'results': results,
                       'blind_spots': BLIND_SPOTS}, f, ensure_ascii=False, indent=2)
    if a.out:
        write_html(a.out, n_hit, n_clear, n_unk)
    return 0


def write_html(path, n_hit, n_clear, n_unk):
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

    P.append('<div class="w"><section><h2>总览</h2><div class="k">')
    for v, n in ((HIT, n_hit), (CLEAR, n_clear), (UNKNOWN, n_unk)):
        P.append('<div class="c" style="border-left-color:%s;background:%s"><b style="color:%s">%d</b>'
                 '<span>%s</span></div>' % (col[v], bg[v], col[v], n, lbl[v]))
    P.append('</div>')
    if n_unk:
        P.append('<p style="font-size:13px;color:#8a5800">有 %d 项<b>无法确认</b> —— '
                 '这些项不能当作「没有」，报告下方列出了原因。</p>' % n_unk)
    P.append('</section>')

    P.append('<section><h2>逐项结果</h2>')
    for r in results:
        v = r['verdict']
        P.append('<div class="r" style="border-left-color:%s;background:%s">' % (col[v], bg[v]))
        P.append('<div class="t">%s <span style="color:%s;font-size:12px">［%s］</span></div>'
                 % (e(r['title']), col[v], lbl[v]))
        P.append('<div class="s">%s</div>' % e(r['evidence']))
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
