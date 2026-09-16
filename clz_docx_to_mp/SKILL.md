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
| 主色 | `#0F4C81`（藏青蓝） |
| 链接色 | `#576b95`（微信官方蓝） |
| 正文 | 16px / 行高 1.75 / `#3f3f3f` / 两端对齐 / 不缩进 |
| 分节标题 | 蓝底白字、居中、加粗、`border-radius:4px` |
| 图片 | `max-width:100%`、`border-radius:4px`、块级居中 |
| 图注 | 13px / `#888888` / 居中 |

- 图片默认压到**最大宽 1440**、JPEG q88（实测 29.5MB → 7.3MB，肉眼几乎无差）
- 标题**不进正文**——写进微信「标题」字段，避免与平台标题重复
- 首尾各插一个 `font-size:0;line-height:0;margin:0` 的空 `<p><br></p>`（借鉴 doocs/md），保住编辑器首尾空行

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

## 相关

- `clz_wechat_mp_ops`：微信后台通用操作（ProseMirror dispatch 改字、配图生成、四层校验、批量替换草稿配图）
- 样式参考：`doocs/md`（**WTFPL**，可自由借鉴）；`lyricat/wechat-format` **无 LICENSE 不可抄**
