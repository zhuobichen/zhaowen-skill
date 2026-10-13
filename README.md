# zhaowen-skill

可复用 Skill 集合（Claude Code / Agent Skill 格式）。

## 带来源前缀（作者标明归属）

| Skill | 目录 | 用途 |
|-------|------|------|
| 英雄联盟「海克斯大乱斗」(海斗/ARAM | [`aram-mayhem-assistant/`](aram-mayhem-assistant/) | 英雄联盟「海克斯大乱斗」(海斗/ARAM) 分析助手：数对局、复盘单局、查符文与英雄、看趋势/画像/出装/对位/队友、跨 |
| docx 转公众号（clz） | [`clz_docx_to_mp/`](clz_docx_to_mp/) | 把 docx 转成公众号图文并推送草稿箱：解析 → 渲染微信兼容 HTML → 推送。内容忠实保留只做样式；含横滑相册、GIF 动效、平台硬限制实测记录 |
| 科研文献证据工程（ylx） | [`ylx_research_evidence_synthesis/`](ylx_research_evidence_synthesis/) | ylx·科研文献证据工程与 Related Work 写作：Claim-first（证据矩阵 + 逻辑树 + 综述），含输出样例 |
| one-hub 用量监测（ylx） | [`ylx_onehub_usage_monitor/`](ylx_onehub_usage_monitor/) | 监测 one-hub API 用量与费用：总额度/已用/剩余、每日每月记账、各模型单价对比 |
| 操作微信公众号后台（clz） | [`clz_wechat_mp_ops/`](clz_wechat_mp_ops/) | 操作微信公众号后台（mp.weixin.qq.com）：登录与扫码（stealth/chrome-direct）、草稿箱/发表记录、读取与编辑图文草稿（标题/正文）、上传图片、获取草稿 appmsgid。含 ProseMirror 编辑器**唯一可靠的正文改法**（dispatch + 点「保存为草稿」）、token 过期与自动保存陷阱、配套的配图生成（HTML→整页截图→PIL 裁剪）与日程图工具链 |

## 其他自制 Skill（无前缀）

| Skill | 目录 | 用途 |
|-------|------|------|
| 科研论文绘图（Nature 投稿级） | [`nature-figure/`](nature-figure/) | 投 Nature 系及高影响期刊的科研配图：Python（matplotlib/seaborn）或 R（ggplot2）多面板图，出图前先定结论、证据逻辑、数据完整性与审稿风险，导出 SVG/PDF/TIFF；另含 AI 生成的机制示意图/图形摘要通道 |
| ML 论文绘图 | [`academic-plotting/`](academic-plotting/) | 从论文上下文提取系统组件与关系生成架构图；从实验数据自动选图型并用 matplotlib/seaborn 生成数据图 |
| 概念问答沉淀 | [`kb-capture/`](kb-capture/) | 说一句「存知识库」即把当前对话里的概念性问答沉淀成知识库原子卡片并 push：先 `search` 判重，命中则读全文后合并、未命中则新建；卡片与索引同步放在同一次提交，写盘前做敏感与卡片规范校验 |
| 公众号模板库 | [`mp-template-lib/`](mp-template-lib/) | 把「看到一个好排版」变成「能吃进来的可复用主题」：`extract_theme.py` 从一篇已发表文章（URL 或 HTML）反推设计令牌、组件形态与对照图，存进 `templates/<主题名>/` 供排版流程取用。触发词：套模板、反推模板、模板库、仿这个排版。不用于写文章（用 khazix-writer）与渲染本身（用 clz_docx_to_mp） |
| ABaCAS 平台操纵 | [`abacas-cloud-ops/`](abacas-cloud-ops/) | ABaCAS Cloud 平台任务/文件/费效评估/结果导入与本地可视化（9 个脚本） |
| n8n 工作流操纵 | [`n8n-web-ops/`](n8n-web-ops/) | n8n 网页操纵：登录、执行记录只读查看、callback_token 自动提取 |
| 网申表单速填 | [`job-form-autofill/`](job-form-autofill/) | 按简历填任意网页的求职/网申表单：闭合选项（下拉/单选）交给 Jev 一次批量判定，需要写字的由助手依据简历生成；**绝不提交**，没依据的一律留空并列出"需要你提供"清单 |
| 中石油网申填表 | [`cnpc-job-apply/`](cnpc-job-apply/) | 中石油高校毕业生招聘平台（zhaopin.cnpc.com.cn）校招网申简历填写：browser-act 填表原语、字段 id 清单、维护时间窗口、承诺告知书保存流程、CDP 混用陷阱 |
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
| 真正搞懂（分层解释法） | [`layered-explainer/`](layered-explainer/) | 两个方向：**A 读**——把看不下去的长输出按理解成本逐级升级（受控语言 ASD-STE100 → 一张图 → 单文件交互 HTML → Manim 视频）；**B 讲**——反过来让你输出、AI 评判（学习阶梯 → 只学最重要的 20% → 当考官一次只问一问 → 一页速查表 → 筛资源 → 费曼法）。每一步都配了失败模式与检查项，含「AI 说你做对了」不算通过 |
| 公众号长文写作 | [`khazix-writer/`](khazix-writer/) | 数字生命卡兹克（Khazix）风格的公众号长文写作（四层自检体系）。触发：写文章、写稿子、续写、扩写、按我的风格写，或丢来 PDF/brief/链接/语音转写说「帮我写篇文章」。不用于小红书/推特等短内容 |
| LaTeX 论文写作 | [`latex-paper-writing/`](latex-paper-writing/) | LaTeX 论文写作 / 编译 PDF |
| MEMORY 整理 | [`memory-organizer/`](memory-organizer/) | MEMORY 笔记整理工作流 |
| Obsidian 知识库工作流 | [`obsidian-wiki-workflow/`](obsidian-wiki-workflow/) | LLM Wiki 知识库构建 / MEMORY→OUTPUT 同步 |
| PPT 双卡片组装 | [`ppt-assembler/`](ppt-assembler/) | 读指南→GPT 生成 python-pptx 代码→.pptx |
| PM2.5 日均浓度 | [`process-daily-pm25/`](process-daily-pm25/) | 小时监测数据转日均（≥20 有效小时质控） |
| PPT 提示词审计 | [`prompt-auditor/`](prompt-auditor/) | 逐条对照源码验证提示词事实声明 |
| 微信消息桥接 | [`wechat-claude-code/`](wechat-claude-code/) | 微信中与 Claude Code 聊天 |
| 本机活动痕迹检查 | [`windows_activity_forensics/`](windows_activity_forensics/) | 某段时间本机有没有被人用过 / 远程连进来 / 翻过浏览历史 / 登录过谁的小号 / 用你的登录态上过网站 / 翻过你和 AI 的聊天 / 拷过东西 / 痕迹被抹过；29 项三态检查，报告开头先给一句白话结论 |
| 大文件 AI 审核范式 | [`large-doc-ai-review/`](large-doc-ai-review/) | 几十到几百页 PDF/Word 的 AI 审核工程套路：目录树定位证据窗口、Prompt 契约（`.md` + `_spec.json` 双文件）、五档结论与人工复核边界、置信度降级兜底、进程锁与心跳；附 `check_verdict_order.py` 强制"结论字段写在证据字段之后"（已对 227 个真实 prompt/spec 零误报验证） |
| Zotero Word 活字段引用 | [`zotero-word-citations/`](zotero-word-citations/) | 把 Word 手稿里的 author-year **文字引用**变成 Zotero 活字段，并生成「引用 ↔ 参考文献可点击跳转」的定稿版。适用：要在 Word 里用 Zotero 管引用而不想手工插文献；拿到一份引用是死文字的稿子；抱怨「点引用跳不到参考文献」 |
| Zotero 文献管理 | [`zotero/`](zotero/) | 用 Zotero 做文献管理、PDF 阅读、引用生成与论文写作：按主题/作者检索条目、读全文与批注、导出引用、配 LaTeX 出参考文献 |
| Zotero 数据库直连 | [`zotero-db/`](zotero-db/) | 直接操作 Zotero 本地 SQLite：批量导入 PDF、生成 citation key、建全文索引、清理孤儿条目；Zotero API 不可用时的兜底通道 |

## 借鉴自 Tiangong AI Skills

以下 Skill 从 [`tiangong-ai/agent-skills`](https://github.com/tiangong-ai/agent-skills)
迁入，保留其工作流与安全边界，并通过 `UPSTREAM_SOURCES.md` 记录来源提交。

| Skill | 目录 | 用途 |
|-------|------|------|
| Academic Paper Download | [`academic-paper-download/`](academic-paper-download/) | 通过 DOI/精确标题获取经过身份、结构、哈希和许可证来源校验的开放获取论文 PDF |
| Document Granular Decompose | [`document-granular-decompose/`](document-granular-decompose/) | 调用 TianGong Unstructure 对本地文档做细粒度全文解析 |
| Convert Image To JPG | [`convert-image-to-jpg/`](convert-image-to-jpg/) | 将常见栅格图片批量转换为指定 DPI 的 JPG |
| Remove Similar Image | [`remove-similar-image/`](remove-similar-image/) | 检测近似重复和模糊图片，并在确认后清理 |
| Reverse Engineer Anything | [`reverse-engineer-anything/`](reverse-engineer-anything/) | 用 REA 逆向成品而非源码：原生二进制、Electron/ASAR、APK、.NET/固件、浏览器端；给出「这个包/这个 App 到底做了什么」的证据化结论。装的是方法说明，REA MCP 与分析引擎需另行接入 |

## 借鉴自腾讯 BrowserSkill

[`Tencent/BrowserSkill`](https://github.com/Tencent/BrowserSkill)（MIT）由 `bsk` CLI 分发到本机
`~/.claude/skills/browser-skill`，此处为发布快照，便于查阅与参考。

| Skill | 目录 | 用途 |
|-------|------|------|
| Browser Skill | [`browser-skill/`](browser-skill/) | 在独立 Agent Window 里驱动你**已登录的** Chrome/Edge：读页面、填表、抓数据、调试网站；借用用户已打开的标签页需显式确认，验证码/OTP/支付等关键节点可交还人工。由 `bsk` CLI + 本地 daemon + 浏览器扩展三段组成，支持 Claude Code / Codex / Cursor / OpenClaw 等调用 Shell 的智能体 |

> ⚠️ 本目录**不是权威副本**。权威来源是本机 `~/.claude/skills/browser-skill`，由 `bsk install-skill`
> 安装并自管版本。上游更新时：`bsk update` → `bsk install-skill` 刷新本机 → 与本目录 `git diff`
> 对比 → 按需重新发布。目录内 `.bsk-source` 是内容哈希清单（可用于判断上游是否变过），
> `.bsk.lock` 是运行时锁文件。

## 使用方式

每个 skill 目录内含 `SKILL.md`，为完整执行说明；`scripts/`（如有）为可复用脚本，`examples/`（如有）为产出样例。

机器可读清单见 [`skill-catalog.json`](skill-catalog.json)，其中包含 `display_name`、UI 元数据路径与上游来源标记（`publish_skill` 会读这里的 `display_name` 作为 README 的 Skill 列）。新增或迁移 Skill 后应同步更新清单，并用 skill-manager MCP 的 `validate_skill` 做结构校验（校验 MCP 服务用 `validate_mcp`）。

> 注：`abacas-cloud-ops` 与 `n8n-web-ops` 中的账号密码、内网 IP、webhook ID、认证服务器地址均已替换为 `<占位符>`，迁移到自己的环境时需对应填写。
