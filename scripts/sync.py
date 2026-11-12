#!/usr/bin/env python3
"""Copy every finalized BotsRated anchor (genesis + daily) into this repo, checking each one first.

For each final entry not yet here: fetch the day document, its leaves (genesis: its chunks),
head.json (the exact bytes the OpenTimestamps proof stamps; sha256(head.json) == anchor) and the
.ots proof; recompute the Merkle root and anchor; refuse to write anything that does not match.
Standard library only. Run by .github/workflows/anchor.yml with the built-in GITHUB_TOKEN.
"""
import hashlib, json, os, sys, urllib.request, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from verify import canon, mth

BASE = os.environ.get("ANCHOR_BASE", "https://botsrated.com/v1/anchor")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = lambda b: hashlib.sha256(b).digest()

def raw(url):
    req = urllib.request.Request(url, headers={"user-agent": "botsrated-anchors-sync/1 (+https://github.com/botsrated/anchors)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def combine_up(nodes):
    if not nodes: return H(b"")
    while len(nodes) > 1:
        nodes = [H(b"\x01" + nodes[i] + nodes[i + 1]) if i + 1 < len(nodes) else nodes[i] for i in range(0, len(nodes), 2)]
    return nodes[0]

def write(rel, data):
    p = os.path.join(ROOT, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f: f.write(data if isinstance(data, bytes) else data.encode())

def head_of(doc):
    return canon({k: doc[k] for k in ("v", "day", "leaf_count", "merkle_root", "prev_anchor")})

def take(day, doc, leaves_files):
    head = head_of(doc).encode()
    if H(head).hex() != doc["anchor"]: raise SystemExit(f"{day}: anchor != sha256(head)")
    served_head = raw(f"{BASE}/{day}/head.json")
    if served_head != head: raise SystemExit(f"{day}: served head.json differs from the document")
    ots = raw(f"{BASE}/{day}/anchor.ots")
    if not ots.startswith(b"\x00OpenTimestamps\x00\x00Proof\x00") or ots[33:65] != H(head): raise SystemExit(f"{day}: .ots does not stamp head.json")
    for rel, data in leaves_files: write(rel, data)
    write(f"days/{day}.json", json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    write(f"proofs/{day}.head.json", head)
    write(f"proofs/{day}.head.json.ots", ots)
    with open(os.path.join(ROOT, "log.csv"), "a") as f:
        f.write(f"{day},{doc['leaf_count']},{doc['merkle_root']},{doc['anchor']},{doc['prev_anchor'] or ''},{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
    print(f"added {day} leaves={doc['leaf_count']} root={doc['merkle_root']} anchor={doc['anchor']}")

def main():
    idx = json.loads(raw(BASE))
    if not os.path.exists(os.path.join(ROOT, "log.csv")):
        write("log.csv", "day,leaf_count,merkle_root,anchor,prev_anchor,committed_at\n")
    have = lambda d: os.path.exists(os.path.join(ROOT, "days", d + ".json"))
    g = idx.get("genesis")
    if g and g["status"] == "final" and not have("genesis"):
        doc = json.loads(raw(f"{BASE}/genesis"))
        roots, files = [], []
        for n in range(doc["chunks"]):
            b = raw(f"{BASE}/genesis/chunks/{n}"); c = json.loads(b)
            r = mth([bytes.fromhex(l["h"]) for l in c["leaves"]])
            if r.hex() != c["root"] or c["root"] != doc["chunk_roots"][n]: raise SystemExit(f"genesis chunk {n} root mismatch")
            if n < doc["chunks"] - 1 and len(c["leaves"]) != doc["chunk_size"]: raise SystemExit(f"genesis chunk {n} is not full")
            roots.append(r); files.append((f"genesis/chunk-{n:05d}.json", b))
        if sum(len(json.loads(f[1])["leaves"]) for f in files) != doc["leaf_count"]: raise SystemExit("genesis leaf_count mismatch")
        if combine_up(roots).hex() != doc["merkle_root"]: raise SystemExit("genesis merkle_root mismatch")
        take("genesis", doc, files)
    prev = None
    for d in idx["days"]:
        if d["status"] != "final": continue
        if have(d["day"]):
            prev = json.load(open(os.path.join(ROOT, "days", d["day"] + ".json")))
            continue
        doc = json.loads(raw(f"{BASE}/{d['day']}"))
        lb = raw(f"{BASE}/{d['day']}/leaves"); lv = json.loads(lb)["leaves"]
        if mth([bytes.fromhex(l["h"]) for l in lv]).hex() != doc["merkle_root"] or len(lv) != doc["leaf_count"]: raise SystemExit(f"{d['day']}: merkle_root mismatch")
        expect_prev = (prev or json.load(open(os.path.join(ROOT, "days", "genesis.json"))))["anchor"] if (prev or have("genesis")) else None
        if doc["prev_anchor"] != expect_prev: raise SystemExit(f"{d['day']}: chain broken (prev_anchor)")
        take(d["day"], doc, [(f"leaves/{d['day']}.json", lb)])
        prev = doc

if __name__ == "__main__":
    main()
