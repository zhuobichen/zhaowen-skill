#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Provider-side setup for a read-only SMB share over Tailscale.

.DESCRIPTION
    Creates (or reuses) a dedicated read-only local account, publishes a folder as a
    share with Share-level Read only, narrows the SMB firewall rule to the tailnet
    range, then verifies read/write behaviour end-to-end by actually authenticating
    as that account.

    Why Share-level Read and not NTFS-only:
      Default data volumes grant `Authenticated Users:(F)` (or `(M)`), and every new
      local account belongs to that group. Adding an "allow read" NTFS ACE therefore
      does NOT make the account read-only. Share Read is intersected with NTFS, so
      Share=Read alone blocks writes. See SKILL.md, supply-side trap 1.

.PARAMETER Path
    Folder to publish, e.g. D:\ or D:\Shared\Data

.PARAMETER ShareName
    Share name, e.g. RO_D

.PARAMETER Account
    Local account used by the remote reader. Created if missing.

.PARAMETER TailnetCIDR
    Remote address ranges allowed to reach SMB. Defaults to the Tailscale CGNAT range.

.EXAMPLE
    .\setup-share-readonly.ps1 -Path 'D:\' -ShareName 'RO_D' -Account 'roview'

.EXAMPLE
    # Publish E: as well, reusing the same account
    .\setup-share-readonly.ps1 -Path 'E:\' -ShareName 'RO_E' -Account 'roview'

.NOTES
    Must run elevated. Idempotent: re-running updates the share and firewall rule.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$ShareName,
    [string]$Account = 'roview',
    [string[]]$TailnetCIDR = @('100.64.0.0/10', 'fd7a:115c:a1e0::/48')
)

$ErrorActionPreference = 'Stop'

function Write-Step($n, $msg) {
    Write-Host ""
    Write-Host "=== [$n] $msg ===" -ForegroundColor Cyan
}

# ---------------------------------------------------------------- sanity
if (-not (Test-Path $Path)) { throw "Path not found: $Path" }

Write-Step 0 'Preflight'
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = ([Security.Principal.WindowsPrincipal]$id).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw 'This script must run elevated.' }
Write-Host "  path    : $Path"
Write-Host "  share   : $ShareName"
Write-Host "  account : $Account"
Write-Host "  tailnet : $($TailnetCIDR -join ', ')"

# ---------------------------------------------------------------- 1. account
Write-Step 1 "Local account '$Account'"
$existing = Get-LocalUser -Name $Account -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host '  already exists, reusing'
    Enable-LocalUser -Name $Account
} else {
    # Share-level auth needs a password; generate a strong one and print it once.
    $chars = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    $buf = New-Object byte[] 20
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buf)
    $pw = -join ($buf | ForEach-Object { $chars[$_ % $chars.Length] })
    $pw = $pw.Substring(0, 16) + '!aZ9'
    New-LocalUser -Name $Account `
        -Password (ConvertTo-SecureString $pw -AsPlainText -Force) `
        -PasswordNeverExpires -AccountNeverExpires `
        -Description 'read-only sftp/smb peer' | Out-Null
    Enable-LocalUser -Name $Account
    Write-Host '  created'
    Write-Host "  PASSWORD: $pw" -ForegroundColor Yellow
    Write-Host '  (copy it now; it is not stored anywhere)'
}

# The account must NOT be an administrator: admin rights bypass share intent
# on local interactive logon and defeat the whole point.
$inAdmin = Get-LocalGroupMember -Group 'Administrators' -ErrorAction SilentlyContinue |
           Where-Object { $_.Name -like "*$Account" }
if ($inAdmin) {
    Write-Host '  !! account is in Administrators, removing' -ForegroundColor Red
    Remove-LocalGroupMember -Group 'Administrators' -Member $Account
}
Write-Host '  not in Administrators: OK'

# ---------------------------------------------------------------- 2. share
Write-Step 2 "Share '$ShareName' (Share-level Read only)"
if (Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue) {
    Remove-SmbShare -Name $ShareName -Force
    Write-Host '  previous share removed'
}
New-SmbShare -Name $ShareName -Path $Path -ReadAccess $Account `
    -Description "read-only for $Account" | Out-Null
Get-SmbShareAccess -Name $ShareName | ForEach-Object {
    Write-Host ("    {0,-40} {1}" -f $_.AccountName, $_.AccessRight)
}
$bad = Get-SmbShareAccess -Name $ShareName |
       Where-Object { $_.AccountName -eq $Account -and $_.AccessRight -ne 'Read' }
if ($bad) { throw 'Share access is not Read-only.' }

# ---------------------------------------------------------------- 3. firewall
Write-Step 3 'Firewall: SMB inbound limited to tailnet'
$rules = Get-NetFirewallRule -ErrorAction SilentlyContinue |
         Where-Object { $_.Direction -eq 'Inbound' -and $_.DisplayName -match 'SMB-In' }
if (-not $rules) {
    New-NetFirewallRule -Name 'FPS-SMB-In-TCP' -DisplayName 'File and Printer Sharing (SMB-In)' `
        -Direction Inbound -Protocol TCP -LocalPort 445 -Action Allow | Out-Null
    $rules = Get-NetFirewallRule -Name 'FPS-SMB-In-TCP'
}
foreach ($r in $rules) {
    Set-NetFirewallRule -Name $r.Name -RemoteAddress $TailnetCIDR -Enabled True -Profile Any
    Write-Host "  $($r.DisplayName) -> $($TailnetCIDR -join ', ')"
}

# ---------------------------------------------------------------- 4. verify
Write-Step 4 'Verify as the remote account (read must work, write must fail)'
$ts = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
$selfIp = $null
if (Test-Path $ts) {
    $selfIp = (& $ts ip -4 2>$null | Select-Object -First 1)
}
if ($selfIp) {
    Write-Host "  own tailnet address: $selfIp"
    $target = "\\$selfIp\$ShareName"
} else {
    Write-Host '  Tailscale not found / not logged in; testing via loopback instead' -ForegroundColor Yellow
    $target = "\\127.0.0.1\$ShareName"
}

if ($existing) {
    Write-Host '  account already existed, so its password is unknown here.'
    Write-Host '  Skipping authenticated test; verify manually:' -ForegroundColor Yellow
    Write-Host "    New-SmbMapping -LocalPath Z: -RemotePath '$target' -UserName '$env:COMPUTERNAME\$Account' -Password '<pw>'"
    Write-Host '    try { "x" | Set-Content Z:\__probe.txt } catch { "write denied OK" }'
} else {
    Remove-SmbMapping -LocalPath 'Z:' -Force -ErrorAction SilentlyContinue
    try {
        New-SmbMapping -LocalPath 'Z:' -RemotePath $target `
            -UserName "$env:COMPUTERNAME\$Account" -Password $pw | Out-Null
        $n = (Get-ChildItem 'Z:\' -ErrorAction Stop | Measure-Object).Count
        Write-Host "  read : OK ($n entries)" -ForegroundColor Green

        $blocked = $false
        try { 'probe' | Set-Content 'Z:\__probe__.tmp' -ErrorAction Stop } catch { $blocked = $true }
        if ($blocked) {
            Write-Host '  write: denied - read-only confirmed' -ForegroundColor Green
        } else {
            Remove-Item 'Z:\__probe__.tmp' -Force -ErrorAction SilentlyContinue
            Write-Host '  write: SUCCEEDED - share is NOT read-only' -ForegroundColor Red
        }
    } catch {
        Write-Host "  mapping failed: $($_.Exception.Message)" -ForegroundColor Red
    } finally {
        Remove-SmbMapping -LocalPath 'Z:' -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host '================ done ================' -ForegroundColor Yellow
Write-Host "share   : $ShareName -> $Path"
Write-Host "account : $env:COMPUTERNAME\$Account"
if ($selfIp) { Write-Host "remote  : \\$selfIp\$ShareName" }
Write-Host ''
Write-Host 'Checklist before handing credentials over:'
Write-Host '  [ ] share access shows Read only'
Write-Host '  [ ] account is not in Administrators'
Write-Host '  [ ] write probe was denied'
Write-Host "  [ ] SMB reachable only from $($TailnetCIDR -join ', ')"
