# 与上游同步

每个内置副本的同步方式不同，别一律「整目录覆盖」——本地改动会被吃掉。
原则：**先 `git diff` 看本地改了哪几处，再决定覆盖还是手工合并。**

## 快照型（无本地改动，可整体覆盖）

| 目录 | 上游 | 命令 |
|---|---|---|
| `academic-plotting/` | Orchestra-Research/AI-Research-SKILLs | `git clone --depth 1 https://github.com/Orchestra-Research/AI-Research-SKILLs /tmp/airs && rsync -a --delete /tmp/airs/20-ml-paper-writing/academic-plotting/ ./academic-plotting/`（注意别删掉 `.openskills.json` 与 `LICENSE`） |
| `convert-image-to-jpg/`、`document-granular-decompose/`、`remove-similar-image/`、`academic-paper-download/` | tiangong-ai/agent-skills | 记录过的提交是 `5e69246`；上游 HEAD 已前进，升级前先看其 CHANGELOG，不要无脑覆盖（这几个含本地环境假设） |

## 跟版本型（大目录，建议改用 submodule）

| 目录 | 上游 | 现在的做法 |
|---|---|---|
| `nature-figure/` | Yuan1z0825/nature-skills | 本地是 v2.1.0、上游 2.8.0。想跟版本：`git clone --depth 1 https://github.com/Yuan1z0825/nature-skills /tmp/nat && git diff --no-index /tmp/nat/skills/nature-figure ./nature-figure`，逐处合。**升级时必须保留** `LICENSE`、`assets/figures4papers/THIRD_PARTY_NOTICES.md`、`LOCAL_CHANGES.md`。若嫌手工麻烦，可改成 submodule：先 `git rm -r --cached nature-figure`，再 `git submodule add <url> vendor/nature-figure`（注意别把 `LICENSE` 留在外面） |

## 改写型（本地有实质改动，只做定点合并）

| 目录 | 上游 | 注意 |
|---|---|---|
| `khazix-writer/` | KKKKhazix/khazix-skills | 本地 414 行 vs 上游 246 行，是旧版/扩写版；上游新增的 `references/quality-check.md` 本地没有。合并时以「本地多余的章节是否有用」逐段判，别覆盖 |
| `hv-analysis/` | KKKKhazix/khazix-skills | 本地 `references/schema.json`、`scripts/md_to_pdf.py` 与上游不同（含本地修正）。上游 SKILL.md 更短，措辞更紧，可参考但不要整体替换 |
| `wechat-claude-code/` | Wechat-ggGitHub/wechat-claude-code | 本地有 Windows 适配（`start.bat`、`daemon.sh`、`provider.ts`、`commands/*`）。上游新增 `docs/`、`src/claude/tool-noise-filter.ts`、`src/claude/turn-router.ts`，升级时这几个新文件要单独拿过来再改 |
| `reverse-engineer-anything/` | morluto/rea | 本地多了 `references/case-studies/`（自己的逆向案例），冲突时以本地为准 |

## 自带版本管理型

| 目录 | 做法 |
|---|---|
| `browser-skill/` | 不要从 GitHub 拉。`bsk update` → `bsk install-skill` 刷新本机 `~/.claude/skills/browser-skill` → 与本目录 `git diff` → 需要时再发布。权威来源是本机目录，本仓库只是快照 |

## 只索引、不在本仓库

`cnki-*` 10 个见 [`INDEXED_SKILLS.md`](INDEXED_SKILLS.md)：需要时按上游 README 装到本机，
本仓库不做同步，也不存内容。

## 每月一次的自查

```bash
# 1) 每个外来目录都该有 LICENSE
for d in academic-paper-download convert-image-to-jpg document-granular-decompose remove-similar-image \
         reverse-engineer-anything browser-skill watch academic-plotting nature-figure \
         khazix-writer hv-analysis wechat-claude-code; do
  [ -f "$d/LICENSE" ] || echo "缺 LICENSE: $d"
done

# 2) UPSTREAM_SOURCES / skill-catalog 的 upstream 字段与实际目录一致
python - <<'PY'
import json, os
d = json.load(open('skill-catalog.json', encoding='utf-8'))
for s in d['skills']:
    if not os.path.isdir(s['path'].rstrip('/')):
        print('目录不存在:', s['path'])
PY
```
