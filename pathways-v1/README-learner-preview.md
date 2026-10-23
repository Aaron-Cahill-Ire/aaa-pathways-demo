# Pathways V1

A working local demonstration of the Pathways course and advocate CRM described in the contractor PRD. It runs in a new, self-contained subfolder and does not modify AAA's website, forms or accounts.

## Start

Requires Python 3.11 or newer with SQLite. No package installation or credentials are needed.

```sh
cd "/Users/aaroncahill/Documents/ChatGPT/Animal Advocacy Africa/pathways-v1"
python3 server.py
```

Open [the local workspace](http://127.0.0.1:8765). If the port is occupied, use `python3 server.py --port 8766` and open the printed address. The server deliberately binds only to `127.0.0.1`.

On this Codex host the bundled Python executable is:

```sh
/Users/aaroncahill/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 server.py
```

Stop with Ctrl+C. Restart with the same command; records persist in `data/pathways.sqlite3`. `PATHWAYS_DB` can select a different SQLite file. Database files are ignored by Git.

## Try the whole journey

1. Open **Add demo advocate**. Enter fictional details, for example `demo.learner@example.test`, and confirm the preview acknowledgement.
2. Open orientation, read the sample lesson, write a reflection and answer both knowledge checks.
3. Save the exercise. Course progress updates immediately.
4. Open **Team workspace**, find that learner under **Advocates**, and inspect the same saved reflection and score.
5. Revisit the exercise and submit another attempt. Both attempts remain in the record.
6. Assign a staff owner, save a next action, add a note or update the human-managed programme stage.
7. Open **Follow-up**. Check inactivity rules, review a message, or pause a person's messages. Nothing is sent.
8. Open **Reports** to see counts derived from the stored records, download CSVs or download a full linked export and SQLite backup.

There are eight seeded fictional participants. Some have completed the course, some are active, and some are inactive so the reminder queue can be demonstrated. Sample names and details are invented and do not describe AAA participants.

## What works

- Learner enrolment with a durable advocate ID and a case-insensitive email duplicate check.
- Six sample course sections with short reading, two knowledge checks and a reflection per section.
- Server-side fixed scoring; a zero is stored as zero, while unsubmitted sections remain missing.
- Progress based on submitted sections, independent of quiz score. No automated admission decisions.
- Every assessment attempt preserved with item code, course version, rubric version and timestamp.
- Idempotent submission events: an identical event can be retried without duplicate records; conflicting reuse is rejected.
- Shared staff record, background, next action, staff owner, programme stage, notes and activity history.
- Inactivity reminder queue with deduplication, pause controls, and suppression when a participant returns or completes.
- Message review recorded without sending.
- Dashboard, searchable/filterable advocate list, record detail, follow-up view, reports and integration handover screen.
- Linked CSV exports with spreadsheet-formula escaping and a consistent SQLite snapshot made with SQLite's backup API.
- Durable SQLite storage, transactions, foreign keys, bounded inputs and same-origin checks.

## Public source and sample content

Reviewed on 23 October 2026:

- [AAA public Pathways page](https://www.animaladvocacyafrica.org/pathways-programme): supplied the broad stages and context. It describes a closed programme with an expression-of-interest route; this V1 explores the proposed always-available experience discussed in the scoping call.
- The first page of the linked public Google Form was viewed in the browser. It requests an email before later pages. No details were entered; no form was submitted; later pages were not retrieved.
- The 30 September scoping-call transcript and the accompanying contractor PRD informed the workflow.

All lesson prose, exercises, knowledge checks, scoring rubrics, records and reminder text are original demonstration content. They are **not** AAA's official curriculum or validated selection criteria. The application labels this clearly. It does not award an AAA certificate or generate AI career advice.

## Credentials needed for real integrations

Nothing below is needed to run this local V1. When connecting real systems, AAA should create and own the accounts and grant scoped access through the relevant service; do not send raw secrets in a chat or commit them to this folder.

| Connection | What AAA needs to provide | Purpose |
| --- | --- | --- |
| Course content | Current course export or documents, final questions and scoring definitions | Replace sample material and agree completion rules |
| Thinkific, if retained | Admin-assisted confirmation of plan/API access; a named, scoped token or supported OAuth connection | Enrolment and progress events; assessment access must be proved separately |
| Google Forms and Sheets | Access to selected forms and response files, approved OAuth or an AAA-created trigger | Receive actual assessment submissions |
| Airtable, if selected | Selected base and table IDs; scoped OAuth or token access | Replace or connect the local CRM after capacity and permissions checks |
| Email sender | AAA-owned provider account, sender identity, domain/DNS assistance and protected API connection | Send approved messages and receive delivery/suppression events |
| Automation and hosting | AAA-owned runtime, billing/admin access, secret store and alert destination | Run intake, reconciliation and reminders unattended |
| Optional AI | Organisation-owned API workspace, protected key, spend limit, approved research and review rubric | Later career-advising or assessment support |

No Squarespace admin access is needed to prototype the course and CRM. Later, limited site-editor access may be useful to change the public signup link or embed the chosen enrolment journey. A read-only walkthrough of the previous course, assessment exports and Stuart's current workflow is more valuable than copying the marketing website.

## Scope and production gaps

This V1 deliberately uses local SQLite and an original sample course to demonstrate the process without choosing AAA's final platform. It is not an integration with Airtable, Thinkific, Google Forms, Slack, Mailchimp or Claude. The course module is replaceable; it is not evidence that Thinkific should be replaced.

Staff and learner views are freely switchable for demonstration. There is no real authentication or participant isolation. Do not expose this server to the internet or store real participant data in it. Same-origin and loopback checks reduce accidental local misuse; they do not make this a production service.

Before launch, the contractor must implement or configure:

- Real sign-in, role-based permissions and authenticated source-ID matching. Preview email checks are not production identity verification.
- Approved notices, consent/purpose rules, retention, correction, deletion and operational access controls.
- Actual source adapters, signed webhook verification, durable retry and exception handling, plus source reconciliation. Reminder checks currently run when a staff member presses the button; there is no unattended scheduler.
- Approved official course content and scoring. Historical multi-course and item-version mappings need validation and migration; this V1 fixes one sample course version.
- Real selection stage histories, attendance, programme outcomes and evaluation exports. The current stage field is a simplified preview with a logged audit trail, not a full programme-management module.
- Delivery provider, bounce and unsubscribe handling, send-time suppression, frequency limits and transactional/marketing separation. No send endpoint exists in this V1.
- Recovery objectives, operational backups, tests against representative volumes and monitoring with a named owner and backup.

Optional career guidance, public resource maintenance, a public directory and automated introductions are not implemented.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use temporary SQLite databases. They cover the HTTP-to-database flow, duplicate signup handling, retry idempotency, retakes, validation, zero-score completion, reminder deduplication and suppression, held reviews, CSV safety and restoration from the backup.

## Local backup and restore

Use **Download local backup** under Connections. The archive contains linked CSVs, the sample course definition and `pathways.sqlite3`.

For a local restore: stop the server, preserve the existing `data/` directory, then start using the extracted snapshot through `PATHWAYS_DB=/absolute/path/to/pathways.sqlite3 python3 server.py`. The automated test restores a generated snapshot and checks its integrity and record links. Production disaster recovery remains a separate acceptance requirement.

## Files and endpoints

- `server.py`: SQLite schema, business rules, seeding, local HTTP server and exports.
- `course.py`: replaceable sample lessons, questions and scoring keys.
- `static/`: responsive browser interface, no external packages or services.
- `tests/test_workflow.py`: integration and recovery tests.

| Endpoint | Behaviour |
| --- | --- |
| `GET /api/state` | Entire fictional preview state; deliberately not a production participant API |
| `POST /api/signup` | Create a fictional advocate and enrolment |
| `POST /api/submissions` | Save versioned assessment attempt with an idempotency key |
| `POST /api/people/{id}` | Update the approved staff fields |
| `POST /api/notes/{id}` | Add an auditable staff note |
| `POST /api/followups/run` | Check the local inactivity rule and queue held messages |
| `POST /api/messages/{id}/review` | Mark reviewed or suppress; never send |
| `GET /api/export?table=people` | Export a selected table as CSV |
| `GET /api/backup` | Export all linked tables and a consistent SQLite snapshot |

All mutations require JSON. Source event IDs are namespaced and checked against a payload hash. The HTTP layer uses one transactional connection per request and serialises writes for this local workload.
