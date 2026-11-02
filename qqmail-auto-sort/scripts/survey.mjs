// 把收件箱剩余的邮件按发件人聚合出来，给人看（我）和给规则对照。
// 输出：每个发件人的封数、时间跨度、最多 4 个主题样本、当前规则给的类别。
import { createRequire } from "node:module";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { classify } from "./categories.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PROJ = (process.env.QQMAIL_MCP_PROJ || "D:/github_project/ZhaoWen_GitHub维护/zhaowen-mcp/qqmail-mcp");
const require = createRequire(PROJ + "/package.json");
const { ImapFlow } = require("imapflow");

const c0 = JSON.parse(fs.readFileSync(path.join(HERE, "qqmail.config.json"), "utf8"));
const client = new ImapFlow({
  host: "imap.qq.com", port: 993, secure: true,
  auth: { user: c0.user, pass: process.env.QQMAIL_AUTH_CODE || c0.authCode },
  logger: false, greetingTimeout: 20000, socketTimeout: 180000,
});

const addrText = (a) => (!a ? "" : (Array.isArray(a) ? a : [a]).map((x) => (x?.name ? `${x.name} <${x.address ?? ""}>` : (x?.address ?? ""))).filter(Boolean).join(", "));

try {
  await client.connect();
  await client.mailboxOpen("INBOX", { readOnly: true });
  const rows = [];
  for await (const m of client.fetch("1:*", { envelope: true })) {
    const e = m.envelope ?? {};
    rows.push({
      date: e.date ? new Date(e.date).toISOString().slice(0, 10) : "",
      from: addrText(e.from),
      subject: e.subject ?? "",
    });
  }
  const by = new Map();
  for (const r of rows) {
    const a = (r.from.match(/<([^>]+)>/)?.[1] || r.from || "?").toLowerCase();
    if (!by.has(a)) by.set(a, { n: 0, first: r.date, last: r.date, subs: [], cat: classify(r) });
    const b = by.get(a);
    b.n++;
    if (r.date && (!b.first || r.date < b.first)) b.first = r.date;
    if (r.date > b.last) b.last = r.date;
    if (b.subs.length < 4 && !b.subs.includes(r.subject.slice(0, 46))) b.subs.push(r.subject.slice(0, 46));
  }
  console.log(`INBOX ${rows.length} 封 / ${by.size} 个发件人`);
  const arr = [...by.entries()].sort((a, b) => b[1].n - a[1].n);
  for (const [a, v] of arr) {
    console.log(`${String(v.n).padStart(4)} [${v.cat}] ${v.first}~${v.last} ${a}`);
    for (const s of v.subs) console.log(`        ${s}`);
  }
} catch (e) {
  console.log("ERR " + String(e?.message ?? e));
} finally {
  try { await client.logout(); } catch {}
}
