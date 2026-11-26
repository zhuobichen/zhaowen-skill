# -*- coding: utf-8 -*-
"""批量删除豆包老会话（3841/3842/3843 前缀，均为 3-7 月的老对话）。

复用已验证流程：完整鼠标事件序列 + 滚动展开 + 更多→删除→弹窗确认→验证。
每个删除后验证消失；失败的记录继续。
"""
import asyncio, json, urllib.request, aiohttp, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

d = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=10).read())
tg = [t for t in d if t.get("type") == "page" and "doubao-launcher/chat" in (t.get("url") or "")][0]

OPS = os.path.dirname(os.path.abspath(__file__))
ids_path = os.path.join(OPS, os.environ.get("DOUBAO_IDS_FILE", "_doubao_delete_ids.json"))
ids = json.load(open(ids_path, encoding="utf-8"))
print("待删老会话:", len(ids))

FIRE = """(args) => {
  const {action, id} = args;
  const fire=(b)=>{for(const t of ['pointerdown','mousedown','pointerup','mouseup','click']){
    const E=t.startsWith('pointer')?PointerEvent:MouseEvent;
    b.dispatchEvent(new E(t,{bubbles:true,cancelable:true,view:window,button:0}));
  }};
  if(action==='expand'){
    let n=0;
    document.querySelectorAll('*').forEach(x=>{
      if(x.children.length===0&&/展开更多项目|展开更多/.test((x.textContent||'').trim())){fire(x);n++;}
    });
    document.querySelectorAll('*').forEach(e=>{
      if(e.scrollHeight>e.clientHeight+30&&e.clientHeight>50) e.scrollTop+=1000;
    });
    return n;
  }
  if(action==='find'){
    const ns=[...document.querySelectorAll('a[class*="conversation-item"]')];
    return {total:ns.length, found:ns.some(x=>(x.getAttribute('href')||'').includes(id))};
  }
  if(action==='more'){
    const ns=[...document.querySelectorAll('a[class*="conversation-item"]')];
    const n=ns.find(x=>(x.getAttribute('href')||'').includes(id));
    if(!n) return 'NOT_FOUND';
    const b=[...n.querySelectorAll('button')].find(x=>x.getAttribute('aria-label')==='更多');
    if(!b) return 'NO_MORE';
    fire(b); return 'MORE_OK';
  }
  if(action==='delitem'){
    const els=[...document.querySelectorAll('*')].filter(x=>
      x.children.length===0 && (x.textContent||'').trim().startsWith('删除'));
    if(!els.length) return 'NO_DEL_ITEM';
    fire(els[0]); return 'DELITEM_OK';
  }
  if(action==='confirm'){
    const dlg=document.querySelector('[role="dialog"]') ||
      [...document.querySelectorAll('[class*="modal"],[class*="dialog"]')].find(x=>(x.innerText||'').includes('确定删除'));
    if(!dlg) return 'NO_DIALOG';
    const b=[...dlg.querySelectorAll('button')].find(x=>(x.textContent||'').trim()==='删除');
    if(!b) return 'NO_CONFIRM_BTN';
    fire(b); return 'CONFIRMED';
  }
  if(action==='check'){
    const ns=[...document.querySelectorAll('a[class*="conversation-item"]')];
    return ns.some(x=>(x.getAttribute('href')||'').includes(id)) ? 'STILL' : 'GONE';
  }
  return 'UNKNOWN';
}"""

async def main():
  async with aiohttp.ClientSession() as s:
    async with s.ws_connect(tg["webSocketDebuggerUrl"], max_msg_size=0) as ws:
      mid = 0
      async def ev(e, arg):
        nonlocal mid; mid += 1; mine = mid
        await ws.send_json({"id": mine, "method": "Runtime.evaluate",
                            "params": {"expression": f"({e})({json.dumps(arg)})", "returnByValue": True}})
        while True:
          z = await asyncio.wait_for(ws.receive_json(), timeout=30)
          if z.get("id") == mine:
            r = z.get("result") or {}
            return r.get("result", {}).get("value") if "exceptionDetails" not in r else None

      # 先展开到全量
      for i in range(30):
        await ev(FIRE, {"action": "expand"})
        f = await ev(FIRE, {"action": "find", "id": ids[0]})
        if isinstance(f, dict) and f.get("found"): break
        await asyncio.sleep(0.4)
      print("展开完成, 首目标:", await ev(FIRE, {"action": "find", "id": ids[0]}))

      done = []; failed = []
      for i, sid in enumerate(ids, 1):
        try:
          f = await ev(FIRE, {"action": "find", "id": sid})
          if isinstance(f, dict) and not f.get("found"):
            for _ in range(8):
              await ev(FIRE, {"action": "expand"})
              await asyncio.sleep(0.3)
              f = await ev(FIRE, {"action": "find", "id": sid})
              if isinstance(f, dict) and f.get("found"): break
          r1 = await ev(FIRE, {"action": "more", "id": sid})
          if r1 != 'MORE_OK': failed.append((sid, r1)); print(f"[{i}] {sid[:10]} FAIL more={r1}"); continue
          await asyncio.sleep(0.6)
          r2 = await ev(FIRE, {"action": "delitem"})
          if r2 != 'DELITEM_OK': failed.append((sid, r2)); print(f"[{i}] {sid[:10]} FAIL delitem={r2}"); continue
          await asyncio.sleep(0.6)
          r3 = await ev(FIRE, {"action": "confirm"})
          if r3 != 'CONFIRMED': failed.append((sid, r3)); print(f"[{i}] {sid[:10]} FAIL confirm={r3}"); continue
          await asyncio.sleep(1.2)
          r4 = await ev(FIRE, {"action": "check", "id": sid})
          if r4 == 'GONE': done.append(sid); print(f"[{i}] {sid[:10]} OK")
          else: failed.append((sid, r4)); print(f"[{i}] {sid[:10]} NOT_GONE")
        except Exception as e:
          failed.append((sid, str(e)[:40])); print(f"[{i}] {sid[:10]} ERR")
      print(f"\n完成 {len(done)} / 失败 {len(failed)}")
      json.dump({"done": done, "failed": failed},
                open(os.path.join(OPS, "_doubao_delete_result.json"), "w"), indent=1)

asyncio.run(main())
