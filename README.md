# Folonto Legal

A web assistant for Turkish lawyers that answers questions, searches case law and legislation,
and drafts or edits petitions. Every statute article and court decision it cites is retrieved
from an official or public source and rendered by the backend, never written from model memory.

The production API includes a Turkish-capable serif font and tests PDF generation during the image build. If preparing a file fails after a draft is saved, downloading it retries the export from that draft.

The Folonto Legal monogram appears on sign-in, in the workspace and in the browser tab.
The chat welcome screen, conversation and message box share a centered column. Answers use
the available width when there are no sources. On wide screens, answers with sources show
them in a side column. On smaller screens, cited sources appear below the answer. Focusing
the message box highlights its rounded border.

Chat loads petition style samples only for drafting requests.
Standalone greetings, check-ins such as `Nasılsın?`, thanks and capability questions receive a direct reply without a model call or a source notice. The chat also omits generic missing-source notices from matching earlier replies.
Requests outside legal work, such as a football score, receive a short redirect before
research or answer generation. The assistant handles legal questions about sports, legal
follow-ups and requests to examine attachments. Instructions inside an attachment are
treated as document content. Analysis, writing, the agenda and calculations share the
Istanbul calendar date when the message was received. For example, on 27 November 2026,
“dün” in that message refers to 26 November 2026. Explicit dates in the case are preserved.

An explicit request for an indexed article's text, such as `6098 sayılı Kanun madde 344`, returns the
article and its source directly from the local index. Statute and case-law research run
concurrently. Petition drafts use one shared decision search and cite only decisions verified
against their material facts and legal route. The screening passage includes the majority
disposition, and the source viewer retains the full decision, including dissents. A direct match requires affirmative source support for each case condition.
Explicit precedent searches show directly
matching decisions first and label decisions that turn on different facts. When the reviewed
passages do not establish a direct match, the answer says so. The existing analysis schema
carries the query variants and conditions together in its case-law text field. Successfully
retrieved official decisions are indexed in the local public corpus for later requests,
including during upstream rate limits.

Generation has a 90-second limit, or 120 seconds in deep research. Live decision retrieval
has a shared budget of 14 seconds for petitions, explicit searches and deep research, or
8 seconds for supplemental lookup. Candidate evaluation has a separate five-second budget.
The chat keeps completed source evaluations and returns linked decisions if the prose for
an explicit precedent search takes too long. A slow citation support check marks affected
statements for review while preserving the answer and its citations. The final event reports
`first_delta_s` when text streamed and `total_s` for the generation run. Saved answer traces
include separate durations for statute and case-law research.

## Layout

| Path | Purpose |
|---|---|
| `apps/web` | Next.js user interface |
| `services/api` | FastAPI backend (`legal_api` package) |
| `prompts/tr`, `playbooks/tr`, `locales/tr` | Turkish-language content (LLM instructions, case checklists, UI strings) |
| `eval/golden` | Evaluation question set |

## Local development

Install Docker Compose, Python 3.12 or newer through [uv](https://docs.astral.sh/uv/),
and Node.js 20 or newer with npm.

```bash
cp .env.example .env      # first-time setup, then fill in the settings below
make setup                # install the Python and web lockfiles
make corpus               # migrate Postgres and load the core statutes from Bedesten
make api                  # serve http://localhost:8000
make web                  # serves http://localhost:3000
make test                 # backend tests, with or without a populated statute index
```

Set `SECRET_KEY` in `.env` to a cryptographically random value of at least 32 characters.
On an empty database, set a private `INVITE_CODE` to create the first administrator.
Remove the bootstrap code from the environment after creating that account. For subsequent
registrations, create an invitation from the admin panel. Use `COOKIE_SECURE=true` when serving
the API over HTTPS. An alternate web API URL goes in `apps/web/.env.local` as
`NEXT_PUBLIC_API_URL` before starting or building the web app.

`make corpus` uses the public legislation service and downloads the local embedding model on
first use. Run it again to refresh the index. `GET /health` reports database and pgvector
status. `GET /ready` returns HTTP 503 until the required core laws are indexed and lists
missing law numbers. To populate the optional local decision archive, follow the ingestion
commands in [Architecture](docs/ARCHITECTURE.md#running-locally).

Maintain the dated calculator tables in `locales/tr`. Fee and severance results require a table
covering the requested period. Interest calculations report the covered days and identify any
part of the request outside the table.

The API supports Anthropic and OpenAI-compatible chat-completions providers. For Open WebUI,
an administrator can set **Model settings** to a base URL ending in `/api` such as
`http://localhost:8080/api`, a key with chat-completions access, and the instance's model IDs.
Only administrators can view or edit the shared configuration. The form opens with the
effective model IDs, including the answer writer and the models routed through OpenRouter on Folonto.
The chat composer shows the model behind each response preset and lets all users choose a preset
for their request.
The settings API stores the key encrypted and exposes only whether it is configured. Headless
settings are in `.env`. Set the input and output rates for a metered compatible provider that
does not return a cost. Daily and monthly limits use a spend ledger that survives chat deletion.
When OpenRouter supplies a smaller affordable token limit, the app can retry before streaming.
The default writer can use the existing main model on the same route when needed. Set
`WRITE_ROUTE` to an OpenRouter model ID to change the writer and `WRITE_FALLBACK_ROUTE` to
explicitly select its alternate for a credit-budget rejection. Other
credit or credential failures show a provider availability message. Short questions reserve
fewer output tokens during analysis. If the writer is unavailable after a calculation runs,
the app still shows and saves the computed result with its evidence.

New answers show a source chip when the cited passage matches the stored original. For
OpenAI-compatible writers, the passage must also appear in the supplied excerpt. Missing or
unmatched citations and uncertain support appear in a compact notice below the complete answer.
Open **Ayrıntıları göster** to read the reasons and select any numbered chip to inspect its source.
When the decision model is configured, the app checks cited claims against those specific sources.
Previous chats display their original citations with a legacy verification label.

## Change your password

Open **Parola değiştir** from your name at the bottom of the sidebar. Enter your current
password and confirm a new password of 8 to 256 characters. The browser you use to save the
change stays signed in. Other sessions for the same account expire.

## Account administration

Administrators open **Yönetim paneli** from their name at the bottom of the sidebar. It
lists each account's daily, monthly and lifetime model spend in USD. Edit either limit in
the account row and save. A blank daily limit uses `DAILY_USER_BUDGET_USD` (3 USD by default).
A blank monthly limit allows unlimited monthly spend, subject to the daily limit. A zero limit
blocks new model operations. The API checks recorded spend before starting new work, so a
request already started can finish after reaching the limit. Periods roll over at midnight UTC
and on the first day of the month in UTC. Choose **Yönetici** or **Kullanıcı** in a row and
save to change the role. At least one administrator must remain.

Under **Yeni kullanıcı daveti**, enter the recipient's email address and choose
**Davet kodu oluştur**. Copy the displayed code and share it privately with the recipient.
They enter it with the same email address on the registration screen. The admin panel keeps
the code and shows whether it is active, used or expired. Registration marks it used, and
unused codes expire 24 hours after creation. Reissue unused codes from before version 0.9.0,
as those records have neither a recoverable code nor an issuance timestamp.

## Calendar and reminders

Open **Takvim → Kayıt ekle**, or select a day and choose **Bu güne ekle**.
Create a hearing, meeting, personal reminder or general event with an optional case, time,
location or meeting link, and notes. For example, choose **Hatırlatıcı**, enter
“Avukat Deniz’i ara”, pick Tuesday and set the alert for the start time. For an all-day
entry, the alert uses 09:00 as its reference. Dates, times and alerts use Europe/Istanbul.
An alert appears across the signed-in app within about 30 seconds while the tab is active,
or when the app is reopened. Dismiss an alert to hide it across devices, or complete the
entry to remove it from pending reminders.

Use **Dava süresi** to save a case deadline directly from the calendar. Enter the date
or use the notice calculator. Case deadlines remain available in the case's deadline
panel. Case-linked events appear on both the calendar and the case page. Deleting a case
keeps its events in your personal calendar. The month view shows official holidays and
the judicial recess. Use the list for a cross-month view and filter by type, case, text
or completion. Calendar questions in chat use the saved records for the open case, or
your calendar when the chat is outside a case.

Open a saved event and choose **ICS indir** to import a copy with its scheduled alarm
into a calendar app that supports iCalendar. The file includes the event's title,
location and notes. The external app controls notification delivery for imported events.

For local upgrades to 0.8.0, run `make setup` and `make migrate` before restarting the API
and rebuilding the frontend.

## Folonto production

Run `sudo bash deploy/release.sh` from the production checkout on the Oracle VM.
After the release passes its health and readiness checks, the script removes unused
older application images and keeps the previous healthy API and web images for rollback.
The [deployment runbook](docs/DEPLOYMENT.md) covers setup, cleanup and rollback.

## Mobile and tablet use

Below 1024 CSS pixels at the default text size, open the navigation drawer from the top bar
to reach chats, cases, the calendar, files and account settings. The message composer stays
above the on-screen keyboard. Swipe across wide tables and code blocks inside a chat, or
across the formatting toolbar in the petition editor on a narrow screen.

In the compact calendar, select a day to read and edit its entries below the month grid.
File actions are available from each item's menu in both list and grid views. Administrators
can create and copy an invitation from the account menu on mobile.

## Calculations and document updates in chat

Ask for a calculation in the existing chat. A hypothetical severance or notice question
can use a stated tenure and gross pay, with the assumed dismissal date shown in the calculation. During a model outage, a clearly
stated monthly tenure, gross pay in TL and hypothetical dismissal can still produce the existing statutory calculation. Attach the relevant files or open the chat in a
case file. The assistant can read document locations, look up statutes and judgments, and
build a calculation using arithmetic, dates, conditions and multiple results. The saved
calculation keeps the inputs, quoted passages, applicable date, reasoning, operations and
result. The source panel opens the material behind each step. If a material fact or rule
cannot be verified, the answer identifies the item that remains open.

You can ask for one line, a table in chat, or an editable Excel workbook. A format change can
reuse the saved calculation. Supply a correction or a replacement document in the same chat
to run a new revision and see which inputs and results changed. For a correction limited to a numeric input, the app verifies the replacement and reuses the approved rules, dates and operations. State which document is authoritative when two files disagree. When you ask to update a Word
file, the assistant can replace a verified amount at an exact location and save a separate
copy in **My files**. Previous answers and their exports remain available in chat history.

Paper scans need a readable text layer for this workflow. Word edits currently target amounts
in the document body, within a single text run. Excel exports contain formulas and the cited source excerpts for the saved plan.
Local changes within Excel are separate from the app's verified revision. Bring changed inputs
back to the chat to verify and record a new revision.

The same local legislation and decision indexes support this workflow. For synthetic or
public-material development, an optional `BRAVE_SEARCH_API_KEY` adds web discovery when the
indexes do not cover a rule. Outbound web queries are built from public legal terms. A result
becomes evidence only after the official document is retrieved and its passage is checked.
Protected mode keeps live source requests off and uses the local indexes.

## Production

[legal.folonto.com](https://legal.folonto.com) runs on the existing Oracle ARM VM. A dedicated
Cloudflare Tunnel sends HTTPS traffic to its loopback proxy. The UI and API share an origin,
with the API under `/api`. Postgres with pgvector runs on the private Compose network. The API
encrypts uploaded files and generated exports before storing them in a private S3 bucket in
Frankfurt. Postgres holds file metadata, extracted text and application records.

See the [deployment runbook](docs/DEPLOYMENT.md) for build, migration, corpus and verification
commands. The live deployment uses the OpenRouter routing from local development. Use
synthetic or public material with that configuration.

## Client data

Use `DATA_MODE=protected` for real client material. Protected mode encrypts original and
generated file payloads, pins inference to an operator-configured endpoint, and uses local
legal indexes for case research. Users continue to read and download their complete content.
`make api-protected` starts the configured API with request access logging disabled. Use
[the privacy and recovery runbook](docs/PRIVACY.md) to migrate existing files, secure
Postgres and temporary files, and test an encrypted backup restore before opening access.

See `NOTICE` for third-party data and code attributions.
