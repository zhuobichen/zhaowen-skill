---
name: n8n-web-ops
description: >
  通过网页(browser-act)操纵 n8n 工作流平台(<内网IP>:5678)。
  当用户要求：查看 n8n 工作流/执行记录、获取 callback_token/finished_callback_url、分析 ABaCAS 平台底层 n8n 工作流
  （如"全链条费效评估 v2"）、登录 n8n、导出执行数据 时使用。
  涵盖：stealth 无头登录(账号密码)、工作流/执行记录只读查看、画布节点识别、执行详情、callback_token 获取方式、
  安全约束(仅只读、禁止触发工作流/修改配置)等经验。
---

# n8n 网页操纵 Skill

> n8n 服务：`http://<内网IP>:5678`（ABaCAS 平台的工作流引擎）
> ⚠️ **安全约束**：n8n 页面**只读**——禁止触发工作流、禁止修改任何配置。

## 前置环境要求

- **browser-act CLI**：`uv tool install browser-act-cli --python 3.12`（浏览器自动化工具）
- **browser-act 浏览器**：stealth 类型 `acs-stealth2`（ID `103206233488452404`）——创建命令：
  `browser-act browser create --type stealth --name acs-stealth2 --desc "ABaCAS微信扫码登录持久化"`
- **Python 3 + requests**：`pip install requests`
- **网络**：内网 `<内网IP>`（n8n，需先连内网/VPN）+ 公网 `cloud-test.abacas-dss.com`
- **适用环境声明**：凭据/浏览器/内网 IP/域名均为作者测试环境，迁移需对应调整

## 1. 平台信息

| 项 | 值 |
|----|-----|
| n8n 地址 | `http://<内网IP>:5678` |
| 登录页 | `/signin`（电子邮件 + 密码） |
| 账号 | `<n8n账号>` / 密码 `<n8n密码>` |
| 关键工作流 | 全链条费效评估 v2（ID `U1s6WBLzg1a1apxE`，169 节点） |
| 工作流 Webhook 触发器 | `POST /webhook/<webhook触发器ID>`（headerAuth） |
| 触发 body | `job_run_id`、`finished_callback_url`(含callback_token)、`log_callback_url` 等 |
| API | `GET /api/v1/executions`（需 `X-N8N-API-KEY` header） |

## 2. 登录（browser-act stealth）

- 用 stealth 浏览器（`103206233488452404`）打开 `http://<内网IP>:5678`
- **n8n session 不持久化**——stealth profile 每次重开都需重新登录（不像 ABaCAS 平台）
- 登录步骤：
  1. `state` 找到 `[3]<input type=email id=emailOrLdapLoginId>` 填入账号
  2. `state` 找到 `[6]<input type=password>` 填入密码
  3. 点击"登录"按钮（index 7）
- 登录成功标志：URL 跳到 `/home/workflows`，无"电子邮件"登录表单
- ⚠️ 元素索引 `[3]/[6]/[7]` 是 browser-act `state` 动态生成的，DOM 变化会失效——失效时重新运行 `browser-act --session X state`，按 `id=emailOrLdapLoginId`（email 框）和 `type=password`（密码框）重新定位索引。

## 3. 只读查看

| 页面 | URL | 说明 |
|------|-----|------|
| 工作流列表 | `/home/workflows` | 所有工作流 |
| 执行记录列表 | `/home/executions` | 执行历史（ID、状态、时间），点击行进入详情 |
| 执行详情 | `/workflow/{workflowId}/executions/{executionId}` | 画布 + 节点运行状态 |
| 工作流编辑器 | `/workflow/{workflowId}` | 画布（节点结构） |

- **画布位置因页面而异**：
  - **工作流编辑器** `/workflow/{workflowId}`：画布**在父页面**（无 iframe），`.vue-flow__node` 直接可查，共 169 节点
  - **执行详情** `/workflow/{id}/executions/{eid}`：画布**在 iframe**（`/workflows/demo`），需 `iframe.contentDocument.querySelectorAll('.vue-flow__node')`
- 节点按 `innerText` 找（如含"Webhook"）；工作流编辑器页画布可看到完整流程节点结构
- 点击执行行（列表里含执行 ID 的 `<a class=_workflowName>`）进入执行详情

## 4. callback_token 获取（关键）

`callback_token` 在 **Webhook 触发节点的输入数据**里（`finished_callback_url`），对应平台某 JobRun。

**推荐获取方式（可靠）**：
1. **自动提取（browser-id + /rest API，⭐ 已突破）**：
   - 登录 n8n 后，从 network 请求捕获 `browser-id` header 值（如 `network requests` 看 XHR 的请求头）
   - 在页面 eval 用 fetch 调 `/rest/executions/{eid}`（带 `browser-id` header + `credentials:'include'`）：
     ```js
     fetch('/rest/executions/' + eid, {headers: {'browser-id': 'X'}, credentials: 'include'}).then(r=>r.text()).then(t => { const i = t.indexOf('workflow-gateway/api/webhook'); ... })
     ```
   - 从响应文本提取 `workflow-gateway/api/webhook/cost-effectiveness-integrated-evaluation?job_run_id=X&callback_token=Y`（用 indexOf 定位，注意数据分片/引用但 URL 以明文存在）
   - 执行记录 ID（eid）从 `/home/executions` 列表或 `/rest/executions?limit=N`（结构 `d.data.results[].id`）获取——**⚠️ `/rest/*` 全部需带 `browser-id` header，列举 `/rest/executions` 也一样，否则 401**
   - **完整流程（已验证成功）**：创建平台 JobRun → 等 n8n 触发 → `/rest/executions?limit=3` 找最新执行（对应 job_run_id）→ `/rest/executions/{eid}` 提取 `workflow-gateway/api/webhook...callback_token=` → 用 `abacas-cloud-ops` webhook 导入结果
2. **用户手动**：让用户从 n8n 执行详情复制最新执行的 `finished_callback_url`（含 `job_run_id=X&callback_token=Y`）——可靠兜底
3. **n8n API**：`GET /api/v1/executions`（带 `X-N8N-API-KEY`）→ 找执行数据里的 Webhook 输入

**⚠️ 已知限制**：无头浏览器（stealth）中点击画布节点**无法弹出 NDV 数据面板**（多次尝试：单击/双击/Enter/节点内按钮均失败）——n8n 的重交互 SPA 在无头渲染受限。需真实浏览器或手动。

## 5. 踩坑记录

1. **n8n session 不持久化**：stealth 重开需重新登录（账号密码），不像 ABaCAS 平台扫码一次长期有效。
2. **画布位置因页面而异**：工作流编辑器页在**父页面**（`.vue-flow__node` 直接可查）；仅执行详情页在 iframe（`/workflows/demo`）。
3. **NDV 面板无头受限（配置+数据均无法弹出）**：工作流编辑器点节点不弹配置面板、执行详情点节点不弹运行数据面板——节点**详细配置/数据无法通过无头浏览器查看**；流程结构（节点列表/阶段）可看，细节需真实浏览器或手动。
4. **n8n `/rest/*` API 401 的解法**：是 **CSRF 双重提交**，需请求头带 **`browser-id`**（值从登录后 network 请求的请求头捕获，如 `348d2a2e-...`）+ session cookie（fetch 自动带）。带 `browser-id` 后 `/rest/executions/{id}` 返回 200（18MB 执行数据）。⚠️ `X-N8N-API-KEY` 用于 `/api/v1/*`（非 `/rest/*`）。
5. **chrome-direct 控制用户 Chrome 报错**：`Page target frame tree could not be built`（本环境不可用）。
6. **执行详情页有公告抽屉**：点击节点内部按钮可能误弹"我们一直在忙着 ✨"公告，非数据面板，需先关闭 `.el-drawer__close-btn`。

## 6. 工作流完善度分析（JSON 法）

n8n 工作流可导出 JSON（用户提供 `全链条费效评估v2_20260812.json`）系统分析：

- **连接完整性**：`connections` 键=源节点名，值含 `main` 数组→目标节点。检查：孤立节点（无入无出）、悬空终点、起点数。全链条费效评估 v2：169 节点，1 起点(Webhook)，0 孤立，0 悬空——**连接完整**。
- **类型分布**：httpRequest(54)/code(38)/compression(26)/merge(20)/set/if/filter/webhook(1)。
- **服务调用**：统计 httpRequest 的 `parameters.url`（去 `{{}}` 模板），看覆盖哪些服务（cost-evaluation、rsm-python、rsm-dotnet、reduction-measures）。
- **异常检查**：空 url、jsCode 含 TODO/FIXME、xxx 占位。全链条费效评估 v2：**0 异常**。
- 结论参考：完整流程 = 连接无孤立 + 服务调用齐全 + 无 TODO 占位。

## 7. 与 abacas-cloud-ops 配合

- n8n 是 ABaCAS 平台工作流引擎，平台的 `finished_callback_url`（含 callback_token）从这里获取
- 拿到 token 后用 `abacas-cloud-ops` 的 webhook 导入结果（`POST /api/webhook/{workflowKey}?job_run_id=X&callback_token=Y`）
- 工作流定义可导出 JSON 分析节点（如 Webhook 触发器、结束任务节点的回调逻辑）
