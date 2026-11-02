/**
 * 增量状态：记住每个文件夹的 UID 水位线，下次只拉“比它大的”邮件。
 *
 * 为什么不用“数封数”：
 *   - 我们把邮件搬出 INBOX 会让总数下降，下一秒又因为新邮件上升，容易误判
 *   - 同期删除/移动会让“封数差”算错
 *   - IMAP 的 UID 在同一文件夹内单调递增，搬走/删除都不影响，天然适合做水位线
 *
 * UIDVALIDITY 变了（服务器重建文件夹）就丢掉水位线，全量重扫。
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATE_PATH = path.join(HERE, "state.json");
const EMPTY = { version: 1, inflow: { uidValidity: null, maxUid: 0 }, folders: {}, pendingUids: [], lastRun: null };

export function loadState() {
  try {
    const j = JSON.parse(fs.readFileSync(STATE_PATH, "utf8"));
    if (j && j.version === 1) return { ...EMPTY, ...j };
  } catch {
    /* 第一次跑或文件坏了，从空状态开始 */
  }
  return JSON.parse(JSON.stringify(EMPTY));
}

export function saveState(st) {
  st.lastRun = new Date().toISOString();
  try {
    fs.writeFileSync(STATE_PATH, JSON.stringify(st, null, 1), "utf8");
    return true;
  } catch {
    return false; // 沙箱里写不了就退化，不影响本轮分类
  }
}

/** 取某个目标文件夹的缓存索引；UIDVALIDITY 对不上就返回空（=全量重扫） */
export function folderCache(st, label, uidValidity) {
  const rec = st.folders[label];
  if (!rec || String(rec.uidValidity) !== String(uidValidity)) {
    return { keys: [], maxUid: 0, fresh: true };
  }
  return { keys: rec.keys ?? [], maxUid: rec.maxUid ?? 0, fresh: false };
}

export function setFolderCache(st, label, uidValidity, keys, maxUid) {
  st.folders[label] = { uidValidity: String(uidValidity), maxUid, keys };
}
