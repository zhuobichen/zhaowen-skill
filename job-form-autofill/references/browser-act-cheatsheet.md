# browser-act 填表速查

`browser-act` v1.4.2（uv tool 装的）。本文只收**填表用得上**的部分与其坑，
不是完整文档（完整用法 `browser-act --help` / `browser-act <cmd> --help`）。

## 调用方式

```bash
browser-act <cmd> ...                                  # 在 PATH 上时
uvx --from browser-act-cli browser-act <cmd> ...        # 不在 PATH 时（注意 --from，写成
                                                       # `uvx browser-act-cli` 会报"不提供该可执行文件"）
~/.local/bin/browser-act.exe <cmd> ...                  # uv tool 的 shim 直接调
```

## 会话：复用本机 Chrome 的登录态

```bash
browser-act browser list                    # 有哪些浏览器实例（看 id= 与 type=）
browser-act --session apply browser open <实例ID> "<URL>"
browser-act --session apply close           # 收尾（不关会占着会话）
```

- **一次会话只用一个工具**：不要 CDP 与 browser-act 同时操作同一页面（见 SKILL.md 的坑 2）。
- 会话名固定（如 `apply`），命令都要带 `--session`。

### ⚠️ 默认是**无头**的 —— 要用户自己登录就必须 `--headed`

`browser open` 的帮助原文：`--headed  Show browser UI (default: headless)`。
**默认无头**，用户看不见任何窗口，也就没法扫码/输密码。两个实测到的坑：

1. **已经跑着的无头浏览器，`--headed` 会被忽略**，输出会说
   `Requested headed mode was ignored because the existing browser is running in headless mode`，
   并要求**先关掉该浏览器上所有活动会话**（`browser-act session list` / `session close <名>`）——
   而关会话可能打断用户别的工作，**要先问过用户**。
2. 更干净的做法：**建一个填表专用的有头浏览器**（不动用户现有的）： 

```bash
browser-act browser create --type chrome --name job-apply \
  --desc "求职网申填表专用" --objective "打开招聘网站并登录，按我的简历填写网申表单"
browser-act --session apply browser open --headed <新建的 id> "<URL>"
```

   新建的浏览器**没有用户的登录态**，每个站要登录一次；登录后 `session list` 里能看到 `browser_headed: true`。

## 读页面

```bash
browser-act --session apply state           # 带序号的可交互元素（首选）
browser-act --session apply get-html        # state 看不出标签关联时再用
browser-act --session apply screenshot      # 极少数需要看图时
```

`state` 的形态：`[12]<input id=basicName />`、`[39]<li class=autocompleter-item />` —— **序号可以拿来 click**。

### ⚠️ `state` 与 `get html` **看不到已填的值**

实测（2026-09-29，北港招聘的表单）：登录后表单里明明有值，`state` 却只显示 `placeholder=请输入姓名`，
`get html` 的 `outerHTML` 里也**没有 `value=`** —— 因为 Vue/Element-UI 的值是 **DOM property，不是 attribute**。

**读已填的值只有两条路**（都是 browser-act 自己的命令，不算"混用 CDP"）：

```bash
# 1) 单个字段
browser-act --session apply get value --selector '#basicName'

# 2) 整表一次读完：eval 里读 DOM property（**读**值不违反"不许用 JS setValue"那条红线）
browser-act --session apply eval '<js>'
```

Element-UI 的表格表单可以这样一把读干净（`TD.bold` 是标签、`TD.inp-box` 是控件，成对出现）：

```js
(() => { const rows = [];
  document.querySelectorAll('td.inp-box').forEach(td => {
    const label = (td.previousElementSibling ? td.previousElementSibling.innerText : '').replace(/[\s*]/g, '');
    const ctrl = td.querySelector('input, textarea, select');
    let v = ctrl ? String(ctrl.value == null ? '' : ctrl.value).trim() : '';
    if (!v && td.querySelector('img')) v = '[已上传图片]';
    rows.push(label + ' = ' + v);
  });
  return rows.join('\n'); })()
```

**注意区分**：`el-select` 的值就在那个只读 `input.value` 里（拿到的是显示文本，如 `壮族` ✓）；
`el-upload` 没有 input，只能看有没有 `img` 来判断"传过没传过"（文件本身在用户磁盘上）。

## 三种填法（按控件真实行为选，别按标签名）

```bash
# 文本框 / textarea —— 必须带 --mode fill（不带是逐字符打字，慢且易失败）
browser-act --session apply input --selector "#basicName" --text "张三" --mode fill

# 下拉 / 有固定选项的控件 —— 传选项**文本**（不是 value、不是下标）
browser-act --session apply select --selector "#mz" --option "壮族"

# 文件上传 —— 用 file input 的 selector（常常是隐藏的，用它的 class/id 就行）
browser-act --session apply upload --selector ".ajax_my_upload_file_ctl" --path "E:/path/photo.jpg"
```

**搜索式下拉**（籍贯、学校、公司这类"打字才出选项"的）：**不能**用 `--mode fill`（不触发搜索）——

```bash
browser-act --session apply input --selector "#nativePlaceName" --text "某市"   # 不加 --mode fill
browser-act --session apply state                                               # 拿下拉项序号
browser-act --session apply click 39                                            # 按序号点
browser-act --session apply get value --selector "#nativePlaceName"             # 验证
```

**按序号点击**（radio / checkbox / 列表项）：

```bash
browser-act --session apply state           # 找到目标元素的 [序号]
browser-act --session apply click 24
```

## 验证（填一个验一个）

```bash
browser-act --session apply get value --selector "#basicName"
```

受控组件"看着填上了、其实没进状态"是这类页面最常见的失败，**只有 `get value` 与页面自己的字数统计
能看出来**。别用截图判断填上了没有。

## 读回来的值不对时，按这个顺序查

1. 该控件是不是**搜索式下拉/级联下拉**（要用 plain input + click，或先填父项）
2. 是不是 `readonly`（日期组件）—— 通用命令填不进去，要用页面自己的组件 API
3. 是不是**受控组件**且你用错了工具（绝不能 JS/CDP setValue）
4. 页面是否被重新导航过（序号会失效，要重新 `state`）

## ⚠️ 弹层里的点击：`--selector` 会**静默失败**

北森的「期望从事行业 / 期望工作城市 / 籍贯」这类弹层，行元素（`.area-item-*`、`.list-item-container`）
用 `click --selector ...` 点下去**不报错、也没选中** —— 计数（页面上的「已选 N/M」）纹丝不动。
2026-09-29 实测，同一目标：

| 目标 | `--selector` 点击 | 按 `state` 序号点击 |
|---|---|---|
| 弹层里的选项行 | ✗ 静默失败 | ✓ |
| 普通下拉的 `li` 选项 | ✓（挂临时 id 后点） | ✓ |
| 输入框（含弹层里的搜索框） | ✓ | ✓ |

**能用的落点**：地区/行业面板点 `.icon-container`（那个单选圈/复选框的图标容器）——
点 `.area-item-name`（标签条）或 `.area-item-container`（整行）都没反应。

```bash
# 通用的"试落点"做法：逐个候选点一下、查一次计数
browser-act --session apply eval '<给 .icon-container 挂 id>'
browser-act --session apply click --selector '#wf-pick'
browser-act --session apply eval '<读「已选 N/M」>'
```

**弹层里的元素不一定出现在 `state` 里。** 同一套 `.area-item-*` 结构：籍贯面板的行**在** state 里
（可点序号），期望工作城市面板的行就**不在**。所以两条路都要备着——先试序号，不行再试落点。

**别用 `offsetParent !== null` 判可见**：滚动后它的 y 会变成负数。判断"在不在视口"要用
`0 <= r.y < window.innerHeight`；而且每换一个字段就**重新量一次坐标**（我照旧坐标点空过两次）。

## ⚠️ 判断"点了有没有反应"，别用轮询 —— 用 MutationObserver

点「暂存」后连查 6 次都是"无弹层"，看着像按钮没生效；其实**真的保存成功了**
（提示是「暂存成功，可在『投递记录』中查看」）。toast 消失得比轮询还快。

```bash
# 先装观察器（只读，不算点击），再点，再读
browser-act --session apply eval '(() => { window.__t=[]; new MutationObserver(ms=>{for(const m of ms)for(const n of m.addedNodes){if(n.nodeType===1){const s=(n.innerText||"").replace(/\s+/g," ").trim(); if(s&&s.length<120) window.__t.push(s);}}}).observe(document.body,{childList:true,subtree:true}); return "ok"; })()'
browser-act --session apply click <暂存序号>
browser-act --session apply eval 'window.__t.join(" || ")'
```

**顺带两条**：`暂存` 会做校验（必填没填时会拦下来），但**「工作经历」整段空着也能存**
（章节里的红 `*` 是给"加了条目"用的）；页面上只剩下"请选择"这种字样时，那多半只是空日期框的
placeholder，不是报错。

## ⚠️ 可重复的段落（项目经历、教育经历…）会**自己重排**

北森的表单把「项目经历」这类可加的段落**按结束时间倒序重排**。实测：填完 `2025-05~2026-08` 的那条
之后，它从最后一位跳到了**第一位**，而 SMAT（`2024-12~2026-01`）退到第二位。

后果很实在：**"最后一个块"这种定位法不成立**——我按它填，把内容写进了错的那一块
（ABaCAS 的名称落进了上海环科院那块，日期还是人家的 `2025-06~2025-08`，串了）。

规矩：

1. **按块号定位，不按位置猜**。先扫一遍所有「项目名称」字段的**下标**，第 i 个块就是第 i 个块的五个字段；
   然后给它们挂 `#wf-pb{i}-name/role/start/end/desc` 这样的 id 再操作。
2. **每填一块就复读一次**（`verify` 那种只读 dump），别攒到最后。
3. **填完必须靠"重新加载页面"来验证**，不能只看读回来是啥：
   `browser-act --session apply reload` → 再 dump 一遍。草稿是暂存到服务端的，
   重载后还在，才算真的填进去了。我一开始就是只看了 DOM 的 `value`，
   看着全对、其实块已经串了。

顺带：**「工作经历」整段留空也能暂存**（章节里的红 `*` 是给"已添加的条目"用的）。

## 不要做的事

- ❌ `element.value = 'x'` / `dispatchEvent(new Event('change'))` 直接改 DOM（受控组件不认）
- ❌ 用 JS 构造 `File` + `DataTransfer` 注入文件（组件不认，保存时仍报"请上传"）
- ❌ 混用 CDP 与 browser-act
- ❌ 拿一次 `state` 的序号一直用（导航/重渲染后全失效）
- ❌ 点保存/提交 —— 填表 skill 一律停在提交前
