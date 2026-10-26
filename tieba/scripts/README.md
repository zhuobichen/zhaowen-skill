# tieba-cli

百度贴吧读取工具。**不导出 cookie**：用已登录的浏览器取页面，落成本地 HTML，再离线解析。

## 为什么这样做

贴吧的 PC 接口（`/c/f/...`）每个请求都要按参数算 `sign`，逆向成本高；而移动版页面是服务端渲染的，
数据直接以 HTML 形式返回。所以只要"能拿到已登录的 HTML"，就不需要签名、也不需要把 cookie 交出去。

```
tieba.ps1 ──bsk──> 浏览器（你的登录态） ──get-html──> 本地 HTML ──> tieba.mjs 解析 ──> 结果
                        ↑ 全程不读 cookie
```

## 用法

```powershell
# 吧的帖子列表（默认第一页 30 条）
.\tieba.ps1 posts -Kw 显卡

# 连续翻多页（自动按 tid 去重，置顶贴不会重复）
.\tieba.ps1 posts -Kw 显卡 -Pages 3

# 从第 N 条开始
.\tieba.ps1 posts -Kw 显卡 -Pn 30

# 帖子楼层
.\tieba.ps1 thread -Tid 11137538751

# 只要原始 HTML
.\tieba.ps1 raw -Url 'https://tieba.baidu.com/mo/q/m?kw=%E6%98%BE%E5%8D%A1' -Out x.html
```

输出 JSON：

```powershell
.\tieba.ps1 posts -Kw 显卡 -Json
.\tieba.ps1 thread -Tid 11137538751 -Json
```

## 离线复算

抓到 HTML 后可以反复解析，不用再联网：

```powershell
node tieba.mjs posts  --file x.html
node tieba.mjs thread --file x.html
```

## 单测

```powershell
node test-parse.mjs     # 用真实抓取的 HTML 片段做 fixture，8 项断言
```

## 实现要点（踩过的坑）

| 坑 | 处理 |
|---|---|
| PC 页面 `/f?kw=` 只有 SPA 空壳 | 走移动版 `/mo/q/m?kw=`，服务端渲染 |
| 帖子页 `/p/` 默认是 PC SPA | 先用 `bsk emulate --device pixel-7`，再取 `comment-content` 结构 |
| PowerShell `"$Tid?pn=…"` 会把 `$Tid?pn` 当变量名 | 用 `'{0}?pn={1}' -f` 格式化 |
| 帖子页异步渲染 | 导航后 `wait-ms 3000`，并校验 `<title>`（不是 404、长度 > 20KB），失败自动重试一次 |
| 偶发抓到上一个标签页 | 同上，重试时重新 `emulate` + `navigate` |
| 标题里混着「置顶/精品」徽标 | 解析前先剥掉 `span.ti_icon_*` |

## 边界

- **只读**：没有发帖、回帖、收藏、点赞能力。
- **搜索暂不支持**：搜索结果是 SPA 渲染的，实测两次分别得到 84 个和 0 个链接，不稳定，没有纳入。
  要搜索建议直接开浏览器。
- 解析依赖页面结构；贴吧改版可能失效，改 `tieba.mjs` 里的 `parseThreadList` / `parseThread` 即可。
- 依赖 `bsk`（browser-skill）与一个已登录贴吧的浏览器。
- 移动版一页 **30 条**（不是 PC 版常见的 50），`-Pages` 按此步进。
