# ASCII only. Identify a directory / exe: publisher, signature, install date, and whether
# it matches a known PUP vendor or a promoter shell. Read-only.
param(
  [Parameter(Mandatory = $true)][string]$Path
)
$ErrorActionPreference = 'SilentlyContinue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$dataPath = Join-Path (Split-Path -Parent $here) 'data\known_pup_vendors.json'
$db = Get-Content -LiteralPath $dataPath -Raw -Encoding UTF8 | ConvertFrom-Json

if (-not (Test-Path -LiteralPath $Path)) { Write-Output "not found: $Path"; exit 1 }

$exes = @()
if ((Get-Item -LiteralPath $Path).PSIsContainer) {
  $exes = Get-ChildItem -LiteralPath $Path -Recurse -Filter *.exe -File | Sort-Object Length -Descending | Select-Object -First 5
} else {
  $exes = @(Get-Item -LiteralPath $Path)
}

$lower = $Path.ToLower()
$vendorHit = @()
foreach ($v in $db.vendors) {
  foreach ($d in $v.dirs) { if ($lower -match [regex]::Escape($d)) { $vendorHit += $v.label; break } }
}
$shellHit = @()
foreach ($s in $db.promoter_shells.names) { if ($lower -match ('\\' + [regex]::Escape($s) + '(\\|$)')) { $shellHit += $s } }
$hasSuper = (Test-Path -LiteralPath (Join-Path $Path 'SuperApp')) -or ($lower -match 'superapp')

Write-Output "PATH : $Path"
Write-Output ("VENDOR MATCH : " + $(if ($vendorHit) { ($vendorHit -join '; ') } else { '(none by path)' }))
Write-Output ("SHELL MATCH  : " + $(if ($shellHit) { ($shellHit -join ', ') } else { '(none)' }))
Write-Output ("SuperApp dir : " + $hasSuper)

foreach ($e in $exes) {
  $sig = Get-AuthenticodeSignature -LiteralPath $e.FullName
  $signer = if ($sig.SignerCertificate) { ($sig.SignerCertificate.Subject -split ',')[0] -replace '^CN=' } else { '(unsigned)' }
  Write-Output "`n  -- $($e.Name)  ($([math]::Round($e.Length/1KB)) KB, created $($e.CreationTime.ToString('yyyy-MM-dd')))"
  Write-Output "     Product : $($e.VersionInfo.ProductName)"
  Write-Output "     Company : $($e.VersionInfo.CompanyName)"
  Write-Output "     Desc    : $($e.VersionInfo.FileDescription)"
  Write-Output "     Signer  : $signer   [$($sig.Status)]"

  $bySigner = @()
  foreach ($v in $db.vendors) {
    foreach ($s in $v.signer) { if ($signer.ToLower() -match [regex]::Escape($s.ToLower())) { $bySigner += $v.label } }
  }
  if ($bySigner) { Write-Output ("     >>> SIGNER MATCHES KNOWN PUP VENDOR: " + (($bySigner | Select-Object -Unique) -join '; ')) }
}

Write-Output "`nREMINDER: a valid signature does NOT mean clean. These vendors all have real code-signing certs."
