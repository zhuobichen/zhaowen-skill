---
name: abacas-cloud-ops
description: >
  操作"经济能源-碳污排放-大气环境动态耦合集成模型平台"(ABaCAS Cloud 测试环境, cloud-test.abacas-dss.com)。
  当用户要求：操作 ABaCAS/abacas-dss 平台、查看/下载任务结果文件、获取任务(JobRun/JobProfile)列表、上传用户文件、
  创建/运行全链条费效评估任务、修改/重命名情景名、以某任务参数新建运行、处理费效比/减排量化/RSM/BenMAP 结果、
  把结果导入平台展示(webhook+callback_token)、从 n8n 工作流获取 token、导出结果后本地重命名 时使用。
  涵盖：browser-act 浏览器自动化(acs-stealth2)、Logto 微信扫码登录、Token 网络拦截捕获、workflow-gateway API 调用、
  webhook 结果导入机制、n8n 工作流结构、callback_token 获取、平台 BUG(改 xlsx 表头会改数值)、导出后重命名方案等经验。
---

# ABaCAS Cloud 平台操纵 Skill

> 平台全称：经济能源-碳污排放-大气环境动态耦合集成模型平台（全链条费效评估）
> 测试环境地址：`https://cloud-test.abacas-dss.com`

## 前置环境要求

- **browser-act CLI**：`uv tool install browser-act-cli --python 3.12`（浏览器自动化）
- **browser-act 浏览器**：stealth `acs-stealth2`（ID `103206233488452404`）。创建命令：
  `browser-act browser create --type stealth --name acs-stealth2 --desc "ABaCAS微信扫码登录持久化"`
  首次使用需在浏览器内**微信扫码登录 ABaCAS 一次**，登录态持久化到该 profile；⚠️ 勿用 `acs-stealth`（有启动故障）
- **Python 3 + requests**：`pip install requests`
- **网络**：公网 `cloud-test.abacas-dss.com`（平台 API）；内网 `<内网IP>`（n8n，需先连内网/VPN）
- **适用环境声明**：凭据/浏览器/内网 IP/域名均为作者测试环境，迁移需对应调整；n8n 凭据见 `n8n-web-ops`
- **配合 skill**：`n8n-web-ops`（获取 callback_token）、`browser-act`（浏览器自动化）

## 1. 平台信息

| 项 | 值 |
|----|-----|
| 首页 | `https://cloud-test.abacas-dss.com/FSAPlatformCloud/home` |
| 全链条评估页 | `/FSAPlatformCloud/IntegratedEvaluation/preview` |
| 创建任务页 | `/FSAPlatformCloud/analysis` |
| API 网关(公网) | `https://cloud-test.abacas-dss.com/workflow-gateway/api` |
| API 网关(内网/n8n侧) | `http://<内网IP>/workflow-gateway/api` |
| Swagger | `/workflow-gateway/swagger/v1/swagger.json` |
| 认证 | Logto OAuth2（微信扫码），认证服务器 `<Logto认证服务器>` |
| 技术栈 | 前端 Vue3 SPA / 后端 ASP.NET Core / 工作流 n8n / JWT ES384 |
| 工作流 Key | `cost-effectiveness-integrated-evaluation` |
| n8n 服务 | `http://<内网IP>:5678`（工作流名"全链条费效评估 v2"） |

## 2. 浏览器自动化（推荐 browser-act）

**首选浏览器：`acs-stealth2`（ID `103206233488452404`）**
- 其 stealth profile **持久化登录 Cookie**，隔天再开通常仍保持登录，无需重复扫码
- ⚠️ **不要用 `acs-stealth`（ID `103204260194844469`）**——有启动故障（BROWSER_IPC_TIMEOUT，chrome.exe 不初始化，stderr 空），暂不可用

```bash
browser-act --session acs browser open 103206233488452404 "https://cloud-test.abacas-dss.com/FSAPlatformCloud/home"
browser-act --session acs eval "(() => { const a=document.querySelector('img[alt=\"User Avatar\"]'); const e=document.body.innerText.includes('登录已过期'); const b=Array.from(document.querySelectorAll('button')).filter(x=>x.innerText.includes('登录')&&!x.innerText.includes('退出')).length; return JSON.stringify({hasAvatar:!!a,loginExpired:e,loginButtons:b}); })()"
```

**登录检测三条件（同时满足=已登录）**：① 有 `img[alt="User Avatar"]` ② 无"登录已过期" ③ 无"登录"按钮（排除"退出登录"）。

若未登录（微信扫码为页面外验证），用 browser-act `remote-assist` 生成远程控制链接交给用户扫码，或 `--headed` 打开可见窗口。

## 3. Token 获取（关键）

- JWT **不存储**于 localStorage/sessionStorage/cookie，由 Vue 内存管理，**只能拦截网络请求**获取
- 导航到 `/IntegratedEvaluation/preview`（触发 `GET /api/JobProfile`）后查看捕获请求的 `Authorization` header
- Token 有效期约 **1 小时**，过期后 API 返回 401；**跨天/隔天必过期**
- 过期后**无需重新扫码**（stealth profile 登录态仍在），重新导航触发 API 再拦截即可

```bash
browser-act --session acs navigate "https://cloud-test.abacas-dss.com/FSAPlatformCloud/IntegratedEvaluation/preview"
browser-act --session acs wait stable
browser-act --session acs network requests --filter workflow-gateway --type xhr,fetch
# 期望输出是 CSV 表，找到 GET 200 的 /api/JobRun 或 /api/JobProfile 那条，取其 request_id：
#   request_id,method,status,...,url
#   D70B78E80C8690E4F6E5BF971F5E2D75:6020.88,GET,200,XHR,...,https://.../api/JobRun
browser-act --session acs network request "<request_id>" | grep -i Authorization
# 期望得到: Authorization=Bearer eyJhbGciOiJFUzM4NCIs...（即 Token）
```

Token 建议存到临时文件复用：`TOKEN=$(cat tmp_token.txt)`（有效期约 1 小时，超时重新导航捕获）。

## 4. API 清单（Bearer Token 认证，除 webhook）

### JobProfile（任务配置模板）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/JobProfile` | 当前用户所有任务配置 |
| POST | `/api/JobProfile` | 创建（body: name, inputFiles, config, workflowKey, description） |
| PUT | `/api/JobProfile/{id}` | 更新 |
| DELETE | `/api/JobProfile/{id}` | 删除配置 |

### JobRun（任务运行）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/JobRun` | 所有运行列表 |
| POST | `/api/JobRun` | 创建并排队（body: profileId, name, description），返回 202 |
| GET | `/api/JobRun/{id}` | 运行详情（status: Pending/Running/Completed/Failed） |
| GET | `/api/JobRun/{id}/Files` | **结果文件列表** |
| GET | `/api/JobRun/{id}/Files/{fileName}` | 下载单个文件（文件名 URL 编码） |
| GET | `/api/JobRun/{id}/Files/Download` | 打包下载 ZIP |
| GET | `/api/JobRun/{id}/Logs` | 执行日志（定位失败原因） |
| DELETE | `/api/JobRun/{id}` | 删除运行 |

### AppFile（文件）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/AppFile/SampleData` | 示例文件列表（内置数据源） |
| GET | `/api/AppFile/SampleData/Download/{fileName}` | 下载单个示例文件 |
| GET | `/api/AppFile/UserUpload` | 用户上传文件列表 |
| POST | `/api/AppFile/UserUpload` | **上传**（multipart/form-data，字段名 `file`） |
| GET | `/api/AppFile/UserUpload/Download/{fileName}` | 下载用户文件 |
| DELETE | `/api/AppFile/UserUpload/{fileName}` | 删除用户文件 |

### Webhook（结果导入，无需 Bearer Token，需 callback_token）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/webhook/{workflowKey}?job_run_id=X&callback_token=Y` | **n8n 回传/导入结果**（multipart: job_status + result_data） |
| POST | `/api/webhook/{workflowKey}/log?job_run_id=X&callback_token=Y` | 追加进度日志（body: message, level, stepName） |

## 5. 核心操作流程

### 5.1 查看任务及结果文件
```python
import requests
h = {'Authorization': 'Bearer '+TOKEN, 'Accept-Encoding': 'gzip, deflate'}
BASE = 'https://cloud-test.abacas-dss.com/workflow-gateway/api'
jobs = requests.get(f'{BASE}/JobRun', headers=h).json()
files = requests.get(f'{BASE}/JobRun/{job_id}/Files', headers=h).json()
logs = requests.get(f'{BASE}/JobRun/{job_id}/Logs', headers=h).json()  # 失败时看这里
```

### 5.2 上传文件（中文文件名必须用 requests）
```python
with open('文件.xlsx','rb') as fh:
    files = {'file': ('文件.xlsx', fh, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    r = requests.post(f'{BASE}/AppFile/UserUpload', headers=h, files=files)
```

### 5.3 复制配置创建新任务
1. `GET /api/JobProfile/{srcId}` 取原配置
2. 深拷贝 `config`，按需改 `config_json.emissionReductionQuantOptions`
3. `POST /api/JobProfile`（body 只含 name, inputFiles, config, workflowKey, description）
4. `POST /api/JobRun`（profileId=新id）→ 得到新 JobRun id
5. 轮询 `GET /api/JobRun/{id}` 至 Completed/Failed

### 5.4 导入结果到任务（webhook，替代重跑展示）

**用途**：不重跑工作流，直接把已有/重命名后的结果文件导入某任务，让平台展示。

```python
# 前置：目标任务 ID + 该任务自己的 callback_token（从 n8n 获取，见 §6）
CB_URL = 'http://<内网IP>/workflow-gateway/api/webhook/cost-effectiveness-integrated-evaluation?job_run_id=X&callback_token=TOKEN'
url = CB_URL.replace('http://<内网IP>', 'https://cloud-test.abacas-dss.com')  # 公网访问

# 把结果文件打包 zip（替换任务现有结果）
import zipfile
with zipfile.ZipFile('result.zip','w',zipfile.ZIP_DEFLATED) as zf:
    for f in result_files:
        zf.write(f, os.path.basename(f))

# webhook 上传（必须用 files 参数生成 multipart；手动 Content-Type 会报 415/boundary 错）
with open('result.zip','rb') as fh:
    r = requests.post(url, files={
        'job_status': (None, 'completed'),
        'result_data': ('result.zip', fh, 'application/zip')
    }, timeout=60)
```

**webhook 响应**：缺 token → `401 The callback token is required`；任务不存在 → `404 Job run 'X' was not found`；成功 → `200/202`。✅ **2026-08-12 后端已改为替换语义**（A1/A2 修复，用户改代码部署）：调用 webhook 导入会**替换该任务全部结果文件**，不再追加/残留——可用于"上传结果不运行"的干净展示。

### 5.5 输出交付规范（导出重命名 + 配置文件 + file-list）

**用途**：把任务结果重命名情景后完整交付（结果文件 + file-list + 配置文件）。

1. **下载结果，保留 UTF-8 BOM**：`content.decode('utf-8-sig')` → 替换 → `content.encode('utf-8-sig')`（平台原始 CSV 有 BOM，须保留）
2. **文件名 + 内容替换**：`情景1→强化治理情景`、`情景2→常规情景`（文件名、measure_SI_summary、BenMAP Case_Name、情景 JSON、ReductionScenarioInfo 全改；JSON 用 `json.load/dump` 更稳）
3. **生成 file-list**（如 `China_file-list-255.json`）：`{taskId, apiEndpoint, retrievedAt, totalFiles, files[]}`，格式对齐平台
4. **生成配置文件**（如 `JobProfile_255_config.json`）：下载 `GET /api/JobProfile/{srcId}` 后本地改：
   - `id` → 新任务号；`name` / `config_json.projectTaskName` / `project_json.projectTaskName` → 新任务名
   - `scenarioColumns[].label` → 新情景名（config_json + project_json 两处）
   - `createdAt` / `updatedAt` → 目标时间（如今早9点 = UTC 01:00）
   - **`emissionReductionQuantOptions` 精简为只保留 `presetFileName`**（删除 selectedMeasures/customizedValues/scenarioColumns/backendType/defaultScenario——后端现在只读 presetFileName）
5. **打包 zip**：结果文件 + file-list + 配置文件

## 6. n8n 工作流与结果回传机制

### 工作流结构（"全链条费效评估 v2"，169 节点）
1. **Webhook 触发器**（`POST /webhook/<webhook触发器ID>`，headerAuth）——平台后端创建 JobRun 时 POST 到这里
2. 触发 body 含：`job_run_id`、`job_run_name`、`job_profile_id`、`finished_callback_url`、`log_callback_url`、`job_profile_config_json` 等
3. n8n 执行全链条评估
4. **结束任务节点**（HTTP Request）`POST` 到 `finished_callback_url`（multipart: `job_status=completed` + `result_data`=二进制）

### callback_token 获取（关键）
- token **每任务唯一**，由平台后端在创建 JobRun 时签发，通过 `finished_callback_url` 传给 n8n
- **API 不暴露 token**（不在 JobRunDto 中）
- 获取途径（二选一）：
  1. **n8n 执行记录**：打开工作流 → Executions → 某次执行 → Webhook 节点输入 → `body.finished_callback_url`（含 token）
  2. **后端 DB/源码**：JobRun 表存的 token，或 abacas-cloud 签发逻辑
- ⚠️ 任务的 token 只对该任务有效；任务删除后 token 即失效

## 7. 导出后重命名替代方案（绕开平台 BUG）

**目标**：让平台展示"强化治理/常规"等自定义情景名（平台直接改不了）。

**方案**：
1. **用原文件跑任务**（表头"情景1/情景2"）→ 数值正确
2. 下载结果，**本地重命名**：文件名+内容中 `情景1→新名1`、`情景2→新名2`（UTF-8 文本替换，注意 3 个 sheet 表头 + measure_SI_summary + BenMAP Case_Name + JSON scenarioName）
3. 打包 zip
4. 用 §5.4 webhook 导入目标任务（需该任务 token）

**命名映射参考**：费效比 B/C 高者（≈3.8）为情景1 → 强化治理情景；低者（≈3.2）为情景2 → 常规情景。

## 8. ⚠️ 踩坑记录（重要）

1. **【平台 BUG】后端硬编码按 xlsx 表头「情景1/情景2」读取减排参数列**：改表头（无论 openpyxl 重存还是保真改 sharedStrings）→ 后端找不到「情景1/情景2」列 → 费效比数值错误（AQB/BI 全线异常）。`scenarioColumns[].label` 配置**完全无效**（不影响输出文件名、scenarioName、数值——输出文件名也来自 xlsx 表头）。**结论：不改表头数值才对（B/C 复现 254 的 3.83/3.18，即平台展示的 3.8/3.2），要改情景名需用 §7 导出重命名方案或提 bug。** 另：openpyxl 重存的 xlsx 即使表头正确，也会破坏内部结构导致情景2 读取错误——**改平台输入 xlsx 必须用保真方式（zipfile 只改 sharedStrings）或直接用原文件**。
2. **curl 上传中文文件名会乱码**（Windows GBK 编码 → 服务端存成 `�`）→ 必须用 Python `requests` 上传。
3. **响应 br 压缩**：requests 解码大响应会报 `ContentDecodingError` → headers 加 `Accept-Encoding: gzip, deflate`。
4. **inputFiles 必须含预设文件**：presetFileName 指向的文件必须在 inputFiles 列表，否则 `REDUCTION_CONVERT_FAILED`。
5. **JobRun ID ≠ JobProfile ID**：通过 `profileId` 字段关联。
6. **SPA 深链接直接访问返回 404**：必须前端路由导航。
7. **acs-stealth 浏览器不可用**：用 acs-stealth2。
8. **webhook multipart 必须用 requests `files` 参数**：手动设 `Content-Type: multipart/form-data` 会报 `415` 或 `Missing content-type boundary`。
9. 结果文件命名：`Case #情景X <指标> <粒度> <Point/Spatial Field>.csv`，另有 `measure_SI_summary.csv`、`*_BenMAP_apvrx.csv`、`情景X.json`、**`ReductionScenarioInfo.json`（情景元数据，本地可视化必需）**。
10. **费效比 B/C = PM25_BenMAP 的 PointEstimate 汇总 / Control Case_Reduction_Cost 的 Control_Cost 汇总**（前端按此展示）。
11. ~~webhook 追加语义~~ → **2026-08-12 后端已改为替换语义**（A1/A2 修复）：导入会替换该任务全部结果文件，不再追加/残留，可干净展示。
12. **Failed 任务在平台 UI 不可见**：无法用"失败任务 + 导入"方案在平台界面展示（平台隐藏 Failed）；要"上传结果不运行"需用**正常任务 + webhook 替换导入**（创建 JobRun 触发一次 n8n，导入替换其结果即干净）。
13. **CSV 保留 UTF-8 BOM**：平台原始 CSV 带 BOM，本地重命名保存必须用 `utf-8-sig` 编码，否则 BOM 丢失。
14. **JobProfile 配置精简**：`emissionReductionQuantOptions` 后端现在只读 `presetFileName`，创建/保存配置可删除 `selectedMeasures`（3751条）等大字段，减小体积。

## 9. 验证

- 下载文件后核对大小与 SampleData 列表一致（防错误页面）
- 费效比文件表头：`Region,Pollutant,Baseline_Emission(Ton),Control_Cost(RMB),Removed_Emission(Ton),Remained_Emission(Ton),RSM_Region`
- 任务完成标准：`status == Completed` 且文件数符合预期
- 导入结果后：`GET /api/JobRun/{id}/Files` 确认文件名为新情景名

## 10. 脚本工具（scripts/）

可复用脚本位于本 skill 的 `scripts/` 目录。Token 来源：`--token` 参数 > `ABACAS_TOKEN` 环境变量 > 工作目录 `tmp_token.txt`。

| 脚本 | 用途 | 用法 |
|------|------|------|
| `upload_file.py` | 上传文件到 UserUpload（中文名安全） | `python upload_file.py 文件.xlsx` |
| `download_results.py` | 下载任务结果（保留 BOM） | `python download_results.py 254 out/` |
| `calc_bc.py` | 计算费效比 B/C | `python calc_bc.py --dir out/` 或 `python calc_bc.py 254` |
| `rename_scenarios.py` | 重命名情景（保留 BOM，支持目录/zip） | `python rename_scenarios.py src.zip out/ --s1 强化治理情景 --s2 常规情景` |
| `import_webhook.py` | webhook 导入结果（需 callback_token） | `python import_webhook.py 262 TOKEN result.zip` |
| `gen_filelist.py` | 生成 file-list JSON | `python gen_filelist.py out/ 255` |
| `gen_config.py` | 生成精简配置文件（改 id/名/情景/时间） | `python gen_config.py 233 --new-id 255 --name China_措施量化_强化治理` |
| `generate_dashboard.py` | 生成本地可视化仪表盘（7 图表：费效比/成本/AQB/BenMAP/各城市成本/效益/效益比，含情景切换） | `python generate_dashboard.py --dir task255_out --out dash.html` |

**典型交付流程**：
`download_results → rename_scenarios → gen_filelist → gen_config → 打包 zip → (可选) import_webhook 导入平台展示 / generate_dashboard 本地可视化`
