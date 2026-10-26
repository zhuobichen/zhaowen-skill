# zhihu-cli

知乎读取工具。和 `tieba-cli` 同一套路：**用已登录浏览器取 HTML，本地离线解析，不导出 cookie**。

## 为什么

知乎接口 `/api/v4/...` 需要 `x-zse-96` 签名（实测不带签名返回 `code 10003`），逆向成本高、随版本失效。
但问题页 HTML 里内嵌了 `<script id="js-initialData">…</script>`，含问题详情、回答数、首屏答案。
所以只要"能拿到已登录的 HTML"，就不需要签名。

```
zhihu.ps1 ──bsk──> 浏览器（你的登录态）──get-html──> 本地 HTML ──> zhihu.mjs 解析
                         ↑ 全程不读 cookie
```

## 用法

```powershell
# 问题详情 + 首屏回答
.\zhihu.ps1 question -Id 2098047112466227298

# 回答全文（默认每条截断 300 字）
.\zhihu.ps1 question -Id 2098047112466227298 -Full

# 直接给 URL
.\zhihu.ps1 question -Url 'https://www.zhihu.com/question/2098047112466227298'

# 热榜
.\zhihu.ps1 hot

# JSON
.\zhihu.ps1 question -Id xxx -Json
.\zhihu.ps1 hot -Json

# 只要原始 HTML（可反复离线解析）
.\zhihu.ps1 raw -Url 'https://www.zhihu.com/question/xxx' -Out q.html
node zhihu.mjs question --file q.html
```

## 输出示例

```
问题 2098047112466227298
  樊振东「卧底」西班牙国家德比，被反复质疑盘查…对此你怎么看？
  回答 250 · 关注 498 · 浏览 1152099
  详情: 樊振东发文：第一次诺坎普之旅，荒诞得像一场梦…

首屏 5 条回答：

── Njone  👍1502  💬132  2026-10-26
   樊振东这次还是输在皇马太尊重他了…
```

## 单测

```powershell
node test-parse.mjs
```

## 限制

- **首屏只有 5 条回答**：更多要翻页/滚动，而分页走的是签名接口，暂未做。
- 热榜标题会带上问题描述，已按第一句截断到 60 字以内。
- 解析依赖 `js-initialData` 结构；知乎改版可能失效，改 `zhihu.mjs` 的 `parseQuestion` 即可。

## 装进本地技能目录（可选）

技能仓库是源码，本地已安装的 skill 目录是另一份副本。如果希望技能目录自带脚本（脱离仓库也能跑），执行一次：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.agents\skills\zhihu\scripts" | Out-Null
Copy-Item '.\*' "$env:USERPROFILE\.agents\skills\zhihu\scripts\" -Recurse -Force
```

（在 `zhaowen-skill\zhihu\scripts\` 目录下执行；其他 harness 把 `.agents\skills` 换成对应目录。）