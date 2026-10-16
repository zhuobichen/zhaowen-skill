# ASCII only (a UTF-8 .ps1 without BOM is read as GBK on this machine and fails to parse).
# Enumerate every autostart entry point that can launch something at logon.
# Read-only: changes nothing.
param(
  [string]$Out = "autostart.json",
  [switch]$ResolveSignatures = $true
)

$ErrorActionPreference = 'SilentlyContinue'
$items = New-Object System.Collections.ArrayList

function Add-Item {
  param([string]$Kind, [string]$Name, [string]$Value, [string]$State)
  [void]$items.Add([pscustomobject]@{ Kind = $Kind; Name = $Name; Value = $Value; State = $State })
}

# ---------- 1. Run / RunOnce ----------
$runKeys = @(
  @{ Path = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run';          Label = 'HKCU\Run' },
  @{ Path = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce';      Label = 'HKCU\RunOnce' },
  @{ Path = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run';          Label = 'HKLM\Run' },
  @{ Path = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce';      Label = 'HKLM\RunOnce' },
  @{ Path = 'HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Run';     Label = 'HKLM\Run(32)' },
  @{ Path = 'HKLM:\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\RunOnce'; Label = 'HKLM\RunOnce(32)' }
)
foreach ($k in $runKeys) {
  if (-not (Test-Path $k.Path)) { continue }
  foreach ($p in (Get-ItemProperty $k.Path).PSObject.Properties) {
    if ($p.Name -like 'PS*') { continue }
    Add-Item 'Run' "$($k.Label) :: $($p.Name)" "$($p.Value)" 'enabled'
  }
}

# ---------- 2. Startup folders ----------
$startupDirs = @(
  (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'),
  (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Startup')
)
foreach ($d in $startupDirs) {
  if (-not (Test-Path $d)) { continue }
  foreach ($f in (Get-ChildItem $d -Force)) {
    if ($f.Name -eq 'desktop.ini') { continue }
    $target = ''
    if ($f.Extension -eq '.lnk') {
      $sh = New-Object -ComObject WScript.Shell
      $target = $sh.CreateShortcut($f.FullName).TargetPath
    }
    Add-Item 'StartupFolder' $f.Name $target $d
  }
}

# ---------- 3. Logon-triggered scheduled tasks ----------
foreach ($t in (Get-ScheduledTask)) {
  $isLogon = $false
  $trigKinds = @()
  foreach ($tr in $t.Triggers) {
    $n = $tr.CimClass.CimClassName -replace 'MSFT_Task', ''
    $trigKinds += $n
    if ($n -match 'Logon|Boot') { $isLogon = $true }
  }
  if (-not $isLogon) { continue }
  foreach ($a in $t.Actions) {
    Add-Item 'ScheduledTask' $t.TaskName "$($a.Execute) $($a.Arguments)" "$($t.State) [$($trigKinds -join ',')]"
  }
}

# ---------- 4. Auto-start services ----------
foreach ($s in (Get-CimInstance Win32_Service)) {
  if ($s.StartMode -ne 'Auto') { continue }
  Add-Item 'Service' $s.Name "$($s.PathName)" "$($s.State)/$($s.StartMode)"
}

# ---------- 5. Winlogon hijack check ----------
$w = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
Add-Item 'Winlogon' 'Shell' "$($w.Shell)" $(if ($w.Shell -eq 'explorer.exe') { 'ok' } else { 'SUSPICIOUS' })
Add-Item 'Winlogon' 'Userinit' "$($w.Userinit)" $(if ($w.Userinit -match '^C:\\Windows\\system32\\userinit\.exe,?$') { 'ok' } else { 'SUSPICIOUS' })

# ---------- resolve target exe metadata ----------
foreach ($it in $items) {
  $exe = $null
  if ($it.Value -match '^\s*"([^"]+\.exe)"') { $exe = $Matches[1] }
  elseif ($it.Value -match '^\s*([A-Za-z]:\\[^"]*?\.exe)') { $exe = $Matches[1] }
  if (-not $exe) { continue }
  $it | Add-Member -NotePropertyName Exe -NotePropertyValue $exe -Force
  if (-not (Test-Path -LiteralPath $exe)) { $it | Add-Member -NotePropertyName Exists -NotePropertyValue $false -Force; continue }
  $it | Add-Member -NotePropertyName Exists -NotePropertyValue $true -Force
  if (-not $ResolveSignatures) { continue }
  $f = Get-Item -LiteralPath $exe
  $sig = Get-AuthenticodeSignature -LiteralPath $exe
  $it | Add-Member -NotePropertyName Created -NotePropertyValue $f.CreationTime.ToString('yyyy-MM-dd') -Force
  $it | Add-Member -NotePropertyName Product -NotePropertyValue "$($f.VersionInfo.ProductName)" -Force
  $it | Add-Member -NotePropertyName Company -NotePropertyValue "$($f.VersionInfo.CompanyName)" -Force
  $it | Add-Member -NotePropertyName Signer -NotePropertyValue $(if ($sig.SignerCertificate) { ($sig.SignerCertificate.Subject -split ',')[0] -replace '^CN=' } else { '(unsigned)' }) -Force
}

# ---------- report ----------
Write-Output ("TOTAL autostart entries: {0}" -f $items.Count)
foreach ($g in ($items | Group-Object Kind | Sort-Object Name)) {
  Write-Output ("`n===== {0}  ({1}) =====" -f $g.Name, $g.Count)
  foreach ($it in $g.Group) {
    $tail = ''
    if ($it.PSObject.Properties['Signer']) { $tail = "  <{0} | {1} | {2}>" -f $it.Signer, $it.Company, $it.Created }
    Write-Output ("  [{0}] {1}" -f $it.State, $it.Name)
    Write-Output ("        {0}{1}" -f $it.Value, $tail)
  }
}
$items | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Out -Encoding UTF8
Write-Output ("`nJSON written to {0}" -f $Out)
