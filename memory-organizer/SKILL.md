---
name: memory-organizer
description: MEMORY笔记整理工作流 - 从原始文档提取精华、建立链接、定期维护
version: 1.1.0
triggers:
  - "整理MEMORY"
  - "整理笔记"
  - "整理OUTPUT"
  - "清理孤立笔记"
  - "检查死链"
  - "维护知识库"
  - "增量整理"
  - "git diff整理"
---

# MEMORY 整理工作流

> 从零开始，将散乱的Markdown文档整理成结构化、可追溯的知识库

---

## 一、核心理念

### Bottom-up 笔记法

```
MEMORY (原始文档) → OUTPUT/Daily (每日记录) → OUTPUT/Notes (精炼) → OUTPUT/Categories (分类)
```

**核心原则：**
1. **MEMORY只增不减** - 原始文档永不删除
2. **原子化提取** - 每条笔记聚焦一个核心观点
3. **双链组织** - 用 [[wikilinks]] 自然关联
4. **定期整理** - 从Daily提炼Evergreen笔记

---

## 二、目录结构

```
MEMORY/                          # 原始文档库（Git追踪）
├── Agent工作流/                  # 按主题分类的原始文档
├── 健康效益/
├── PM2.5研究/
└── ...

OUTPUT/                          # 精炼知识库（新创建）
├── Categories/                  # 主题分类索引
│   ├── Evergreen.md            # 常青笔记方法论
│   ├── PM25研究.md              # PM2.5研究分类
│   ├── 健康效益.md              # 健康效益分类
│   └── Agent工作流.md           # Agent工作流分类
│
├── Notes/                      # 精炼后的原子笔记
│   ├── PM25_融合方法分解组合策略.md
│   ├── Claude_三角色闭环.md
│   └── ...
│
├── Daily/                      # 每日整理记录
│   └── 2026-04-09.md
│
└── Templates/                  # 笔记模板
    └── Daily.md
```

---

## 三、快速启动

### 3.1 每日维护任务

执行完整的每日维护检查：

```bash
# 1. 检查 Git 状态
cd /e/CodeProject/MEMORY
git status
git log --oneline -3

# 2. 检查 Obsidian 孤立笔记
cmd //c "obsidian orphans"

# 3. 检查死链
cmd //c "obsidian unresolved"

# 4. 检查无出链笔记（死端）
cmd //c "obsidian deadends"

# 5. 查看未同步文件
git status --short
```

### 3.2 增量整理（基于 git diff）

当用户已编辑原始 MEMORY 文档，需要提取/更新整理笔记时：

```bash
# 1. 先提交维护操作（保持 git status 干净）
git status
git commit -m "维护: 整理笔记/修复链接"  # 如果有已跟踪文件被修改

# 2. 查看用户编辑的文档变更
git diff --name-only HEAD

# 3. 分析变更内容
git diff HEAD -- "MEMORY/Agent工作流/xxx.md"

# 4. 更新/创建对应 OUTPUT 笔记

# 5. 刷新缓存并检查
cmd //c "obsidian reload"
cmd //c "obsidian unresolved"

# 6. 更新 Daily 笔记并提交
git add OUTPUT/
git commit -m "整理: YYYY-MM-DD 日更新"
```

### 3.3 提取新笔记

从原始文档提取精华到 OUTPUT：

```bash
# 使用 Claude Code 批量处理
# 参考 patterns:
# - 分析文档核心观点
# - 创建原子化笔记
# - 建立 wikilinks 关联
```

### 3.4 修复链接问题

```bash
# 刷新 Obsidian 缓存
cmd //c "obsidian reload"

# 查找孤立笔记
cmd //c "obsidian orphans"

# 查找死链
cmd //c "obsidian unresolved"

# 查找无出链笔记
cmd //c "obsidian deadends"

# 查看所有笔记
cmd //c "obsidian files"
```

---

## 四、完整工作流（基于 Git Diff）

### 4.1 每日增量整理流程

当用户已编辑原始 MEMORY 文档，需要提取/更新整理笔记时执行：

```
┌─────────────────────────────────────────────────────────────┐
│ 增量整理流程（基于 git diff）                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 先提交维护操作（保持 git status 干净）                         │
│     ├─> git status 查看当前状态                              │
│     ├─> 如果有已跟踪文件的修改（组织工作），先 commit            │
│     └─> git commit -m "维护: 整理笔记/修复链接"                │
│                                                             │
│  2. 查看用户编辑的文档变更                                     │
│     └─> git diff --name-only HEAD                           │
│         → 获得用户编辑/新增的原始文档列表                        │
│                                                             │
│  3. 分析变更内容                                              │
│     └─> git diff HEAD -- [文件路径]                          │
│         → 直接读取 diff 输出，提取关键变更                      │
│         → 不需要重新读取完整文件                                │
│                                                             │
│  4. 更新/创建对应 OUTPUT 笔记                                 │
│     ├─> 如果是已有笔记的相关文档 → 更新现有笔记                  │
│     ├─> 如果是新文档 → 创建新笔记                              │
│     └─> 确保 wikilinks 关联正确                               │
│                                                             │
│  5. 更新 Daily 笔记                                          │
│     ├─> 记录当日整理的文档                                    │
│     ├─> 记录创建/更新的 OUTPUT 笔记                          │
│     └─> 使用 [[../Notes/笔记名]] 格式                          │
│                                                             │
│  6. Git 提交变更                                             │
│     └─> git add OUTPUT/                                     │
│         git commit -m "整理: YYYY-MM-DD 日更新"              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Git Diff 提取命令

```bash
# 查看所有已跟踪文件的变更（不包括未跟踪）
git diff --name-only HEAD

# 查看特定文件的变更内容
git diff HEAD -- "MEMORY/Agent工作流/xxx.md"

# 查看新增文件
git diff --name-only --diff-filter=A HEAD

# 查看修改文件
git diff --name-only --diff-filter=M HEAD

# 组合：查看新增和修改的文件
git diff --name-only --diff-filter=AM HEAD
```

### 4.3 增量整理检查清单

```
执行前：
- [ ] git status 确认状态
- [ ] 有变更的文件是否是需要整理的原始文档？（非组织维护文件）

执行中：
- [ ] 使用 git diff 读取变更内容
- [ ] 为每个变更文档提取核心观点
- [ ] 更新或创建对应 OUTPUT 笔记
- [ ] 检查 wikilinks 关联

执行后：
- [ ] 运行 obsidian reload 刷新缓存
- [ ] 运行 obsidian unresolved 确认无死链
- [ ] 更新 Daily 笔记
- [ ] Git 提交 OUTPUT 变更
```

---

## 五、每日整理流程

### 5.1 每日维护（建议每天 10:00 AM）

执行完整的每日维护检查：

```
┌─────────────────────────────────────────────────────────────┐
│ 每日维护                                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Git 状态检查                                            │
│     └─> git status → 是否有新文档需要整理？                   │
│                                                             │
│  2. Obsidian 健康检查                                        │
│     ├─> orphans → 孤立笔记？                                │
│     ├─> unresolved → 死链？                                 │
│     └─> deadends → 无出链笔记？                            │
│                                                             │
│  3. 报告结果                                                │
│     └─> 如果有问题，询问用户是否修复                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 提取新笔记流程

```
┌─────────────────────────────────────────────────────────────┐
│ 提取新笔记                                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 扫描 MEMORY 中的新文档                                  │
│     └─> git status 查看未跟踪的文档                          │
│                                                             │
│  2. 分析文档核心观点                                         │
│     └─> 阅读文档，提取关键思想                               │
│                                                             │
│  3. 创建原子笔记                                            │
│     ├─> 标题即观点                                          │
│     ├─> 聚焦单一主题                                        │
│     └─> 添加 frontmatter                                    │
│                                                             │
│  4. 建立链接                                                │
│     ├─> 链接到 Categories                                   │
│     └─> 链接到相关 Notes                                    │
│                                                             │
│  5. 更新 Daily 笔记                                         │
│     └─> 记录当日整理进展                                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 创建新分类流程

```
┌─────────────────────────────────────────────────────────────┐
│ 创建新分类                                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 创建分类笔记                                            │
│     └─> OUTPUT/Categories/[分类名].md                      │
│                                                             │
│  2. 添加 frontmatter                                        │
│     ```yaml                                                 │
│     ---                                                     │
│     tags: [categories]                                      │
│     created: YYYY-MM-DD                                     │
│     ---                                                     │
│     ```                                                     │
│                                                             │
│  3. 添加核心主题链接                                         │
│     └─> ## 核心主题                                         │
│         - [[相关笔记1]]                                      │
│         - [[相关笔记2]]                                      │
│                                                             │
│  4. 添加来源说明                                            │
│     └─> ## 来源                                            │
│         从 `[[../原始文档/]]` 中提取                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 六、模板

### 6.1 Evergreen 笔记模板

```markdown
---
categories:
  - "[[分类名]]"
created: YYYY-MM-DD
topics:
  - "[[主题名]]"
tags:
  - 0🌲
status: 整理中
---

# 标题（核心观点）

核心思想：...

## 分解

1. ...

## 组合

...

## 优势

- ...

## 来源

从 `[[../原始文档/xxx.md]]` 提取
```

### 5.2 Category 笔记模板

```markdown
---
tags:
  - categories
created: YYYY-MM-DD
---

# 分类名

分类描述。

## 核心主题
- [[笔记1]]
- [[笔记2]]
- [[笔记3]]

## 来源

从 `[[../原始文档/]]` 中提取
```

### 6.3 Daily 笔记模板

```markdown
---
created: YYYY-MM-DD
tags:
  - daily
---

# YYYY-MM-DD

## 今日主要进展

- ...

## 精炼笔记

从MEMORY中提取并创建了以下精炼笔记：

### [分类]
- [[../Notes/笔记名]]

## 明日计划

- ...

## 链接

- [[../Categories/分类]]
- [[../Categories/分类2]]
```

---

## 七、常用命令速查

### 6.1 Obsidian CLI

```bash
# 刷新缓存
cmd //c "obsidian reload"

# 孤立笔记检查
cmd //c "obsidian orphans"

# 死链检查
cmd //c "obsidian unresolved"

# 死端检查（无出链）
cmd //c "obsidian deadends"

# 列出所有文件
cmd //c "obsidian files"

# 搜索内容
cmd //c "obsidian search query=关键词"

# 查看笔记大纲
cmd //c "obsidian outline file=笔记名"

# 查看反向链接
cmd //c "obsidian backlinks file=笔记名"

# 查看出链
cmd //c "obsidian links file=笔记名"

# 创建笔记
cmd //c "obsidian create name=笔记名 path=Notes content=内容"

# 删除笔记
cmd //c "obsidian delete file=笔记名"
```

### 6.2 Git 命令

```bash
# 查看状态
git status

# 查看最近提交
git log --oneline -5

# 查看更改统计
git diff --stat

# 添加并提交
git add .
git commit -m "描述"
git push
```

### 6.3 文件操作

```bash
# 列出 MEMORY 中的 MD 文件
ls /e/CodeProject/MEMORY/*.md

# 列出 OUTPUT 笔记
ls /e/CodeProject/MEMORY/OUTPUT/Notes/

# 列出 OUTPUT 分类
ls /e/CodeProject/MEMORY/OUTPUT/Categories/

# 搜索文件内容
grep -r "关键词" /e/CodeProject/MEMORY/OUTPUT/
```

---

## 八、故障排除

### 8.1 Obsidian CLI 无法连接

```bash
# 确保 Obsidian 正在运行
# 如果没运行，启动它
cmd //c "start obsidian"

# 等待几秒后重试
sleep 5
cmd //c "obsidian vault"
```

### 8.2 孤立笔记无法删除

```bash
# 使用绝对路径
cmd //c "obsidian delete path=Notes/文件名.md"

# 或移动到回收站
cmd //c "obsidian move file=文件名.md to=Trash/"
```

### 8.3 死链无法修复

```bash
# 1. 搜索死链来源
grep -r "死链关键词" /e/CodeProject/MEMORY/OUTPUT/

# 2. 确定是 wikilink 还是 status 字段
# 如果是 status 字段，移除 [[]]
# 如果是真正的 wikilink，创建对应笔记或更新链接
```

---

## 九、执行检查清单

### 每日维护（自动触发）

- [ ] Git 状态检查
- [ ] 孤立笔记检查
- [ ] 死链检查
- [ ] 死端检查
- [ ] 报告结果

### 增量整理（基于 git diff）

- [ ] git status 确认状态
- [ ] git diff --name-only HEAD 查看用户编辑的文档
- [ ] git diff HEAD -- [文件] 读取变更内容
- [ ] 更新/创建对应 OUTPUT 笔记
- [ ] obsidian reload 刷新缓存
- [ ] obsidian unresolved 确认无死链
- [ ] 更新 Daily 笔记
- [ ] git commit OUTPUT 变更

### 每周整理

- [ ] 扫描新文档
- [ ] 提炼新笔记
- [ ] 建立分类链接
- [ ] 更新 Daily 笔记
- [ ] Git 提交

---

*版本：1.1.0*
*新增基于 git diff 的增量整理工作流*
