---
name: dsh-session-viewer
description: 查/读/搜/导出/删除本机 DeepSeek Harness (DSH) 的会话记录——只翻磁盘上的会话文件，不启动 DSH、不联网。默认只读；只有 delete 子命令写盘，且默认 dry-run、必须显式 --apply。当用户说"我那个会话不见了""找之前聊 XX 的那次对话""看看我和 DSH 聊了什么""把那次会话导出来""把这个会话删掉"时用。也用来回答"DSH 里某句话是哪次说的"。
metadata:
  type: skill
---

# 看/删 DSH 的会话

DSH 的会话全在本机磁盘上，一个会话一个文件。这个 skill 直接读文件，**不需要** DSH 在跑，也不碰 GUI。
典型场景：侧栏里找不到某个会话了、想全文搜"我当时提过什么"、要把某次对话导成 Markdown、要真正删掉某个会话。

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
python $S delete afb6b83f            # 删除（dry-run，只打印计划）
python $S delete afb6b83f --apply    # 真删
python $S delete afb6b83f --with-children --apply   # 连子代理会话一起删
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

## 五、删除会话（唯一的写操作）

DSH **没有**删除接口（`dsh-session-persistence-jsonl` 的 seam 明确不提供删除）。
自己删目录的坑是：**删盘不会自动把 id 从 `sessionIds` 摘掉**，侧栏会留一条点不开的空条目。
`delete` 就是把这个顺序做对：

```
备份 zip → 从 sessionIds/archived/pinned 摘掉 → 删目录 → 删 projcache → 校验「0 悬空」
```

```powershell
python $S delete <id>                       # 默认 dry-run：打印目标、体积、分组、子会话
python $S delete <id> --apply               # 执行
python $S delete <id> --with-children --apply   # 连子代理会话一起删
python $S delete <id> --apply --backup-dir D:\backup   # 指定备份位置
python $S delete <id> --apply --no-backup   # 不备份（不建议）
```

**必须知道的四条**

1. **改完 `workspace.json` 要重启 dsh web**，侧栏才同步。宿主持有内存态、写入时整份覆盖。
2. **重启前别在侧栏做归档/置顶**——那会用内存里的旧数组把这次改动静默覆盖，
   结果就是"侧栏有条目、点开报错"。
3. **子代理会话是孤儿陷阱**：`origin=subagent` 的会话不在侧栏，只在父会话的「子代理」里可见。
   父会话删了它们就既不可见也无入口。dry-run 会把这些列出来，确认后加 `--with-children`。
   实测一个例子：两个会话各挂 5 / 6 个子会话，父 3.85 MB、子 8.39 MB——**大头在子会话**。
4. **备份不是免费的**：会话本身是 zstd，再打包几乎不压缩（12.2 MB → 12.12 MB）。
   确认不打算回滚后，把备份 zip 删掉才真正腾出磁盘。

干完记得校验：脚本最后会打印「登记悬空条目 N 个」，**必须是 0**。

## 六、分工

| 想做 | 用 |
|---|---|
| 读 / 搜 / 导出 DSH 历史会话 | 本 skill |
| 从外部给 DSH 发消息、续接会话 | `dsh_messaging` |
| 查 Claude Code / Codex 的会话 | `agent-dialog_management` |

## 七、边界

- **默认只读**：`list` / `search` / `show` / `export` / `where` / `paths` 都不写盘、不启停 DSH。
- 唯一写操作是 `delete`；不加 `--apply` 永远不动文件，且只允许删探测到的 `<DSH_HOME>/sessions` 下的目录（有路径闸门）。
- 删除不可逆（DSH 无回收站）；默认先打包备份，但备份包要你自己删才腾出磁盘。
- 不解析附件二进制；图片/文件只以 `sha256` 占位出现在 `show` 里。
- 旧版会话的标题在 projcache 里没有，只能靠 `session/title` 事件或首条消息。
