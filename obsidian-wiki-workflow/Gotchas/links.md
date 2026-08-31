# 链接问题 (Links)

## 死链 (Unresolved Links)

### 原因
1. wikilink 指向不存在的文件
2. 重命名/移动文件后未更新链接
3. `status` 字段使用了 `[[]]` 包裹，被当作链接解析

### 排查命令
```bash
obsidian unresolved
grep -r "\[\[" Vault/Evergreen/ | grep -v "Sources/"
```

### 修复
1. 创建缺失的页面
2. 修正链接目标
3. 从 status 字段移除 `[[]]`

---

## 孤立页面 (Orphans)

### 定义
没有任何页面通过 wikilink 指向它们

### 排查命令
```bash
obsidian orphans
```

### 处理
- 入口页面（Daily、index、README）正常孤立可忽略
- Evergreen 孤立页面需要建立链接或归档

---

## 死端页面 (Dead Ends)

### 定义
页面没有任何出链（不链接到其他页面）

### 排查命令
```bash
obsidian deadends
```

### 处理
- Templates/SCHEMA.md 等参考文档正常
- Evergreen 死端需要补充相关链接

---

## 跨层链接

### 问题
Evergreen 笔记中的来源链接指向外部（如 `MEMORY/`）而非 `../Sources/`

### 正确模式
```
Evergreen/PM25/xxx.md → ../Sources/PM25/原始文档.md
```

### 修复
使用 `grep` 检查并批量替换：
```bash
grep -r "\.\./MEMORY" Vault/Evergreen/
```
