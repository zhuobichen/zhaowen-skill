---
name: tailscale-smb-readonly
description: >-
  用 Tailscale + SMB 从一台 Windows 只读访问另一台 Windows 的文件夹（跨网段也行）。
  含本机实测出来的七个坑：盘符只能单字母（C1: 非法）、只跑服务不跑托盘客户端时
  tailscale CLI 一断开后端就被停掉、一次性 authkey 用过即失效、节点身份可从
  server-state.conf 备份恢复因而无需新密钥、up 报 "requires mentioning all non-default
  flags"、net use 传含特殊字符的密码会被 PowerShell 拆坏、映射空闲显示 Disconnected 属正常。
  当用户说「连另一台电脑的共享」「只读访问那台机器的文件」「tailscale 掉线/offline」
  「SMB 映射失败」「invalid key」时用。
user-invocable: true
---

# Tailscale + SMB 只读共享接入

把"另一台机器上的文件夹"变成本机几个只读盘符。适合**Windows ↔ Windows、跨网段、只要读**的场景。

## 什么时候用这个，什么时候不要

| 需求 | 方案 |
|---|---|
| Windows 到 Windows，只要读文件/看目录 | **本文：Tailscale + SMB**（系统原生、无额外服务端） |
| 需要跑命令、要 shell、要 rsync | SSH/SFTP（见文末对照） |
| 只在内网且已能直连 | 可以不走 Tailscale，直接 `\\IP\share` |
| 对方是 Linux | SMB 也行（samba），但 SSH 更自然 |

只读 = **账号层（ACL 只给读）+ 共享层（share 权限 Read）** 双保险，缺一层都能被绕过。

## 一分钟流程

供方（数据方）一次：
1. 装 Tailscale，登录，`tailscale status` 拿到自己 `100.x.x.x`
2. 建只读账号，把要共享的目录配成 `Read` 共享
3. 防火墙放行 445，**只对 tailnet 网段**：`100.64.0.0/10` + `fd7a:115c:a1e0::/48`
4. 生成 authkey 给对方（一次性即可）

求方（本机）一次：
```powershell
# 1) 入网（一次性密钥，成功后即刻失效，别重试）
& "$env:ProgramFiles\Tailscale\tailscale.exe" up --authkey=tskey-auth-XXXX --hostname=<名字> --accept-dns=false

# 2) 必须让托盘客户端常驻，否则后端会被停掉（见坑 2）
Start-Process "$env:ProgramFiles\Tailscale\tailscale-ipn.exe"

# 3) 验证
Test-NetConnection <供方100.x> -Port 445          # 必须 True

# 4) 映射（盘符必须是单字母！见坑 1）
New-SmbMapping -LocalPath 'X:' -RemotePath '\\100.x.x.x\RO_D' -UserName 'HOST\roview' -Password '***' -Persistent $true

# 5) 存凭据，重启后自动重连（否则重启要重输密码）
cmdkey /add:100.x.x.x /user:HOST\roview /pass:***
```

现成脚本：`scripts/join-and-mount.ps1`（带 `-DryRun` 只检查、`-Unmount` 一键卸载）。

## 七个坑（都是本机真踩过的）

| # | 现象 | 根因 | 处理 |
|---|---|---|---|
| 1 | `net use C1:` 报 "命令语法不正确"；`New-SmbMapping -LocalPath 'C1:'` 报 "device name is invalid" | **Windows 盘符只能是单个字母 A–Z**，`C1:` 不是盘符 | 用 `X:` `Y:` `Z:` 这类空闲字母；先查占用 |
| 2 | `tailscale up` 返回 0，但状态永远 `NoState`；网卡上只有 `169.254.x` | 只跑服务、没有常驻客户端时，**CLI 一断开后端就停**。日志：`client disconnected (…): disconnecting Tailscale` → `Tailscale is stopped` | 启动 `tailscale-ipn.exe`（托盘客户端）并给它加开机自启 |
| 3 | 首次能连，之后报 `invalid key: API key xxx not valid` | **一次性 authkey 已被那次成功加入消耗**，不是密钥坏了 | 不要重新要密钥；从状态备份恢复节点身份（见下） |
| 4 | `up` 报 `changing settings requires mentioning all non-default flags` | prefs 里有非默认项 | 照提示把非默认项全列上，或直接 `up --reset --authkey=…` |
| 5 | `net use X: \\…\share 密码 /user:…` 报语法错误 | 密码含 `!` 等字符，经 PowerShell 传参被拆坏 | 用 `New-SmbMapping -Password`（或 `cmd /c`） |
| 6 | `Get-SmbMapping` 显示 `Disconnected` | SMB 空闲超时断开，**属正常** | 访问一次路径即自动重连；别误判为故障 |
| 7 | 重启后盘符在但打不开 / 要密码 | 凭据没入库 | `cmdkey /add:<host> /user:… /pass:…` |

### 坑 3 的关键：不用新密钥也能救回来

设备此前加入过，节点身份就躺在状态文件里（base64 包装的 JSON）：

```powershell
# server-state.conf 里几个字段是 base64，解出来看
$j = Get-Content 'C:\ProgramData\Tailscale\server-state.conf' -Raw | ConvertFrom-Json
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($j._machinekey))   # privkey:...
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($j._profiles))      # 含节点密钥与 tailnet 名
```

恢复步骤：
1. `Stop-Service Tailscale`
2. 把备份的 `server-state.conf`（含 `_machinekey`）复制回去；`profile-data` 一并还原
3. `Start-Service Tailscale`，然后**不带 authkey** 执行：
   `tailscale up --accept-dns=false --hostname=<原主机名>`
4. 启动 `tailscale-ipn.exe`；几十秒内 tailnet 地址会**原样回来**（同一个节点，不是新注册）

判断"到底有没有成功加入过"：翻 `C:\ProgramData\Tailscale\Logs\tailscale-service-*.txt`，找

```
netmap: self: auth=machine-authorized [100.x.x.x/32 ...]     ← 加过的铁证
Switching ipn state Running -> NoState                        ← 就是这一步被踢下线的
```

## 只读必须验收（别只看状态 OK）

```powershell
# 读：能列
Get-ChildItem X:\ | Measure-Object | Select-Object Count

# 写：必须失败
try { Set-Content X:\__probe__.tmp 'x' -ErrorAction Stop; '写成功了，权限没配好' }
catch { '写入被拒 OK' }

# 删：必须失败
try { Remove-Item (Get-ChildItem Y:\ -File | Select-Object -First 1).FullName -ErrorAction Stop; '删成功了！' }
catch { '删除被拒 OK' }
```

三条都过才算只读。只做第 1 条是常见自欺。

## 带宽与礼貌

- 目录浏览几乎不耗带宽；**吃带宽的是批量复制**。
- SMB 没有 `scp -l` 那种限速开关，用 `robocopy` 的包间隔：
  ```cmd
  robocopy \\100.x.x.x\RO_D\某目录 D:\备份 /E /R:1 /W:1 /IPG:50
  ```
  `/IPG:50` ≈ 每个包间隔 50ms，能显著压下降速；不够慢就加大。
- 想硬限速：`New-NetQosPolicy -Name SmbLimit -AppPathNameMatchCondition "System" -ThrottleRateActionBitsPerSecond 2mb`（服务端按进程限，粗但有效）。
- 错峰：白天别拉大目录。

## 安全边界（必须跟用户讲清）

- **整盘只读 ≠ 安全**：`RO_C -> C:\` 会把 `C:\Windows`、`Program Files`、整个用户目录都暴露，连浏览器保存的密码、`.ssh`、`.dsh` 都可能在内。**能收窄就收窄到具体目录**。
- 凭据会**明文进凭据管理器**（`cmdkey`），共享密码常被写在聊天/文档里 —— 用后建议轮换。
- 撤销要清三处：映射（`Remove-SmbMapping`）、凭据（`cmdkey /delete:<host>`）、供方账号/共享。
- 共享层权限和 NTFS 权限是两套，**都要设成只读**，只改一处仍可能写入。

## 排障对照表

| 症状 | 先查 | 结论 |
|---|---|---|
| ping 100.x 不通 | `tailscale status`、`Get-NetIPAddress` 看 tailnet 网卡 | 没入网 / 后端被停（坑 2）/ 对方 offline |
| ping 通但 445 不通 | 对方防火墙是否只放 `100.64.0.0/10` | 端口没放行，或放行范围不含本机 |
| 映射报"device name invalid" | 盘符是否单字母 | 坑 1 |
| 映射报"不允许一个用户使用多个用户名" | `net use * /delete /y` 清旧连接 | 同 host 换过账号 |
| 重启后打不开 | `Get-SmbMapping` 是否 Disconnected、凭据是否在 | 坑 6 / 坑 7 |
| 写入竟然成功 | 账号是否在管理员组 | 管理员绕过 ACL |

## 与 SSH/SFTP 的分工

| | SMB（本文） | SSH/SFTP |
|---|---|---|
| Windows 供方成本 | 共享 + 权限，无额外服务 | 装 OpenSSH Server、改 sshd_config |
| 只读强制力 | ACL + share 双权限 | `ForceCommand internal-sftp` + ACL，更硬 |
| 能跑命令 | 否 | 是（除非也锁成 sftp-only） |
| 限速 | robocopy `/IPG`、QoS | `scp -l`、rsync `--bwlimit` |
| 适合 | 看/取文件 | 需要 shell 或同步 |

一句话：**只要读文件用 SMB，要动手才上 SSH。**
