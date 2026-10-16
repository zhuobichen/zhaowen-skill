# ASCII only. What actually ran right after the user logged in?
#
# Method: explorer.exe's StartTime == the logon moment. Prefetch last-write time ==
# last execution. So the programs that ran in the minutes after logon are exactly the
# ones worth looking at for boot-time popups.
#
# NOTE: do NOT use LastBootUpTime for this. On a machine that boots at night and is
# logged into hours later, "20 minutes after boot" contains only system processes.
param(
  [int]$WindowMinutes = 12,
  [int]$Top = 120,
  [switch]$IncludeSystem
)

$ErrorActionPreference = 'SilentlyContinue'

$ex = Get-Process explorer | Sort-Object StartTime | Select-Object -First 1
if (-not $ex) { Write-Output "no explorer.exe running - cannot determine logon time"; exit 1 }
$logon = $ex.StartTime

$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
Write-Output ("logon (explorer start) : {0}" -f $logon)
Write-Output ("last boot              : {0}" -f $boot)
if (($logon - $boot).TotalMinutes -gt 30) {
  Write-Output ("NOTE: logon was {0:N0} min after boot - the boot window is useless here, using logon window." -f ($logon - $boot).TotalMinutes)
}
Write-Output ("window: [{0} .. {1}]" -f $logon.ToString('HH:mm:ss'), $logon.AddMinutes($WindowMinutes).ToString('HH:mm:ss'))

$sysNames = @('SVCHOST','CONHOST','RUNDLL32','RUNTIMEBROKER','SIHOST','SHELLEXPERIENCEHOST',
              'DLLHOST','WMIADAP','WINMGMT','LODCTR','TASKKILL','SC','REG','WHERE','TZUTIL',
              'CURL','GIT','SH','SSH','BASH','TAIL','HEAD','SLEEP','CAT','WHICH','LOCALE',
              'HOSTNAME','ENV','POWERSHELL','OPENCONSOLE','NODE','CMD')

$hits = Get-ChildItem 'C:\Windows\Prefetch\*.pf' -Force |
  Where-Object { $_.LastWriteTime -ge $logon.AddMinutes(-1) -and $_.LastWriteTime -le $logon.AddMinutes($WindowMinutes) } |
  Sort-Object LastWriteTime

$rows = foreach ($h in $hits) {
  $name = $h.BaseName -replace '-[0-9A-F]{8}$', ''
  # prefetch base names keep the extension (RUNDLL32.EXE-xxxx) -> strip it before matching
  $bare = ($name -replace '\.EXE$', '').ToUpper()
  if (-not $IncludeSystem -and ($sysNames -contains $bare)) { continue }
  [pscustomobject]@{ Time = $h.LastWriteTime; Name = $name }
}
$rows = @($rows)
Write-Output ("`n===== {0} non-system programs executed in that window =====" -f $rows.Count)
$rows | Select-Object -First $Top | ForEach-Object { Write-Output ("  {0}  {1}" -f $_.Time.ToString('HH:mm:ss'), $_.Name) }

Write-Output "`n===== full window (including system), for reference ====="
$hits | Select-Object -First $Top | ForEach-Object {
  Write-Output ("  {0}  {1}" -f $_.LastWriteTime.ToString('HH:mm:ss'), ($_.BaseName -replace '-[0-9A-F]{8}$', ''))
}
