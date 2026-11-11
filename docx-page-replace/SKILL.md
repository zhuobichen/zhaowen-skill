---
name: docx-page-replace
description: 在 .docx 里按文本锚点删掉一段内容（段落或表格行），并在原位插入「一图一页」的图片——常用于把空白表格页换成签字盖章的扫描件、把整节换成扫描附件、或往报告末尾插几页图。当用户说「把这几页扫描件替换进相应的页」「把这一节删掉换成图片」「往 docx 里插整页图」时使用。
---

# docx-page-replace

## 核心目标
- 输入 docx + 锚点文本 + 图片，输出**新** docx：指定区间被删掉，原位置按一图一页插入图片。
- 只动 `word/document.xml` 与图片关系，不碰页眉页脚、样式、编号定义。
- 只依赖标准库；读图片尺寸用 Pillow（没装也能跑 PNG / JPEG）。

## 需要的工具
- `scripts/docx_pages.py`（标准库实现，不需要 python-docx）。
- 可选：`Pillow` —— 只在图片是 WebP/BMP/TIFF 这类非 PNG/JPEG 格式时需要。
- 校验/预览：`python docx_pages.py check`；渲染成 PDF 需要本机 Word/LibreOffice，
  不是必须的，但**交付前建议人眼过一眼**（见「验证」）。

## 快速开始

```bash
# 1. 先看文档结构，确认锚点文字真的存在、且只出现一次
python scripts/docx_pages.py list report.docx
python scripts/docx_pages.py list report.docx --rows      # 展开每个表格的每一行

# 2. 删掉「四、实践单位考核」到「附件1：」之间的全部内容，换成两页扫描件
python scripts/docx_pages.py replace report.docx --out report_v2.docx \
    --start "四、实践单位考核" --end "附件1：" \
    --images p16.jpg p17.jpg

# 3. 校验（zip / XML / 关系引用 / 图片是否超出版心）
python scripts/docx_pages.py check report_v2.docx
```

- `--start` 命中在**表格行**里时按行删（从该行到表尾，表格前面的行保留）；
  命中在**段落**里时从该段落删到 `--end`。
- `--end` 省略 = 删到文末（不含 `sectPr`）。
- `--images` 省略 = 只删不插；只想往末尾插图时，`--start` 给文末最后一个标题即可
  配合 `--end` 一起用，或者用 `--start` 指向结束处那一行文字。
- `--width` 默认 0.92；贴满 1.0 往往会把最后一张图挤到下一页，多出半页空白。

## 为什么这么设计

- **按文本锚点，不按序号。** 删掉几行之后序号就变了，而「四、实践单位考核」这种
  标题不会变。锚点命中 0 处或 2 处都直接报错退出：这类操作错一次就是交错的材料，
  宁可让人把锚点写长一点。
- **绝不覆盖输入。** `--out` 指向输入文件会直接拒绝；默认写 `<原名>_edited.docx`。
- **删表必须补闭合标签。** 行级删除是把表格截断（`...</w:tr></w:tbl>`），不是
  删掉 `</w:tbl>`——后者会让整份文档结构断裂，Word 报「unreadable content」。

## 必踩的三个坑（都实际踩过）

1. **DrawingML 命名空间得自带。** `a:` 与 `pic:` 前缀在 `document.xml` 根节点上
   **没有**声明（只挂在各个 `<a:graphic>` 上）。新插入的 `<w:drawing>` 如果不写
   `xmlns:a` / `xmlns:pic`，Python 侧报 `unbound prefix`，Word 侧直接打不开。
   脚本里已经把它们声明在 `<w:drawing>` 上。
2. **表格行级截断，且不能留空表。** 行级删除是把表格截断成
   `...最后一个保留行</w:tr></w:tbl>`；删掉 `</w:tbl>` 会让整份文档结构断裂。
   而如果锚点就在表首行（等于整张表都不要），留下一个只有 `<w:tblPr>` 没有
   `<w:tr>` 的空表同样非法，所以这种情况脚本直接整块删掉表格。
3. **版心宽度贴满会多一页。** 图宽等于版心宽时，行距/边框的 1–2 px 误差就会把它推到
   下一页，表现为「图后面多一张空白页」。默认 0.92 是留给这个的。

## 验证（交付前必做）

1. `check` 必须打印 `结论: 通过`——它检查 zip 完整性、两份 XML 是否良构、17 类
   `rId` 是否都能解析、media 文件是否都在、图片是否超出版心。
2. 顺手确认可见文字没被多删：`list` 新文件，看被删区间前后的标题是否还在。
3. **分页排版只能人眼看。** 脚本不渲染，Word 的 COM 自动化在很多会话里会挂死
   （`Documents.Open` 抛「Word 未能引发事件」），LibreOffice 也常常没装。所以：
   交付时明说「结构已校验、分页请你打开看一眼第 N–M 页」，不要假装验过。

## 边界
- 只处理正文（`w:body` 的直接子块）。锚点落在**嵌套表格**里、或在页眉页脚/文本框里，
  都会定位不到——那种情况需要手工改。
- 不处理跨节（`sectPr`）与分栏；多节文档只按最后一节的版心算图片尺寸。
- 图片只做等比缩放 + 居中，不裁剪、不加边框、不压缩体积。

## 脚本
- `scripts/docx_pages.py` —— `list` / `replace` / `check` 三个子命令，全部离线。
