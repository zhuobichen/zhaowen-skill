# tieba.ps1 —— 用已登录浏览器取页面，再用本地 CLI 解析
#
# 设计目标：全程不导出、不传递 cookie。
#   1) bsk 在 Agent Window 里以已登录身份打开贴吧页面（并伪装成手机，拿服务端渲染的版本）
#   2) bsk get-html 把渲染后的 HTML 落成本地文件
#   3) node tieba.mjs 离线解析这个文件
#
# 用法:
#   .\tieba.ps1 posts  -Kw 显卡 [-Pn 0] [-Pages 3] [-Json]
#   .\tieba.ps1 thread -Tid 11137538751 [-Pn 1] [-Json]
#   .\tieba.ps1 raw    -Url 'https://...' -Out x.html

param(
  [Parameter(Mandatory = $true)][ValidateSet('posts', 'thread', 'raw')][string]$Mode,
  [string]$Kw,
  [string]$Tid,
  [int]$Pn = 0,
  [int]$Pages = 1,
  [string]$Url,
  [string]$Out,
  [switch]$Json
)

$ErrorActionPreference = 'Stop'
# bsk 位置：环境变量 BSK_EXE > PATH > 上级工作区的 .tools\bsk（本机放法）> 报错
function Resolve-Bsk {
  if ($env:BSK_EXE -and (Test-Path $env:BSK_EXE)) { return $env:BSK_EXE }
  $c = Get-Command bsk -ErrorAction SilentlyContinue
  if ($c) { return $c.Source }
  # scripts -> tieba -> zhaowen-skill -> <workspace>/.tools/bsk
  $cand = Join-Path $PSScriptRoot '..\..\..\.tools\bsk\bsk.exe'
  if (Test-Path $cand) { return (Resolve-Path $cand).Path }
  throw '找不到 bsk：装好 browser-skill 后确保 bsk 在 PATH，或设环境变量 BSK_EXE 指向 bsk.exe'
}
# 没有显式设 BSK_HOME 时，跟着用工作区里的 .bsk-home
if (-not $env:BSK_HOME) {
  $homeCand = Join-Path $PSScriptRoot '..\..\..\.bsk-home'
  if (Test-Path $homeCand) { $env:BSK_HOME = (Resolve-Path $homeCand).Path }
}
$bsk = Resolve-Bsk

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$tmpDir = Join-Path $here '.cache'
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
$cli = Join-Path $here 'tieba.mjs'

# 移动版一页 30 条（实测，不是 PC 版常见的 50）
$PageSize = 30

# ── 取一页 HTML ──────────────────────────────────────────
function Fetch-Html {
  param([string]$TargetUrl, [string]$File)

  $script:Nav = $TargetUrl
  & $bsk navigate $TargetUrl --session $Session 2>&1 | Out-Null
  & $bsk wait-ms 3000 --session $Session 2>&1 | Out-Null

  $grab = {
    & $bsk get-html --session $Session --out $File --max-bytes 4000000 2>&1 | Out-Null
    if (-not (Test-Path $File)) { return $false }
    $h = [System.IO.File]::ReadAllText($File)
    $t = ([regex]::Match($h, '<title>([^<]*)</title>')).Groups[1].Value
    return -not ($t -match '404' -or $h.Length -lt 20000)
  }

  if (-not (& $grab)) {
    # 偶发拿到上一个标签页或空壳：重新模拟 + 重新导航，再来一次
    Write-Verbose '首次抓取异常，重试一次'
    & $bsk emulate --session $Session --device pixel-7 2>&1 | Out-Null
    & $bsk navigate $TargetUrl --session $Session 2>&1 | Out-Null
    & $bsk wait-ms 3500 --session $Session 2>&1 | Out-Null
    if (-not (& $grab)) { throw "取页面失败（可能被 404 或安全验证拦截）: $TargetUrl" }
  }
}

# ── 会话 ────────────────────────────────────────────────
$Session = (& $bsk session start 2>&1 | Select-String -Pattern '^[a-z]{4}$' | Select-Object -First 1).ToString().Trim()
if (-not $Session) { throw '无法建立 bsk 会话' }

try {
  & $bsk emulate --session $Session --device pixel-7 2>&1 | Out-Null

  switch ($Mode) {
    'posts' {
      if (-not $Kw) { throw 'posts 模式需要 -Kw <吧名>' }
      $escaped = [uri]::EscapeDataString($Kw)
      $all = @()
      for ($i = 0; $i -lt [Math]::Max(1, $Pages); $i++) {
        $start = $Pn + $i * $PageSize
        $u = 'https://tieba.baidu.com/mo/q/m?kw={0}&pn={1}' -f $escaped, $start
        $file = Join-Path $tmpDir ("posts-" + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.html')
        Fetch-Html -TargetUrl $u -File $file
        $pageJson = & node $cli posts --file $file --json | ConvertFrom-Json
        $all += $pageJson
        Write-Verbose ("第 {0} 页: {1} 条 (pn={2})" -f ($i + 1), $pageJson.Count, $start)
        Remove-Item $file -Force -ErrorAction SilentlyContinue
        if ($pageJson.Count -lt $PageSize) { break }   # 已经到最后一页
        if ($i -lt ([Math]::Max(1, $Pages) - 1)) { Start-Sleep -Seconds 1 }
      }
      # 按 tid 去重（置顶贴会重复出现）
      $seen = @{}
      $merged = foreach ($t in $all) { if (-not $seen.ContainsKey($t.tid)) { $seen[$t.tid] = 1; $t } }

      if ($Json) {
        $merged | ConvertTo-Json -Depth 5
      } else {
        Write-Host ("贴吧「{0}」共 {1} 条（{2} 页）" -f $Kw, $merged.Count, [Math]::Max(1, $Pages))
        foreach ($t in $merged) {
          $tags = ('{0}{1}' -f $(if ($t.置顶) { '[置顶]' } else { '' }), $(if ($t.精品) { '[精品]' } else { '' }))
          Write-Host ("  {0}{1}" -f $tags, $t.title)
          Write-Host ("     tid={0}" -f $t.tid)
        }
      }
    }

    'thread' {
      if (-not $Tid) { throw 'thread 模式需要 -Tid <帖子ID>' }
      $page = if ($Pn -le 0) { 1 } else { $Pn }
      $u = 'https://tieba.baidu.com/p/{0}?pn={1}' -f $Tid, $page
      $file = Join-Path $tmpDir ("thread-" + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.html')
      Fetch-Html -TargetUrl $u -File $file
      if ($Out) { Copy-Item $file $Out -Force }
      if ($Json) { & node $cli thread --file $file --json }
      else { & node $cli thread --file $file }
      Remove-Item $file -Force -ErrorAction SilentlyContinue
    }

    'raw' {
      if (-not $Url) { throw 'raw 模式需要 -Url' }
      $file = if ($Out) { $Out } else { Join-Path $tmpDir ("raw-" + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.html') }
      Fetch-Html -TargetUrl $Url -File $file
      Write-Host ("已保存 {0} ({1} KB)" -f $file, [math]::Round((Get-Item $file).Length / 1KB))
    }
  }
} finally {
  & $bsk session stop $Session 2>&1 | Out-Null
}
