---
name: qqmail-auto-sort
description: 把 QQ 邮箱收件箱按固定类别自动归档（规则优先、TypeSafe Jev 只判规则没把握的那部分、纯代码搬邮件），每天 00:00 跑一次并生成 HTML 报告。当需要整理/归档邮箱、加分类规则、排查“邮件没被归档”、或要一份“今天分了多少封、每类都有什么”的报告时使用。
license: MIT
allowed-tools: Bash, Read, Write, Edit
metadata:
  version: "1.0.0"
---

# /qqmail-auto-sort

白天邮件留在收件箱（随时能看到），每天 **00:00** 统一归档一次，归档完生成 HTML 报告。
判类两段式：**规则先判（零成本，约 85%）→ 只有规则没把握的才送 Jev**。

## 什么时候用

- 用户说“帮我整理邮箱 / 把邮件分一下类 / 做个邮箱归档”
- 用户想加/改分类规则、加“重要邮件”判定
- 用户问“今天分了多少邮件 / 每类有什么”
- 归档出问题时排查（漏信、重复、核对失败）

## 前置

1. **IMAP 依赖**：脚本复用 `qqmail-mcp` 项目里的 `imapflow`，默认路径写死在本机；
   换机器时设环境变量 `QQMAIL_MCP_PROJ` 指向那个项目的根目录。
2. **凭据**：`scripts/qqmail.config.json`（QQ邮箱 16 位授权码，不是登录密码）
3. **模型**（可选）：`scripts/llm.config.json`（302.AI key + Jev endpoint）。没有就纯规则跑，不影响归档。

两个真实配置文件已在 `.gitignore` 里，仓库只提交 `*.example.json`。

## 用法

```bash
cd scripts

node sort.mjs --llm --triage --dry   # 预览：只判类，不动邮箱
node sort.mjs --llm --triage         # 执行归档
node sort.mjs --rescan               # 忽略 UID 水位线，全量重扫（改了规则、怀疑漏信时）
node sort.mjs --selftest             # 自检 COPY→核对→删副本链路（不碰原件）
node sort.mjs --limit=500            # 单次上限（默认 200）

node survey.mjs                      # 收件箱按发件人盘点 + 当前规则会给的类别
node report.mjs                      # 生成当天 HTML 报告
node report.mjs --open               # 生成并打开
node llm-eval.mjs 5                  # 评测：每类取 5 封，比 Jev / 规则 / 已归档结果

node daily.mjs --at=00:00            # 常驻定时器，每天 00:00 归档 + 出报告
node daily.mjs --once                # 只跑一次（给计划任务用）
```

## 分类

| 文件夹 | 判定要点 |
|---|---|
| `00-重要邮件` | 真人直接找你办事：`PEOPLE` 名单、或主题含“请你确认/审稿邀请/面试邀请/项目合作”；群发地址不参与 |
| `01-CI构建通知` | GitHub Actions 失败/完成 |
| `02-个人日报` | 自己发给自己的日报素材 |
| `03-学术科研` | 审稿投稿、期刊会议、合作者往来 |
| `04-求职校园` | 招聘投递、竞赛、学校事务 |
| `05-游戏娱乐` | Steam/Humble/Rockstar/EA 等商店 |
| `06-账号验证码` | 验证码、登录、密码重置 —— **不管哪个平台发的** |
| `07-订阅推广` | AI 工具订阅、行业简报、营销 |
| `08-平台通知` | npm/GitHub 非 CI/QQ邮箱官方/条款域名变更 |
| `09-财务账单` | 工资、发票、订单、收据、续费 |
| `10-工作项目` | 自建 Gitea、GitHub Issue/PR 讨论 |
| `11-垃圾广告` | 贷款/征信/申卡类群发 |
| 留在收件箱 | 都没命中 → 人说的话，故意不动 |

规则优先级（`scripts/categories.mjs` 的 `classifyDetail`）：
精确发件人 → 真人/直接请求 → GitHubCI三分 → 强安全信号 → 强身份域 → 主题关键词（安全>垃圾>钱>学术>招聘>游戏>通知）→ 弱域名。

**关键设计**：账号类关键词（验证码/密码/登录）优先于发件域。
原因：qoder、brave、anaconda、vercel 这些域既发验证码也发营销，按域一刀切会把验证码扫进推广。

## 安全约束（改代码时必须守住）

1. **不用 MOVE**，用 `COPY` 逐封复制；`messageCopy` 失败返回 `false` 而不抛异常，**必须检查返回值**。
2. 复制后用**另一条独立连接**按 `Message-ID` 核对；核对通过才 `EXPUNGE` 原件。
3. 核对不过 → 原件留收件箱 + 进 `pendingUids`，下轮补。**最坏是重复，绝不丢信**。
4. 复制失败率 > 30% 直接中止，一封不删。
5. 增量靠 **UID 水位线**（`state.json`），不要用“封数”。取候选前要**重新 SELECT**：
   `fetch("N:*")` 里的 `*` 是 SELECT 时刻的快照上限，新邮件会让范围算成空区间。
6. QQ 的 `UID EXPUNGE` **不接受逗号列表**，必须逐封删。
7. QQ 对**新建文件夹**的 COPY 有可见性延迟，核对要重试（4/8/12s）。

## 排查

```bash
tail -n 50 sort.log      # 每轮归档日志
tail -n 50 daily.log     # 定时器日志
cat last-run.json        # 最近一轮的结构化结果
cat state.json           # 水位线 + 各文件夹去重索引（可能有几百 KB）
```

- “扫 0 封新邮件”但其实有新信 → 检查是否漏了重新 SELECT，或水位线被手动改过（用 `--rescan`）
- “核对未通过”反复出现 → 看是否新文件夹延迟；`pendingUids` 会一直重试
- 报告没更新 → `node report.mjs` 手动跑，读 `report/data/<日期>.json`

## 定时（不需要管理员）

把 `daily-hidden.vbs` 的快捷方式放进 `shell:startup`，开机静默挂起。
或用计划任务：`schtasks /Create /F /TN "QQMail-AutoSort" /SC DAILY /ST 00:05 /TR "\"<scripts>\daily.cmd\""`
