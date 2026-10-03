---
name: claude-code-message
description: 向本机正在运行的 Claude Code 会话发送消息并获取回复——列出活跃会话、选择目标、注入消息、读取最新对话
version: 1.1.0
triggers:
  - "给claude发消息"
  - "给claude code发消息"
  - "向claude会话发消息"
  - "给另一个claude发消息"
  - "跨会话发消息"
  - "claude code message"
  - "send to claude"
  - "给那个会话发消息"
  - "让另一个claude做"
---

# Claude Code 跨会话发消息

> 通过 `claude --resume --print` 向本机任意已有会话注入消息，加载完整上下文后获取回复。

---

## 一、原理

Claude Code 的每个会话对应一个 `sessionId`，对话历史存储在 `~/.claude/projects/<项目路径编码>/<sessionId>.jsonl`。

使用 `--resume <sessionId> --print "<消息>"` 可以：
1. 启动一个非交互式 Claude Code 进程
2. 加载该会话的**完整历史上下文**
3. 发送指定消息
4. 输出 Claude 的回复后退出

消息会追加到原会话的 jsonl 文件中（除非加 `--fork-session`）。

---

## 二、快速开始

### 2.1 列出当前活跃会话

```bash
python scripts/claude_message.py --list
```

输出示例：
```
PID     SESSION_ID                              CWD                              NAME              LAST_ACTIVE
35140   b0fcf1fe-ce5c-4709-9981-af8d797efae6  C:\Users\chenlizhuo             chenlizhuo-72     2026-10-03 12:41
27136   ed1aba91-1b12-4269-89b5-b45f6a5bc0fa  E:\CodeProject\其余工程         agent-session-monitor  2026-10-03 12:35
...
```

### 2.2 向指定会话发消息

**⚠ 必须指定 `--cwd` 为目标代码仓库根目录**，否则 Claude 的工具权限会被限定在当前目录，导致读不到目标代码、也写不进去。

```bash
python scripts/claude_message.py --session b0fcf1fe-... --message "你的消息" --cwd /path/to/repo
```

脚本默认会添加 `--dangerously-skip-permissions`（否则只有读权限，写文件/执行命令会被拦截）。如需关闭，加 `--no-skip-permissions`。

或直接用原始命令（注意先 `cd` 到目标目录）：

```bash
cd /path/to/repo
claude --resume <sessionId> --dangerously-skip-permissions --print "你的消息"
```

### 2.3 安全测试（不污染原会话）

加 `--fork` 创建分支会话，消息写入新 sessionId，原会话不受影响：

```bash
python scripts/claude_message.py --session <id> --message "测试" --fork
```

### 2.4 查看某会话最新消息

```bash
python scripts/claude_message.py --session <id> --latest 5
```

---

## 三、命令参考

### 脚本封装：`scripts/claude_message.py`

| 参数 | 说明 |
|---|---|
| `--list` | 列出当前运行的 Claude Code 会话 |
| `--session <uuid>` | 目标会话 ID（可从 `--list` 获取） |
| `--message "<text>"` | 要发送的消息内容 |
| `--cwd <path>` | **运行命令的工作目录（重要）**——应设为目标代码仓库根目录，否则 Claude 读不到目标代码、也写不进去 |
| `--fork` | 创建分支会话，不写入原会话 |
| `--latest <n>` | 查看该会话最近 n 条对话（不发消息） |
| `--timeout <sec>` | 等待回复的超时时间（默认 300 秒） |
| `--no-skip-permissions` | 不添加 `--dangerously-skip-permissions`（默认会添加；不加的话只有读权限） |

### 原始 CLI 命令

```bash
# 基本用法（先 cd 到目标代码目录！）
cd /path/to/repo
claude --resume <sessionId> --dangerously-skip-permissions --print "消息"

# 分支模式（安全测试）
claude --resume <sessionId> --fork-session --dangerously-skip-permissions --print "消息"

# 指定模型
claude --resume <sessionId> --dangerously-skip-permissions --model sonnet --print "消息"
```

**两个关键参数：**
- `--dangerously-skip-permissions`：不加的话只有读权限，写文件/执行命令会被拦截
- 工作目录：必须在目标代码仓库根目录下运行，否则 Claude 的工具权限被限定在当前目录

---

## 四、注意事项

### 4.0 ⚠ 工作目录与权限（最常见的坑）

实测踩过两次，务必注意：

| 问题 | 现象 | 解决 |
|---|---|---|
| **工作目录不对** | Claude 能回复，但说"读不到目标代码"、"权限被拒" | 必须加 `--cwd /path/to/repo`，或先 `cd` 到目标目录再运行 |
| **没加 skip-permissions** | Claude 能读代码，但写文件/执行 git 全被拦 | 默认已加 `--dangerously-skip-permissions`；如用原始命令需手动加 |

**原理**：`--print` 模式下，Claude Code 的工具信任域基于**当前工作目录**。从错误的目录启动，它就只能访问那个目录。

### 4.1 性能与成本

- **大会话恢复慢**：上下文越大，加载时间越长。85MB / 4万条记录的会话可能需要 1 分钟以上。
- **Token 消耗**：每次 `--resume` 都要重新加载完整上下文，频繁调用成本不低。
- 建议：长会话优先用 `--fork` 测试，确认无误后再直接写入。

### 4.2 并发写入风险

- 如果目标会话**正在运行**（有对应终端窗口），直接写入会让两个进程同时追加同一个 jsonl 文件。
- jsonl 是行级追加，每行独立 JSON，**实际冲突概率极低**，但理论上存在交错可能。
- 如需绝对安全，先关闭目标终端，或使用 `--fork` 模式。

### 4.3 stdin 警告

- 在 PowerShell / cmd 中直接运行时，可能出现 `Warning: no stdin data received in 3s`。
- 这是正常现象，不影响功能。加 `< NUL`（Windows）或 `< /dev/null`（Linux/macOS）可消除。

### 4.4 回复不会实时显示在原终端

- 通过 `--print` 发送的消息和回复会写入 jsonl 文件。
- 但**正在运行的那个终端窗口不会实时刷新显示**新消息。
- 下次在该终端执行 `/resume` 或重新打开会话时，可以看到完整历史。

---

## 五、典型工作流

### 场景 A：让另一个会话帮忙查东西

```bash
# 1. 列出会话，找到目标
python scripts/claude_message.py --list

# 2. 发消息请求帮助（必须指定 --cwd 为目标代码目录）
python scripts/claude_message.py --session b0fcf1fe-... --cwd /path/to/repo --message "帮我查一下 PF-ERSM 里 transportX 的定义，贴出相关代码行"

# 3. 等待回复输出
```

### 场景 B：批量向多个会话发通知

```bash
for sid in $(python scripts/claude_message.py --list --ids-only); do
  python scripts/claude_message.py --session "$sid" --message "系统将在 10 分钟后重启，请保存工作"
done
```

### 场景 C：审查另一个会话的最新进展

```bash
# 查看最近 10 条对话
python scripts/claude_message.py --session b0fcf1fe-... --latest 10
```

---

## 六、数据来源

- 会话索引：`~/.claude/sessions/<pid>.json`
- 对话历史：`~/.claude/projects/<路径编码>/<sessionId>.jsonl`
- 进程信息：Windows `Get-CimInstance Win32_Process` / Linux `ps`

只读本地数据，不联网。

---

## 七、Agent 管理规范

> 管理者通过本 skill 统一下发任务、检查进度、验收成果、处置异常。以下为管理规定。

### 7.1 下属会话命名规范

每个活跃会话应有明确名称，格式：`<项目缩写>-<角色>-<序号>`

| 示例 | 含义 |
|---|---|
| `hcyx-rsm-porter` | hcyx 项目，RSM 模块，代码搬运工 |
| `weflow-dev-main` | weflow-cli 项目，主力开发 |
| `review-code-audit` | 通用代码审查 |

用 `--list` 查看时，NAME 列应能一眼看出该下属在做什么。名称模糊的（如 `chenlizhuo-72`）应在任务下发时通过 `--name` 重命名，或在终端里 `/name` 修改。

### 7.2 任务下发规定

**下发前三项检查（缺一不可）：**

1. **会话存在**：`--list` 确认目标会话在运行
2. **工作目录正确**：`--cwd` 必须指向目标代码仓库根目录
3. **权限足够**：默认已加 `--dangerously-skip-permissions`；如下属反馈写不进去，检查是否被 `--no-skip-permissions` 覆盖

**指令模板：**

```
<任务目标> + <验收标准> + <时间预期>

示例：
"完成 PF-ERSM 四层字典壳的搬运，按施工方案推进，校验上游隐含假设。
 验收：5434+ 测试通过、代码落盘、文档更新、git 提交。
 预期 10 分钟内完成，超时我会检查。"
```

**禁止下发的指令：**
- 不含 `--cwd` 的代码操作任务（必踩权限坑）
- 目标不明确的"继续弄"（下属不知道做到什么程度算完）
- 同时给多个下属下发操作同一文件的任务（git 冲突风险）

### 7.3 进度检查机制

| 场景 | 命令 | 频率 |
|---|---|---|
| 日常巡检 | `--list` | 每天至少一次 |
| 任务中跟进 | `--session <id> --latest 5` | 下发后 5 分钟、预期完成时间点 |
| 异常排查 | `--session <id> --latest 20` | 下属超时未响应时 |

**进度判断标准：**
- ✅ 正常：下属有持续输出，在按计划推进
- ⚠ 卡点：下属反复说"权限不足""目录不对""找不到文件"——立即解决后重发
- ❌ 卡死：超过 `--timeout` 无输出、或输出停留在同一位置超过 5 分钟——考虑新开会话

### 7.4 资源管控

**Token 预算：**
- 每次 `--resume` 都要重新加载完整上下文，大会话（>10MB）单次恢复可能消耗大量 token
- 同一会话 1 小时内下发不超过 3 次任务，合并指令减少恢复次数
- 超过 50MB 的会话考虑归档历史、新开会话继续

**并发控制：**
- 同一代码仓库同时只允许一个下属执行写操作
- 读操作（查询、分析）可并发，但不超过 3 个
- 下发写任务前确认目标仓库 `git status` 干净

**会话大小监控：**
- 用 `--latest` 时注意文件大小输出
- >20MB：提醒下属注意上下文压缩
- >50MB：建议归档并新开会话

### 7.5 验收规定

任务完成后，下属必须给出总结，管理者逐项验证：

| 验收项 | 验证方式 |
|---|---|
| 代码落盘 | `git diff --stat` 确认文件变更 |
| 测试通过 | 下属报告的测试数 + 关键测试名 |
| 文档更新 | 检查相关 doc/README 是否同步 |
| Git 提交 | `git log --oneline -3` 确认提交号和信息 |
| 无残留 | `git status` 确认工作区干净 |

**不接受的"完成"：**
- 只说"做完了"但没有测试结果和提交号
- 代码写了但没跑测试
- 改了代码但没更新文档
- 工作区有未提交的改动

### 7.6 异常处理手册

| 异常现象 | 原因 | 处置 |
|---|---|---|
| 下属说"读不到目标代码" | 工作目录不对 | 加 `--cwd <目标目录>` 重发 |
| 下属说"写文件被拒" | 权限不足 | 确认 `--dangerously-skip-permissions` 已加，重发 |
| 下属说"找不到文件/路径" | cwd 或路径错误 | 用 `--latest` 看他实际在哪个目录，修正后重发 |
| 超时无输出 | 大会话恢复慢 / 任务复杂 | 延长 `--timeout`；或 `--latest` 看是否在推进 |
| 输出停住不动 | 会话卡死 / 等待人工输入 | 新开会话，用 `--fork` 测试后再正式下发 |
| Git 冲突 | 多下属同时写同一仓库 | 确保同时只有一个写操作；冲突时 `git stash` 后逐个处理 |
| 下属重复犯同样错误 | 指令没说清 / 上下文丢失 | 在指令里明确写出前置条件（目录、权限、依赖） |

### 7.7 会话生命周期

| 阶段 | 操作 | 标准 |
|---|---|---|
| **创建** | 新任务优先复用已有同项目会话 | 保持上下文连贯，避免重复加载 |
| **复用** | `--resume <sessionId>` | 同一项目的任务尽量在同一会话里 |
| **重命名** | 终端 `/name <新名称>` 或下发时 `--name` | 名称应反映当前任务，不模糊 |
| **归档** | 项目完成后保留会话，不删除 | 历史可追溯，jsonl 就是档案 |
| **清理** | 关闭长期不用的僵尸会话终端 | `--list` 里超过 30 天无活动的可关 |
| **禁止** | 不删除任何会话的 jsonl 文件 | 历史记录是资产，不是垃圾 |

### 7.8 管理者每日巡检清单

```
□ 1. --list 查看所有下属状态，确认无僵尸会话
□ 2. 检查进行中任务的进度（--latest）
□ 3. 确认昨日下发的任务已验收（测试+提交+文档）
□ 4. 检查各会话大小，超 50MB 的提醒归档
□ 5. 确认目标仓库工作区干净，无未提交改动
□ 6. 规划今日任务分配，避免同仓库并发写操作
```
