---
name: android-phone-ops
description: 用 android MCP 操作本机那台安卓模拟器（或真机）：构建装包、点界面、读层级、截图、输入中文、看日志；也包括"帮我在手机上干件事"这类委托。当用户说「操作模拟器」「手机上点一下」「装个 App 试试」「给某人发条消息」「看看手机上现在什么界面」「跑一下这个 App」时使用。
metadata:
  type: skill
---

# 用 AI 操作手机

配套 MCP：`android`（28 个工具）。工具清单和参数不在这里重复 —— 那个在
`zhaowen-mcp/android-mcp/README.md`。**本 skill 只写三样它给不了的东西：流程、判据、纪律。**

## 一、开工三步（别跳第一步）

1. `android_status` —— 看 adb / 设备 / **当前生效的禁区规则**。没有设备就先 `android_start_emulator`。
2. `android_prepare` —— 关三个动效缩放 + 亮屏解锁。**这一步能省掉后面一大串 sleep**：
   界面在动画中时，你截图和取层级拿到的都是中间态。
3. 之后每次跳转/加载完，用 `android_wait_idle` 而不是 sleep。

多设备时**必须显式传 `serial`** —— 工具宁可报错也不会替你猜（猜错就是把操作打到别人手机上）。

## 二、看屏幕：dump 优先，截图补充

- 要"找按钮 / 判断某元素在不在 / 拿坐标" → `android_dump_ui`（紧凑、省 token、坐标现成）。
- 要"知道长什么样" → `android_screenshot`（`inline=true` 能省掉你再去读文件那一轮）。
- **Canvas / Surface / WebView 内部** dump 不出来，只能截图 + 坐标点。
- `dump_ui` 的 `format="json"` 适合程序消费，也顺手给出当前前台 activity。

## 三、操作：能按文字就别按坐标

- `android_tap(text="登录")` 会自动定位；文字落在不可点的 `TextView` 上时它会往上找可点的祖先。
- 命中多个会列出来让你消歧，别硬猜 —— 用更精确的 text 或 `first=true`。
- 长按 / 双击 / 拖拽分别是 `android_long_press` / `android_double_tap` / `android_drag`
  （别再用 "swipe 起终点相同" 硬凑长按了）。
- **等待模式**：`android_wait_for_text` 等出现、`gone=true` 等消失、`android_wait_idle` 等稳定。
  `sleep` 只在"等一个设备侧计时器"这种没办法的情况下用，而且要在心里记着它不可靠。

## 四、输入中文

`android_input_text` 会自动分流，**你不用管走哪条路**，但要会读它的返回：

- 返回里有「走法」一行，写的是这次实际用了哪条通道；
- 有「校验」一行 —— **以回读为准**，广播"发成功"不等于字进去了；
- 走 ADBKeyboard 时工具会自己切输入法再切回来，不用你管；没装那个输入法会退到剪贴板路径，
  并标注"**只对模拟器有效**"（真机不行）。

**最常见的一次失败原因**：目标输入框没有焦点。工具会尽量自己重新聚焦，但如果它提示
"没识别到有焦点的输入框"，就用 `android_tap` 点一下那个框，然后再输入。

## 五、禁区：这是配置说了算，不是我记性好

`android-mcp/guardrails.json` + 用户级 `~/.claude/android-guardrails.json`。
命中会在工具层**直接拒执行**，并报出是哪条规则。

- 看到「已被禁区规则拦下」：**停手**，把规则名和原因告诉用户，让他决定。
  **不要试图绕过**（换个说法、拆成两步、用 `android_shell` 直连）—— 那等于把用户设的边界当建议。
- 内置那条 `qq-qzone` 是用户明确要求的：**QQ / 微信里的「空间」一律不碰**，包括"看"。
- 规则里限定 app 的条目（例如只在 QQ/微信内生效），在前台识别不出来时会**保守拦下** ——
  这是故意的，不是 bug。
- 要改规则：找用户确认后再改配置文件，改完要重连 MCP 才生效。`android_status` 里能看到当前规则。

## 六、纪律（比技巧重要）

- **不代登录**。要账号密码、验证码、扫码、短信确认的，停下来交给用户。
- **发送/删除/支付类动作，先确认再执行**。委托里没明说"发什么"就别自己编内容发出去。
- **聊天记录、联系人、空间这类内容不外带**：不贴进公开文件、不写进别人能看到的地方。
- 用户说"你看看手机上有什么" ≠ 授权你翻私人内容。他要是立了规矩（比如某人的空间不许看），
  那条规矩优先于"任务需要"。

## 七、装一个 App

本机的路子（应用商店详情页多是 SPA，抓不到直链，这条更稳）：

1. 豌豆荚：`https://www.wandoujia.com/apps/<数字id>/download/dot?ch=detail_normal_dl`
   会 302 到 `ucdl.25pp.com` 上的真 `.apk`；本机 `curl.exe -L -o <文件>` 下下来；
2. 校验是 PK 头（zip/apk），记下 sha256；
3. `android_install` 推上去（`grant_permissions=true` 一次授全权限）；
4. `android_launch_app` 起来，`android_wait_idle` 等它稳定。

**ABI 注意**：这台模拟器是 x86_64 但带 arm64 翻译层，所以只带 arm64 的包也能装能跑；
反过来 **32 位包装不上**（`abilist32` 为空）。

## 八、排障：症状 → 先查什么

| 症状 | 先查 |
|------|------|
| 「当前没有在线设备」 | 模拟器是不是被关了（`android_status`）；起来后等 `sys.boot_completed=1` |
| 「没识别到有焦点的输入框」 | 用 `android_tap` 点一下输入框再输入 |
| 「文字『X』命中 N 个节点」 | 换更精确的 text，或 `first=true`，别猜 |
| dump 出来是空的 | 该页可能是 Canvas/Surface 自绘或 WebView，改用截图 + 坐标 |
| 截图/层级拿到的是半截 | 动效没关 → `android_prepare`；跳转后先 `android_wait_idle` |
| 点不动/点错位置 | `android_foreground` 看是不是还在你以为的那一页 |
| 中文只进去一半或全没进 | 看 `android_input_text` 返回里的「走法」和「校验」两行 |

更细的踩坑记录见 [references/troubleshooting.md](references/troubleshooting.md)。
