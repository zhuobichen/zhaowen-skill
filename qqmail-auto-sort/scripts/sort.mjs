#!/usr/bin/env node
/**
 * QQ 邮箱自动分类（每日跑一次即可）
 *
 * 安全设计（上次批量 MOVE 出事的教训）：
 *   1. 不用 MOVE。用 COPY，逐封执行，检查返回值（imapflow 失败时返回 false，不抛异常）。
 *   2. 用**另一条独立连接**在目标文件夹按 Message-ID 核对，确认副本真的在。
 *   3. 只对「核对到位」的邮件在 INBOX 里 EXPUNGE —— 最坏情况是留下重复，绝不丢信。
 *   4. 幂等：目标文件夹里已有同 Message-ID 的，不再复制，只做核对 + 清理原件。
 *   5. 失败率 > 30% 直接中止；每次有硬上限；不并发。
 *
 * 用法：
 *   node sort.mjs               # 执行（自动分类收件箱）
 *   node sort.mjs --dry         # 预览：只统计「需复制 / 已在目标 / 留在收件箱」
 *   node sort.mjs --selftest    # 自检链路（复制一封到临时文件夹→核对→删副本，不碰原件）
 *   node sort.mjs --limit=500   # 本次最多处理多少封（默认 200）
 *   node sort.mjs --days=3      # 只处理最近 3 天的
 *   node sort.mjs --verbose
 */
import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { classify, classifyDetail, needsModel, CATS } from "./categories.mjs";
import { classifyWithLlm } from "./llm-classify.mjs";
import { loadState, saveState, folderCache, setFolderCache } from "./state.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PROJ = (process.env.QQMAIL_MCP_PROJ || "D:/github_project/ZhaoWen_GitHub维护/zhaowen-mcp/qqmail-mcp");
const require = createRequire(PROJ + "/package.json");
const { ImapFlow } = require("imapflow");

// ---------------------------------------------------------------- 参数
const argv = process.argv.slice(2);
const DRY = argv.includes("--dry");
const SELFTEST = argv.includes("--selftest");
const VERBOSE = argv.includes("--verbose");
// --rescan：忽略 UID 水位线，全量重扫（改了规则、或怀疑漏了邮件时用）
const RESCAN = argv.includes("--rescan");
const ST = loadState();
// --llm：用 TypeSafe Jev（llm.config.json 里 shape=jev）判类，规则退化为兜底
const LLM = argv.includes("--llm") || argv.includes("--jev");
// --triage：两段式 —— 规则有把握的直接定，只有 weak/none 才送 Jev（推荐，配 --llm 用）
const TRIAGE = argv.includes("--triage");
const argNum = (name, dflt) => {
  const hit = argv.find((a) => a.startsWith(`--${name}=`));
  return hit ? Number(hit.split("=")[1]) : dflt;
};
const LIMIT = argNum("limit", 200);
const DAYS = argNum("days", 0);
const PER_COPY_DELAY = argNum("delay", 120);

// ---------------------------------------------------------------- 凭据
function loadCreds() {
  const local = path.join(HERE, "qqmail.config.json");
  if (fs.existsSync(local)) {
    const c = JSON.parse(fs.readFileSync(local, "utf8"));
    return { user: c.user, pass: (process.env.QQMAIL_AUTH_CODE || c.authCode || "").trim() };
  }
  const cfg = JSON.parse(fs.readFileSync(path.join(os.homedir(), ".claude.json"), "utf8"));
  const env = cfg?.mcpServers?.["qqmail-mcp"]?.env ?? {};
  return {
    user: (env.QQMAIL_USER || "").trim(),
    pass: (process.env.QQMAIL_AUTH_CODE || env.QQMAIL_AUTH_CODE || "").trim(),
  };
}

function makeClient(user, pass) {
  return new ImapFlow({
    host: "imap.qq.com",
    port: 993,
    secure: true,
    auth: { user, pass },
    logger: false,
    greetingTimeout: 20000,
    socketTimeout: 600000, // QQ 上逐封 EXPUNGE 很慢，别让长连接被 3 分钟的空闲超时掐掉
    maxIdleTime: 600000,
  });
}

/**
 * 连接自杀恢复：长跑时 socket 会超时（ETIMEOUT 是未被捕获的 error 事件，会直接把进程带走）。
 * 每个动作包一层，断了就重连、重开 INBOX，再重试同一封。
 */
async function withReconnect(client, fn, label = "") {
  let lastErr = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      if (!client.usable) {
        await client.connect();
        await client.mailboxOpen("INBOX");
      }
      return await fn();
    } catch (e) {
      lastErr = e;
      if (label) log(`  ~ ${label} 第 ${attempt + 1} 次失败：${String(e?.message ?? e).slice(0, 80)}，重连重试`);
      await sleep(1000 * (attempt + 1));
      try { await client.logout(); } catch {}
    }
  }
  if (label) log(`  ! ${label} 三次都失败，跳过（原件保留，可下次重跑）`);
  void lastErr;
  return null;
}

// ---------------------------------------------------------------- 日志
const LOGFILE = path.join(HERE, "sort.log");
function log(msg, toFile = true) {
  console.log(msg);
  if (toFile) {
    try {
      fs.appendFileSync(LOGFILE, `[${new Date().toISOString()}] ${msg}\n`, "utf8");
    } catch {
      /* 无写权限就只打屏，不影响分类 */
    }
  }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 把本次运行结果落盘，供 report.mjs 生成 HTML（纯数据，不含模型调用） */
function writeRunLog(payload) {
  const day = (payload.ts || new Date().toISOString()).slice(0, 10);
  try {
    fs.writeFileSync(path.join(HERE, "last-run.json"), JSON.stringify(payload, null, 1), "utf8");
  } catch (e) {
    log(`! 写 last-run.json 失败：${e.message}`);
  }
  // 同一天跑多次（手动补跑、--once 等）就累加到当日文件，报告按天汇总
  try {
    const dir = path.join(HERE, "report", "data");
    fs.mkdirSync(dir, { recursive: true });
    const fp = path.join(dir, `${day}.json`);
    let dayFile = { date: day, runs: [] };
    if (fs.existsSync(fp)) {
      try { dayFile = JSON.parse(fs.readFileSync(fp, "utf8")); } catch {}
    }
    dayFile.runs = Array.isArray(dayFile.runs) ? dayFile.runs : [];
    dayFile.runs.push({
      ts: payload.ts,
      inboxBefore: payload.inboxBefore,
      inboxAfter: payload.inboxAfter,
      scanned: payload.scanned,
      movedTotal: payload.movedTotal,
      movedByLabel: payload.movedByLabel,
      kept: payload.kept,
      llm: payload.llm,
      srcCount: payload.srcCount,
      note: payload.note,
    });
    fs.writeFileSync(fp, JSON.stringify(dayFile, null, 1), "utf8");
  } catch (e) {
    log(`! 写当日报告数据失败：${e.message}`);
  }
}
const addrText = (a) =>
  !a ? "" : (Array.isArray(a) ? a : [a]).map((x) => (x?.name ? `${x.name} <${x.address ?? ""}>` : (x?.address ?? ""))).filter(Boolean).join(", ");

// ---------------------------------------------------------------- 启动
const { user, pass } = loadCreds();
if (!user || !pass) {
  log("[致命] 缺少账号或授权码：请在 qqmail.config.json 里填 user / authCode。", false);
  process.exit(2);
}

const A = makeClient(user, pass); // 收件箱线：COPY / EXPUNGE
const B = makeClient(user, pass); // 核对线：只读
let exitCode = 0;

/** 目标文件夹里已有的 Message-ID 集合（懒加载 + 缓存） */
const indexCache = new Map();
async function indexFor(label) {
  if (indexCache.has(label)) return indexCache.get(label);
  const set = new Set();
  try {
    const box = await B.mailboxOpen(label, { readOnly: true });
    const uv = String(box.uidValidity);
    const cached = RESCAN ? { keys: [], maxUid: 0, fresh: true } : folderCache(ST, label, uv);
    for (const k of cached.keys) set.add(k);
    const fromUid = cached.fresh ? 1 : cached.maxUid + 1;
    let maxUid = cached.maxUid;
    let added = 0;
    // 不要用 uidNext 判断“有没有新增”：QQ 的 UIDNEXT 会滞后于刚 COPY 进来的邮件，
    // 曾经因此跳过取信、导致“核对未通过”的死循环。直接 fetch，没有就是空，成本很小。
    {
      for await (const m of B.fetch(`${fromUid}:*`, { envelope: true, uid: true }, { uid: true })) {
        const e2 = m.envelope ?? {};
        const id = e2.messageId;
        if (id) set.add(id);
        // 没有 Message-ID 的邮件（QQ 偶尔会有）用「主题+日期+发件人」做兜底键，否则每轮都会重复复制
        const d2 = e2.date ? new Date(e2.date).toISOString().slice(0, 10) : "";
        const f2 = (e2.from?.[0]?.address ?? "").toLowerCase();
        set.add(`S|${(e2.subject ?? "").trim()}|${d2}|${f2}`);
        if (m.uid > maxUid) maxUid = m.uid;
        added++;
      }
      if (VERBOSE) log(`  · ${label} 索引 +${added} 条（uid > ${cached.maxUid}）`);
    }
    setFolderCache(ST, label, uv, [...set], maxUid);
  } catch (e) {
    log(`  ? 读不到 ${label}：${e.message}`);
  }
  indexCache.set(label, set);
  return set;
}

/** 一封邮件在索引里的去重键：优先 Message-ID，没有就用 主题+日期+发件人 */
const keyOf = (r) => {
  if (r.msgId) return r.msgId;
  const addr = (String(r.from || "").match(/<([^>]+)>/)?.[1] || r.from || "").toLowerCase();
  return `S|${(r.subject ?? "").trim()}|${r.date || ""}|${addr}`;
};

try {
  await A.connect();
  await A.mailboxOpen("INBOX");

  // ============================ 自检 ============================
  if (SELFTEST) {
    const tmp = "ZZ-self-test";
    await B.connect();
    if (!(await A.list()).some((b) => b.path === tmp)) await A.mailboxCreate(tmp);
    let sample = null;
    for await (const m of A.fetch("1:*", { envelope: true, uid: true })) sample = m;
    if (!sample) {
      log("INBOX 为空，自检跳过。");
    } else {
      const msgId = sample.envelope?.messageId;
      log(`自检样本：uid=${sample.uid}  ${(sample.envelope?.subject ?? "").slice(0, 40)}`);
      const res = await A.messageCopy(String(sample.uid), tmp, { uid: true });
      if (!res) throw new Error("COPY 返回 false");
      let destUid = res.uidMap ? res.uidMap.get(sample.uid) : undefined;
      await B.mailboxOpen(tmp, { readOnly: true });
      if (!destUid) destUid = (await B.search({ header: { "message-id": msgId } }, { uid: true }))[0];
      const check = destUid ? await B.fetchOne(String(destUid), { envelope: true }, { uid: true }) : null;
      const same = check && (check.envelope?.messageId ?? "") === (msgId ?? "");
      log(`核对：目标 uid=${destUid}，Message-ID 一致 = ${same ? "是" : "否"}`);
      if (!same) throw new Error("核对失败");
      await B.mailboxClose();
      await B.mailboxOpen(tmp, { readOnly: false });
      log(`清理副本：${(await B.messageDelete(String(destUid), { uid: true })) ? "已删除" : "失败"}`);
      await B.mailboxClose();
      try { await A.mailboxDelete(tmp); log("临时文件夹已删除。"); } catch (e) { log(`临时文件夹删除失败：${e.message}`); }
      log("自检通过：COPY → 核对 → 删副本可用；INBOX 原件未动。");
    }
    await B.logout();
    await A.logout();
    process.exit(0);
  }

  // ============================ 取候选（增量） ============================
  // 只取「UID > 上次水位线」的邮件，加上上次没处理成功的 pendingUids。
  // 不再每次把 INBOX 全量拉一遍 —— 这是最省时间的一处。
  // 重新 SELECT 一次，刷新 uidNext / exists 快照。
  // （原来读的是启动那次 SELECT 的值：之后新到的邮件它不认，配合 UID 范围里的 "*"
  //   会被算成空区间，结果就是“看起来没新信”。）
  await A.mailboxOpen("INBOX");
  const total = A.mailbox.exists;
  const uvIn = String(A.mailbox.uidValidity);
  const uidNextIn = Number(A.mailbox.uidNext) || 0;
  const inflowFresh = RESCAN || String(ST.inflow.uidValidity) !== uvIn;
  const fromUid = inflowFresh ? 1 : (ST.inflow.maxUid ?? 0) + 1;
  const pending = new Set((ST.pendingUids ?? []).map(Number));
  const rows = [];
  let scanned = 0;
  // 注意第三个参数 { uid: true }：不加的话 "3134:*" 会被当成「序号」而不是「UID」，
  // 而 INBOX 只有几十封，序号 3134 不存在 → 永远是 0 封（一个非常安静的坑）。
  for await (const m of A.fetch(`${fromUid}:*`, { envelope: true, uid: true, flags: true }, { uid: true })) {
    const e = m.envelope ?? {};
    const d = e.date ? new Date(e.date) : null;
    rows.push({
      uid: m.uid,
      msgId: e.messageId ?? "",
      date: d ? d.toISOString().slice(0, 10) : "",
      ts: d ? d.getTime() : 0,
      from: addrText(e.from),
      subject: e.subject ?? "",
    });
    scanned++;
  }
  // 自检：服务器说 UIDNEXT 已经超过水位线，却一封都没取到 → 查询口径错了，退回全量，绝不漏信
  if (!inflowFresh && uidNextIn > fromUid && scanned === 0 && total > 0) {
    log(`! 异常：UIDNEXT=${uidNextIn} > 水位线+1=${fromUid}，却只取到 0 封。退回全量重扫。`);
    rows.length = 0;
    for await (const m of A.fetch("1:*", { envelope: true, uid: true, flags: true })) {
      const e = m.envelope ?? {};
      const d = e.date ? new Date(e.date) : null;
      rows.push({
        uid: m.uid,
        msgId: e.messageId ?? "",
        date: d ? d.toISOString().slice(0, 10) : "",
        ts: d ? d.getTime() : 0,
        from: addrText(e.from),
        subject: e.subject ?? "",
      });
      scanned++;
    }
  }
  // 上次失败的、以及（非全量模式下）水位线之外漏掉的，补进来
  if (pending.size) {
    for await (const m of A.fetch([...pending].join(","), { envelope: true, uid: true, flags: true }, { uid: true })) {
      const e = m.envelope ?? {};
      const d = e.date ? new Date(e.date) : null;
      if (rows.some((r) => r.uid === m.uid)) continue;
      rows.push({
        uid: m.uid,
        msgId: e.messageId ?? "",
        date: d ? d.toISOString().slice(0, 10) : "",
        ts: d ? d.getTime() : 0,
        from: addrText(e.from),
        subject: e.subject ?? "",
      });
    }
  }
  rows.sort((a, b) => a.uid - b.uid);
  log(
    inflowFresh
      ? `INBOX 全量模式（水位线已失效/首次运行）：扫 ${scanned} 封`
      : `INBOX 增量模式：扫 ${scanned} 封新邮件（水位线 uid>${fromUid - 1}，UIDNEXT=${uidNextIn}，共 ${total} 封）`
  );

  let cand = rows;
  if (DAYS > 0) {
    const cut = Date.now() - DAYS * 86400000;
    cand = cand.filter((r) => r.ts >= cut);
  }
  if (cand.length > LIMIT) cand = cand.slice(-LIMIT);

  // ============================ 分类 ============================
  // 两段式：规则先判（strong/medium 直接定），只有 weak/none 才送 Jev（--triage）。
  // 不加 --triage 时 --llm 会把全部候选送模型（更贵，但更"统一"）。
  const detailOf = new Map();
  for (const r of cand) detailOf.set(r.uid, classifyDetail(r));
  const ruleOf = new Map(cand.map((r) => [r.uid, detailOf.get(r.uid).key]));
  const ambiguous = cand.filter((r) => needsModel(detailOf.get(r.uid)));

  let llmMap = null; // Map<uid, {cat, conf}>
  let llmStats = null; // 写进报告：调用次数、成本、模型
  if (LLM) {
    const targets = TRIAGE ? ambiguous : cand;
    const tag = TRIAGE ? `规则没把握的 ${targets.length}/${cand.length}` : `全部 ${targets.length}`;
    if (!targets.length) {
      log(`送模型：0 封（规则全部直接判定，不花模型钱）`);
    } else {
      try {
        const res = await classifyWithLlm(targets, { verbose: VERBOSE });
        llmStats = res.stats;
        llmMap = new Map();
        let i = 0;
        for (const t of targets) {
          const hit = res.map.get(i++);
          if (hit) llmMap.set(t.uid, hit);
        }
        log(
          `送模型（${tag} 封）：成功判 ${llmMap.size} 封，调用 ${res.stats.calls} 次` +
            `（重问 ${res.stats.retried}，缓存 ${res.stats.cached}），成本 $${res.stats.cost.toFixed(6)} · ${res.stats.model ?? ""}`
        );
      } catch (e) {
        log(`[警告] 模型不可用，这批继续按规则分类（weak/none 会留在收件箱）：${String(e.message).slice(0, 120)}`);
      }
    }
  }

  const groups = new Map();
  const finalCat = new Map(); // uid → 最终类别
  let kept = 0;
  let disagree = 0;
  cand.forEach((r) => {
    const d = detailOf.get(r.uid);
    const llm = llmMap?.get(r.uid);
    const k = llm?.cat ?? d.key;
    finalCat.set(r.uid, k);
    if (llm && llm.cat !== d.key) {
      disagree++;
      if (VERBOSE) log(`  ~ 分歧《${r.subject.slice(0, 28)}》规则=${d.key}(${d.src}) → Jev=${llm.cat}(${llm.conf})`);
    }
    if (k === "other") { kept++; return; } // 人对人邮件永远留在收件箱
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(r);
  });
  const srcCount = { strong: 0, medium: 0, weak: 0, none: 0 };
  for (const r of cand) srcCount[detailOf.get(r.uid).src]++;
  log(`规则把握度：strong ${srcCount.strong} / medium ${srcCount.medium} / weak ${srcCount.weak} / none ${srcCount.none}`);
  if (llmMap) log(`与规则不一致 ${disagree} 封（以模型判定为准）`);

  // ============================ 幂等检查 ============================
  await B.connect();
  const todo = []; // 需要复制
  const already = []; // 目标里已有同一封（Message-ID 或 主题+日期）
  for (const [k, list] of groups) {
    const label = CATS.find((c) => c.key === k).label;
    let idx = null;
    let hits = 0;
    for (const r of list) {
      idx = idx ?? (await indexFor(label));
      if (idx.has(keyOf(r))) { already.push({ ...r, label }); hits++; continue; }
      todo.push({ ...r, label });
    }
    if (hits) log(`  ${label.padEnd(12)} 已在目标 ${String(hits).padStart(3)} 封（只需核对+清理原件）`);
  }

  log(`INBOX ${total} 封 → 候选 ${cand.length}（上限 ${LIMIT}${DAYS ? `，最近 ${DAYS} 天` : ""}）；需复制 ${todo.length}；已归档待清理 ${already.length}；保留收件箱 ${kept}`);
  for (const c of CATS) {
    const g = groups.get(c.key);
    if (g?.length) log(`    ${c.label.padEnd(12)} ${String(g.length).padStart(3)} 封`);
  }
  if (!todo.length && !already.length) {
    log("没有需要处理的邮件。");
    // 这批全被判成 other（人对人邮件），推进水位线，下一轮不再重复扫它们
    if (!DRY && rows.length) {
      const maxSeen0 = rows.reduce((mx, r) => Math.max(mx, r.uid), 0);
      ST.inflow = { uidValidity: uvIn, maxUid: Math.max(maxSeen0, ST.inflow?.maxUid ?? 0) };
      ST.pendingUids = [];
      saveState(ST);
      log(`水位线推进到 uid=${ST.inflow.maxUid}（这些邮件留在收件箱，不再重复扫）`);
    }
    writeRunLog({
      ts: new Date().toISOString(),
      inboxBefore: total,
      inboxAfter: total,
      scanned,
      movedTotal: 0,
      movedByLabel: {},
      kept: cand.filter((r) => finalCat.get(r.uid) === "other").map((r) => ({ from: r.from, subject: r.subject, date: r.date })),
      llm: llmStats,
      srcCount,
      note: "本次没有需要归档的邮件",
    });
    await B.logout(); await A.logout();
    process.exit(0);
  }
  if (DRY) {
    log("（--dry 预览，未改动邮箱。）");
    await B.logout(); await A.logout();
    process.exit(0);
  }

  // ============================ 建文件夹 ============================
  const have = new Set((await A.list()).map((b) => b.path));
  for (const k of groups.keys()) {
    const label = CATS.find((c) => c.key === k).label;
    if (!have.has(label)) { await A.mailboxCreate(label); log(`新建文件夹：${label}`); }
  }

  // ============================ 逐封 COPY ============================
  const copied = [];
  let copyFail = 0;
  let tick = 0;
  for (const r of todo) {
    const res = await withReconnect(A, async () => {
      if (A.mailbox?.path !== "INBOX") await A.mailboxOpen("INBOX");
      return await A.messageCopy(String(r.uid), r.label, { uid: true });
    }, `COPY uid=${r.uid}`);
    if (!res) {
      copyFail++;
      log(`  ! COPY 失败 uid=${r.uid} 《${r.subject.slice(0, 30)}》（原件保留）`);
    } else {
      copied.push(r);
      if (VERBOSE) log(`  copied uid=${r.uid} → ${r.label}`);
    }
    if (++tick % 80 === 0) {
      await withReconnect(A, async () => A.noop(), "");
      log(`  … 已复制 ${tick}/${todo.length}`);
    }
    await sleep(PER_COPY_DELAY);
  }
  log(`COPY：成功 ${copied.length}，失败 ${copyFail}`);
  const ratio = copied.length + copyFail > 0 ? copyFail / (copied.length + copyFail) : 0;
  if (ratio > 0.3) {
    log(`[中止] 复制失败率 ${(ratio * 100).toFixed(0)}% > 30%，不删除任何原件。`);
    await B.logout(); await A.logout();
    process.exit(1);
  }

  // ============================ 核对（独立连接） ============================
  const verified = [];
  const byLabel = new Map();
  for (const r of copied) {
    if (!byLabel.has(r.label)) byLabel.set(r.label, []);
    byLabel.get(r.label).push(r);
  }
  for (const [label, items] of byLabel) {
    // QQ 对新建成文件夹的 COPY 有可见性延迟（实测建完立刻拷，目标里要过几秒才看得到），
    // 所以核对要重试，不能一次没看到就判失败。
    let fresh = null;
    let missing = items;
    for (let attempt = 0; attempt < 4 && missing.length; attempt++) {
      if (attempt) {
        log(`  … ${label} 还差 ${missing.length} 封没见到，${4 * attempt}s 后重查（QQ 建新文件夹有延迟）`);
        await sleep(4000 * attempt);
      }
      indexCache.delete(label);
      fresh = await indexFor(label);
      missing = items.filter((i) => !fresh.has(keyOf(i)));
    }
    let ok = 0;
    for (const i of items) {
      if (!missing.includes(i)) { verified.push(i); ok++; }
      else log(`  ! 核对未通过 uid=${i.uid} 《${i.subject.slice(0, 30)}》（原件保留）`);
    }
    log(`核对 ${label}：${ok}/${items.length} 到位`);
  }
  // 已归档的那批本身就等于“核对通过”（索引里查到的就是它）
  const allVerified = verified.concat(already);
  log(`核对合计：新复制 ${verified.length}/${copied.length}；已有副本 ${already.length}；共可清理 ${allVerified.length}`);

  if (!allVerified.length) {
    log("没有一封核对通过，中止（不删原件）。");
    await B.logout(); await A.logout();
    process.exit(1);
  }

  // ============================ 清理原件 ============================
  // 注意：QQ 的 UID EXPUNGE 不接受逗号列表（实测整批返回 false），所以逐封删。
  // 长跑时 socket 会超时，所以每封都走 withReconnect，每 80 封 NOOP 保活。
  let expunged = 0;
  let n = 0;
  const okUids = [];
  for (const v of allVerified) {
    const ok = await withReconnect(A, async () => {
      if (A.mailbox?.path !== "INBOX") await A.mailboxOpen("INBOX");
      return await A.messageDelete(String(v.uid), { uid: true });
    }, `EXPUNGE uid=${v.uid}`);
    if (ok) { expunged++; okUids.push(v.uid); }
    else log(`  ! EXPUNGE 未生效 uid=${v.uid}（已复制，留重复，安全）`);
    if (++n % 80 === 0) {
      await withReconnect(A, async () => A.noop(), "");
      log(`  … 已清理 ${n}/${allVerified.length}`);
    }
    await sleep(60);
  }

  const after = await withReconnect(A, async () => A.mailboxOpen("INBOX", { readOnly: true }), "recount");
  log(`收件箱：${total} → ${after ? after.exists : "?"} 封；EXPUNGE 报 ${expunged} 封`);

  // ============================ 写本次运行记录（给 HTML 报告用） ============================
  const byUid = new Map(cand.map((r) => [r.uid, r]));
  const movedByLabel = {};
  for (const uid of okUids) {
    const r = byUid.get(uid);
    if (!r) continue;
    const key = finalCat.get(uid);
    const label = CATS.find((c) => c.key === key)?.label ?? key;
    (movedByLabel[label] ??= []).push({ from: r.from, subject: r.subject, date: r.date });
  }
  writeRunLog({
    ts: new Date().toISOString(),
    inboxBefore: total,
    inboxAfter: after ? after.exists : null,
    scanned,
    movedTotal: okUids.length,
    movedByLabel,
    kept: cand.filter((r) => finalCat.get(r.uid) === "other").map((r) => ({ from: r.from, subject: r.subject, date: r.date })),
    llm: llmStats,
    srcCount,
  });

  // ============================ 推进水位线 ============================
  // 只有真正执行（非 --dry）才推进，否则下次会误以为这些邮件已处理。
  const doneUids = new Set(allVerified.map((v) => v.uid));
  const failed = cand.filter((r) => !doneUids.has(r.uid) && finalCat.get(r.uid) !== "other").map((r) => r.uid);
  const maxSeen = rows.reduce((mx, r) => Math.max(mx, r.uid), 0);
  ST.inflow = { uidValidity: uvIn, maxUid: Math.max(maxSeen, ST.inflow?.maxUid ?? 0) };
  ST.pendingUids = failed;
  saveState(ST);
  log(
    `水位线推进到 uid=${ST.inflow.maxUid}（UIDNEXT=${uidNextIn}）；` +
      `未处理/待重试 ${failed.length} 封；下轮只扫新邮件`
  );
  log("完成。");
  await B.logout();
  await A.logout();
} catch (e) {
  log(`[错误] ${e?.message ?? e}`, false);
  exitCode = 1;
  try { await A.logout(); } catch {}
  try { await B.logout(); } catch {}
}
process.exit(exitCode);
