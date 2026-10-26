#!/usr/bin/env node
/**
 * zhihu-cli —— 知乎读取工具（离线解析）
 *
 * 知乎的接口（/api/v4/...）需要 x-zse-96 签名，逆向成本高；但问题页的 HTML 里内嵌了
 * 完整的初始状态 <script id="js-initialData">…</script>，包含标题、回答数、首屏答案。
 * 所以走"浏览器取 HTML（已登录）→ 本地解析 initialData"，不需要签名、不导出 cookie。
 *
 * 用法：
 *   node zhihu.mjs question --file q.html [--json] [--full]
 *   node zhihu.mjs question --id 2098047112466227298 [--json]   # 需要登录态，直连会被拦
 */

import fs from 'fs';

const stripHtml = (s) =>
  String(s || '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<figure[\s\S]*?<\/figure>/gi, '[图片]')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\n{3,}/g, '\n\n')
    .trim();

/** 从 HTML 里取出 js-initialData 并解析 */
function parseInitialData(html) {
  const m = html.match(/<script id="js-initialData"[^>]*>([\s\S]*?)<\/script>/);
  if (!m) throw new Error('页面里没有 js-initialData（可能取到的是空壳或验证页）');
  return JSON.parse(m[1]);
}

/** 解析问题页：标题、回答数、首屏答案 */
function parseQuestion(html) {
  const data = parseInitialData(html);
  const state = data.initialState || {};
  const entities = state.entities || {};

  const questions = entities.questions || {};
  const q = Object.values(questions)[0] || {};
  const answers = entities.answers || {};

  // answers 可能挂在 question.answers 里，也可能在顶层 entities
  const list = Object.values(answers).map((a) => {
    const author = a.author || {};
    return {
      答主: author.name || '',
      赞同: a.voteupCount ?? a.voteup_count ?? 0,
      评论: a.commentCount ?? a.comment_count ?? 0,
      时间: a.createdTime ? new Date(a.createdTime * 1000).toISOString().slice(0, 10) : '',
      回答ID: a.id,
      内容: stripHtml(a.content),
      摘要: stripHtml(a.excerpt)
    };
  }).sort((x, y) => y.赞同 - x.赞同);

  return {
    问题ID: q.id,
    标题: q.title || '',
    回答数: q.answerCount ?? q.answer_count ?? null,
    关注数: q.followerCount ?? q.follower_count ?? null,
    浏览数: q.visitCount ?? q.visit_count ?? null,
    详情: stripHtml(q.detail).slice(0, 300),
    首屏答案数: list.length,
    答案: list
  };
}

// ── 入口 ────────────────────────────────────────────────

function arg(name, def) {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
}
const hasFlag = (n) => process.argv.includes(`--${n}`);

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, '/').split('/').pop());
if (isMain) {
  try {
    const cmd = process.argv[2];
    const file = arg('file');
    if (cmd !== 'question' || !file) {
      console.log(`zhihu-cli
用法:
  node zhihu.mjs question --file <本地HTML> [--json] [--full]

提示: HTML 用 zhihu.ps1 取（浏览器已登录态），本 CLI 只做离线解析`);
      process.exit(file ? 1 : 0);
    }
    const html = fs.readFileSync(file, 'utf-8');
    const q = parseQuestion(html);

    if (hasFlag('json')) {
      console.log(JSON.stringify(q, null, 2));
    } else {
      console.log(`问题 ${q.问题ID}`);
      console.log(`  ${q.标题}`);
      console.log(`  回答 ${q.回答数} · 关注 ${q.关注数} · 浏览 ${q.浏览数}`);
      if (q.详情) console.log(`  详情: ${q.详情}`);
      console.log(`\n首屏 ${q.首屏答案数} 条回答：`);
      for (const a of q.答案) {
        console.log(`\n── ${a.答主}  👍${a.赞同}  💬${a.评论}  ${a.时间}`);
        const text = hasFlag('full') ? a.内容 : a.内容.slice(0, 300);
        console.log(text.split('\n').map((l) => '   ' + l).join('\n'));
        if (!hasFlag('full') && a.内容.length > 300) console.log('   …');
      }
    }
  } catch (e) {
    console.error('错误: ' + e.message);
    process.exit(1);
  }
}

export { parseQuestion, parseInitialData, stripHtml };
