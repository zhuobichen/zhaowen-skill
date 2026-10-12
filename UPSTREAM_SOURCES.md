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

上游仓库使用 MIT License；本地后续修改应保留对应目录中的许可证文件和来源记录。
