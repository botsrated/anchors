#!/usr/bin/env python3
"""Check a BotsRated daily anchor without trusting BotsRated's math.

  python3 verify.py genesis 2026-11-12   # fetch from botsrated.com, recompute, compare
  python3 verify.py 2026-11-12 --local    # use days/<day>.json and leaves/<day>.json from this repo

Recomputes the RFC 6962 Merkle root from the published leaf hashes, recomputes the day's
anchor hash, and checks the chain to the previous day. To check one record you hold, hash its
canonical JSON (keys sorted, no whitespace, sig included) and look for that hash in the leaves.
This proves when a set of records existed (once the anchor is committed / OpenTimestamped),
not that the records are correct. Standard library only.
"""
import hashlib, json, sys, urllib.request, os

BASE = os.environ.get("ANCHOR_BASE", "https://botsrated.com/v1/anchor")
H = lambda b: hashlib.sha256(b).digest()

def canon(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def mth(leaves):
    if not leaves:
        return H(b"")
    if len(leaves) == 1:
        return H(b"\x00" + leaves[0])
    k = 1
    while k * 2 < len(leaves):
        k *= 2
    return H(b"\x01" + mth(leaves[:k]) + mth(leaves[k:]))

def get(url):
    req = urllib.request.Request(url, headers={"user-agent": "botsrated-anchor-verify/1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def load(day, local):
    here = os.path.dirname(os.path.abspath(__file__))
    if local:
        return (json.load(open(os.path.join(here, "days", day + ".json"))),
                json.load(open(os.path.join(here, "leaves", day + ".json"))))
    return get(f"{BASE}/{day}"), get(f"{BASE}/{day}/leaves")

def combine_up(nodes):
    if not nodes: return H(b"")
    while len(nodes) > 1:
        nodes = [H(b"\x01" + nodes[i] + nodes[i + 1]) if i + 1 < len(nodes) else nodes[i] for i in range(0, len(nodes), 2)]
    return nodes[0]

def check_genesis(local):
    here = os.path.dirname(os.path.abspath(__file__))
    doc = json.load(open(os.path.join(here, "days", "genesis.json"))) if local else get(BASE + "/genesis")
    errs, roots, n = [], [], 0
    for i in range(doc["chunks"]):
        c = json.load(open(os.path.join(here, "genesis", f"chunk-{i:05d}.json"))) if local else get(f"{BASE}/genesis/chunks/{i}")
        r = mth([bytes.fromhex(l["h"]) for l in c["leaves"]]); roots.append(r); n += len(c["leaves"])
        if r.hex() != doc["chunk_roots"][i]: errs.append(f"chunk {i} root mismatch")
        if i < doc["chunks"] - 1 and len(c["leaves"]) != doc["chunk_size"]: errs.append(f"chunk {i} not full")
    root = combine_up(roots).hex()
    if root != doc["merkle_root"]: errs.append(f"merkle_root mismatch: recomputed {root}")
    if n != doc["leaf_count"]: errs.append("leaf_count mismatch")
    anchor = H(canon({k: doc[k] for k in ("v", "day", "leaf_count", "merkle_root", "prev_anchor")}).encode()).hex()
    if anchor != doc["anchor"]: errs.append("anchor mismatch")
    print(f"genesis leaves={n} merkle_root={root} anchor={anchor} -> {'OK' if not errs else 'FAIL'}")
    for e in errs: print("  -", e)
    return not errs

def check(day, local=False):
    if day == "genesis":
        return check_genesis(local)
    doc, lv = load(day, local)
    leaves = lv["leaves"]
    order = sorted(leaves, key=lambda l: (l["s"], l["id"] or "", l["h"]))
    errs = []
    if order != leaves: errs.append("leaves are not in (s, id, h) order")
    root = mth([bytes.fromhex(l["h"]) for l in leaves]).hex()
    if root != doc["merkle_root"]: errs.append(f"merkle_root mismatch: recomputed {root}")
    if lv.get("merkle_root") != doc["merkle_root"]: errs.append("leaves file root differs from day doc")
    if len(leaves) != doc["leaf_count"]: errs.append("leaf_count mismatch")
    head = {k: doc[k] for k in ("v", "day", "leaf_count", "merkle_root", "prev_anchor")}
    anchor = H(canon(head).encode()).hex()
    if anchor != doc["anchor"]: errs.append(f"anchor mismatch: recomputed {anchor}")
    if doc.get("prev_day"):
        here = os.path.dirname(os.path.abspath(__file__))
        prev = (json.load(open(os.path.join(here, "days", doc["prev_day"] + ".json"))) if local else get(f"{BASE}/{doc['prev_day']}"))
        if prev["anchor"] != doc["prev_anchor"]: errs.append("chain broken: prev_anchor != previous day's anchor")
    print(f"{day} status={doc['status']} leaves={len(leaves)} merkle_root={root} anchor={anchor} -> {'OK' if not errs else 'FAIL'}")
    for e in errs: print("  -", e)
    return not errs

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ok = all(check(d, "--local" in sys.argv) for d in args)
    sys.exit(0 if ok else 1)
