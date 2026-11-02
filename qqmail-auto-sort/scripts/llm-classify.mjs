/**
 * LLM 分类器 —— 默认走 TypeSafe Jev（System One 决策模型），可回落到普通 chat 模型。
 *
 * Jev 的调用形状（实测可用）：
 *   POST https://api.302ai.cn/typesafeai/v1/systemone
 *   { model: "jev-latest", state: "<多封邮件拼成的编号文本>", questions: { m0: {type:"choice", instructions, criteria}, m1: {...} } }
 *   → { answers: { m0: {type:"choice", choice:"auth", probabilities:{...}, confidence:0.95} }, usage }
 * 特点：一次调用并行回答多个问题（每封一个问题），不产生自然语言，类别不可能跑到 schema 外。
 *
 * 分类只负责“判类”，搬邮件仍由 sort.mjs 的 COPY→核对→删除 完成。
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { CATS } from "./categories.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CFG_PATH = path.join(HERE, "llm.config.json");
const CACHE_PATH = path.join(HERE, "llm-cache.json");

export const VALID_KEYS = CATS.map((c) => c.key); // 含 other
const FOLDER_KEYS = CATS.filter((c) => c.key !== "other").map((c) => c.key);

const DEFAULT_CFG = {
  shape: "jev",
  baseUrl: "https://api.302ai.cn/typesafeai/v1/systemone",
  apiKey: "",
  model: "jev-latest",
  batchSize: 8,
  timeoutMs: 60000,
  minConfidence: 0.6, // 低于这个置信度就单封重问一次；还低就回落规则
  chat: {
    // 备用通道：Jev 限流/欠费时用
    baseUrl: "https://api.302ai.cn/v1",
    model: "deepseek-chat",
  },
};

export function loadLlmConfig() {
  let cfg = JSON.parse(JSON.stringify(DEFAULT_CFG));
  if (fs.existsSync(CFG_PATH)) {
    try {
      const j = JSON.parse(fs.readFileSync(CFG_PATH, "utf8"));
      cfg = { ...cfg, ...j, chat: { ...cfg.chat, ...(j.chat ?? {}) } };
    } catch {}
  }
  if (process.env.LLM_API_KEY) cfg.apiKey = process.env.LLM_API_KEY;
  if (process.env.LLM_MODEL) cfg.model = process.env.LLM_MODEL;
  return cfg;
}

// ---------------------------------------------------------------- 缓存（同封不重复花钱）
let cache = null;
const loadCache = () => (cache ??= (() => { try { return JSON.parse(fs.readFileSync(CACHE_PATH, "utf8")); } catch { return {}; } })());
const saveCache = () => { try { fs.writeFileSync(CACHE_PATH, JSON.stringify(cache), "utf8"); } catch {} };

export function cacheKey(m) {
  if (m.msgId) return m.msgId;
  const addr = (String(m.from || "").match(/<([^>]+)>/)?.[1] || m.from || "").toLowerCase();
  return `S|${(m.subject ?? "").trim()}|${m.date || ""}|${addr}`;
}

// ---------------------------------------------------------------- 类别说明
const CRITERIA = Object.fromEntries(CATS.map((c) => [c.key, `${c.label}：${c.desc}`]));

function stateText(batch) {
  return batch
    .map((m, i) => `[#${i}] from: ${m.from} | subject: ${String(m.subject ?? "").slice(0, 120)} | date: ${m.date || "?"}`)
    .join("\n");
}

function questionsFor(batch, opts = {}) {
  const q = {};
  batch.forEach((_, i) => {
    q[`m${i}`] = {
      type: "choice",
      instructions:
        `state 中标记 [#${i}] 的那封邮件，应该归到哪个文件夹？` +
        `判定顺序：验证码/登录类优先于营销；平台营销邮件里夹带的 "verify your email" 也算验证码类；拿不准就选 other。`,
      criteria: CRITERIA,
    };
  });
  return q;
}

async function post(cfg, url, payload) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), cfg.timeoutMs);
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${cfg.apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: ctrl.signal,
    });
    const text = await r.text();
    if (r.status !== 200) throw new Error(`HTTP ${r.status}: ${text.slice(0, 160)}`);
    return JSON.parse(text);
  } finally {
    clearTimeout(timer);
  }
}

async function askJev(cfg, batch) {
  const j = await post(cfg, cfg.baseUrl, {
    model: cfg.model,
    state: stateText(batch),
    questions: questionsFor(batch),
  });
  const out = new Map();
  batch.forEach((_, i) => {
    const a = j.answers?.[`m${i}`];
    const cat = a?.choice;
    if (cat && VALID_KEYS.includes(cat)) out.set(i, { cat, conf: Number(a.confidence ?? 0.5) });
  });
  return { out, usage: j.usage, model: j.model };
}

async function askChat(cfg, batch) {
  const system = `你是邮件分拣员。给你一批邮件头，为每封选出唯一目标文件夹。
只能从这些 key 里选：${FOLDER_KEYS.join(", ")}, other
类别含义：\n${CATS.map((c) => `- ${c.key}: ${c.label} —— ${c.desc}`).join("\n")}
判定顺序：验证码/登录类优先于营销（营销邮件里的 "verify your email" 也算验证码类）；工资/发票/订单归 money；审稿投稿会议归 acad；招聘竞赛学校归 job；游戏商店归 game；平台系统通知归 notice；自家项目协作归 work；CI 通知归 ci；自己发自己的日报归 daily；贷款征信诈骗群发归 spam；拿不准用 other。
只输出 JSON：{"items":[{"i":序号,"cat":"key","conf":0.0~1.0}]}`;
  const rows = batch.map((m, i) => ({ i, from: m.from, subject: m.subject, date: m.date || "" }));
  const j = await post(cfg, cfg.chat.baseUrl.replace(/\/$/, "") + "/chat/completions", {
    model: cfg.chat.model,
    temperature: 0,
    response_format: { type: "json_object" },
    messages: [
      { role: "system", content: system },
      { role: "user", content: JSON.stringify(rows) },
    ],
  });
  const content = j.choices?.[0]?.message?.content ?? "";
  let parsed;
  try { parsed = JSON.parse(content); } catch {
    const m = content.match(/\{[\s\S]*\}/);
    parsed = m ? JSON.parse(m[0]) : null;
  }
  const items = parsed?.items ?? (Array.isArray(parsed) ? parsed : []);
  const out = new Map();
  for (const it of items) {
    const i = Number(it.i);
    if (!Number.isFinite(i) || !batch[i]) continue;
    if (!VALID_KEYS.includes(it.cat)) continue;
    out.set(i, { cat: it.cat, conf: Number(it.conf ?? 0.5) });
  }
  return { out, usage: j.usage, model: j.model || cfg.chat.model };
}

/**
 * 批量判类（带缓存、低置信重问、失败回落）。
 * @param {Array<{msgId?,from,subject,date}>} items
 * @returns {Promise<{map: Map<number,{cat,conf,cached?}>, stats:{calls,cost,tokens,model}}>}
 */
export async function classifyWithLlm(items, opts = {}) {
  const cfg = loadLlmConfig();
  if (!cfg.apiKey) throw new Error("llm.config.json 缺少 apiKey");
  const bs = Math.max(1, Math.min(20, opts.batchSize ?? cfg.batchSize ?? 8));
  const minConf = opts.minConfidence ?? cfg.minConfidence ?? 0.6;
  const c = loadCache();
  const map = new Map();
  const stats = { calls: 0, cost: 0, tokens: 0, model: null, cached: 0, retried: 0 };

  const pending = [];
  items.forEach((m, i) => {
    const hit = c[cacheKey(m)];
    if (hit?.cat && VALID_KEYS.includes(hit.cat)) {
      map.set(i, { cat: hit.cat, conf: hit.conf ?? 0.5, cached: true });
      stats.cached++;
    } else pending.push(i);
  });

  const ask = async (batch, idxs) => {
    let res;
    try {
      res = cfg.shape === "jev" ? await askJev(cfg, batch) : await askChat(cfg, batch);
    } catch (e) {
      if (cfg.shape === "jev" && !opts.noFallback) {
        if (opts.verbose) console.log(`  ! Jev 失败（${e.message.slice(0, 60)}），本次改用 chat 通道`);
        res = await askChat(cfg, batch);
      } else throw e;
    }
    stats.calls++;
    stats.model = res.model;
    stats.cost += res.usage?.cost ?? 0;
    stats.tokens += res.usage?.input_tokens ?? 0;
    for (const [k, v] of res.out) {
      const gi = idxs[k];
      map.set(gi, v);
      c[cacheKey(items[gi])] = { cat: v.cat, conf: v.conf, ts: Date.now() };
    }
    return res.out;
  };

  // 主批次
  for (let p = 0; p < pending.length; p += bs) {
    const idxs = pending.slice(p, p + bs);
    await ask(idxs.map((i) => items[i]), idxs);
  }

  // 低置信 / 缺失 → 单封重问一次
  for (const i of pending) {
    const got = map.get(i);
    if (got && got.conf >= minConf) continue;
    stats.retried++;
    try {
      const single = await ask([items[i]], [i]);
      if (!single.size) map.delete(i);
    } catch { map.delete(i); }
  }

  if (stats.calls) saveCache();
  return { map, stats };
}
