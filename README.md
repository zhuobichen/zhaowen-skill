# zhaowen-skill

可复用 Skill 集合（Claude Code / Agent Skill 格式）。

| Skill | 目录 | 用途 |
|-------|------|------|
| Search CNKI (中国知网) f | [`ylx_cnki_search/`](ylx_cnki_search/) | Search CNKI (中国知网) for papers by keyword. Use when the user  |
| ABaCAS 平台操纵 | [`abacas-cloud-ops/`](abacas-cloud-ops/) | ABaCAS Cloud 平台任务/文件/费效评估/结果导入与本地可视化（9 个脚本） |
| n8n 工作流操纵 | [`n8n-web-ops/`](n8n-web-ops/) | n8n 网页操纵：登录、执行记录只读查看、callback_token 自动提取 |
| 科研文献证据工程（ylx） | [`ylx_research_evidence_synthesis/`](ylx_research_evidence_synthesis/) | ylx·科研文献证据工程与 Related Work 写作：Claim-first（证据矩阵 + 逻辑树 + 综述），含输出样例 |

## 使用方式

每个 skill 目录内含 `SKILL.md`，为完整执行说明；`scripts/`（如有）为可复用脚本，`examples/`（如有）为产出样例。

> 注：`abacas-cloud-ops` 与 `n8n-web-ops` 中的账号密码、内网 IP、webhook ID、认证服务器地址均已替换为 `<占位符>`，迁移到自己的环境时需对应填写。
