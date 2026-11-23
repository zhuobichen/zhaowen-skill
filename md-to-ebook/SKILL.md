---
name: md-to-ebook
description: >
  AI 驱动的 Markdown 电子书生成（炼书）系统。当用户要求：把 Markdown/笔记/文档/技能手册
  整理成一本电子书或 PDF、用 AI 逐章写书写教材、把一堆 md 文件合并排版成 PDF、
  给项目写配套教程并导出、批量生成中文技术书、复刻某本书的结构与文风续写章节 时使用。
  覆盖：book.yaml 配置格式、write/build/run 三命令真实用法、ReportLab 中文 PDF 排版、
  章节设计、教科书式写作提示词铁律、常见坑（字体、标题去重、章节文件被删、API key 泄露、
  Windows 控制台 GBK emoji 崩溃）。
  注意：源项目的 md2book 七步流水线大部分是占位实现，本 skill 用的是真正可跑的 write/build/run。
---

# MD-to-Ebook 炼书 Skill

把 Markdown 素材 + AI 写作 + ReportLab 排版，产出中文 PDF 电子书。

## 本 skill 自带的东西

```
md-to-ebook/
├── SKILL.md
├── scripts/
│   ├── cli.py       ← 入口：write / build / run
│   ├── writer.py    ← 逐章 AI 写作
│   ├── builder.py   ← 合并去重 + ReportLab PDF
│   └── api.py       ← LLM 调用（OpenAI 兼容）
├── config/
│   ├── default.example.yaml
│   ├── books/       ← 三本实战配置（claude_code / digital_humanities / im_tools）
│   └── styles/      ← 三种风格（tutorial / casual / principles）
└── agents/openai.yaml
```

脚本已改成**互为同级模块**（`from api import LLM`），直接 `python scripts/cli.py ...` 就能跑，不需要装包。

---

## 一、先搞清楚哪条链路是真的

源项目有**两套 CLI**，README 和 `docs/AI-AGENT-GUIDE.md` 描述的是理想版，**大量命令是占位**：

| 入口 | 命令 | 真实状态 |
|---|---|---|
| `scripts/cli.py`（本 skill） | `write` / `build` / `run` | ✅ **真实可跑**，产出成品 PDF |
| `md2book`（源项目 `src/main.py`） | `init` / `ingest` | ✅ 可跑（扫描+解析+入库） |
| `md2book`（源项目 `src/main.py`） | `analyze` / `plan` / `refine` / `review` / `export` / `run` | ❌ **全部 `not_implemented` 占位** |

**结论：出书走 `scripts/cli.py`，不要用 `md2book run`。**

`docs/AI-AGENT-GUIDE.md` 里那套 7 步流水线和 JSON 响应示例是**设计稿**，照着做会卡在 `analyze` 返回 `"status": "not_implemented"`。

---

## 二、真实出书流程（三命令）

```
book.yaml ──write──▶ ch01.md ~ chNN.md ──build──▶ 合并稿.md + 成品.pdf
```

### 2.0 准备 API Key

**推荐用环境变量，不要把 key 写进文件**：

```bash
# Windows PowerShell
$env:MD2BOOK_API_KEY="sk-..."
$env:MD2BOOK_API_BASE="https://api.deepseek.com/v1"    # 可选
$env:MD2BOOK_MODEL="deepseek-chat"                      # 可选

# bash
export MD2BOOK_API_KEY="sk-..."
```

也可复制 `config/default.example.yaml` 为 `config/default.yaml` 再填 `ai.api_key`。
读取优先级：`MD2BOOK_API_KEY` → `DEEPSEEK_API_KEY` → `OPENAI_API_KEY` → 配置文件。

> 没 key 时会**立刻报清晰错误**并退出，不会跑到一半才失败。

### 2.1 写一章

```bash
python scripts/cli.py write config/books/<book>.yaml <work_dir>
```

- 按 `chapters` 顺序**逐章串行**调用 LLM（`writer.py`）
- 每章写到 `<work_dir>/<ch.file>`
- `work_dir` 可省略：优先级 `命令行参数` → `$MD2BOOK_WORKDIR` → `当前目录`
- 写完的文件**不含 H1 标题**，标题由 build 阶段统一加
- 单章失败只打印 `❌`，**不会中断全书**——必须检查输出里每章是否都是 `✅`

### 2.2 合并 + 出 PDF

```bash
python scripts/cli.py build config/books/<book>.yaml <work_dir>
```

`builder.py` 做的四件事：
1. **合并**所有 `chapters[].file`
2. **标题去重**：剥掉每章开头的 `#`/`##` 行，再删正文里散落的 `## 第X章：xxx`
3. **ReportLab 渲染** PDF（A4，22mm 页边距）
4. **复制到根目录** + **删除章节 md 文件**（见坑 5）

### 2.3 一键

```bash
python -m src.cli run config/books/<book>.yaml    # write + build
```

---

## 三、book.yaml 配置格式

这是全流程的唯一输入。完整范例见 `config/books/im_tools.yaml`。

```yaml
meta:
  title: 我的电子书
  author: 你的名字
  language: zh-CN
  output_file: 我的电子书.md          # build 时以此为准，同名 .pdf 一起生成

# 素材：会被注入到每章 prompt 里 {SRC} 的位置
source: |
  ## 项目A：xxx
  核心技术：...
  功能链：...

# 自定义系统提示词（可选，不填用 writer.py 的默认教科书体）
system_prompt: |
  你是一位技术图书作者...

chapters:
  - file: ch01.md                     # 章节文件名
    title: "# 第1章 为什么要做这个"    # 注意：要带 "# " 前缀
    target_words: 5000                # 只用于提示 AI，不强制截断
    prompt: |
      写第1章，围绕以下内容展开：{SRC}
```

### 字段要点

| 字段 | 必填 | 坑 |
|---|---|---|
| `meta.output_file` | ✅ | 决定最终 md/pdf 文件名 |
| `source` | 建议 | 只有 prompt 里写了 `{SRC}` 才会注入 |
| `chapters[].title` | ✅ | **必须带 `# ` 前缀**，build 直接拼进正文 |
| `chapters[].prompt` | ✅ | 支持 `{SRC}` 占位 |
| `chapters[].target_words` | 可选 | 默认 4000，只是软提示 |

---

## 四、写作质量控制

`writer.py` 的默认系统提示词是**教科书体**，已经调好了，要点：

```
1. 像教科书一样分段叙事，每段 3-6 句话，不用列表当主体
2. 章节开头 2-3 段引入
3. 术语解释融入段落，不要"术语：解释"字典格式
4. 用"你"和"我"对话体
5. 代码放 ```块内，前后必须有段落解释
6. 结尾 2-3 段小结
7. 不要 emoji、不要 > 引用块、不要 ### 三级标题
8. 只用 ## 做小节标题
```

**这几条是这本书能被读下去的关键**。想调风格就改 `system_prompt`，但别放松第 1、7、8 条——否则 PDF 会变成一堆项目符号，毫无阅读感。

默认 `temperature=0.55`，太高会跑题，太低会重复。

---

## 五、ReportLab 中文排版

`builder.py` 内置的排版规则：

| 项 | 值 |
|---|---|
| 字体 | `simhei.ttf`（优先）→ `simfang` → `simkai` → `msyh*.ttc` |
| 等宽字体 | `consola.ttf`（代码块） |
| 正文 | 10.5pt / 行距 19 / 首行缩进 20 / `wordSpace="CJK"` |
| H1 | 18pt，**仅当含「第X章」时生效** |
| H2/H3 | 13pt / 11pt |
| 代码块 | 7.5pt，左缩进 14，浅灰底 |

**`wordSpace="CJK"` 不能去掉**，否则中文断行会出现诡异的字间距。

渲染时会剥掉 `**加粗**`、`*斜体*`、`` `行内码` ``、HTML 标签、`$数学$`——**所以 PDF 里看不到加粗效果，是纯文本排版**。

---

## 六、必踩的坑

> 标 ✅ 的坑**本 skill 的脚本里已经修好了**，列出是为了让你知道原项目有这么回事。

### 坑 1：API key 硬编码在 config 里
源项目 `config/default.yaml` 里写着明文 `api_key`（真实泄露过）。本 skill 已改为**环境变量优先**。

### 坑 2：章节标题必须带 `# ` 前缀
`title: "第1章 xxx"` → build 后没有章标题，整本书变成平铺段落。
`title: "# 第1章 xxx"` → 正确。

### 坑 3：H1 只有在含「第X章」时才放大
`builder._is_chapter_title()` 用正则 `第[一二三四五六七八九十0-9]+章` 判断。
标题写成「前言」「附录 A」的，会被降级成 H2。**这是设计如此**，想让前言也大就改这个名字规则。

### 坑 4 ✅：work_dir / output_root 硬编码
源项目 `cli.py` 固定 `Path("E:/CodeProject")`，`builder.py` 固定 `Path.cwd()`，换机器会写错地方、还会把产物复制到当前目录污染工作区。

本 skill 已改为：
- `work_dir`：命令行参数 → `$MD2BOOK_WORKDIR` → 当前目录
- `output_root`：默认跟随 `work_dir`，不再跨目录复制

### 坑 5：build 成功后**删除章节 md**
`builder.build()` 最后会 `cf.unlink()` 删掉所有 `chapters[].file`。
**只有合并稿 `.md` 和 `.pdf` 会留下。** 想保留分章源稿，先备份，或注释掉 `builder.py` 末尾的清理循环。

### 坑 6 ✅：Windows 控制台 GBK 遇到 emoji 直接崩溃
源脚本大量 `print("✅ ...")`，Windows 默认 GBK 控制台会抛：
```
UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f4c2'
```
**这不是警告，是直接退出、PDF 出不来。**

本 skill 三个脚本开头都已加：
```python
for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")
```

### 坑 7：README 与实现不符
源项目 `README.md` 写的 `--style` / `--format` / `--input` 参数，**`src/cli.py` 全都不支持**。
实际只接受 `<write|build|run> <book.yaml> [work_dir]`。

### 坑 4：work_dir 硬编码 `E:/CodeProject`
`cli.py` 第 60 行：`work_dir = Path("E:/CodeProject")`。
换机器必须改，否则章节写到奇怪的地方。`builder.py` 的 `output_root` 同理。

### 坑 5：build 成功后**删除章节 md**
`builder.build()` 最后会 `cf.unlink()` 删掉所有 `chapters[].file`。
**只有合并稿 `.md` 和 `.pdf` 会留下。** 想保留分章源稿，先备份，或注释掉 `builder.py` 第 231-232 行。

### 坑 6：`cli.py` 默认 yaml 路径
不传参数时默认 `config/books/cmaq.yaml`（大概率不存在），必须显式传路径。

### 坑 7：README 与实现不符
`README.md` 写的 `--style` / `--format` / `--input` 参数，**`src/cli.py` 全都不支持**。
那是 `main.py` 的设计稿。实际只接受 `<write|build|run> <book.yaml>`。

---

## 七、素材从哪来

实践中最省力的做法：**先写素材，再让 AI 展开**。

`source` 段写成「压缩过的技术要点」——每条讲清楚**是什么、怎么做、为什么**，AI 会把它展开成教科书段落。范例见 `config/books/im_tools.yaml` 的 `source`：

```
## weflow-cli：微信聊天记录本地解密+导出+AI分析工具
核心技术：微信加密数据库逆向——4.x 用 WCDB 内置加密（FFI 调用 wcdb_api.dll 提运行时密钥），
3.x 用 SQLCipher（PBKDF2-HMAC-SHA1 64000 迭代 + AES-256-CBC 逐页解密）。...
功能链：解密→导出→AI分析→Obsidian 同步。
安全设计：AES-256-GCM 密钥加密绑定单机。
```

**注意**：一个 `source` 可以塞多个项目，让一本书讲一个主题簇（如"IM 工具开发"包含 weflow-cli + qchat-cli + 公众号 + 飞书）。

---

## 八、产出物与归档

一次成功的 build 产出：

```
<work_dir>/
├── 我的电子书.md          ← 合并稿（带 YAML frontmatter）
└── 我的电子书.pdf         ← 成品
```
外加 `output_file` 指定的副本（`push_to_root=True` 时复制到 `output_root`）。

**建议归档结构**（本项目实践）：

```
output/<slug>/
├── ch01.md ~ ch09.md       ← 分章源稿（build 前先备份）
├── BOOK_OUTLINE.md         ← 全书大纲
├── EDITORIAL_REVIEW.md     ← 编辑评审记录
├── <slug>.md               ← 合并稿
└── <书名>.pdf              ← 成品
```

---

## 九、快速开工清单

1. 复制 `config/books/` 里最像的一本 yaml，改名
2. 改 `meta.title` / `meta.output_file` / `meta.author`
3. 写 `source`（技术要点，可分多个项目）
4. 列 `chapters`，每章 `title` **记得带 `# `**
5. 设 `MD2BOOK_API_KEY` 环境变量（**别把 key 写进文件**）
6. `python scripts/cli.py run config/books/<book>.yaml <work_dir>`
7. 检查每章是否都 `✅`，看 PDF 页数与字数是否合理

---

## 十、依赖

```bash
pip install pyyaml reportlab
```

**只要这两个**。`click` / `rich` 只有源项目的 `md2book`（`main.py`）才用，本 skill 的 `cli.py` 链路不需要。

字体依赖 Windows 系统字体（`C:/Windows/Fonts/simhei.ttf`），Linux 需自行改 `builder._init_fonts()` 的路径。

---

## 十一、已验证

本 skill 的三个脚本已经实际跑通：

| 测试项 | 结果 |
|---|---|
| `build` 双章合并 → PDF | ✅ 生成 PDF，章节标题/小节/代码剥离正常 |
| 中文渲染 | ✅ 用 simhei，`第1章` 正常放大 |
| 无 API key 时 | ✅ 立刻报清晰错误并退出（不再跑一半才崩） |
| `work_dir` 指定 | ✅ 产物落在指定目录，不污染当前工作区 |
| Windows GBK 控制台 | ✅ emoji 不再崩溃 |
