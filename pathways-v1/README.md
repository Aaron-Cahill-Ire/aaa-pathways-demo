# AAA Pathways staff dashboard

Verified 23 October 2026. The dashboard reads six fixed fictional advocates, ingests the existing private Airtable assessment form into immutable attempts, and stores verified Thinkific enrolment percentages in Airtable. **Actual lesson activity is not yet verified:** the demo course remains Draft, which blocks learner access.

The updated integration preview runs on http://127.0.0.1:8767. The older preview on 8766 was left running; it has older Python modules loaded. Use 8767 for these integrations.

## Run

Python 3.11+ on macOS or Linux; the service uses only the standard library. Run from this directory:

```sh
python3 integrations.py sync
python3 server.py --port 8767
```

On the current host, the bundled interpreter is `/Users/aaroncahill/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`.

The browser reads a snapshot. **Refresh sources** explicitly pulls new source data and ingests raw form submissions; there is no scheduler, webhook receiver or automatic polling. The server binds to loopback and checks request host/origin. It has no production sign-in or roles. Keep fictional data only.

## Credentials and scope

Adapters read `../.secrets/airtable.env` and `../.secrets/thinkific.env`, or equivalent environment variables. `.env.example` contains names only. Secrets stay server-side and are excluded from browser responses, source bundles and review files. Configure organisation-owned connections for a handover.

All activity is restricted to course **3558004**, the six identities in `../thinkific-demo/source_registry.json`, and the two dedicated demo tables. The fixed Airtable record IDs distinguish advocates from submissions, even when a raw response repeats the same Demo ID. Remote identity markers and mappings are rechecked before writes. No non-demo tables are read or changed. Fictional Thinkific accounts use `example.test` addresses and were created with `send_welcome_email: false`; no participant-message send was performed.

## What works

| Integration | Verified result | Limit |
| --- | --- | --- |
| Staff dashboard | Six advocates; Airtable reads, guarded stage/next-action edits, search, filters and CSV | Local demo access only |
| Thinkific enrolments | Amina and Kwame are enrolled; actual API reports 0%, no start/completion date | Draft course blocks lesson activity testing |
| Thinkific to Airtable | Source IDs, percentages, dates and independent quiz-access status saved in `Thinkific progress JSON`; dashboard shows those percentages | Four unmapped advocates retain labelled synthetic counts; source API supplies no completed-lesson count |
| Native Thinkific quizzes | Named GraphQL `quizSubmissions` query succeeds, filtered by demo course and mapped fictional users | No stored submissions returned; admin preview 2/2 is not an enrolled learner result |
| Native Airtable form | Nuru's two browser submissions match the registered advocate, retain 0/2 and 2/2, and appear separately | Name and Demo ID are claims, not authenticated learner identity |
| Attempts and review | Six immutable attempt mirrors; three matched attempts, three unmatched/conflicting claims for review | Staff resolution UI is not implemented; review decisions must be designed before real participants |
| Retry and recovery | HTTP replay creates no duplicate; changed payload under the same retry key returns 409; remote envelopes rebuild attempt history | Production alerting, unattended retry scheduling and complete disaster recovery remain work |

The selected assessment is the **existing private Airtable form**, rather than Google Forms. It already creates the necessary submission rows and calculates the sample score. Adding a Google response sheet would introduce another identity and delivery boundary without helping this demo. Its collaborator-only access setting was retained. Do not broaden access as an incidental setup step.

## Data flow and identity contract

1. Six advocate rows in `DEMO Pathways Assessments` remain the profile authority. Their stable Airtable IDs are pinned in `source_registry.json`; rows created by the form never become new advocates automatically.
2. The existing private form creates a new raw row for each submission. Ingestion reads only rows with a fictional `DEMO - ` name, `AAA-DEMO-` numeric ID and either no email or an `example.test` email. It skips the six registered profile IDs. Source table membership/form ID is not proof of who submitted a row, or proof it came from the browser form: the same inbox also accepts the labelled staff API tests.
3. Matching requires one registered Demo ID and an exact participant name (ignoring case and surrounding whitespace). If supplied, email must agree too. Unknown IDs, mismatched claims and missing answers remain unlinked with a review reason. This is sufficient only for the explicitly fictional exercise. It must not authorise learner access, consequential decisions or production identity merges.
4. The attempt key is `airtable:<raw-record-id>`. SQLite commits its original answers, reflection, source creation time, capture time, assessment version `starting-point-demo-v1`, rubric `demo-AA-v1`, score or null, identity decision and advocate record ID. Original raw values are retained. Missing answers produce null; B/B produces a submitted zero. A is correct for both sample questions; the dashboard wording now follows the native form.
5. An outbox mirrors the complete immutable envelope to `DEMO Assessment Attempts`, using `Source key` and `Payload JSON`. The envelope contains the advocate foreign ID and matching evidence. The dashboard derives latest matched answers and shows all attempts. Profile Q1/Q2/Reflection remain the original seed; new submissions do not overwrite them, Stage or Next action.
6. A new raw source ID is a new attempt, including an identical retake. Re-delivery of the same ID and payload is a replay. Changed source content creates a distinct conflict journal entry and leaves the original attempt intact. An altered remote mirror fails validation visibly. A payload hash detects drift; it is not identity authentication or protection against a malicious base editor.
7. Thinkific is independent. Fixed user/enrolment IDs are checked against the demo course and fictional account. `percentage_completed` is a fraction from 0 to 1, multiplied by 100 for display. It is never treated as a lesson count or quiz score. Available quiz results/status are captured separately inside the source envelope. Staff fields retain their own authority.

The source table is a legacy mixed inbox/profile layout. The fixed registry makes the separation explicit without moving or breaking the existing private form. For production, use separate normalised advocate, raw submission, assessment, enrolment and review-decision records with typed links and approved access rules.

## Setup and actual permissions

Already configured in this account:

- `DEMO Pathways Assessments` (`tblwbn6JRl9WeyBjJ`): existing profile and form inbox fields, plus long-text fields `Thinkific progress JSON` and `Submission request key`.
- `DEMO Assessment Attempts` (`tblZ0fe6zb7erPRAz`): primary text `Source key` and long-text `Payload JSON`. Native new-table defaults are unused.
- Private form: `https://airtable.com/appAAuxNKQ0KNGSil/pagk5GhaNoKEmxpLv/form`. Participant, Demo ID, Q1 and Q2 remain required. Submit exact fictional name/ID pairs from the registry. Native form/lesson introductory copy predates this integration; this runbook and the updated dashboard describe current behaviour.

`python3 pipeline.py setup` validates/creates the dedicated demo schema when the token has schema-write capability. **The current token returned HTTP 403 for schema creation.** The demo-only fields and table were instead created through the signed-in Airtable UI. Record reads/writes and schema reads work. A new account can create the same schema manually with creator access, then run ingestion; no credential-permission expansion is required just to run this configured prototype.

Thinkific mappings:

| Fictional advocate | User ID | Enrolment ID | Verified progress |
| --- | --- | --- | --- |
| AAA-DEMO-001 Amina | 260700368 | 894392343 | 0%; not started |
| AAA-DEMO-002 Kwame | 260700371 | 894392352 | 0%; not started |

The course overview visibly confirmed **Draft**, two enrolments and 0% average progress. API enrollment in a draft course succeeded. Thinkific documents that students cannot access draft/unpublished products. No publication, lesson completion or fabricated progress change was performed. A publication decision is required before the outstanding real learner activity and stored quiz-attempt acceptance tests can be completed.

## Walkthrough

1. Open http://127.0.0.1:8767 and inspect Amina/Kwame. Each shows **0% — Verified Thinkific API**. Open either record for source enrolment ID, last check and absence of activity. Their old seeded counts remain in Airtable as a labelled baseline.
2. Open Nuru (`AAA-DEMO-006`). The latest assessment is 2/2; **Assessment attempts** retains the first 0/2 and separate retake 2/2 with original source IDs and reflections. Nuru's course progress remains synthetic.
3. Open the private native form as an existing collaborator. Submit fictional registry details, then use **Refresh sources** in the dashboard. The raw source row becomes an immutable attempt and mirror. Repeating Refresh creates no new attempts.
4. Use the dashboard fictional assessment form. It creates a new source row, not an update to the advocate answers. A stable request key survives retries within that form submission. The same key with changed content is rejected with 409. Starting a new submission is a retake.
5. Open **Connections**. The review queue includes legacy `AAA-DEMO-007`, unknown `AAA-DEMO-999`, and a submitted name that disagrees with `AAA-DEMO-006`. None is merged into an advocate.
6. Staff can still edit Stage and Next action. No assessment or source refresh changes those fields, and no email is sent.

## Retry and recovery

- Preserve `data/source-events.sqlite3` across restarts. It stores source attempts, retry requests, conflicts and mirror state. Reentrant thread/process locks and SQLite transactions serialize the updated workers on one host. Atomic snapshot replacement avoids partial files. An old process from before this change does not use the new locking; use the new preview for integration refreshes.
- GET and idempotent PATCH requests retry HTTP 429 and selected 5xx responses up to three tries with bounded delay, respecting numeric Retry-After up to 30 seconds. Unkeyed POSTs are never automatically retried. Network/permission failures remain visible and pending mirrors are retained.
- After restoring connectivity, run `python3 pipeline.py ingest` or **Refresh sources**. A mirror acknowledged remotely before a local failure is found by its source key and compared before any write, so the retry does not create another attempt. Conflicting content is held for review.
- Each ingest validates existing remote envelopes. If a local attempt journal is absent, validated Airtable mirrors can rebuild its attempt rows and original timestamps. This was tested against the actual six remote mirrors using an isolated temporary database. It does not rebuild the local staff edit journal, conflict journal or all prior retry-request receipts.
- For a local backup, use SQLite's online backup API, or stop only your integration worker before copying the SQLite file and any WAL sidecar. Copying only a live main SQLite file is not a reliable backup. Keep the JSON snapshot and staff journal too. The older learner preview's backup endpoint covers that separate learner database only.
- If an identity mapping changes, ingestion stops. Review the registry and remote profile together; do not silently relink an immutable attempt. There is no production resolution endpoint. A future resolver must append an auditable staff decision, not edit original answers.
- Failed source refreshes retain prior verified values and show stale/error labels. There is no background alert, shared multi-host worker, credential rotation service, production restore procedure or external-editor audit trail.

## Verification and evidence

From `pathways-v1`:

```sh
python3 -m unittest discover -s tests -v
# Opt-in: real vendor calls and one retry-safe fictional Amina submission
python3 tests/live_demo_check.py --fictional-demo-only
```

34 automated checks cover the retained learner flow, guards, pagination, score semantics, immutable retakes, conflicting claims, changed source records, replay, outbox recovery, tamper detection, bounded rate-limit retry and stale live progress. Mock APIs are used in this suite. The opt-in live test separately checks HTTP → real source row → immutable mirror → dashboard, 409 on changed replay, all six remote attempts, two verified enrolments, native quiz API access and isolated remote recovery.

`../thinkific-demo/live_integration_evidence.json` holds fictional source IDs, timestamps, complete attempt evidence and acceptance limitations. Nuru's two native browser submissions are raw records `recLS6sBhB4DosonM` and `recMEWxg6HxhxOqAS`; Amina's HTTP submission is `recx0dOXsa2JY2csj`. The evidence distinguishes them from seeded answers and admin preview tests.

## Handoff and remaining work

The updated Word contractor handoff and AAA decision brief govern this prototype. The offline review and contractor ZIP are rebuilt from the current snapshot/source without credentials. Bundles contain the fixed fictional registry and evidence, excluding the live SQLite journal and secrets. Fresh source runs can hydrate assessment history from Airtable mirrors after configuring credentials.

Production still requires authenticated learner identity, a suitable external form access model, an auditable review-resolution workflow, scheduled ingestion/retries, monitoring, staff sign-in/roles, retention and correction rules, durable backup/restore, maintenance ownership and any separately approved messaging. The unfinished Thinkific acceptance step is actual enrolled-learner lesson activity and a stored native quiz attempt under an authorised publication setup.

The earlier independent SQLite learner demo remains at `/learner#/learn`; see `README-learner-preview.md`. Its six-section completion and quizzes do not establish Thinkific activity.

Vendor references checked 23 October 2026: [Thinkific Admin API and schema](https://developers.thinkific.com/api/api-documentation), [GraphQL introduction](https://support.thinkific.dev/hc/en-us/articles/22111777531415-GraphQL-API-Introduction), [GraphQL token authorization](https://support.thinkific.dev/hc/en-us/articles/22112790485655-GraphQL-Authorization), [unpublished learner access](https://support.thinkific.com/hc/en-us/articles/360036944513-How-to-Unpublish-Your-Product), [Airtable forms create records](https://support.airtable.com/articles/3684762465-updating-records-using-a-form-in-airtable), and [Airtable API pagination and limits](https://support.airtable.com/articles/6292134965-getting-started-with-airtable-s-web-api).
