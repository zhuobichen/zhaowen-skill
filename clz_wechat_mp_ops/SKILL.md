---
name: clz_wechat_mp_ops
description: >
  操作微信公众号后台（mp.weixin.qq.com）：登录、查看草稿箱/发表记录、读取图文草稿内容、编辑修改草稿文字（标题/正文）。
  当用户要求：修改微信公众号文章/草稿、把某篇草稿从旧版更新到新版、对比公众号文章与文档差异、
  在微信后台改文字（日期/邮箱/措辞/标题）、生成第三轮/新版通知并更新到草稿 时使用。
  涵盖：stealth/chrome-direct 登录与扫码、token 过期处理、草稿编辑页 URL 结构、ProseMirror 编辑器 DOM 结构、
  EditorView 实例获取、**修改正文唯一可靠方式（dispatch + 点"保存为草稿"按钮）**、标题修改、验证持久化、
  获取草稿 appmsgid（Vue 实例 $data.appid）、上传图片（file input 设可见 + upload）、图片删除/移动（inline image dispatch）、
  常见陷阱（直接改 DOM 部分保存 / 自动保存不监听 dispatch / token 过期回退）、
  配套技能（生成公众号配图 HTML→整页截图→PIL 裁剪 / 解析 WPS 问题 xlsx 用 zipfile XML / ABaCAS 日程图生成工具：
  gen_session_agenda.py 纯中文版、extract_bi_map.py 提取中英文映射、gen_session_agenda_bi.py 中英双语版（中文上英文下、主席先中后英）、
  diff_session_agenda.py 版本对比、update_mp_agenda.py 一键更新草稿，含 4 层发布前校验机制）等经验。
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

- 样式模板（精致商务风·方角版，已验证）：深蓝渐变标题栏（`linear-gradient(135deg,#14304F,#2E5B9A,#3A6EA8)`，白字）+ 白色方形标签（无圆角）；信息条方形白底；**表头蓝色渐变白字**（`linear-gradient(180deg,#4A7DBD,#2E5B9A)`）；正文全黑字（时间/题目粗体 20px、报告人/单位加粗 19px，靠粗体区分主次：题目→报告人/单位→时间）；休息行浅蓝灰；**整体不用圆角用方角**
- 宽度：正文配图设 **1400px**（公众号清晰度上限附近）；**标题栏 td 必须 `colspan="4"`**（漏了会只占一列宽导致换行）
- 截图：`browser-act --session X screenshot --full <out.png>`（headless 视口固定 1902，无法 `resizeTo`）
- 截图会含背景 → 用 PIL 自动裁剪**上下+左右**边界（扫描非背景色行列）得到干净整图；页眉矮图尤其要裁上下
- 生成脚本可用 `openpyxl`/`pandas` 读数据 + Python 拼 HTML；数据里空题目/空单位照实留空

## 11. 批量替换草稿中的配图（如更新日程图）

数据表更新→重新生成图后，把草稿里的一组旧图整体替换为新图（保留装饰小图/文字）：

1. 定位草稿 image 节点，**只删要替换的旧图**（如日程图），保留装饰小图（svg 尺寸小，如 63x150）：
   ```js
   // 收集所有 image 节点，保留前 N 张装饰图，删除其余（从后往前删避免 pos 偏移）
   var imgs=[]; view.state.doc.descendants(function(n,p){if(n.type.name==='image')imgs.push(p);return true;});
   var tr=view.state.tr;
   for(var i=imgs.length-1;i>=N;i--){ tr.delete(imgs[i],imgs[i]+1); }
   view.dispatch(tr);
   ```
2. file input 设可见（`opacity:1;position:fixed;top:0;left:0;z-index:99999`），`state` 找 index
3. **把光标设到文档末尾**再逐张上传，保证顺序：
   ```js
   var doc=view.state.doc; var Sel=view.state.selection.constructor;
   view.dispatch(view.state.tr.setSelection(Sel.create(doc,doc.content.size))); view.focus();
   ```
4. `browser-act upload <index> <图路径>` 逐张上传（上传后微信自动压到 1080 宽；立即检查 src 可能是 base64 占位，等几秒加载完变 CDN）
5. 点「保存为草稿」→ 重新加载验证：图片自然宽 1080、顺序对应内容
6. 删除时保留的装饰图（svg）尺寸小（63x150），别误删

## 12. 校验机制（发布前必检，严肃对待）

日程/通知要正式发布，必须多层检查，任何 ⚠️/❌ 都要人工确认后才发布：

### 第 1 层：数据校验（生成脚本内）
`gen_session_agenda.py` 解析后自动检查，输出需人工确认项：
- 每个分会场有名称 / 时间 / 日程行
- 题目为空（TBD/未填）、报告人为空（非茶歇午餐）→ ⚠️
- **空时段**（题目+报告人都空，如分会场1 的 17:35~17:50）→ ❌ 重点核实，可能是数据删除/未填

### 第 2 层：生成校验（生成脚本内）
- 12 张 PNG 都生成（合并图 + 分会场2~12）
- 每张宽 1406（截图正常），文件名对应
- 输出 `✅ [生成] 检查通过` 才算完成

### 第 3 层：上传校验（update_mp_agenda.py）
上传后等 8 秒（DATA 占位→CDN），检查：
- 图片总数 = 预期（如 2 svg + 12 = 14）
- 开头 2 张是装饰小图（63x150）
- **无 DATA 占位**（上传未完成必须重试）
- 首张日程图宽 1080（微信压缩，顺序正确）
- 有 ⚠️ 必须人工复核草稿，不能直接发布

### 第 4 层：版本差异核对
数据表更新后，用 `diff_session_agenda.py` 对比新旧版本，确认：
- 报告人/单位变化、新增/删除行（逐条看）
- **中英双语化**（题目从纯中/英文→双语，大量 [~] 属正常）
- 时间/地点/主席变化
- 发现"整体顺移/空时段"要回到原表核实数据

### 发布前最终清单
1. ✅ 生成校验通过（12 图全、宽 1406）
2. ✅ 上传校验通过（图数对、无占位、顺序对）
3. ✅ 数据层无 ❌（无空时段等硬伤）
4. ⚠️ 人工复核 TBD 题目/空项是否允许发布
5. 草稿重新加载，肉眼过一遍每张图（尺寸 1080 宽、内容对应）

> 任何一步出现 ⚠️/❌，宁可暂停核实，也不要带错发布。

## 13. ABaCAS 日程图生成工具（配套脚本）

位置: `E:/CodeProject/ABaCaS/ABaCAS会议数据/分会场拟邀请人与日程/日程图生成工具/`

| 脚本 | 作用 |
|------|------|
| `gen_session_agenda.py` | 解析分会场日程 xlsx → 生成 **页眉+分会场1 合并图** + 分会场2~12（精致商务风方角版，1400 宽）；内置数据校验 + 生成校验 |
| `extract_bi_map.py` | 从第四轮通知 docx 提取「中英文映射」文档（严格取 docx 原文，不自行翻译）：题目/报告人/单位中英 + 时间/地点/主席中英 |
| `gen_session_agenda_bi.py` | 中英双语版：`<最新xlsx> <中英文映射json>` → 生成中英双语日程图（中文上英文下） |
| `diff_session_agenda.py` | 版本差异对比：区分报告人/单位变化、仅题目双语化、增删行、时间/地点/主席变化 |
| `update_mp_agenda.py` | 一键流程：重新生成图 → 打开公众号（扫码）→ 定位会议议程草稿 → 删旧图 → 上传新图 → 上传校验 → 保存 |

用法：
```bash
python gen_session_agenda.py <xlsx>           # 纯中文版，生成图 + 校验
python extract_bi_map.py <第四轮docx>          # 提取中英文映射（严格 docx 原文）
python gen_session_agenda_bi.py <xlsx> <映射json>  # 中英双语版
python update_mp_agenda.py <xlsx>             # 生成图 + 自动更新公众号草稿
python diff_session_agenda.py <旧> <新> [更多] # 版本差异
```

- 输入 xlsx 为 WPS/Excel 生成的「分会场拟邀请人与日程安排」表（13 sheet：概览+12 分会场），用「时间 Time」表头行自动定位列，兼容 openpyxl 读不动的样式怪文件
- **头图方案**：页眉（会议议程·持续更新说明）与分会场1 合并成一张图，避免公众号图片间距（约 27px 平台固定）影响头部紧凑感
- 数据表更新后跑 `update_mp_agenda.py` 即可全自动完成「生成→更新草稿」

### 中英双语版规则（用户确认）

- **中英顺序**：题目/报告人/单位 **中文上、英文下**；本来就是英文的不加中文（如纯英文题目/外文名）
- **主席/召集人/主持人（特殊）**：**先全部中文（3行）再全部英文（3行）**，中间空一行（不用逐行对应）
- **中英来源优先级**：优先 xlsx 本身的中英（`split_cn_en` 提取原文）；xlsx 缺的中/英文才从第四轮映射补（`extract_bi_map.py` 严格取 docx 原文，**无自译**）；数据源都没有的 → 不补（留中文）
- **6 列错位表格**（如分会场12）：时间/题目/题目重复/报告人+英文/重复/单位+英文 → 用 列0/1/3/5 提取（`extract_bi_map.py` 已支持）
- **信息行**：每张图含 标题栏（中英主题）+ 时间/地点（中英）+ 主席/召集人/主持人（先中后英）+ 完整日程（题目/报告人/单位中英）
- **v10 值清洗为空须从映射补**：xlsx 里 `Venue:`（空值）不能被当成有值，清洗前缀后为空则用第四轮映射补

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
