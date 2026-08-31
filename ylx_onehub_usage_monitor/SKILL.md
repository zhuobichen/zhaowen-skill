---
name: ylx_onehub_usage_monitor
description: 监测 one-hub API 用量与费用：查询总额度/已用/剩余(美元+人民币)、每日/每月记账、各模型 one-hub 实际单价 vs 官方价对比。当需要查询公司/个人 one-hub 中转额度消耗、统计每日费用、评估模型成本或选模型省钱时使用。
metadata:
  type: skill
---

# one-hub 用量监测与费用统计

## 一、查询当前用量

- **MCP 工具**（推荐）：`mcp__onehub-monitor__check_usage` → 实时总额度/已用/剩余/使用率
- **本地脚本**：`python E:\CodeProject\问题修理\cost_stats.py`（读 `ONEHUB_API_KEY` 环境变量）
- 汇率自动从 `/api/status` 的 `PaymentUSDRate` 动态读取（约 7.3）

## 二、每日 / 每月记账

- 工具：`mcp__onehub-monitor__daily_snapshot`；脚本：`cost_stats.py --daily`
- 账本文件：`E:\CodeProject\问题修理\cost_stats_history.json`（MCP 与脚本共享）
- 每日花费 = 当日快照 `total_usage` − 前日快照
- ⚠️ **关键限制**：one-hub billing 接口只返回累计总量、忽略日期参数；按天/月靠本地每日快照累积，**历史无法回溯**，需从记账那天起每天运行

## 三、定时监测

- 会话内定时：每天 21:07 调 `check_usage` + `daily_snapshot`（session-only，7 天过期）
- **使用率 > 80% 必须重点提醒**用户关注额度余量

## 四、各模型实测定价（2026-08，$/M ≈ output 价，含 input 少量）

| 档位 | 模型（实测 $/M） |
|---|---|
| 🟢 原价/便宜 | deepseek-v4-flash($0.26)、MiniMax-M3($1.04)/M2.5/M2.7($1.17)、composer-2.5($1.87)、gemini-3.5-flash-lite($2.48)、gpt-5.4-mini($4.43)、grok-4.6($5.5)/4.5($5.7)、codex-auto-review($5.87)、**gpt-5.6-luna($5.86)**、gemini-3.5-flash($8.9)、gpt-5.4($14.67)、gpt-5.5($29.43) |
| 🟠 加价 1.6~3x | gemini-3.7-flash($11.9)、claude-haiku-4-5($14.9)、claude-sonnet-5($22.1)、claude-opus-5($71.6)、gpt-5.6-terra($44.9)、gpt-5.6-sol($62.1) |
| 🔴 严重加价 | **deepseek-v4-pro($18.85，官方 ~$0.8-4 → 5~22x)** |
| ❌ 不可用 | claude-fable-5（列表有但 404） |

**结论**：one-hub 对主流模型（DeepSeek-flash/MiniMax/Grok/gemini-flash/gpt-5.4/5.5/luna）基本**官方原价**；仅对 **deepseek-pro、Claude 全系、gpt-5.6-terra/sol、gemini-3.7** 加价 1.6~22 倍。省钱用原价档，避雷加价档。

## 五、测量与注意事项

- `total_usage` 单位是**美分**（÷100 得美元），实测验证过
- 测量方法：大输出调用对比 `total_usage` 差值；**正在被并发使用的模型测不准**（如用户 Codex 默认模型）
- **个人 vs 总池子**：sk- key 只能查自己关联账户的额度；公司总池子、按模型明细需 one-hub 登录 token（普通 key 无权限）
- 相关工具：`E:\CodeProject\mcp-server\onehub-monitor\`（MCP 源码，已入 zhaowen-mcp 仓库）
