---
name: doubao-session-management
description: >-
  管理豆包桌面版（Doubao / TraeWork 同类的字节 Electron 客户端）的会话：导出会话正文为
  脱敏 Markdown、生成"来时路"HTML 时间线、按"多久没动"批量删除会话。核心方法是 CDP 挂
  调试端口，从 DOM 抓消息与 <TIME> 时间；正文在云端、本地 IndexedDB 只有元数据，所以
  改本地库删不掉会话，必须走应用自己的删除菜单。当用户说"读豆包会话""把豆包对话导出来"
  "看我用豆包的来时路""删掉豆包里很久没用的会话"时用。
user-invocable: true
---

# 豆包会话管理：导出、时间线、批量删除

豆包桌面版是「Electron + 云端同步」的聊天工具。这次完整打通了三件事：导出正文、
抓会话时间、批量删除。所有坑都是真踩过的，下面按"先能用、再避坑"写。

## 零、最重要的三条结论（先看，省几小时）

1. **会话正文 100% 在云端，本地 IndexedDB 里没有**。
   全盘扫过 7 个 IndexedDB 库（User / User Data 各 4 个）+ 4490 条物理记录，
   会话 ID 命中 **0**。所以——
2. **改本地 leveldb 删不掉会话，还会损坏数据库**。
   classic-level 用 `idb_cmp1` 字节序 comparator 能打开库但**读出 0 条**（comparator 不匹配），
   硬写等于破坏数据。删除必须走应用自己的删除菜单（它会同步删云端）。
3. **CDP 连的是隐藏辅助窗口，不是你看到的主窗口**。
   CDP 页面视口只有 400×600 / 1008×524，主窗口是 1512×786 的原生 WebView2。
   所以**按钮坐标全是负的**（x=-56、-273），用坐标点击永远点不对。
   解法：**用 JS 派发完整鼠标事件序列**（见第三节），不依赖坐标。

## 一、启动与连接

```powershell
# 必须干净重启 + 调试端口；豆包自己崩溃重启会丢端口
Get-Process | ? ProcessName -eq 'Doubao' | % { try{$_.Kill()}catch{} }
Start-Sleep -Seconds 5
Start-Process 'D:\豆包\Doubao\app\Doubao.exe' -ArgumentList '--remote-debugging-port=9222'
# 判活
Invoke-RestMethod 'http://127.0.0.1:9222/json/list'
```

Python 侧用 `aiohttp` 的 `ws_connect`（本机没有 `websocket-client`，但有 `aiohttp`）：

```python
async with s.ws_connect(ws_url, max_msg_size=0) as ws:
    await ws.send_json({"id": 1, "method": "Runtime.evaluate",
                        "params": {"expression": js, "awaitPromise": True,
                                   "returnByValue": True}})
```

**选页面**：连 `doubao-launcher/chat` 或 `?viewId=101` 的 page。导航到某个会话后
URL 会变成 `doubao-launcher/chat/<id>`，下次要重新按前缀匹配，别写死 viewId。

## 二、导出会话正文与抓时间

正文和时间都在 DOM 里，**一次导航同时抓**：

```js
// 消息节点：class 含 message/bubble，或 data-role
document.querySelectorAll('[class*="message"],[data-role],[class*="bubble"]')
// 时间节点：<TIME> 元素，文本如「3月5日 17:46」
document.querySelectorAll('TIME').map(n => n.textContent.trim())
```

时间解析：`(\d{1,2})月(\d{1,2})日` → 补当前年；若结果在未来则用去年。

**关键坑**：导航到 `chrome://doubao-launcher/chat/<id>` 或 `chrome://doubao-chat/chat/<id>`
后，Electron **不会真正打开会话正文**（TIME 抓不到）。必须在侧栏 DOM 里**点开**会话项，
或页面本来就停在该会话上。脚本 `doubao_cdp_extract.py` 里做了"轮询等待渲染"。

**导出时必做脱敏**：会话里可能含 API key（如 `sk-xxx`），替换成 `[REDACTED_API_KEY]`。
密钥一旦出现在对话/截图里，提醒用户去控制台轮换。

## 三、批量删除（核心，已验证删 270+ 个）

### 3.1 触发菜单：必须用完整鼠标事件序列

普通 `el.click()` **不触发** React 组件的菜单。必须在页面上下文里派发：

```js
const fire = (b) => {
  for (const t of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    const E = t.startsWith('pointer') ? PointerEvent : MouseEvent;
    b.dispatchEvent(new E(t, {bubbles:true, cancelable:true, view:window, button:0}));
  }
};
```

### 3.2 完整删除链（每项都验证）

```
1. 定位会话项：a[class*="conversation-item"] 里 href 含目标 id
2. fire(该项下 aria-label="更多" 的 button)
3. 找短文本以「删除」开头的元素 → fire
4. 弹窗 [role="dialog"] 里找文本为「删除」的 button → fire
5. 验证：该 id 不再出现在 DOM（GONE）
```

菜单项实测有：置顶 / 重命名 / 复制分享链接 / 归档 / **删除（Ctrl+D）**。
注意别点到相邻的「归档对话」——我早期误归档过一个会话。

### 3.3 加载全部会话：反复滚动容器

侧栏默认只显示「最近」20-30 个，老会话在折叠的项目分组里。
每轮：点所有「展开更多项目」+ 滚动所有可滚动容器（`scrollTop += 1200`），
会话数会 23→60→76→229 这样涨，直到不再增加。

### 3.4 两个必踩的坑

- **`NO_DIALOG` 大批失败**：连续删除太快，弹窗没渲染完。等待从 0.25s 加到
  **0.6s（more/delitem 后）、1.2s（confirm 后）** 后，124 个重试全部成功。
- **CDP 页面被导航弄丢**：一个脚本导航到 `doubao-chat/chat/<id>` 后，launcher 页消失，
  后续脚本取页面 `IndexError`。每个脚本开头重新 `json/list` 取页面，别缓存。
- **`NOT_FOUND` 不一定是失败**：重跑时目标已在上轮删掉，属正常，别当成没删成功。

### 3.5 删除后验证

重启豆包（丢 CDP 端口也不怕）→ 重新带 9222 启动 → 滚动加载全部 → 抽查已删 ID
是否 GONE、应保留的（如「主对话」）是否还在。**云端删除重启后依然生效**才算真删掉。

## 四、会话分类与时间判据

豆包会话 ID 是递增的雪花 ID，前缀能粗判年代（本机实测）：

| ID 前缀 | 大致年代 | 备注 |
|---|---|---|
| `1409...` | 主对话，一直在用 | 别删 |
| `3841...` | 3-4 月 | 老会话 |
| `3842...` | 6-7 月 | 老会话 |
| `3843...` | 6-7 月 | 老会话 |
| `3844...` | 9-10 月 | 易漏：不在早期接口清单里 |
| `3845...` | 10-11 月 | 近期，多数 <21 天，需看实际时间 |

**不要只按前缀删**：我漏过 3844 那批（9月4日的会话），因为第一批清单基于不完整的
47 个接口会话。用「已有 DOM 时间记录 + 前缀」双重判据，没时间的才用前缀推断。

## 五、接口与本地库（知道就行，别走这条路）

- `POST https://www.doubao.com/im/conversation/batch_get` —— 只返回**首屏**会话
  （47 个），`hasMoreConversations: false` 是假的，只针对当前视图。别用它做全量。
- 展开项目 + 滚动侧栏才能拿到**全部 160-229 个**会话。
- `sdk_storage/*/messages.db` 等本地库全加密（头 16 字节随机密文），打不开。
- `chrome_doubao-chat_0.indexeddb.leveldb` 用 dfindexeddb 能读元数据，但**无会话正文**。

## 六、可复用脚本

| 脚本 | 干什么 |
|---|---|
| `scripts/doubao_cdp_extract.py` | CDP 导航到会话，抓正文 + `<TIME>`，输出 md（脱敏） |
| `scripts/scan_sidebar.py` | 展开项目 + 滚动，抓全部会话的 id + 名字 |
| `scripts/batch_delete.py` | 批量删除：完整事件序列 + 更多→删除→确认→验证，带 NO_DIALOG 防护 |
| `scripts/make_timeline.py` | 从导出 md + 时间生成"来时路"HTML |

所有脚本依赖 `aiohttp`（`pip install aiohttp`），输出目录可用命令行参数指定。

## 七、顺带一提：GitHub 上的批量删除攻略

豆包桌面版本身有官方批量删除：侧栏分组悬停 → 右侧图标 → **历史对话管理** →
右上角 → **批量删除对话** → 勾选 → 删除。CDP 操作时这个入口比逐条快，但需要找对
按钮（本 skill 的逐条 fire 法更稳，因为不依赖坐标）。
