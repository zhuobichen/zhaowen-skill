# 子Agent「内容丢失」问题 · 调查结论

> 调查日期：2026-10-14 | 证据来自本机 `~/.claude/projects/` 真实转录文件，非文档推测

## 一句话结论

**内容没有丢。** 子Agent 的完整轨迹（每一条 prompt、每一次工具调用、每一个 tool_result、全部上下文）
一直写在磁盘上：`~/.claude/projects/<项目>/<sessionId>/subagents/agent-<agentId>.jsonl`。
本机共 **195 个子Agent 转录文件、44,440 行、约 200 MB**，最早 2026-08-07，最晚 2026-10-14。

你感知到的「全丢」，是三件事叠加造成的错觉：

| 现象 | 真实原因 |
|---|---|
| 界面上子Agent 一片空白 | CLI 只把子Agent 的**最终总结**回填进主会话，过程默认折叠；`/resume` 恢复的是主会话，**子Agent 没有独立的 resume 入口** |
| Temp 里的 `.output` 是空的 | `%TEMP%\claude\<项目>\<sessionId>\tasks\<taskId>.output` 只是**进度流缓冲**。实测 20 个文件全部 0 字节，而同批子Agent 的 jsonl 有 200~1700 KB。**它不是记录** |
| 主会话里 `tool_use.id` 和子Agent 文件对不上 | 主会话 1820 个 tool_use id 与子Agent 内的 id **交集为 0**（两套独立 id 空间）。真正的关联键是 `task_status` 附件里的 `taskId`，它 **等于** agentId |

## 异常终止到底丢多少

判据：转录最后一条是 `assistant`（正常收尾）还是 `user`（被硬切断）。

```
最后一条记录类型分布: {'assistant': 191, 'user': 4}
```

- **191 个正常收尾**（`stop_reason=end_turn`）—— 完整。
- **4 个被手动打断**，最后一条都是 `[Request interrupted by user]` / `[Request interrupted by user for tool use]`：

| agentId | 时间 | 记录数 | 已花 | 打断原因 |
|---|---|---|---|---|
| a67fdc69dc615a591 | 10-14 06:30 | 645 | 1.38 CNY | 用户中断 |
| ac06fd2f89528b83a | 10-14 06:30 | 227 | 0.43 CNY | 用户中断（拒绝工具调用）|
| ae2a164e2f0841d82 | 10-08 04:25 | 45 | 0.05 CNY | 用户中断 |
| acfc50ba99807ff6c | 09-08 07:56 | 14 | 0.00 CNY | 用户中断 |

**没有任何一个是「关机」或「余额耗尽」造成的**——那两种情况在转录里根本不产生新记录，磁盘上留下的是一个完整的旧文件。
换句话说：**关机 / 手动 / API 断费，最多丢掉「最后一步工具调用之后没写完的那一段」，
之前的全部内容一条不少。** 这 4 个也一样：前 644 条记录、1.38 元已经花掉的工作全在文件里。

## 怎么把它找回来

本仓库新增 `subagents.py`（Claude Code 与 Codex 都适用）：

```powershell
# 索引：按花费 / 时间列出所有子Agent，附带任务 prompt 摘要
python E:\CodeProject\ds-manager\subagents.py index --sort cost --limit 20
python E:\CodeProject\ds-manager\subagents.py index --day 2026-10-14 --sort time

# 全文可读转录（已把 tool_use / tool_result 渲染成 Markdown）
python E:\CodeProject\ds-manager\subagents.py show a67fdc69dc615a591

# 导出留档
python E:\CodeProject\ds-manager\subagents.py export a67fdc69dc615a591 --out D:\被打断的调研.md

# 某个主会话底下的全部子Agent
python E:\CodeProject\ds-manager\subagents.py session 79b26d95-e19d-46a6-92e7-b79cd77f2fc0
```

已生成的索引：

- `reports/subagents-index.json` — 全部 195 个
- `reports/subagents-index-2026-10-14.json` — 当天 41 个

## 想真正「不丢」要做的三件事

1. **保留期**。Claude Code 只有 `cleanupPeriodDays`（默认 30 天），**没有归档功能**，
   到期直接删转录。要长留就把它调大（`~/.claude/settings.json`）。
   这才是「内容真的没了」的唯一原因。
2. **重要子Agent 跑完就导出**。`export` 出来的 Markdown 脱离 Claude Code 独立存在，
   不受保留期影响。
3. **别在子Agent 里只让它「调研」不要求它「落盘」**。本次 10-14 那批求职调研子Agent
   全部只回了文本总结、没有写文件，所以即使转录还在，结论也要现挖 ——
   `show <agentId>` 就能把最后的总结取出来。

## 现状数据

- 全部 195 个子Agent，按 DeepSeek 低价档估算合计 **≈ 91.5 CNY**（真实账单口径见 `usage-2026-10-14.md`，
  高价档 2 倍的部分会让实际值更高）
- 2026-10-14 当天 41 个子Agent，估算 **≈ 27 CNY**，占当天 Claude Code 消耗的近一半
- 单个最贵的子Agent：`a518785f34c596d1`（央广/运营商/电网校招调研，1221 轮、309 次工具调用、≈4.87 CNY）
