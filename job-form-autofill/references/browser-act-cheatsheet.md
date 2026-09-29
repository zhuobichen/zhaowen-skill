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
browser-act --session apply input --selector "#nativePlaceName" --text "钦州"   # 不加 --mode fill
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

## 不要做的事

- ❌ `element.value = 'x'` / `dispatchEvent(new Event('change'))` 直接改 DOM（受控组件不认）
- ❌ 用 JS 构造 `File` + `DataTransfer` 注入文件（组件不认，保存时仍报"请上传"）
- ❌ 混用 CDP 与 browser-act
- ❌ 拿一次 `state` 的序号一直用（导航/重渲染后全失效）
- ❌ 点保存/提交 —— 填表 skill 一律停在提交前
