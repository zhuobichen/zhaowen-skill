# zhihu.ps1 —— 用已登录浏览器取知乎页面，再用本地 CLI 解析
#
# 与 tieba-cli 同一套路：全程不导出 cookie。
#   1) bsk 在 Agent Window 里以已登录身份打开知乎问题页
#   2) bsk get-html 把 HTML 落成本地文件（知乎把初始状态内嵌在 js-initialData 里）
#   3) node zhihu.mjs 离线解析
#
# 用法:
#   .\zhihu.ps1 question -Id 2098047112466227298 [-Json] [-Full]
#   .\zhihu.ps1 question -Url 'https://www.zhihu.com/question/xxx' [-Json]
#   .\zhihu.ps1 hot [-Json]          # 热榜列表
#   .\zhihu.ps1 raw -Url 'https://...' -Out x.html

param(
  [Parameter(Mandatory = $true)][ValidateSet('question', 'hot', 'raw')][string]$Mode,
  [string]$Id,
  [string]$Url,
  [string]$Out,
  [switch]$Json,
  [switch]$Full
)

$ErrorActionPreference = 'Stop'

# bsk 位置：环境变量 BSK_EXE > PATH > 上级工作区的 .tools\bsk（本机放法）> 报错
function Resolve-Bsk {
  if ($env:BSK_EXE -and (Test-Path $env:BSK_EXE)) { return $env:BSK_EXE }
  $c = Get-Command bsk -ErrorAction SilentlyContinue
  if ($c) { return $c.Source }
  # scripts -> zhihu -> zhaowen-skill -> <workspace>/.tools/bsk
  $cand = Join-Path $PSScriptRoot '..\..\..\.tools\bsk\bsk.exe'
  if (Test-Path $cand) { return (Resolve-Path $cand).Path }
  throw '找不到 bsk：装好 browser-skill 后确保 bsk 在 PATH，或设环境变量 BSK_EXE 指向 bsk.exe'
}
if (-not $env:BSK_HOME) {
  $homeCand = Join-Path $PSScriptRoot '..\..\..\.bsk-home'
  if (Test-Path $homeCand) { $env:BSK_HOME = (Resolve-Path $homeCand).Path }
}
$bsk = Resolve-Bsk

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$tmpDir = Join-Path $here '.cache'
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
$cli = Join-Path $here 'zhihu.mjs'

function Fetch-Html {
  param([string]$TargetUrl, [string]$File)
  & $bsk navigate $TargetUrl --session $Session 2>&1 | Out-Null
  & $bsk wait-ms 4000 --session $Session 2>&1 | Out-Null

  $grab = {
    & $bsk get-html --session $Session --out $File --max-bytes 4000000 2>&1 | Out-Null
    if (-not (Test-Path $File)) { return $false }
    $h = [System.IO.File]::ReadAllText($File)
    $t = ([regex]::Match($h, '<title>([^<]*)</title>')).Groups[1].Value
    return -not ($t -match '安全验证|验证码|404' -or $h.Length -lt 20000)
  }

  if (-not (& $grab)) {
    & $bsk navigate $TargetUrl --session $Session 2>&1 | Out-Null
    & $bsk wait-ms 5000 --session $Session 2>&1 | Out-Null
    if (-not (& $grab)) { throw "取页面失败（可能被安全验证拦截）: $TargetUrl" }
  }
}

$Session = (& $bsk session start 2>&1 | Select-String -Pattern '^[a-z]{4}$' | Select-Object -First 1).ToString().Trim()
if (-not $Session) { throw '无法建立 bsk 会话' }

try {
  switch ($Mode) {
    'question' {
      if (-not $Url) {
        if (-not $Id) { throw 'question 模式需要 -Id 或 -Url' }
        $Url = 'https://www.zhihu.com/question/{0}' -f $Id
      }
      $file = Join-Path $tmpDir ('q-' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.html')
      Fetch-Html -TargetUrl $Url -File $file
      if ($Out) { Copy-Item $file $Out -Force }
      $args = @($cli, 'question', '--file', $file)
      if ($Json) { $args += '--json' }
      if ($Full) { $args += '--full' }
      & node @args
      Remove-Item $file -Force -ErrorAction SilentlyContinue
    }

    'hot' {
      $file = Join-Path $tmpDir ('hot-' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.html')
      Fetch-Html -TargetUrl 'https://www.zhihu.com/hot' -File $file
      if ($Out) { Copy-Item $file $Out -Force }
      $html = [System.IO.File]::ReadAllText($file)
      # 热榜条目是普通链接（href 可能是绝对地址），直接按 /question/<id> 抽取
      $items = [regex]::Matches($html, 'href="(?:https?://[^"]*)?/question/(\d+)"[^>]*>([\s\S]{0,300}?)</a>') |
        ForEach-Object {
          $title = [regex]::Replace($_.Groups[2].Value, '<[^>]+>', ' ')
          $title = [regex]::Replace($title, '\s+', ' ').Trim()
          # 链接文本里常带问题描述，按第一句截断，避免列表被长文淹掉
          if ($title.Length -gt 60) {
            $cut = $title.IndexOf('？')
            if ($cut -gt 8 -and $cut -lt 80) { $title = $title.Substring(0, $cut + 1) }
            elseif ($title.Length -gt 60) { $title = $title.Substring(0, 60) + '…' }
          }
          [pscustomobject]@{ 问题ID = $_.Groups[1].Value; 标题 = $title }
        } | Where-Object { $_.标题 } | Sort-Object 问题ID -Unique

      if ($Json) { $items | ConvertTo-Json -Depth 4 }
      else {
        Write-Host ('知乎热榜，共 {0} 条' -f $items.Count)
        $i = 0
        foreach ($it in $items) { $i++; Write-Host ('  {0}. {1}' -f $i, $it.标题); Write-Host ('     id={0}' -f $it.问题ID) }
      }
      Remove-Item $file -Force -ErrorAction SilentlyContinue
    }

    'raw' {
      if (-not $Url) { throw 'raw 模式需要 -Url' }
      $file = if ($Out) { $Out } else { Join-Path $tmpDir ('raw-' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.html') }
      Fetch-Html -TargetUrl $Url -File $file
      Write-Host ('已保存 {0} ({1} KB)' -f $file, [math]::Round((Get-Item $file).Length / 1KB))
    }
  }
} finally {
  & $bsk session stop $Session 2>&1 | Out-Null
}
