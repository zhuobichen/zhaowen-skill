---
name: zhihu
description: 用真实浏览器（bsk）操控知乎：打开页面、搜索、阅读问题与回答、点赞收藏关注、看热榜、发想法/写回答。当用户要在知乎上浏览或操作内容时使用；只读操作可直接执行，任何「发布/发送」类动作必须先给用户确认。
version: 1.0.0
---

# 知乎操作（真实浏览器驱动）

不依赖 API 或逆向，全部通过用户的真实浏览器（`browser-skill` / `bsk`）完成，登录态直接复用。

## 前置

1. `browser-skill` 已就绪：`bsk status` 显示 `browsers connected` ≥ 1
2. 知乎已登录。判定方法（本机实测）：
   - 标题形如 `(99+ 封私信 / 80 条消息) 首页 - 知乎`
   - 顶栏有「创作中心」「80 条通知」「410 条私信」这类入口，个人主页按钮是 `点击打开<昵称>的主页`
   - 未登录时顶栏只有「登录/注册」，任何操作都会弹登录框
3. 没登录就 `bsk request-help` 让用户扫码，**不要尝试代填账号密码**。

## 现成脚本（优先用）

`scripts/` 下已经封装好：

```powershell
.\scripts\zhihu.ps1 question -Id 2098047112466227298 [-Json] [-Full]
.\scripts\zhihu.ps1 hot [-Json]
.\scripts\zhihu.ps1 raw -Url 'https://...' -Out q.html
node scripts\zhihu.mjs question --file q.html    # 离线复算
```

原理：bsk 用你的登录态打开问题页 → `get-html` 落盘 → 解析页面内嵌的 `js-initialData`
（标题、回答数、首屏答案都在里面），**不需要 x-zse-96 签名，也不读 cookie**。
要求 `bsk` 在 PATH，或设环境变量 `BSK_EXE`。

限制：首屏只有 5 条回答，更多要走签名接口，暂未做。细节见 `scripts/README.md`。

## 生命周期（手工模式）

```bash
bsk session start                       # 记下 4 位会话 id
bsk navigate https://www.zhihu.com --session <id>
bsk snapshot --session <id>             # 拿 @eN 引用
bsk click @eN --session <id>            # 或 fill / press / select
bsk session stop <id>                   # 结束；空闲 5 分钟会被自动回收
```

CLI 细节（退出码、`--json`、`request-help` 参数）见 `browser-skill` 手册，这里只写知乎特有的部分。

## 常用流程

### 搜索

1. snapshot 找搜索框（`combobox "搜索"`，本机为 `@e10`）
2. `bsk fill @eN --value "<关键词>" --session <id>`
3. `bsk press Enter --session <id>` → `bsk wait-ms 800` → 重新 snapshot（结果页是 SPA，会二次渲染）

### 打开问题 / 回答

- 问题页形如 `zhihu.com/question/<id>`，答案形如 `.../answer/<id>`
- 长回答要滚动才加载完整；只读场景用
  `bsk evaluate --session <id> "document.querySelector('.RichText').innerText"` 取正文，
  比逐屏截图省得多；但**只用于读正文**，不要用来抓凭据。

### 点赞 / 收藏 / 喜欢

- 按钮在回答底部操作栏，snapshot 里通常是 `button "赞同"` / `button "收藏"`
- 点完**必须再 snapshot 确认状态变化**（文案变「已赞同」或计数 +1），不要假设成功

### 关注问题 / 关注用户

- 按钮文案「关注」→ 点后应变为「已关注」；同一按钮再点即取消关注

### 热榜

```bash
bsk navigate https://www.zhihu.com/hot --session <id>
bsk snapshot --session <id>             # 榜单条目直接可读
```

### 发想法 / 写回答（发布类，需确认）

1. 进编辑器：首页「分享此刻的想法...」或问题页「写回答」
2. `bsk fill` 写入正文
3. **把最终文案原样贴给用户，等明确同意**
4. 同意后再点「发布」

## 坑

| 现象 | 处理 |
|---|---|
| 弹登录框 | 停手，`bsk request-help` 让用户登录 |
| 验证码 / 滑块 | 同上，交给人 |
| 标题变了但内容没变 | SPA 未 commit，`bsk wait-ms 500` 后重新 snapshot |
| 引用失效 | 每次跳转后 `@eN` 全部作废，必须重新 snapshot |
| 无限滚动 | 要更多内容就 `bsk press PageDown` 再 snapshot，不要狂刷 |
| 搜索框占位词是推荐内容 | 占位词会变化，不要按文本匹配，用 `combobox` 角色定位 |

## 红线

- 不读 `document.cookie` / localStorage / 任何凭据
- 不批量私信、不刷赞、不自动关注陌生人
- 发布类动作（想法 / 回答 / 评论 / 私信）一律先确认再提交
- 任务完成就 `bsk session stop`，不要长时间占用用户的登录窗口
