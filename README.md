# zhaowen-skill

可复用 Skill 集合（Claude Code / Agent Skill 格式）。

目录分两类：**自制**（下面前两节）与**别人做的、上游迁入**（「上游迁入的第三方 Skill」一节）。
第三方目录的版权归上游作者，每个目录内都带上游 `LICENSE`；只给链接不存内容的见
[`INDEXED_SKILLS.md`](INDEXED_SKILLS.md)。

## 自制 Skill

`clz` 标记的是本人在另一台机器上的产出；`ylx` 标记的见下一节（他人产出、已标明归属）。

| Skill | 目录 | 用途 |
|-------|------|------|
| 英雄联盟「海克斯大乱斗」（海斗/ARAM） | [`aram-mayhem-assistant/`](aram-mayhem-assistant/) | 数对局、复盘单局、查符文与英雄、看趋势/画像/出装/对位/队友、跨账号对比、导出报告 |
| docx 整页替换 | [`docx-page-replace/`](docx-page-replace/) | 在 .docx 里按**文本锚点**删掉一段正文（段落或表格行），原位插入「一图一页」的图片：把空白考核表页换成签字盖章扫描件、把整节换成扫描附件、往报告末尾插几页图。纯标准库实现（不需要 python-docx），带 `list` / `replace` / `check` 三个子命令；拒绝歧义锚点、拒绝覆盖原文件，`check` 校验 zip/XML/关系引用/图片是否超出版心。三个真踩过的坑写在 SKILL.md 里（DrawingML 命名空间、删表要补闭合标签、图宽贴满会多挤出一页） |
| docx 转公众号（clz） | [`docx_to_mp/`](docx_to_mp/) | 把 docx 转成公众号图文并推送草稿箱：解析 → 渲染微信兼容 HTML → 推送。内容忠实保留只做样式；含横滑相册、GIF 动效、平台硬限制实测记录 |
| 操作微信公众号后台（clz） | [`wechat_mp_ops/`](wechat_mp_ops/) | 操作微信公众号后台（mp.weixin.qq.com）：登录与扫码（stealth/chrome-direct）、草稿箱/发表记录、读取与编辑图文草稿（标题/正文）、上传图片、获取草稿 appmsgid。含 ProseMirror 编辑器**唯一可靠的正文改法**（dispatch + 点「保存为草稿」）、token 过期与自动保存陷阱、配套的配图生成（HTML→整页截图→PIL 裁剪）与日程图工具链 |
| air-journal-intro-writing | [`air-journal-intro-writing/`](air-journal-intro-writing/) | 空气/环境类期刊 Introduction / 研究背景写作法，实证自 Atmospheric Environment（16 篇）、Aerosol and Air Quality Research（14 篇）与 Sustainability… |
| pup-cleanup | [`pup-cleanup/`](pup-cleanup/) | 清理本机流氓软件/开机弹窗广告：找出推广告的"壳"、用官方卸载器卸、卸不动的走隔离；含自启动普查、登录后执行痕迹、按厂商识别推广家族。 |
| dsh_messaging | [`dsh_messaging/`](dsh_messaging/) | 用官方 CLI 从外部给 DeepSeek Harness (DSH) 发消息、续接既有会话、拿结构化输出与 token 用量。 |
| 看 DSH 会话 | [`dsh-session-viewer/`](dsh-session-viewer/) | 只读直翻本机 DSH 会话文件：列会话（带侧栏分组）、全文搜索「我什么时候提过 X」、定位「会话不见了」、按轮次查看、导出 Markdown。含三个必踩坑：多帧 zstd 只解出第一帧、正文在 `data` 里、注入上下文混在 user 消息中 |
| 豆包会话管理 | [`doubao-session-management/`](doubao-session-management/) | 豆包桌面版会话的导出、时间线、批量删除：CDP 挂 9222 从 DOM 抓正文+`<TIME>`、脱敏 md、来时路 HTML、按"多久没动"批量删（已验证删 270+ 个）。核心坑：正文在云端本地库只有元数据、CDP 连的是隐藏小窗口坐标全负、菜单必须用完整鼠标事件序列触发、删除间隔要够否则 NO_DIALOG |
| 手机拍照转扫描件 | [`photo-to-scan/`](photo-to-scan/) | 把手机拍的纸页照片变成平直扫描件（扫描全能王那种观感）：自动判 0/90/180/270、纠偏、去阴影黑边、裁成 A4 比例、出 JPG/PNG/多页 PDF，红章与手写保留。纯按经典算法实现（OpenCV 透视 + 投影轮廓纠偏 + 平场去光照 + Sauvola 二值化与彩色层合成），离线可跑；附上游方案调研笔记 |
| 用 AI 操作手机 | [`android-phone-ops/`](android-phone-ops/) | 配套 `android` MCP 操作模拟器/真机：构建装包、点界面、读层级、截图、**输入中文**、看日志，也包括"帮我在手机上干件事"这类委托。写的是流程与纪律（开工先 `status`+`prepare`、用 `wait_idle` 替 sleep、能按文字就别按坐标、发送/登录类动作先确认），工具清单不重复 MCP 的 README；**禁区**（如 QQ/微信的「空间」）在工具层强制拦截，命中就停手交回给用户 |
| 概念问答沉淀 | [`kb-capture/`](kb-capture/) | 说一句「存知识库」即把当前对话里的概念性问答沉淀成知识库原子卡片并 push：先 `search` 判重，命中则读全文后合并、未命中则新建；卡片与索引同步放在同一次提交，写盘前做敏感与卡片规范校验 |
| 公众号模板库 | [`mp-template-lib/`](mp-template-lib/) | 把「看到一个好排版」变成「能吃进来的可复用主题」：`extract_theme.py` 从一篇已发表文章（URL 或 HTML）反推设计令牌、组件形态与对照图，存进 `templates/<主题名>/` 供排版流程取用。触发词：套模板、反推模板、模板库、仿这个排版。不用于写文章（用 khazix-writer）与渲染本身（用 docx_to_mp） |
| 技术博客多平台分发 | [`dev-blog-distribution/`](dev-blog-distribution/) | 把一篇技术长文铺到 CSDN / 知乎 / 掘金 / 腾讯云开发者（附博客园、开源中国、思否的实测特征）：**一稿一角度**的差异化矩阵（对抗判重与推荐降权）、各站发布器的真实控件与标签规则（腾讯云标签必须下拉选、掘金分类必选、CSDN 等级<3 不能建自定义标签）、bsk 在窗口最小化/编辑器是 CodeMirror·Draft·cledit 时的可靠操作法（`evaluate` 原生点击、剪贴板粘贴、sync+observation 配对）、发布只点一次并事后核对 |
| ABaCAS 平台操纵 | [`abacas-cloud-ops/`](abacas-cloud-ops/) | ABaCAS Cloud 平台任务/文件/费效评估/结果导入与本地可视化（9 个脚本） |
| n8n 工作流操纵 | [`n8n-web-ops/`](n8n-web-ops/) | n8n 网页操纵：登录、执行记录只读查看、callback_token 自动提取 |
| 网申表单速填 | [`job-form-autofill/`](job-form-autofill/) | 按简历填任意网页的求职/网申表单：闭合选项（下拉/单选）交给 Jev 一次批量判定，需要写字的由助手依据简历生成；**绝不提交**，没依据的一律留空并列出"需要你提供"清单 |
| 中石油网申填表 | [`cnpc-job-apply/`](cnpc-job-apply/) | 中石油高校毕业生招聘平台（zhaopin.cnpc.com.cn）校招网申简历填写：browser-act 填表原语、字段 id 清单、维护时间窗口、承诺告知书保存流程、CDP 混用陷阱 |
| 智能体对话管理 | [`agent-dialog_management/`](agent-dialog_management/) | Claude Code + Codex 对话统一列表/搜索/恢复/导出 |
| 会话考古 | [`session-archaeology/`](session-archaeology/) | 找回"记得做过但找不到"的会话/产物：按执行痕迹（命令/路径/扩展名/模型名）而非内容词搜索，跨 DSH/Codex/Claude 统计排序并反推产物；含轻量扫描脚本，找到后用正式工具查看 |
| 录音有效性检测 | [`audio-validity-check/`](audio-validity-check/) | 严格判断录音里有没有真语音（vs 音乐/噪音）：能量粗筛→Silero VAD 神经网判定→关闭 VAD 强制转写终审；含三阶段脚本与"音乐被误判为7分钟语音"的血泪教训，用于决定能否转写/能否删原音频 |
| Claude 用量与费用分析 | [`claude-usage-billing/`](claude-usage-billing/) | 把 one-hub 账单 CSV + `~/.claude/projects` 日志出成 HTML：主会话与其subagent 合并成"任务"，定位当天最烧钱的会话/子Agent，可展开每个子Agent 的任务指令与最终产出；附子Agent 轨迹持久化结论（关机不丢，真丢只因 30 天清理） |
| 拆解原理（从零讲基本功） | [`principle-dissection/`](principle-dissection/) | 把你自己刚做完的产物（代码/系统/流程/AI 帮你搭的）拆成「它用到的每一门基本功」并从零讲清：是什么 → 这个领域的标准手段 → 我这项目用的是哪一种（术语先定义、配最小例子）。主体是知识不是「验收」，「能不能判错」只作可选验收。动手前先读学习者基线、跳过已会的。不要用于学别人的材料（用 layered-explainer）/ 拆别人成品（用 reverse-engineer-anything） |
| 真正搞懂（分层解释法） | [`layered-explainer/`](layered-explainer/) | 两个方向：**A 读**——把看不下去的长输出按理解成本逐级升级（受控语言 ASD-STE100 → 一张图 → 单文件交互 HTML → Manim 视频）；**B 讲**——反过来让你输出、AI 评判（学习阶梯 → 只学最重要的 20% → 当考官一次只问一问 → 一页速查表 → 筛资源 → 费曼法）。每一步都配了失败模式与检查项，含「AI 说你做对了」不算通过 |
| LaTeX 论文写作 | [`latex-paper-writing/`](latex-paper-writing/) | LaTeX 论文写作 / 编译 PDF |
| MEMORY 整理 | [`memory-organizer/`](memory-organizer/) | MEMORY 笔记整理工作流 |
| Obsidian 知识库工作流 | [`obsidian-wiki-workflow/`](obsidian-wiki-workflow/) | LLM Wiki 知识库构建 / MEMORY→OUTPUT 同步 |
| PPT 双卡片组装 | [`ppt-assembler/`](ppt-assembler/) | 读指南→GPT 生成 python-pptx 代码→.pptx |
| PM2.5 日均浓度 | [`process-daily-pm25/`](process-daily-pm25/) | 小时监测数据转日均（≥20 有效小时质控） |
| PPT 提示词审计 | [`prompt-auditor/`](prompt-auditor/) | 逐条对照源码验证提示词事实声明 |
| 本机活动痕迹检查 | [`windows_activity_forensics/`](windows_activity_forensics/) | 某段时间本机有没有被人用过 / 远程连进来 / 翻过浏览历史 / 登录过谁的小号 / 用你的登录态上过网站 / 翻过你和 AI 的聊天 / 拷过东西 / 痕迹被抹过；29 项三态检查，报告开头先给一句白话结论 |
| 大文件 AI 审核范式 | [`large-doc-ai-review/`](large-doc-ai-review/) | 几十到几百页 PDF/Word 的 AI 审核工程套路：目录树定位证据窗口、Prompt 契约（`.md` + `_spec.json` 双文件）、五档结论与人工复核边界、置信度降级兜底、进程锁与心跳；附 `check_verdict_order.py` 强制"结论字段写在证据字段之后"（已对 227 个真实 prompt/spec 零误报验证） |
| Zotero Word 活字段引用 | [`zotero-word-citations/`](zotero-word-citations/) | 把 Word 手稿里的 author-year **文字引用**变成 Zotero 活字段，并生成「引用 ↔ 参考文献可点击跳转」的定稿版。适用：要在 Word 里用 Zotero 管引用而不想手工插文献；拿到一份引用是死文字的稿子；抱怨「点引用跳不到参考文献」 |
| Zotero 文献管理 | [`zotero/`](zotero/) | 用 Zotero 做文献管理、PDF 阅读、引用生成与论文写作：按主题/作者检索条目、读全文与批注、导出引用、配 LaTeX 出参考文献 |
| 只读副屏 | [`second-screen-display/`](second-screen-display/) | 把旧手机/墨水屏/实体副屏做成**只显示不操作**的第二块屏：本机一个 HTTP 服务喂画面（仪表盘/远端桌面/电子书），设备端只负责显示。涵盖 USB 反向隧道（adb reverse，不依赖网络）、局域网 HTTP、mDNS 固定名字、PrintWindow 抓远端窗口（**最小化即黑图**）、DXGI 与混合显卡下的"假黑"、MIUI 安装/输入门禁、墨水屏转载与屏保路径、CursorKeeper 锁鼠标（自写 ClipCursor 必须 DPI 感知，否则桌面点不动） |
| Zotero 数据库直连 | [`zotero-db/`](zotero-db/) | 直接操作 Zotero 本地 SQLite：批量导入 PDF、生成 citation key、建全文索引、清理孤儿条目；Zotero API 不可用时的兜底通道 |
| AI 炼书（md-to-ebook） | [`md-to-ebook/`](md-to-ebook/) | 把 Markdown 素材 + AI 逐章写作 + ReportLab 排版做成一本书：`book.yaml` 写 meta/source/chapters，`scripts/cli.py write` 逐章生成、`build` 合并去重出中文 PDF（A4、simhei、CJK 字间距）。含三本实战配置（Claude Code / IM 工具 / 数字人文）与三种风格。**关键**：源项目的 md2book 七步流水线（analyze/plan/refine/review/export）大部分是 `not_implemented` 占位，本 skill 用的是真正跑通的 write/build/run 链路；已修掉 API key 硬编码、work_dir 硬编码、Windows GBK 控制台遇 emoji 崩溃三个坑 |
| Tailscale 只读共享 | [`tailscale-smb-readonly/`](tailscale-smb-readonly/) | 用 Tailscale + SMB 把另一台 Windows 的文件夹挂成本机**只读盘符**（跨网段也行，不用装 SSH）。七个实测坑：盘符只能单字母（`C1:` 非法）、只跑服务不跑托盘客户端时 CLI 一断后端即停（日志 `client disconnected … disconnecting Tailscale`）、一次性 authkey 用过即失效而节点身份可从 `server-state.conf` 恢复（无需新密钥）、`up` 要求显式列非默认项、`net use` 传含特殊字符密码会被 PowerShell 拆坏、映射空闲显示 Disconnected 属正常、凭据不入库则重启要重输。含 `join-and-mount.ps1`（`-DryRun` / `-Unmount`）与只读验收三条（读通、写拒、删拒） |

## 他人产出（`ylx` 标记，已标明归属）

| Skill | 目录 | 用途 |
|-------|------|------|
| 科研文献证据工程（ylx） | [`research_evidence_synthesis/`](research_evidence_synthesis/) | ylx·科研文献证据工程与 Related Work 写作：Claim-first（证据矩阵 + 逻辑树 + 综述），含输出样例 |
| one-hub 用量监测（ylx） | [`onehub_usage_monitor/`](onehub_usage_monitor/) | 监测 one-hub API 用量与费用：总额度/已用/剩余、每日每月记账、各模型单价对比 |

## 上游迁入的第三方 Skill（内置副本）

这些**是别人的作品**，版权归上游作者，不是本仓库作者。每个目录内都放有上游 `LICENSE`；
来源与提交号见 [`UPSTREAM_SOURCES.md`](UPSTREAM_SOURCES.md)，许可证汇总见
[`THIRD_PARTY.md`](THIRD_PARTY.md)，同步方式见 [`SYNC.md`](SYNC.md)。
改动这些目录时请保留 `LICENSE`，并用目录内 `LOCAL_CHANGES.md` 说明改了什么。

| Skill | 目录 | 上游 | 许可证 | 本地情况 |
|-------|------|------|--------|----------|
| Nature Figure | [`nature-figure/`](nature-figure/) | [`Yuan1z0825/nature-skills`](https://github.com/Yuan1z0825/nature-skills) | **Apache-2.0** | 旧快照 v2.1.0（上游 2.8.0），删减与改动见 `LOCAL_CHANGES.md` |
| Academic Plotting | [`academic-plotting/`](academic-plotting/) | [`Orchestra-Research/AI-Research-SKILLs`](https://github.com/Orchestra-Research/AI-Research-SKILLs) | MIT | 与上游逐字节一致（保留 `.openskills.json` 供追溯） |
| 公众号长文写作 | [`khazix-writer/`](khazix-writer/) | [`KKKKhazix/khazix-skills`](https://github.com/KKKKhazix/khazix-skills) | MIT | 旧版/扩写版，非整段照搬，同步时手工合并 |
| 横纵分析法 | [`hv-analysis/`](hv-analysis/) | [`KKKKhazix/khazix-skills`](https://github.com/KKKKhazix/khazix-skills) | MIT | 方法论由数字生命卡兹克提出；本地有修正 |
| 微信消息桥接 | [`wechat-claude-code/`](wechat-claude-code/) | [`Wechat-ggGitHub/wechat-claude-code`](https://github.com/Wechat-ggGitHub/wechat-claude-code) | MIT | 分支式改写：新增权限审批（`src/permission.ts`）与 Windows 启动，见 `LOCAL_CHANGES.md` |
| 看视频 | [`watch/`](watch/) | [`bradautomates/claude-video`](https://github.com/bradautomates/claude-video) | MIT | v0.3.2 快照；**本地新增** `windows-notes.md`（PATH/TEMP、WhisperX 安装坑、Silero VAD 离线补丁）。把视频变成「时间戳关键帧 + 字幕/转写」两份证据：yt-dlp 下载、ffmpeg 抽帧去重、字幕优先、无字幕走本地 WhisperX；四档 detail 决定 token 成本，`--start/--end` 可只盯一段 |

### 分项：Tiangong AI Skills

以下 Skill 从 [`tiangong-ai/agent-skills`](https://github.com/tiangong-ai/agent-skills)
迁入，保留其工作流与安全边界，并通过 `UPSTREAM_SOURCES.md` 记录来源提交。

| Skill | 目录 | 用途 |
|-------|------|------|
| Academic Paper Download | [`academic-paper-download/`](academic-paper-download/) | 通过 DOI/精确标题获取经过身份、结构、哈希和许可证来源校验的开放获取论文 PDF |
| Document Granular Decompose | [`document-granular-decompose/`](document-granular-decompose/) | 调用 TianGong Unstructure 对本地文档做细粒度全文解析 |
| Convert Image To JPG | [`convert-image-to-jpg/`](convert-image-to-jpg/) | 将常见栅格图片批量转换为指定 DPI 的 JPG |
| Remove Similar Image | [`remove-similar-image/`](remove-similar-image/) | 检测近似重复和模糊图片，并在确认后清理 |
| Reverse Engineer Anything | [`reverse-engineer-anything/`](reverse-engineer-anything/) | 用 REA 逆向成品而非源码：原生二进制、Electron/ASAR、APK、.NET/固件、浏览器端；给出「这个包/这个 App 到底做了什么」的证据化结论。装的是方法说明，REA MCP 与分析引擎需另行接入 |

### 分项：腾讯 BrowserSkill

[`Tencent/BrowserSkill`](https://github.com/Tencent/BrowserSkill)（MIT）由 `bsk` CLI 分发到本机
`~/.claude/skills/browser-skill`，此处为发布快照，便于查阅与参考。

| Skill | 目录 | 用途 |
|-------|------|------|
| Browser Skill | [`browser-skill/`](browser-skill/) | 在独立 Agent Window 里驱动你**已登录的** Chrome/Edge：读页面、填表、抓数据、调试网站；借用用户已打开的标签页需显式确认，验证码/OTP/支付等关键节点可交还人工。由 `bsk` CLI + 本地 daemon + 浏览器扩展三段组成，支持 Claude Code / Codex / Cursor / OpenClaw 等调用 Shell 的智能体 |

> ⚠️ 本目录**不是权威副本**。权威来源是本机 `~/.claude/skills/browser-skill`，由 `bsk install-skill`
> 安装并自管版本。上游更新时：`bsk update` → `bsk install-skill` 刷新本机 → 与本目录 `git diff`
> 对比 → 按需重新发布。目录内 `.bsk-source` 是内容哈希清单（可用于判断上游是否变过），
> `.bsk.lock` 是运行时锁文件。

## 只索引、未内置

| Skill 组 | 上游 | 为什么只索引 |
|----------|------|--------------|
| CNKI（知网）10 个：检索 / 高级检索 / 翻页 / 论文详情 / 期刊收录 / 期刊目录 / 下载 / 导出 | [`cookjohn/cnki-skills`](https://github.com/cookjohn/cnki-skills) | 上游**没有 LICENSE**（默认保留所有权利），不再分发副本 |

安装方式与能力说明见 [`INDEXED_SKILLS.md`](INDEXED_SKILLS.md)。

## 使用方式

每个 skill 目录内含 `SKILL.md`，为完整执行说明；`scripts/`（如有）为可复用脚本，`examples/`（如有）为产出样例。

机器可读清单见 [`skill-catalog.json`](skill-catalog.json)，其中包含 `display_name`、UI 元数据路径与上游来源标记（`publish_skill` 会读这里的 `display_name` 作为 README 的 Skill 列）。`skills[]` 里是有目录的条目，`index_only[]` 里是只给上游链接、不在本仓库放内容的条目。新增或迁移 Skill 后应同步更新清单，并用 skill-manager MCP 的 `validate_skill` 做结构校验（校验 MCP 服务用 `validate_mcp`）。

## 来源与许可证

| 文件 | 作用 |
|------|------|
| [`UPSTREAM_SOURCES.md`](UPSTREAM_SOURCES.md) | 每个外来 skill 的上游仓库、提交号、迁入方式、许可证、本地改动要点 |
| [`THIRD_PARTY.md`](THIRD_PARTY.md) | 第三方内容汇总：许可证分组、版权方、不属于任何许可证的部分 |
| [`INDEXED_SKILLS.md`](INDEXED_SKILLS.md) | 只索引不内置的上游（目前是 CNKI 10 个）与其安装命令 |
| [`SYNC.md`](SYNC.md) | 每类外来 skill 的同步方式（快照型 / 跟版本型 / 改写型 / bsk 自管） |

本仓库自身内容（无上游记录的目录）暂未声明许可证；外来目录各自带上游 `LICENSE`，不受此影响。

> 注：`abacas-cloud-ops` 与 `n8n-web-ops` 中的账号密码、内网 IP、webhook ID、认证服务器地址均已替换为 `<占位符>`，迁移到自己的环境时需对应填写。