---
title: LLM Wiki Schema
created: {{date}}
---

# LLM Wiki Schema

定义 LLM 如何组织、维护和演进 Wiki 的规则。

## 核心原则

1. **Raw Sources 不可修改** - LLM 只读不写
2. **Wiki 由 LLM 维护** - 人类负责方向，LLM 负责所有文书工作
3. **Schema 是活文档** - 随着经验演进，持续更新

---

## 文件夹结构

```
Vault/
├── index.md           # 内容索引
├── log.md            # 操作日志
├── Sources/          # 原始参考资料（不可变）
├── Evergreen/         # 常青笔记（LLM 维护）
├── Categories/        # 顶层分类索引
├── Daily/            # 每日记录
└── Templates/        # 模板 + Schema
```

---

## Evergreen 笔记规范

### 命名规则

- 标题即观点，简短易记（不超过 20 字）
- 使用中文命名
- 避免特殊字符：`/\:*?"<>|`

### Frontmatter 标准

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
---
```

---

## 操作规范

### Ingest

1. 读取原始文档
2. 提取核心观点
3. 创建/更新 Evergreen 笔记
4. 更新 Sources/ 副本
5. 更新 index.md
6. 追加 log.md

### Query

1. 先读 index.md
2. 读取相关页面
3. 综合回答
4. 高质量回答归档到 Evergreen

### Lint

定期检查：
- 死链 → 修复或删除
- 孤立页面 → 链接或归档
- 过时内容 → 更新或删除
- 矛盾页面 → 合并或标注

---

## index.md 格式

```markdown
# index

## 分类1
- [[Evergreen/分类1/页面1]] - 一句话描述
- [[Evergreen/分类1/页面2]] - 一句话描述

## 分类2
- [[Evergreen/分类2/页面3]] - 一句话描述
```

## log.md 格式

```markdown
# log

## [YYYY-MM-DD] ingest | 标题
- 操作描述

## [YYYY-MM-DD] lint | 健康检查
- 检查结果
```

---

*版本：1.0.0*
