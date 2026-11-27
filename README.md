# Legal Assistant (working name)

A web assistant for Turkish lawyers that answers questions, searches case law and legislation,
and drafts or edits petitions. Every statute article and court decision it cites is retrieved
from an official or public source and rendered by the backend, never written from model memory.

Standalone greetings and thanks receive a short reply. A later follow-up or formatting request can still use the last substantive answer and its sources. A new independent question starts fresh. Citation concerns remain available under each answer. Open a numbered reference in the details to inspect the source behind a flagged statement.

For a related follow-up the planner can use up to ten prior user messages (bounded excerpts of long messages, keeping the opening request) and the five most recently referenced file IDs from the active topic. It resolves references into a research question and can request one clarification when the intended person, document or action is ambiguous. A combined request can run a calculation and an explicit precedent search in the same answer. Documents supply case facts; legal conclusions still use retrieved sources.

Request calculations in chat by describing the calculation and providing the relevant dates and amounts.

A request for an indexed article's text, such as `6098 sayılı Kanun madde 344`, returns the
article and its source directly from the local index. Chat runs overlapping statute and case-law searches when both are needed. The chat saves the
answer as soon as it is ready and keeps the question-derived title if the title model is still
working. Generation has a 60-second limit, or 105 seconds in deep research. Timed-out requests
offer a retry. The final event reports `first_delta_s` when answer text streamed and `total_s`
for the generation run, including follow-up routing.

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
Set `INVITE_CODE` to register the first account, which becomes the administrator. Clear it
and restart the API when registration should close. Use `COOKIE_SECURE=true` when serving
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

The model extracts facts from the conversation and sends structured inputs to the relevant
calculator. For severance, it can send the reported service in whole months and gross pay.
If the termination date is missing and the request gives no indication of another period, the
model can request an explicit estimate for the current date in Türkiye. The answer gives the
conditional amount, links to the official ceiling for the period, and asks for the facts needed
to confirm entitlement or the applicable date. The built-in ceiling table covers 2022–2026.
A period outside that coverage yields no gross or net severance estimate.

Amount-focused answers lead with the supported result and its assumptions, with gross and net
amounts labelled. The default research pass focuses on the rules that determine the result.
A request for precedent or the deep research mode can still expand the search. Follow-up answers
retain the original request and the facts supplied to clarify it.

The analysis response uses a compact structured schema. The backend validates classification
labels before routing. If a provider rejects grammar compilation, the backend can use schema-guided
JSON from the same analysis model and validate it locally. Chat failure logs record the phase and HTTP status without provider bodies.

The API supports Anthropic and OpenAI-compatible chat-completions providers. For Open WebUI,
an administrator can set **Model settings** to a base URL ending in `/api` such as
`http://localhost:8080/api`, a key with chat-completions access, and the instance's model IDs.
The settings API stores the key encrypted and exposes only whether it is configured. Headless
settings are in `.env`. Set the input and output rates for a metered compatible provider that
does not return a cost. The daily budget uses a spend ledger that survives chat deletion.
When OpenRouter supplies a smaller affordable token limit, the app can retry before streaming.
The default writer can use the existing main model on the same route when needed. Set
`WRITE_ROUTE` to an OpenRouter model ID to change the writer and `WRITE_FALLBACK_ROUTE` to
explicitly select its alternate for a credit-budget rejection. Other
credit or credential failures show a provider availability message. Short questions reserve
fewer output tokens during analysis. If the writer is unavailable after a calculation runs,
the app still shows and saves the computed result with its evidence.

New answers show a source chip when the cited passage matches the stored original. For
OpenAI-compatible writers, the passage must also appear in the supplied excerpt. Missing and unmatched
citations show a warning alongside the complete answer. When the decision model is configured,
the app also checks cited claims against those specific sources and marks uncertain support.
Claims citing the same sources share a request while keeping individual verdicts and paragraph context.
Previous chats display their original citations with a legacy verification label.

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

## Client data

Use `DATA_MODE=protected` for real client material. Protected mode encrypts original and
generated file payloads, pins inference to an operator-configured endpoint, and uses local
legal indexes for case research. Users continue to read and download their complete content.
`make api-protected` starts the configured API with request access logging disabled. Use
[the privacy and recovery runbook](docs/PRIVACY.md) to migrate existing files, secure
Postgres and temporary files, and test an encrypted backup restore before opening access.

See `NOTICE` for third-party data and code attributions.
