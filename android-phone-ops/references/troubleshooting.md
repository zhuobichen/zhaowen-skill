# 踩坑记录（都是真机上撞出来的）

配套 MCP：`zhaowen-mcp/android-mcp`。这里只记"文档里没写、但会咬人"的那些。

## 中文输入

- `adb shell input text` 对非 ASCII **直接抛 NPE**（`InputShellCommand.sendText`，Android 16 实测），
  汉字一个都进不去。所以含中文时必须走设备侧的 ADBKeyboard 广播。
- **切完输入法，当前输入框会丢掉输入连接** —— 此时广播 `ADB_INPUT_B64` 返回 `result=0`（看着成功），
  但字哪儿也没去。必须先把输入框重新点一次再广播。工具已经内置这一步。
- **`result=0` 不代表字进去了**。真正的判据是回读输入框内容；工具返回里的「校验」一行就是这个。
- 设备侧输入法版本：**必须 v2.5-dev**。v2.4-dev 在 Android 16 上不可用。装它用
  `node scripts/setup-input-ime.mjs`（校验 sha256，grab 失败会重试 —— 本机 GitHub 约一半请求超时）。
- 剪贴板回退路径（宿主 `clip.exe` + `KEYCODE_PASTE`）**只对模拟器成立**：靠的是模拟器与宿主机剪贴板互通，
  真机没有这回事。

## 前台识别

- Android 16（API 36）上 `dumpsys activity activities` 里**没有 `mResumedActivity` 了**，
  换成了 `topResumedActivity=` / `ResumedActivity:`。只认老字段名会一直"识别不出前台"，
  而且**症状很安静**：`android_foreground` 返回一句"没能识别"，`dump_ui` 的 json 里 `foreground: null`。
- 前台识别不出来时，禁区里"限定 app"的规则会**保守拦下**（宁可多拦一次）。

## 等待与稳定

- 三个动效缩放（`window_animation_scale` 等）默认是 1.0，界面在动画中时截图和 dump 拿到的都是中间态。
  开工前 `android_prepare` 关掉。
- `android_wait_idle` 的判据是"连续两次 dump 节点完全一致"，比 sleep 靠谱；
  但**纯动画页面**（一直有东西在动）可能等不到稳定，那就退回 sleep + 截图。

## 手势

- AOSP 的 `input` **没有 doubletap 子命令**，双击只能连点两次（间隔 ~90ms）。
- 拖拽用 `input draganddrop`，不是 `swipe` —— 后者是"划过去"，前者才是按住再移动。
- 长按 = `swipe` 起终点相同 + 长 duration。工具里已经封装成 `android_long_press`。
  早年用 swipe 硬凑长按，在 QQ 聊天页上一次把整个窗口弄没了。

## 设备与网络

- 模拟器里 `ping` 不通**不代表没网**：QEMU 用户态网络挡 ICMP，应用照样能联网。
  要判连不连通，看"实际加载出来了什么"（图片/列表），别拿 ping 当判据。
- 判开机完成看 `getprop sys.boot_completed` 是不是 1，不要看 `offline/device`。
  `android_start_emulator` 的判据是"出现一台**新**设备"，所以本机已有设备在线时也不会误判超时。

## 禁区

- 配置在两处：随服务的 `guardrails.json` + 用户级 `~/.claude/android-guardrails.json`，后者追加。
- `denyTapText` 是**精确匹配**（归一化后），`denyTapTextContains` 才是包含匹配。
  用精确是刻意的：否则「空间」会误伤「存储空间」这类正常入口。
- dump / screenshot 也过禁区检查 —— 只拦"点进去"是不够的，人已经手工进去了、我还在读内容，那更糟。
- **诚实边界**：坐标点击、以及 app 内用 WebView 打开的页面，靠文字/包名不一定认得出来。
  配置能拦"点进去"和"已知地址"，真正的保证是"从不点进去"。
