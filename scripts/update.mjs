// Daily mirror of the OFAC SDN list's digital currency addresses, for workers that cannot reach Treasury.
// Source: https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML (U.S. Treasury, public domain).
// Output: sdn-dca.json  (publish_date, record_count, fetched_at, address maps). Fails (non-zero exit, no commit) if the
// download or the sanity floors fail, so a stale file is never refreshed with bad data.
import { downloadSdnList } from "./ofac-parse.mjs";
import { writeFileSync } from "node:fs";
const list = await downloadSdnList({});
const out = { ...list, mirror: "https://github.com/botsrated/anchors/tree/ofac-data", note: "Digital Currency Address ids only. Consumers must check fetched_at and fail closed when it is too old." };
writeFileSync("sdn-dca.json", JSON.stringify(out, null, 0) + "\n");
console.log(JSON.stringify({ publish_date: out.publish_date, record_count: out.record_count, addresses_total: out.addresses_total, evm_count: out.evm_count, fetched_at: out.fetched_at }));
