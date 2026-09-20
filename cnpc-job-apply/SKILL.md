---
name: cnpc-job-apply
description: >
  在"中国石油高校毕业生招聘"平台(zhaopin.cnpc.com.cn)填写校招网申简历。
  当用户要求：填中石油网申/校园招聘简历、操作 zhaopin.cnpc.com.cn、上传网申照片、
  检查中石油投递状态、"帮我填中石油简历" 时使用。
  涵盖：browser-act 填表(input --mode fill / select / upload)、字段 id 清单、
  维护时间窗口(0:00-6:00 不可用)、systemCheck.html 真实含义、特长爱好字数限制、
  籍贯 autocomplete 操作、保存流程(承诺告知书)、CDP 与 browser-act 混用陷阱等经验。
---

# 中石油网申填表 Skill

> 平台：中国石油高校毕业生招聘 `https://zhaopin.cnpc.com.cn`
> 简历编辑页：`/web/createResume.html`

## ⚠️ 最重要的坑：维护时间 0:00-6:00

平台公告原文：
> **每日北京时间 0:00 至 6:00 为系统维护时间，不可登录**

维护期间的表现（**极易误判为"反自动化检测"**）：

| 现象 | 真相 |
|------|------|
| 保存后跳转 `systemCheck.html` | 该页标题是「**系统维护**」，不是拦截页 |
| `systemCheck.html` DOM 为空 | 维护中，页面内容未渲染 |
| 首页 `ERR_TIMED_OUT` | 维护中，服务未响应 |
| 保存失败、提示莫名 | 维护导致，**不是**表单校验问题 |

**排查方法（第一步就做这个）**：
1. 运行 `date` 看当前时间 → 若在 **0:00-6:00** 之间，直接停止，告知用户等维护结束
2. 访问 `systemCheck.html` 看 `<title>` → 若为「系统维护」，**不是反自动化问题**

**注意**：该站**没有**反自动化检测（已验证）：
- `navigator.webdriver` = `false`
- 无 `cdc_*` ChromeDriver 特征变量
- UA 无 `Headless`
→ **可以用自动化正常操作**

---

## 🔧 正确操作方式：只用 browser-act

```bash
# 先查出 chrome-direct 类型的浏览器 ID（复用本地 Chrome 登录态）
browser-act browser list | grep -A2 "chrome-direct"

# 打开会话（把 <ID> 换成上一步查到的 id）
browser-act --session cnpc browser open <ID> \
  "https://zhaopin.cnpc.com.cn/web/createResume.html"
```

> 若本地无 chrome-direct 浏览器，用 `browser list` 挑一个可用的；
> 或参考 browser-act 文档创建带登录态的会话。

### 三种填写命令（关键：`--mode fill`）

```bash
# 1. 文本框 —— 必须加 --mode fill（不带则逐字符打字，慢且易失败）
browser-act --session cnpc input --selector "#basicName" --text "施显晟" --mode fill

# 2. 下拉框 —— 直接用 select，传选项**文本**
browser-act --session cnpc select --selector "#mz" --option "壮族"

# 3. 文件上传 —— 用隐藏 input 的 selector
browser-act --session cnpc upload --selector ".ajax_my_upload_file_ctl" \
  --path "E:/path/to/photo.jpg"
```

### 籍贯（autocomplete）唯一正确姿势

籍贯 `#nativePlaceName` 是搜索式下拉，**不能**用 `--mode fill`（不触发搜索）：

```bash
# 1. 逐字符打字（不加 --mode fill）触发搜索
browser-act --session cnpc input --selector "#nativePlaceName" --text "钦州"

# 2. state 拿到下拉项 index
browser-act --session cnpc state
#   [39]<li class=autocompleter-item /> 广西壮族自治区-钦州市-钦北区

# 3. 按 index 点击
browser-act --session cnpc click 39

# 4. 用 get value 验证
browser-act --session cnpc get value --selector "#nativePlaceName"
```

### 验证字段（每步都验，别猜）

```bash
browser-act --session cnpc get value --selector "#basicName"
```

---

## 🚫 三个必须避免的坑

### 1. 不要用 CDP/JS 直接 setValue

页面的下拉是**受控组件**，`element.value = 'x'` 或 `dispatchEvent(new Event('change'))`
**只改 DOM、不更新组件内部状态** → 表现为：
- 页面上值看着对
- 但字数统计显示"已输入 **0** 字"
- 保存时报"请选择 XX"

**必须用 browser-act 的 `input`/`select`**（模拟真实交互）。

### 2. 不要混用 CDP 和 browser-act

两个工具**同时**操作同一页面会互相干扰：
- browser-act 刚填入的值，CDP 检查时显示为空（误判为"没填进去"）
- 页面可能被意外重置

**规则：一次会话只用一种工具**。用 browser-act 就用 browser-act 验证。

### 3. 保存前逐项核对必填（含容易漏的）

保存报错时，**先看弹窗的具体提示**（如"请选择健康状况！"），别急着重填全部。
**最容易漏的**：`#healthCondition`（健康状况）—— 页面重置后常丢。

---

## 📋 基本信息字段 id 清单

| 字段 | selector | 类型 | 备注 |
|------|----------|------|------|
| 姓名 | `#basicName` | input | |
| 姓名拼音缩写 | `#nameSpellAbb` | input | 例：张三→ZHS |
| 出生日期 | `#basicBirthday` | input | 系统自动带出 |
| 照片 | `.ajax_my_upload_file_ctl` | file | 见下方上传说明 |
| 户口省份 | `#domicilePlace` | select | 选后城市才联动加载 |
| 户口城市 | `#domicilePlaceC` | select | **需先选省份** |
| 民族 | `#mz` | select | |
| 婚姻状况 | `#hy` | select | |
| 户口性质 | `#hk` | select | |
| 生源地 | `#sy` | select | |
| 籍贯 | `#nativePlaceName` | autocomplete | 见上文操作 |
| 政治面貌 | `#zzmm` | select | |
| 家庭所在地 | `#homePlace` | select | |
| 健康状况 | `#healthCondition` | select | **最易漏，别忘** |
| 身高 | `#stature` | input | 厘米 |
| 体重 | `#weight` | input | 公斤 |
| 特长 | `#speciality` | textarea | **限 90 字** |
| 爱好 | `#hobby` | textarea | **限 40 字** |

**字数限制实测**：特长 111 字会被拦（提示"最多 90 个字"），需压缩到 90 内。

---

## 🖼️ 照片上传

要求：**jpg / jpeg**，**≤200KB**。

```bash
browser-act --session cnpc upload --selector ".ajax_my_upload_file_ctl" \
  --path "E:/path/to/photo.jpg"
```

成功后页面弹「**文件上传成功**」，照片区显示预览 + "删除照片"按钮。

**坑**：
- 页面**重置**（刷新/重新导航）后照片会丢，需重传
- 照片是**必填**，没有照片保存会被拦（提示"请上传照片"）
- 用 JS 构造 `File` + `DataTransfer` 注入 **无效**（组件不认，保存仍报错）

---

## 💾 保存流程

```
填完所有必填
  ↓
点「保存基本信息」(a.return_btn)
  ↓
弹出「承诺告知书」→ 点「已知晓」(button.closePromiss)
  ↓
保存成功（页面刷新后：字段显示为只读 + 出现"修改"按钮）
  ↓
才能点「+添加教育背景」等后续板块
```

**重要规则**（页面原文）：
- 必须先保存基本信息，才能填其他板块
- 有其他板块未填时，保存可能被拦
- 有正在应聘的记录时**不能改简历**（要先撤销应聘）

---

## 📑 后续板块（都是「+ 添加XXX」形式）

| 板块 | 必填 | 按钮 |
|------|:---:|------|
| 教育背景 | ✅ | + 添加教育背景 |
| 外语水平 | | + 添加外语水平 |
| 通讯信息 | ✅ | + 添加通讯信息 |
| 实习/工作/入伍经历 | | + 添加实习/工作/入伍经历 |
| 获奖信息 | | + 添加获奖信息 |
| 家庭成员 | ✅ | + 添加家庭成员 |
| 其他资格 | | + 添加其它资格 |
| 附件 | | + 添加附件 |

全部填完后点页面底部「**完整性校验**」。

### ⚠️ 各板块的「隐藏必填项」（2026-09-20 实测）

**每一个都需要上传文件** —— 这是最容易低估的地方：

| 板块 | 除了文字，还必填 |
|------|-----------------|
| 教育背景 | `#gradePoint` 学分绩点（**纯数字，非数字报"请输入数字"**）+ `#transcriptAttachmentFile` 成绩单 |
| 外语水平 | 外语水平证明文件 + `准考证号` + `报告单编号`（成绩单上才有） |
| 获奖信息 | 每条的获奖证明文件（**选完奖项名称后上传按钮才可用**） |
| 附件 | 都是"选填"（个人简历/就业推荐表/其他资料） |

→ **结论**：能真正"纯自动化"填完的只有 **基本信息 / 通讯信息 / 家庭成员**。其余板块需要用户提供成绩单、证书扫描件、准考证号等，提前跟用户要。

### 🔁 「+ 添加XX」是替换，不是追加

点「+ 添加家庭成员」（或任何「+ 添加XX」）会**清空当前未保存的表单**并换成空白表单，**不会**保留上一条。

- ❌ 想一次填完父母两条 → 第二条一点，第一条全丢
- ✅ 正确顺序：**填一条 → 保存 → 再点「+ 添加」填下一条**

> 教育背景同理，需 2 条（第一学历 + 最高学历）时必须逐条保存。

### 📅 日期字段（readonly）

`#educationStartDate`、`#educationEndDate`、`#birthday` 等都是 `readonly` + `form_date`，**不能 fill**。

用 datetimepicker API（**不是** setValue）：

```js
window.jQuery(el).data("datetimepicker").setDate(new Date(2024, 8, 1))  // 月份 0-based
```

### 🏫 教育背景的院校是「先选省份再选校」

- `#schoolCode` 是 select，**选完 `#province` 后才加载**对应学校列表
- 华南理工大学 = `440100002`；列表末尾有 `999999999=其他院校`（手工输入）
- 选系统内院校后 `#schoolChinaName` 会**隐藏**，不用填（隐藏字段不参与校验）
- 学位值示例：`333`=资源与环境硕士，`343`=工程硕士
- 学历：`21`=硕士研究生，`31`=大学本科；学历形式：`1`=普通全日制
- 绩点制：`1`=四分制

### 👨👩👦 家庭成员字段 id 重复

同一页面多条家庭成员记录**共用同一组 id**（`#relation`、`#name`、`#birthday`…），`getElementById` 只能拿到第一条。

要定位"当前展开的那条"，用：

```js
[...document.querySelectorAll("form")].find(f => f.offsetParent && f.querySelector("#birthday"))
```

- 关系值：`51`=父，`52`=母
- `#department`（工作单位）是 `list="depList"` 的 datalist 输入框，直接填文本即可
- 页面上的树/ref 顺序与 checkbox 实际 id **可能错位一格** —— 勾选后务必用 JS 回读 `checked` 验证

### 📎 上传文件的权限坑

`bsk upload` 可能报 `Not allowed` —— 浏览器扩展缺 **「允许访问文件网址」** 权限。
此时**不要反复重试**，直接交给用户手动选文件（或让用户在扩展设置里开权限）。

---

## 🔍 常用只读查询

```bash
# 查看已填值
browser-act --session cnpc get value --selector "#basicName"

# 查看页面可交互元素（含 index）
browser-act --session cnpc state

# 截图
browser-act --session cnpc screenshot "E:/tmp/page.png"

# 关闭会话（用完记得关）
browser-act session close cnpc
```

**投递状态查询**：页面顶部「职位申请记录」，可看应聘企业/岗位/状态。
规则：每人最多同时应聘 **2 家**单位，每家限 **1 个**岗位。

---

## ✏️ 修改已保存的记录（只能删了重建）

列表页每条记录**只有「X」删除按钮，没有编辑入口**。要改一个字段，必须：

1. 用 X 删掉旧记录（弹「该数据已删除」→ 点「关闭」）
2. 点「+ 添加XX」重新填一条

**删除前务必先把整条记录抄下来**（getBoundingClientRect 无法恢复数据）。删除是服务端立即生效的，不可撤销。

---

## 🖱️ BrowserSkill（bsk）实战陷阱 —— 2026-09-20 实测

用 `bsk` 替代 browser-act 时的几个坑，都会表现成**"点错元素"**：

### 1. `@eN` ref 会错位一格

observe 出来的 ref 顺序**不等于** DOM 顺序。实测勾选「最高学历」的 ref 实际点到了「最高学位」。

**对策**：涉及勾选/删除等有副作用的操作，先 `evaluate` 回读状态验证；或改用 CSS selector。

### 2. 用 CSS selector 代替 ref（更稳）

`bsk click` 接受 CSS selector。对没有稳定 id 的元素：

```js
// 先定位 + 打 id 标记，并滚到视口中央
(()=>{const b=[...document.querySelectorAll("a,button,div,span")]
  .filter(e=>e.offsetParent && e.textContent.replace(/[\s+]+/g,"")==="添加家庭成员" && e.children.length<=2);
  if(!b.length) return "nf";
  const t=b[b.length-1]; t.id="zzAddMom"; t.scrollIntoView({block:"center"}); return "ok";})()
```

```bash
bsk click "#zzAddMom" --session <id>
```

### 3. 元素在视口外时坐标点击会乱跳

未滚动就直接 `bsk click "@eN"`，元素在页面很深的位置时，点击可能落到**别的元素**上（实测点「删除母亲」跳到了「帮助中心」页）。

**对策**：先 `scrollIntoView({block:"center"})`，再点。

### 4. `element.click()` 对某些按钮无效，对另一些有效

- 「+ 添加XX」按钮：JS `click()` **不生效**，必须真实点击
- 「X」删除按钮、「关闭」弹窗按钮：JS `click()` **有效**（实测成功）

### 5. navigate 会另开 tab，导致后续操作打空

`bsk navigate` 后如果 Agent Window 里有 2 个 tab，`observe`/`click` 默认作用于 **active** tab，而你导航的是新 tab → 报 `element not visible` / `tabs outside an Agent Window must first be borrowed`。

**对策**：

```bash
bsk tab list --session <id>          # 看有几个 agent tab
bsk tab close <多余tab-id> --session <id>
bsk tab select <保留的tab-id> --session <id>
```

### 6. session 会因中断/超时而消失

命令被用户中断（Ctrl-C）后 session 常直接失效（`session not registered`），需重新 `bsk session start`。**新 session 是新窗口，登录态可能丢失**，要重新登录。

### 7. 点击前若报 `Renderer did not become ready for input`

先跑一次 `bsk observe`，再执行点击。

---

## 经验来源

2026-09 填 2027 届校招简历时踩坑总结。核心教训：
**"保存失败"先查是否在维护时段（0:00-6:00）**，别急着怀疑反自动化。
