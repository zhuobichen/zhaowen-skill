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
python $SKILL/render_wechat.py <build_dir> [--embed] [--strip-brackets] [--max-width 1440]

# ③ 推送草稿箱（需先登录拿到当前 token）
python $SKILL/push_to_mp.py <build_dir> --token <TOKEN> --session <SESSION>
```

- `render_wechat.py` 不带 `--embed` 产出 `article.html`（相对路径，供浏览器预览）；带 `--embed` 产出单文件（推送用，`push_to_mp.py` 内部自行内嵌，不必手动生成）
- `--strip-brackets` 去掉题注外层【】，视觉更干净；**默认保留原文**
- 推送前可 `--dry-run` 看分批情况

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
- 推送后需**轮询等待**所有图 `data:` 前缀消失（`push_to_mp.py` 已内置，最多等约 2 分钟）

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

**会议通稿的卡片化配方**（本 skill 默认）：

| 元素 | 处理 |
|---|---|
| 页面底色 | `#F2F6FA` 冷调浅蓝灰（比纯白有质感，且不与照片里的蓝冲突） |
| 图片 | 白色卡片 `radius 12px` + `box-shadow 0 4px 16px rgba(15,76,129,.10)` |
| 图注 | 放在图片卡片**内部**下方居中，13px `#9AA5B1` |
| 正文 | 白色卡片，`padding 18px 16px` |
| 分节标题 | 实底蓝兜底 + 135° 渐变 + 编号徽标 |

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

会议通稿常见「一张图配一条题注」，但原文经常不规整。`parse_docx.py` 的规则：

- 图片段落**自带文字** → 该文字即题注（如 `[我的题注][IMG]【xx致辞】`）
- **题注段落紧跟图片段落** → 归给紧邻的**前一张**图
- **两张图共用一条题注** → 题注归**最后一张**，前面的图**保持无题注**（不臆造、不复制）
- 无题注的图会在解析结果里列出来供人工确认

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
- 图片默认压到**最大宽 1440**、JPEG q88（实测 29.5MB → 7.1MB，肉眼几乎无差）
- 标题**不进正文**——写进微信「标题」字段，避免与平台标题重复
- 首尾各插一个 `font-size:0;line-height:0;margin:0` 的空 `<p><br></p>`（借鉴 doocs/md），保住编辑器首尾空行
- 配色控制在 **3 色以内**（主色 + 灰 + 正文色），这是通稿排版的通行约束

## 推送后校验（别跳过）

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

## 相关

- `clz_wechat_mp_ops`：微信后台通用操作（ProseMirror dispatch 改字、配图生成、四层校验、批量替换草稿配图）
- 样式参考：`doocs/md`（**WTFPL**，可自由借鉴）；`lyricat/wechat-format` **无 LICENSE 不可抄**
