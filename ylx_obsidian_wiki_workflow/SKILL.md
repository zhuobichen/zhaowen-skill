---
name: ylx_obsidian_wiki_workflow
description: |
  基于 LLM Wiki + kepano-obsidian 的 Obsidian 知识库构建工作流。
  适用场景：创建新知识库、整理散乱笔记、建立 Evergreen 笔记体系、
  设计三层架构（Raw Sources / Wiki / Schema）、执行 Ingest/Lint/Query 操作。
  MEMORY 同步：用户手动更新 MEMORY → LLM 根据 git 变化增量更新 OUTPUT Evergreen。
triggers:
  - "创建 Obsidian 知识库"
  - "整理笔记"
  - "建立 Evergreen 体系"
  - "LLM Wiki"
  - "三层架构"
  - "Ingest"
  - "Lint"
  - "知识库维护"
  - "MEMORY 同步"
config:
  vault_path: ""
  default_category: "General"
  memory_path: "E:\\CodeProject\\MEMORY"
  output_path: "E:\\CodeProject\\MEMORY\\OUTPUT"
version: 1.1.0
---

# Obsidian Wiki 工作流

基于 Karpathy LLM Wiki 架构 + kepano-obsidian Bottom-up 方法论的 Obsidian 知识库构建与维护系统。

---

## 核心理念

### 三层架构

```
Raw Sources (原始文档) → Sources (副本隔离) → Wiki (Evergreen 笔记) → index/log
```

1. **Raw Sources** - 原始文档，只增不减，LLM 只读不写
2. **Wiki (Evergreen)** - LLM 增量维护的原子化笔记网络
3. **Schema** - LLM 的操作规则和约定

### Bottom-up 笔记流

```
原始输入 → Daily 笔记 → Evergreen 笔记 → Categories 索引
```

---

## 目录结构

```
Vault/
├── index.md              # 内容索引（所有 Evergreen 页面的目录）
├── log.md               # 操作日志（ingest/query/lint 记录）
├── Sources/             # 原始文档副本（隔离层）
│   ├── Papers/
│   ├── Books/
│   └── Articles/
├── Evergreen/           # 常青笔记（原子化、可组合）
│   ├── PM25/
│   ├── Agent工作流/
│   ├── 前端/
│   └── 健康效益/
├── Categories/           # 顶层分类索引
│   ├── Evergreen.md      # 方法论说明
│   ├── PM25研究.md
│   ├── Agent工作流.md
│   └── ...
├── Daily/               # 每日记录
│   └── YYYY-MM-DD.md
└── Templates/           # 模板 + Schema
    ├── Daily.md
    ├── Evergreen.md
    └── SCHEMA.md
```

---

## 核心操作

### 1. Ingest（摄取）

当有新的原始文档需要处理时：

```
1. 读取原始文档
2. 提取核心观点（标题即观点）
3. 创建/更新 Evergreen 笔记（可能影响 10-15 个页面）
4. 更新 Sources/ 中的副本
5. 更新 index.md
6. 追加 log.md
```

### 2. Query（查询）

当用户提出问题时：

```
1. 先读 index.md 找到相关页面
2. 读取相关页面获取详情
3. 综合回答，带上引用
4. 质量高的回答归档到 Evergreen
```

### 3. Lint（健康检查）

定期执行：

```
- 检查死链（unresolved links）
- 检查孤立页面（orphans/deadends）
- 检查过时内容
- 检查矛盾页面
```

---

## MEMORY → OUTPUT 同步工作流

### 核心架构

```
MEMORY（原始资料） → OUTPUT（Evergreen Wiki）
     ↑                    ↑
 用户手动更新          LLM 增量维护
（只增不减）         （根据 MEMORY 变化更新）
```

### 关键原则

| 目录 | 角色 | 维护者 | 规则 |
|------|------|--------|------|
| **MEMORY** | Raw Sources（原始资料） | 用户 | 只增不减，LLM 只读不写 |
| **OUTPUT** | Evergreen Wiki（常青笔记） | LLM | 根据 MEMORY 变化增量更新 |

### 标准同步流程

```
1. 用户手动更新 MEMORY（添加新笔记、修改现有内容）
         ↓
2. LLM 执行：git log / git diff 查看 MEMORY 的增量变化
         ↓
3. LLM 根据变化内容，更新 OUTPUT 对应的 Evergreen 笔记
         ↓
4. 追加 log.md 记录本次同步操作
```

### LLM 禁止操作

- ❌ 直接修改 MEMORY 内容
- ❌ 删除 MEMORY 中的文件
- ❌ 覆盖用户原始记录

### 同步操作命令

```bash
# 查看 MEMORY 的 git 状态
git -C "E:/CodeProject/MEMORY" status

# 查看 MEMORY 的最近提交
git -C "E:/CodeProject/MEMORY" log --oneline -10

# 查看 MEMORY 与上一次同步的差异
git -C "E:/CodeProject/MEMORY" diff HEAD~1

# 查看 OUTPUT 的最后同步时间（从 log.md）
```

### 同步动作对照表

| MEMORY 变化类型 | OUTPUT 同步动作 |
|----------------|----------------|
| 新增笔记 | 在 Evergreen 创建对应的原子化笔记 |
| 修改笔记 | 更新对应 Evergreen 笔记的相关内容 |
| 删除笔记 | 在 OUTPUT 中标记为「已归档」或删除 |
| 新增主题 | 在 Categories 添加新分类索引 |

---

## Frontmatter 标准

```yaml
---
categories:
  - "[[分类名]]"
created: YYYY-MM-DD
topics:
  - "[[主题名]]"
tags:
  - 0🌲
status: 整理中
source: "[[MEMORY/xxx.md]]"
---

# 标题（核心观点）
```

| 字段 | 必填 | 说明 |
|------|------|------|
| categories | 是 | 所属分类，用 wikilink |
| created | 是 | 创建日期 |
| topics | 否 | 相关主题 |
| tags | 是 | `0🌲` 表示常青笔记 |
| status | 否 | `整理中` / `已整理` / `待审核` |
| source | 否 | 来源 MEMORY 文件链接 |

---

## 命令速查

```bash
# Obsidian CLI（Claude Code 中使用完整路径）
"/e/软件/Obsidian/Obsidian.exe" reload        # 刷新缓存
"/e/软件/Obsidian/Obsidian.exe" unresolved     # 检查死链
"/e/软件/Obsidian/Obsidian.exe" orphans        # 检查孤立页面
"/e/软件/Obsidian/Obsidian.exe" deadends      # 检查无出链页面
"/e/软件/Obsidian/Obsidian.exe" files          # 列出所有文件
"/e/软件/Obsidian/Obsidian.exe" folders        # 列出所有文件夹

# MEMORY 同步
git -C "E:/CodeProject/MEMORY" log --oneline -10
git -C "E:/CodeProject/MEMORY" diff HEAD~1
```

---

## Lint 执行流程（含 Obsidian 启动）

### 标准 Lint 流程

```bash
# 1. 启动 Obsidian（如果未运行）
"/e/软件/Obsidian/Obsidian.exe" &

# 2. 等待几秒让 Obsidian 完全启动
sleep 5

# 3. 执行健康检查
cmd //c "obsidian orphans"      # 检查孤立页面
cmd //c "obsidian unresolved"    # 检查死链
cmd //c "obsidian deadends"     # 检查无出链页面
```

### Daily 日记写作规范

**必须包含内容:**
1. **执行的具体命令** - 完整的命令字符串
2. **原始输出结果** - 检查输出如实记录
3. **发现的问题** - 包括文件路径、行数等细节
4. **采取的操作** - 包括 commit hash、文件变化统计

**日记模板:**
```markdown
## [任务名称] (YYYY-MM-DD)

### 1. 准备
- [具体检查命令和结果]

### 2. 执行
- [变更分析]
- [具体操作]

### 3. 结果
- [最终状态]
- [commit hash]
```

**重要**: 完成后必须同步更新 `OUTPUT/log.md`

### 文件名记录规范（重要）

**禁止**：
- ❌ 禁止推测不存在的文件名
- ❌ 禁止使用解码后的可能文件名
- ❌ 禁止假设文件名与记忆或描述匹配

**正确做法**：
- ✅ 直接使用 `git diff --name-status` 输出的原始路径
- ✅ 如果文件名包含中文编码不可读，保留原始编码路径
- ✅ 对于不确定的文件，标注"文件名待确认"

**示例**：
```bash
# 错误做法（会导致文件名不匹配）
- 修改文件: `待办-已办提示词工作流/整理清单.md`  # 可能不存在！

# 正确做法
- 修改文件: `git diff --name-status` 输出的原始路径
  - "待办-已办提示词工作流/整理清单.md" (文件名待确认)
```

**验证方法**：
```bash
# 检查文件是否实际存在
ls "/e/CodeProject/MEMORY/待办-已办提示词工作流/"

# 检查git中实际跟踪的文件
git ls-files "待办-已办提示词工作流/"

# 用git show查看实际提交的文件名
git show HEAD --name-only
```

### 常见问题处理

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| "CLI is unable to find Obsidian" | Obsidian 未运行 | 启动 Obsidian: `"/e/软件/Obsidian/Obsidian.exe" &` |
| obsidian 命令超时 | Obsidian 需要更长时间启动 | 增加 sleep 时间: `sleep 8` |
| orphans 显示 Sources 文件 | Sources 是隔离层，正常现象 | 无需处理 |

### Windows Git Bash 中使用 cmd //c

包含冒号的命令必须用 `cmd //c` 包装：
```bash
# 正确
cmd //c "obsidian orphans"
cmd //c "obsidian unresolved"

# 错误（会失败）
obsidian orphans
obsidian unresolved
```

---

## 关联 Skill

- [[obsidian]] - Obsidian CLI 操作
- [[memory-organizer]] - MEMORY 笔记整理流程
