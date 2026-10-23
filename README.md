# Animal Advocacy Africa — Pathways demo

A populated staff dashboard with six fictional advocates, real Airtable source records, saved assessment attempts and independently retrieved Thinkific enrolment evidence. The Thinkific course is Draft, so the two verified enrolments show 0%; other lesson counts remain labelled synthetic scenarios.

## Clone and build upon it

```sh
git clone https://github.com/Aaron-Cahill-Ire/aaa-pathways-demo.git
cd aaa-pathways-demo
PYTHONPATH=pathways-v1 python3 -m unittest discover -s pathways-v1/tests -v
cd pathways-v1
python3 server.py --port 8767
```

Use Python 3.12 (standard library only). The dashboard code lives in `pathways-v1/static/`, local HTTP routes in `pathways-v1/server.py`, vendor adapters in `pathways-v1/integrations.py`, and assessment ingestion in `pathways-v1/pipeline.py`. The earlier course/learner preview is available locally at `/learner#/learn`.

For a populated local dashboard without credentials, copy `web-demo/data/snapshot.json` to `pathways-v1/data/dashboard-snapshot.json` after creating that directory. This saved JSON includes the attempt history, but the local server derives attempts from SQLite. To restore those attempts and enable live reads and guarded writes, configure your own credentials as below and run `python3 integrations.py sync` from `pathways-v1/`.

## Hosted version

Vercel builds the dashboard using `python3 scripts/build_hosted.py`. It serves the same interface with editing disabled, downloadable handoff documents, search, filters, insights, assessment history and CSV export. `api/dashboard.py` supplies its data.

Without credentials it shows `web-demo/data/snapshot.json`: the populated capture of the local integration, clearly marked **Saved source snapshot**. With all required environment variables it reads the six pinned advocates from Airtable, their raw and mirrored assessment attempts, and the independent Thinkific course/enrolment/quiz APIs. **Refresh sources** re-reads those sources, with a short cache to bound repeat clicks. It never writes to either provider. API failures retain a visible stale snapshot. Each function refresh rebuilds temporary assessment storage from source records, so it does not rely on persistent SQLite on Vercel.

Configure these server-side environment variables in Vercel under Settings → Environment Variables for Production (and Preview if needed), then redeploy:

| Variable | Required | Purpose |
| --- | --- | --- |
| `AIRTABLE_TOKEN` | Yes | Read records and base schema in the dedicated demo base |
| `AIRTABLE_BASE_ID` | Yes | Base containing the two dedicated demo tables |
| `THINKIFIC_API_TOKEN` | Yes | Read demo course, mapped enrolments and quiz query |
| `THINKIFIC_SUBDOMAIN` | Optional | Account metadata; retained for local adapter compatibility |

Enter credentials directly in Vercel; do not commit them. No frontend `PUBLIC` variables are needed. Locally the adapters accept the same environment variables or `.secrets/airtable.env` and `.secrets/thinkific.env`. See `pathways-v1/.env.example` for names and `pathways-v1/README.md` for the full source contract and verified limitations.

The registry in `thinkific-demo/source_registry.json` pins source identities. To adapt this demo for another base/course, update the registry, scoped adapter checks and tests together. Do not substitute real participants into a public demo: this preview has no staff sign-in. The local write-capable service remains loopback only. No version sends emails.

## Handoff and maintenance

`handoff/` includes the contractor brief, decision brief, PRD and API setup guide. The documents describe the original local prototype; this README documents the added hosted read-only adapter. GitHub repository access must be granted to collaborators before they can clone this private repository. Connected credentials and databases are deliberately excluded; each maintainer configures their own access.

Run the existing local suite and the hosted adapter suite before deploying:

```sh
PYTHONPATH=pathways-v1 python3 -m unittest discover -s pathways-v1/tests -v
python3 -m unittest discover -s tests -v
python3 scripts/build_hosted.py
node --input-type=module --check < dist/dashboard.js
```

The connected demo tests in `pathways-v1/tests/live_demo_check.py` are opt-in and perform a fictional source write. They are not part of the hosted read-only verification.
