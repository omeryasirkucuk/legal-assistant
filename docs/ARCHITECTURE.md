# Architecture

A grounded legal research assistant for Turkish lawyers. Its one promise: nothing about the
law is stated without a source the lawyer can open. This page describes the system as it is.
Decisions and their reasons are in [DECISIONS.md](DECISIONS.md); the current state, known
issues and measurements are in [STATUS.md](STATUS.md).

## Components

| Path | Role |
|---|---|
| `apps/web` | Next.js 15 UI (TypeScript, Tailwind v4). Talks to the API with a session cookie. |
| `services/api` | FastAPI backend, package `legal_api`. Python 3.12, managed with `uv`. |
| `docker-compose.yml` | Postgres 16 + pgvector, bound to `127.0.0.1:5433`. |
| `prompts/tr` | LLM instructions (Turkish). Loaded by name via `legal_api.prompts.prompt()`. |
| `locales/tr` | Every Turkish string: UI copy, status messages, citation templates, institution names, statute terms. |
| `eval/golden` | Evaluation questions with the points a correct answer must cover. |
| `var/` (ignored) | Downloaded corpus files, eval outputs, logs. |

Turkish text lives only in `prompts/tr`, `locales/tr`, `playbooks/tr`, `eval/golden` and `services/api/tests/fixtures/tr`;
code, comments and docs are English.

## Backend packages (`services/api/legal_api`)

| Package | Responsibility |
|---|---|
| `sources/` | Live adapters for official services. `gateway.py` is the single HTTP gate: honest User-Agent, one request per second per host for the whole process, cooldown on 403/429/captcha/HTML-instead-of-JSON, never retries. `bedesten_decisions.py` (Court of Cassation, Council of State, regional appeal and first-instance civil courts, appeals in the interest of law), `bedesten_statutes.py` (legislation search, article tree, single article, lettered, additional and temporary article labels such as `269/a`), `aym.py` (Constitutional Court). `cache.py` is a TTL cache with single-flight used for legislation. |
| `corpus/` | Offline ingestion. `ingest.py` loads decisions from the public parquet dataset, `chunking.py` splits them into offset-preserving paragraph chunks, `embed.py` fills embeddings, `statutes.py` syncs core laws into the statute index. |
| `retrieval/` | `hybrid.py`: decision search (full text + vector, fused with Reciprocal Rank Fusion). `statutes.py`: the same over statute articles (optionally within given laws), exact article lookup, and law-name resolution (number, abbreviation from `locales/tr/law_abbreviations.json`, or name). `references.py`: reads cross-references out of article text (vocabulary in `locales/tr/references.json`). Full-text matching uses the SQL function `any_terms()` (OR semantics), not `websearch_to_tsquery` (AND). |
| `embeddings.py` | `intfloat/multilingual-e5-small` (384 dims) via sentence-transformers, on MPS/CUDA/CPU. |
| `agent/` | The answer pipeline (below): `turn.py`, `route.py`, `reformat.py`, `queries.py`, `candidates.py`, `screen.py`, `follow.py`, `decompose.py`, `case_law.py`, `compose.py`, `sources.py`, `atoms.py`, `answer.py`, `detail.py`. |
| `decisions.py` | Client for a decision model (typed yes/no questions answered with probabilities, no text) via OpenRouter's Decisions API; `DECISION_API_KEY`, `DECISION_MODEL`. |
| `grounding/` | `numbers.py`: numbers stated in text (digits and Turkish number words) for checking short answers. `evidence.py`: the evidence ledger. Each source gets a key (`E1`, `E2`, ...); citation strings are built from the source's structured fields, never by the model. `normalize.py`: Turkish casefolding and quote matching. |
| `llm.py` | Provider client (Anthropic, or OpenAI-compatible such as OpenRouter or Open WebUI), role-based model choice (`main`, `draft`, `cheap`, `judge`), automatic prompt caching, token and cost accounting per pipeline step. |
| `chat/` | History for follow-up questions and persistence of answers (`service.py`), answer runs independent of the connection (`runs.py`), generated titles (`titles.py`), sidebar search where partial words match (`history_search.py`: prefix full-text, Turkish-folded substring backed by trigram indexes, titles). |
| `api/` | Routes: `auth`, `chats` (streaming answers, on-demand detail, history search), `search` (decision search without an LLM), `settings` (admin model settings), `health`. |
| `auth.py`, `privacy/` | scrypt password hashing, signed session cookie, encrypted provider credentials. |
| `evaluation/` | `golden.py` runs the question set with a spend cap; `coverage.py` grades whether each expected point is covered. |
| `locale.py`, `prompts.py`, `config.py` | Access to Turkish strings, prompts and settings (`.env`). |

## Data

| Table | Content |
|---|---|
| `corpus_decisions`, `corpus_chunks` | Local decision archive. Development subset: 6,693 Court of Cassation decisions from 2025-26 (civil chambers 1, 2, 3, 12, General Assembly of Civil Chambers, criminal chamber 1), 27,562 chunks with embeddings. Source: Hugging Face `mrfg/turkish-court-decisions` (CC0, 11M decisions, snapshot of August 2026). Document ids match the Ministry's public pages (`https://mevzuat.adalet.gov.tr/ictihat/<id>`). |
| `statute_articles` | Statute index: 17 core laws, 5,973 articles (enforcement, obligations, civil, civil procedure, criminal, criminal procedure, administrative procedure, commercial, labour, labour courts, mediation, condominium, attorneys, notification, fees, consumer, constitution). One row per article including lettered, additional and temporary articles; full text, marginal title, embedding. Synced from Bedesten's consolidated law documents. |
| `users`, `chats`, `messages`, `message_evidence` | Accounts, conversations, answers (`messages.meta.answer` holds the structured answer, `meta.detail` the cached detail section, `meta.cost_usd` the spend) and every source an answer used, so citations stay viewable later. |
| `llm_connection_settings` | Admin-managed provider endpoint, encrypted key and model ids. |

## Answer pipeline

```
message in a chat
  0. route (decision model) new question | reformat the previous answer | follow-up question
                            (agent/route.py, turn.py). Reformat: the previous answer's cited
                            sub-answers are written again as gists under the lawyer's
                            instruction, no new retrieval (reformat.py). Follow-up: retrieval
                            uses the previous question together with the new message.
question
  1. candidate provisions   statute search on the question, fused with searches on 3
                            statute-language phrases written by a cheap call (queries.py),
                            24 candidates (candidates.py)
     screen (decision model) each candidate judged in full: does it answer the question?
                            p >= 0.85 shown to the planner in full, 0.4-0.85 as an excerpt
                            to review, below 0.4 dropped (screen.py; skipped without a key)
     follow references      cross-references in confirmed articles are read out of the text
                            (retrieval/references.py); by label within an indexed law, kept if
                            the decision model finds them relevant; for a repealed or
                            unindexed law, references of one article to that law are merged,
                            candidates are searched by content, and the successor is the
                            article picked in a majority of 3 per-candidate judgments (follow.py)
  2. decompose (LLM)        structured JSON: review of every candidate, branches and atomic
                            sub-questions with the articles to read and an optional case-law
                            query. Code then adds a sub-question for every confirmed article
                            the plan left out (unless the planner rejected it), grouped by the
                            planner's situation name, and one for every followed reference in
                            the citing branch (decompose.py)
  3. per sub-question, in parallel (atoms.py):
       sources              the named articles (local index; live service only for a law the
                            index does not hold); a statute search only if none was found;
                            case-law passages when a case-law query was written: local
                            archive (4) + live Court of Cassation search (4 decisions, closest
                            passage each), screened by the decision model, best 2 (case_law.py)
       cited answer (LLM)   sources as citation-enabled documents (Citations API); one short
                            sentence or NOT_FOUND
       retry                if NOT_FOUND: the named articles' neighbours (+-2), a statute
                            search on the sub-question and, if the plan asked for no case
                            law, screened decision passages for a phrase written by a cheap call
  4. compose                a cheap call writes a gist per sub-answer; code joins each branch's
                            gists into one line, citation keys from the sub-answers, a gist
                            with a number its sub-answer lacks falls back to the sub-answer
                            (compose.py). No line at all: "no answer found" message
  5. message                <short>lines</short><detail>every cited sub-answer</detail>;
                            history for later turns uses the short part only
```

Grounding is enforced by construction. With the Anthropic provider, every cited passage is
returned by the API and is guaranteed to exist in its document; a sub-answer without any
citation is shown as "not found" instead of being displayed. With OpenAI-compatible
providers, which have no citations API, the model must write `<quote ref="E3">exact
text</quote>[[E3]]` and the quote is checked against the source. Numbers in the short answer
(digits or words) must appear in the sub-answer they summarise (grounding/numbers.py).

Law names the planner writes are resolved locally (retrieval/statutes.py `law_number_of`):
an indexed law number anywhere in the text ("Law 6100", "6098 <numbered> ..."), a customary
abbreviation (locales/tr/law_abbreviations.json) or the law's name; article labels accept
"art. 65", "352/2" (paragraph) and "269/a" (lettered article).

Every stored answer keeps a `trace` in `messages.meta`: confirmed articles, followed
references, how many candidates were left to review or unscreened, or the route taken.

Streaming events from `POST /chats/{id}/messages`: `question`, `step` (name, active/done,
counts: understand, search, screen, references, plan, answer with done/total, compose),
`route`, `plan`, `evidence`, `atom`, `line` (a branch's short-answer line, sent as soon as
that branch's sub-answers are in), `final`, `title` (first turn: a generated chat title),
`saved`, `error`, `cancelled`. The answer runs as a server-side task (`chat/runs.py`) that
records its events: closing the connection (switching chats, reloading) does not stop it, and
`GET /chats/{id}/run` replays the running answer's events from the start and follows it (204
when nothing runs); `POST /chats/{id}/run/cancel` stops it. One run per chat; runs are kept in
the API process's memory, so a single API process is assumed. Detail: `POST /chats/{id}/messages/{mid}/detail` streams `delta` then
`detail`. `GET /chats/stats/today`: answers given today, average and longest duration.

## Web UI (`apps/web/src`)

`app/login` (registration needs the invite code), `app/page.tsx` (chat shell),
`lib/useChatRuns.ts` (answers in progress per chat; opening a chat re-attaches to its running
answer, switching away only stops watching), `lib/pending.ts`
(the streamed answer built from events; steps only advance, sources and lines are only
added), components: `Sidebar` (chats with generated titles, history search, today's answer
count and average time, settings for admins), `Composer` (ask mode, and decision search
without LLM), `AnswerProgress` (live checklist of steps with counts and a running clock),
`StreamingAnswer` (the plan's cases as placeholders, each replaced by its line as it arrives,
words revealed in order, then citation chips; sources in the margin are only those cited),
`AssistantAnswer` (saved answer: short answer first, details behind a toggle, numbered
citation chips, sources in the margin, answer duration), `SourceDrawer` (full source text with
official link and fetch time), `SettingsPanel` (admin model settings), `SearchResults`. All
copy comes from `locales/tr/common.json`. Existing chats can be given generated titles with
`uv run python -m legal_api.chat.titles`.

## Security and spend controls

Registration requires `INVITE_CODE`; passwords use scrypt; sessions are signed cookies
(`COOKIE_SECURE=true` behind HTTPS); each user has a daily LLM budget
(`DAILY_USER_BUDGET_USD`, default 3); Postgres listens on localhost only; provider keys live in
`.env` (git-ignored) or encrypted in the database.

## Running locally

```bash
cp .env.example .env                       # provider, key, INVITE_CODE, SECRET_KEY
make api                                   # Postgres, migrations, API on :8000
make web                                   # UI on :3000
cd services/api
uv run python -m legal_api.corpus.statutes                       # sync the statute index
uv run python -m legal_api.corpus.ingest FILE.parquet --chamber "3. Hukuk Dairesi=1500"
uv run python -m legal_api.corpus.embed                          # embed decision chunks
uv run python -m legal_api.evaluation.golden --only icra-0 --max-usd 0.2
```
