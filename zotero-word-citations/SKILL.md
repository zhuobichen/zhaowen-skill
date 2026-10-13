---
name: zotero-word-citations
description: 把 Word 手稿里的 author-year 文字引用变成 Zotero 活字段，并生成「引用 ↔ 参考文献可点击跳转」的定稿版。当用户要在 Word 里用 Zotero 管理引用、不想手工插文献；或拿到一份引用是死文字的稿子；或抱怨"点引用跳不到参考文献"时使用。
argument-hint: "[link|build|finalize] [--md 手稿.md] [--journal aaqr|ae]"
---

# Zotero → Word 引用

把手稿的 author-year 文字引用转成 **Zotero 活字段**（能在 Word 里 Refresh 自动更新），
再可以出一个**引用 ↔ 参考文献可点击跳转**的静态定稿版。

脚本：`scripts/zotero_word.py`（`link` / `build` / `finalize`）、
`scripts/verify_zotero_docx.py`（结构核验）。

## 一句话原理

Word 的「域」是藏起来的：`begin / instrText(指令) / separate / 结果文本 / end`，
**Word 默认只画结果文本**，所以插好的域看上去就是普通文字（`Alt+F9` 才能看到指令）。
Zotero 的域指令是 ` ADDIN ZOTERO_ITEM CSL_CITATION {json}`，json 里带
`uris`（指向库内条目）、`itemData`（完整书目内联）、`formattedCitation`（当前显示文本=缓存）。
**Word 完全不懂 Zotero**，它只是照着指令画；`ADDIN` 表示这个域归外部加载项管。

参考文献**不是**一条条排的：`ZOTERO_BIBL` 域的数据几乎是空的
（`{uncited:[],omitted:[],custom:[]}`），Zotero 刷新时扫全文找所有 `CSL_CITATION` 域、
收集被引条目、跑 CSL 样式引擎，把结果写进去 —— **参考文献是从正文引用推出来的**。

## ⚠️ 域与跳转互斥（决定为什么有两个产物）

域的结果文本是**缓存**，Refresh 会整段重写。书签/超链接就埋在结果文本里，一刷新就没了。
所以只能二选一：

| 产物 | 命令 | 用途 | 特征 |
|---|---|---|---|
| 活字段版 | `build` | 写作期间 | 有 Zotero 域，能 Refresh；**无跳转** |
| 定稿版 | `finalize` | 投稿 | 无域，引用↔参考文献**可点击跳转** |

**Zotero 原生不做点击跳转**（长期未实现，`zotero/zotero#4263`；官方说 cannot create
clickable links automatically）。发表 PDF 里能跳是**出版商排版环节**加的。
`finalize` 用 Word 自己的内置功能补上：条目上打 `<w:bookmarkStart w:name="_RefN"/>`，
正文引用包成 `<w:hyperlink w:anchor="_RefN">`。**故意不加 `Hyperlink` 字符样式** ——
加了正文引用会变蓝带下划线，投稿稿不该这样。

## 前置条件（缺一不可）

1. **Zotero 正在运行** + **Better BibTeX 插件**（脚本走 `http://127.0.0.1:23119`）
2. **期刊的 CSL 样式已装进 Zotero**，否则参考文献渲染会失败或降级。
   - ⚠️ **Zotero 只在启动时扫样式目录**（`Zotero.Styles.init()` 建内存缓存；
     `xpcom/style.js` 里没有目录监视）。往 `styles/` 丢 `.csl` 后**必须重启 Zotero**，
     否则一直报 `CSL style ... not found`。
   - 装样式：`curl -o "<Zotero数据目录>/styles/<style>.csl" https://www.zotero.org/styles/<style>`
3. **Zotero 数据目录**要对。不是 `~/Zotero` —— 看 `prefs.js` 里的
   `extensions.zotero.dataDir`。用 `ZOTERO_DATA_DIR` 环境变量覆盖。

## 用法

```bash
# 1) 建立 refs.bib ↔ Zotero 库 的映射（会调 BBT 搜索，较慢，结果缓存复用）
python scripts/zotero_word.py link --bib <手稿目录>/build/refs.bib

# 2) 活字段版（写作期）
python scripts/zotero_word.py build --md <手稿>.md --journal aaqr --out out_fields.docx

# 3) 投前定稿版（可点击跳转）
python scripts/zotero_word.py finalize --md <手稿>.md --journal aaqr --out out_linked.docx

# 核验（域结构、JSON、样式名、断链）
python scripts/verify_zotero_docx.py out_fields.docx
```

路径全部可用参数或环境变量覆盖：`ZOTERO_DATA_DIR`、`ZOTERO_WORD_MD`、
`ZOTERO_WORD_CACHE`、`ZOTERO_WORD_SHELL_AAQR` / `_AE`。
`--shell` 指定期刊模板壳（带命名样式 + `w:lnNumType` 行号 + 页脚页码的 docx）。
加新期刊：在脚本的 `STYLES` / `SHELLS` 里加一条。

手稿要用 **author-year 文本引用**（`(Son et al., 2010; Seltzer et al., 2020)`）；
叙述式引用（`Alexeeff et al. (2015)`）也能认，走 `suppress-author`。

## 上手前先看这几个坑

- **⚠️ 不要走 Word COM。** 本机 `Word.Application` 的 ProgID 被 **WPS 劫持**
  （`Dispatch` 拿到 `Name`="Microsoft Word"、`Version`=12.0 —— 12.0 就是破绽，
  真 Word 是 16.x）。`Fields.Add` / `CustomDocumentProperties` 会**静默不生效**，
  还可能挂死并留下隐藏 wps 实例锁住文件。脚本因此**直接拼 OOXML**。
- **` ADDIN ` 前缀谁写**：走 COM 时是 Word 替你补；**直写 XML 要自己写**。漏了 Zotero 认不出。
- **文档首选项 `ZOTERO_PREF_1` 必须带 `fieldType`**（Word 用 `"Field"`）。
  `Session.init` 里 `if (!data.prefs.fieldType) { await this.setDocPrefs(); }` ——
  缺了它，用户点 Refresh 会先弹「文档首选项」对话框。
  存在 `docProps/custom.xml` 的**自定义文档属性**里（不是 `w:docVar`）。
- **活字段版里参考文献域的显示文本是空的**，这不是 bug —— 故意不渲染（渲染了就会过时），
  第一次 Refresh 后 Zotero 才填。
- **未入库的引用**：bib 里有、Zotero 库里没有的条目，只能留纯文本、进不了参考文献域。
  多篇同引时该组会变成"半截"（域只装在库的那部分，显示文本却是全部，Refresh 后会丢）。
  脚本会打印清单；先导进 Zotero 再重跑。
- **`item.search` 有时 `date` 返回 `None`**（年份只在 `issued.date-parts` 里），
  按 `date` 判年份会把条目误筛掉。姓氏兜底时**年份只有取不到才放宽**，
  否则不同年份的同作者会被误配。

## 参考

- `references/field-format.md` —— 字段格式的完整取证记录（源码位置 + 原文片段）
