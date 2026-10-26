---
name: dsh-session-viewer
description: 查/读/搜/导出本机 DeepSeek Harness (DSH) 的会话记录——只翻磁盘上的会话文件，不启动 DSH、不联网、不改任何东西。当用户说"我那个会话不见了""找之前聊 XX 的那次对话""看看我和 DSH 聊了什么""把那次会话导出来"时用。也用来回答"DSH 里某句话是哪次说的"。
metadata:
  type: skill
---

# 看 DSH 的会话（只读）

DSH 的会话全在本机磁盘上，一个会话一个文件。这个 skill 直接读文件，**不需要** DSH 在跑，也不碰 GUI。
典型场景：侧栏里找不到某个会话了、想全文搜"我当时提过什么"、要把某次对话导成 Markdown。

## 一、命令

脚本：`scripts/dsh_sessions.py`（依赖 `zstandard`，`python -m pip install zstandard`）

```powershell
$S = "<这个 skill 目录>\scripts\dsh_sessions.py"

python $S paths                      # 先看探测到哪些数据源
python $S list                       # 全部会话：时间 / 分组 / 消息数 / 标题
python $S list -v --limit 20         # 带 id 和 cwd
python $S search "远程连接"           # 全文搜（用户+助手+推理）
python $S search "frpc" --role user  # 只搜用户说过的话
python $S search "报错" --tools       # 连工具输出一起搜（找那次的报错原文）
python $S where afb6b83f             # 这个会话在哪个分组、文件在哪
python $S show afb6b83f              # 按轮次打印
python $S show afb6b83f --user-only  # 只看用户说了什么（最快回忆起上下文）
python $S show afb6b83f --from 44 --to 62   # 只看第 44–62 轮（长会话里截一段）
python $S show afb6b83f --tools      # 带工具调用/结果
python $S export afb6b83f -o x.md    # 导出 Markdown
```

id 支持前缀（`afb6b83f` / `session-afb6b83f` 都行）。

## 二、数据源（全部只读）

| 位置 | 内容 |
|---|---|
| `<DSH_HOME>/sessions/<cwd转义>/<session-id>/session.v4.jsonl.zstd` | 当前版本会话 |
| `~/.dsh/sessions/.../session.jsonl.zstd` | 旧版（0.1.0-rc.x）会话，新版 GUI 不显示，标 `[旧版]` |
| `<DSH_HOME>/storages/workspace.json` | 侧栏分组：哪个会话属于哪个 workspace、分组名、归档列表 |
| `<DSH_HOME>/storages/session_projcache/sessions/<id>.json` | GUI 缓存：标题、首条消息（比会话文件里的标题更准） |

`DSH_HOME` 没设时脚本会去探 `~/.dsh`、`./dsh/home`、`~/Documents/deepseek-harness`；也可以 `--home <路径>` 指定。

## 三、三个坑（不知道会白找半天）

1. **会话是「多帧 zstd」追加写的。** 直接 `ZstdDecompressor().decompress(整个文件)` 只解出**第一帧**，
   症状是"这份会话只有 1 行"。必须 `stream_reader(..., read_across_frames=True)` 或流式 `decompressobj`。
2. **正文不在事件顶层。** 事件形如 `{"type":"user/message","data":{...}}`；助手正文在
   `data.message.content[]` 里，按 `type` 区分 `reasoning`（推理）和 `text`（要说的话）。
3. **用户消息里混着 harness 注入的上下文**（`source.kind` = `runtime-context` / `skill-catalog` /
   `time-context` / `user-approval` / `compact-checkpoint` / `tool-jobs`）。这些不是用户打的字，
   统计"用户说了几句"、导出对话时都要排除；`show --injected` 才显示。

## 四、"会话不见了"的三种真相（按概率排序）

1. **它在另一个分组里。** 侧栏按会话的 **cwd** 分组，换个工作目录开的会话就落到别的分组
   （比如 `C:\...\deepseek-harness\default-workspace` 那一组）。`where <id>` 直接告诉你它在哪组。
2. **标题是自动生成的，跟你记忆的关键词对不上。** 标题取首句或模型摘要（"逆向分析豆包数据导入同步"
   其实后半段在聊远程连接）。**别按标题找，按 `search` 找内容。**
3. **被归档了**（`workspace.json` 的 `archivedSessionIds`，`list` 里标 `[归档]`），或被导入工具写坏
   （报 `stored log is corrupt`；那种在 `list` 里仍然列得出来，`show` 会报错）。

确认没删、只是藏起来的话，告诉用户去 GUI 侧栏切到对应分组即可——**不要**去动
`workspace.json` 手工"修复"，那个文件被 DSH 持有，写了会被覆盖或引发加载失败。

## 五、分工

| 想做 | 用 |
|---|---|
| 读 / 搜 / 导出 DSH 历史会话 | 本 skill |
| 从外部给 DSH 发消息、续接会话 | `dsh_messaging` |
| 查 Claude Code / Codex 的会话 | `agent-dialog_management` |

## 六、边界

- 只读：不写会话文件、不改 `workspace.json`、不启停 DSH。
- 不解析附件二进制；图片/文件只以 `sha256` 占位出现在 `show` 里。
- 旧版会话的标题在 projcache 里没有，只能靠 `session/title` 事件或首条消息。
