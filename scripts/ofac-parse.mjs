// Copied from botsrated-panel jobs/panel/src/ofac.js (parser + download only are used here).
// OFAC SDN payTo screen for the panel Worker. Port of pipeline/buyer/sanctions.mjs + screen.mjs (legal review M8).
// Source: OFAC SDN list (U.S. Treasury Sanctions List Service). Only "Digital Currency Address - <coin>" ids are kept.
// Cache: D1 meta key "ofac:sdn_dca" (one small row, overwritten). Refreshed when older than 24 h.
// FAIL CLOSED: if the list can't be downloaded and the cache is stale or missing, loadSdnList() throws and no buy is made.
// The ~30 MB XML is parsed as a stream so the Worker never holds the whole file in memory.

export const SDN_URL = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML";
export const MAX_AGE_MS = 24 * 3600e3;
export const META_KEY = "ofac:sdn_dca";
// 2026-11-25: the Treasury host does not answer Cloudflare egress (timed out from the edge, verified), so the
// download must give up fast instead of hanging the whole run, and one run loads the list at most once.
export const DOWNLOAD_TIMEOUT_MS = 30000;
// A DRY run spends nothing, so it may screen against a cached list up to this old (default 14 days, var
// OFAC_DRY_MAX_AGE_DAYS). LIVE buys keep the 24 h rule and still fail closed on anything older.
export const DRY_MAX_AGE_MS = 14 * 86400e3;
let memo = null; // per-run: { key, promise }
export function resetSdnMemo() { memo = null; }
const MIN_RECORDS = 5000, MIN_ADDRESSES = 200, MIN_EVM = 20; // same sanity floors as the box
const EVM = /^0x[0-9a-fA-F]{40}$/;
const tag = (blk, name) => { const m = blk.match(new RegExp(`<${name}>([\\s\\S]*?)</${name}>`)); return m ? m[1].trim() : null; };
const unxml = (s) => String(s ?? "").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, "&");

function addEntryBlock(blk, acc) {
  if (!blk.includes("Digital Currency Address")) return;
  const uid = tag(blk, "uid");
  const ire = /<id>([\s\S]*?)<\/id>/g; let i;
  while ((i = ire.exec(blk))) {
    const t = tag(i[1], "idType") || ""; const n = unxml(tag(i[1], "idNumber"));
    const c = t.match(/^Digital Currency Address - (.+)$/);
    if (!c || !n) continue;
    const address = n.trim(), coin = c[1].trim();
    acc.addresses_total += 1;
    acc.by_coin[coin] = (acc.by_coin[coin] || 0) + 1;
    if (EVM.test(address)) acc.evm[address.toLowerCase()] = { coin, uid }; else acc.other[address] = { coin, uid };
  }
}

/** Parse SDN XML from a string or a ReadableStream of bytes. */
export async function parseSdn(source) {
  const acc = { publish_date: null, record_count: NaN, addresses_total: 0, by_coin: {}, evm: {}, other: {}, saw_root: false };
  const consume = (buf, final) => {
    if (!acc.saw_root && buf.includes("<sdnList")) acc.saw_root = true;
    if (acc.publish_date === null) {
      const pub = buf.match(/<publshInformation>([\s\S]*?)<\/publshInformation>/);
      if (pub) { acc.publish_date = tag(pub[1], "Publish_Date"); acc.record_count = Number(tag(pub[1], "Record_Count")); }
    }
    let pos = 0;
    for (;;) {
      const s = buf.indexOf("<sdnEntry>", pos); if (s < 0) break;
      const e = buf.indexOf("</sdnEntry>", s); if (e < 0) { pos = s; return final ? "" : buf.slice(s); }
      addEntryBlock(buf.slice(s + 10, e), acc); pos = e + 11;
    }
    const keep = buf.lastIndexOf("<");
    return final ? "" : (acc.publish_date === null ? buf.slice(Math.max(0, buf.length - 4096)) : buf.slice(keep >= pos ? keep : buf.length));
  };
  if (typeof source === "string") { consume(source, true); }
  else {
    const reader = source.pipeThrough(new TextDecoderStream()).getReader();
    let carry = "";
    for (;;) { const { value, done } = await reader.read(); if (done) break; carry = consume(carry + value, false); }
    consume(carry, true);
  }
  return acc;
}

export function checkList(list) {
  const why = !list ? "no list" : !(list.record_count >= MIN_RECORDS) ? `record_count ${list.record_count} < ${MIN_RECORDS}`
    : !(list.addresses_total >= MIN_ADDRESSES) ? `only ${list.addresses_total} digital currency addresses` : !(list.evm_count >= MIN_EVM) ? `only ${list.evm_count} EVM addresses` : null;
  if (why) throw new Error("OFAC SDN list failed sanity check: " + why);
  return list;
}

export async function downloadSdnList({ fetchFn = fetch, now = Date.now() } = {}) {
  const r = await fetchFn(SDN_URL, { redirect: "follow", headers: { "user-agent": "BotsRated-buyer-sanctions/0.1 (+https://botsrated.com/methodology)" }, signal: AbortSignal.timeout(DOWNLOAD_TIMEOUT_MS) });
  if (!r.ok) throw new Error(`OFAC SDN download HTTP ${r.status}`);
  const p = await parseSdn(r.body);
  if (!p.saw_root) throw new Error("OFAC SDN download is not SDN XML");
  return checkList({ source: "OFAC SDN list (sanctionslistservice.ofac.treas.gov)", url: SDN_URL, publish_date: p.publish_date, record_count: p.record_count,
    fetched_at: new Date(now).toISOString(), addresses_total: p.addresses_total, evm_count: Object.keys(p.evm).length, by_coin: p.by_coin, evm: p.evm, other: p.other });
}

/** Fresh cache (< 24 h) -> use it. Else download; if that fails, THROW (fail closed). Never falls back to a stale cache. */
export async function loadSdnList(env, opts = {}) {
  const maxAge = opts.maxAgeMs || MAX_AGE_MS;
  if (opts.memo !== false && memo && memo.maxAge === maxAge) return memo.promise;
  const promise = loadSdnListOnce(env, { ...opts, maxAge });
  if (opts.memo !== false) memo = { maxAge, promise };
  return promise;
}

async function loadSdnListOnce(env, { fetchFn = fetch, now = Date.now(), download = downloadSdnList, maxAge = MAX_AGE_MS } = {}) {
  let cached = null;
  try {
    const row = env?.DB ? await env.DB.prepare("SELECT v FROM meta WHERE k = ?").bind(META_KEY).first() : null;
    cached = row?.v ? JSON.parse(row.v) : null;
  } catch { cached = null; }
  if (cached?.fetched_at && now - Date.parse(cached.fetched_at) < maxAge) return { list: checkList(cached), from: maxAge > MAX_AGE_MS && now - Date.parse(cached.fetched_at) >= MAX_AGE_MS ? "cache (older than 24 h; dry run only)" : "cache" };
  let fresh;
  try { fresh = await download({ fetchFn, now }); }
  catch (e) { throw new Error(`OFAC SDN list unavailable (${e.message}); cached copy ${cached?.fetched_at ? "is from " + cached.fetched_at + ", older than " + Math.round(maxAge / 3600e3) + " h" : "missing"}. Refusing to buy (fail closed).`); }
  if (env?.DB) {
    await env.DB.prepare("INSERT INTO meta (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v").bind(META_KEY, JSON.stringify(fresh)).run();
  }
  return { list: fresh, from: "download" };
}

export function screenAddress(addr, list) {
  const a = String(addr || "").trim(); if (!a) return { blocked: false };
  const hit = EVM.test(a) ? list.evm?.[a.toLowerCase()] : list.other?.[a];
  return hit ? { blocked: true, reason: "sanctions_screen", address: a, coin: hit.coin, sdn_uid: hit.uid, list_publish_date: list.publish_date } : { blocked: false };
}

/** Screen every payTo the seller offered. Never throws: { ok, list?, sanctions? } or { ok:false, reason, detail }. */
export async function screenPayTos(env, payTos, opts = {}) {
  let list, from;
  try { ({ list, from } = await loadSdnList(env, opts)); }
  catch (e) { return { ok: false, reason: "blocked: sanctions_list_unavailable", detail: String(e.message).slice(0, 240) }; }
  for (const p of payTos) {
    const s = screenAddress(p, list);
    if (s.blocked) return { ok: false, reason: "blocked: sanctions_screen", detail: `payTo ${p} is on the OFAC SDN list (${s.coin}, SDN uid ${s.sdn_uid})`, match: s };
  }
  return { ok: true, list, sanctions: { screened: payTos.length, list_publish_date: list.publish_date, list_fetched_at: list.fetched_at, list_from: from, result: "no match" } };
}
