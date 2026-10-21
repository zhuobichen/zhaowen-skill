# 上游来源记录

本文件记录从外部 Skill 仓库迁入或借鉴的目录，便于后续同步、审查许可证和定位本地改动。

| 本地目录 | 上游仓库 | 上游提交 | 迁入方式 | 备注 |
|---|---|---|---|---|
| `academic-paper-download/` | `https://github.com/tiangong-ai/agent-skills` | `5e692461708a4e02c1012086a59d2bd75da99673` | 目录快照 | 保留 DOI/标题解析、PDF 身份校验、哈希和许可证来源边界 |
| `document-granular-decompose/` | `https://github.com/tiangong-ai/agent-skills` | `5e692461708a4e02c1012086a59d2bd75da99673` | 目录快照 | 使用前配置 `UNSTRUCTURED_AUTH_TOKEN` 和 API 地址 |
| `convert-image-to-jpg/` | `https://github.com/tiangong-ai/agent-skills` | `5e692461708a4e02c1012086a59d2bd75da99673` | 目录快照 | 本地图片转换，不上传图片 |
| `remove-similar-image/` | `https://github.com/tiangong-ai/agent-skills` | `5e692461708a4e02c1012086a59d2bd75da99673` | 目录快照 | 删除/移动前应先查看检测报告 |
| `reverse-engineer-anything/` | `https://github.com/morluto/rea` | `b8fab74` | 目录快照（`.agents/skills/reverse-engineer-anything`） | 仅装说明，不注册 MCP；分析引擎（Ghidra/JADX/Binwalk 等）需另行安装，SKILL.md 明确禁止顺手升级无关软件。**本地新增（非上游）**：`references/case-studies/` 案例文档目录，内容为作者自己的逆向案例，不参与上游同步，冲突时以本地为准 |
| `large-doc-ai-review/` | 内部项目 `jjj-project-review-ai`（未公开） | — | 范式提炼 | 只提炼通用工程套路（解析定位、Prompt 契约、结论兜底、进程锁），业务规则、真实数据、指南文件均未收录 |
| `browser-skill/` | `https://github.com/Tencent/BrowserSkill`（MIT，经 `bsk` CLI 分发） | 未固定到 commit（bsk 0.3.1 bundled 快照；锚点为目录内 `.bsk-source` 内容哈希清单） | 目录快照（本机 `~/.claude/skills/browser-skill`，由 `bsk install-skill` 安装） | **发布快照，非权威**：权威来源是本机目录，版本由 `bsk` 自管。上游更新走 `bsk update` → `bsk install-skill` → 与本目录 `git diff` 对比 → 按需重新发布。上游为 MIT，但 bundled 快照未附带 LICENSE 文件，许可依上游仓库声明；`.bsk.lock` 为运行时锁文件 |
| `watch/` | `https://github.com/bradautomates/claude-video` | `03ceb42f7fa2c4439aca01752118044baabffb8f`（v0.3.2 tag） | 目录快照（上游 `skills/watch`） | 依赖 ffmpeg/ffprobe + yt-dlp；无字幕视频需本地 WhisperX 或云转写。**本地新增（非上游）**：`windows-notes.md`（PATH/TEMP 处理、WhisperX 安装坑、Silero VAD 离线补丁），不参与上游同步 |

上游仓库使用 MIT License；本地后续修改应保留对应目录中的许可证文件和来源记录。
