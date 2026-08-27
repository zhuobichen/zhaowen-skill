# Obsidian Wiki Workflow Skill

基于 LLM Wiki + kepano-obsidian 的 Obsidian 知识库构建工作流。

## 目录结构

```
obsidian-wiki-workflow/
├── SKILL.md           # 主 Skill 文件
├── config.json        # 配置
├── README.md          # 本文件
├── templates/
│   ├── Evergreen.md  # Evergreen 笔记模板
│   └── SCHEMA.md      # Schema 模板
└── Gotchas/
    └── links.md       # 链接问题避坑清单
```

## 使用

### 1. 配置 vault_path

在 `config.json` 中设置你的 Obsidian 保管库路径：

```json
{
  "vault_path": "E:/Path/To/Your/Vault"
}
```

### 2. 创建基础结构

```bash
# 创建必要文件夹
mkdir -p Sources Evergreen Categories Daily Templates

# 创建 index.md 和 log.md
touch index.md log.md
```

### 3. 执行 Ingest

当有新的原始文档需要整理时：

1. 将原始文档复制到 `Sources/`
2. 根据 `templates/Evergreen.md` 创建笔记
3. 更新 `index.md`
4. 追加 `log.md`

### 4. 健康检查

```bash
obsidian reload
obsidian unresolved   # 死链检查
obsidian orphans      # 孤立页面检查
obsidian deadends     # 死端页面检查
```

## 触发词

- 创建 Obsidian 知识库
- 整理笔记
- 建立 Evergreen 体系
- LLM Wiki
- 三层架构
- Ingest / Lint / Query

## 关联 Skill

- `obsidian` - Obsidian CLI 操作
- `memory-organizer` - MEMORY 笔记整理流程
