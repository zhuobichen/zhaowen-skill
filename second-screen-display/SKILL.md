---
name: second-screen-display
description: >
  把闲置设备做成“只读副屏”：旧 Android 手机、电子墨水屏、或接在电脑上的第二块显示器，
  统一由本机一个 HTTP 服务喂画面（面板 / 远端桌面 / 电子书），设备端只负责显示。
  当用户要求：把旧手机/平板/墨水屏当第二块屏、把远端桌面（ToDesk/向日葵）投到副屏、
  做一块“只看不点”的状态屏、给副屏限制鼠标、屏幕上显示 API 额度/系统指标/日志、
  或排查“副屏识别到但全黑 / 截屏全黑 / 拔插线后画面停住”时使用。
  涵盖：USB 反向隧道（adb reverse）、局域网 HTTP 图片流、mDNS 固定名字、
  PrintWindow 抓窗口（含最小化即黑图的坑）、DXGI 桌面复制在混合显卡下的假黑、
  安卓 MIUI 安装/输入注入门禁、电子墨水屏的转载与屏保路径、CursorKeeper 锁鼠标。
---

# 只读副屏（Second Screen as a Read-Only Display）

> 目标形态：**副屏只显示，不参与操作**。设备端不需要装 App（能开网页即可），
> 或者哪怕不能开网页，也能通过“推图片”看到内容。

## 什么时候用这个 skill

- 想把一台**旧手机 / 平板**当第二块屏，又不想装 spacedesk 之类的客户端
- 想把 **ToDesk / 远程桌面** 的画面投到另一块屏（本机操作、副屏只看）
- 想要一块**常亮的状态屏**：CPU/GPU/磁盘/网络/API 余额/待办
- 已经把第二块显示器接上了，但**识别到、却全黑**
- 拔插数据线、换 Wi-Fi 之后**画面停住、不再刷新**

## 整体架构

```
[ 本机 Windows ]
   stream.py ── HTTP :8080 ──┬─ /panel      彩色仪表盘（服务端 Pillow 画成图）
                             ├─ /eink       墨水屏版（黑白大字）
                             ├─ /remote     远端桌面窗口抓取（PrintWindow）
                             ├─ /           本机桌面镜像
                             └─ /clients    最近来访 IP + 请求路径（排障用）

   设备端（三选一）：
   A. 手机/平板/墨水屏浏览器 → 直接开上面的网址（推荐；页面自带刷新与全屏手势）
   B. 只支持 MTP 的设备     → 走文件投递：生成的 PNG / EPUB 推到设备目录
   C. 实体副屏（HDMI/DP）   → 浏览器窗口铺在副屏 + 鼠标锁在主屏
```

## 关键决策：为什么面板是“一张图”而不是 HTML 页面

HTML + CSS 在手机上能跑，但**老浏览器 / 墨水屏 / 高 DPI 副屏**上会翻车：

1. Chrome 对超出视口的页面做 shrink-to-fit，字号一改，缩放比例就变，布局永远对不齐
2. 用 `transform: rotate(90deg)` 伪造横屏时，`vh/vw` 在旋转后的取值不稳定
3. 某些国产浏览器对 `http://host.local` 的 mDNS 解析直接失败，报“网页不存在”

所以最终方案是**服务端用 Pillow 直接画位图**，设备端只有一个 `<img>`。
布局由服务端精确控制，浏览器再没有发挥空间。

## 快速开始

```bash
pip install mss pillow        # 基础
pip install dxcam zeroconf    # 可选：DXGI 抓屏、mDNS 广播

python scripts/stream.py      # 服务起来，监听 0.0.0.0:8080
```

设备端打开 `http://<本机IP>:8080/panel`。

## 设备接入的三条路

### A. USB 反向隧道（最稳，不需要 Wi-Fi）

```bash
adb reverse tcp:8080 tcp:8080
adb shell am start -a android.intent.action.VIEW -d http://127.0.0.1:8080/panel
```

- 手机访问 `127.0.0.1:8080` 的流量经 USB 到电脑，**完全不依赖网络**
- **拔线即失效**，需要在插回时重建 → 用 `scripts/usb_reverse.py` 守护（每 5 秒扫设备）
- 好处：不受校园网/公司网“同 SSID 不同子网、单向阻断”的影响

### B. 局域网 HTTP（换设备方便，但要看网络）

- 同一子网才稳；**相同 SSID ≠ 相同子网**，校园网常把设备分到不同 VLAN 且互访被 ACL 挡
- 排障顺序：`/clients` 有没有对端 IP → 防火墙丢包日志 → ARP 表看是不是同一段
- 名字想固定用 mDNS：`scripts/mdns_publish.py` 广播 `dsh.local`（但不保证目标浏览器支持 `.local`）

### C. 文件投递（设备没有浏览器也能用）

- 电子墨水屏：把 PNG 推进 `/iReader/skins/本地屏保/`，在设备设置里选为屏保
- 长文阅读：`scripts/reading.py` 把 Markdown/TXT 转成适合墨水屏排版的 EPUB，推进 `i-transfer`

## 实体副屏（HDMI/DP）作为“只读显示”

```bash
# 1) 桌面复制抓远端窗口 → 服务端出图（PrintWindow，见下）
# 2) 副屏开一个浏览器窗口铺满，指向 /remote
# 3) 鼠标锁在主屏：CursorKeeper（开源）
```

- 窗口定位**必须 DPI 感知**，否则 `SetWindowPos` 的坐标会被系统缩放，窗口跑到屏幕外
- 浏览器的 `--window-position` 同样受 DPI 影响，别指望命令行参数摆准，用 API 摆

## 五个必踩的坑（按严重程度）

### 1. `PrintWindow` 抓最小化窗口 = 黑图
远端监控类软件（ToDesk/向日葵）窗口一旦最小化，`PrintWindow` 只能拿到黑框。
**推导出的两条硬规则**：
- 要持续抓图，就**不能最小化**那个窗口（本 skill 的守护会把它拉回来）
- 抓图失败时**不要把黑图当真实画面发出去**，要么保留上一帧，要么明确报错

### 2. 混合显卡下“副屏全黑”
核显负责输出、独显负责渲染时，显示器能被识别、分辨率也对，但画面全黑。
- 先排查是不是**抓屏假黑**：`mss`(GDI) 与 `dxcam`(DXGI) 各抓一次
- 两个都黑 → 是真没渲染；把线插到**独显**口几乎总能解决
- 次选：按“先更新核显驱动、再更新独显驱动”的顺序

### 3. 安卓 MIUI 的四个门禁
`USB 安装`、`USB 调试（安全设置）` 关着时：`adb install` 报 `USER_RESTRICTED`，
`adb shell input` 报 `INJECT_EVENTS`。没有 SIM + 小米账号这两个开关根本打不开。
**除非必要，不要依赖 adb 输入注入**，尽量用“网页自己会做的事”。

### 4. 息屏 → Wi-Fi 断 → 页面停住
手机不插电时 Doze 会掐断网络，浏览器停止刷新。
- 硬件层：`settings get global stay_on_while_plugged_in`（插电常亮）
- 网页层：Screen Wake Lock（`navigator.wakeLock.request('screen')`）；
  `127.0.0.1` 属于安全上下文，所以 **USB 隧道模式下这个 API 才可靠**
- 守护层：定时检查前台应用，被切走就重新拉起页面

### 5. 鼠标误滑到副屏
自写 `ClipCursor` 脚本时**必须 DPI 感知**（`SetProcessDpiAwareness(2)`），
否则 `GetSystemMetrics` 返回逻辑尺寸（如 1707×960），会把鼠标关进错误矩形，
表现为**桌面点不动、点哪都没反应**。
直接上成熟工具 `CursorKeeper`（开源）更省事；必须自写时只在“按住某键”期间裁剪。

## 排障清单

| 现象 | 先查什么 |
| --- | --- |
| 页面打不开（DNS 类报错） | `/clients` 有没有对端 IP；`.local` 是否被浏览器解析 |
| 页面打不开（连接被拒） | 服务是否在监听 `0.0.0.0`；防火墙是否放行该端口 |
| 有画面但不刷新 | 设备是否息屏/断网；Wake Lock 是否拿到；`/clients` 的 age 是否在涨 |
| 副屏全黑但窗口有内容 | 先分“抓屏假黑”和“真没渲染”，用两种抓屏 API 对比 |
| 抓到的永远是黑图 | 被抓的窗口是否最小化 |
| 桌面点不动 | 是否有残留的 `ClipCursor`；是否有不可见的顶层窗口在吞点击（`WindowFromPoint` 定位） |

## 相关脚本

| 脚本 | 作用 |
| --- | --- |
| `scripts/stream.py` | 服务主体：面板 / 墨水屏版 / 远端抓取 / 额度 / 来访日志 |
| `scripts/usb_reverse.py` | adb reverse 守护：插上即建隧道、把页面拉回前台 |
| `scripts/remote_screen.py` | 副屏窗口定位 + 被监控窗口防最小化 |
| `scripts/reading.py` | Markdown/TXT → 墨水屏排版 EPUB |
| `scripts/make_screensaver.py` | 生成墨水屏竖屏图（仪表盘 / 远端快照） |
| `scripts/check_m2.py` | 副屏自检：抓图取亮度极值，判断是否全黑 |
| `scripts/upload_ireader.py` | 向 iReader 的 WiFi 传书接口（`/test.php?action=addBook`）上传文件 |

排障细节与实测数据见 [`references/副屏方案.md`](references/副屏方案.md)。
