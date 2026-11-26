---
name: session-archaeology
description: >-
  从本机任意 AI 客户端的会话里找回"某次做过的事"，尤其是用户记得做过、但找不到会话/产物的情况。
  覆盖 DSH、Codex、Claude Code 的会话日志与归档，核心方法是按"执行痕迹"（工具调用、命令、
  文件路径、模型名）而不是内容词搜索，并通过产物反推会话。当用户说"我记得以前用 X 做过 Y"
  "那次会话放哪了""找找之前转写/处理过的东西""我明明做过为什么找不到"时用。
  不负责读某个具体会话的内容（那是 dsh-session-viewer / agent-dialog_management）。
user-invocable: true
---

# 会话考古：找回"记得做过但找不到"的事

这不是"读会话"的 skill（读会话用 `dsh-session-viewer` / `agent-dialog_management`），
而是**用户记得做过某事、但会话和产物都找不到时的方法论**。核心教训来自一次真实排查：
用户记得"用本机 whisper 把分享会录音转成文字再让 AI 重写"，连续找了 DSH 全部会话、
Codex 会话、各种客户端都不命中，最后按"执行痕迹"重扫才在 Codex 一个 7/25 会话里找到，
并顺带找回了 6 份完整转写产物。

## 一、第一原则：按执行痕迹搜，不要按内容词搜

**这是整个 skill 最重要的一条。** 用户记忆里的词（人名、主题、软件名）往往是**产物里的词**，
不是会话里的词。直接拿这些词搜会话会大面积误命中或不命中。

| 搜索维度 | 可靠性 | 例子（本次真实数据） |
|---|---|---|
| 内容词（人名/主题）| ✗ 差 | 搜"振华老师/文韬/罗阳" → Codex 只命中 2 个无关会话（那是聊天记录里的联系人） |
| **执行痕迹**（工具调用/命令/路径/扩展名/模型名）| ✓ 好 | 搜 `whisper`+`.m4a`+`转写` → 立刻命中目标会话（whisper 130 次、转写 205 次、分享会 185 次） |

所谓执行痕迹包括：
- 工具/命令名：`whisper`、`faster-whisper`、`python -m whisper`、`ffmpeg`、`git commit`
- 文件扩展名与路径：`.m4a` / `.mp3` / `output/` / `AudioTranscriber` / `Bandicam录屏`
- 模型/库名：`transcribe(`、`WhisperModel`、`model.transcribe`、`deepseek`
- 参数与产物文件名：`完整逐字稿.md`、`--model medium`

**做法：先问自己"用户说的那件事，如果真在会话里执行过，会调用什么命令、写什么文件？"**，
用那个去搜，而不是用用户记得的名词。

## 二、第二个原则：先定位产物，再反推会话

用户记得的"结果"往往比"过程"更容易找到。

1. 先全盘搜**产物文件**：按扩展名（`.md/.txt/.docx/.srt/.vtt`）、按独特文件名
   （`完整逐字稿`、`逐字保留整理稿`）、按内容特征（时间戳行、说话人标记）。
2. 找到产物后，看它的**路径、目录名、创建时间、文件头**，里面有生成它的工具名和时间戳。
3. 拿工具名/时间戳回到会话库里搜，命中率极高。

本次路径：先找到 `D:\...\AudioTranscriber\output\20260724_分享会...\完整逐字稿.md`，
目录名里的工具名 `AudioTranscriber` 和日期直接指向 7/25 的 Codex 会话。

## 三、客户端会话库地图（Windows 本机）

| 客户端 | 活跃会话 | 归档/备份 | 格式 |
|---|---|---|---|
| DSH | `<DSH_HOME>/sessions/<cwd转义>/<id>/session.v4.jsonl.zstd` | `~/.dsh/sessions`（旧版）、`<DSH_HOME>/_dsh-backup-*`、`dsh-import/_out`、归档 id 在 `storages/workspace.json` 的 `archivedSessionIds` | 多帧 zstd，JSONL |
| Codex | `~/.codex/sessions/<Y>/<M>/<D>/rollout-*.jsonl` | `~/.codex/archived_sessions/`、`~/.codex/session_index.jsonl` | 明文 JSONL（`response_item` 等） |
| Claude Code | `~/.claude/projects/<项目>/*.jsonl` | `~/.claude/history.jsonl`（早期输入痕迹） | 明文 JSONL |
| 豆包/Kimi/Trae | 在各自 AppData 或云端，本机未必有 | — | — |

`DSH_HOME` 常见在 `D:\<项目>\dsh\home`；没设时脚本会探 `~/.dsh` 等。
**Codex 的归档目录一定单独搜**——很多老会话被移进 `archived_sessions/`，默认列表里看不到。
**DSH 的归档不是移走文件**，只是 `workspace.json` 里记了 id，文件还在主库里。

## 四、解压与解析要点（踩过的坑）

- **DSH 会话是多帧 zstd 追加写**。用 `ZstdDecompressor().decompress(整个文件)` 只解出第一帧，
  症状是"这个会话只有 1 行"。必须用 `stream_reader(f)` 流式读，或 `read_across_frames=True`。
- ** parole 编码**：Windows 控制台默认 GBK，直接 print 中文会报 `UnicodeEncodeError`。
  开头加 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`，或把结果写文件再读。
- **Codex rollout 的正文不在顶层**：消息在 `payload`/`message`/`content` 里，
  且 `content` 常是 `[{"type":"text","text":...}]`；要递归取值，别只看一层。
- **关键词计数排序比逐个打开高效**：先写脚本统计每个会话命中的执行痕迹次数，
  按总数排序，命中数异常高（几十上百次）的会话基本就是目标，再单独 dump 它。
- **路径会变**：会话里写的产物路径可能是旧路径（本次写 `D:\github_project\AudioTranscriber`，
  实际在 `D:\github_project\ZhaoWen_GitHub维护\AudioTranscriber`）。找不到产物时按目录名全盘搜，
  不要信会话里的路径原文。

## 五、标准排查流程（按顺序做，别跳）

1. **确定客户端**：用户说不清时，按"这件事用什么软件做"推断——
   命令行脚本/工具搭建 → Codex 或 Claude Code；DSH 里的对话/插件 → DSH。
2. **列会话库**：`agent_sessions_scan`（MCP 工具，一次列出全部 Claude/Codex 会话及归档状态）；
   DSH 用 `dsh-session-viewer` 的 `paths` / `list`。
3. **按执行痕迹统计排序**（见下方脚本骨架），落盘结果再读，不要在终端里硬刷。
4. **dump 命中最高的会话**的用户消息 + 工具调用，确认是不是它。
5. **找产物**：全盘搜可能的文件名/扩展名，核对目录名、时间戳。
6. **交叉验证**：会话里说生成了 A/B/C 文件，磁盘上是否都在；数量、时长、人名对得上。
7. **别太快下"不存在"结论**：用户记得这么清楚，通常是搜索维度不对（回到第 1 条）。
   只有四个客户端的会话库和全盘产物都搜过，才能说找不到。

## 六、脚本骨架

见 `scripts/session_hunt.py`：按"执行痕迹关键词"统计所有客户端会话的命中数并排序，
支持 `--client dsh|codex|claude|all`、`--pattern`、`--dump <id>`。
它是轻量扫描器，不替代正式读取工具；找到目标会话后，用 `dsh-session-viewer` /
`agent-dialog_management` 做完整查看和导出。

```bash
python <skill>/scripts/session_hunt.py rank "whisper .m4a transcribe" --client all
python <skill>/scripts/session_hunt.py dump <rollout-id或session-id关键词> --pattern "whisper"
```

## 七、边界

- 只读：不写会话文件、不改 `workspace.json`、不动归档状态、不启停任何客户端。
- 不上传任何会话内容到网络；全部在本机磁盘完成。
- 命中数只是线索不是结论：高命中会话也可能是代码讨论（如 weflow-cli 里改 `transcribe_wav()`），
  必须 dump 出用户消息和命令上下文才能确认。
- 找不到时如实说找不到，并列出"搜过哪些库、用了什么维度"，让用户决定下一步
  （去云端找 / 换客户端找 / 提供新线索），不要编造不存在的会话。
