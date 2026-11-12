---
name: dev-blog-distribution
description: 把一篇中文技术长文分发到国内开发者社区（CSDN / 知乎 / 掘金 / 腾讯云开发者 / 博客园 / 开源中国 / 思否），并对抗「一稿多投」带来的判重与推荐降权。当用户说「发博客」「多平台分发」「引流」「投稿到 XX 社区」「把这篇发出去」时使用。含各站发布器的真实控件、标签规则、审核坑，以及 bsk（browser-skill）在窗口最小化、编辑器是 CodeMirror/Draft/cledit 时的可靠操作法。
version: 1.0.0
---

# 技术博客多平台分发

用真实浏览器（`browser-skill` / `bsk`）在用户已登录的各站发布，不调用任何官方 API。本文里所有选择器、按钮文案、坑都是 2026-11-12 一次真实分发里量到的，不是推断。

## 何时用 / 不用

用：要把一篇已经写好的技术文章铺到多个中文开发者平台；要评估「发哪几个站值得」；某个平台的发布器点了没反应。

不用：写文章本身（用 `khazix-writer` 出公众号稿，或按项目材料直接写）；公众号排版与推草稿箱（用 `docx_to_mp` / `mp-template-lib`）；纯公众号单平台发布（用 `wechat_mp_ops`）。

## 铁律：一稿一角度，不要一稿多投

同一份正文原样贴到四五个站，有三个明确代价：

- 搜索引擎判重，后发的页面权重被压，白干
- 社区推荐算法对「站外已见过」的内容降权
- 各站受众不同，同一篇在腾讯云社区和掘金的命中率差很远

正确做法是**同一份素材拆成多个入口**，每篇能独立被搜到，末尾都指回项目。实测有效的分工：

| 平台 | 角度 | 主线 |
|---|---|---|
| CSDN | 踩坑复盘 | 完整技术叙事 + 代码 + 清单，作为「主版本」 |
| 知乎 | 同样是复盘，标题更口语 | 长尾搜索 + 专栏 |
| 掘金 | 复盘，标题更抓 | 技术人信息流 |
| 腾讯云开发者 | 部署/运维 | 云主机当批处理执行器、临时盘、机器绑定密钥、端口边界 |
| 博客园 | 纯机制 | 去掉产品叙事，只讲通用机制与可复用代码 |
| 开源中国 | 项目向 | 为什么这么设计，挂 GitHub 项目页 |
| 思否 | 问答体 | 对着「XXX 能不能直接…」这类搜索词写 |

判断标准很朴素：**读者从哪个入口进来，看到的都该是对他有用、且别处看不到的那一面**。做不到就说明这篇还不该铺这么多站。

## 平台速查

| 平台 | 发布地址 | 编辑器 | 登录态判据 | 备注 |
|---|---|---|---|---|
| CSDN | `editor.csdn.net/md/` | cledit（`pre.editor__inner`） | 顶栏出现「已登录」气泡 | 新版编辑器有 AI 侧栏遮挡，**用旧版 md 编辑器**；博客等级 <3 不能建自定义标签 |
| 知乎 | `zhuanlan.zhihu.com/write` | Draft.js（`.public-DraftEditor-content`） | 顶栏有「创作中心」「消息 99+」 | 发布后弹「发布成功 感谢你的第 N 篇创作」 |
| 掘金 | `juejin.cn/editor/drafts/new` | CodeMirror（`.CodeMirror`） | 顶栏无「登录/注册」，有「创作者中心」 | 发布弹窗必选分类；标签 `byte-select` |
| 腾讯云开发者 | `cloud.tencent.com/developer/article/write` | Draft.js | 顶栏显示昵称（如「用户12117112」） | 发布后进**审核**；标签必须从下拉选 |
| 博客园 | `i.cnblogs.com/posts/edit` | Markdown/富文本两组 | 顶部有「我的博客」 | 支持 md，直接贴源码最省事 |
| 开源中国 | `my.oschina.net/u/<id>/blog/write` | 富文本 | 顶栏头像 | 适合挂项目链接 |
| 思否 | `segmentfault.com/write` | 富文本 | 顶栏头像 | 支持 md 模式 |

## bsk 操作要点（按踩坑顺序）

### 1. 先把版本对齐，否则浏览器永远「未连接」

扩展 0.4.x 要求 CLI 协议 ≥1.6，而旧 CLI（0.2.0，协议 1.1）连上会被直接踢：daemon 日志里刷 `kicked: local protocol 1.1 is below peer min_compatible_protocol 1.6`，`bsk status` 始终 `browsers connected 0`。用 `bsk --version` 和扩展版本对一下，CLI 太旧就换新版二进制。

`BSK_HOME` 要指到一个**可写**目录（默认 `~/.bsk` 在某些受限令牌下写不进去，daemon 会 panic 在 `initializing rolling file appender failed`）。

### 2. daemon 在 Job Object 里起不来

托管环境里 `bsk daemon start` 会报 `cannot start an independent Windows daemon; the Job Object of this process does not allow breakaway`。改用前台常驻：

```powershell
bsk daemon start --foreground --port 52800 --session-idle 90m --daemon-idle 8h
```

`--session-idle` 默认 5 分钟，坐一会儿会话就 `session_idle_timeout`，标签页全关。分发是长流程，必须调大。

### 3. 每个动作前必须 sync，且要「sync 完立刻动」

新协议（0.4.1+）所有写操作都要一对 `--context` + `--observation`：

```powershell
$j = bsk cooperate sync --session $s --json | ConvertFrom-Json
bsk click '@e12' --session $s --context $j.context_id --observation $j.observation_id
```

`sync` 和动作之间隔了别的命令，就会报 `this action needs an explicit current observation` / `the strict observation changed`。一次 sync 只能配一次动作，不要复用。

### 4. 窗口最小化时 view=0x0，click / fill / 截图全废，但 evaluate 还活着

症状：`snapshot` 里 `@view 0x0`，点击报 `target element has no visible geometry` 或 `browser rejected the underlying CDP call`，截图 `viewport capture timed out`。

两种修法，按可靠性排：

1. 用 Win32 `ShowWindow(SW_RESTORE)` + `SetForegroundWindow` 把窗口复原（用户手动最小化过的时候多半是这个原因）
2. 复原也无效时，**全部改用 `bsk evaluate` 里的原生点击**：`el.click()`、`dispatchEvent(new MouseEvent('mousedown'|'mouseup'|'click',{bubbles:true}))`。React/Vue 都吃原生事件，这条路在窗口不可见的机器上实测可用。

### 5. file:// 被拒，本地 HTML 用本地端口打开

想「把本地 HTML 渲染出来再复制正文」，`file:///` 会被拦：`Cannot navigate to a file URL without local file access`。起一个只读静态服务即可：

```powershell
python -m http.server 8767 --bind 127.0.0.1   # 在 HTML 所在目录
```

### 6. 富文本编辑器一律走剪贴板，不要指望 fill

各站编辑器分别是 cledit / Draft.js / CodeMirror，`bsk fill` 会报 `not fillable`、`fill target changed`、`the selected target is not currently actionable`。可用的路径只有两条：

- **编辑器 API**：CodeMirror `document.querySelector('.CodeMirror').CodeMirror.setValue(md)`
- **剪贴板**：源页面 `Ctrl+A` → `Ctrl+C` → 目标页 JS `focus()` → `Ctrl+V`

Draft.js 必须先 `document.querySelector('.public-DraftEditor-content').focus()`，否则粘贴会进到标题框（实测把整篇正文粘进知乎标题，标题长度直接爆掉，得手动重填）。

### 7. 标题单独填，别和正文抢焦点

- 知乎：`textarea`（placeholder「请输入标题（最多 100 个字）」）
- 掘金：`input[placeholder*="标题"]`
- 腾讯云：`textarea.article-title`
- CSDN：`input.article-bar__title`（React 受控，必须走原生 setter + `input` 事件，直接改 `.value` 不生效）

### 8. 用户随时可能接管，发布动作只做一次

用户点一下页面就会变成 `the user has control of this tab`，此时任何 sync 都被拒。正确反应是 `bsk cooperate wait`，别硬抢、别重试点击。

发布类按钮**一次只点一下，点完立刻核对**（成功 toast / 跳转 / 文章管理页计数）。这条比省时间重要：重复发布会生成两篇，删起来比发起来麻烦。

## 发布器实测细节

### CSDN（旧版 Markdown 编辑器）

- 入口 `https://editor.csdn.net/md/`，比新版编辑器稳（新版右侧 AI 侧栏会盖住工具栏，点「使用 MD 编辑器」会被侧栏吃掉）
- 标题 `input.article-bar__title`，JS 原生 setter + `input` 事件
- 正文 `pre.editor__inner`：剪贴板粘贴，先 `Ctrl+A` 再 `Ctrl+V` 覆盖
- 发布弹窗：标签只能从**推荐池**选，`博客等级不满足三级，无法创建自定义标签`；自定义标签点不进去不是 bug
- 账号有「墨衍会员」时，文章页顶部有「一键同步至各平台」（微信公众号/微博/知乎/掘金/百家号/博客园/抖音/小红书）。省事，但排版会被压平、标签要重设，只适合补量

### 知乎

- 标题 `textarea`；正文 `.public-DraftEditor-content`
- 发布按钮文案「发布」；成功后弹窗写着「感谢你的第 N 篇创作」，并从弹窗可复制链接
- 正文里的 `<pre>` 会被拆成多个代码块（一个 `pre` 变几段），可接受；粗体可能丢失

### 掘金

- CodeMirror 直接 `setValue(md)`，标题另填
- 发布弹窗：**分类必选**（后端/前端/Android/iOS/人工智能/开发工具/代码人生/阅读）；标签是 `byte-select`，可搜索也可自定义
- 「确定并发布」→ 跳 `https://juejin.cn/published`，页内显示「发布成功」+ 文章标题

### 腾讯云开发者

- 标题 `textarea.article-title`；正文 Draft.js
- 首次进编辑器会弹「新版富文本&Markdown编辑器已上线」，点「暂不体验」，否则遮住发布按钮
- 发布弹窗四个硬要求：
  1. `文章来源 = 原创`（radio，默认不选）
  2. **`文章标签` 必须从搜索下拉里选**——「自定义关键词」里按 Enter 建的那个**不算**，点确认只会弹 `请选择文章标签`
  3. 下拉项对普通 `click` 不响应，要派发 `mousedown → mouseup → click` 三连（判据：`还可以添加 N 个标签` 的数字减一）
  4. 封面可选，专栏可选
- 提交成功 toast 是「发布成功！文章正在审核中」，文章进 `审核中`，不是即时可见
- 核对地址：`https://cloud.tencent.com/developer/creator/article`

## 流水线

1. **正文只留一份真源**：`xxx.md`，标题用一级标题，其余全在正文里
2. **md → HTML**（`scripts/md2html.py`），去掉一级标题（标题单独填）
3. **起本地静态服务**，`tab create` 打开 HTML → `Ctrl+A` / `Ctrl+C`
4. **逐站**：navigate → 判登录态 → 填标题 → 编辑器 `focus()` → `Ctrl+V` → 核对正文字数
5. **补齐站点必填项**：分类、标签、文章来源、摘要
6. **发布一次**，立刻核对（toast / 跳转 / 管理页计数）
7. **记录链接**，写进分发台账

## 发布前检查表

- [ ] 这一版和已发的站**角度不同**（不是同一份正文）
- [ ] 标题 ≤ 平台上限（知乎 100 字、腾讯云 80 字）
- [ ] 正文里的图片是平台可访问的 URL，不是本地路径
- [ ] 标签是「下拉选中的」，不是「自定义关键词」
- [ ] 摘要/导语已填（不填会被截前 256 字）
- [ ] 发布按钮只点一次，点完先核对再决定是否重试
- [ ] 用户已经明确同意「发」，发布动作不是自作主张

## 附：脚本

- `scripts/md2html.py` —— 零依赖 md → HTML（标题/段落/代码块/表格/列表/引用/分隔线，支持 `--no-title`），给剪贴板粘贴用
- `scripts/serve.ps1` —— 在指定目录起 `http.server` 并把 URL 打出来（配合 bsk 的 `tab create`）

## 已知未解决

- 知乎草稿箱偶尔会留一份「已发布文章」的旧草稿，发布前建议先看草稿箱，避免以为没发而重复发
- 掘金文章 URL 不在 `/published` 页暴露，需要再从创作者中心或站内搜索取；发布后 5 分钟内站内搜索通常还搜不到
- 腾讯云审核时长不定（实测几分钟到几小时），审核未过时文章只在创作者中心可见
