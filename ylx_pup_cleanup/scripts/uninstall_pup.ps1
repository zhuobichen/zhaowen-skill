# ASCII only. Find uninstall entries matching a pattern and (optionally) run their
# official uninstallers. SAFE BY DEFAULT: without -Execute it only lists.
#
# Why this exists: the same product can be installed by several different "promoter
# shells", each registering its OWN uninstall entry. Uninstalling one leaves the others
# alive. So we always enumerate ALL matching entries and report what remains after.
param(
  [Parameter(Mandatory = $true)][string]$Match,   # regex over DisplayName / InstallLocation / Publisher
  [switch]$Execute,
  [int]$WaitSeconds = 8
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
  # split: first quoted (or first whitespace-delimited) token is the exe, rest are args
  $exe = $null; $argsStr = ''
  if ($cmd -match '^\s*"([^"]+)"\s*(.*)$') { $exe = $Matches[1]; $argsStr = $Matches[2] }
  elseif ($cmd -match '^\s*(\S+)\s*(.*)$')  { $exe = $Matches[1]; $argsStr = $Matches[2] }
  if (-not (Test-Path -LiteralPath $exe)) { Write-Output "`n-- skip (missing exe): $exe"; continue }

  Write-Output ("`n>> launching: $exe")
  Write-Output ("   args: $argsStr")
  Write-Output ("   NOTE: if a window appears, a human must click through it. These UIs often")
  Write-Output ("         put Uninstall right next to Keep/Repair, and may try to install something else.")
  if ($argsStr) { Start-Process -FilePath $exe -ArgumentList $argsStr } else { Start-Process -FilePath $exe }
  Start-Sleep -Seconds $WaitSeconds
}

Write-Output "`n===== what remains (re-check) ====="
foreach ($e in $entries) {
  $dirLeft = if ($e.Location -and (Test-Path -LiteralPath $e.Location)) { 'DIR STILL THERE' } else { 'dir gone' }
  $keyLeft = if (Test-Path -LiteralPath $e.Key) { 'REGKEY STILL THERE' } else { 'regkey gone' }
  Write-Output ("  {0}`n      {1} / {2}" -f $e.DisplayName, $dirLeft, $keyLeft)
  if ($keyLeft -eq 'REGKEY STILL THERE') { Write-Output ("      -> backup + remove: reg export `"{0}`" backup.reg /y ; reg delete `"{0}`" /f" -f $e.Key) }
}
Write-Output "`nIf a directory is still there with its .exe intact, the uninstaller was a no-op:"
Write-Output "use quarantine.ps1 to move it out instead of fighting it."
