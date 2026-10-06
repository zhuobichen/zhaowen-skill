---
name: agent-dialog_management
description: >
  管理电脑上所有智能体（Claude Code + Codex）的对话记录：统一列出、全文搜索找回
  遗忘/关闭的对话、查看内容、导出 Markdown、备注收藏、一键恢复（新开终端窗口
  继续之前的会话）、查看正在运行的对话。当用户说"我的对话""找到之前那个对话"
  "恢复某次对话""正在运行的对话""看看智能体聊了什么""导出这次对话"等涉及
  历史/进行中对话的查找/管理/恢复场景时使用。
user-invocable: true
---

# 智能体对话管理（agent-dialog_management）

统一管理本机 **Claude Code** 与 **Codex** 的所有对话。核心价值：对话散落在多个目录，
用户记不清哪个会话做了什么，本 skill 帮用户**找到 → 查看 → 恢复**，并支持
备注/收藏/导出。

## 数据源（只读，不联网）

| 来源 | 位置 | 说明 |
|---|---|---|
| Claude Code | `~/.claude/projects/<项目>/*.jsonl` | 会话 ID = 文件名 |
| Codex | `~/.codex/sessions/<Y>/<M>/<D>/rollout-*.jsonl` | 含 Desktop/CLI 会话 |
| Codex 归档 | `~/.codex/archived_sessions/` | 已归档会话，list 中标记 `[归档]` |
| 早期输入历史 | `~/.claude/history.jsonl` | **2025-11 至今**的全部输入记录（早期完整对话已清理，仅剩此处痕迹） |
| 备注/收藏 | `~/.claude/skills/agent-dialog_management/state/notes.json` | skill 自身维护 |

每个会话记录：ID、来源（C=Claude / X=Codex）、真实工作目录、时间、标题（自动取
AI 标题或第一条用户消息）、归档状态。

## 核心命令

脚本路径（在 Bash 中执行，`~` 会自动展开）：

```bash
# 先定义（建议每次执行前定义，避免拼错）
DIALOG="$HOME/.claude/skills/agent-dialog_management/scripts/agent_dialog.py"
# 或直接写绝对路径：
#   C:\Users\<你的用户名>\.claude\skills\agent-dialog_management\scripts\agent_dialog.py
```

| 用户意图 | 执行命令 |
|---|---|
| 列出全部对话 | `python <脚本> list [--agent claude\|codex] [--limit 20]` |
| 搜索找回 | `python <脚本> search <关键词>` |
| 查看内容 | 先 `search`/`list` 拿到短 ID → `python <脚本> show <短ID> [--full]` |
| 恢复对话 | `python <脚本> resume-cmd <短ID>` → 执行输出的命令 |
| 导出 | `python <脚本> export <短ID> --out <路径.md>` |
| 备注 | `python <脚本> note <短ID> <文本>` |
| 收藏/取消 | `python <脚本> star <短ID>` |
| 命名对话 | `python <脚本> rename <短ID> <名字>` |
| 列出有备注的 | `python <脚本> notes` |
| 查看正在运行的对话 | `python <脚本> running [--minutes 30]` |
| 搜索早期输入历史 | `python <脚本> hist <关键词> [--limit 30]` |
| 启动监控面板 | `python <脚本> serve [--port 8765] [--no-browser]` |
| 关闭所有 Claude 会话 | `python <脚本> shutdown [--yes]`（更新 claude 后重启用，输出恢复清单） |
| 查看数据源 | `python <脚本> paths` |

**ID 支持前缀匹配**：`show 79b26d95` 或完整 UUID 均可。

## 工作流

### 1. 列出/概览
```bash
python <脚本> list --limit 20
```
输出格式：`[C] 短ID 时间 项目 ⭐[归档]` + 缩进标题。Claude Code 列表、Codex 列表
混排按时间倒序。

### 2. 找回"遗忘"的对话
用户描述模糊时先 `search` 关键词：
```bash
python <脚本> search 邮箱
```
返回命中对话 + 上下文片段。用户确认后 `show` 看全文。

### 3. 恢复对话（在当前 Windows Terminal 新标签）
```bash
python <脚本> resume-cmd <短ID>
```
脚本会输出一条命令（基于 `wt.exe` + `-EncodedCommand`）：
`"C:\Users\<用户>\AppData\Local\Microsoft\WindowsApps\wt.exe" -w 0 new-tab -d "<cwd>" powershell -NoExit -EncodedCommand <base64>`
编码内容 = `Remove-Item Env:CLAUDE_CODE_CHILD_SESSION; claude --dangerously-skip-permissions --resume <id>`
**执行这条输出**，会在**当前 Windows Terminal 窗口**新开标签页恢复该会话（不弹独立窗口）。
codex 会话用 `codex resume <id>`。

> 经验（2026-08-10）：
> - 用 `wt -w 0 new-tab -d <目录>` 开当前窗口新标签；**不要**用 `Start-Process powershell`（弹独立系统窗口）
> - 启动前必须 `Remove-Item Env:CLAUDE_CODE_CHILD_SESSION`——否则 claude 继承当前会话的
>   "子会话"标记，显示 "Transcript saving is off"，**不保存对话记录**
> - 命令用 `-EncodedCommand`（base64）：**分号在 wt `-Command` 参数里会被拆开**导致 claude 不启动
> - resume 是交互式命令，不能在当前 Claude Code 会话内直接运行

### 3.4 监控面板（多终端同时看）
```bash
python <脚本> serve          # 启动浏览器面板 http://localhost:8765
```
一个页面同时展示所有活跃会话（Claude + Codex）：标题/项目/最近对话（3 秒自动刷新）、
进程统计。**可向任一会话直接发指令**（卡片底部输入框）——内部用 `claude --resume <id> -p`
或 `codex exec resume <id>` 非交互恢复执行，回复自动写回会话，面板刷新可见。
指令处理较慢（取决于模型），面板会显示"AI 处理中…"。端口占用时用 `--port` 换。

### 3.5 搜索早期输入历史（history）
2025-11 ~ 2026-05 的完整对话已被清理，但 `history.jsonl` 保留了你当时**每一次输入**（命令/提问/粘贴）。
用户说"我早期做过 XX"时：
```bash
python <脚本> hist downscaler      # 找回 207 条提到 Downscaler 的历史输入
python <脚本> hist 惠州             # 找回惠州项目相关输入（含 2025-12 的记录）
```
每条结果带：时间 / 项目 / sessionId / 输入内容。若 sessionId 恰好对应 6 月后的完整对话，
可再用 `show`/`resume` 深入。

### 4. 备注 / 收藏
给重要对话加备注便于日后找回：
```bash
python <脚本> note 79b26d95 "简历项目整理，已完成初稿"
python <脚本> star 79b26d95        # 切换收藏
python <脚本> notes                # 列出所有带备注/收藏的
```

### 5. 导出 Markdown
```bash
python <脚本> export 79b26d95 --out "E:/CodeProject/notes/对话.md"
```

### 6. 命名对话（让对话认得出）

```bash
python <脚本> rename 79b26d95 "简历项目整理"
```

一个会话的名字有**两层存储**，本命令同时写两处：

| 记录 | 作用 |
|---|---|
| `{"type":"custom-title","customTitle":...}` | `/resume` 选择器显示的名字；`claude --resume <名字>` 用它定位 |
| `{"type":"agent-name","agentName":...}` | 会话**自身**的名字，重启时采用（同时体现在 `~/.claude/sessions/<pid>.json`） |

> 实测（2026-10，Claude Code 2.1.288 / 2.1.291）：
>
> - **终端标签标题改不动**：运行中的会话把名字放在内存里（只写不读），改转录、改 session 文件都不会让标签变。
>   要让标签立刻变，只能**在那个会话的窗口里敲 `/rename <名字>`**。
> - **不保证永久**：运行中的会话会周期性重写自己的 `agent-name`；部分会话（重启后 `nameSource` 变回 `auto`）
>   会在启动时**自动重新命名**，把写入覆盖掉。实测 3 个会话里 2 个成功、1 个被覆盖。
> - **想钉住标签标题**：开标签时用
>   `wt -w new new-tab -d <目录> --title "<名字>" --suppressApplicationTitle powershell -NoExit -EncodedCommand <b64>`
>   —— `--suppressApplicationTitle` 之后，程序自己发的改名转义序列压不过它（WT 1.24 实测有效）。
> - 会话内还有：`/rename`（改名，别名 `/name`）、`/color`（给输入栏上色）——官方对"同时开多个会话"的推荐组合；
>   启动时命名用 `claude -n <名字>`。

### 7. 会话之间发消息（跨会话 SendMessage）

Claude Code 自带会话间消息通道：先列本机其它会话，再点对点发。

| 动作 | 工具 |
|---|---|
| 列出本机其它会话（名字/状态/启动时间） | `ListAgents` |
| 给某个会话发消息 | `SendMessage`（`to` 填会话名） |

**默认行为：按「权限模式对等」送达** —— 发送方与接收方的权限模式类别相同（bypass↔bypass 或 prompting↔prompting）才自动投递；
不一致就**扣住等对方批准**；发送方没声明模式而接收方是 bypass 时也扣住。

用 settings 里的 `crossSessionInbound` 改这个行为（用户级 `~/.claude/settings.json`，对全机生效）：

| 值 | 行为 |
|---|---|
| `"accept"` | **收到就直接投递**，不弹批准（显式值总是优先于默认的对等规则） |
| `"hold"` | 扣住等人工审阅，不让 Claude 自动行动 |
| `"refuse"` | 本会话直接拒收 |

> 请注意几点（2026-10 实测 / 二进制核实）：
> - **被扣住不等于送达**。会收到一条 `[Cross-session delivery notice]`（held / released / denied / expired 各一条）；
>   **别把接口返回的 `success: true` 当成对方已收到** —— 那只表示消息进了对方收件箱。
> - 企业 managed 设置或**仓库级设置**可以把它收紧成 `hold`，且用户自己的 `accept` 压不过（"a repo may only tighten"）。
>   managed 现在不存在，但要知道有这条约束。
> - 与**监控面板的「发指令」是两套机制**：面板走 `claude --resume <id> -p`，**另起一个进程**，不受权限模式约束；
>   `crossSessionInbound` 只管会话间消息通道那条路。
> - 会话内可 `/color` 给输入栏上色、`/rename` 改名，多个会话一眼区分（官方推荐组合）。
> - **2026-10-06 双向闭环已实测**：设了 `accept` 后，bypass 会话发给 prompting 会话、对方回信到 bypass 会话，**两向都免批准直接送达**；
>   回信带 `from-mode="prompting"`（可据此看出对方的权限模式类别）。
> - 走网关（`ANTHROPIC_BASE_URL` 指向中转）的会话启动时会弹一条 auto 模式分类器计费的提示框，**会挡住消息投递**；
>   按 Enter 即写入 `~/.claude.json` 的 `autoModeClassifierBillingNoticeAcknowledgedAt`，之后不再弹。

## 边界与约定

- **默认只读用户数据**：扫描/读取 JSONL 从不修改。skill 自身的写入只有两处 —— `state/notes.json`（备注/收藏），以及 `rename` 命令（按你明确要求往转录追加命名记录）。
- **Codex 会话管理**（归档/删除）用官方命令：`codex archive <id>` / `codex delete <id>`，
  skill 不做绕过。

### 为什么 Claude Code 侧没有归档/删除（2026-10-02 查证）

用户问「能不能归档或删除 Claude Code 对话」。查证结论：**两边都没有这个能力，
而且原因是产品设计不同，不是 skill 偷懒。**

证据来自两边二进制的字符串（不是文档推测）：

**Codex —— 归档是一等公民**
```
"Archive this session now"
"This will archive the current session and exit Codex"
archived_at INTEGER NOT NULL DEFAULT ...    ← 数据库字段
unarchive ×8                                 ← 可撤销
```
所以 `codex archive` / `codex delete` 是官方命令，本 skill 只需转告。

**Claude Code —— 本地会话只有「保留期」，没有归档态**
```
cleanupPeriodDays  ×25
"cleanupPeriodDays must be at least 1. To keep transcripts for a long time,
 set a large number (e.g. 3650 for ~10 years)."
"Transcript retention cleanup is paused until the settings errors above are fixed"
```

> ⚠️ 容易误判：Claude Code 二进制里**确实有** `archiveSession()` / `unarchiveSession()` /
> `fleet_view_archive_session` / `POST /v1/sessions/<id>/archive` —— 但那些全是
> **remote-bridge / fleet**（远程控制与后台智能体会话）的，**不碰本地对话记录**。
> 只看到 "archive" 就下结论「Claude Code 也有归档」是错的。

**设计取向的区别**（这句是解读，不是事实）：

| | Codex | Claude Code |
|---|---|---|
| 本地会话状态 | 「在用」/「已归档」**两态** | 只有「在」，**没有第二态** |
| 到期怎么办 | 你自己决定收不收 | **按保留期自动删**（默认 30 天）|
| 想长留 | 归档 | 把 `cleanupPeriodDays` 设大 |

可以理解为：Codex 把本地会话当**用户资产**（给你「收起来」的动作），
Claude Code 把它当**缓存**（用保留期策略管理）。

**对本 skill 的影响**：Claude Code 侧的「收藏」只是 `notes.json` 里一个标记，
**不是归档** —— 文件仍在原地，仍会被保留期清掉。要长留必须改 `cleanupPeriodDays`。
- **标题兜底**：无 AI 标题时取第一条用户消息，无消息则显示 `(无标题)`。
- **running 判定**：活跃 = 最近 N 分钟有写入且未归档。Codex 后台 app-server 会 touch
  旧会话文件造成误报，因此当 Codex 无交互进程时，其"活跃"记录会标注为后台服务活动。
- **性能**：99 个对话全文搜索约 1~3 秒；list 秒回。
- 本 skill 用本地 git 管理（`~/.claude/skills/agent-dialog_management/` 内 `git init`），
  只 commit 不 push。
