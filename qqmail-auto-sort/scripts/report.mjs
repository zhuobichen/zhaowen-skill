#!/usr/bin/env node
/**
 * 生成归档报告（纯代码，不调 AI）。
 *
 * 数据源：last-run.json（sort.mjs 每轮写一份）
 * 产物：report/YYYY-MM-DD.html —— 单文件、内联 CSS、不依赖外网，双击就能看
 *
 * 用法：
 *   node report.mjs                    # 用最近的 last-run.json 生成今天的报告
 *   node report.mjs --open             # 生成并打开
 *   node report.mjs --file=x.json      # 指定数据源
 *   node report.mjs --all              # 把 report/ 下所有历史汇总成一个总览页
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
import { CATS } from "./categories.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.join(HERE, "report");
const argv = process.argv.slice(2);
const OPEN = argv.includes("--open");
const fileArg = argv.find((a) => a.startsWith("--file="))?.split("=")[1];

const esc = (s) =>
  String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

const fmtTime = (iso) => {
  if (!iso) return "?";
  const d = new Date(iso);
  const p = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
};

function loadRun() {
  const p = fileArg || path.join(HERE, "last-run.json");
  if (fileArg) return JSON.parse(fs.readFileSync(p, "utf8"));

  // 优先读「当日汇总」（同一天跑过多次就合并），没有就退回最近一次
  const dayGuess = new Date().toISOString().slice(0, 10);
  const dayFile = path.join(HERE, "report", "data", `${dayGuess}.json`);
  if (fs.existsSync(dayFile)) {
    try {
      const d = JSON.parse(fs.readFileSync(dayFile, "utf8"));
      return mergeRuns(d);
    } catch {}
  }
  if (!fs.existsSync(p)) {
    console.error(`找不到 ${p}，先跑一次 node sort.mjs`);
    process.exit(2);
  }
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

/** 把同一天的多次运行合并成一份（按 主题+日期 去重，避免手动补跑把同一封算两次） */
function mergeRuns(dayFile) {
  const runs = dayFile.runs ?? [];
  if (!runs.length) return { ts: new Date().toISOString(), movedTotal: 0, movedByLabel: {}, kept: [] };
  const seen = new Set();
  const movedByLabel = {};
  let kept = [];
  const llm = { calls: 0, cost: 0, cached: 0, model: null };
  const srcCount = { strong: 0, medium: 0, low: 0 };
  let scanned = 0;
  for (const r of runs) {
    scanned += r.scanned ?? 0;
    for (const [label, items] of Object.entries(r.movedByLabel ?? {})) {
      for (const it of items) {
        const k = `${it.subject}|${it.date}|${label}`;
        if (seen.has(k)) continue;
        seen.add(k);
        (movedByLabel[label] ??= []).push(it);
      }
    }
    if (r.kept?.length) kept = r.kept;
    if (r.llm) {
      llm.calls += r.llm.calls ?? 0;
      llm.cost += Number(r.llm.cost ?? 0);
      llm.cached += r.llm.cached ?? 0;
      llm.model = r.llm.model ?? llm.model;
    }
    if (r.srcCount) {
      srcCount.strong += r.srcCount.strong ?? 0;
      srcCount.medium += r.srcCount.medium ?? 0;
      srcCount.low += (r.srcCount.weak ?? 0) + (r.srcCount.none ?? 0);
    }
  }
  const last = runs[runs.length - 1];
  const total = Object.values(movedByLabel).reduce((n, a) => n + a.length, 0);
  return {
    ts: last.ts,
    runsCount: runs.length,
    inboxBefore: runs[0].inboxBefore,
    inboxAfter: last.inboxAfter,
    scanned,
    movedTotal: total,
    movedByLabel,
    kept,
    llm: llm.calls ? llm : null,
    srcCount: srcCount.strong || srcCount.medium ? { ...srcCount, weak: 0, none: srcCount.low } : last.srcCount,
  };
}

function render(run) {
  const moved = run.movedByLabel ?? {};
  const entries = CATS.map((c) => ({ ...c, items: moved[c.label] ?? [] })).filter((c) => c.items.length);
  const total = run.movedTotal ?? entries.reduce((n, c) => n + c.items.length, 0);
  const max = Math.max(1, ...entries.map((c) => c.items.length));
  const kept = run.kept ?? [];
  const llm = run.llm;
  const day = (run.ts || new Date().toISOString()).slice(0, 10);

  const rows = entries
    .map(
      (c) => `
      <tr>
        <td><a href="#${esc(c.key)}">${esc(c.label)}</a></td>
        <td class="num">${c.items.length}</td>
        <td class="bar"><span style="width:${Math.round((c.items.length / max) * 100)}%"></span></td>
        <td class="pct">${total ? ((c.items.length / total) * 100).toFixed(1) : 0}%</td>
      </tr>`
    )
    .join("");

  const sections = entries
    .map(
      (c) => `
    <section id="${esc(c.key)}">
      <h2>${esc(c.label)} <small>${c.items.length} 封</small></h2>
      <p class="desc">${esc(c.desc)}</p>
      <table class="items">
        <thead><tr><th style="width:88px">日期</th><th>主题</th><th style="width:34%">发件人</th></tr></thead>
        <tbody>
        ${c.items
          .map(
            (i) => `<tr><td class="dim">${esc(i.date || "")}</td><td>${esc(i.subject || "(无主题)")}</td><td class="dim">${esc(i.from || "")}</td></tr>`
          )
          .join("\n        ")}
        </tbody>
      </table>
    </section>`
    )
    .join("");

  const keptHtml = kept.length
    ? `<section id="kept"><h2>收件箱留存 <small>${kept.length} 封</small></h2>
       <p class="desc">规则和模型都判为「人说人话」的邮件，故意不动，等你亲手处理。</p>
       <table class="items"><thead><tr><th style="width:88px">日期</th><th>主题</th><th style="width:34%">发件人</th></tr></thead><tbody>
       ${kept.map((i) => `<tr><td class="dim">${esc(i.date || "")}</td><td>${esc(i.subject || "(无主题)")}</td><td class="dim">${esc(i.from || "")}</td></tr>`).join("\n       ")}
       </tbody></table></section>`
    : "";

  const llmLine = llm
    ? `调用 <b>${llm.calls}</b> 次 · 成本 <b>$${Number(llm.cost ?? 0).toFixed(6)}</b> · 模型 <code>${esc(llm.model ?? "-")}</code>` +
      (llm.cached ? ` · 缓存命中 ${llm.cached}` : "")
    : "本次未调用模型（规则全包）";

  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>邮件归档报告 ${day}</title>
<style>
  :root{--fg:#1f2328;--dim:#6b7280;--line:#e5e7eb;--bg:#f7f8fa;--accent:#2f6feb;--ok:#1a7f37}
  *{box-sizing:border-box}
  body{margin:0;padding:32px 20px 64px;background:var(--bg);color:var(--fg);
       font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
  .wrap{max-width:980px;margin:0 auto}
  header{background:#fff;border:1px solid var(--line);border-radius:12px;padding:22px 26px;margin-bottom:20px}
  h1{margin:0 0 6px;font-size:21px}
  .sub{color:var(--dim);font-size:13px}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0 0}
  .card{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
  .card .k{font-size:12px;color:var(--dim)}
  .card .v{font-size:22px;font-weight:600;margin-top:2px}
  .card .v small{font-size:12px;font-weight:400;color:var(--dim)}
  h2{font-size:16px;margin:26px 0 4px}
  h2 small{color:var(--dim);font-weight:400;font-size:12px;margin-left:6px}
  .desc{color:var(--dim);font-size:12px;margin:0 0 10px}
  table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:10px;overflow:hidden}
  th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
  th{background:#fafbfc;font-size:12px;color:var(--dim);font-weight:600}
  tbody tr:last-child td{border-bottom:0}
  td.num{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
  td.pct{text-align:right;color:var(--dim);font-variant-numeric:tabular-nums}
  td.bar{padding:9px 12px}
  td.bar span{display:block;height:8px;border-radius:5px;background:linear-gradient(90deg,#9cc2ff,#2f6feb)}
  td.dim{color:var(--dim);font-size:13px}
  a{color:var(--accent);text-decoration:none}
  code{background:#eef1f5;padding:1px 5px;border-radius:4px;font-size:12px}
  footer{margin-top:32px;color:var(--dim);font-size:12px;text-align:center}
  .stat{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--dim);margin-top:10px}
  @media (prefers-color-scheme:dark){
    :root{--fg:#e6edf3;--dim:#8b949e;--line:#30363d;--bg:#0d1117;--accent:#58a6ff}
    header,table{background:#161b22}
    th{background:#1c2128}
    code{background:#21262d}
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>邮件归档报告 · ${day}</h1>
    <div class="sub">生成时间 ${esc(fmtTime(run.ts))} · 规则优先、Jev 兜底、纯代码搬邮件</div>
    <div class="cards">
      <div class="card"><div class="k">本次归档</div><div class="v">${total} <small>封</small></div></div>
      <div class="card"><div class="k">收件箱</div><div class="v">${run.inboxBefore ?? "?"} <small>→</small> ${run.inboxAfter ?? "?"}</div></div>
      <div class="card"><div class="k">扫描（增量）</div><div class="v">${run.scanned ?? "-"} <small>封</small></div></div>
      <div class="card"><div class="k">留在收件箱</div><div class="v">${kept.length} <small>封</small></div></div>
    </div>
    <div class="stat">
      <span>${llmLine}</span>
      ${run.srcCount ? `<span>规则把握度：strong ${run.srcCount.strong} / medium ${run.srcCount.medium} / weak ${run.srcCount.weak} / none ${run.srcCount.none}</span>` : ""}
    </div>
  </header>

  ${
    entries.length
      ? `<h2>分类汇总</h2>
  <table>
    <thead><tr><th>文件夹</th><th class="num">封数</th><th style="width:42%">占比</th><th class="pct" style="width:64px">比例</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`
      : `<p class="desc">本次没有归档任何邮件${run.note ? `（${esc(run.note)}）` : ""}。</p>`
  }

  ${sections}
  ${keptHtml}

  <footer>由 report.mjs 生成 · 数据来自 last-run.json · 分类规则见 categories.mjs</footer>
</div>
</body>
</html>`;
}

const run = loadRun();
fs.mkdirSync(OUT_DIR, { recursive: true });
const day = (run.ts || new Date().toISOString()).slice(0, 10);
const out = path.join(OUT_DIR, `${day}.html`);
fs.writeFileSync(out, render(run), "utf8");
console.log(`报告已生成：${out}`);
console.log(`  归档 ${run.movedTotal ?? 0} 封；收件箱 ${run.inboxBefore ?? "?"} → ${run.inboxAfter ?? "?"}`);

if (OPEN) {
  try { execFileSync("cmd", ["/c", "start", "", out], { stdio: "ignore" }); } catch {}
}
