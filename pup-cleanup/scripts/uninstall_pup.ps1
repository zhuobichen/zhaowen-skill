# ASCII only. Find uninstall entries matching a pattern and (optionally) run their
# official uninstallers. SAFE BY DEFAULT: without -Execute it only lists.
#
# Why this exists: the same product can be installed by several different "promoter
# shells", each registering its OWN uninstall entry. Uninstalling one leaves the others
# alive. So we always enumerate ALL matching entries and report what remains after.
param(
  [Parameter(Mandatory = $true)][string]$Match,   # regex over DisplayName / InstallLocation / Publisher
  [switch]$Execute,
  [int]$WaitSeconds = 8,
  # -Sequential: launch ONE uninstaller, wait for it to actually finish, then the next.
  # Use it when a human has to click through each UI - otherwise the windows stack up.
  [switch]$Sequential,
  [int]$TimeoutSec = 240
)
$ErrorActionPreference = 'SilentlyContinue'

$roots = @(
  'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
  'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
  'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
)
$entries = @()
foreach ($r in $roots) {
  if (-not (Test-Path $r)) { continue }
  foreach ($k in (Get-ChildItem $r)) {
    $p = Get-ItemProperty $k.PSPath
    $blob = "$($p.DisplayName) $($p.InstallLocation) $($p.Publisher)"
    if ($blob -match $Match) {
      $entries += [pscustomobject]@{
        DisplayName   = $p.DisplayName
        Publisher     = $p.Publisher
        Location      = $p.InstallLocation
        Uninstall     = $p.UninstallString
        Key           = ($k.PSPath -replace '^Microsoft\.PowerShell\.Core\\Registry::', '')
      }
    }
  }
}

if ($entries.Count -eq 0) { Write-Output "no uninstall entry matches: $Match"; exit 0 }

Write-Output ("MATCHED {0} uninstall entry/entries:" -f $entries.Count)
foreach ($e in $entries) {
  Write-Output ""
  Write-Output ("  Name      : {0}" -f $e.DisplayName)
  Write-Output ("  Publisher : {0}" -f $e.Publisher)
  Write-Output ("  Location  : {0}" -f $e.Location)
  Write-Output ("  Uninstall : {0}" -f $e.Uninstall)
  Write-Output ("  RegKey    : {0}" -f $e.Key)
}

if (-not $Execute) {
  Write-Output "`nDRY RUN. Re-run with -Execute to actually launch these uninstallers."
  exit 0
}

foreach ($e in $entries) {
  $cmd = $e.Uninstall
  if (-not $cmd) { Write-Output "`n-- skip (no UninstallString): $($e.DisplayName)"; continue }
  # Uninstall strings come in three shapes. Parsing them by whitespace is WRONG:
  #   1) "C:\path\uninst.exe" /S        <- quoted
  #   2) C:\path\uninst.exe /S          <- bare, no spaces in path
  #   3) C:\Program Files (x86)\X\uninst.exe /S   <- bare path WITH spaces
  # Naive \S+ splitting turns (3) into "C:\Program" and silently skips it.
  # So: cut at the first ".exe" and treat the remainder as arguments.
  $exe = $null; $argsStr = ''
  if ($cmd -match '^\s*"([^"]+\.exe)"\s*(.*)$') { $exe = $Matches[1]; $argsStr = $Matches[2] }
  elseif ($cmd -match '^\s*(.+?\.exe)\s*(.*)$') { $exe = $Matches[1].Trim(); $argsStr = $Matches[2] }
  if (-not $exe) { Write-Output "`n-- skip (cannot parse UninstallString): $cmd"; continue }
  if (-not (Test-Path -LiteralPath $exe)) { Write-Output "`n-- skip (missing exe): [$exe]"; continue }

  $mbBefore = 0
  if ($e.Location -and (Test-Path -LiteralPath $e.Location)) {
    $mbBefore = [math]::Round((Get-ChildItem $e.Location -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1MB, 1)
  }

  Write-Output ("`n>> launching: $exe")
  Write-Output ("   args: $argsStr")
  Write-Output ("   NOTE: if a window appears, a human must click through it. These UIs often")
  Write-Output ("         put Uninstall right next to Keep/Repair, and may try to install something else.")
  if ($argsStr) { Start-Process -FilePath $exe -ArgumentList $argsStr } else { Start-Process -FilePath $exe }

  if (-not $Sequential) { Start-Sleep -Seconds $WaitSeconds; continue }

  # ---- Sequential: wait for THIS uninstaller to actually finish before the next ----
  # Wait on the install dir going idle, not on a fixed sleep. Two extra things matter:
  #   * NSIS uninstallers re-launch themselves from %TEMP%\~nsu?.tmp as Un_A.exe / Au_.exe,
  #     so the original path is already free while it is still working.
  #   * those temp dirs are normally deleted on success - if ~nsu?.tmp survives, the
  #     uninstaller was probably interrupted, so do not treat it as a clean run.
  $t0 = Get-Date
  while ($true) {
    Start-Sleep -Seconds 3
    $alive = @(Get-CimInstance Win32_Process | Where-Object {
      ($_.ExecutablePath -and $e.Location -and $_.ExecutablePath.ToLower().StartsWith($e.Location.ToLower())) -or
      ($_.Name -match '^(Un_A|Au_|Un_[A-Z])') -or
      ($_.CommandLine -and $exe -and $_.CommandLine -like "*$(Split-Path $exe -Leaf)*")
    })
    if ($alive.Count -eq 0) { break }
    if (((Get-Date) - $t0).TotalSeconds -gt $TimeoutSec) {
      Write-Output ("   TIMEOUT {0}s - still running: {1}" -f $TimeoutSec, (($alive | ForEach-Object { $_.Name }) -join ', '))
      break
    }
  }
  $nsu = @(Get-ChildItem $env:TEMP -Directory -Filter '~nsu*.tmp' -ErrorAction SilentlyContinue)
  if ($nsu.Count -gt 0) { Write-Output ("   note: {0} still present -> uninstaller probably did NOT finish cleanly" -f $nsu[0].Name) }

  if (-not (Test-Path -LiteralPath $e.Location)) {
    Write-Output ("   result: dir gone (was {0} MB)" -f $mbBefore)
  } else {
    $mbAfter = [math]::Round((Get-ChildItem $e.Location -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1MB, 1)
    Write-Output ("   result: dir still there  {0} MB -> {1} MB" -f $mbBefore, $mbAfter)
    if ($mbBefore -gt 0 -and $mbAfter -eq $mbBefore) { Write-Output "   -> size unchanged: this uninstaller was a NO-OP, go straight to quarantine.ps1" }
  }
}

Write-Output "`n===== what remains (re-check) ====="
foreach ($e in $entries) {
  $dirLeft = if ($e.Location -and (Test-Path -LiteralPath $e.Location)) { 'DIR STILL THERE' } else { 'dir gone' }
  # NOTE: Test-Path does NOT understand "HKEY_CURRENT_USER\..." - it would report every
  # key as gone. Use reg query, which does.
  reg query $e.Key *> $null
  $keyLeft = if ($LASTEXITCODE -eq 0) { 'REGKEY STILL THERE' } else { 'regkey gone' }
  Write-Output ("  {0}`n      {1} / {2}" -f $e.DisplayName, $dirLeft, $keyLeft)
  if ($keyLeft -eq 'REGKEY STILL THERE') { Write-Output ("      -> backup + remove: reg export `"{0}`" backup.reg /y ; reg delete `"{0}`" /f" -f $e.Key) }
}
Write-Output "`nIf a directory is still there with its .exe intact, the uninstaller was a no-op:"
Write-Output "use quarantine.ps1 to move it out instead of fighting it."
