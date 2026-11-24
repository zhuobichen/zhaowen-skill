# 第三方内容汇总

本仓库里的第三方 skill 一览。每一项的许可证全文在该目录的 `LICENSE`；
来源、提交号与本地改动见 [`UPSTREAM_SOURCES.md`](UPSTREAM_SOURCES.md)，
同步命令见 [`SYNC.md`](SYNC.md)。

> 约定：`LICENSE` 里的版权方是**上游作者**，不是本仓库作者。修改这些目录时不要删掉 `LICENSE`，
> 也不要把上游代码改成看起来像本仓库原创。

## MIT

| 目录 | 上游 | 版权方（见目录内 LICENSE） |
|---|---|---|
| `academic-paper-download/` | tiangong-ai/agent-skills | 见目录内 `LICENSE.paper-fetch.txt`（Agents365-ai） |
| `document-granular-decompose/` | tiangong-ai/agent-skills | linancn |
| `convert-image-to-jpg/` | tiangong-ai/agent-skills | linancn |
| `remove-similar-image/` | tiangong-ai/agent-skills | linancn |
| `reverse-engineer-anything/` | morluto/rea | morluto |
| `browser-skill/` | Tencent/BrowserSkill | Tencent |
| `watch/` | bradautomates/claude-video | Bradley Bonanno |
| `academic-plotting/` | Orchestra-Research/AI-Research-SKILLs | Claude AI Research Skills Contributors |
| `khazix-writer/` | KKKKhazix/khazix-skills | 数字生命卡兹克 |
| `hv-analysis/` | KKKKhazix/khazix-skills | 数字生命卡兹克 |
| `wechat-claude-code/` | Wechat-ggGitHub/wechat-claude-code | Wechat-ggGitHub |

## Apache-2.0

| 目录 | 上游 | 备注 |
|---|---|---|
| `nature-figure/` | Yuan1z0825/nature-skills | 旧快照（v2.1.0）；本地改动见 `nature-figure/LOCAL_CHANGES.md`。Apache-2.0 要求保留 LICENSE、NOTICE（上游无 NOTICE）并声明修改 |

## 不属于上述许可证的部分

| 位置 | 情况 |
|---|---|
| `nature-figure/assets/figures4papers/` | 来自 `ChenLiu-1996/figures4papers`，上游**没有 LICENSE**。按目录内 `THIRD_PARTY_NOTICES.md` 的原始声明，仅为来源标注与研究参考保留，不授予复制/修改/再分发许可 |
| `mp-template-lib/templates/`、`docx_to_mp/references/` | 公众号排版样式来自具体文章的视觉反推，文字与图片版权归原公众号；只作样式参考，不随仓库授权 |
| `wechat_mp_ops/`、`docx_to_mp/` 里引用的第三方实现 | 如 `doocs/md`（WTFPL）、`AAAAAnson/mbeditor`（MIT），只在注释里标注出处，未整段搬运 |

## 已移除

`cnki-*` 10 个目录（上游 `cookjohn/cnki-skills`，无 LICENSE）已删除副本，改为
[`INDEXED_SKILLS.md`](INDEXED_SKILLS.md) 的索引条目。
