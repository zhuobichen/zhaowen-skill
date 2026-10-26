---
name: tieba
description: 用真实浏览器（bsk）操控百度贴吧：进吧、看帖子、搜索吧或贴子、回帖、发主题帖、签到、看个人主页。当用户要在贴吧上浏览或操作内容时使用；只读操作可直接执行，发帖/回帖等动作必须先给用户确认。
version: 1.0.0
---

# 百度贴吧操作（真实浏览器驱动）

全部通过用户的真实浏览器（`browser-skill` / `bsk`）完成，登录态直接复用，不碰 Cookie。

## 前置

1. `browser-skill` 已就绪：`bsk status` 显示 `browsers connected` ≥ 1
2. 贴吧已登录。判定方法（本机实测）：
   - 打开 `https://tieba.baidu.com/home/main`，**返回个人主页**（标题 `<昵称>-百度贴吧`，页面里有 `ID <数字>`）即已登录
   - 未登录会被重定向到 `passport.baidu.com` 登录页
3. 没登录就 `bsk request-help` 让用户扫码/登录。

## 生命周期

```bash
bsk session start
bsk navigate <url> --session <id>
bsk snapshot --session <id>
bsk click @eN --session <id>            # 或 fill / press
bsk session stop <id>
```

CLI 细节见 `browser-skill` 手册。

## 必须知道的布局差异

Agent 窗口默认很窄（本机约 764px 宽），贴吧会自动切成**移动版布局**：

- 顶栏只有：`发贴` / `back old` / `down client` / `game center` / `message`
- **没有**桌面版的值班表、吧务入口、右侧签到面板
- 移动版和桌面版的 DOM 完全不同，**任何 selector 都不能跨布局复用**，一律以当次 snapshot 为准

需要桌面版控件时，改走 PC 路由（不是首页）：

```text
https://tieba.baidu.com/f?kw=<URL 编码后的吧名>
```

吧名含中文必须先编码（例如「孙笑川吧」→`%E5%AD%99%E7%AC%91%E5%B7%9D%E5%90%A7`）。

## 常用流程

### 进吧 / 看帖子列表

```bash
bsk navigate "https://tieba.baidu.com/f?kw=<encoded>" --session <id>
bsk snapshot --session <id>     # 帖子标题是 link，列表可能懒加载
```

### 看某个帖子

snapshot 里帖子标题是一个 link（常带 `回复/查看` 数字的兄弟节点）；click 进去后重新 snapshot。

### 搜索吧或贴子

首页顶部有 `searchbox "搜索吧或者贴子"`：`bsk fill` 关键词 → `bsk press Enter`。

### 回帖

1. 进入帖子页，滚到底部
2. snapshot 找到回复输入框（`textbox` / `contenteditable`）
3. `bsk fill` 写入内容
4. **把内容贴给用户确认**，再点「发表/回复」

### 发主题帖

1. 吧页点 `发贴`
2. 填标题 + 正文
3. **文案先确认**，再提交
4. 注意：新号/低等级号在部分吧有发帖限制或进入审核，提交后不一定立刻可见

## 坑

| 现象 | 处理 |
|---|---|
| DOM 结构和文档/上次不同 | 多半是移动版↔桌面版切换，重新 snapshot，别套旧 ref |
| 发帖弹验证码 | `bsk request-help`，不要重试硬发 |
| 提交成功但列表里看不到 | 可能进审核/被系统过滤，如实告诉用户，不要反复重发 |
| 中文吧名 404 | 忘了 URL 编码 |
| 被重定向到 passport | 登录态失效，让用户重新登录 |
| 页面很长 | 用 `bsk press PageDown` 逐步加载，别一次跳底 |

## 红线

- 不读 `document.cookie` / localStorage / 任何凭据
- 不刷帖、不批量回帖、不批量关注
- 发帖 / 回帖 / 私信等「发出去」的动作一律先确认
- 任务完成就 `bsk session stop`
