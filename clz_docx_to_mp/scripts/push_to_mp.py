# -*- coding: utf-8 -*-
"""
微信兼容 HTML → 公众号草稿箱（公众号排版流水线第三步）

已实测验证的链路（2026-09，browser-act 1.4.2）：
    1. 新建草稿：导航到
       /cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&createType=0&token=T
       会打开一个全新的空编辑器；原 URL 里的 token 需为当前有效值
    2. 灌入正文：正文 ProseMirror 的 EditorView 有 pasteHTML(html) 方法
       内联样式、<h2>、<figure>/<figcaption> 都能存活；图片用 base64 data URI
       会被微信自动上传到 CDN（cgi-bin/uploadimg2cdn）并把 src 换成 mmbiz.qpic.cn
    3. 保存：点击 span#js_submit 里的 button；保存后 URL 从 isNew=1 变为 appmsgid=N

为规避单次 eval 体积上限，正文按块分批 pasteHTML（pasteHTML 在光标处追加，
粘贴后光标自动移到末尾，因此分批顺序拼接即可）。

用法：
    python push_to_mp.py <build_dir> --token TOKEN --session NAME
                          [--browser-act PATH] [--chunk-mb 1.2]
                          [--keep-existing-view] [--dry-run]
"""
import sys
import os
import io
import json
import argparse
import subprocess
import time

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_wechat import (THEME, render_block, render_blocks, to_data_uri,  # noqa: E402
                           EMPTY_NODE, END_LINE, frame_wrap)

DEFAULT_BA = r'C:\Users\Administrator\.local\bin\browser-act.exe'

NEW_DRAFT_URL = ('https://mp.weixin.qq.com/cgi-bin/appmsg'
                 '?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77'
                 '&createType=0&token=%s&lang=zh_CN')

EDIT_DRAFT_URL = ('https://mp.weixin.qq.com/cgi-bin/appmsg'
                  '?t=media/appmsg_edit&action=edit&type=77'
                  '&appmsgid=%s&token=%s&lang=zh_CN')

# 统一的取 view 逻辑。
# ⚠️ 必须每步都自愈式重取，不能只在开头取一次：微信编辑页加载完成后可能还有一次
#    客户端重定向，会把 window 上的全局变量冲掉，导致后续步骤拿到 NO_VIEW。
JS_ENSURE_FN = r'''
window.__ensureView = function(){
  if (window.__mpView && window.__mpView.state) return window.__mpView;
  var pms = document.querySelectorAll('.ProseMirror'), body = null;
  for (var i = 0; i < pms.length; i++) {
    var par = pms[i].parentElement;
    if (par && (par.className || '').indexOf('rich_media_content') !== -1) body = pms[i];
  }
  if (!body) return null;
  var el = body, vue = null;
  for (var k = 0; k < 12 && el; k++) { if (el.__vue__) { vue = el.__vue__; break; } el = el.parentElement; }
  if (!vue) return null;
  var view = vue['$options']['parent']['$parent']['__editorView'];
  if (view) window.__mpView = view;
  return view || null;
};
'''

# 清空正文：直接对 ProseMirror doc 做整段删除，比模拟全选+退格可靠
JS_CLEAR_BODY = JS_ENSURE_FN + r'''
(function(){
  var v = window.__ensureView();
  if (!v) return 'NO_VIEW';
  var size = v.state.doc.content.size;
  try { v.dispatch(v.state.tr.delete(0, size)); } catch(e) { return 'ERR:' + e.message; }
  return 'CLEARED:' + v.state.doc.content.size;
})()
'''

JS_GET_VIEW = JS_ENSURE_FN + r'''
(function(){ return window.__ensureView() ? 'VIEW_OK' : 'NO_VIEW'; })()
'''

# 校验：外框各批次之间有没有缝隙（微信给 <section> 默认加了 margin-bottom:24px，
# 不显式 margin:0 就会断成一节一节）+ 图片是否全部上了 CDN + 题注/标题是否在
JS_VERIFY = r'''
(function(){
  var pms = document.querySelectorAll('.ProseMirror'), body = null;
  for (var i = 0; i < pms.length; i++) {
    var par = pms[i].parentElement;
    if (par && (par.className || '').indexOf('rich_media_content') !== -1) body = pms[i];
  }
  if (!body) return JSON.stringify({err: 'NO_BODY'});
  var fr = [];
  body.querySelectorAll('section').forEach(function (s) {
    if ((s.getAttribute('style') || '').indexOf('border-left:1px solid') !== -1) {
      var r = s.getBoundingClientRect();
      fr.push({top: r.top + window.scrollY, bottom: r.bottom + window.scrollY,
               left: Math.round(r.left), w: Math.round(r.width)});
    }
  });
  var gaps = [];
  for (var i = 1; i < fr.length; i++) {
    var g = Math.round(fr[i].top - fr[i - 1].bottom);
    if (g !== 0) gaps.push(g);
  }
  var imgs = 0, dataN = 0, cdn = 0;
  body.querySelectorAll('img').forEach(function (im) {
    if ((im.className || '').indexOf('ProseMirror-separator') !== -1) return;
    imgs++;
    var src = im.getAttribute('src') || '';
    if (src.indexOf('data:') === 0) dataN++;
    if (src.indexOf('mmbiz.qpic.cn') !== -1) cdn++;
  });
  var lefts = {}, widths = {};
  fr.forEach(function (f) { lefts[f.left] = 1; widths[f.w] = 1; });
  var gals = [];
  body.querySelectorAll('section').forEach(function (s) {
    var st = s.getAttribute('style') || '';
    if (st.indexOf('scroll-snap-type') !== -1) {
      var r = s.getBoundingClientRect();
      gals.push({vis: Math.round(r.width), scroll: s.scrollWidth,
                 n: s.querySelectorAll('img').length,
                 ok: s.scrollWidth > r.width * 1.5});
    }
  });
  return JSON.stringify({
    frames: fr.length, gaps: gaps,
    lefts: Object.keys(lefts), widths: Object.keys(widths),
    imgs: imgs, cdn: cdn, stillData: dataN,
    captions: body.querySelectorAll('figcaption').length,
    headings: body.querySelectorAll('section[style*="border-radius:20px"]').length,
    galleries: gals,
    hasEnd: body.innerText.indexOf('END') !== -1
  });
})()
'''


def ba(args, cmd, stdin_data=None, timeout=600):
    """调用 browser-act"""
    full = [args.browser_act, '--session', args.session] + cmd
    p = subprocess.run(full, input=stdin_data, capture_output=True, timeout=timeout)
    out = (p.stdout or b'').decode('utf-8', 'replace')
    err = (p.stderr or b'').decode('utf-8', 'replace')
    return p.returncode, out.strip(), err.strip()


def eval_js(args, js, timeout=600):
    """执行 JS。

    两个坑都要绕开：
      1. 中文/非 ASCII 直接塞进命令行会损坏 → 用 json.dumps 转成纯 ASCII 字面量
      2. Windows 命令行长度上限约 32767 字符，1MB 的 payload 用 argv 必然
         报 WinError 206「文件名或扩展名太长」→ 走 eval --stdin 管道
    """
    # 传进来的 js 必须是纯 ASCII：所有中文都要由调用方用 json.dumps 转义，
    # JS 里不能出现裸中文（**包括注释**——js.encode('ascii') 会因为注释里的中文直接抛错）
    try:
        payload = js.encode('ascii')
    except UnicodeEncodeError as e:
        bad = js[e.start:e.end]
        raise SystemExit(
            '❌ 传给 eval 的 JS 含非 ASCII 字符 %r（位置 %d）。\n'
            '   中文必须用 json.dumps(s) 转义成 \\uXXXX 字面量；JS 注释里也不能有中文。'
            % (bad, e.start))
    return ba(args, ['eval', '--stdin'], stdin_data=payload, timeout=timeout)


def chunk_blocks(content, theme, img_dir, budget_bytes, strip_brackets=False):
    """按 HTML 体积切块，保证每块 < budget_bytes

    走 render_blocks（与预览同一套渲染逻辑），保证标题编号在推送稿里也一致。
    """
    htmls = render_blocks(content, theme, img_dir, embed=True,
                          strip_brackets=strip_brackets, gallery=True,
                          gallery_anchor='主旨报告')
    htmls.append(END_LINE)
    # 先按体积切块，再给每块套上「外框的一段」（首批顶边、末批底边+右下投影）
    raw, cur, cur_len = [], [], 0
    for html in htmls:
        n = len(json.dumps(html))
        if cur and cur_len + n > budget_bytes:
            raw.append(cur)
            cur, cur_len = [], 0
        cur.append(html)
        cur_len += n
    if cur:
        raw.append(cur)
    return [frame_wrap(''.join(blocks), theme,
                       first=(i == 0), last=(i == len(raw) - 1))
            for i, blocks in enumerate(raw)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('build_dir')
    ap.add_argument('--token', required=True)
    ap.add_argument('--session', required=True)
    ap.add_argument('--browser-act', default=DEFAULT_BA)
    ap.add_argument('--chunk-mb', type=float, default=1.2)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--no-title', action='store_true', help='不设置标题（调试用）')
    ap.add_argument('--appmsgid', default=None,
                    help='复用已有草稿（清空正文后重推），避免每次改动都新建一篇')
    args = ap.parse_args()

    build = args.build_dir
    with open(os.path.join(build, 'content.json'), encoding='utf-8') as f:
        content = json.load(f)

    img_dir = os.path.join(build, 'images_web')
    if not os.path.isdir(img_dir):
        print('❌ 找不到 images_web/，请先跑 render_wechat.py')
        return 1

    # content.json 里是原始文件名（xxx.jpeg/png），images_web 里是压缩后的同名 .jpg，
    # 这里按 compress_images 的命名规则（stem + .jpg）重指一次
    remapped = 0
    for b in content['blocks']:
        if b['type'] != 'image':
            continue
        stem = os.path.splitext(b['file'])[0]
        cand = stem + '.jpg'
        if os.path.exists(os.path.join(img_dir, cand)):
            b['file'] = cand
            remapped += 1
    print('图片映射: %d/%d 指向 images_web'
          % (remapped, sum(1 for b in content['blocks'] if b['type'] == 'image')))
    if remapped == 0:
        print('❌ 没有一张图匹配到 images_web/，请先跑 render_wechat.py')
        return 1

    budget = int(args.chunk_mb * 1024 * 1024)
    chunks = chunk_blocks(content, THEME, img_dir, budget)
    print('正文将分 %d 批推送（每批上限 %.1f MB）' % (len(chunks), args.chunk_mb))

    if args.dry_run:
        for i, c in enumerate(chunks, 1):
            print('  批 %d: %d 块, %.2f MB' % (i, len(c), len(json.dumps(''.join(c))) / 1048576.0))
        return 0

    # ---- 1) 新建草稿 / 或复用已有草稿 ----
    if args.appmsgid:
        url = EDIT_DRAFT_URL % (args.appmsgid, args.token)
        print('① 复用已有草稿 appmsgid=%s …' % args.appmsgid)
    else:
        url = NEW_DRAFT_URL % args.token
        print('① 新建草稿 …')
    rc, out, err = ba(args, ['navigate', url], timeout=180)
    if rc != 0:
        # 编辑页很重，navigate 常报「未在超时前到达 DOMContentLoaded」，
        # 但页面其实已经可用。这里不直接判死，改为等一下再验编辑器是否真的在里面。
        print('   ⚠️ navigate 报错（页面重时常见误报），继续验证编辑器是否可用')
        print('     ', err[:160])
        time.sleep(8)
    else:
        time.sleep(6)

    # ---- 2) 取得 EditorView ----
    print('② 取得正文 EditorView …')
    rc, out, err = eval_js(args, JS_GET_VIEW)
    if 'VIEW_OK' not in out:
        print('   ❌ 取 view 失败:', out[:300], err[:200])
        return 1
    print('   OK')

    # 复用草稿时先清空原正文，否则内容会叠加
    if args.appmsgid:
        rc, out, err = eval_js(args, JS_CLEAR_BODY)
        print('   清空原正文:', out[:60])
        if 'CLEARED' not in out:
            print('   ❌ 清空失败，中止以免内容叠加')
            return 1

    # ---- 3) 分批灌入正文 ----
    print('③ 分批灌入正文 …')
    for i, blocks in enumerate(chunks, 1):
        html = EMPTY_NODE + ''.join(blocks) if i == 1 else ''.join(blocks)
        js = (JS_ENSURE_FN +
              '(function(){var v=window.__ensureView(); if(!v) return "NO_VIEW";'
              'try{v.pasteHTML(%s);}catch(e){return "ERR:"+e.message;}'
              'return "OK:"+v.state.doc.content.size;})()' % json.dumps(html))
        rc, out, err = eval_js(args, js, timeout=900)
        ok = '"OK:' in out or 'OK:' in out
        print('   批 %d/%d: %s' % (i, len(chunks), out[:60] if ok else ('❌ ' + out[:200] + err[:200])))
        if not ok:
            return 1

    # ---- 4) 等待图片全部上传到 CDN ----
    print('④ 等待图片上传 CDN …')
    wait_js = r'''
(function(){
  var pms=document.querySelectorAll('.ProseMirror');
  var body=null;
  for(var i=0;i<pms.length;i++){var par=pms[i].parentElement;
    if(par && (par.className||'').indexOf('rich_media_content')!==-1) body=pms[i];}
  if(!body) return 'NO_BODY';
  var imgs=[]; body.querySelectorAll('img').forEach(function(im){
    if((im.className||'').indexOf('ProseMirror-separator')===-1) imgs.push(im.getAttribute('src')||'');});
  var local=imgs.filter(function(s){return s.indexOf('data:')===0;}).length;
  var cdn=imgs.filter(function(s){return s.indexOf('mmbiz.qpic.cn')!==-1;}).length;
  return JSON.stringify({total:imgs.length, local:local, cdn:cdn});
})()
'''
    # 图片多 + 质量高时（如 q95/4:4:4，43 图约 16MB base64）上传会明显变慢，
    # 等待窗口要给足，否则会误报「仍有图片未上传」——实测最后一张常在此之后才传完。
    MAX_WAIT = 240
    waited = 0
    done = False
    while waited < MAX_WAIT:
        rc, out, err = eval_js(args, wait_js)
        try:
            st = json.loads(out.split('\n')[-1])
        except Exception:
            time.sleep(4)
            waited += 4
            continue
        print('   %d 张：CDN %d，本地待传 %d' % (st['total'], st['cdn'], st['local']))
        if st['local'] == 0 and st['total'] > 0:
            done = True
            break
        time.sleep(4)
        waited += 4
    if not done:
        print('   ⚠️ 等待 %ds 后仍有图未上传；继续保存，保存后再复查一次' % MAX_WAIT)

    # ---- 5) 设置标题 ----
    if not args.no_title and content.get('title'):
        print('⑤ 设置标题 …')
        # 踩坑：只改 textarea#title.value 或只对标题 ProseMirror 做「选中并删除」都不落库。
        # 必须对标题 ProseMirror 真正插入文本 → execCommand('insertText')；
        # 同时同步 textarea#title.value 并触发 input。两者缺一，重载后标题就空。
        js = r'''
(function(){
  var t = %s;
  var pms = document.querySelectorAll('.ProseMirror'), pm = null;
  for (var i = 0; i < pms.length; i++) {
    var par = pms[i].parentElement;
    if (par && (par.className || '').indexOf('title-editor') !== -1) pm = pms[i];
  }
  if (!pm) return 'NO_TITLE_PM';
  pm.focus();
  var r = document.createRange(); r.selectNodeContents(pm);
  var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  document.execCommand('insertText', false, t);
  var ta = document.getElementById('title');
  if (ta) { ta.value = t; ta.dispatchEvent(new Event('input', {bubbles:true})); }
  return 'TITLE_SET:' + pm.innerText.slice(0, 20);
})()
''' % json.dumps(content['title'])
        rc, out, err = eval_js(args, js)
        print('   ', out[:80])
        if 'TITLE_SET' not in out:
            print('   ⚠️ 标题可能没设上，保存后请复查')

    # ---- 6) 保存为草稿 ----
    print('⑥ 保存为草稿 …')
    rc, out, err = ba(args, ['click', '--selector', '#js_submit button'], timeout=180)
    time.sleep(6)
    rc2, out2, _ = eval_js(args, "location.href")
    print('   URL:', out2.strip()[-120:])
    import re
    m = re.search(r'appmsgid=(\d+)', out2)
    if m:
        print('✅ 已保存为草稿，appmsgid =', m.group(1))
        appmsgid = m.group(1)
    else:
        print('⚠️ 未见 appmsgid，请到草稿箱确认是否保存成功')
        return 0

    # ---- 7) 自动校验（别靠肉眼）----
    print('⑦ 自动校验 …')
    rc, out, err = eval_js(args, JS_VERIFY)
    try:
        v = json.loads(out.split('\n')[-1])
    except Exception:
        print('   ⚠️ 校验解析失败:', out[:160])
        return 0
    problems = []
    if v.get('gaps'):
        problems.append('外框接缝有 %s px 的缝（应为 0）——多半是外框样式漏了 margin:0'
                        % '/'.join(str(g) for g in v['gaps'][:5]))
    if len(v.get('lefts', [])) > 1:
        problems.append('各段左边距不一致 %s，框会左右错位' % v['lefts'])
    if len(v.get('widths', [])) > 1:
        problems.append('各段宽度不一致 %s' % v['widths'])
    if v.get('stillData'):
        problems.append('%d 张图仍是 data: 未传完' % v['stillData'])
    if v.get('imgs') and v.get('cdn') != v.get('imgs'):
        problems.append('图片 CDN 数 %s ≠ 总数 %s' % (v.get('cdn'), v.get('imgs')))
    if not v.get('hasEnd'):
        problems.append('没找到文末 END 线')
    gals = v.get('galleries') or []
    for i, g in enumerate(gals):
        if not g.get('ok'):
            problems.append('第 %d 个横滑相册滑不动（可见 %s / 滚动 %s）——多半是行宽或项宽没配套'
                            % (i + 1, g.get('vis'), g.get('scroll')))
    print('   外框 %s 段 / 接缝 %s / 图 %s（CDN %s）/ 图注 %s / 分节标题 %s'
          % (v.get('frames'), v.get('gaps') or '无', v.get('imgs'), v.get('cdn'),
             v.get('captions'), v.get('headings')))
    if gals:
        print('   横滑相册 %d 组：%s'
              % (len(gals), ', '.join('%d 张(%s)' % (g['n'], '可滑' if g['ok'] else '不可滑') for g in gals)))
    if problems:
        print('   ❌ 发现问题：')
        for p in problems:
            print('      -', p)
    else:
        print('   ✅ 校验通过：无断缝、图片齐、结构完整')
    print('   草稿地址: https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit'
          '&action=edit&type=77&appmsgid=%s&token=%s&lang=zh_CN' % (appmsgid, args.token))
    return 0


if __name__ == '__main__':
    sys.exit(main())
