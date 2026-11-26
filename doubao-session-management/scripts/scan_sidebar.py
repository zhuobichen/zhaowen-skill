# -*- coding: utf-8 -*-
"""扫描当前豆包全部剩余会话（滚动展开到底）。"""
import asyncio, json, urllib.request, aiohttp, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d=json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/list").read())
tg=[t for t in d if t.get("type")=="page" and "doubao-launcher/chat" in (t.get("url") or "")][0]

FIRE = """(args) => {
  document.querySelectorAll('*').forEach(e=>{
    if(e.scrollHeight>e.clientHeight+30&&e.clientHeight>50) e.scrollTop+=1200;
  });
  document.querySelectorAll('*').forEach(x=>{
    if(x.children.length===0&&/展开更多项目|展开更多/.test((x.textContent||'').trim())) x.click();
  });
  const ns=[...document.querySelectorAll('a[class*="conversation-item"]')];
  return ns.map(n=>({id:(n.getAttribute('href')||'').replace('/chat/',''),
                     name:(n.textContent||'').replace(/\\s/g,'').slice(0,36)}));
}"""

async def main():
  async with aiohttp.ClientSession() as s:
    async with s.ws_connect(tg["webSocketDebuggerUrl"],max_msg_size=0) as ws:
      mid=0
      async def ev(e,arg):
        nonlocal mid;mid+=1;mine=mid
        await ws.send_json({"id":mine,"method":"Runtime.evaluate","params":{"expression":f"({e})({json.dumps(arg)})","returnByValue":True}})
        while True:
          z=await asyncio.wait_for(ws.receive_json(),timeout=30)
          if z.get("id")==mine:
            r=z.get("result") or {}
            return r.get("result",{}).get("value") if "exceptionDetails" not in r else None
      seen={}
      for i in range(40):
        rows=await ev(FIRE,{}) or []
        before=len(seen)
        for r in rows:
          if r["id"]: seen[r["id"]]=r["name"]
        print(f"[{i}] {len(seen)} (+{len(seen)-before})")
        if i>5 and len(seen)==before: break
        await asyncio.sleep(0.5)
      arr=[{"id":k,"name":v} for k,v in seen.items()]
      json.dump(arr,open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"_doubao_remaining.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=1)
      print("\n剩余总数:",len(arr))
asyncio.run(main())
