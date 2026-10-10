# 模板反推记录：redcard2026

**来源**：C:\Users\Administrator\AppData\Local\Temp\mp\article_body.html
**原文标题**：AI Agent 架构终于讲清楚了：Planner、Reasoning、Tool、MCP、Memory、Reflection 全链路拆解
**产出**：`theme.json` · `sample.html` · `preview.png`

> 数值来自对原文 HTML 的**实测抠取**，非推测。

## 一、配色

| 色值 | 出现次数 |
|---|---|
| `rgb(220, 38, 38)` | 114 |
| `rgb(55, 65, 81)` | 58 |
| `rgb(254, 202, 202)` | 56 |
| `rgb(254, 226, 226)` | 39 |
| `rgb(153, 27, 27)` | 36 |
| `rgb(252, 165, 165)` | 26 |
| `rgb(28, 25, 23)` | 21 |
| `rgb(254, 242, 242)` | 20 |
| `rgb(75, 85, 99)` | 12 |
| `rgb(156, 163, 175)` | 5 |
| `rgb(226, 232, 240)` | 2 |
| `rgba(220, 38, 38, 0.15)` | 1 |
| `rgb(214, 211, 209)` | 1 |
| `rgb(250, 250, 250)` | 1 |

（微信外壳自带的颜色已剔除：微信绿 `#07C160`、链接蓝 `#576B95` 等）

## 二、排版

- **字体**：`-apple-system, BlinkMacSystemFont, &quot;PingFang SC&quot;, `×31 · `&quot;SF Mono&quot;, Consolas, Monaco, monospace`×2 · `Consolas, Monaco, monospace`×1
- **字号**：`15px`×84 · `14px`×34 · `12px`×32 · `18px`×28 · `10px`×14 · `16px`×7
- **行高**：`1.8`×84 · `1.3`×14 · `1.7`×13 · `0`×3 · `1`×2 · `1.6`×2
- **字距**：`0.5px`×45 · `3px`×15 · `1px`×6
- **圆角**：`50%`×36 · `4px`×16 · `999px`×16 · `6px`×14 · `10px`×11 · `0px 10px 10px 0px`×6
- **阴影**：`rgba(220, 38, 38, 0.15) 0px 4px 24px -4px`×1 · `rgba(15, 23, 42, 0.4) 0px 4px 16px -8px`×1
- **内边距**：`0px 10px`×29 · `3px 10px`×16 · `4px 14px`×14 · `2px 10px`×11 · `18px 22px`×6 · `8px 12px`×6
- **外边距**：`0px`×82 · `0px 0px 2px`×14 · `0px 0px 6px`×12 · `0px 0px 8px`×8 · `0px 6px 8px 0px`×8 · `0px 0px 24px`×3

## 三、组件形态

| 组件 | 出现次数 | 实测样式（首个样本） |
|---|---|---|
| **行内高亮（span 上的下划线）** | 50 | `border-bottom:2px solid rgb(254, 202, 202);font-weight:600;visibility:visible` |
| **圆形元素（序号/圆点）** | 36 | `display:inline-block;width:6px;height:6px;background:rgb(220, 38, 38);border-radius:50%;margin-right:5px;vertical-align:middle` |
| **强调色文字（strong/span 带彩色）** | 27 | `` |
| **胶囊标签（大圆角）** | 16 | `display:inline-block;font-size:14px;font-weight:700;color:rgb(153, 27, 27);background:rgb(254, 226, 226);padding:3px 10px;border-radius:999px` |
| **章节标题条（挂在 section 上的底部实线）** | 14 | `display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;padding-bottom:14px;border-bottom:3px solid rgb(220, 38, 38)` |
| **标题元素 h1~h4** | 14 | `` |
| **分隔线（渐变）** | 13 | `height:1px;background:linear-gradient(to right, transparent, rgb(252, 165, 165), rgb(220, 38, 38), rgb(252, 165, 165), transparent);margin:0px` |
| **描边盒（1-3px 实线边框）** | 11 | `flex:1 1 0%;background:rgb(254, 242, 242);border-radius:10px;padding:16px 12px;margin-right:8px;text-align:center;border:1px solid rgb(254, 226, 226)` |
| **粗体引词 strong** | 10 | `` |
| **引用块（左侧竖线）** | 8 | `background:rgb(254, 242, 242);border-radius:0px 10px 10px 0px;border-left:4px solid rgb(220, 38, 38);padding:18px 22px;margin-bottom:24px;visibility:visible` |
| **底色式标题条/标签块（实色底 + 内边距 + 大字号或居中）** | 5 | `flex:1 1 0%;background:rgb(254, 242, 242);border-radius:10px;padding:16px 12px;margin-right:8px;text-align:center;border:1px solid rgb(254, 226, 226)` |
| **图片** | 3 | `` |
| **卡片外层（圆角 + 阴影）** | 2 | `color:rgb(55, 65, 81);font-family:-apple-system, BlinkMacSystemFont, &quot;PingFang SC&quot;, &quot;Hiragino Sans GB&quot;, &quot;Microsoft YaHei&quot;, sans-se` |
| **表格** | 1 | `` |
| **其他 <mp*>（多为无意义标记，如 mp-style-type）** | 1 | `` |

## 四、结构事实（未预设组件签名）

> 上一节是「按见过的签名归类」；这一节是**原始事实**。
> 遇到没见过的写法时，签名会整类漏掉，但事实不会 —— 优先看这一节。

**标签普查**：`span`×506 · `section`×161 · `p`×149 · `br`×31 · `h3`×14 · `strong`×10 · `td`×4 · `img`×3 · `tr`×3 · `th`×2 · `div`×1 · `table`×1 · `thead`×1 · `tbody`×1

- **边框**：`1px solid rgb(254, 202, 202)`×6 · `1px solid rgb(254, 226, 226)`×5
- **单边线**：`2px solid rgb(254, 202, 202)`×50 · `3px solid rgb(220, 38, 38)`×14 · `1px solid rgb(254, 226, 226)`×10 · `4px solid rgb(220, 38, 38)`×7 · `4px solid rgb(214, 211, 209)`×1
- **背景**：`rgb(220, 38, 38)`×57 · `rgb(254, 226, 226)`×24 · `rgb(254, 242, 242)`×20 · `linear-gradient(to right, transpar`×14 · `rgb(255, 255, 255)`×1 · `rgb(250, 250, 250)`×1
- **display**：`inline-block`×63 · `flex`×52 · `inline-flex`×17 · `none`×1
- **对齐**：`justify`×69 · `start`×31 · `center`×17 · `left`×2
- **小尺寸(<=24px)**：`22px`×34 · `6px`×32 · `0px`×31 · `1px`×13 · `10px`×6 · `2px`×2

## ⚠️ 人工复核清单（**必做**）

`theme.json` 只描述**数值**。数值对 ≠ 模板对。2026-09-30 实测过一次：
颜色/圆角/字号全部解析正确，但**结构错三处**，而且这三处靠读 CSS 推不出来 ——

| 我推出来的 | 实际 | 怎么发现的 |
|---|---|---|
| 章节标题条 = 左标签 + 右胶囊（两端布局） | **红方块 + 英文小字 + 中文标题**（三件套） | 渲染后并排看 |
| 引用块 = 圆角浅底 | 还多一根 **`border-left` 红竖线** | 渲染后并排看 |
| 胶囊 = 纯文字 | 内嵌一个 **6px 小红圆点** | 渲染后并排看 |

**所以请打开 `preview.png`，并排对照原文，逐条确认：**

- [ ] 卡片：圆角多大？阴影是「淡色大扩散」还是「深色小硬边」？有没有边框？
- [ ] 章节标题：是左右两端、还是「色块 + 多行文字」？色块里是数字还是文字？
- [ ] 引用块：左侧有竖线吗？圆角是四角还是只圆右侧（`0 Xpx Xpx 0`）？
- [ ] 标签/胶囊：里面有圆点或图标吗？底色是浅色还是实色？
- [ ] 序号：是圆点、方块、还是数字？圆点里有内容吗？
- [ ] 正文：字号、行高、是否两端对齐（`text-align: justify`）？
- [ ] 有没有**只在少数位置出现**的组件（容易被"最常见值"统计盖掉）？

**优先看出现次数少的组件** —— 高频值会掩盖特例，而特例往往才是模板的辨识度所在。
