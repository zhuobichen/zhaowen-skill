# 在指定目录起一个只读静态服务，给 bsk 的 tab create 用。
#
# 为什么需要它：bsk 不允许导航到 file://（Cannot navigate to a file URL
# without local file access），而「把本地 HTML 渲染出来再 Ctrl+A/Ctrl+C」是
# 往富文本编辑器灌版式内容最稳的一条路。
#
# 用法:
#   .\serve.ps1 -Dir 'D:\work\_tmp' -Port 8767
param(
    [Parameter(Mandatory = $true)][string]$Dir,
    [int]$Port = 8767
)

if (-not (Test-Path $Dir)) { throw "目录不存在: $Dir" }

Write-Host "serving $Dir at http://127.0.0.1:$Port/"
Push-Location $Dir
try {
    python -m http.server $Port --bind 127.0.0.1
}
finally {
    Pop-Location
}
