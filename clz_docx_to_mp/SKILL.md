---
name: clz_docx_to_mp
description: |
  把 docx / Word 文档转成微信公众号图文并推送草稿箱。当用户要求：文档发公众号、docx 转公众号文章、
  给 Word 稿排版、公众号样式美化、会议通稿/新闻稿上公众号、批量图文推草稿箱 时使用。
  触发词：docx转公众号、Word发公众号、公众号排版、文档转图文、推到草稿箱、公众号样式、通稿上公众号。
  三步流水线：解析 docx → 渲染微信兼容 HTML → 推送草稿箱。内容按原文忠实保留，只做样式。
  涵盖：新建草稿 URL、pasteHTML 注入、base64 图片自动上传 CDN、图片压缩、内联样式硬约束、
  figure/figcaption 实测结论、题注归属规则、分批推送、推送后校验。
  配套 skill：clz_wechat_mp_ops（改已有草稿 / 发布侧）。
  不要用于：Markdown 转公众号（用 md2wechat 系工具）、纯文章写作（用 khazix-writer）。
---

# docx → 微信公众号图文

> 目标：把一份 docx 忠实转成**样式好看**的公众号图文，推进草稿箱。
> 原则：**内容一字不改，只做排版**。改编、润色、补写属于写作，不属于本 skill。

## 前置环境

- **browser-act CLI**：`C:\Users\Administrator\.local\bin\browser-act.exe`（**不在 PATH**，脚本里用绝对路径）
- **python-docx** + **Pillow**：已安装
- 微信公众平台需**管理员扫码登录**，token 几小时后过期
- 配套 skill：`clz_wechat_mp_ops`（ProseMirror / token / 校验的通用经验）

## 三步流水线

```bash
SKILL=~/.claude/skills/clz_docx_to_mp/scripts

# ① 解析 docx → content.json + images/
python $SKILL/parse_docx.py <input.docx> <build_dir>

# ② 渲染 → 微信兼容 HTML（同时压缩图片到 images_web/）
python $SKILL/render_wechat.py <build_dir> [--embed] [--strip-brackets] [--max-width 1080]

# ③ 推送草稿箱（需先登录拿到当前 token）
python $SKILL/push_to_mp.py <build_dir> --token <TOKEN> --session <SESSION>
```

- `render_wechat.py` 不带 `--embed` 产出 `article.html`（相对路径，供浏览器预览）；带 `--embed` 产出单文件（推送用，`push_to_mp.py` 内部自行内嵌，不必手动生成）
- `--max-width 0` 表示不缩放（原尺寸交给微信处理）
- `--strip-brackets` 去掉题注外层【】，视觉更干净；**默认保留原文**
- 推送前可 `--dry-run` 看分批情况

## 微信平台的硬性限制（决定图片规格）

| 项目 | 限制 | 本 skill 的应对 |
|---|---|---|
| **正文图宽度** | **> 1080px 一律压到 1080px**（硬顶，绕不过） | **主动缩到 1080**（LANCZOS），别让微信去缩——控制权在自己手里 |
| 单图大小 | ≤ 10MB（2023 年由 5MB 提到 10MB） | 压缩后最大约 300KB，远低于上限 |
| 单图像素 | 宽×高 ≤ 600 万 | 1080×720 = 78 万，安全 |
| 正文图片数量 | **无限制** | 43 张没问题 |
| 正文字数 | ≤ 20000 字 | — |
| 标题 | ≤ 64 字 | — |
| 摘要 | ≤ 120 字（不填则自动抓正文前 64 字） | 本 skill 不设摘要 |

**关键认知**：**「让图片更完整地上传」在宽度上没有空间**——1080 是平台硬顶，
原图再大也会被压。能做的是**别让微信做那个缩放**，自己用高质量重采样缩到 1080，
再把质量给足，抵消微信那次重编码的损失。

### ⭐ 画质杀手：JPEG 色度子采样（`subsampling`）

**这是最容易被忽略、但对「清晰度」观感影响最大的一项。**

PIL 的 `Image.save(..., 'JPEG')` 默认用 **4:2:0 色度子采样**——把色彩分辨率砍掉一半。
后果：**彩色背景上的细白字会拖出红橙色边**（色度伪影），看起来就是「图糊」「不清晰」。

```python
im.save(dst, 'JPEG', quality=95, subsampling=0,   # 0 = 4:4:4，关闭子采样
        optimize=True, progressive=True)
```

实测对照（演示文稿截图，蓝底白字）：

| 版本 | 单图体积 | 白字边缘 |
|---|---|---|
| 原图 PNG | — | 干净 |
| q92 + **4:2:0**（旧） | 118 KB | ❌ 明显红橙彩边 |
| q95 + **4:4:4**（现） | 230 KB | ✅ 接近原图 |
| q85 + 4:2:0 | 82 KB | ❌ 最差 |

代价是体积约翻倍（43 图 6.8MB → 11.9MB），推送批数变多、更慢。**值得**——
尤其通稿里有大量「彩色背景 + 白字」的演示文稿截图时。

> 若体积不可接受，优先保 `subsampling=0`、降 `quality` 到 90，而不要反过来。

> 实测：上传 1269px 的图，微信存下来是 **1080px**（`naturalWidth` 实测确认）。
> 另注：社区实测 JPG/PNG 在宽度 ≤1080 时**不被缩放**，只做重编码；
> 图片走 API 上传另有 **1MB** 的单图限制（比后台手传的 10MB 严得多）。

## 微信兼容性硬约束（实测结论，务必遵守）

| 约束 | 说明 |
|---|---|
| **不能用 `<style>` 块 / class 选择器** | 微信编辑器会剥掉。样式必须**全部 inline** |
| **不能用 `var()` / `calc()`** | 微信不认。所有值在渲染期就写死字面值 |
| **图片尺寸走 `style`，不用 `width`/`height` 属性** | 微信会剥属性 |
| **不设置 `font-family`** | 有实测记录：带了字体设置会导致样式被丢弃（ufologist/wechat-mp-article 踩坑实录） |
| 图片宽度用 `max-width:100%` | **不要写 `width:100%`**，小图会被拉糊 |

### 已实测可用的能力（2026-09，browser-act 1.4.2 + 微信编辑器当前版本）

| 能力 | 结论 |
|---|---|
| 内联 `style`（color/font-size/line-height/text-align/background） | ✅ 完整保留并持久化 |
| `<h2>` 等标题标签 | ✅ 存活 |
| `<figure>` + `<figcaption>` | ✅ **存活且持久化**（与部分资料的「微信会剥 figcaption」说法相反） |
| `<img src="data:image/...;base64,...">` | ✅ **微信自动上传 CDN**（`cgi-bin/uploadimg2cdn`），src 被换成 `mmbiz.qpic.cn` |
| `view.pasteHTML(html)` 注入空正文 | ✅ 可用（正文 ProseMirror 的 EditorView 方法） |

## 关键机制

### 1. 新建草稿（`clz_wechat_mp_ops` 里没有的能力）

直接导航到下面的 URL 即可打开**全新空编辑器**（`isNew=1` 是关键）：

```
https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&createType=0&token=TOKEN&lang=zh_CN
```

保存后 URL 自动变成 `...t=media/appmsg_edit&action=edit&type=77&appmsgid=N&token=TOKEN`，`appmsgid` 即新草稿 ID。

### 2. 注入正文：`pasteHTML`

```js
// 取正文 EditorView（正文的父容器是 .rich_media_content，与标题编辑器区分）
var pms = document.querySelectorAll('.ProseMirror'), body = null;
for (var i=0;i<pms.length;i++){ var par=pms[i].parentElement;
  if (par && (par.className||'').indexOf('rich_media_content')!==-1) body = pms[i]; }
var el = body, vue = null;
for (var k=0;k<12 && el;k++){ if (el.__vue__){ vue=el.__vue__; break; } el=el.parentElement; }
var view = vue['$options']['parent']['$parent']['__editorView'];
window.__mpView = view;
// 注入
view.pasteHTML('<p style="color:#0F4C81;font-size:16px;">正文</p>');
```

- `pasteHTML` 在**光标处追加**，粘贴后光标自动移到末尾 → **分批顺序拼接即可**
- 微信会自动把文字包进 `<span leaf="">`（平台「叶子」机制），并给图片加 `class="rich_pages wxw-img"`、`contenteditable="false"`

### 3. 图片：base64 内嵌，微信自动传 CDN

**这是本 skill 相对「逐张 file input 上传」的最大优势**——43 张图不必逐张 upload：

- 渲染时把图片转成 `data:image/jpeg;base64,...` 内嵌进 HTML
- `pasteHTML` 后微信自动调 `uploadimg2cdn` 上传，几秒后 src 变成 `mmbiz.qpic.cn`
- 推送后需**轮询等待**所有图 `data:` 前缀消失（`push_to_mp.py` 已内置，最多等 240s——高画质模式下 43 图约 16MB base64，上传明显更慢，等待窗口要给足否则误报）

### 4. 分批推送

单次 eval 的 payload 不宜过大，`push_to_mp.py` 按 **1.2 MB/批** 切块（实测 43 图 ≈ 9 批）。
JS 字符串先用 `json.dumps(html)`（`ensure_ascii=True`）编码成纯 ASCII 字面量，**规避中文与编码问题**——直接把中文塞进 shell/JS 会损坏。

### 5. 保存

点击 `span#js_submit` 里的 `button`（同 `clz_wechat_mp_ops` §7）。保存后读 URL 拿 `appmsgid`。

### 6. 设置标题（有坑）

标题编辑器是**另一个** ProseMirror（父容器 `.title-editor__input`）。**两种写法都不落库**：

- ❌ 只改 `textarea#title.value` + 派发 input
- ❌ 只对标题 ProseMirror 做「全选 + `deleteFromDocument()`」

必须**真正把文本写进标题 ProseMirror**：

```js
var pm = /* 父容器含 title-editor 的那个 .ProseMirror */;
pm.focus();
var r = document.createRange(); r.selectNodeContents(pm);
var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
document.execCommand('insertText', false, title);   // ← 关键，别漏
var ta = document.getElementById('title');
if (ta) { ta.value = title; ta.dispatchEvent(new Event('input', {bubbles:true})); }
```

> 实测教训：漏掉 `execCommand` 那步时，脚本会「成功」返回但**保存后重载标题是空的**。
> 校验时务必重载草稿、读 `textarea#title.value` 确认。

## 封面（可直接复用正文图，无需二次上传）

正文图已经传到了微信 CDN，设封面时**用「从正文选择」直接挑**，不必重新上传：

1. 点封面区 `.js_cover_btn_area`
2. 弹层里点 `.js_selectCoverFromContent`（文案「从正文选择」）
3. 「选择图片」对话框里选 `.appmsg_content_img_item`——**索引与正文图片顺序一一对应**
   （0 基）。选中的项会带上 `selected` class，可据此确认选对
4. 点「下一步」→ 进入「编辑封面」，两个比例：`2.35:1`（消息列表）/ `1:1`（转发卡片和主页）
5. 点「确认」→ **再点「保存为草稿」**，否则封面不落库

> 常规做法是拿正文第一张图当封面（通稿常是合影/现场全景）。
> 若原图比 2.35:1 更宽（如合影长图），裁剪会切掉左右各约 6%，微信默认居中裁——
> 一般可接受；要精确构图得手工拖裁剪框。

## 版式蓝本：2024 年同系列会议文章（领导指定）

**参考文章**：`https://mp.weixin.qq.com/s/NK6oHHieNbtPrSTAl3wBmg`
（2024年大气污染控制费效与达标评估暨大气霾化学国际学术研讨会在沪召开）

**完整实解见 `references/template-2024-abaas.md`。** 这是本 skill 默认主题
（`THEME['name'] = 'abaas2024'`）的直接来源。**核心特征：无外框、无整篇底色；
正文包在 `#F4F8FC` 浅蓝圆角卡片里；章节标题是「内联 SVG 星形 + 蓝字 + 渐变下划线」。**

| 元素 | 参考文章实取值 |
|---|---|
| 正文容器 | **`#F4F8FC` 浅蓝圆角卡片**（`padding:15px` / `border-radius:10px`），一卡装多段 |
| 正文 | `line-height:2em; text-indent:2.1875em`；文字 16px `#3F3F3F`，字距 1.5px |
| 分节标题 | **内联 SVG 星形（`fill:#4F81BD`）+ 蓝色加粗标题 + 向右渐隐的渐变下划线** |
| 图片 | 通栏，图注 **15px `#888888` 居中、字距 1px、不带【】** |
| 主色 | `#4F81BD`；亮蓝 `#1D81E6`；青 `#76C5CB`；细线 `#4E83BC` |
| 字体 | 设在**最外层 `<section>`** 上（不是文字节点）：`font-family:微软雅黑, "Microsoft YaHei"` |

### ⚠️ 无分节标题的稿子：用「分段装饰件」补节奏，不要自己加标题

2024 模板最标志的元素是 SVG 星形标题条，但**有些稿子（如 v6）本身没有分节标题**。

此时**不要自己加标题**——那会引入原文没有的文字，读者无法分辨哪句是作者写的。
本 skill 的做法：不渲染任何标题条，改为在**相册前放一枚模板自带的分段装饰件**
（两枚渐变小竖条 + 蓝细线，见 `DIVIDER` 常量）来补视觉呼吸。纯装饰，零文字。

> 领导要求「模板一致」时尤其要守住这条：**版式可以对齐，内容不能补。**
> 若确实需要标题，先向用户确认——那是内容决策，不是排版决策。

### ⚠️ 不要「每元素一张卡片」

早期版本给每张图、每段正文各套一张白色圆角卡片 + 柔和阴影。**实测反馈是「连贯性不强，有点隔开」**——
43 张图变成 43 张卡，文章被切成一节一节。参考文章的做法恰恰相反：**一个框，内容连续**。
卡片化只在极少数「需要强调的独立信息块」上才用。

### 分批推送时怎么做出「一个框」

推送要分多批 `pasteHTML`，而 `pasteHTML` 会自动闭合未闭合标签，跨批次的单个 `<section>` 包不住。
解法（`frame_wrap(html, theme, first, last)` 已实现）：

- **每批**都带 `border-left` + `border-right`
- **首批**额外带 `border-top`
- **末批**额外带 `border-bottom`，并补上右下角的硬投影
- 中间批只向右侧投影（`box-shadow:7px 0 0 0`），拼起来才是一条连续的硬投影

#### ⚠️⚠️ 外框样式必须显式写 `margin:0`（否则每批之间断 24px）

**微信编辑器给 `<section>` 默认加了 `margin-bottom: 24px`。** 外框样式若不显式声明
`margin`，这个默认值就会生效——**9 批就是 8 条 24px 的缝，框断成一节一节**。

```
实测：computed margin = "0px/24px"  ← 上 0、下 24，来自微信的样式表
```

外框的 inline style 里 **`margin:0;` 不能省**。这条踩过，用户反馈「中间有没有断的地方」才发现。

#### 推送后必须自动校验接缝（`push_to_mp.py` 第 ⑦ 步已内置）

靠肉眼在 4 万像素的长文里找 24px 的缝是不现实的。脚本现在会自动量测：

- 各批次之间的 `gap`（应为 **0**）
- 各批次的 `left` / `width` 是否一致（不一致 = 框左右错位）
- 图片是否全部上 CDN、图注/分节标题/END 线是否齐全

> 判据来自真实教训：`gaps:[]` 才算过；出现任何非 0 值，**优先怀疑外框样式漏了 `margin:0`**。

## 横向可滑相册（图多时用）

结构实测自 **2024 年同系列会议文章**（`mp.weixin.qq.com/s/NK6oHHieNbtPrSTAl3wBmg`），
那篇里有两个相册：8 张和 11 张。

```html
<!-- 外层：横向滚动容器 -->
<section style="width:100%;vertical-align:top;overflow:auto;
                scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;">
  <!-- 行宽 = 100% × 图片数（8 张就写 800%） -->
  <section style="width:800%;display:flex;flex-flow:row;max-width:800% !important;">
    <!-- 每项宽 = 100% ÷ 图片数（8 张就写 12.5%） -->
    <section style="vertical-align:top;width:12.5%;scroll-snap-align:center;
                    max-width:12.5% !important;">
      <figure>…图片 + 图注…</figure>
    </section>
    …
  </section>
</section>
```

**三个必须配套的点，缺一个就滑不动**：

1. **外层用 `overflow:auto`（不是 `overflow-x`）**——实测微信只认 `overflow:auto`
   （这也是一个排查坑：搜 `overflow-x` 找不到任何相册）
2. **行宽 = `100% × N`，项宽 = `100% ÷ N`**，两者必须配套；`max-width` 也要跟 `!important`
3. 外层要有 `scroll-snap-type:x mandatory`，滑动才会一屏一屏对齐

### ⚠️ 相册内必须等高，否则矮图下方留大片空白

相册是 flex 行，**行高由最高的一项决定**。横竖混排时竖图把行撑高，
横图下方就空出一大块——实测 26 张里混 2 张竖图，横图下方各空约 300px。

**解法**：进相册前把比例统一裁成 `GALLERY_RATIO`（3:2，与 2024 模板一致），
`gallery_variant()` 已实现（居中裁；比例本来就对的原样不动）。
**只裁进相册的图**——平铺的图是纵向堆叠的，比例不同不影响观感。

> 校验：`push_to_mp.py` 第 ⑦ 步的 `heights` 字段，**必须为 1**（全等高）；
> >1 就是混排，会报问题。

### 动效：CSS 动画做不了，但 **GIF 可以** ⭐

**先纠正一个我下早了的结论**：最初查 2024 模板时看到「正文 `animation`/`transition` 各 0 处」，
就断定动效做不了。**漏了 GIF**——GIF 就是普通 `<img>`，微信正常上传播放，
是正文里**唯一可行**的动效手段。

**CSS 动画确实不行**（两条硬约束）：

1. `@keyframes` 只能写在 `<style>` 里，而微信会剥掉 `<style>` → 内联写 `animation:xxx` 也没用
2. `transition` 需要 hover/active 触发，内联样式定义不了伪类，移动端也没有 hover

**GIF 可行**——2024 模板实际用了两个（已提取存到 `assets/`）：

| 文件 | 尺寸 | 帧数 | 用途与摆法 |
|---|---|---|---|
| `deco-bird.gif` | 466×343 | 67 | **内容块右上角**：`width:50px; margin-left:auto; margin-bottom:-15px`（负边距压住卡片上沿） |
| `deco-arrow-down.gif` | 200×269 | 13 | **分节之间的下滑引导**：`width:44px; margin:0 auto`（居中） |

**管线接线要点**：

- GIF **绝不能走 `compress_images`**——会被重编码成 JPEG，只剩第一帧，动画全丢。
  已在 `compress_images` 里对 `.gif` 原样跳过。
- `to_data_uri` 的 mime 表要含 `.gif` → `image/gif`，否则 MIME 错了播放不了。
- 素材放 skill 的 `assets/`；预览时拷到 build 目录走相对路径，推送时直接 base64 内嵌。

> ⚠️ **素材来源**：这两个 GIF 是从 2024 年同系列会议文章里提取的。
> 属第三方素材，非本 skill 原创——**换机构/换号使用前应先确认授权**。

### 滚动条美化：只能用可内联的标准属性

微信会剥掉 `<style>`，所以 `::-webkit-scrollbar` 那套自定义样式**用不上**。
能内联设置、且微信会保留的只有：

```html
<section style="… overflow:auto; scrollbar-width:thin;
                scrollbar-color:#4F81BD #F4F8FC;">
```

- `scrollbar-width:thin` → 细条
- `scrollbar-color:<滑块色> <轨道色>` → 主色滑块 + 浅底轨道

**不要把滚动条直接隐藏**（`scrollbar-width:none`）：用户明确要求保留可拖动的滑条。
真机上微信的滚动条本来就会自动隐藏／半透明，桌面端才是那条难看的灰条。

### 相册下方要有滑动提示

2024 模板在相册**后一个兄弟节点**放了提示，原文照抄：

```html
<section><p style="text-align:center;font-size:15px;letter-spacing:2px;line-height:1.6em;">
  <span style="color:#888888;letter-spacing:1px;">◁ 左右滑动查看更多 ▷</span>
</p></section>
```

### 哪些图进相册、哪些平铺

用户口径：**「致辞的六个人都放出来，不用滚动，其余的是滚动」**——通稿的开幕式致辞段，
读者要一眼看全每位致辞人，不该藏进相册。

`render_blocks(gallery=True)` 的分组线判定：

| 稿子类型 | 分组线 |
|---|---|
| 有分节标题（`Heading 1`） | **第一个标题之后**开始合组 |
| **没有分节标题**（如 v6 稿） | 用 `gallery_anchor` 指定文字，**遇到含该文字的段落之后**开始合组（默认「主旨报告」） |

`--no-gallery` 可整体关掉相册、全部平铺；`--gallery-anchor "xxx"` 换锚点。

> 校验：`push_to_mp.py` 第 ⑦ 步会量每个相册的 `scrollWidth` 与可见宽，
> `scrollWidth > 可见宽 × 1.5` 才算「真的能滑」。

## 背景色与卡片化（「白花花」的解法与最大的坑）

**症状**：整篇纯白，只有零星主色点缀，显得寡淡。根因是**最外层容器没有底色**。

**但背景色有个大坑**（来源：`AAAAAnson/mbeditor` MIT，2026-06 实测）：

> 微信会**解包** `<article>` `<main>` `<header>` `<footer>` `<aside>` `<nav>` 等语义标签——
> 子内容保留，但**标签连同 style 一起被丢**。页面级背景写在单一外层容器上，
> 一旦该标签被解包，**整页背景变白、内层背景还在**。

**可靠做法：每个顶层块各自重复写 `background-color`**，且：

- 块之间**不留 margin**，间隙由各块自身的 `padding` 提供 → 相邻同色块视觉连成一片
- 用 `<section>` 而非 `<div>`（`div` 的样式继承在微信里有时会丢）
- 本 skill 还额外套了一层同色外层容器：**外层被剥还有内层，内层被剥还有外层**，双保险

```html
<!-- 每个顶层块长这样 -->
<section style="background-color:#F2F6FA;padding:9px 12px;">
  <figure style="margin:0;padding:8px;background-color:#FFFFFF;border-radius:12px;
                 box-shadow:0 4px 16px rgba(15,76,129,0.10);">…</figure>
</section>
```

**其余已知约束**：

| 约束 | 后果 |
|---|---|
| `background-image` 加在 `section` 上 | 有「整个 section 被删」的社区报告 → **渐变前先给 `background-color` 兜底** |
| 正文卡片用网格/条纹 `background-image` | 深色模式下文字配色会错，别用 |
| `<body>` / 完整 HTML 文档背景 | 被剥，必须搬到 `section` 上 |
| 装饰性空元素内部不放假内容 | 节点被剥、样式一起消失 → 要塞 `<span leaf=""><br></span>` |
| 字号 > 24px | 容易被编辑器改写 |

**（历史方案，已被上方「版式蓝本」取代）** 曾用过「页面底色 `#F2F6FA` + 每个元素一张白卡片」，
底色确实解决了「白花花」，但卡片切碎了连贯性。**现在默认走「单外框 + 连续流淌」**。

> 设计参考：`laogou717/md-wechat`（**MIT**，26 套主题）、`chuanfan-ai/wechat-typesetter`（**MIT**）、
> `AAAAAnson/mbeditor`（**MIT**）。**不要用** `isjiamu/gzh-design-skill`（AGPL 传染）、
> `xiaohuailabs/xiaohu-wechat-format`（无 License）、`geekjourneyx/md2wechat-skill`（BUSL，禁商用）。

## docx 图片的旋转与裁剪（最容易踩的保真坑）

**症状**：导出的图里，本来竖着的照片变成了横躺的。

**根因**：Word 里「转正过的竖图」，在 docx 文件里存的是**躺倒的横图** + 一个旋转属性；
只取 `r:embed` 拿原始像素，就会把这类图原样导成横躺的。

`parse_docx.py` 已处理这两个属性：

| 属性 | 位置 | 含义 |
|---|---|---|
| `a:xfrm/@rot` | `<w:drawing>` 内 | 旋转角，单位 **1/60000 度，顺时针为正** |
| `a:srcRect` | `<w:drawing>` 内 | 裁剪，`l/r/t/b` 单位 **1/1000 百分号**（100000 = 100%） |

关键换算：`PIL` 的 `rotate()` **逆时针为正**，与 OOXML 相反 → 用 `im.rotate(-rot_deg, expand=True)`。
处理顺序是**先按 srcRect 裁剪，再旋转**。

> 本次实测：43 张图里 3 张带 `rot="16200000"`（270°）、其中 1 张还带 `srcRect` 裁剪。
> 不处理就会静默出错——图不会报错，只是方向不对，很容易漏过去。
> **验收时务必逐张看图**，别只看数量对不对。

## 题注归属规则（docx 常见歧义）

**规则**：题注段落配给**最近一张还没题注的图**（不是「紧跟的那张」）。

> 踩坑（v6 稿）：原实现要求题注紧跟图片，但 v6 是「图A、图B+自带题注、题注B」的错位排布——
> 上一张图配完自带题注后待配列表被清空，导致题注B 变成**孤儿正文段**。
> 改成「配给最近一张无题注的图」后，42 张图 42 条题注全中。

**标题兜底**：v6 这类稿子把标题写成普通段落（`Normal`），没有 `Title` 样式。
解析器会在末尾兜底：整篇没有 title、且**第一个 block** 是短段落且含
「研讨会/会议/召开/举行」→ 提升为 title，否则标题会整条丢失。

**其余细则**：

- 图片段落**自带文字** → 该文字即题注（如 `[我的题注][IMG]【xx致辞】`）
- 正文段**不清空**待配列表——「图、正文、题注」也是合法排布
- 实在配不上题注的图，解析结果里会列出来供人工确认

> ⚠️ 脚本**从不自行编造题注**。原文没有的就留空——宁可难看，也不要通顺但可能错的文字。

## 样式基线（藏青蓝主题）

| 元素 | 参数 |
|---|---|
| 主色 | `#0F4C81`（藏青蓝）→ `#2E5B9A`（渐变末端） |
| 链接色 | `#576b95`（微信官方蓝） |
| 正文 | 16px / 行高 1.75 / `#3f3f3f` / 两端对齐 / **不缩进** |
| 分节标题 | **135° 蓝渐变底 + 白字加粗 + 左侧半透明编号徽标（01/02）** |
| 图片 | `max-width:100%`、`border-radius:4px`、块级居中 |
| 图注 | **14px / `#999999` / 居中**（对齐通稿惯例） |
| 文末 | **END 渐隐装饰线**（用 table 实现，flex 在微信支持有限） |

- 编号 `01/02` 是**纯装饰**，不引入原文之外的内容。**不要自作主张给分节标题加英文译名**——那是替作者翻译，违反「内容不变」
- 图片默认压到**最大宽 1080**（微信硬顶，见上表）、**JPEG q95 + （4:4:4）**（实测 29.5MB → 11.9MB）
- **分节标题的编号 `01/02` 必须与标题同字号同字重同色**。曾用 13px + 半透明，
  用户反馈「明显比旁边的小」——那看着像出错而不是设计。要突出就整体突出，别缩字号
- 标题**不进正文**——写进微信「标题」字段，避免与平台标题重复
- 首尾各插一个 `font-size:0;line-height:0;margin:0` 的空 `<p><br></p>`（借鉴 doocs/md），保住编辑器首尾空行
- 配色控制在 **3 色以内**（主色 + 灰 + 正文色），这是通稿排版的通行约束

## 推送后校验（脚本已内置第 ⑦ 步，别跳过）

`push_to_mp.py` 保存后会**自动量测并报告**：外框接缝 gap（应为 0）、各段 left/width 是否一致、
图片 CDN 数、图注数、分节标题数、END 线。看到 `✅ 校验通过` 才算完成。

人工仍需复核的：
1. **重载草稿**确认标题在（`textarea#title.value`）
2. **逐张看图**——尤其 docx 里带 `rot` 的竖图方向对不对（脚本不会替你判断方向）
3. 手机端预览一遍整体观感



1. 重新加载 `...&appmsgid=N` 编辑页，确认**文字、图片、题注都在**
2. 检查图片 src 都是 `mmbiz.qpic.cn`（**无 `data:` 残留**，有残留说明上传没完成）
3. 逐张核对图片顺序与题注对应（尤其原文有歧义处）
4. 核对正文是否与 docx **逐字一致**——这是「内容不变」的底线

## 常见陷阱

1. **token 过期**：报「请重新登录」就重新登录换 token
2. **browser-act 不在 PATH**：用绝对路径 `C:\Users\Administrator\.local\bin\browser-act.exe`
3. **中文塞进 shell 会损坏**：一律用 `json.dumps(..., ensure_ascii=True)` 转义，别裸传中文
4. **screenshot 超时**：页面含几十张图时浏览器截图会超时（100s），重试一次通常能成；预览长文建议只截视口
5. **`images_web/` 与 `content.json` 文件名不一致**：压缩后统一改成 `.jpg`，`push_to_mp.py` 会自行重映射；若报「没有一张图匹配」，先跑 `render_wechat.py`
6. **`import render_wechat` 时 stdout 报 closed**：模块级 `TextIOWrapper` 重复包装所致，已加 `__name__ == '__main__'` 守卫，勿删
7. **`UnicodeEncodeError: 'ascii' codec can't encode ...`**：传给 `eval --stdin` 的 JS 含非 ASCII。
   中文一律用 `json.dumps(s)` 转义成 `\uXXXX`；**JS 注释里也不能写中文**（已踩过：一行中文注释
   导致推送在第 ⑤ 步崩掉，且因为崩在保存之前，整篇内容没落库）
8. **改动后重推别新建草稿**：加 `--appmsgid N` 复用已有草稿，会先清空正文再灌，
   避免草稿箱堆一串半成品。封面不会因此丢失
9. **`NO_VIEW`／清空失败**：微信编辑页加载完成后可能还有一次客户端重定向，会冲掉
   `window.__mpView`。**每一步都要自愈式重取**（`window.__ensureView()`），
   不能只在开头取一次——已踩过：开头取到 view、下一步清空就 NO_VIEW
10. **⚠️ 千万不要中断正在推送的任务**（已踩，代价大）：中途 kill 掉推送脚本，会留下
   **挂起的 `uploadimg2cdn` 请求**，那篇草稿的编辑页从此**永久卡在 `readyState=loading`**，
   换会话、重开浏览器都救不回来（同一篇的编辑页再也打不开）。
   诊断特征：`network requests --filter uploadimg2cdn` 里那批请求**有 URL 但没有 status**。
   处理：**放弃那篇草稿，推到一篇新草稿**（新建草稿的编辑器秒开，可用来确认是草稿坏了
   而非浏览器坏了）；坏掉的旧草稿只能人工去草稿箱删。
   预防：推送要么跑完，要么在**开始前**就决定不做——不要跑到一半喊停
11. **编辑页 navigate 报「未到达 DOMContentLoaded」**：编辑页很重时常见**误报**，
   页面其实已经可用。不要直接判死——等一下再验 `__ensureView()` 能不能取到编辑器即可

## 相关

- `clz_wechat_mp_ops`：微信后台通用操作（ProseMirror dispatch 改字、配图生成、四层校验、批量替换草稿配图）
- 样式参考：`doocs/md`（**WTFPL**，可自由借鉴）；`lyricat/wechat-format` **无 LICENSE 不可抄**
