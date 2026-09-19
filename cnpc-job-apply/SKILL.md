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

## 经验来源

2026-09 填 2027 届校招简历时踩坑总结。核心教训：
**"保存失败"先查是否在维护时段（0:00-6:00）**，别急着怀疑反自动化。
