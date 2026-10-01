# collect.ps1  (ASCII only) - dump forensic artifacts to JSON for the activity report
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

# ---------- authenticode signatures of the relevant binaries ----------
$cands = New-Object System.Collections.ArrayList
foreach ($d in @(
  "C:\Program Files (x86)\LdsMultiWechatA",
  "C:\Program Files (x86)\LdsDuplicateFileClean\SuperApp\multi_wechat",
  "C:\Program Files (x86)\LdsSysClean\SuperApp\multi_wechat",
  "C:\Program Files (x86)\LhpLionProtect\SuperApp\multi_wechat"
)) {
  foreach ($f in (Get-ChildItem "$d\*.exe")) { [void]$cands.Add($f) }
}
foreach ($d in @("D:\WeiXin", "C:\QQ")) {
  foreach ($f in (Get-ChildItem "$d\*.exe")) { [void]$cands.Add($f) }
}
foreach ($f in (Get-ChildItem "C:\QQ\versions\*\QQ.exe")) { [void]$cands.Add($f) }
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

# ---------- recent file activity under Tencent / game roots ----------
$since  = (Get-Date).AddDays(-4)
$skipRe = '(?i)\\cache\\|\\temp\\|\\crashpad\\|\\cachedata\\|\\apps\\|\\TinyDLEx\\|\\AntiCheatExpert\\|\\versions\\|\\dumps\\|\\CrashDumps\\'
$roots  = New-Object System.Collections.ArrayList
foreach ($p in @("$env:APPDATA\Tencent", "$env:LOCALAPPDATA\Tencent",
                 "$env:USERPROFILE\Documents\Tencent Files",
                 "$env:APPDATA\Microsoft\Windows\Recent")) {
  if (Test-Path $p) { [void]$roots.Add($p) }
}
foreach ($p in @("D:\WeiXin", "C:\QQ", "D:\英雄联盟\WeGame\TLog",
                 "D:\英雄联盟\WeGame\config", "D:\英雄联盟\WeGame\client_config")) {
  if (Test-Path $p) { [void]$roots.Add($p) }
}
foreach ($d in (Get-ChildItem "D:\英雄联盟" -Directory -Recurse -Depth 2 -ErrorAction SilentlyContinue)) {
  if ($d.Name -match '(?i)^logs?$|^TLog$') { [void]$roots.Add($d.FullName) }
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
foreach ($p in @("D:\英雄联盟\WeGame", "C:\Program Files (x86)\Tencent\WeGame", "D:\WeGame")) {
  [void]$sdkCand.Add($p)
}
foreach ($base in ($sdkCand | Select-Object -Unique)) {
  if (-not $base -or -not (Test-Path $base)) { continue }
  foreach ($f in (Get-ChildItem $base -Recurse -Depth 2 -File -Filter "QQNTOpenSDK*" -ErrorAction SilentlyContinue)) {
    [void]$sl.Add([PSCustomObject]@{ p=$f.FullName; t=$f.LastWriteTime.ToString("s"); s=$f.Length })
  }
}
Save $sl.ToArray() "sdkloc.json"

"COLLECT_DONE"
