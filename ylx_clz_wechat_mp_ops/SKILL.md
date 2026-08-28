---
name: ylx_clz_wechat_mp_ops
description: >
  操作微信公众号后台（mp.weixin.qq.com）：登录、查看草稿箱/发表记录、读取图文草稿内容、编辑修改草稿文字（标题/正文）。
  当用户要求：修改微信公众号文章/草稿、把某篇草稿从旧版更新到新版、对比公众号文章与文档差异、
  在微信后台改文字（日期/邮箱/措辞/标题）、生成第三轮/新版通知并更新到草稿 时使用。
  涵盖：stealth/chrome-direct 登录与扫码、token 过期处理、草稿编辑页 URL 结构、ProseMirror 编辑器 DOM 结构、
  EditorView 实例获取、**修改正文唯一可靠方式（dispatch + 点"保存为草稿"按钮）**、标题修改、验证持久化、
  获取草稿 appmsgid（Vue 实例 $data.appid）、上传图片（file input 设可见 + upload）、图片删除/移动（inline image dispatch）、
  常见陷阱（直接改 DOM 部分保存 / 自动保存不监听 dispatch / token 过期回退）、
  配套技能（生成公众号配图 HTML→整页截图→PIL 裁剪 / 解析 WPS 问题 xlsx 用 zipfile XML）等经验。
---

# 微信公众号后台操作 Skill

> 平台：`https://mp.weixin.qq.com`（微信公众平台图文编辑器，基于 **ProseMirror**）

## 前置环境

- **browser-act CLI**（浏览器自动化，必读其 `get-skills core`）
- **浏览器选择**：优先 `chrome-direct`（`n8n-direct`，ID `direct_local_112182917546901584`，直接控制本地 Chrome，继承微信登录态）；若调试端口故障（打开超时/`9222` 返回 404），改用 stealth `acs-stealth2`（ID `103206233488452404`）扫码登录
- **配合 skill**：`browser-act`

## 1. 登录与 token

微信公众平台登录需**管理员微信扫码**（页面外验证）。stealth 首次需 `remote-assist` 生成远程链接让用户扫码；登录态非永久，几小时后会过期。

- 后台任意页面 URL 都带 `token=<数字>`，**token 会过期**（"请重新登录"/"登录超时"即 token 失效）
- 获取**当前有效 token**：登录后导航到 `https://mp.weixin.qq.com/`，页面自动跳转到 `.../cgi-bin/home?...&token=XXXX`，取该 token
- 用户给的旧 URL 里的 token 常已过期，需用当前 token 替换后重试

## 2. 关键 URL（token 用当前有效值）

| 页面 | URL 模板 |
|------|---------|
| 草稿箱 | `https://mp.weixin.qq.com/cgi-bin/appmsg?begin=0&count=10&type=77&action=list_card&token=TOKEN&lang=zh_CN` |
| 发表记录 | `https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list&begin=0&count=10&token=TOKEN&lang=zh_CN` |
| 草稿编辑页 | `https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=77&appmsgid=APPMSGID&token=TOKEN&lang=zh_CN` |

- 草稿 `type=77`，`appmsgid` 是草稿 ID
- 发表记录列表里，文章标题是 `<a class=weui-desktop-mass-appmsg__title>`，点击进入的是预览页；编辑草稿要进草稿箱点标题卡（`<a class=weui-desktop-publish__cover__title>`）

### 获取草稿 appmsgid（卡片 href 是 javascript:void，data 属性里也没有）

草稿卡片的 `appmsgid` 不直接暴露在 DOM 属性里，从 Vue 实例读：

```js
var el = document.querySelector('.publish_card_container'); // 草稿卡片容器
var d = el.__vue__.$data;
// d.appid 就是 appmsgid（注意：d.id 是空字符串，别用错）
```

## 3. 编辑器 DOM 结构（关键）

微信图文编辑器 = 标题 + 正文，**各一个 ProseMirror**（`contenteditable`）：

| 元素 | 位置 | 特征 |
|------|------|------|
| 标题 textarea | `textarea#title` | 存储标题 value |
| 标题 ProseMirror | `div.title-editor__input > div.ProseMirror` | 短（几十字符） |
| 正文 ProseMirror | `div.ProseMirror`（另一个） | 长（>100 字符） |
| 正文图片 | `img.rich_pages.wxw-img` | 二维码/委员会图等，替换文字勿动图片 |

```js
// 区分标题/正文 ProseMirror：正文 innerText 长度 > 100
var body = null;
document.querySelectorAll('.ProseMirror').forEach(function(p){ if(p.innerText.length > 100) body = p; });
```

**获取正文 EditorView 实例**（走 Vue 实例链）：

```js
var el = body, vue = null;
for(var i=0;i<10 && el;i++){ if(el.__vue__){ vue = el.__vue__; break; } el = el.parentElement; }
var view = vue['$options']['parent']['$parent']['__editorView'];
```

## 4. 读取内容

```js
// 读取 ProseMirror state 全文（权威，非 DOM）
var text = view.state.doc.textBetween(0, view.state.doc.content.size, String.fromCharCode(10));

// 读取标题（可用 getContent）
window.__mpTitleEditor.getContent();  // 返回标题字符串
```

## 5. 修改正文（唯一可靠方式）⭐

> ⚠️ **踩坑记录（务必遵守）**：
> - ❌ **直接改 DOM 文本节点 + `dispatchEvent('input')`** → 只**部分保存**（措辞保存、日期丢失），重新加载回退
> - ❌ **`view.dispatch()` + 等自动保存** → **完全不保存**（微信自动保存不监听 ProseMirror dispatch，只监听 DOM input）
> - ✅ **`view.dispatch()` + 点击"保存为草稿"按钮** → 正确持久化

**正确流程：先 dispatch 精确替换，再点保存按钮。**

```js
// 1) dispatch 精确文本替换（遍历文本节点，逐个替换）
var pairs = [['旧文本','新文本'], ['旧2','新2']];
pairs.forEach(function(p){
  var doc = view.state.doc;
  var found = false, tr = view.state.tr;
  doc.descendants(function(node, pos){
    if(found || !node.isText) return true;
    var idx = node.text.indexOf(p[0]);
    if(idx !== -1){
      tr.replaceWith(pos + idx, pos + idx + p[0].length, view.state.schema.text(p[1]));
      found = true;
    }
    return !found;
  });
  if(found) view.dispatch(tr);
});
```

```js
// 2) 定位"保存为草稿"按钮并点击（browser-act state 里 id=js_submit 下的 button）
//    state 里 grep "保存为草稿"，点击对应 index（本例为 133）
```

- **替换字符串务必唯一**：日期类注意区分带/不带 `2026` 前缀（如 `2026年9月1日前` 只在重要日期，`会务组将于9月1日前` 只在报名注册段），避免误替换多处
- 目标文本跨多个文本节点时 `node.text.indexOf` 会 miss；先探查确认目标在单节点内（见下）

**探查目标文本是否在单节点内（替换前先跑）：**

```js
doc.descendants(function(node,pos){ if(node.isText && node.text.indexOf('目标')!==-1){ console.log(pos, node.text.slice(0,80)); } return true; });
```

### 图片操作（删除 / 移动 inline image）

正文图片是 inline image 节点（`node.type.name === 'image'`，size=1）。用 dispatch 删除/移动：

```js
// 定位所有图片节点
var images = [];
doc.descendants(function(node,pos){ if(node.type.name==='image'){ images.push({pos:pos, node:node}); } return true; });

// 移动图片：把 pos 靠后的图 移到 靠前的旧图位置（先删后图，再删前图，最后插入）
var oldPos = images[0].pos, newPos = images[1].pos, newNode = images[1].node;
var tr = view.state.tr;
tr.delete(newPos, newPos+1);   // 先删位置靠后的
tr.delete(oldPos, oldPos+1);   // 再删靠前的（此时其 position 未变，因为删的是它后面的）
tr.insert(oldPos, newNode);    // 在目标位置插入
view.dispatch(tr);
```

### 上传图片到正文

编辑器「图片」按钮（`#js_editor_insertimage`）→「本地上传」触发隐藏 file input（`input[type=file][name=file]`）。该 input 是 **0×0 透明元素**（opacity:0, position:absolute），state 不列出，`upload` 命令无法直接定位。先把它移到 body 并设为可见，再 state 找 index，最后 upload：

```js
// eval 里移动 + 设可见
var f = document.querySelector('input[type=file]');
document.body.appendChild(f);
f.style.cssText = 'display:block;opacity:1;position:fixed;top:0;left:0;width:200px;height:40px;z-index:99999;';
```
然后 `browser-act state` 找 `type=file` 的 index，`browser-act upload <index> <本地图片路径>`。上传后新图插入到当前光标处，再用上面的 dispatch 把它移到目标位置并删旧图。

## 6. 修改标题

- `window.__mpTitleEditor.getContent()` 可读；`setContent()` **不生效**（勿用）
- 可靠方式：直接改 `textarea#title.value` + 标题 ProseMirror 文本节点 + 触发 input（本次实测生效）；改完同样点保存

```js
var ta = document.getElementById('title');
ta.value = ta.value.replace('旧','新');
ta.dispatchEvent(new Event('input',{bubbles:true}));
// 再改标题 ProseMirror 文本节点 + dispatchEvent('input')
```

## 7. 保存与验证

- 保存按钮：browser-act `state` 里 grep「保存为草稿」，其外层是 `<span id=js_submit>`，点击该 `button` 的 index
- 验证持久化：**重新加载编辑页**（navigate 回同一 URL）后读 DOM/state 确认改动还在，`已保存` 状态文字不代表 dispatch 已入库
- 保存状态文字：`div.page_tips.success` 显示「已保存」；但 dispatch 不触发它变化，只有点按钮才真正落库

### 发布后检查（已群发文章）

群发后用 stealth-extract 抓取 `https://mp.weixin.qq.com/s/<id>`（无需登录），核对标题、文字、图片、发表地区：

```bash
browser-act stealth-extract "https://mp.weixin.qq.com/s/xxx" --content-type markdown
# 图片检查：--content-type html 后 grep data-src / mmecoa.qpic.cn，下载后 image-vision 核对
```

## 8. 常见陷阱汇总

1. **token 过期**：旧 URL 报"请重新登录"，换当前 token
2. **chrome-direct 调试端口故障**：打开超时、`http://127.0.0.1:9222/json/version` 返回 404（不是标准 DevTools）→ 换 stealth 浏览器
3. **chrome 类型浏览器登录态过期**：快照非实时，微信登录态几小时失效
4. **直接改 DOM 部分保存**：措辞/标题可能存，日期可能丢，务必用 dispatch + 保存按钮
5. **dispatch 后不点保存就 navigate**：改动丢失
6. **多个 ProseMirror**：标题短、正文长，用 innerText 长度区分
7. **正文图片勿动**：替换文字时用文本节点遍历（`NodeFilter.SHOW_TEXT`），不碰 `img`
8. **发表地区（位置）是自动定位，非手动设置**：编辑器底部「位置」设置 `#js_btm-poi-container` 默认 `display:none`；点「添加当前位置信息」若提示「未开启位置信息授权」，是浏览器 Geolocation 权限被拒（`navigator.permissions.query({name:'geolocation'})` 返回 `denied`）。文章标题下的省份（如「广东」）是发布时按 IP 自动定位的，改不了；要让某地区显示，就用该地区网络 + 已授权位置的浏览器（本地 Chrome）发布

## 9. 配套：用 HTML 生成公众号配图（如日程表图）

要放图（日程表/名单等）时，先生成 HTML 再用 browser-act 整页截图，比直接画图灵活、可复用。

- 样式模板（精致商务风，已验证）：深蓝渐变标题栏（`linear-gradient(135deg,#14304F,#2E5B9A,#3A6EA8)`）+ 底部金色分隔线 + 胶囊徽标；白色圆角胶囊信息条；渐变浅蓝表头；**日程行隔行变色**（`row-even`/`row-odd`）＋茶歇/午餐等休息行浅蓝灰；时间列金色加粗；整体 `.card` 圆角+阴影
- 宽度：正文配图设 **1400px**（公众号清晰度上限附近），字号标题 26px / 正文 16~17px
- **标题栏 td 必须 `colspan="4"`**（漏了会只占一列宽导致换行）
- 截图：`browser-act --session X screenshot --full <out.png>`（headless 视口固定 1902，无法 `resizeTo`）
- 截图会含背景 → 用 PIL 自动裁剪内容区（扫描非背景色列的左右边界）得到干净整图
- 生成脚本可用 `openpyxl`/`pandas` 读数据 + Python 拼 HTML；数据里空题目/空单位照实留空

## 10. 配套：解析 WPS 生成的问题 xlsx

`openpyxl` 读取部分 WPS 生成的 xlsx 会报 `TypeError: Fill() takes no arguments`（样式解析 bug，`pandas` 底层也用 openpyxl，同样失败）。替代方案——**用 zipfile 直接解析 XML**：

```python
import zipfile, re, xml.etree.ElementTree as ET
M = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
z = zipfile.ZipFile('xxx.xlsx')
# 共享字符串
shared = [''.join(t.text or '' for t in si.iter(M+'t'))
          for si in ET.fromstring(z.read('xl/sharedStrings.xml').decode('utf-8')).findall(M+'si')]
# 单元格（sheet 名→文件见 xl/_rels/workbook.xml.rels，sheet 内 rId 见 workbook.xml）
root = ET.fromstring(z.read('xl/worksheets/sheet2.xml').decode('utf-8'))
for row in root.iter(M+'row'):
    for c in row.iter(M+'c'):
        v = c.find(M+'v')
        val = shared[int(v.text)] if c.get('t')=='s' and v is not None else (v.text if v is not None else '')
        # col = re.match(r'([A-Z]+)', c.get('r')).group(1)
```

- 列位置不固定（有的日程在 A-D 列、有的在 I-M 列）→ **定位含「时间 Time」的表头行，从该单元格列号 +1/+2/+3 推断题目/报告人/单位列**
- 大段数据先 dump 成 JSON 再喂给 HTML 生成脚本，避免命令行超长被截断（base64 传长文本也会被截断）
