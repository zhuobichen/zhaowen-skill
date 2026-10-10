---
name: kb-capture
description: |
  把当前对话里的「概念性问答」沉淀成 Obsidian 知识库的原子卡片并自动 push。
  适用场景：用户说「存知识库 / 存进知识库 / 存卡片 / 沉淀一下 / 记录这个概念」，
  且内容是概念、原理、术语、方法的问答（不是项目代码任务）。
  自动去重（同概念已存在则合并更新既有卡）、批量单次提交、写盘前做敏感与规范校验。
  知识库：ZhaoWen_KnowledgeBase（Obsidian Vault），卡片落在 OUTPUT/Evergreen/概念卡片/。
triggers:
  - "存知识库"
  - "存进知识库"
  - "存卡片"
  - "沉淀一下"
  - "沉淀知识库"
  - "记录这个概念"
version: 1.0.0
---

# 概念问答沉淀（kb-capture）

把**当前这轮对话**里的概念性问答，写成知识库的原子卡片并存档。

## 适用与不适用

**适用**：概念、原理、机制、术语辨析、方法论的问答。典型如「什么是 Morlet 小波」「RAG 和微调的区别」「为什么用十折交叉验证」。

**不适用**：项目代码任务、调试过程、操作步骤、纯执行类对话。那些属于工作流文档或 `memory-organizer` 的范畴 —— 不要往概念卡片里塞。

**只沉淀你自己当前会话里的问答。** 你的上下文里就有刚才这轮问答，**不要去读 transcript 文件**，也不要去读取或汇总另一个 AI（Codex 等）的会话记录 —— 在对应的对话里总结，质量最高。

## 权威规范

卡片的完整格式与合并规则，以知识库内的 `OUTPUT/Templates/概念卡片规范.md` 为准。本文件是操作入口，那份是细则。若两者冲突，以仓库内那份为准。

## 工作流

### 1. 判定与拆卡

确认当前上下文是概念性问答。**一个概念 = 一张卡**：一轮对话问了 5 个概念就准备 5 张卡，不要合并成一张大卡。

### 2. 逐概念判重（不可跳过）

对每个概念调用：

```
search_docs(query="<概念名>", path="OUTPUT")
```

- `candidates` **非空** → 调 `read_doc(该路径)` 读全文，走「合并」（第 3 步）
- `candidates` **为空** → 新建

### 3. 生成或合并卡片内容

**新建**时按以下结构（`write_docs` 的 `mode` 用 `create`）：

```markdown
---
categories:
  - "[[概念卡片]]"
created: {{TODAY}}
updated: {{TODAY}}
topics:
  - "[[<概念名>]]"
tags:
  - 0🌲
status: 整理中
---

# <概念名>（核心观点，≤20 字）

核心思想：一句话说清是什么、为什么重要。

## 定义
## 关键点
## 常见误区
## 关联文档
- [[相关卡文件名，不带路径]]

## 来源
- 类型：AI 对话问答
- 来源：Claude Code 会话（{{TODAY}}）
- 会话：`{{SESSION_ID}}`
- 原始提问：<用户原话>
```

**合并既有卡**时（`mode` 用 `overwrite`）：

| 部分 | 规则 |
|---|---|
| `created` | **保持原值不动**（卡片生日） |
| `updated` | 改为今天 |
| `categories` / `topics` | 并集去重，原顺序在前 |
| `# 标题` | 全文只允许一个 H1 |
| `核心思想：` | **改写**成更准的一句，不是追加 |
| 定义 / 关键点 / 常见误区 | **逐条粒度合并**：等价条目就地增强，新条目插到逻辑位置；**绝不允许两条同义 bullet** |
| `## 关联文档` | wikilink 并集去重 |
| `## 来源` | **追加一行**，保留历史 |
| 矛盾 | 两个说法都留，显式标注分歧与出处，不静默覆盖 |
| 规模 | 合并后 >~120 行 → **裂卡**（拆两张互链） |

**去重纪律**：对每一句准备写入的新内容自问「旧卡里是不是已经说了？」—— 说了就不写；说了但更弱就**替换**；确实是新信息才落新句。

`{{TODAY}}` / `{{SESSION_ID}}` 由 `write_docs` 自动展开，直接写占位符即可。

### 4. 索引同步（每次都要做）

三处 read-modify-write，先读原文件再改，保留原格式：

| 文件 | 动作 |
|---|---|
| `OUTPUT/index.md` | 在 `## 概念卡片` 段追加 `- [[Evergreen/概念卡片/<卡名>]] - 一句话描述`；更新结尾 `*最后更新：YYYY-MM-DD*` |
| `OUTPUT/Categories/概念卡片.md` | 在 `## 核心主题` 下追加 `- [[Evergreen/概念卡片/<卡名>]]` |
| `OUTPUT/log.md` | **插在 frontmatter 之后的最前面**（该文件是时间倒序，不是追加到末尾）：`## [YYYY-MM-DD] query \| 对话沉淀：<概念1>、<概念2>` |

### 5. 一次提交

把全部文件（N 张卡 + index.md + Categories/概念卡片.md + log.md）放在**同一次** `write_docs` 调用里：

```
write_docs({
  files: [
    { path: "OUTPUT/Evergreen/概念卡片/<卡名>.md", content: "...", mode: "create" },
    ...其他卡片...,
    { path: "OUTPUT/index.md", content: "<改后的完整内容>", mode: "overwrite" },
    { path: "OUTPUT/Categories/概念卡片.md", content: "...", mode: "overwrite" },
    { path: "OUTPUT/log.md", content: "...", mode: "overwrite" }
  ],
  message: "query: 对话沉淀 <概念列表>",
  strict_evergreen: true,
  sensitive_action: "abort"
})
```

**不要分多次调用** —— 保证原子性，避免 `index.md` 指向尚不存在卡片的「幻链」。

### 6. 汇报

用返回的 JSON 向用户报告：新建/更新了哪些卡、commit 短哈希、是否 push 成功。若有 `warnings` 或 `pushed=false`，明确说出来并给出后续命令。

## 常见错误处理

| 返回值 | 含义与处理 |
|---|---|
| `目标已存在…create 模式不会覆盖` | 说明漏了判重。先 `read_doc` 读全文，合并后改 `mode="overwrite"` 重试 |
| `Evergreen 卡片规范校验未通过` | 按报错修正。最常见是 `status` 被写成了 `[[整理中]]`（必须是纯文本） |
| `敏感检查命中` | 卡片里不该有凭据。删掉那部分，或确认误报后用 `sensitive_ignore: ["ip-2"]` |
| `pushed=false` | 已本地提交但推送失败。给出 `git -C "<仓库>" push origin <分支>` 让用户手动执行 |

## 与相邻 skill 的边界

| skill | 职责 | 触发 |
|---|---|---|
| **kb-capture（本 skill）** | 会话内**一句话**沉淀概念问答 → 原子卡；即时、小批量、来源是**对话** | 存知识库 |
| `obsidian-wiki-workflow` | 文档级 Ingest/Lint/Query、MEMORY→OUTPUT 增量同步；大批量、来源是**文档** | 整理笔记 |
| `memory-organizer` | 定期运维：git-diff 增量整理、孤立页/死链修复、全库体检 | 整理 MEMORY / 检查死链 |
| `obsidian` (CLI) | Obsidian CLI 操作手册 —— **本 skill 不依赖它** | vault 操作 |

本 skill **不做** lint、不做批量同步、不碰仓库根的原始沉淀层。遇到那类需求，让用户改用对应的 skill。

## 红线

- `status` 写成 `[[整理中]]` → 产生死链
- **`topics` / `## 关联文档` 里的 wikilink 指向不存在的笔记** → 产生 `unresolved` 死链。`topics` 两种写法都可接受：纯文本 `"主题名"`（该主题没有独立笔记时，推荐）或 `"[[笔记名]]"`（确有独立笔记时）。用 wikilink 就必须指向真实存在的笔记，宁可不写
- 正文出现两个 `# H1`
- 绕过 `write_docs` 直接 `git add -A`
- 没 `read_doc` 就读旧卡就 `overwrite`
- 把项目代码任务当概念问答存进来

## 写入前自检

1. 每个 `[[...]]` 都指向真实存在的笔记了吗？（`categories` → `Categories/` 分类页；`topics` 若用 wikilink → 同名卡或既有笔记）
2. 全文只有一个 H1 吗？
3. `status` 是纯文本吗？
4. `## 来源` 是纯文本对话出处，而非 `[[../Sources/...]]` 吗？
