# 只索引、未内置的上游 Skill

这里列的是**别人做的、本仓库不存放内容**的 skill。以前这些目录是整份拷贝进来的，现在只保留索引：
需要时按下面的命令自己装到本机技能目录，上游更新时直接重装即可。

收录标准：上游**没有许可证**（默认保留所有权利，不适合再分发），或体积大、更新频繁、本地没有实质改动。
有本地实战改动、需要留档的，走「内置副本 + `UPSTREAM_SOURCES.md` 登记 + 目录内 `LICENSE`」那条路。

## CNKI（中国知网）系列 10 个

- 上游：[`cookjohn/cnki-skills`](https://github.com/cookjohn/cnki-skills)（★1.1k）
- 许可证：**仓库未提供 LICENSE**，因此本仓库不再分发副本，只索引。
- 组成：`cnki-search`、`cnki-advanced-search`、`cnki-parse-results`、`cnki-navigate-pages`、
  `cnki-paper-detail`、`cnki-journal-search`、`cnki-journal-index`、`cnki-journal-toc`、
  `cnki-download`、`cnki-export`，另带一个编排 agent `cnki-researcher`。
- 能力：经 Chrome DevTools MCP 操作知网——关键词/字段检索、翻页排序、论文详情、期刊收录与影响因子、
  期刊目录、下载 PDF/CAJ、推送到 Zotero 或出 GB/T 7714 引用。

安装（上游 README 的官方步骤）：

```bash
# 前置：Chrome DevTools MCP
claude mcp add chrome-devtools -- npx -y chrome-devtools-mcp@latest

# 装 skills + agent
git clone https://github.com/cookjohn/cnki-skills.git
cd cnki-skills
cp -r skills/ agents/ .claude/
```

说明：上游用它自己的 agent / skill 目录结构分发，不是按单目录 `skills add` 的形式；
装完后以 `~/.claude/skills/` 下出现的目录为准。它与本仓库的 `zotero*` 系列可以配合用
（`cnki-export` 推 Zotero，`zotero-research` / `zotero-db` 做后续检索与整理）。

## 为什么不做成 submodule

CNKI 这套是「上游没有许可证」的情形，submodule 仍然会在你的仓库快照里留下内容指针与历史记录，
不如纯索引干净。需要跟版本的、许可证明确的大目录（如 `nature-figure`）才适合 submodule，见 `SYNC.md`。
