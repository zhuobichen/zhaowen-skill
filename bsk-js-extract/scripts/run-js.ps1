# 在已登录的页面上跑一段 JS，返回结果。
# 用法：
#   .\run-js.ps1 -Session abc -JsFile ..\snippets\list-inputs.js
#   .\run-js.ps1 -Session abc -Js '(()=>document.title)()'
#   .\run-js.ps1 -Session abc -Url 'https://hotels.ctrip.com/hotels/list?city=32' -Js '...'
param(
    [Parameter(Mandatory = $true)][string]$Session,
    [string]$Js,
    [string]$JsFile,
    [string]$Url,          # 给就先导航（导航也需要 context+observation）
    [int]$WaitMs = 0       # 导航后等多久（毫秒）
)

$ErrorActionPreference = "Continue"

$ws = if ($env:BSK_WORKSPACE) { $env:BSK_WORKSPACE } else { "D:\github_project\ZhaoWen_GitHub维护" }
$env:BSK_HOME = Join-Path $ws "_bskhome"
$env:TEMP = Join-Path $ws "_tmp"; $env:TMP = $env:TEMP
$env:BSK_AUTO_START = "0"
$bsk = if ($env:BSK_EXE) { $env:BSK_EXE } else { Join-Path $ws "_bsk041\bsk.exe" }

if (-not (Test-Path $bsk)) { Write-Error "找不到 bsk：$bsk"; exit 2 }
if ($JsFile) { $Js = Get-Content $JsFile -Raw -Encoding UTF8 }
if (-not $Js) { Write-Error "必须给 -Js 或 -JsFile"; exit 2 }

function Sync {
    $raw = & $bsk cooperate sync --session $Session --policy target 2>&1 | Out-String
    try { return ($raw | ConvertFrom-Json) } catch { Write-Error "cooperate sync 失败：$raw"; return $null }
}

if ($Url) {
    $s = Sync
    if (-not $s) { exit 3 }
    & $bsk navigate $Url --session $Session --context $s.context_id --observation $s.observation_id 2>&1 | Out-Null
    if ($WaitMs -gt 0) { Start-Sleep -Milliseconds $WaitMs } else { Start-Sleep -Seconds 3 }
}

$s = Sync
if (-not $s) { exit 3 }

& $bsk evaluate $Js --session $Session --context $s.context_id --observation $s.observation_id
exit $LASTEXITCODE
