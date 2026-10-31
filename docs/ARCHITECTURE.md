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
| `agent/` | The answer pipeline (below): `turn.py`, `route.py`, `pipeline.py`, `understand.py`, `research.py`, `write.py`; the earlier pipeline kept for comparison: `reformat.py`, `queries.py`, `candidates.py`, `screen.py`, `follow.py`, `decompose.py`, `case_law.py`, `compose.py`, `sources.py`, `atoms.py`, `answer.py`, `detail.py`. |
| `decisions.py` | Client for a decision model (typed yes/no questions answered with probabilities, no text) via OpenRouter's Decisions API; `DECISION_API_KEY`, `DECISION_MODEL`. |
| `grounding/` | `numbers.py`: numbers stated in text (digits and Turkish number words) for checking short answers. `evidence.py`: the evidence ledger. Each source gets a key (`E1`, `E2`, ...); citation strings are built from the source's structured fields, never by the model. `normalize.py`: Turkish casefolding and quote matching. |
| `llm.py` | Provider client (Anthropic, or OpenAI-compatible such as OpenRouter or Open WebUI), role-based model choice (`main`, `draft`, `cheap`, `judge`), automatic prompt caching, token and cost accounting per pipeline step. |
| `chat/` | History for follow-up questions and persistence of answers (`service.py`), answer runs independent of the connection (`runs.py`), generated titles (`titles.py`), sidebar search where partial words match (`history_search.py`: prefix full-text, Turkish-folded substring backed by trigram indexes, titles). |
| `api/` | Routes: `auth`, `chats` (streaming answers, on-demand detail, history search), `drafting` (samples, style profile, drafts, adjustments, Word export), `search` (decision search without an LLM), `settings` (admin model settings), `health`. |
| `drafting/` | Petition drafting (docs/DRAFTING.md): `types.py` (petition types from `playbooks/tr/petitions`), `style.py` (measured style), `profile.py` (targets from samples and preferences), `feedback.py` (buttons and edits move preferences), `brief.py` and `prepare.py` (what the writer is told; required-content articles added to the sources), `adjust.py` (the four rewrites), `memory.py` (preferences learnt from edits, chosen by meaning), `export.py` (Word), `store.py` (samples, profile, drafts). |
| `files/` | `store.py`: the per-user file space and quota; `extract.py`: text of uploaded files; `labels.py`: format, kind and area of law of each file, for filtering; `context.py`: attachments given to the model. |
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

The chat answers through `agent/pipeline.py` (understand -> research -> write). The earlier
pipeline (`agent/answer.py`, decompose -> sub-answers -> gists) is kept for comparison only.

```
message in a chat
  0. route (decision model) new question | reformat the previous answer | follow-up question
                            (agent/route.py, turn.py). Reformat: the previous answer written
                            again from its own sources under the lawyer's instruction.
  1. understand (LLM)       task (lookup, consultation, drafting, search, review), legal
                            characterisation of the facts, the issues the answer rests on with
                            a statute-language search phrase each, articles known to apply,
                            a case-law query when practice matters, missing facts
                            (agent/understand.py)
  2. research               statute search on the question and every issue (all results
                            judged); the named articles read from the local index (the
                            understanding step sees the indexed laws); each candidate, with its
                            section path, judged by the
                            decision model ("does a complete answer need this rule": the rule,
                            an available route, a precondition, a time limit, the competent
                            court); kept: named articles and those >= 0.6, best 10; references
                            of the clearly answering ones followed; screened case-law passages
                            (local + live, 15 s budget) for consultations or a case-law query
                            (agent/research.py)
  3. write (Sonnet, streamed) one pass over all sources as citation-enabled documents, in the
                            structure of the task (prompts/tr/write.md): lookup = ruling with
                            basis, numbered cases, practical notes; consultation = short
                            answer, routes with conditions and steps, this case, preconditions
                            and deadlines, facts to clarify (agent/write.py)
  4. check                  every sentence stating a quantity: its numbers must appear in the
                            sources it relies on (cited or named by article), and the decision
                            model must judge it supported; failures are shown as unverified.
                            Quantities are then written as digits
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
added), components: `Sidebar` (collapsible to an icon rail with new chat, search and the account;
chats grouped by day, history search), `UserMenu` (opened from the user's row or initials:
email, today's use, "Yazım tarzım", model settings for admins, sign out), `StylePanel`
("Yazım tarzım": length and language chosen in plain words or learnt, own petitions, written
wishes), `DraftFile` (a petition as a file card: download, other formats, edit),
`DraftPanel` (the draft editor with the four adjustment buttons), `Composer` (ask mode, and decision search
without LLM), `AnswerProgress` (live checklist of steps with counts and a running clock),
`StreamingAnswer` (the plan's cases as placeholders, each replaced by its line as it arrives,
words revealed in order, then citation chips; sources in the margin are only those cited),
`AssistantAnswer` (saved answer: short answer first, details behind a toggle, numbered
citation chips, sources in the margin, answer duration), `SourceDrawer` (full source text with
official link and fetch time), `SettingsPanel` (admin model settings), `SearchResults`. The composer sits in the answer column's grid and both the message area and the composer
reserve the scrollbar width, so their edges line up. All
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
