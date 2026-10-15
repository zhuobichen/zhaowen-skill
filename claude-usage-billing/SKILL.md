---
name: claude-usage-billing
description: >
  分析 Claude Code / one-hub 的 token 与费用：按天出HTML 报告，把主会话和它派生的
  subagent 合并成"任务"，定位当天最烧钱的会话/子Agent，并可直接展开每个子Agent 的
  任务指令与最终产出。同时回答"子Agent 委派中途关机/中断后内容是不是丢了"这类问题。
  触发词：用量、费用分析、花了多少钱、账单、token 花了多少、哪个会话最烧钱、
  子Agent 花了多少、claude code 花费、one-hub 账单 CSV、usage_data。
  数据源 ~/.claude/projects 日志 + one-hub 导出的 amount-*.csv。
argument-hint: '[YYYY-MM-DD]'
user-invocable: true
---

# Claude Code 用量与费用分析（claude-usage-billing）

回答两类问题：**钱花在哪**（按任务/会话/子Agent 拆开算），和**子Agent 的内容去哪了**。

## 何时用

- "我 10-14 花了多少钱 / 哪个会话最烧钱 / 那个大头是干什么的"
- "各个子Agent 分别花了多少，它们在做什么"
- "子Agent 中途关机/手动停了，内容是不是丢了、还存在哪"
- 拿到 one-hub 导出的 `usage_data_*.zip` / `amount-*.csv`，要出账单分析

## 快速开始

```bash
# 1. 生成报告（不传日期默认昨天）
python scripts/html_report.py 2026-10-14

# 2. 体检（结构完整性 + 内容异常，交付前必跑）
python scripts/check_html.py claude-usage-2026-10-14.html
```

账单 CSV 查找顺序：`--csv <文件>` → `--csv-dir <目录>` → 环境变量
`DS_USAGE_CSV_DIR` → `~/Downloads` → `<skill>/data`。one-hub 导出的 zip 解压后即可。

常用参数：`--out <html>` 指定输出位置，`--root <dir>` 指定会话日志根目录
（默认 `~/.claude/projects`）。

Windows 上脚本已强制 UTF-8 输出，CJK 不会乱码。

## 报告里有什么

| 区块 | 内容 |
|---|---|
| 汇总卡片 | 账单总额、会话数（主/子）、任务数、子Agent 占比、最大任务、主会话总轮次 |
| 按项目 | 各 `~/.claude/projects/<项目>` 的折算金额与占比条 |
| 按任务 | main + 其 subagent 合并后的开销排序；每行可展开 |
| └ 主会话 | 当天**逐轮**对话：时间、你说了什么（原文可展开）、该轮金额、该轮工具调用数 |
| └ 子 Agent | agentId、当天金额、工具调用构成、**任务指令**（首条用户消息）、**最终产出**（末条助手文本） |

所有子Agent 卡片都带内容（指令 + 产出），这是本skill 与普通"账单汇总"的关键差别。

## 归并口径（必须理解，否则会读错结论）

- **一个"任务"= 一个主会话 + 它的全部 subagent**。主会话文件是 `<sid>.jsonl`，
  子 Agent 在 `<sid>/subagents/agent-<agentId>.jsonl`。归并时把主会话文件名
  **去掉 `.jsonl` 后缀**再与目录名匹配——漏掉这一步就会散成几十个"独立会话"。
- **单价来自账单 CSV**（按 key × token 类型加权混合），不是官方牌价。
- **折算列 = 日志口径 × 账单总额 / 日志合计**。日志侧 cache-hit 会多记、output 会
  少记，所以绝对金额只取折算列；排名与占比不受影响，合计精确等于账单。

## 子Agent 内容持久化（结论摘要）

子 Agent 的完整轨迹**一直是落盘的**：`<sessionId>/subagents/agent-<id>.jsonl`，
关机也不影响。真正会丢的是"看起来丢了"的三个原因——进度缓冲是0 字节、
`/resume` 只恢复主会话、超过 `cleanupPeriodDays`（默认 30 天）会被清理。
细节与排查命令见 `references/subagent-persistence.md`。

## 已踩过的坑

- **标题抓错**：直接取"当天最长的消息"会抓到 `<task-notification>`、
  `Another Claude session sent a message`、`Base directory for this skill`、
  `[Your previous response had no visible output]` 等系统注入文本。脚本已内置
  黑名单（`BOILER`），改脚本时别删。真人消息都极短时用"最后 3 条拼接"。
- **`content` 可能是 str 也可能是 block 列表**，统一走 `blocks()` 归一化再取 text。
- 逐轮金额要把每条 usage **归属到它所属的那一轮**（一轮 = 一条真人 user 消息
  + 其后的 assistant/tool 记录），否则单轮全是 0。

## 相关 Skill

- [`agent-dialog_management`](../agent-dialog_management/)——按主题查找/查看/恢复具体某个会话
- [`onehub_usage_monitor`](../onehub_usage_monitor/)——one-hub 实时额度与余额监测（不做回溯账单分析）
