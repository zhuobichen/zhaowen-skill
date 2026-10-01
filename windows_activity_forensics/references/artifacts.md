# 证据源字段与路径速查

## 文件 / 目录

| 证据 | 路径 | 时间语义 |
|---|---|---|
| Prefetch | `C:\Windows\Prefetch\*.pf` | `.pf` 文件 mtime = **最后一次运行** |
| UserAssist | `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist\{GUID}\Count` | 值名 ROT13 编码；last-run 在偏移 60 |
| 计划任务 | `Get-ScheduledTask` + `Get-ScheduledTaskInfo` | `LastRunTime` / `LastTaskResult` |
| 自启动 | HKCU/HKLM/WOW6432Node `...\CurrentVersion\Run`、两个 Startup 文件夹、Winlogon、服务表 | —— |
| 浏览器历史 | `%LOCALAPPDATA%\<浏览器>\User Data\<Profile>\History`（SQLite） | `visits.visit_time` = 1601 起**微秒** |
| 时间线 | `%LOCALAPPDATA%\ConnectedDevicesPlatform\*\ActivitiesCache.db` | `Activity.StartTime` = **Unix 秒** |
| 回收站 | `C:\$Recycle.Bin\<SID>\$I*` | 偏移 16 = 删除时间 FILETIME |
| 下载 | `%USERPROFILE%\Downloads`、`Desktop` | mtime |
| 腾讯登录 SDK | `%APPDATA%\Tencent\QQNTOpenSDK\<appid>\{log,sdk_db,msf}` | 按小时刷新的 `prelogin-log_YYYYMMDDHH.xlog` |
| WeGame 登录账号 | `%APPDATA%\Tencent\WeGame\login_pic\<QQ号>` | **文件名就是账号号** |
| QQ 聊天窗口 | `%APPDATA%\Microsoft\Windows\Recent\ntqq-notification-*fuin=<QQ号>*` | `.lnk` mtime ≈ 窗口打开时间 |
| ToDesk | `<安装目录>\Logs\*.log`、`config.ini` | 见下 |

## 二进制布局

### 回收站 `$I`（版本 2，Win10+）
```
0..7    uint64  版本 (=2)
8..15   uint64  原文件大小
16..23  uint64  删除时间 (FILETIME, UTC)
24..27  uint32  路径长度（UTF-16 字符数）
28..    路径（UTF-16LE, 以 \0 结尾）
```
版本 1 无长度字段，路径直接跟 24 开始、固定 260 字符。按版本分支读。

### Prefetch
```
0x00  uint32  版本 (23/26/30/31)
0x04  uint32  签名：'<I' 读得 0x41434353("SCCA")；Win11 24H2+ 读得 0x044D414D("MAM")
0x10  60 字节 可执行文件名（UTF-16LE）
```
旧格式 v30/v31 最近 8 次运行时间在尾部；**新 MAM 格式布局不同，暂无稳定解析**，改用文件 mtime。

### UserAssist 值（REG_BINARY，72 字节）
```
0..3    会话 ID
4..7    运行次数（很多 Win11 上恒为 0，不可用）
60..67  最后运行时间 (FILETIME, UTC)
```
值名是 ROT13 编码的路径或 PIDL。

### ToDesk `config.ini` 关键项
| 项 | 含义 |
|---|---|
| `clientId` | 本机设备号（别人要连必须知道它） |
| `LoginPhone` | 登录手机号 |
| `TfaForConn` | 连接双因素，0 = 未启用 |
| `IsFirstTimeConnect` | 是否首次连接 |
| `updatePassTime` | 临时密码刷新时间（运行中会滚动更新，**不代表有人连过**） |
| `FileCenterDownloadPath` | 文件传输落盘目录 |

### ToDesk 日志方向判据
| 行 | 方向 |
|---|---|
| `client recv connect request, myid=<本机> destid=<对端>` | 本机**主动连出** |
| `host recv connect request, myid=<本机> destid=<对端>` | 本机**被连入** |
| `mode_=1` / `mode_=0` | 分别对应 client / host |
| `TCP_VIDEO_HOST begin connect transfer server` | 被控端建立视频通道 |
| `<sessionXXXX>_YYYY_MM_DD.log` 出现 | 一次真实远程会话被拉起 |

## 安全日志登录类型

| 类型 | 含义 |
|---|---|
| 2 | 交互式（本地键盘） |
| 3 | 网络（共享/凭据） |
| 5 | 服务（噪声，数量最大） |
| 7 | 解锁 |
| 8 | 网络明文 |
| 10 | **远程桌面 (RDP)** |
| 11 | 缓存凭据 |

只看 2 / 3 / 8 / 10 即可；5 会淹没其余。类型 2 里 `DWM-*` / `UMFD-*` 是开机产生的系统账户，不算人为登录。

## 权限要求

- 读安全日志（4624/4688）需要**管理员**。
- `HKLM\SYSTEM\CurrentControlSet\Services\bam\State\UserSettings`（BAM）需要 **SYSTEM**，
  普通管理员读不到 —— 报告里别把"空"说成"没运行过"。
- SRUM（`C:\Windows\System32\sru\SRUDB.dat`）被 DPS 服务占用，未实现；它是"按小时的应用使用"最佳来源，
  想补需要 ESE 解析。**目前是已知缺口**。
