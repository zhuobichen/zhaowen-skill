# 上游来源记录

本文件记录从外部仓库迁入或借鉴的目录，便于后续同步、审查许可证和定位本地改动。

**判定口径**：只有「本仓库自带内容」的目录才记在上表；只给链接、不存内容的记在
[`INDEXED_SKILLS.md`](INDEXED_SKILLS.md)。每个内置副本的许可证全文放在该目录内的
`LICENSE`（有本地改动的另附 `LOCAL_CHANGES.md`）。

| 本地目录 | 上游仓库 | 上游提交 | 迁入方式 | 许可证 | 备注 |
|---|---|---|---|---|---|
| `academic-paper-download/` | `https://github.com/tiangong-ai/agent-skills` | `5e692461708a4e02c1012086a59d2bd75da99673` | 目录快照 | MIT（`Copyright (c) 2025 linancn`） | 保留 DOI/标题解析、PDF 身份校验、哈希和许可证来源边界 |
| `document-granular-decompose/` | `https://github.com/tiangong-ai/agent-skills` | `5e692461708a4e02c1012086a59d2bd75da99673` | 目录快照 | MIT（同上，已放 `LICENSE`） | 使用前配置 `UNSTRUCTURED_AUTH_TOKEN` 和 API 地址 |
| `convert-image-to-jpg/` | `https://github.com/tiangong-ai/agent-skills` | `5e692461708a4e02c1012086a59d2bd75da99673` | 目录快照 | MIT（同上，已放 `LICENSE`） | 本地图片转换，不上传图片 |
| `remove-similar-image/` | `https://github.com/tiangong-ai/agent-skills` | `5e692461708a4e02c1012086a59d2bd75da99673` | 目录快照 | MIT（同上，已放 `LICENSE`） | 删除/移动前应先查看检测报告 |
| `reverse-engineer-anything/` | `https://github.com/morluto/rea` | `b8fab74` | 目录快照（`.agents/skills/reverse-engineer-anything`） | MIT（`Copyright (c) 2026 morluto`） | 仅装说明，不注册 MCP；分析引擎（Ghidra/JADX/Binwalk 等）需另行安装，SKILL.md 明确禁止顺手升级无关软件。**本地新增（非上游）**：`references/case-studies/` 案例文档目录，内容为作者自己的逆向案例，不参与上游同步，冲突时以本地为准 |
| `browser-skill/` | `https://github.com/Tencent/BrowserSkill` | 未固定到 commit（`bsk` bundled 快照；锚点为目录内 `.bsk-source` 内容哈希清单） | 目录快照（本机 `~/.claude/skills/browser-skill`，由 `bsk install-skill` 安装） | MIT（`Copyright (c) 2026 Tencent`，已放 `LICENSE`） | **发布快照，非权威**：权威来源是本机目录，版本由 `bsk` 自管。上游更新走 `bsk update` → `bsk install-skill` → 与本目录 `git diff` 对比 → 按需重新发布。`.bsk.lock` 为运行时锁文件 |
| `watch/` | `https://github.com/bradautomates/claude-video` | `03ceb42f7fa2c4439aca01752118044baabffb8f`（v0.3.2 tag） | 目录快照（上游 `skills/watch`） | MIT（`Copyright (c) 2026 Bradley Bonanno`，已放 `LICENSE`） | 依赖 ffmpeg/ffprobe + yt-dlp；无字幕视频需本地 WhisperX 或云转写。**本地新增（非上游）**：`windows-notes.md`（PATH/TEMP 处理、WhisperX 安装坑、Silero VAD 离线补丁），不参与上游同步 |
| `large-doc-ai-review/` | 内部项目 `jjj-project-review-ai`（未公开） | — | 范式提炼 | 自建 | 只提炼通用工程套路（解析定位、Prompt 契约、结论兜底、进程锁），业务规则、真实数据、指南文件均未收录 |
| `academic-plotting/` | `https://github.com/Orchestra-Research/AI-Research-SKILLs` | `773a52944ba4`（首次迁入 `2026-05-07`，经 `openskills` 安装） | 目录快照（上游 `20-ml-paper-writing/academic-plotting`，与上游逐字节一致） | MIT（`Copyright (c) 2025 Claude AI Research Skills Contributors`，已放 `LICENSE`） | 上游曾用名 `zechenzhangAGI/AI-research-SKILLs`；目录里保留的 `.openskills.json` 记录了安装来源，供追溯，勿删。无本地改动 |
| `nature-figure/` | `https://github.com/Yuan1z0825/nature-skills` | `c6701dbea29a` | 目录快照（上游 `skills/nature-figure`，**旧快照 v2.1.0**，上游已 2.8.0） | **Apache-2.0**（已放 `LICENSE`） | 见目录内 `LOCAL_CHANGES.md`：本地删掉了 `chart-atlas/`、`gallery/`、`assets/figures4papers/` 的图片与 `references/ai-graphical-abstract-workflow.md`，`SKILL.md`/`manifest.yaml`/`evals`/README 有改动。`assets/figures4papers/` 下的脚本**不属于** Apache-2.0，按目录内 `THIRD_PARTY_NOTICES.md` 的原始声明仅为来源标注与研究参考保留 |
| `khazix-writer/` | `https://github.com/KKKKhazix/khazix-skills` | `76fc0f8e8245` | 目录快照 + 改写 | MIT（`Copyright (c) 2026 数字生命卡兹克`，已放 `LICENSE`） | 上游为 246 行的精简版，本地是 414 行的旧版/扩写版，`references/` 也与上游不同；同步时以 `git diff` 手工合并，不要整目录覆盖 |
| `hv-analysis/` | `https://github.com/KKKKhazix/khazix-skills` | `76fc0f8e8245` | 目录快照 + 改写 | MIT（同上，已放 `LICENSE`） | 方法论（横纵分析法）由数字生命卡兹克提出；本地描述与 `references/schema.json`、`scripts/md_to_pdf.py` 相对上游有改动 |
| `wechat-claude-code/` | `https://github.com/Wechat-ggGitHub/wechat-claude-code` | `50143077c012` | 目录快照 + Windows 适配 | MIT（`Copyright (c) 2026 Wechat-ggGitHub`，`LICENSE` 为原文件，未改） | 见 `LOCAL_CHANGES.md`：`start.bat` 指向本机 `E:\CodeProject\ClaudeRoom\...`，另有 `daemon.sh`、`src/claude/provider.ts`、`src/commands/*` 的本地改动；上游另有 `docs/`、`README_en.md`、`src/claude/{tool-noise-filter,turn-router}.ts` 本地没有 |

## 已移除副本、改为索引的上游

| 曾内置目录 | 上游仓库 | 上游提交（移除时） | 许可证 | 处理 |
|---|---|---|---|---|
| `cnki-search/`、`cnki-advanced-search/`、`cnki-download/`、`cnki-export/`、`cnki-journal-index/`、`cnki-journal-search/`、`cnki-journal-toc/`、`cnki-navigate-pages/`、`cnki-paper-detail/`、`cnki-parse-results/` | `https://github.com/cookjohn/cnki-skills` | `20d65f660456` | **无 LICENSE**（默认保留所有权利，不可再分发） | 2026-11 从仓库删除这 10 个副本，改为 [`INDEXED_SKILLS.md`](INDEXED_SKILLS.md) 中的索引条目（只给上游地址与安装方式） |

## 许可证归属

- 上述 MIT / Apache-2.0 目录的许可证全文均已随目录放入 `LICENSE`；版权归各上游作者，不是本仓库作者。
- 本仓库自身内容（无上游记录的目录）目前未声明许可证，选型待定；第三方目录不受此影响。
- 新增或迁移 Skill 后：同步更新本文件、[`THIRD_PARTY.md`](THIRD_PARTY.md)、[`SYNC.md`](SYNC.md) 与
  [`skill-catalog.json`](skill-catalog.json) 的 `upstream` 字段。
