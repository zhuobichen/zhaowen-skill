# zhaowen-skill

可复用 Skill 集合（Claude Code / Agent Skill 格式）。

| Skill | 目录 | 用途 |
|-------|------|------|
| 监测 one-hub API 用量与费用 | [`ylx_onehub_usage_monitor/`](ylx_onehub_usage_monitor/) | 监测 one-hub API 用量与费用：查询总额度/已用/剩余(美元+人民币)、每日/每月记账、各模型 one-hub |
| 微信公众号后台操作 | [`clz_wechat_mp_ops/`](clz_wechat_mp_ops/) | 微信公众号后台操作（登录/草稿/编辑，ProseMirror dispatch+保存按钮唯一可靠改法；配图生成 HTML→截图→PIL 裁剪；WPS 问题 xlsx 用 zipfile XML 解析） |
| 审计 PPT 提示词准确性——逐条对照源 | [`ylx_prompt_auditor/`](ylx_prompt_auditor/) | 审计 PPT 提示词准确性——逐条对照源码验证每个事实声明（数字/公式/逻辑），给出 ✅/⚠️/❌ 结论及源码行号。当用 |
| GPT-5 | [`ylx_ppt_assembler/`](ylx_ppt_assembler/) | GPT-5.5 组装 PPTX——读 PPT 制作指南 → 发 GPT-5.5 生成 python-pptx 代码 →  |
| MEMORY笔记整理工作流 - 从原始文 | [`ylx_memory_organizer/`](ylx_memory_organizer/) | MEMORY笔记整理工作流 - 从原始文档提取精华、建立链接、定期维护 |
| > | [`ylx_latex_paper_writing/`](ylx_latex_paper_writing/) | > |
| This skill should be | [`ylx_process_daily_pm25/`](ylx_process_daily_pm25/) | This skill should be used when converting hourly PM2.5 stati |
| | | [`ylx_obsidian_wiki_workflow/`](ylx_obsidian_wiki_workflow/) | | |
| | | [`ylx_hv_analysis/`](ylx_hv_analysis/) | | |
| | | [`ylx_khazix_writer/`](ylx_khazix_writer/) | | |
| 微信消息桥接 - 在微信中与 Claud | [`ylx_wechat_claude_code/`](ylx_wechat_claude_code/) | 微信消息桥接 - 在微信中与 Claude Code 聊天。支持文字对话、图片识别、权限审批、斜杠命令。 |
| > | [`ylx_agent_dialog_management/`](ylx_agent_dialog_management/) | > |
| Parse current CNKI s | [`ylx_cnki_parse_results/`](ylx_cnki_parse_results/) | Parse current CNKI search results page into structured paper |
| Extract full paper d | [`ylx_cnki_paper_detail/`](ylx_cnki_paper_detail/) | Extract full paper details from a CNKI paper page including  |
| Navigate CNKI search | [`ylx_cnki_navigate_pages/`](ylx_cnki_navigate_pages/) | Navigate CNKI search result pages (next/previous/specific pa |
| Browse journal issue | [`ylx_cnki_journal_toc/`](ylx_cnki_journal_toc/) | Browse journal issues, view table of contents, and download  |
| Search for journals/ | [`ylx_cnki_journal_search/`](ylx_cnki_journal_search/) | Search for journals/publications on CNKI by name, ISSN, CN,  |
| Query journal indexi | [`ylx_cnki_journal_index/`](ylx_cnki_journal_index/) | Query journal indexing/inclusion status on CNKI - check whic |
| Export paper from CN | [`ylx_cnki_export/`](ylx_cnki_export/) | Export paper from CNKI and push to Zotero, or save as RIS fi |
| Download a paper PDF | [`ylx_cnki_download/`](ylx_cnki_download/) | Download a paper PDF/CAJ from CNKI. Requires user to be logg |
| Perform advanced sea | [`ylx_cnki_advanced_search/`](ylx_cnki_advanced_search/) | Perform advanced search on CNKI with field filters like auth |
| Search CNKI (中国知网) f | [`ylx_cnki_search/`](ylx_cnki_search/) | Search CNKI (中国知网) for papers by keyword. Use when the user  |
| ABaCAS 平台操纵 | [`abacas-cloud-ops/`](abacas-cloud-ops/) | ABaCAS Cloud 平台任务/文件/费效评估/结果导入与本地可视化（9 个脚本） |
| n8n 工作流操纵 | [`n8n-web-ops/`](n8n-web-ops/) | n8n 网页操纵：登录、执行记录只读查看、callback_token 自动提取 |
| 科研文献证据工程（ylx） | [`ylx_research_evidence_synthesis/`](ylx_research_evidence_synthesis/) | ylx·科研文献证据工程与 Related Work 写作：Claim-first（证据矩阵 + 逻辑树 + 综述），含输出样例 |

## 使用方式

每个 skill 目录内含 `SKILL.md`，为完整执行说明；`scripts/`（如有）为可复用脚本，`examples/`（如有）为产出样例。

> 注：`abacas-cloud-ops` 与 `n8n-web-ops` 中的账号密码、内网 IP、webhook ID、认证服务器地址均已替换为 `<占位符>`，迁移到自己的环境时需对应填写。
