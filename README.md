# zhaowen-skill

可复用 Skill 集合（Claude Code / Agent Skill 格式）。

## 带来源前缀（作者标明归属）

| Skill | 目录 | 用途 |
|-------|------|------|
| 科研文献证据工程（ylx） | [`ylx_research_evidence_synthesis/`](ylx_research_evidence_synthesis/) | ylx·科研文献证据工程与 Related Work 写作：Claim-first（证据矩阵 + 逻辑树 + 综述），含输出样例 |
| one-hub 用量监测（ylx） | [`ylx_onehub_usage_monitor/`](ylx_onehub_usage_monitor/) | 监测 one-hub API 用量与费用：总额度/已用/剩余、每日每月记账、各模型单价对比 |
| 微信公众号后台（clz） | [`clz_wechat_mp_ops/`](clz_wechat_mp_ops/) | 微信公众号后台操作（登录/草稿/编辑，ProseMirror dispatch+保存；配图 HTML→截图→裁剪；xlsx 保真处理） |

## 其他自制 Skill（无前缀）

| Skill | 目录 | 用途 |
|-------|------|------|
| ABaCAS 平台操纵 | [`abacas-cloud-ops/`](abacas-cloud-ops/) | ABaCAS Cloud 平台任务/文件/费效评估/结果导入与本地可视化（9 个脚本） |
| n8n 工作流操纵 | [`n8n-web-ops/`](n8n-web-ops/) | n8n 网页操纵：登录、执行记录只读查看、callback_token 自动提取 |
| CNKI 基础搜索 | [`cnki-search/`](cnki-search/) | CNKI 关键词检索论文 |
| CNKI 高级搜索 | [`cnki-advanced-search/`](cnki-advanced-search/) | 字段过滤（作者/标题/期刊/日期/来源类别） |
| CNKI 论文下载 | [`cnki-download/`](cnki-download/) | 下载论文 PDF/CAJ（需登录态） |
| CNKI 导出 | [`cnki-export/`](cnki-export/) | 导出到 Zotero / 保存 RIS |
| CNKI 期刊收录 | [`cnki-journal-index/`](cnki-journal-index/) | 北大核心/CSSCI/CSCD/SCI/EI 收录查询 |
| CNKI 期刊搜索 | [`cnki-journal-search/`](cnki-journal-search/) | 期刊搜索 |
| CNKI 期刊目录 | [`cnki-journal-toc/`](cnki-journal-toc/) | 期刊目录浏览 / TOC PDF 下载 |
| CNKI 翻页排序 | [`cnki-navigate-pages/`](cnki-navigate-pages/) | 翻页 / 排序 |
| CNKI 论文详情 | [`cnki-paper-detail/`](cnki-paper-detail/) | 标题/作者/单位/摘要/关键词/基金提取 |
| CNKI 结果解析 | [`cnki-parse-results/`](cnki-parse-results/) | 解析搜索结果列表为结构化数据 |
| 智能体对话管理 | [`agent-dialog_management/`](agent-dialog_management/) | Claude Code + Codex 对话统一列表/搜索/恢复/导出 |
| 横纵分析法 | [`hv-analysis/`](hv-analysis/) | 系统性深度研究（产品/公司/概念/人物） |
| 公众号长文写作 | [`khazix-writer/`](khazix-writer/) | 数字生命卡兹克公众号长文（四层自检） |
| LaTeX 论文写作 | [`latex-paper-writing/`](latex-paper-writing/) | LaTeX 论文写作 / 编译 PDF |
| MEMORY 整理 | [`memory-organizer/`](memory-organizer/) | MEMORY 笔记整理工作流 |
| Obsidian 知识库工作流 | [`obsidian-wiki-workflow/`](obsidian-wiki-workflow/) | LLM Wiki 知识库构建 / MEMORY→OUTPUT 同步 |
| PPT 双卡片组装 | [`ppt-assembler/`](ppt-assembler/) | 读指南→GPT 生成 python-pptx 代码→.pptx |
| PM2.5 日均浓度 | [`process-daily-pm25/`](process-daily-pm25/) | 小时监测数据转日均（≥20 有效小时质控） |
| PPT 提示词审计 | [`prompt-auditor/`](prompt-auditor/) | 逐条对照源码验证提示词事实声明 |
| 微信消息桥接 | [`wechat-claude-code/`](wechat-claude-code/) | 微信中与 Claude Code 聊天 |

## 使用方式

每个 skill 目录内含 `SKILL.md`，为完整执行说明；`scripts/`（如有）为可复用脚本，`examples/`（如有）为产出样例。

> 注：`abacas-cloud-ops` 与 `n8n-web-ops` 中的账号密码、内网 IP、webhook ID、认证服务器地址均已替换为 `<占位符>`，迁移到自己的环境时需对应填写。
