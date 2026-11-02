// 用已归档的真实邮件做对照：Jev 判的 vs 规则判的 vs 实际所在文件夹。
// 只读：不复制、不删除、不改文件夹。
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { classify, CATS } from "./categories.mjs";
import { classifyWithLlm } from "./llm-classify.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PROJ = (process.env.QQMAIL_MCP_PROJ || "D:/github_project/ZhaoWen_GitHub维护/zhaowen-mcp/qqmail-mcp");
const require = createRequire(PROJ + "/package.json");
const { ImapFlow } = require("imapflow");

const PER_FOLDER = Number(process.argv[2] || 4);
const c0 = JSON.parse(fs.readFileSync(path.join(HERE, "qqmail.config.json"), "utf8"));
const client = new ImapFlow({
  host: "imap.qq.com", port: 993, secure: true,
  auth: { user: c0.user, pass: process.env.QQMAIL_AUTH_CODE || c0.authCode },
  logger: false, greetingTimeout: 20000, socketTimeout: 120000,
});

const addrText = (a) => (!a ? "" : (Array.isArray(a) ? a : [a]).map((x) => (x?.name ? `${x.name} <${x.address ?? ""}>` : (x?.address ?? ""))).filter(Boolean).join(", "));

const samples = [];
await client.connect();
for (const c of CATS) {
  if (c.key === "other" || c.key === "daily") continue;
  try {
    await client.mailboxOpen(c.label, { readOnly: true });
  } catch { continue; }
  const rows = [];
  for await (const m of client.fetch("1:*", { envelope: true })) {
    const e = m.envelope ?? {};
    rows.push({
      msgId: e.messageId,
      from: addrText(e.from),
      subject: e.subject ?? "",
      date: e.date ? new Date(e.date).toISOString().slice(0, 10) : "",
    });
  }
  // 均匀取样，避免只拿到同一批发件人
  const step = Math.max(1, Math.floor(rows.length / PER_FOLDER));
  for (let i = 0; i < rows.length && samples.filter((s) => s.label === c.label).length < PER_FOLDER; i += step) {
    samples.push({ ...rows[i], label: c.label });
  }
}
await client.logout();

const ruleCats = samples.map((s) => classify(s));
const { map, stats } = await classifyWithLlm(samples, { verbose: true });

const byKey = Object.fromEntries(CATS.map((c) => [c.label, c.key]));
let agreeRules = 0, agreeJev = 0, n = 0;
const rows = [];
for (let i = 0; i < samples.length; i++) {
  const s = samples[i];
  const truth = byKey[s.label];
  const jv = map.get(i)?.cat ?? "(无)";
  const conf = map.get(i)?.conf;
  const ru = ruleCats[i];
  n++;
  if (ru === truth) agreeRules++;
  if (jv === truth) agreeJev++;
  if (ru !== truth || jv !== truth) rows.push({ s, truth, ru, jv, conf });
}

console.log(`\n样本 ${n} 封（每类 ${PER_FOLDER} 封）；调用 ${stats.calls} 次，成本 $${stats.cost.toFixed(6)}，模型 ${stats.model}`);
console.log(`与归档结果一致：规则 ${agreeRules}/${n} (${((agreeRules / n) * 100).toFixed(1)}%)  Jev ${agreeJev}/${n} (${((agreeJev / n) * 100).toFixed(1)}%)`);
if (rows.length) {
  console.log("\n不一致的明细（truth=归档处 / rule=规则判定 / jev=模型判定）");
  for (const r of rows) {
    console.log(`  [${r.truth}] rule=${r.ru} jev=${r.jv}(${r.conf})  ${String(r.s.from).slice(0, 34)} | ${r.s.subject.slice(0, 44)}`);
  }
}
