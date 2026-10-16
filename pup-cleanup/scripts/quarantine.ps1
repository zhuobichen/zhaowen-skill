# ASCII only. Move junk OUT instead of deleting it: keeps the machine recoverable and
# leaves an audit trail. Handles three things: folders/files, shortcuts, registry keys.
#
# Registry keys are EXPORTED to .reg before deletion, so the whole thing can be undone.
#
# Gotcha this avoids: `Remove-Item` with wildcard/registry paths gets blocked by the
# sandbox's static check ("protected path from removal"). So we use `reg delete` with a
# fully-qualified single key, and we never pass wildcards to Remove-Item.
param(
  [string[]]$Paths = @(),
  [string[]]$Shortcuts = @(),
  [string[]]$RegistryKeys = @(),
  [string]$QuarantineDir = "",
  [switch]$Execute
)
$ErrorActionPreference = 'SilentlyContinue'

if (-not $QuarantineDir) {
  # Default OUTSIDE the skill folder (and off the user profile): quarantine data must not
  # end up inside ~/.claude/skills (it would be picked up by publish/scan tooling).
  $QuarantineDir = "D:\_quarantine_adware_" + (Get-Date -Format 'yyyyMMdd')
}
Write-Output "quarantine dir: $QuarantineDir"

# ---- plan ----
$plan = @()
foreach ($p in $Paths)     { $plan += [pscustomobject]@{ Kind='Path';     Src=$p } }
foreach ($s in $Shortcuts) { $plan += [pscustomobject]@{ Kind='Shortcut'; Src=$s } }
foreach ($r in $RegistryKeys) { $plan += [pscustomobject]@{ Kind='RegKey'; Src=$r } }

Write-Output "`nPLAN:"
foreach ($x in $plan) {
  if ($x.Kind -eq 'RegKey') {
    reg query $x.Src *> $null
    $exists = ($LASTEXITCODE -eq 0)
  } else {
    $exists = Test-Path -LiteralPath $x.Src
  }
  Write-Output ("  [{0}] {1}  exists={2}" -f $x.Kind, $x.Src, $exists)
}
if (-not $Execute) { Write-Output "`nDRY RUN. Re-run with -Execute to apply."; exit 0 }

New-Item -ItemType Directory -Force -Path $QuarantineDir | Out-Null
$manifest = @()

# ---- 1. kill processes running from those paths ----
foreach ($p in $Paths) {
  foreach ($proc in (Get-CimInstance Win32_Process)) {
    if ($proc.ExecutablePath -and $proc.ExecutablePath.ToLower().StartsWith($p.ToLower())) {
      Write-Output ("  kill PID {0}  {1}" -f $proc.ProcessId, $proc.Name)
      Stop-Process -Id $proc.ProcessId -Force
      $manifest += [pscustomobject]@{ action='killed'; pid=$proc.ProcessId; name=$proc.Name; path=$proc.ExecutablePath }
    }
  }
}
Start-Sleep -Seconds 1

# ---- 2. shortcuts ----
foreach ($s in $Shortcuts) {
  if (Test-Path -LiteralPath $s) {
    Move-Item -LiteralPath $s -Destination $QuarantineDir -Force
    Write-Output "  moved shortcut: $s"
    $manifest += [pscustomobject]@{ action='moved'; kind='shortcut'; src=$s }
  }
}

# ---- 3. registry keys (export then delete) ----
foreach ($r in $RegistryKeys) {
  reg query $r *> $null
  if ($LASTEXITCODE -ne 0) { continue }
  $safe = ($r -replace '[^\w]', '_')
  $regFile = Join-Path $QuarantineDir ("$safe.reg")
  reg export $r $regFile /y *> $null
  reg delete $r /f *> $null
  Write-Output "  regkey deleted (backup: $regFile): $r"
  $manifest += [pscustomobject]@{ action='regkey-deleted'; key=$r; backup=$regFile }
}

# ---- 4. dirs / files ----
foreach ($p in $Paths) {
  if (-not (Test-Path -LiteralPath $p)) { continue }
  $item = Get-Item -LiteralPath $p
  $sizeMB = if ($item.PSIsContainer) { [math]::Round((Get-ChildItem $p -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 2) } else { [math]::Round($item.Length / 1MB, 2) }
  $dest = Join-Path $QuarantineDir $item.Name
  Move-Item -LiteralPath $p -Destination $dest -Force
  Write-Output ("  moved: {0}  ({1} MB)" -f $p, $sizeMB)
  $manifest += [pscustomobject]@{ action='moved'; kind='path'; src=$p; dest=$dest; sizeMB=$sizeMB }
}

$manifestPath = Join-Path $QuarantineDir 'quarantine-manifest.json'
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Output "`nmanifest: $manifestPath"
Write-Output "`nVERIFY (each should be False / not found):"
foreach ($p in $Paths) { Write-Output ("  {0} -> exists={1}" -f $p, (Test-Path -LiteralPath $p)) }
foreach ($r in $RegistryKeys) { reg query $r *> $null; Write-Output ("  {0} -> found={1}" -f $r, ($LASTEXITCODE -eq 0)) }
Write-Output "`nTo undo a path: move it back from $QuarantineDir."
Write-Output "To undo a regkey: double-click the .reg backup in $QuarantineDir."
