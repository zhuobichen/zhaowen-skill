---
name: bsk-js-extract
description: 用 browser-skill(bsk) 在网页里直接跑 JS 一次读完数据，代替"逐步点击/填写"。适合在用户已登录的站点上批量抽取列表、价格、表单状态，或按条件筛选后再取数（例如携程酒店比价）。当任务涉及"在网页上读出多条数据""比价""按关键词筛选后取结果"时使用。
version: 1.0.0
---

# 用 JS 读网页（bsk + evaluate）

全部通过用户的**真实浏览器**（`browser-skill` / `bsk`）完成，复用其登录态，不碰 Cookie。

## 为什么用 JS 而不是逐步点击

bsk 0.4.x 是 **strict 控制策略**：每个 `click`/`fill` 都要先
`cooperate sync` 拿 `context_id` + `observation_id`，而**页面一变（甚至人手一碰）context 就失效**，
报 `the control context no longer belongs to the current document`。

逐步点会反复被这个打断。**改成 `evaluate` 跑一段 JS，一次调用把整页数据读回来**，
又稳又省 token。

## 前置（本机已知的三个坎）

1. `bsk` 不在 PATH，在 `C:\Users\Administrator\.codex\browser-skill\bsk.exe`（旧版 0.1.8，**不能用**）
2. 当前 shell 是受限令牌，**写不了 `~/.bsk` 和 `%TEMP%`** → 必须把家目录指到工作区
3. Edge 里的扩展是 **0.4.1**，CLI 也要 0.4.1；0.4.1 **不允许分离启动 daemon**，要 `--foreground`

```powershell
$ws = "D:\github_project\ZhaoWen_GitHub维护"
$env:BSK_HOME = Join-Path $ws "_bskhome"
$env:TEMP = Join-Path $ws "_tmp"; $env:TMP = $env:TEMP
$env:BSK_AUTO_START = "0"
$bsk = Join-Path $ws "_bsk041\bsk.exe"       # 0.4.1，从 GitHub releases 下到工作区
```

`_bsk041` 若不存在：
`https://github.com/Tencent/BrowserSkill/releases/download/cli-v0.4.1/bsk-v0.4.1-x86_64-pc-windows-msvc.zip`

daemon 必须在**常驻后台任务**里起（前台会阻塞，这是 0.4.1 的要求）：

```powershell
& $bsk daemon start --foreground        # 后台作业
```

判据只有一个：**`bsk status` 里 `browsers connected >= 1`**。
daemon 起来了但 browser=0，就是 CLI/扩展版本不一致或扩展没连上。

## 标准流程

```powershell
$out = & $bsk session start 2>&1
$sid = ($out | Where-Object { $_ -match '^[a-z]{4}$' } | Select-Object -Last 1)

& $bsk navigate "<url>" --session $sid

# 每次动作/读取前都要 sync；取 context_id 与 observation_id
$s = (& $bsk cooperate sync --session $sid --policy target 2>&1 | Out-String) | ConvertFrom-Json

& $bsk evaluate $js --session $sid --context $s.context_id --observation $s.observation_id

& $bsk session stop $sid
& $bsk daemon stop
```

- 有 `scripts/run-js.ps1` 把"sync + evaluate"合成一步，优先用它
- `snapshot` 不需要 context，可以先用来定位；但**动作和 evaluate 需要**

## 常用 JS 片段

**1. 列出输入框（找 ref / 定位字段）**

```js
(()=>{const i=[...document.querySelectorAll("input")];
return JSON.stringify(i.map((x,k)=>({k,ph:x.placeholder||"",v:x.value||"",t:x.type})));})()
```

**2. React 受控输入赋值**（直接 `el.value = x` 不触发更新，必须走原型 setter）

```js
(()=>{
 const el=[...document.querySelectorAll("input")].find(i=>i.placeholder.includes("位置/品牌"));
 const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set;
 set.call(el,"关键词");
 el.dispatchEvent(new Event("input",{bubbles:true}));
 el.dispatchEvent(new Event("change",{bubbles:true}));
 return JSON.stringify({ok:el.value});
})()
```

**3. 点按钮（按文字精确匹配）**

```js
(()=>{const b=[...document.querySelectorAll("button")].filter(x=>x.textContent.trim()==="搜索");
if(b.length)b[0].click();return JSON.stringify({clicked:b.length});})()
```

**4. 按行扫描抽"名称 + 数值"列表（通用）**

思路：`body.innerText` 按行切 → 记住"最近一个实体名" → 遇到目标模式（如 `^¥\d+$`）就配对。
比抓 DOM class 稳，站点改版也不容易坏。

```js
(()=>{
 const L=[...document.body.innerText.split("\n")].map(s=>s.trim()).filter(Boolean);
 const out=[];let cur=null,rating=null,dist=null;
 for(const s of L){
  if(/酒店|公寓|民宿|公馆/.test(s)&&s.length<40&&!/^距|搜索/.test(s)){cur=s;rating=null;dist=null;}
  if(cur&&/^\d\.\d$/.test(s)&&rating===null){rating=s;}
  if(cur&&/^距.*(公里|米)/.test(s)&&dist===null){dist=s.split("查看地图")[0].trim();}
  if(cur&&/^¥\d+$/.test(s)){out.push({name:cur,rating,dist,price:+s.slice(1)});cur=null;}
 }
 ...去重后返回
})()
```

**5. 分页/滚动加载**：`window.scrollTo(0,document.body.scrollHeight)` 后 `wait-ms 1500` 再取，
分批读并把进度存 `window.__V`（`evaluate` 有 30s RPC 硬超时，长任务必须分批）。

## 已知站点参数（实测）

| 站点 | 事实 |
| --- | --- |
| 携程酒店 | 城市 id：**广州=32、深圳=30**（`?city=32`） |
| 携程 | **URL 里的 `keyword=` 参数无效**，结果不筛；必须用 JS 改「位置/品牌/酒店」再点搜索 |
| 携程 | 未登录会跳 `passport.ctrip.com` 登录页 → 用 `bsk request-help` 让用户登录，页面可交互 |
| 携程 | 登录成功判据：页面出现 `我的账户: 尊敬的会员` / `我的订单` |
| 携程 | 价格默认是**当晚**（今天→明天）；换日期要点日期控件 |

## 红线

- **不碰密码 / 支付 / 银行 / SSO 页面**上的 `evaluate`
- 只读优先；点击"提交/下单/支付"必须先问用户
- `request-help` 停在登录页让用户自己登，**不要代填账号密码**
- 收尾必须 `session stop` + `daemon stop`

## 相关记忆

`bsk-daemon-needs-workspace-home`（本机起 daemon 的四个坎）·
`ctrip-price-read-via-bsk-js`（携程比价实测样例）
