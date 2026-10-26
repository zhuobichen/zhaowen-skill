#!/usr/bin/env node
/**
 * tieba-cli —— 百度贴吧直连命令行（不依赖浏览器、不依赖签名）
 *
 * 原理：贴吧的 PC 接口（/c/f/...）每个请求都要按参数计算 sign，逆向成本高；
 * 但**移动版页面 /mo/q/m?kw=吧名 是服务端渲染的完整 HTML**（实测约 385KB），
 * 帖子列表直接在里面，不需要 sign。所以这里走移动版页面 + HTML 解析。
 *
 * 唯一前提：登录态。不带 cookie 直连只会拿到 ~2.5KB 的拦截页。
 *
 * Cookie 来源（按优先级）：
 *   1. 环境变量 TIEBA_COOKIE（可以是 "BDUSS=xxx" 或只写 xxx）
 *   2. 文件 %USERPROFILE%\.tieba-cookie（同样两种写法都认）
 *
 * 用法：
 *   node tieba.mjs posts --kw 显卡 [--pn 0] [--json]
 *   node tieba.mjs thread --tid 11085093277 [--pn 1] [--json]
 *   node tieba.mjs posts --kw 显卡 --dump raw.html
 */

import fs from 'fs';
import os from 'os';
import path from 'path';

const MOBILE_UA =
  'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36';

// ── cookie ──────────────────────────────────────────────

function loadCookie() {
  const fromEnv = process.env.TIEBA_COOKIE;
  if (fromEnv && fromEnv.trim()) return normalizeCookie(fromEnv.trim());

  const file = path.join(os.homedir(), '.tieba-cookie');
  try {
    const raw = fs.readFileSync(file, 'utf-8').replace(/^\uFEFF/, '').trim();
    if (raw) return normalizeCookie(raw);
  } catch {}
  return null;
}

/** 允许用户只粘贴 BDUSS 的值，也允许粘贴整串 cookie */
function normalizeCookie(raw) {
  const text = raw.replace(/\s*\n\s*/g, '; ').trim();
  if (/BDUSS\s*=/i.test(text)) return text;
  return `BDUSS=${text}`;
}

// ── 请求 ────────────────────────────────────────────────

async function fetchHtml(pathname) {
  const cookie = loadCookie();
  if (!cookie) {
    throw new Error(
      '缺少登录态。把 BDUSS 写进 %USERPROFILE%\\.tieba-cookie，或设环境变量 TIEBA_COOKIE。\n' +
      '  取值：浏览器 F12 → Application → Cookies → tieba.baidu.com → BDUSS（值是 httpOnly）'
    );
  }
  const url = pathname.startsWith('http') ? pathname : `https://tieba.baidu.com${pathname}`;
  const resp = await fetch(url, {
    headers: {
      'User-Agent': MOBILE_UA,
      'Cookie': cookie,
      'Referer': 'https://tieba.baidu.com/',
      'Accept': 'text/html,application/xhtml+xml',
      'Accept-Language': 'zh-CN,zh;q=0.9'
    }
  });
  const html = await resp.text();

  // 被反爬拦住时，百度会返回一个很小的验证页
  if (html.length < 5000) {
    const blocked = /安全验证|验证码|请输入验证码|wappass|网络不给力/i.test(html);
    throw new Error(
      blocked
        ? `被百度安全验证拦截（返回 ${html.length} 字节）。稍后重试，或换个网络/走代理。`
        : `返回内容过短（${html.length} 字节），可能是 cookie 失效或地址不对。`
    );
  }
  return html;
}

// ── 解析 ────────────────────────────────────────────────

const stripTags = (s) =>
  s.replace(/<script[\s\S]*?<\/script>/gi, ' ')
   .replace(/<[^>]+>/g, ' ')
   .replace(/&nbsp;/g, ' ')
   .replace(/&amp;/g, '&')
   .replace(/&lt;/g, '<')
   .replace(/&gt;/g, '>')
   .replace(/&quot;/g, '"')
   .replace(/\s+/g, ' ')
   .trim();

/** 吧页帖子列表：<li data-tid="…"> <a href="/p/tid…"> <div class="ti_title">… */
function parseThreadList(html) {
  const out = [];
  const re = /<li[^>]*class="[^"]*tl[^"]*"[^>]*data-tid="(\d+)"[\s\S]*?(?=<li[^>]*class="[^"]*tl|<\/ul>)/g;
  for (const m of html.matchAll(re)) {
    const block = m[0];
    const tid = m[1];
    const titleMatch = block.match(/<div class="ti_title"[^>]*>([\s\S]*?)<\/div>/);
    // 标题里常混着「置顶/精品」徽标 span，先剥掉再取文本
    const titleHtml = (titleMatch ? titleMatch[1] : '').replace(
      /<span[^>]*class="[^"]*ti_icon_[^"]*"[^>]*>[\s\S]*?<\/span>/g,
      ''
    );
    const title = stripTags(titleHtml);
    const isTop = /ti_icon_zhiding|置顶/.test(block);
    const isGood = /ti_icon_jinghua|精品/.test(block);
    // 作者与回复数：移动版在 li 里的 a/span 上，取能匹配到的
    const author = (block.match(/class="ti_author[^"]*"[^>]*>([\s\S]*?)<\//) || [])[1];
    const reply = (block.match(/class="ti_reply[^"]*"[^>]*>([\s\S]*?)<\//) || [])[1];
    out.push({
      tid,
      title,
      置顶: isTop,
      精品: isGood,
      作者: author ? stripTags(author) : undefined,
      回复: reply ? stripTags(reply) : undefined
    });
  }
  return out;
}

/** 帖子页：楼层内容（移动版 PB 结构 + PC 老结构都兼容） */
function parseThread(html) {
  const posts = [];

  // 移动版（bsk emulate 之后 / mo_device）：楼层在 div.comment-content 里
  const mobileBlocks = html.split(/<div[^>]*class="[^"]*\bcomment-content\b[^"]*"/).slice(1);
  for (const block of mobileBlocks) {
    const contentHtml =
      (block.match(/class="pb-text-wrapper[^"]*"[^>]*>([\s\S]*?)<\/span>\s*<\/span>/) ||
       block.match(/class="pb-text-wrapper[^"]*"[^>]*>([\s\S]*?)<\/div>/))?.[1] || '';
    const content = stripTags(contentHtml);
    if (!content) continue;

    const descHtml = (block.match(/class="comment-desc-left"[^>]*>([\s\S]*?)<\/div>/) || [])[1] || '';
    const descParts = [...descHtml.matchAll(/<span[^>]*>([\s\S]*?)<\/span>/g)].map((m) => stripTags(m[1]));
    const author = stripTags((block.match(/class="head-name[^"]*"[^>]*>([\s\S]*?)<\//) || [])[1] || '');

    posts.push({
      作者: author,
      楼层: descParts[0] || '',
      时间: descParts[1] || '',
      地区: descParts[2] || '',
      内容: content
    });
  }
  if (posts.length) return posts;

  // PC 老结构兜底
  for (const block of html.split(/<div[^>]*class="[^"]*\bl_post\b[^"]*"/).slice(1)) {
    const author = stripTags((block.match(/class="p_author_name[^"]*"[^>]*>([\s\S]*?)<\//) || [])[1] || '');
    const content = stripTags((block.match(/class="d_post_content[^"]*"[^>]*>([\s\S]*?)<\/div>/) || [])[1] || '');
    const time = stripTags((block.match(/class="p_date[^"]*"[^>]*>([\s\S]*?)<\//) || [])[1] || '');
    const floor = stripTags((block.match(/class="p_floor[^"]*"[^>]*>([\s\S]*?)<\//) || [])[1] || '');
    if (content) posts.push({ 作者: author, 楼层: floor, 时间: time, 内容: content });
  }
  return posts;
}

// ── 命令 ────────────────────────────────────────────────

function hasFlag(name) { return process.argv.includes('--' + name); }

function arg(name, def) {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
}

async function cmdPosts() {
  const kw = arg('kw');
  const fromFile = arg('file');
  if (!fromFile && !kw) throw new Error('缺少 --kw <吧名>（或用 --file <本地HTML> 离线解析）');

  let html;
  if (fromFile) {
    // 离线模式：解析已经存到本地的 HTML（例如用 bsk get-html 由已登录浏览器导出）
    html = fs.readFileSync(fromFile, 'utf-8');
  } else {
    const pn = arg('pn', '0');
    html = await fetchHtml(`/mo/q/m?kw=${encodeURIComponent(kw)}&pn=${pn}`);
    const dump = arg('dump');
    if (dump) {
      fs.writeFileSync(dump, html);
      console.log(`原始 HTML 已保存到 ${dump}（${html.length} 字节）`);
    }
  }

  const list = parseThreadList(html);
  if (hasFlag('json')) {
    console.log(JSON.stringify(list, null, 2));
    return;
  }
  const label = fromFile ? path.basename(fromFile) : `「${kw}」`;
  console.log(`贴吧 ${label} 帖子列表，共 ${list.length} 条`);
  for (const t of list) {
    const tags = [t.置顶 ? '[置顶]' : '', t.精品 ? '[精品]' : ''].join('');
    console.log(`  ${tags}${t.title}`);
    console.log(`     tid=${t.tid}`);
  }
}

async function cmdThread() {
  const tid = arg('tid');
  const fromFile = arg('file');
  if (!fromFile && !tid) throw new Error('缺少 --tid <帖子ID>（或用 --file <本地HTML> 离线解析）');

  let html;
  if (fromFile) {
    html = fs.readFileSync(fromFile, 'utf-8');
  } else {
    const pn = arg('pn', '1');
    html = await fetchHtml(`/p/${tid}?pn=${pn}&mo_device=1`);
  }

  const posts = parseThread(html);
  const pageTitle = ((html.match(/<title>([^<]*)<\/title>/) || [])[1] || '').replace(/-百度贴吧$/, '').trim();
  if (hasFlag('json')) {
    // 带上标题，方便下游把它当会话名（消费方：Ember 的 tieba 适配器）
    console.log(JSON.stringify({ tid: tid || null, 标题: pageTitle, 楼层: posts }, null, 2));
    return;
  }
  console.log(`帖子 ${tid || path.basename(fromFile)}${pageTitle ? ' · ' + pageTitle : ''} 解析到 ${posts.length} 层`);
  for (const p of posts.slice(0, 20)) {
    console.log(`\n[${p.楼层 || '-'}] ${p.作者 || '-'}  ${p.时间 || ''} ${p.地区 || ''}`);
    console.log(`  ${p.内容.slice(0, 200)}`);
  }
}

// ── 入口 ────────────────────────────────────────────────

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, '/').split('/').pop());
if (isMain) {
  const cmd = process.argv[2];
  try {
    if (cmd === 'posts') await cmdPosts();
    else if (cmd === 'thread') await cmdThread();
    else {
      console.log(`tieba-cli
用法:
  node tieba.mjs posts --kw <吧名> [--pn 0] [--json] [--dump raw.html]
  node tieba.mjs thread --tid <帖子ID> [--pn 1] [--json]

登录态: %USERPROFILE%\\.tieba-cookie 里放 BDUSS 值，或设 TIEBA_COOKIE`);
    }
  } catch (e) {
    console.error('错误: ' + e.message);
    process.exit(1);
  }
}

export { parseThreadList, parseThread, normalizeCookie };
