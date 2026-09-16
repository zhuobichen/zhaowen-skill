# 链路实测记录（2026-09-16）

本文件记录 `clz_docx_to_mp` 全链路的**原始验证证据**。结论已写进 SKILL.md，
这里保留证据与「为什么这么设计」，便于日后微信改版时对照排查。

**环境**：browser-act 1.4.2 · 微信公众平台编辑器（ProseMirror）· 2026-09-16

---

## 1. 新建草稿：`isNew=1`

`clz_wechat_mp_ops` 里记载的全部是「编辑已有草稿」，新建是空白。实测：

```
GET https://mp.weixin.qq.com/cgi-bin/appmsg
      ?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&createType=0&token=TOKEN&lang=zh_CN
```

直接打开**全新空编辑器**：空标题（`textarea#title`，placeholder「请在这里输入标题」）、
空正文（`.rich_media_content > .ProseMirror`，placeholder「从这里开始写正文」）、正文字数 0。

点击 `span#js_submit` 里的 button 保存后，URL 变为：

```
.../cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=77&appmsgid=APPMSGID&token=...
```

即 `isNew=1` → `appmsgid=<ID>`，保存成功。

## 2. 正文注入：`view.pasteHTML` 可用

正文 ProseMirror 的 EditorView 暴露了 `pasteHTML` 方法（同族还有 `pasteText`）。
该 view 需通过 Vue 实例链取得，且**必须用 `.rich_media_content` 定位正文**——
页面上有两个 ProseMirror（标题 / 正文），标题那个的父容器是 `.title-editor__input`。

实测注入：

```js
view.pasteHTML('<p style="color:#0F4C81;font-size:16px;">测试段落甲</p>')
```

结果（编辑器 DOM）：

```html
<p style="color:#0F4C81; font-size:16px;" data-pm-slice="0 0 []">
  <span leaf="">测试段落甲：这是一次草稿链路验证。</span>
</p>
```

- 内联样式**完整保留**
- 微信自动包 `<span leaf="">`（平台「叶子」机制）

## 3. 图片：base64 → 自动上传 CDN

注入 `<img src="data:image/png;base64,...">` 后：

1. 微信立即把它当作真图片节点，加上 `class="rich_pages wxw-img"`、`contenteditable="false"`
2. **数秒后 src 自动换成 CDN 地址**：`https://mmbiz.qpic.cn/sz_mmbiz_png/...`
3. 网络日志确认两条 `POST /cgi-bin/uploadimg2cdn` 返回 **200**

> 这是本 skill 相对「逐张 `browser-act upload` file input」路线的核心优势：
> 43 张图可以靠 base64 批量进，不必逐张上传。

## 4. 图注：`figure`/`figcaption` 存活

部分资料（含 `ufologist/wechat-mp-article`、`isjiamu/gzh-design-skill`）称
「微信编辑器会剥掉 figcaption」，主张改用 `section` + `p`。**实测结论相反**：

注入

```html
<figure><img ...><figcaption style="text-align:center;color:#888;font-size:13px;">图注A</figcaption></figure>
```

重新加载草稿后，`document.querySelector('figure figcaption')` **仍在**，样式保留。

两条写法都验证可用，本 skill 选用语义化的 `figure`/`figcaption`。
若日后微信改版导致失效，改回 `section` + `p` 是 `render_wechat.py` 里两行的改动。

## 5. 端到端持久化

保存草稿后，**重新加载** `...&appmsgid=APPMSGID`：

```
bodyText: 测试段落甲… | 测试段落乙… | 测试小标题 | 正文段落测试文字。 | 图注测试A-figcaption | 图注测试B-p标签
imgCount: 3      （全部 mmbiz.qpic.cn，无 data: 残留）
hasH2: true      hasFigcaption: true
```

文字、样式、图片、`<h2>`、`<figcaption>` **全部持久化**。

---

## 6. 踩过的坑

| 坑 | 现象 | 解法 |
|---|---|---|
| 中文经 shell 传递损坏 | `'utf-8' codec can't encode character '\udc98'` | 用 `json.dumps(s)`（`ensure_ascii=True`）转成 `\uXXXX` 纯 ASCII 字面量 |
| eval 参数过长 | `WinError 206 文件名或扩展名太长` | Windows argv 上限约 32767 字符 → 改用 `eval --stdin` 管道 |
| 模块导入后 print 崩 | `ValueError: I/O operation on closed file` | 模块级 `TextIOWrapper` 被重复包装，GC 时关掉底层 buffer → 加 `__name__ == '__main__'` 守卫 |
| screenshot 超时 | 页面含 43 张图（约 39000px 高）时 100s 超时 | 重试一次；长文预览只截视口，别整页 |
| 图片找不到 | 分批只出 1 批、图片数为 0 | `content.json` 里是原始文件名，压缩后统一变 `.jpg` → `push_to_mp.py` 自行重映射 |
| 标题设了但没落库 | 脚本返回 `TITLE_SET`，重载后 `textarea#title.value` 为空 | 只改 textarea / 只删除标题 ProseMirror 都不行，必须 `document.execCommand('insertText', false, t)` 真正写入标题 ProseMirror |

## 7. 未验证 / 待观察

- **发布后的手机端渲染**：本次只验证到「草稿箱编辑器内持久化」。`figure`/`figcaption`
  在正式发表页（非编辑器环境）的渲染未实测——因为发表会推送给关注者，不能在验证阶段做。
  如用户反馈排版异常，优先怀疑此处。
- **极大图片**：本次最大单图压缩后约 350KB。未测超过微信 `uploadimg2cdn` 上限的图（原图 17MB 已本地压缩规避）。
- **token 生命周期**：本次全程约 40 分钟内有效，未测过期边界。
