# collect.ps1 - dump forensic artifacts to JSON for the activity report
# NOTE: 本文件含中文，**必须存成 UTF-8 with BOM**。
# 无 BOM 的 UTF-8 会被 Windows PowerShell 5.1 按当前代码页（简体中文下是 GBK）解码，
# 中文串的字节会吃掉后面的引号/大括号 → 直接语法错。这个症状只在改过中文注释后出现，
# 且报错行号指向的往往是无辜的那一行。
param([string]$Out = (Join-Path $env:TEMP "activity_forensics"))
$ErrorActionPreference = "SilentlyContinue"
$out = $Out
New-Item -ItemType Directory -Force -Path $out | Out-Null

function Save($obj, $name) {
  $obj | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $out $name)
}

# ---------- environment ----------
$rdp = (Get-ItemProperty "HKLM:\System\CurrentControlSet\Control\Terminal Server").fDenyTSConnections
$os  = Get-CimInstance Win32_OperatingSystem
Save ([PSCustomObject]@{
  hostname  = $env:COMPUTERNAME
  user      = $env:USERNAME
  os        = [string]$os.Caption
  build     = ([string]$os.Version + " build " + [string]$os.BuildNumber)
  rdp_deny  = $rdp
  now       = (Get-Date).ToString("s")
  lastboot  = $os.LastBootUpTime.ToString("s")
}) "env.json"

# ---------- 4624 logons (last 7 days) ----------
$ev = @(Get-WinEvent -FilterHashtable @{LogName="Security"; Id=4624; StartTime=(Get-Date).AddDays(-7)} -MaxEvents 3000)
$rows = New-Object System.Collections.ArrayList
foreach ($e in $ev) {
  $x = [xml]$e.ToXml(); $d = @{}
  foreach ($n in $x.Event.EventData.Data) { $d[[string]$n.Name] = [string]$n."#text" }
  [void]$rows.Add([PSCustomObject]@{
    time = $e.TimeCreated.ToString("s")
    lt   = [string]$d["LogonType"]
    user = [string]$d["TargetUserName"]
    src  = [string]$d["IpAddress"]
    proc = [string]$d["ProcessName"]
  })
}
Save $rows.ToArray() "logons.json"

# ---------- 4625 failed logons ----------
$f = @(Get-WinEvent -FilterHashtable @{LogName="Security"; Id=4625; StartTime=(Get-Date).AddDays(-7)} -MaxEvents 500)
$fr = New-Object System.Collections.ArrayList
foreach ($e in $f) {
  $x = [xml]$e.ToXml(); $d = @{}
  foreach ($n in $x.Event.EventData.Data) { $d[[string]$n.Name] = [string]$n."#text" }
  [void]$fr.Add([PSCustomObject]@{ time=$e.TimeCreated.ToString("s"); user=[string]$d["TargetUserName"]; src=[string]$d["IpAddress"]; lt=[string]$d["LogonType"] })
}
Save $fr.ToArray() "failed.json"

# ---------- session change / lock / logoff ----------
$s = @(Get-WinEvent -FilterHashtable @{LogName="Security"; Id=4800,4801,4634,4647,4778,4779; StartTime=(Get-Date).AddDays(-10)} -MaxEvents 400)
$sr = New-Object System.Collections.ArrayList
foreach ($e in $s) { [void]$sr.Add([PSCustomObject]@{ time=$e.TimeCreated.ToString("s"); id=$e.Id }) }
Save $sr.ToArray() "session.json"

# ---------- boot / shutdown ----------
$b = @(Get-WinEvent -FilterHashtable @{LogName="System"; Id=6005,6006,6008,1074,41} -MaxEvents 60)
$br = New-Object System.Collections.ArrayList
foreach ($e in $b) { [void]$br.Add([PSCustomObject]@{ time=$e.TimeCreated.ToString("s"); id=$e.Id }) }
Save $br.ToArray() "boot.json"

# ---------- 4688 process-creation audit availability ----------
$p = @(Get-WinEvent -FilterHashtable @{LogName="Security"; Id=4688} -MaxEvents 5000)
$newest = ""; $oldest = ""
if ($p.Count -gt 0) { $newest = $p[0].TimeCreated.ToString("s"); $oldest = $p[-1].TimeCreated.ToString("s") }
Save ([PSCustomObject]@{ count=$p.Count; newest=$newest; oldest=$oldest }) "audit4688.json"

# ---------- scheduled tasks (non-Microsoft) ----------
$t = Get-ScheduledTask | Where-Object { $_.TaskPath -notmatch "Microsoft" }
$tr = New-Object System.Collections.ArrayList
foreach ($task in $t) {
  $i = $task | Get-ScheduledTaskInfo
  $last = ""; if ($i.LastRunTime) { $last = $i.LastRunTime.ToString("s") }
  $acts  = ($task.Actions  | ForEach-Object { [string]$_.Execute + " " + [string]$_.Arguments }) -join " ;; "
  $trigs = ($task.Triggers | ForEach-Object { $_.CimClass.CimClassName }) -join ","
  [void]$tr.Add([PSCustomObject]@{
    name  = ("{0}{1}" -f $task.TaskPath, $task.TaskName)
    state = [string]$task.State
    last  = $last
    rc    = $i.LastTaskResult
    trig  = $trigs
    act   = $acts
  })
}
Save $tr.ToArray() "tasks.json"

# ---------- prefetch header magic (detect format generation) ----------
$magic = @{}
foreach ($f in (Get-ChildItem "C:\Windows\Prefetch\*.pf" | Select-Object -First 300)) {
  try {
    $fs = [System.IO.File]::OpenRead($f.FullName)
    $buf = New-Object byte[] 4
    [void]$fs.Read($buf, 0, 4)
    $fs.Close()
    $h = ($buf | ForEach-Object { $_.ToString("x2") }) -join ""
    if ($magic.ContainsKey($h)) { $magic[$h] = [int]$magic[$h] + 1 } else { $magic[$h] = 1 }
  } catch { }
}
$mr = New-Object System.Collections.ArrayList
foreach ($k in $magic.Keys) { [void]$mr.Add([PSCustomObject]@{ magic=$k; count=$magic[$k] }) }
Save $mr.ToArray() "pfmagic.json"

# ---------- AUTORUNS: every place that can launch something at logon/boot ----------
$ar = New-Object System.Collections.ArrayList
function AddAR($where, $name, $val) {
  [void]$ar.Add([PSCustomObject]@{ where=$where; name=[string]$name; value=[string]$val })
}
foreach ($pair in @(
  @{ p="HKCU:\Software\Microsoft\Windows\CurrentVersion\Run";             w="HKCU Run" },
  @{ p="HKLM:\Software\Microsoft\Windows\CurrentVersion\Run";             w="HKLM Run" },
  @{ p="HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"; w="HKLM Run (32-bit)" },
  @{ p="HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce";         w="HKCU RunOnce" },
  @{ p="HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce";         w="HKLM RunOnce" }
)) {
  $k = Get-Item $pair.p
  foreach ($n in $k.GetValueNames()) { AddAR $pair.w $n ($k.GetValue($n)) }
}
foreach ($pair in @(
  @{ d="$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup";    w="Startup folder (user)" },
  @{ d="$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup"; w="Startup folder (all users)" }
)) {
  foreach ($f in (Get-ChildItem $pair.d -Force)) {
    if ($f.Name -ne "desktop.ini") { AddAR $pair.w $f.Name "" }
  }
}
$wl = Get-Item "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
AddAR "Winlogon" "Userinit" ([string]$wl.GetValue("Userinit"))
AddAR "Winlogon" "Shell"    ([string]$wl.GetValue("Shell"))
foreach ($svc in (Get-CimInstance Win32_Service)) { AddAR "Service" $svc.Name ([string]$svc.PathName) }
Save $ar.ToArray() "autoruns.json"

# ---------- client / game install roots ----------
# 客户端/游戏目录**不写死盘符** —— 每台机器的安装盘和自定义目录都不同，
# 写死了既只对一台机器成立，那条路径本身又是那台机器的指纹。
# 必须放在**签名段之前**（签名段要按它去找客户端主程序）。
# 这里只用固定盘扫描；卸载注册表给的 InstallLocation 稍后追加（那时 $soft 才建好）。
$nameRe   = '(?i)weixin|wechat|tencent|wegame|英雄联盟|league of legends|todesk|^qq'
$appRoots = New-Object System.Collections.ArrayList
try {
  foreach ($drv in [System.IO.DriveInfo]::GetDrives()) {
    try { $ready = $drv.IsReady } catch { $ready = $false }
    if ($drv.DriveType -ne 'Fixed' -or -not $ready) { continue }
    foreach ($d in (Get-ChildItem $drv.RootDirectory.FullName -Directory -ErrorAction SilentlyContinue)) {
      if ($d.Name -match $nameRe) { [void]$appRoots.Add($d.FullName) }
    }
  }
} catch {}

# ---------- authenticode signatures of the relevant binaries ----------
$cands = New-Object System.Collections.ArrayList
# 「多开/清理」类工具要知道是**哪几个名字**（鲁大师系），但不该写死它们装在
# 哪个盘哪个子目录 —— 用标准 ProgramFiles 根 + 名字去找。
$pf86 = [Environment]::GetFolderPath('ProgramFilesX86')
foreach ($d in @("$pf86\LdsMultiWechatA",
                 "$pf86\LdsDuplicateFileClean\SuperApp\multi_wechat",
                 "$pf86\LdsSysClean\SuperApp\multi_wechat",
                 "$pf86\LhpLionProtect\SuperApp\multi_wechat")) {
  if (-not (Test-Path $d)) { continue }
  foreach ($f in (Get-ChildItem "$d\*.exe" -ErrorAction SilentlyContinue)) { [void]$cands.Add($f) }
}
# 聊天客户端主程序：在 $appRoots（上面按固定盘扫出的客户端目录）里找，不指定盘符
foreach ($d in $appRoots) {
  foreach ($f in (Get-ChildItem $d -Recurse -Depth 3 -File -ErrorAction SilentlyContinue |
                  Where-Object { $_.Name -match '(?i)^(weixin|wechat|wechatappex|qq)\.exe$' })) {
    [void]$cands.Add($f)
  }
}
$sig = New-Object System.Collections.ArrayList
$seen = @{}
foreach ($f in $cands) {
  if ($seen.ContainsKey($f.FullName)) { continue }
  $seen[$f.FullName] = 1
  $sg = Get-AuthenticodeSignature $f.FullName
  $subj = ""; $exp = ""
  if ($sg.SignerCertificate) {
    $subj = [string]$sg.SignerCertificate.Subject
    $exp  = $sg.SignerCertificate.NotAfter.ToString("s")
  }
  [void]$sig.Add([PSCustomObject]@{
    path   = $f.FullName
    status = [string]$sg.Status
    signer = $subj
    expires= $exp
    size   = $f.Length
    mtime  = $f.LastWriteTime.ToString("s")
    sha256 = (Get-FileHash $f.FullName -Algorithm SHA256).Hash
  })
}
Save $sig.ToArray() "signatures.json"

# ---------- Recent items (QQ chat-window opens leave fuin= in the filename) ----------
$rec = New-Object System.Collections.ArrayList
foreach ($f in (Get-ChildItem "$env:APPDATA\Microsoft\Windows\Recent\*.lnk" -Force)) {
  [void]$rec.Add([PSCustomObject]@{ name=$f.Name; time=$f.LastWriteTime.ToString("s"); size=$f.Length })
}
Save $rec.ToArray() "recent.json"

# ---------- running processes snapshot ----------
$pr = New-Object System.Collections.ArrayList
foreach ($proc in (Get-Process)) {
  $st = ""
  try { $st = $proc.StartTime.ToString("s") } catch { }
  [void]$pr.Add([PSCustomObject]@{ name=[string]$proc.Name; id=$proc.Id; start=$st; path=[string]$proc.Path })
}
Save $pr.ToArray() "procs.json"

# ---------- installed Tencent / game software ----------
$soft = New-Object System.Collections.ArrayList
foreach ($hive in @("HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
                    "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
                    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*")) {
  foreach ($e in (Get-ItemProperty $hive)) {
    $dn = [string]$e.DisplayName
    if ($dn -match "(?i)wegame|league|英雄联盟|腾讯游戏|tencent|weixin|wechat|qq|鲁大师|ludashi|tcls|riot") {
      $loc = [string]$e.InstallLocation
      if (-not $loc) { $loc = Split-Path ([string]$e.UninstallString) -Parent }
      [void]$soft.Add([PSCustomObject]@{
        name = $dn; ver = [string]$e.DisplayVersion
        pub = [string]$e.Publisher; loc = $loc
      })
    }
  }
}
Save $soft.ToArray() "software.json"

# 把卸载注册表给的 InstallLocation 并进 $appRoots（上面那段扫固定盘时 $soft 还没建）。
# 注册表里登记过的目录更精确（如 WeGame 在 LoL 目录内），补进来能多发现一层。
foreach ($s in $soft) { if ($s.loc) { [void]$appRoots.Add([string]$s.loc) } }
$appRoots = @($appRoots | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique)
Save $appRoots "app_roots.json"


# ---------- recent file activity under Tencent / game roots ----------
$since  = (Get-Date).AddDays(-4)
$skipRe = '(?i)\\cache\\|\\temp\\|\\crashpad\\|\\cachedata\\|\\apps\\|\\TinyDLEx\\|\\AntiCheatExpert\\|\\versions\\|\\dumps\\|\\CrashDumps\\'
$roots  = New-Object System.Collections.ArrayList
foreach ($p in @("$env:APPDATA\Tencent", "$env:LOCALAPPDATA\Tencent",
                 "$env:USERPROFILE\Documents\Tencent Files",
                 "$env:APPDATA\Microsoft\Windows\Recent")) {
  if (Test-Path $p) { [void]$roots.Add($p) }
}
# 客户端/游戏目录来自上面按固定盘扫出的 $appRoots（不写死盘符）。
foreach ($p in $appRoots) {
  [void]$roots.Add($p)
  # 这些目录里真正有时间价值的是日志/配置子目录，往下补两层
  foreach ($d in (Get-ChildItem $p -Directory -Recurse -Depth 2 -ErrorAction SilentlyContinue)) {
    if ($d.Name -match '(?i)^logs?$|^TLog$|^config$') { [void]$roots.Add($d.FullName) }
  }
}
$rf = New-Object System.Collections.ArrayList
foreach ($root in ($roots | Select-Object -Unique)) {
  Get-ChildItem $root -Recurse -File -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -gt $since -and $_.FullName -notmatch $skipRe } |
    ForEach-Object { [void]$rf.Add([PSCustomObject]@{ t=$_.LastWriteTime.ToString("s"); p=$_.FullName; s=$_.Length }) }
}
Save ($rf.ToArray() | Select-Object -First 8000) "activity.json"
"activity_files=" + $rf.Count

# ---------- QQ login SDK hourly logs + its account db ----------
$pre = New-Object System.Collections.ArrayList
foreach ($f in (Get-ChildItem "$env:APPDATA\Tencent\QQNTOpenSDK\*\log\*.xlog" -ErrorAction SilentlyContinue)) {
  [void]$pre.Add([PSCustomObject]@{ n=$f.Name; t=$f.LastWriteTime.ToString("s"); s=$f.Length; app=$f.Directory.Parent.Name })
}
Save $pre.ToArray() "prelogin.json"

$sdk = New-Object System.Collections.ArrayList
foreach ($f in (Get-ChildItem "$env:APPDATA\Tencent\QQNTOpenSDK\*\sdk_db\*" -ErrorAction SilentlyContinue)) {
  [void]$sdk.Add([PSCustomObject]@{ p=$f.FullName; t=$f.LastWriteTime.ToString("s"); s=$f.Length })
}
Save $sdk.ToArray() "sdkdb.json"

# ---------- application / system error events (last 4 days) ----------
$ae = New-Object System.Collections.ArrayList
foreach ($log in @("Application", "System")) {
  foreach ($e in (Get-WinEvent -FilterHashtable @{LogName=$log; Level=1,2,3; StartTime=(Get-Date).AddDays(-4)} -MaxEvents 300 -ErrorAction SilentlyContinue)) {
    $m = ($e.Message -replace "\s+", " ")
    if ($m.Length -gt 220) { $m = $m.Substring(0, 220) }
    [void]$ae.Add([PSCustomObject]@{ log=$log; t=$e.TimeCreated.ToString("s"); id=$e.Id
                                     lvl=$e.LevelDisplayName; prov=$e.ProviderName; msg=$m })
  }
}
Save $ae.ToArray() "appevents.json"

# ---------- WeGame login avatars: one file per account reaching the login UI ----------
$wg = New-Object System.Collections.ArrayList
foreach ($f in (Get-ChildItem "$env:APPDATA\Tencent\WeGame\login_pic\*" -File -ErrorAction SilentlyContinue)) {
  [void]$wg.Add([PSCustomObject]@{ n=$f.BaseName; t=$f.LastWriteTime.ToString("s")
                                   s=$f.Length; tmp=($f.Extension -eq ".tmp") })
}
Save $wg.ToArray() "wegame_accounts.json"

# ---------- game login ticket dirs ----------
$tl = New-Object System.Collections.ArrayList
foreach ($base in @("$env:APPDATA\Tencent\WGLogin", "$env:APPDATA\Tencent\TCLSCore")) {
  if (-not (Test-Path $base)) { continue }
  Get-ChildItem $base -Recurse -File -ErrorAction SilentlyContinue |
    ForEach-Object { [void]$tl.Add([PSCustomObject]@{ p=$_.FullName; t=$_.LastWriteTime.ToString("s"); s=$_.Length }) }
}
Save $tl.ToArray() "gamlogin.json"

# ---------- locate the QQNTOpenSDK host (which app ships this SDK) ----------
$sl = New-Object System.Collections.ArrayList
$sdkCand = New-Object System.Collections.ArrayList
foreach ($loc in @($soft | ForEach-Object { $_.loc })) {
  if ($loc) { [void]$sdkCand.Add($loc) }
}
# 兜底：WeGame 常装在自定义目录、注册表里未必有 InstallLocation ——
# 复用上面按固定盘扫出来的客户端目录，而不是写死盘符
foreach ($p in $appRoots) { if ($p) { [void]$sdkCand.Add([string]$p) } }
foreach ($base in ($sdkCand | Select-Object -Unique)) {
  if (-not $base -or -not (Test-Path $base)) { continue }
  foreach ($f in (Get-ChildItem $base -Recurse -Depth 2 -File -Filter "QQNTOpenSDK*" -ErrorAction SilentlyContinue)) {
    [void]$sl.Add([PSCustomObject]@{ p=$f.FullName; t=$f.LastWriteTime.ToString("s"); s=$f.Length })
  }
}
Save $sl.ToArray() "sdkloc.json"

"COLLECT_DONE"
