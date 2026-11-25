# BotsRated anchors

Daily Merkle roots over the hashes of BotsRated's signed records, copied here by a scheduled GitHub Actions
workflow and stamped with [OpenTimestamps](https://opentimestamps.org) (Bitcoin).

The workflow runs every three hours at :50 UTC (`50 */3 * * *`) and also once a day at 12:30 UTC
(`30 12 * * *`), after a day typically turns final (~11:23 UTC). GitHub's scheduled runs can drift or skip a
slot; if a day is missing, run the `anchor` workflow by hand (Actions → Run workflow).

What this shows: a record whose hash is in a day's leaves existed no later than that day's commit here and
its Bitcoin timestamp. It does not show that the record's contents are correct.

## Files

- `genesis/`, `days/genesis.json`: one-time root over every signed record stored before 2026-11-12 00:00 UTC.
  Those records are shown to exist as of 2026-11-12/13, not on their original dates.
- `days/YYYY-MM-DD.json`: one UTC day, from 2026-11-12 on. `prev_anchor` links each day to the one before
  (the first day links to genesis).
- `leaves/YYYY-MM-DD.json`: that day's leaf hashes.
- `proofs/<day>.head.json` and `.head.json.ots`: the stamped bytes (`sha256(head.json) == anchor`) and the
  OpenTimestamps proof. Proofs start as pending and are upgraded once Bitcoin confirms.
- `log.csv`: day, leaf count, root, anchor, previous anchor, commit time.

Source: `https://botsrated.com/v1/anchor` (index), `/v1/anchor/<day>`, `/v1/anchor/<day>/leaves`,
`/v1/anchor/genesis`, `/v1/anchor/genesis/chunks/<n>`, `/v1/anchor/<day>/head.json`, `/v1/anchor/<day>/anchor.ots`.

## Rules (`botsrated-anchor-1`)

- Leaf: sha256 of the record's canonical JSON (keys sorted, no whitespace, `sig` included). Bulk probe
  receipts are covered through the signed daily archive manifest, which lists the sha256 of every archive part.
  Each day document's `rules` field gives the exact list.
- Order: by `(s, id, h)` for a day; genesis by source, then primary key.
- Tree: RFC 6962 Merkle tree hash (`sha256(0x00||leaf)`, `sha256(0x01||left||right)`).
- Anchor: sha256 of canonical JSON `{v, day, leaf_count, merkle_root, prev_anchor}` = sha256 of `head.json`.

## Check it

```bash
python3 verify.py 2026-11-12 --local            # recompute root, anchor and chain from this repo
pip install opentimestamps-client
ots verify proofs/2026-11-12.head.json.ots      # Bitcoin timestamp (needs a Bitcoin node, or use ots info)
```

To check a record you hold: hash its canonical JSON and look for the hash in that day's leaves.

## Workflow pins

The `anchor` workflow can write to this repository, so what it runs is pinned:

- `actions/checkout` and `actions/setup-python` are pinned to a commit, not a moving tag.
- `opentimestamps-client` is pinned to an exact version (`0.8.0`). Its own dependencies are not hash-locked yet. To lock them, run `pip-compile --generate-hashes` on a machine with pip and switch the install step to `pip install --require-hashes -r requirements.txt`.
- The commit step adds only `days/`, `leaves/`, `proofs/`, `genesis/` and `log.csv`. A change anywhere else is reported as a warning in the run and is not committed.
- `scripts/sync.py` accepts a day name from the index only when it is exactly `YYYY-MM-DD`, before it is used in a URL or a file path.

To update a pin, change it in `.github/workflows/anchor.yml` in a pull request.

## OFAC mirror (branch `ofac-data`)
`.github/workflows/ofac.yml` copies the digital currency addresses from the U.S. Treasury OFAC SDN list to the separate branch [`ofac-data`](https://github.com/botsrated/anchors/tree/ofac-data) every 6 hours. The BotsRated test-buy Worker screens every payee against it before paying (Treasury does not answer Cloudflare egress) and refuses to pay when the copy is older than 48 hours. It does not change the anchor data on `main`.
