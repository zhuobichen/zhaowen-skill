# claude-usage-billing

把 Claude Code 的 token 账单变成**能读的 HTML 报告**：主会话和它派生的 subagent
合并成"任务"，定位当天最烧钱的会话与子 Agent，并可直接展开每个子 Agent 的
**任务指令**与**最终产出**。

## 用法

```bash
python scripts/html_report.py 2026-10-14 --csv-dir ~/Downloads
python scripts/check_html.py claude-usage-2026-10-14.html
```

- 账单 CSV：one-hub 导出的 `usage_data_*.zip` 解压后得到的 `amount-*.csv`。
  查找顺序 `--csv` → `--csv-dir` → `$DS_USAGE_CSV_DIR` → `~/Downloads` → `<skill>/data`。
- 会话日志：`~/.claude/projects`（可用 `--root` 覆盖）。
- 不传日期默认分析**昨天**。

## 为什么要"折算"

日志侧 token 与账单侧有系统性偏差（cache-hit 多记、output 少记）。报告同时给出
「日志口径」和按账单总额等比缩放的「折算」金额：**排名与占比看折算列，绝对金额也看
折算列**，其合计精确等于账单金额。

## 子 Agent 内容怎么取

见 `references/subagent-persistence.md`：子 Agent 轨迹一直落盘在
`<sessionId>/subagents/agent-<id>.jsonl`，关机不丢；真正会丢的只有
`cleanupPeriodDays`（默认 30 天）过期与两个认知误区。

## 目录

```text
SKILL.md                        # 技能说明（frontmatter + 工作流 + 已踩的坑）
scripts/html_report.py          # 报告生成器
scripts/check_html.py           # 报告体检（结构 + 内容异常）
assets/report_template.html     # 报告模板（改样式改这个）
references/subagent-persistence.md
```
