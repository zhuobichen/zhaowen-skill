#!/usr/bin/env node
/**
 * 每天定时归档一次（默认 00:00）。
 *
 * 为什么不是"来一封分一封"：白天新邮件留在收件箱你随时看得到，
 * 半夜统一归档，第二天进收件箱就是干净的。实时分拣反而要跑去文件夹里找新信。
 *
 * 两个模式：
 *   常驻（推荐，不需要管理员）：node daily.mjs --at=00:00
 *     进程自己算到下一个 00:00 的毫秒数，睡着等；跑完再等下一个。
 *   一次性（配计划任务）：node daily.mjs --at=00:00 --once
 *
 * 补跑：进程启动时如果发现"最近一次该跑的时间点已经过去了但没跑过"（比如半夜关机），
 *       会立刻补一次，不会漏掉那天。
 */
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadState, saveState } from "./state.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const ONCE = argv.includes("--once");
const NO_LLM = argv.includes("--no-llm");
const arg = (n, d) => {
  const hit = argv.find((a) => a.startsWith(`--${n}=`));
  return hit ? hit.split("=")[1] : d;
};
const AT = arg("at", "00:00");
const LIMIT = Number(arg("limit", 400));
const LOG = path.join(HERE, "daily.log");

function log(msg) {
  console.log(msg);
  try { fs.appendFileSync(LOG, `[${new Date().toISOString()}] ${msg}\n`, "utf8"); } catch {}
}

// ---------------------------------------------------------------- 时间
function parseAt(s) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(s.trim());
  if (!m) throw new Error(`--at 格式应为 HH:MM，收到 ${s}`);
  const h = Number(m[1]);
  const mi = Number(m[2]);
  if (h > 23 || mi > 59) throw new Error(`--at 时间不合法：${s}`);
  return { h, mi };
}
const { h, mi } = parseAt(AT);

/** 今天这个时间点（本地时区） */
function todayAt() {
  const d = new Date();
  d.setHours(h, mi, 0, 0);
  return d;
}
/** 最近一个"应该已经跑过"的时间点 */
function mostRecentSlot() {
  const t = todayAt();
  return new Date() >= t ? t : new Date(t.getTime() - 86400000);
}
function nextSlot() {
  const t = todayAt();
  return new Date() >= t ? new Date(t.getTime() + 86400000) : t;
}

// ---------------------------------------------------------------- 执行
let running = false;
function runSort(reason) {
  if (running) { log(`上一轮还没结束，跳过（${reason}）`); return; }
  running = true;
  const args = [path.join(HERE, "sort.mjs"), "--limit", String(LIMIT)];
  if (!NO_LLM) args.push("--llm", "--triage");
  log(`▶ 开始归档（${reason}）`);
  const child = spawn(process.execPath, args, { cwd: HERE, stdio: "inherit" });
  child.on("exit", (code) => {
    running = false;
    try {
      const st = loadState();
      st.lastDailyRun = new Date().toISOString();
      saveState(st);
    } catch {}
    log(`■ 归档结束 exit=${code}，生成 HTML 报告…`);
    // 归档完顺手出报告（纯代码，不调 AI）
    const rep = spawn(process.execPath, [path.join(HERE, "report.mjs")], { cwd: HERE, stdio: "inherit" });
    rep.on("exit", (rc) => log(`■ 报告完成 exit=${rc}，下次归档：${nextSlot().toLocaleString("zh-CN")}`));
    rep.on("error", (e) => log(`✗ 生成报告失败：${e.message}`));
  });
  child.on("error", (e) => { running = false; log(`✗ 拉起归档进程失败：${e.message}`); });
}

// ---------------------------------------------------------------- 主流程
const st0 = loadState();
const lastRun = st0.lastDailyRun ? new Date(st0.lastDailyRun) : null;
const slot = mostRecentSlot();

log(`定时归档：每天 ${AT}（上限 ${LIMIT} 封/次，${NO_LLM ? "仅规则" : "规则+Jev 兜底"}）`);
log(`上次运行：${lastRun ? lastRun.toLocaleString("zh-CN") : "(无记录)"}；最近应跑时间点：${slot.toLocaleString("zh-CN")}`);

if (!lastRun || lastRun < slot) {
  log(`检测到该跑但没跑过（可能是半夜关机），先补一次`);
  runSort("补跑");
} else if (ONCE) {
  log("今天这一轮已经跑过了，--once 模式直接退出");
}

if (ONCE) {
  // 给 --once 留出子进程跑完的时间
  const t = setInterval(() => { if (!running) { clearInterval(t); process.exit(0); } }, 1000);
} else {
  const scheduleNext = () => {
    const ms = Math.max(1000, nextSlot().getTime() - Date.now());
    log(`下一次归档：${new Date(Date.now() + ms).toLocaleString("zh-CN")}（${Math.round(ms / 60000)} 分钟后）`);
    setTimeout(() => {
      runSort(`定时 ${AT}`);
      scheduleNext();
    }, ms);
  };
  scheduleNext();
  process.on("SIGINT", () => { log("收到 Ctrl-C，退出定时器"); process.exit(0); });
}
