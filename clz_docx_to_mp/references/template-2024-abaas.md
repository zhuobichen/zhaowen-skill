# 版式模板实解：2024 年 ABaCAS 会议文章

**来源**：`https://mp.weixin.qq.com/s/NK6oHHieNbtPrSTAl3wBmg`
（2024年大气污染控制费效与达标评估暨大气霾化学国际学术研讨会在沪召开）

这是同系列会议的**上一届**文章，是本 skill 默认版式的直接蓝本。以下全部为**实测抠出的原文样式**，
非推测。抠取时间 2026-09-17。

---

## 一、整体框架

```html
<section style="font-family: 微软雅黑, 'Microsoft YaHei';">   ← 最外层，字体设在这里
  <section style="margin-bottom:8px;">                        ← 顶部封面图
    <img …>
  </section>
  …正文…
</section>
```

> ⚠️ 注意：**`font-family` 是设在包裹用 `<section>` 上的**，不是设在文字节点（span/p）上。
> 这与「带字体设置会导致样式被丢弃」的踩坑记录并不矛盾——那条说的是设在**文字元素**上。

## 二、配色（全文只用这几个）

| 用途 | 色值 |
|---|---|
| 主蓝（标题、图标） | `#4F81BD` = `rgb(79,129,189)` |
| 亮蓝（渐变下划线起点） | `#1D81E6` = `rgb(29,129,230)` |
| 青（渐变小竖条） | `#76C5CB` = `rgb(118,197,203)` |
| 卡片底 | `#F4F8FC` = `rgb(244,248,252)` |
| 正文 | `#3F3F3F` = `rgb(63,63,63)` |
| 图注 | `#888888` = `rgb(136,136,136)` |
| 细线 | `#4E83BC` = `rgb(78,131,188)` |

## 三、正文 —— 放在浅蓝卡片里，不是通栏平铺 ⭐

```html
<section style="background-color:#F4F8FC; padding:15px; border-radius:10px;
                margin-top:4px; margin-bottom:4px;">
  <section style="line-height:1.75em; letter-spacing:1.5px; font-size:14px;
                  color:#333333; background-color:transparent; padding-top:5px;">
    <p style="line-height:2em; text-indent:2.1875em;">
      <span style="font-size:16px; color:#3F3F3F;">正文文字…</span>
    </p>
  </section>
</section>
```

- **正文包在 `#F4F8FC` 浅蓝圆角卡片里**（`padding:15px` / `border-radius:10px`）
- 段落：`line-height:2em`、`text-indent:2.1875em`（首行缩进）
- 文字：16px `#3F3F3F`

## 四、章节标题组件 ⭐

```html
<section style="margin:10px auto;">
  <section style="display:flex; justify-content:flex-start; align-items:center;">
    <section style="flex-shrink:0;">
      <section style="width:20px;">
        <!-- 星形 SVG，无需图片文件，直接内联 -->
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 35 33.01" style="display:block;">
          <path d="M35,12.31l-10.54,8L28,32.71l-10.71-7.2L6.39,33l3.92-12.48L0,12.79l13.13-.51L17.68,0l4.2,12.16Z"
                style="fill:#4f81bd; fill-rule:evenodd;"></path>
        </svg>
      </section>
    </section>
    <section style="font-size:16px; color:#4F81BD; text-align:left;
                    padding-right:10px; padding-left:10px;">
      <strong>大会主旨报告</strong>
    </section>
  </section>
  <!-- 向右渐隐的渐变下划线 -->
  <section style="width:100%; height:6px; overflow:hidden;
                  background-image:linear-gradient(to right, #1D81E6, transparent);"><br></section>
</section>
```

**要点**：星形是**内联 SVG**，不用图片文件——SVG 在微信里最稳（不受深浅色模式影响、
不会被压缩、不占图片额度）。

## 五、图片 + 图注（平铺）

```html
<p style="text-align:center; text-indent:0em; line-height:1.5em;">
  <img style="width:100%; height:auto; aspect-ratio:calc(1.5)/1; vertical-align:baseline;">
</p>
<p style="text-align:center; text-indent:0em; margin-bottom:10px; line-height:1.6em;">
  <span style="font-size:15px; color:#888888; letter-spacing:1px; line-height:1.67em;">
    清华大学郝吉明院士致辞
  </span>
</p>
```

- 图注：**15px / `#888888` / 居中 / 字距 1px**
- **图注不带【】**——直接写「清华大学郝吉明院士致辞」

## 六、横向可滑相册

见 `SKILL.md` 的「横向可滑相册」一节（同一来源）。要点回顾：
外层 `overflow:auto` + `scroll-snap-type:x mandatory`；行宽 `100%×N`；项宽 `100%÷N`。

## 七、装饰件

**① 分段小竖条**（两枚，配一条细线）：

```html
<section style="margin:10px auto; padding:0 7px;">
  <section style="display:flex; align-items:center;">
    <section style="flex-shrink:0; padding-right:7px;">
      <section style="display:flex;">
        <section style="width:10px; height:26px; border-radius:25px;
                        background-image:linear-gradient(rgb(79,129,189), #fff);"></section>
        <section style="width:10px; height:26px; border-radius:25px;
                        background-image:linear-gradient(rgb(118,197,203), #fff);"></section>
      </section>
    </section>
    <section style="width:100%; height:1px; overflow:hidden;
                    border-top:1px solid rgb(78,131,188);"></section>
  </section>
</section>
```

**② 底部收尾线**：`<section style="width:100%; height:3px; overflow:hidden; border-bottom:1px solid rgb(79,129,189);"></section>`

**③ 小图标**：35px / 50px 的小图（原文章节图标，可能是会议 logo）

---

## 八、与我们当前实现的差异

| 项 | 2024 模板 | 我们当前 | 建议 |
|---|---|---|---|
| 正文容器 | **浅蓝卡片 `#F4F8FC` 圆角** | 通栏平铺 | 可改 |
| 图注 | 15px `#888` **不带【】** | 13px `#6E7B89` **带【】** | 可对齐 |
| 章节标题 | **星形 SVG + 蓝字 + 渐变下划线** | 浅蓝胶囊 + 菱形 + 编号 | 可换 |
| 外层边框 | 无 | 有蓝框 + 硬投影 | 我们额外加的 |
| 主色 | `#4F81BD` | `#0F4C81` | 可对齐 |
| 字体 | 最外层设 `微软雅黑` | 不设 | 可加 |
| 相册 | ✅ | ✅ 已对齐 | — |
