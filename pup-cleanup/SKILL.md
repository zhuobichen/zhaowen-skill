---
name: pup-cleanup
description: 清理本机流氓软件/开机弹窗广告：找出推广告的"壳"、用官方卸载器卸、卸不动的走隔离；含自启动普查、登录后执行痕迹、按厂商识别推广家族。当用户说"开机弹窗广告""桌面弹出网游广告""帮我卸载XX""清理流氓软件""电脑老是弹东西"时使用。
user-invocable: true
---

# 流氓软件 / 开机弹窗广告清理

> 目标：**把"弹广告的那一窝"整族清掉**，而不是只删那个弹窗程序。
> 只处理用户本人机器上、用户明确说要清的东西。**永远先报告、再动手**。

## 一句话方法论

**弹窗只是症状，推广告的"壳"才是病。** 今天实测的完整链条长这样：

```
鲁大师系(LhpLionProtect/SuperApp/adblock_master_pop.exe)   ← 名字叫「广告拦截大师」，实际在弹广告
        ↓ 它在弹一个老网游的推广
keytask\keytaskpop_tzcq0807                               ← 你点了，于是装上了「天尊传奇」
xtp\xtp0908bzbz                                            ← 同一个游戏又被另一套壳装了一遍
```

- 只删 `天尊传奇` → 那个壳还在，还会接着推
- 只删 `adblock_master_pop.exe` → 已经装上的游戏还在
- **两头的壳都要清，而且要清全**：同一个东西会被**多个壳各装一遍**

## 工作流

### 第 1 步：普查自启动（别猜，全摊开）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\scan_autostart.ps1 -Out autostart.json
```

覆盖六处：`HKCU/HKLM 的 Run 与 RunOnce`（含 Wow6432Node）、**两个 Startup 文件夹**、
**登录触发的计划任务**、**自启动服务**、`Winlogon 的 Shell/Userinit`。每一条会带上
发布者/签名/安装日期 —— **签名有效不等于干净**（流氓软件大多有正规签名）。

### 第 2 步：看"登录后到底跑了什么"（最有信息量的一步）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\logon_trace.ps1
```

原理：`explorer.exe` 的启动时间 = **登录时刻**，然后列出 Prefetch 里在那之后 12 分钟内
被执行过的程序。开机弹窗的家族会在那一小段里**挤成一堆**，一眼就能看出来。

> ⚠️ **必须用登录时刻，不能用开机时刻。** 今天实测机器 02:31 开机、12:06 才登录，
> 拿"开机后 20 分钟"去筛 Prefetch，只筛出 5 条系统进程 —— 什么都看不到。

### 第 3 步：认厂商，按"家族"清

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\identify_pup.ps1 -Path "C:\Program Files (x86)\某个目录"
```

`data/known_pup_vendors.json` 里记了实测遇到的推广厂商与它们的"壳"目录名特征。
同一个厂商常有**一套壳 + 一堆马甲产品**（如奇鲁科技的 LuDaShi / LdsSysClean / LhpLionProtect /
WinOpt Assistant / Sys Boost / PC Optimizer … 共 20 个目录）。

### 第 4 步：卸 + 清

**先走官方卸载器**（从注册表 `UninstallString` 原样取参数，不要自己拼）：

```powershell
# 先 dry-run 看清单（默认就不执行）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall_pup.ps1 -Match "天尊|百战"

# 需要人点界面时用 -Sequential：一次只弹一个窗，等它真跑完再开下一个
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\uninstall_pup.ps1 -Match "WinQuick|WinEase" -Sequential -Execute
```

它会：列出所有匹配的卸载项 → 跑对应卸载器 → **逐条复查**（目录/注册表键/进程）→
给出没删干净的怎么移入隔离区。

`-Sequential` 的三个要点：等的是**安装目录空闲**而不是固定秒数（NSIS 会把自己复制到
`%TEMP%\~nsu?.tmp` 再跑，原目录早就空了）；`~nsu?.tmp` **还在**说明卸载器没干净收尾；
目录体积**前后没变**说明这个卸载器是空壳，直接去隔离，别跟它耗。

**卸载器不干活时**（实测遇到过：跑了、返回成功、文件一个没少），走隔离：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\quarantine.ps1 `
  -Paths "$env:APPDATA\xtp" -Shortcuts "$env:USERPROFILE\Desktop\某游戏.lnk" `
  -RegistryKeys "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\xtp_xtp0908bzbz"
```

**隔离而不是硬删**，并把注册表项 `reg export` 成 .reg 一并留下 —— 随时能还原。

## 今天实测踩到的坑（每条都花过时间）

| 坑 | 真相 |
|---|---|
| 计划任务的 `Settings.Hidden = $true` | **不抑制窗口**。三组对照实测窗口照弹。它的语义只是"在任务计划程序界面里不显示"。要真没窗口只能让动作不产生控制台（如用 `pythonw.exe`） |
| `.ps1` 里写中文**路径**（不只是中文输出） | 无 BOM UTF-8 被按 GBK 读，`维护` 变成 `缁存姢` —— 于是 `Move-Item` **静默搬到另一个目录**，脚本照报"已移动"、`Test-Path` 复查源也确实是 False，**一路全绿而东西搬错了地方**。规矩：脚本里**一个非 ASCII 字符都不许有**，路径一律由调用方以参数传入（命令行参数走 UTF-16，中文安全） |
| 把"删除目标"和"移动目标"写成同一个变量表达式 | 一次实测直接抹掉了整个隔离区（491 MB / 5426 项），回收站没有、卷影副本没有、恢复不了。**不可逆命令执行前必须先打印目标清单**（本 skill 的 `quarantine.ps1` 现在带自引用硬拦 + 每条目标带体积） |
| `[System.IO.Directory]::Delete` / `Remove-Item` | **都不进回收站**，误删没有兜底。移动用 `Move-Item`，别用"复制完再删源"的写法 |
| 守卫/判据自己写错变量 | `Where-Object` 里写成 `$x` 而不是 `$_`，配合 `$ErrorActionPreference='SilentlyContinue'` → 守卫**静默失效**。假守卫比没守卫更危险：写完必须**跑一个"应该被拦住"的用例**确认它真会拦 |
| 卸载器的作用域可能比产品名大 | 实测重橙的 `FlashCenterUninst.exe` 在卸 FlashCenter 的同时**把整个 Adobe Flash Player 34（ActiveX/NPAPI/PPAPI）+ Flash Helper Service 一起卸了**。跑之前先估边界，跑之后逐项复查，并在报告里如实说明实际范围 |
| NSIS 的 `/S` 静默参数 | **可能被无视**（自定义 GUI 不检查 Silent 模式）：实测重橙卸载器 `/S` 跑了、什么都没删。别硬上 GUI 卸载器赌运气；不能静默就直接手动清（停服务 → 删注册表项 → 移动目录），结果可预测得多 |
| 拿"新出现的进程数"当判据 | **会被自己这个 shell 开的进程淹掉**。要按**窗口标题/进程路径**精确匹配，并先跑对照组 |
| 用单字符中文去扫二进制找"有没有正文" | **不可用**：UTF-16LE 下随机 16 位落进 CJK 区间的概率约 32%，4MB 能刷出上百万假命中。要测中文，探针**够长**或直接用已知长串 |
| `Remove-Item` 带通配路径 | 会被沙箱静态检查拦（它把通配的注册表路径当成删除目标）。用 `reg delete` 或**精确到单个键** |
| 卸载器"成功"但没删 | **必须复查**：目录、注册表项、快捷方式、计划任务、残留进程，逐项看 |
| `.ps1` 里写中文 | 无 BOM 的 UTF-8 会被按 GBK 读 → **语法直接崩**。脚本一律**纯 ASCII**，中文数据放 `data/*.json` 用 `-Encoding UTF8` 读 |
| 体检/日志会不会提醒我 | **不会**。实测被 `Disable-ScheduledTask` 禁用的计划任务，`schtasks /query` 返回码仍是 0、`Last Result: 0`，体检照报"均在位且上次成功" |

## 不可逆操作的三条纪律（血换来的）

清理类操作**没有撤销键**：`Move-Item`、`Remove-Item`、`Directory::Delete`、`reg delete`
都不进回收站。所以：

1. **先打印，后执行。** 默认 dry-run，`-Execute` 才动手；输出里每条目标带**体积** ——
   体积不对是发现"要动的东西搞错了"的最后一道机会。
2. **源和目标是两个独立的表达式。** 不要图省事把同一个变量/表达式同时当来源和去向；
   工具自身要**硬拒绝**动自己的隔离区（`quarantine.ps1` 已内建，测过会拦）。
3. **东西只能往隔离区搬，不能删。** 搬进去了就别再动它 —— 合并隔离区、清理空壳目录
   这类"顺手整理"是最危险的时刻，因为那时你手上拿着最大的那份数据。

> 判断依据：隔离区是**唯一的还原路径**。丢了它，前面所有"随时能还原"的承诺全部作废。

## 判据要能证伪（做任何"清理有效"的结论前）

- **先跑对照组**：在"应该看得到"的情况下能不能看到？看不到就是检测器瞎了，不是没问题。
  （今天在"窗口检测"上正是靠这一步发现自己的检测器完全看不见窗口）
- **改动前后各测一次**，不要只测改后
- **"状态没更新"推不出"没干活"**：脚本的状态文件没动，可能是它早退了，也可能是那段时间本来没事
- 报告里把\"实测到的\"和\"推断的\"分开写

## 边界

- **不擅自卸载**。先列出匹配项（名称/发行者/路径）让用户勾，再动手；用户没点名的组件
  （如"清 FlashCenter"里的 Flash 播放器本体）**先问再动**
- **不点卸载器的按钮**：那类界面上"卸载"和"保留/修复"经常挨着，还可能**偷偷再装一个**。拉起卸载器后交给用户点
- **要弹 GUI 窗口前先说一声**。用户可能正在打游戏；而且一旦弹出来，后面发生什么就不再由你控制
  （实测：GUI 卸载器在无人干预的几分钟里把卸载跑完了，超出授权范围也没人拦得住）
- **报告里必须写清卸载器实际动了什么**，不只是你要求它动的那个 —— 连坐带走的东西要列出来，
  并说明**是否可还原**（隔离区里有 = 可还原；没有 = 永久删除，别含糊）
- 隔离区放仓库外、**路径纯 ASCII**（如 `D:\_quarantine_adware_<日期>\`），避开 `.ps1` 编码坑；
  报告里给出路径与体积
- 清完提示用户跑一次杀毒全盘扫描 —— 这类软件常有正规签名，杀软不一定拦
