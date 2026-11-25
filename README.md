# OFAC SDN digital-currency-address mirror (branch ofac-data)

A small mirror of the **digital currency addresses** in the U.S. Treasury OFAC SDN list, refreshed every 6 hours by `.github/workflows/ofac.yml` on `main`. This branch holds only this data and is separate from the anchor history on `main`.

- Source: `https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML` (public U.S. government data).
- File: [`sdn-dca.json`](sdn-dca.json): `publish_date`, `record_count`, `fetched_at`, `addresses_total`, `evm_count`, `by_coin`, `evm` (lowercase 0x address → coin, SDN uid), `other`.
- Why: BotsRated's test-buy Worker screens every payee against this list before paying, and Treasury's host does not answer Cloudflare egress.
- Rule for consumers: check `fetched_at` and **refuse to pay when it is older than 48 hours**. If an update fails, the file is not rewritten, so its age shows the failure.

Not legal advice. For authoritative data use Treasury's Sanctions List Service.
