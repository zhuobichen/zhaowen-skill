# Zotero Word 字段格式 —— 取证记录

> 全部取自本机 Zotero 7 安装，**不是推测**。核实日期 2026-10-13。

## 取证来源

| 内容 | 位置 |
|---|---|
| 域指令怎么拼、`Citation` 怎么序列化 | `C:\Program Files\Zotero\app\omni.ja` → `chrome/content/zotero/xpcom/integration.js` |
| Word 插件的域类型与书签机制 | 同 `omni.ja` → `integration/word-for-windows/components/zoteroWinWordIntegration.mjs` |
| 文档首选项存哪、什么格式 | `%APPDATA%\Microsoft\Word\STARTUP\Zotero.dotm` → `docProps/custom.xml` |
| 样式目录何时扫描 | `omni.ja` → `chrome/content/zotero/xpcom/style.js` |

`omni.ja` 就是个 zip，直接 `zipfile.ZipFile(...).read(路径)` 就能读。

## 一、引用域

`integration.js` 里 `Zotero.Integration.Field.setCode()`：

```js
if (this.type == INTEGRATION_TYPE_ITEM) {
  await this._field.setCode(`ITEM CSL_CITATION ${code}`);
} else if (this.type == INTEGRATION_TYPE_BIBLIOGRAPHY) {
  await this._field.setCode(`BIBL ${code} CSL_BIBLIOGRAPHY`);
}
```

Word 插件 DLL 在前面再加 `ADDIN ZOTERO_`，所以 Word 里实际存的 instrText 是：

```
 ADDIN ZOTERO_ITEM CSL_CITATION {json}
 ADDIN ZOTERO_BIBL {json} CSL_BIBLIOGRAPHY
```

`code` = `Citation.serialize()` = `JSON.stringify(this.toJSON())`，而
`toJSON()` 只保留三个键（`saveProperties` / `saveCitationItemKeys`）：

```js
const saveProperties = ["custom", "unsorted", "formattedCitation", "plainCitation",
                        "dontUpdate", "noteIndex"];
const saveCitationItemKeys = ["locator", "label", "suppress-author", "author-only",
                              "prefix", "suffix", "ignoreRetraction"];
```

所以一条引用域长这样：

```json
{
  "citationID": "8位随机",
  "properties": {
    "formattedCitation": "(Son et al., 2010; Seltzer et al., 2020)",
    "plainCitation": "(Son et al., 2010; Seltzer et al., 2020)",
    "noteIndex": 0
  },
  "citationItems": [
    {
      "uris": ["http://zotero.org/users/20061961/items/ABCD1234"],
      "itemData": { "...完整 CSL-JSON，去掉库内标识..." },
      "id": 35
    }
  ]
}
```

- **叙述式引用**（作者写在正文里，如 `Alexeeff et al. (2015)`）：
  在该 `citationItem` 上加 `"suppress-author": true`，于是域只渲染出 `(2015)`。
- **参考文献域的数据几乎是空的**：`{"uncited":[],"omitted":[],"custom":[]}`。
  条目是 Zotero 刷新时扫全文的 `CSL_CITATION` 域推导出来的。

## 二、文档级样式偏好

存在 **自定义文档属性**（不是 `w:docVar`）：`docProps/custom.xml` 里的 `ZOTERO_PREF_1`。
`Zotero.dotm` 自带的那份实测值：

```xml
<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="ZOTERO_PREF_1">
  <vt:lpwstr>&lt;data data-version="3" zotero-version="7.0.0.SOURCE.249c5b8d1"&gt;
    &lt;session id="S2ILiAdz"/&gt;
    &lt;style id="" hasBibliography="0" bibliographyStyleHasBeenSet="0"/&gt;
    &lt;prefs/&gt;
  &lt;/data&gt;</vt:lpwstr>
</property>
```

`DocumentData.unserialize` **先试 `JSON.parse`、失败才当 XML**：

```js
Zotero.Integration.DocumentData.prototype.unserialize = function (input) {
  try { return Object.assign(this, JSON.parse(input)); }
  catch (e) { if (!(e instanceof SyntaxError)) throw e; }
  if (input[0] == "<") { this.unserializeXML(input); } else { /* 2.x 老格式 */ }
};
```

所以写 JSON（`dataVersion: 4`）也认。`serialize()` 的 XML 分支写出
`<pref name="…" value="…"/>`，与 `unserializeXML` 里读 `/data/prefs[1]/pref` 对应。

### ⚠️ `prefs.fieldType` 必须写

```js
// Session.prototype.init
if (!data.prefs.fieldType) {
  if (dontRunSetDocPrefs) return false;
  await this.setDocPrefs();          // ← 弹「文档首选项」对话框
}
```

Word 的取值（`zoteroWinWordIntegration.mjs`）：

```js
primaryFieldType: "Field",
secondaryFieldType: "Bookmark",      // 旧的「书签跟踪」模式，不是超链接
```

写成 `<prefs><pref name="fieldType" value="Field"/></prefs>` 即可免掉那次弹窗。
另注意 `setDocPrefs` 里有：

```js
if (data.prefs.fieldType !== app.primaryFieldType &&
    data.prefs.fieldType !== app.secondaryFieldType) {
  throw new Zotero.Exception.Alert("integration.error.fieldTypeMismatch", …);
}
```

## 三、字段在 document.xml 里的形状

五段式，缺一段 Word 会认不出或修不好：

```xml
<w:r><w:fldChar w:fldCharType="begin"/></w:r>
<w:r><w:instrText xml:space="preserve"> ADDIN ZOTERO_ITEM CSL_CITATION {…}</w:instrText></w:r>
<w:r><w:fldChar w:fldCharType="separate"/></w:r>
<w:r><w:t xml:space="preserve">(Son et al., 2010)</w:t></w:r>
<w:r><w:fldChar w:fldCharType="end"/></w:r>
```

⚠️ instrText 里的 JSON 会被 XML 转义（`"` → `&quot;`）。**读回来要先反转义再 `json.loads`**，
否则会报 `Expecting property name enclosed in double quotes: line 1 column 2`。

⚠️ ` ADDIN ` 前缀：
- 走 COM `Fields.Add(rng, 81, text, True)`（81 = `wdFieldAddin`）→ **Word 自动加**，
  自己再加就变成 `ADDIN ADDIN ZOTERO_ITEM`，Zotero 认不出。
- 直写 OOXML → **必须自己写**。

## 四、为什么样式要重启 Zotero 才认

```js
// xpcom/style.js
Zotero.Styles = new function () {
  var _initialized = false;
  var _styles, _visibleStyles;
  this.init = async function (options = {}) { /* 把样式元数据load进内存 _styles */ };
  ...
};
```

整个 `style.js` 里 **`watch` 出现 0 次**，只有一个 `memory-pressure` 观察者。
即样式目录**没有文件监视**，新丢进去的 `.csl` 只有下次启动才被读到。
表现：BBT 一直报 `Error: CSL style "…" not found`。

## 五、点击跳转为什么是另一个东西

Zotero 不生成引用↔参考文献的内部链接（`zotero/zotero#4263`，官方："cannot create
clickable links automatically"）。跳转要用 Word 自己的：

```xml
<!-- 参考文献条目上 -->
<w:bookmarkStart w:id="7" w:name="_Ref12"/>条目文字<w:bookmarkEnd w:id="7"/>
<!-- 正文引用上 -->
<w:hyperlink w:anchor="_Ref12" w:history="1"><w:r><w:t>(Son et al., 2010)</w:t></w:r></w:hyperlink>
```

书签名列全文档唯一、不以数字开头（`_Ref1` 可以）。`w:id` 是不重复整数。
**不加 `Hyperlink` 字符样式** —— 否则正文引用变蓝带下划线。
