#requires -version 5.1
<#
.SYNOPSIS
    连接 Tailscale 对端，并把只读 SMB 共享映射成本机盘符。

.DESCRIPTION
    设计依据（都是实测踩出来的）：
      * Windows 盘符只能是单个字母，C1:/D1: 是非法盘符 —— 默认用 X:/Y:/Z:
      * 只跑服务、不跑托盘客户端时，tailscale CLI 一断开后端就被停掉；
        所以这里会确保 tailscale-ipn.exe 常驻。
      * net use 传含特殊字符的密码会被 PowerShell 拆坏 —— 统一用 New-SmbMapping。
      * 映射会空闲断开（Disconnected），属正常；凭据入库后重启可自动重连。

.PARAMETER Target
    对端 tailnet 地址，如 100.65.242.15

.PARAMETER RemoteUser
    共享账号，如 LAPTOP-16KH5PPA\roview

.PARAMETER Password
    共享密码。省略则交互输入。

.PARAMETER ShareNames
    依次对应的共享名，默认 RO_C RO_D RO_E

.PARAMETER Letters
    依次对应的盘符（单字母），默认 X Y Z

.PARAMETER AuthKey
    仅在尚未加入 tailnet 时需要；已在网内可省略。

.PARAMETER DryRun
    只检查并打印计划，不映射、不改设置。

.PARAMETER Unmount
    只卸载本脚本映射的盘符。

.EXAMPLE
    .\join-and-mount.ps1 -Target 100.65.242.15 -RemoteUser 'LAPTOP-16KH5PPA\roview' -DryRun
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Target,
    [Parameter(Mandatory = $true)][string]$RemoteUser,

    [string]$Password,
    [string[]]$ShareNames = @('RO_C', 'RO_D', 'RO_E'),
    [string[]]$Letters    = @('X', 'Y', 'Z'),
    [string]$AuthKey,
    [switch]$DryRun,
    [switch]$Unmount
)

$ErrorActionPreference = 'Stop'

function Step([string]$n, [string]$t) { Write-Host ""; Write-Host ("[{0}] {1}" -f $n, $t) -ForegroundColor Cyan }
function Ok([string]$m)   { Write-Host ("    [OK]   " + $m) -ForegroundColor Green }
function Warn([string]$m) { Write-Host ("    [注意] " + $m) -ForegroundColor Yellow }
function Bad([string]$m)  { Write-Host ("    [失败] " + $m) -ForegroundColor Red }

# 原生命令统一包一层，避免 stderr 在 Stop 模式下打断脚本
function Run([string]$exe, [string[]]$argv) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out  = & $exe @argv 2>&1
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
    return [pscustomobject]@{ Out = ($out | Out-String).Trim(); Code = $code }
}

function Get-TailnetIp {
    (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceAlias -like '*Tailscale*' -and $_.IPAddress -like '100.*' } |
        Select-Object -First 1 -ExpandProperty IPAddress)
}

$ts  = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
$ipn = Join-Path $env:ProgramFiles 'Tailscale\tailscale-ipn.exe'

if ($Letters.Count -ne $ShareNames.Count) { throw 'Letters 与 ShareNames 数量必须一致' }
foreach ($L in $Letters) { if ($L.Length -ne 1) { throw ("盘符必须是单个字母，收到: " + $L) } }

# ------------------------------------------------------------------ 卸载
if ($Unmount) {
    Step 0 '卸载映射'
    foreach ($L in $Letters) {
        $m = Get-SmbMapping -LocalPath "${L}:" -ErrorAction SilentlyContinue
        if ($m) { Remove-SmbMapping -LocalPath "${L}:" -Force -ErrorAction SilentlyContinue; Ok ("已移除 " + $L + ":") }
        else { Warn ($L + ": 本来就没映射") }
    }
    return
}

# ------------------------------------------------------------------ 前置
Step 0 '前置检查'
if (-not (Test-Path $ts)) { throw "未找到 Tailscale：$ts" }
Ok ("Tailscale: " + $ts)

$tailnetIp = Get-TailnetIp
if (-not $tailnetIp -and -not $AuthKey) {
    throw ('当前不在 tailnet 内，需要 -AuthKey。' + "`r`n" +
           '若这台设备此前加入过，通常只需启动托盘客户端即可恢复，不必重新要密钥。')
}

if (-not $Password) {
    $sec = Read-Host -AsSecureString ("输入 " + $RemoteUser + " 的密码")
    $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}
Ok '凭据已就绪'

# ------------------------------------------------------------------ 上线
Step 1 '确保 Tailscale 在线'
if ((Get-Service Tailscale).Status -ne 'Running') {
    if ($DryRun) { Warn '服务未运行（DryRun 不启动）' } else { Start-Service Tailscale; Ok '服务已启动' }
}

if (-not (Get-Process tailscale-ipn -ErrorAction SilentlyContinue)) {
    if ($DryRun) { Warn '托盘客户端未运行（DryRun 不启动）' }
    elseif (Test-Path $ipn) { Start-Process -FilePath $ipn; Ok '已启动托盘客户端（保持后端在线）' }
    else { Warn '找不到 tailscale-ipn.exe' }
} else { Ok '托盘客户端已在运行' }

if ($AuthKey -and -not $tailnetIp -and -not $DryRun) {
    & $ts up "--authkey=$AuthKey" '--accept-dns=false' 2>&1 | ForEach-Object { Write-Host ("      " + $_) }
}

if (-not $DryRun) {
    $deadline = (Get-Date).AddSeconds(60)
    do {
        Start-Sleep -Seconds 3
        $tailnetIp = Get-TailnetIp
    } while (-not $tailnetIp -and (Get-Date) -lt $deadline)
}

if ($tailnetIp) { Ok ("本机 tailnet 地址：" + $tailnetIp) }
else { Bad '未拿到 tailnet 地址'; throw '先解决 Tailscale 在线问题（检查托盘客户端 / tailscale status）' }

# ------------------------------------------------------------------ 连通
Step 2 ("检查 " + $Target + " 的 445")
if ($DryRun) { Warn 'DryRun 跳过探测' }
else {
    $reach = $false
    $deadline = (Get-Date).AddSeconds(45)
    do {
        $reach = Test-NetConnection -ComputerName $Target -Port 445 -WarningAction SilentlyContinue -InformationLevel Quiet -ErrorAction SilentlyContinue
        if (-not $reach) { Start-Sleep -Seconds 3 }
    } while (-not $reach -and (Get-Date) -lt $deadline)
    if ($reach) { Ok 'TCP 445 可达' }
    else { throw 'TCP 445 不可达：对方离线 / 防火墙 / 密钥失效' }
}

# ------------------------------------------------------------------ 映射
Step 3 '映射只读共享'
$plan = @()
for ($i = 0; $i -lt $ShareNames.Count; $i++) {
    $plan += [pscustomobject]@{ 盘符 = $Letters[$i] + ':'; 共享 = "\\$Target\$($ShareNames[$i])" }
}

foreach ($p in $plan) {
    if ($DryRun) { Write-Host ("    计划: {0} -> {1}" -f $p.盘符, $p.共享); continue }
    if (Get-SmbMapping -LocalPath $p.盘符 -ErrorAction SilentlyContinue) {
        Remove-SmbMapping -LocalPath $p.盘符 -Force -ErrorAction SilentlyContinue
    }
    try {
        New-SmbMapping -LocalPath $p.盘符 -RemotePath $p.共享 -UserName $RemoteUser `
            -Password $Password -Persistent $true -ErrorAction Stop | Out-Null
        Ok ("{0} -> {1}" -f $p.盘符, $p.共享)
    } catch {
        Bad ("{0} -> {1} : {2}" -f $p.盘符, $p.共享, $_.Exception.Message)
    }
}

if ($DryRun) { Write-Host ""; Write-Host 'DryRun 完成，未做任何更改。' -ForegroundColor Green; return }

Run 'cmdkey' @("/add:$Target", "/user:$RemoteUser", "/pass:$Password") | Out-Null
Ok '凭据已入库（重启后自动重连）'

# ------------------------------------------------------------------ 验收
Step 4 '验收只读（读要通、写要拒）'
$rows = @()
foreach ($p in $plan) {
    $root = $p.盘符 + '\'
    $okRead = $false; $cnt = 0
    try { $items = Get-ChildItem -LiteralPath $root -ErrorAction Stop; $okRead = $true; $cnt = ($items | Measure-Object).Count } catch { }
    $blocked = $true
    try {
        Set-Content -LiteralPath ($root + '__probe__.tmp') -Value 'x' -ErrorAction Stop
        $blocked = $false
        Remove-Item -LiteralPath ($root + '__probe__.tmp') -Force -ErrorAction SilentlyContinue
    } catch { }
    $rows += [pscustomobject]@{
        盘符   = $p.盘符
        可读   = $(if ($okRead) { '是' } else { '否' })
        顶层项 = $(if ($okRead) { "$cnt" } else { '-' })
        写入   = $(if ($blocked) { '被拒绝 OK' } else { '竟然成功 !!' })
    }
}
$rows | Format-Table -AutoSize | Out-String | Write-Host

if ($rows | Where-Object { $_.可读 -ne '是' -or $_.写入 -ne '被拒绝 OK' }) {
    Warn '有盘符不符合预期，见上表'
} else {
    Ok '全部为「可读 + 不可写」，只读生效'
}

Write-Host ""
Write-Host '卸载：.\join-and-mount.ps1 -Target <ip> -RemoteUser <user> -Unmount' -ForegroundColor Cyan
