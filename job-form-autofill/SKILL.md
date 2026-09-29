---
name: job-form-autofill
description: >
  按简历快速填写**任意网页的求职/网申表单**（企业官网申请系统、校招平台、猎聘/前程无忧/BOSS 的
  网页表单等），把"逐项手填"变成"校对一下"。当用户要求：根据简历填网申表单、批量填写招聘表、
  "帮我填这个申请页面"、"这些空填什么"、或者打开一个申请页不知道某些选项怎么选时使用。
  下拉/单选/勾选这类**闭合选项**交给 Jev 决策模型一次批量判定（weflow-cli decide），
  需要写字的字段（自我介绍、项目描述、期望薪资说明）由助手依据简历生成。
  **绝不替用户提交**，遇到登录/验证码/需上传证书时停下来交给用户。
  依赖 browser-act CLI（复用本机 Chrome 登录态）与 weflow-cli（Jev 决策）。
---

# 按简历填网申表单

> 目标：**把已经有的东西搬进去，把要判断的交给 Jev，把没有的列出来问用户。**
> 不做的事：编造没写在简历里的事实；替用户点提交。

## 何时用 / 不用

**用**：用户给了一个申请/网申页面的 URL（或已经开在浏览器里），手上有一份简历，要把它填进去。
**不用**：页面还没打开（先问 URL）；要新建/改写简历内容（那是另一件事）；要投递/发消息（本项目里
`cnpc-job-apply` 是某个具体平台的专用手册，通用填表用它；发送类操作按各平台 skill 的规矩走）。

## 依赖与预检（第一步就做，别跳）

```bash
python scripts/preflight.py          # 只读：报 browser-act / weflow-cli / profile 三样在不在
```

- **browser-act** 必须可用，而且要**真有浏览器连着**（`browser list` 里能看到 `chrome-direct` 才能复用
  本机登录态）。本机是 uv tool 装的：不在 PATH 时用 `uvx --from browser-act-cli browser-act`，
  或直接 `~/.local/bin/browser-act.exe`。`preflight.py` 会依次试这三种并告诉你用哪个。
  ⚠️ 写成 `uvx browser-act-cli` 会失败（包名与可执行文件名不同），必须带 `--from`。
- **weflow-cli**：Jev 走 `weflow-cli decide`。**允许用 `$WEFLOW_CLI` 覆盖**成任何能跑的命令——
  本机实测 npm 全局那份装坏了（shim 在、包文件缺，报 `Cannot find module .../weflow-cli/cli.cjs`），
  这时用 `WEFLOW_CLI="npx tsx bin/weflow-cli.ts"`（在 weflow-cli 仓库里）就行。
- **profile**（见下）：没有就先建，别硬填。

### 实测数据（2026-09-30，本机）

| 事实 | 实测值 |
|---|---|
| 3 个下拉字段的判定 | **一次调用、2.2 秒**（含 npx 启动），`$0.00003`，模型 `jev-1.13.0` |
| 20 个下拉框的估算 | 仍是**一次调用**，约 `$0.0002` —— 所以不用心疼，该问就问 |
| 无歧义字段的置信度 | **1.00** |
| 资料里没依据的字段 | **0.70~0.71**（同一请求两次跑有 ±0.01 波动） |
| 低置信度阈值 | 脚本用 **0.85**（用 0.7 时那个 0.70 正好卡边界不报警——阈值别设在会被波动跨过的位置） |
| `choice` 的 criteria | 是**「选项名 → 什么时候选它」的对象**，不是选项数组 |
| 无依据时的写法 | 给一个「视情况而定」选项，criteria 写"资料里没有任何依据" —— 实测它会被正确选中 |

## 简历 → profile（放技能包**外面**）

profile 是"简历的结构化事实 + 自由文本片段"，**每次填表都读它**，所以只建一次。

| 规则 | 说明 |
|------|------|
| 位置 | `$JOB_PROFILE` → `~/.job-apply/profile.md`（**默认放这里**） |
| **绝不放技能包目录里** | 技能包是公开仓库，个人数据进去就等于发布出去 |
| 格式 | Markdown + frontmatter；每个事实一行 `key: value`，便于 grep 与手改 |
| 来源可追 | frontmatter 里记 `source_resume:`（简历文件路径）与 `built_at:` |

```markdown
---
source_resume: <简历文件路径>
built_at: 2026-09-30
---
## 事实
姓名: 张三
手机: 138...
邮箱: ...
学历: 本科
学校: ...
专业: ...
毕业时间: 2026-06
籍贯: 广西壮族自治区-钦州市
政治面貌: 中共党员
身高: 175
...

## 自由文本片段
自我介绍: >
  （一段可直接粘贴的自我介绍，按目标岗位微调）
项目经历-<项目名>: >
  （STAR 写法：背景/我做了什么/结果，带数字）
```

**建 profile 时**：读简历原文（md/pdf/docx 都可以），把**能直接抄的**抄成事实行；
**需要成段写的**（自我介绍、项目描述）放在"自由文本片段"里。
**不要在 profile 里编简历里没有的事实**——缺失项就留空、让填表时报"需要你提供"。

## 工作流

### 1. 开会话，复用本机 Chrome 的登录态

```bash
browser-act browser list | grep -A2 "chrome-direct"     # 找带登录态的实例 id
browser-act --session apply browser open <ID> "<表单URL>"
```

会话名固定用一个（如 `apply`），**一次会话只用一个工具**（见"三个坑"）。

### 2. 读表单（`state`，不要先上 HTML/截图）

```bash
browser-act --session apply state
```

`state` 给的是带序号的可交互元素（`[12]<input ...>`、`[39]<li class=autocompleter-item />`），
够读出"有哪些字段、各自的标签、当选项列表"。`state` 看不出标签关联时再用 `get-html` 定位。

### 3. 分类：**按控件的真实行为，不按标签名**

| 真实行为 | 怎么看出来的 | 正确填法 |
|---|---|---|
| 文本框 | `<input type=text>` / `<textarea>` | `input --selector ... --text ... --mode fill` |
| 下拉/单选/勾选（**闭合选项**） | `<select>` / radio / checkbox 且有固定选项 | `select --option "<选项文本>"`；radio/checkbox 用 `click` |
| **搜索式下拉**（籍贯、公司、学校） | 是个 input，但旁边的选项是**输入后才出现**的 `<li>` | **不加 `--mode fill`** 逐字符打字 → `state` → `click <序号>` |
| **级联下拉**（省份→城市、省份→学校） | 父项选完子项才加载 | **先填父项，再重新 `state`**，然后填子项——顺序不能颠倒，也不能一次算完 |
| 只读日期 | `readonly` + 日期组件 | 通用命令填不进去，要用**页面自己的组件 API**（见下） |
| 文件上传 | `<input type=file>`（常被隐藏） | `upload --selector ... --path ...` |

### 4. 取值：三条来路，按优先级

**① 能追溯到 profile 的就直接抄**（姓名/手机/学历/籍贯/身高等）。填写时记住来源，报告里要能对上。

**② 闭合选项 → Jev 一次性批量判定。** 这是本 skill 相对手填的主要优势：几十个选择题**一次请求**约 1 秒。

```bash
python scripts/decide_batch.py --fields fields.json --dry-run   # 先看形状，不调模型
python scripts/decide_batch.py --fields fields.json --yes       # 确认后真调
```

`fields.json` 的形状（每个字段一条，`options` 就是页面上给的选项原文）：

```json
{
  "job_context": "岗位：数据分析（南宁）；公司：某环保科技",
  "fields": [
    { "key": "hy",   "label": "婚姻状况", "options": ["未婚", "已婚", "离异"] },
    { "key": "zzmm", "label": "政治面貌", "options": ["中共党员", "共青团员", "群众"] }
  ]
}
```

Jev 的回答是**带概率的选项**：把它当"建议 + 可信度"用，低概率或与 profile 冲突的**要在报告里标出来**
让用户复核，而不是默默照填。**级联下拉**：父项选完后子项选项才会加载，所以可能要把步骤 3-4 走两遍。

**③ 需要写字的 → 助手依据 profile 生成**（自我介绍、项目描述、投递理由）。
尊重字段长度限制（`maxlength` 或页面明文写着"最多 N 字"），超了要压缩而不是硬塞。
期望薪资/到岗时间这类**判断题**也可以走 Jev（把它变成带选项的问题，而不是让模型自由发挥）。

**④ 没有依据的一律留空**，并进报告。绝不编造（身份证号、婚育、家庭住址这类尤其不要凭空写）。

### 5. 填，然后**逐个验证**

```bash
browser-act --session apply input --selector "#basicName" --text "..." --mode fill
browser-act --session apply select --selector "#mz" --option "壮族"
browser-act --session apply get value --selector "#basicName"     # 填完就验，别猜
```

**填一个验一个**。受控组件"看起来填上了、其实没进组件状态"是这类页面最常见的失败，
只有 `get value` 与页面的字数统计能看出来。

### 6. 停在提交前 —— **这是硬规则**

填完最后一栏就停下，把页面交给用户：

- **不点保存/提交/发送**，哪怕后面还有"承诺告知书"这种一步到底的确认
- 报告三样东西：**① 填了什么（值 + 来源）② 留空了什么、为什么 ③ 需要你提供什么**
- 如果用户自己点了保存而页面弹错，**读弹窗原文**（"请选择健康状况！"），只补那一项，别整表重填

**"需要你提供"清单**是常规产出，不是失败：成绩单、证书扫描件、准考证号、推荐表这类
**只有人手上才有**的东西，提前列出来比填到一半卡住强。

## 🚫 三个必须避免的坑（都是实测踩出来的）

1. **不要用 JS/CDP 直接 setValue。** 这类页面的下拉是**受控组件**：
   `el.value = 'x'` 或 `dispatchEvent(new Event('change'))` 只改 DOM、不更新组件内部状态——
   页面上看着对，字数统计显示 0，保存时报"请选择 XX"。**必须用 browser-act 的 `input`/`select`**
   （它模拟真实交互）。同理，用 JS 构造 `File` + `DataTransfer` 注入文件**无效**，要用 `upload`。
2. **不要混用 CDP 与 browser-act。** 两个工具同时操作同一页面会互相干扰：browser-act 刚填的值，
   CDP 查出来是空的（误判"没填进去"），甚至把页面重置。**一次会话只用一个工具，验证也用同一个。**
3. **不要一次算完所有字段再动手。** 级联下拉（省份→城市/学校）与搜索结果都是**填一步才出现下一步**的，
   预先算好的"完整填写计划"一定会过期。**填 → 重读 `state` → 再决定**。

## 报告格式（给用户看的）

```
已填 12 项
  · 姓名 = 张三（来源：profile）
  · 婚姻状况 = 未婚（Jev 0.93）
  · 政治面貌 = 中共党员（Jev 0.99 / profile 一致）
留空 3 项
  · 紧急联系人电话 —— profile 里没有
  · 身高 —— 页面要求但简历未写
需要你提供
  · 成绩单 PDF（必填）、外语准考证号（成绩单上才有）
复核一下再点提交
  · 期望薪资 = 8-10K（Jev 0.61，置信度不高；与上次填的 10-12K 不一致）
```

## 北森（phoenix）表单：直接用 `scripts/formkit.py`

北森这套表单（`zhiye.com` 系的网申）有一堆"不这么做就静默失败"的地方。`formkit.py` 把
在真表单上试出来的原语收成一个 CLI，**别再从零手写 JS**。

```bash
python scripts/formkit.py dump                 # 全表字段：标题/控件/当前值（每项挂 #wf-f<N>）
python scripts/formkit.py options              # 当前打开的弹层里有哪些选项
python scripts/formkit.py pick 钦州市           # 在弹层里选中一行
python scripts/formkit.py date 2024-09         # 在打开的日期面板里选年月
python scripts/formkit.py blocks               # 列可重复块（项目经历/工作经历）
python scripts/formkit.py block-fill --key AQMAT --name … --role … --start 2025-05 --end 2025-10 --desc …
python scripts/formkit.py block-text --key AQMAT --name … --role … --desc …   # 只改文字，不碰日期
python scripts/formkit.py block-now weflow-cli # 勾该块的「至今」
python scripts/formkit.py click-text 暂存       # 按文字点（唯一命中才点）
python scripts/formkit.py collect              # 滚一遍收集虚拟化列表的全部选项
```

它替你挡住的四件事（每一条都是实测翻车换来的，细节见速查表）：

1. **弹层里的行不能用 `--selector` 点** —— 点了不报错也不选中。`pick` 会自动试落点，
   并且**用页面上的"已选 N/M"计数判断是否真的生效**，而不是看返回值。
2. **可重复块会按结束时间自己重排** —— 所以一律**按名称定位块**（`--key`），
   命中 0 个或 ≥2 个就停手；`block-*` 全按这个规矩。
3. **日期面板每次跳年都重渲染** —— 序号全失效，`date` 每一跳都重新读 `state`。
4. **「至今」复选框不在结束时间的 form-item 里** —— 按子树找会落空，`block-now` 按"它属于哪个块"定位。

⚠️ **改完必须用 `reload` 验证落盘**（`formkit` 不管这一步）：只看读回来的 `value`
会被受控组件骗 —— 我在这上面翻过一次车（内容写进了错的那一块，读回来却全对）。
重载后还在，才算真的填进去了。

## 参考

- `references/browser-act-cheatsheet.md` —— 填表常用命令、会话管理、状态读取的速查，
  以及上面那四条坑的**实测记录**（含失败现象与错误结论长什么样）
- 某个平台的专用手册（字段 id 清单、维护窗口、字数限制）：见同仓库的 `cnpc-job-apply`
