---
name: dsh_messaging
description: 用官方 CLI 从外部给 DeepSeek Harness (DSH) 发消息、续接既有会话、拿结构化输出与 token 用量。当需要脚本化调用 DSH、把任务丢给 DSH 跑、或用命令行驱动 DSH 对话时使用。
metadata:
  type: skill
---

# 给 DSH 发消息（`dsh` CLI）

DSH 有两条互不相干的用法：**web profile 是常驻服务**（给人用浏览器点的），**headless profile 是一次性执行器**（给脚本用的）。要「从外面发一条消息给它」，走的是后者。

## 一、环境（本机专属）

DSH 装在一个专用目录，**不是** C 盘那个 `~/.dsh`（那是 0.1.0-rc.6 的旧环境，别用）：

```
DSH_HOME = D:\github_project\ZhaoWen_GitHub维护\dsh\home
CLI      = D:\github_project\ZhaoWen_GitHub维护\dsh\toolchain\node_modules\@deepseek-ai\dsh\lib\bin.js
启动器   = D:\github_project\ZhaoWen_GitHub维护\dsh\dsh.cmd   （自动设好 DSH_HOME）
```

版本 `0.2.0-rc.2`。PowerShell 里调：

```powershell
$env:DSH_HOME = 'D:\github_project\ZhaoWen_GitHub维护\dsh\home'
$cli = 'D:\github_project\ZhaoWen_GitHub维护\dsh\toolchain\node_modules\@deepseek-ai\dsh\lib\bin.js'
& node $cli --profile headless "你的问题"
```

## 二、发消息（四种形态）

| 形态 | 命令 | 用途 |
|---|---|---|
| 一次性问答 | `& node $cli --profile headless "问题"` | 回复直接打到 stdout |
| 从 stdin | `"长文本" \| & node $cli --profile headless -` | 提示词很长时，避开命令行转义 |
| 结构化 | `& node $cli --profile headless --json "问题"` | 每行一个 JSON 事件，能拿 sessionId 和 token 用量 |
| **续接会话** | `& node $cli --profile headless --session-id <id> "追问"` | 接上次的上下文继续问 |

**会话从哪来**：`--json` 的第一行就是它：

```json
{"type":"session","sessionId":"session-aa0cef67-91f6-42f4-ba6f-5ad42e5841b3","cwd":"..."}
```

记下这个 id，之后加 `--session-id` 就能接着聊。传一个不存在的 id 会明确报错 `session "..." does not exist; omit --session-id to start a new Session`。

## 三、`--json` 的事件类型（实测）

```
{"type":"session","sessionId":"...","cwd":"..."}
{"type":"status","phase":"turn_start","turn":1}
{"type":"status","phase":"step_start","turn":1,"step":1}
{"type":"thinking","text":""}
{"type":"text","text":"ok"}                       ← 最终回答
{"type":"status","phase":"step_end","turn":1,"step":1,
 "usage":{"inputTokens":706,"outputTokens":2,"cacheReadTokens":5504,"cacheWriteTokens":0,"totalTokens":6212}}
```

`usage` 里直接有 token 数，脚本里做成本统计用它，不用另接计费接口。

## 四、几个坑（都是实测踩到的）

1. **推理过程走 stderr**，会以 `dsh: reasoning:` 打头混进输出。要清爽的结果，过滤掉：`... 2>&1 | Select-String -NotMatch '^dsh: reasoning'`
2. **PowerShell 会把 stderr 当错误**：正常的 `dsh: reasoning:`、甚至 `java -version` 的输出都会让 `$?` 变 false、退出码变成 255。**别拿退出码判成败**，看输出内容。
3. **headless profile 是「裸」的**。它只有基础 bundle——`dsh-ops`、`dsh-pet`、`dsh-theme-whalegirl`、`dsh-infinite-gen-5` 这些都只装在 `web` profile 里。想在脚本化轮次里用到它们（比如 `ig5_doctor`），得单独往 headless 里装。
4. **它会真的用工具**，不是纯聊天。问需要文件操作的题，它会自己去 glob / 读文件。
5. **profile 首次使用会自动初始化**（`dsh plugin --profile <名> install`），复用共享 store，不会重下。

## 五、会话落在哪

```
<DSH_HOME>\sessions\<cwd 转义后的目录名>\...
```

目录名是工作目录转义来的，例如 `--D-github_project-ZhaoWen-GitHub~7EF4~62A4-dsh--`（`~7EF4~62A4` 是「维护」的 UTF-8 转义）。想盘点历史会话就翻这里。

## 六、能力边界

- **能**：起新会话、续接会话、拿结构化事件和用量、跑工具、读 stdin。
- **不能**：往**正在跑的 web 服务**里的某个界面会话发消息。`--profile headless` 起的是独立会话，跟浏览器里那个不是同一个。要做到这个得走 web 服务的 RPC（未摸通）。
- `dsh sdk` / `dsh acp` 另外提供 stdio JSON-RPC 接口，适合做长期驻留的集成——本次没试，需要另立 skill。
