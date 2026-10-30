# Decisions

Each entry: what was decided, why, and what it replaced. Newest first.

## D25. Answers run on the server, not inside the request (2026-10-30)
Switching to another chat while an answer was streaming lost the answer: the browser closed
the connection, the response generator was cancelled with it, and nothing was saved. The
answer now runs as a background task that records its events and saves the result whether or
not anyone watches; the browser can re-attach and replay the events from the start. The UI
keeps answers in progress per chat, never aborts a run when switching, and the stop button
cancels the run on the server. Runs live in process memory: a deployment with several API
workers would need a shared store for them.

## D24. Answer streams branch by branch; progress, titles and durations shown (2026-10-30)
Lawyer feedback on the UI: the answer appeared at once at the end, sources and text appeared
and were then removed (interim sub-answers were replaced by the final text), it was hard to
tell whether anything was running, chat titles were the first characters of the question,
and answer times were not visible. Now the pipeline emits step events and a short-answer line
per branch as soon as that branch is answered (compose runs per branch); the UI shows the
plan's cases as placeholders that fill in, never removes what it showed, keeps a live step
list with a clock, shows each answer's duration and today's count and average in the sidebar,
and a cheap call titles a chat from its first question (about $0.0001).

## D23. Retrieval in the statutes' own words; retry from neighbours and case law (2026-10-30)
Lawyers and codes name things differently (the practice term for "division in kind" is not the
code's word for "dividing and sharing"), so the
right article (civil code art. 699) was not among 20 candidates. A cheap call writes 3
statute-language phrases whose results are fused with the question's. When the named articles
do not answer a sub-question (the planner named art. 698 from memory, next to the right one),
the sub-question is retried once with the named articles' neighbours (+-2, codes keep related
rules together), a statute search, and screened case law. Decision passages now also come from
live Court of Cassation search (local archive: 6,693 decisions, often nothing on point), each
judged by the decision model before the answering model sees it. A sub-question answers from
a general rule that covers the asked case instead of returning NOT_FOUND.

## D22. Coverage tied to screened articles, not to one plan (2026-10-30)
The planner sometimes wrote one branch where five regimes apply (two runs of the same
question gave 1 and 5 branches). Code now adds a sub-question for every article the decision
model confirmed that the plan left out, unless the planner reviewed it and rejected it;
articles with the same situation name share one. Screening threshold raised from 0.7 to 0.85:
confirmed articles scored 0.92-0.96, neighbouring provisions 0.79-0.83. Successor picking for
repealed-law references was unstable (3 runs, 3 different picks); references of one article to
the same law are merged and the pick is a per-candidate verdict, kept if chosen in 2 of 3.

## D21. Follow-up messages are routed (2026-10-30)
"Make these shorter" was answered as a new legal question: it was searched as statute text,
found nothing, and 3 of 4 branches came back "not found". The decision model now classifies a
message as a new question, a reformat request, or a follow-up question. A reformat reuses the
previous answer's cited sub-answers and sources (no retrieval, about $0.0003); a follow-up is
retrieved together with the question it follows. Without a decision model, a message after
an answer is treated as a follow-up, as before.

## D20. A real short answer (2026-10-30)
The "short answer" was every sub-answer pasted together, mostly statute sentences, and side
sub-questions showed up front. Now a cheap call writes a gist of each sub-answer and code joins
a branch's gists into one line (one line written freely dropped a branch's second period);
citation keys come from the sub-answers; a gist stating a number its sub-answer does not is
replaced by the sub-answer. The stored message is `<short>`lines`</short><detail>`sub-answers
`</detail>`, which the UI already shows as short answer plus "details". Evaluation grades the
short answer. Prompt examples that matched evaluation answers were replaced with neutral ones
(they had been inflating results).

## D19. Follow cross-references; read only the articles the plan names (2026-10-30)
Answers missed rules that an article states by reference. Example: enforcement law art. 269
points to "the notice and legal period in articles 260 and 288 of the Code of Obligations",
a repealed law; the 30-day period now sits in obligations law art. 315 with different
numbering. General fix, not tied to that question:
- `references.py` reads references out of every confirmed article (by number, by name, same
  law). Within an indexed law the article is fetched by label and kept if the decision model
  judges it relevant. For a repealed or unindexed law, candidates are searched by content
  with the referring sentence, and Haiku picks the successor (the decision model could not:
  0.28 for the right article, since old and new numbering differ).
- Every followed article becomes a sub-question in the citing branch, added by code. When
  this was left to the planner it was skipped in one of two runs.
- Law names written by the planner (abbreviations, "BK 315", "6098 <numbered> ...") were not
  resolved, so
  the article was requested from the live service and often lost; names now resolve locally
  through numbers, customary abbreviations and folded names.
- A sub-question reads only the articles it names; statute search is a fallback when none is
  found. With searched articles next to named ones, the bills-of-exchange sub-question was
  once answered with the general 7-day rule instead of its own 5 days.
- Prompt examples that hinted at the evaluation answers were replaced by neutral ones.
Measured on the payment-order question: 4/4 in two of three runs (3/4 in the run where the
planner skipped the reference), 24-26 s, about $0.01.

## D18. Screen candidate articles with a decision model (2026-10-30)
The planner used to judge 15 candidates from their first 220 characters while also writing the
branches, so it missed articles whose rule appears later (enforcement law art. 168) and chose a
different set on every run. Now `typesafe/jev-1.13` judges each of 20 candidates on its own,
from the full text, as a yes/no probability; confirmed articles reach the planner in full and
must each become a branch source. About $0.001 and a few seconds per question; probabilities
moved by at most 0.06 between runs. Measured on the payment-order question: coverage 2/4 to
3/4, both bills-of-exchange regimes now present. Without a key the pipeline behaves as before.

## D17. External projects reviewed: Zekai Suni and Mizan (2026-10-30)
`ZekaiSuni/zekai-suni-tr-legal` (MIT, prototype) has no retrieval or source access, so it does
not address answer quality. Worth reusing later, as ideas or small ported pieces with MIT
attribution: the deterministic deadline engine and public-holiday calendar (for the planned
deadline calculator; its holiday list is hand-maintained and partly approximate), reversible
personal-data masking before LLM calls, the fenced "document is data" prompt guard for
uploaded files, and the citation-audit verdict set (supports directly / by inference /
partly / contradicts / wrong pinpoint / misquote / not found) for checking a lawyer's petition.
`AlicanKiraz0/Mizan-27B` (Qwen 27B fine-tune) is not used: CC-BY-NC-4.0 forbids commercial
use, the decision model gives probabilities without sources (nothing to cite), the public Space
would receive client facts, and local use needs a 15-27 GB download. Its one transferable idea,
fixed typed questions answered by choice instead of free generation, matches the planned fix for
unstable branch structure (STATUS known issue 2) and needs no model.

## D16. Remove question-specific answer paths (2026-10-30)
PR #1 added `payment_order_branches` and `_payment_order_answer`: any question containing the
Turkish words for "payment order" and "objection" received three fixed branches and hand-written answers. They fit one
evaluation question and nothing else, and they make the same kind of question behave in two
different ways depending on wording. Removed; coverage must come from the general pipeline.
The OpenAI-compatible provider support from the same PR is kept.

## D15. Answer by atomic sub-questions with the Citations API (2026-10-29)
Problems: answers took 70-120 s, missed cases (rent enforcement and its 30-day payment
period), and blended provisions of different regimes into one statement (two justified
notices vs. default notice). Root cause shared by all three: one long answer was written over
all sources and then checked and repaired. Now the question is split into sub-questions; each
is retrieved for and answered on its own, with Anthropic's Citations API binding every claim
to an exact passage. The short answer is composed from the sub-answers; detail is written only
on request. Replaced: model-written `[[E#]]` markers, regex checks, the sentence reviewer and
the repair round. Measured: 16-37 s and $0.004-0.014 per question on Haiku.

## D14. Full-text search with OR semantics (2026-10-29)
`websearch_to_tsquery` requires every term, so natural-language questions (for example "within what
period must the case be filed?") matched nothing and only vector search ranked results. SQL function
`any_terms()` turns the query's stemmed terms into an OR query ranked by `ts_rank_cd`.

## D13. Statute index (2026-10-29)
Articles were only reachable by number, so the system found what the model already knew.
Core laws are now stored per article (including lettered, additional and temporary articles) with full-text and
vector search. Each law is fetched as one consolidated document from Bedesten (one request),
split at article headings, and replaced atomically on resync. Also removes most live
legislation requests and their rate-limit risk.

## D12. Cheapest model in every role (2026-10-29)
User decision: quality must come from the system, not from an expensive model. All roles
default to `claude-haiku-5-5` (Opus answers had cost $0.28-0.77 each). Evaluation runs take
`--max-usd` (default 0.5) and any run estimated above about $1 needs the user's approval.

## D11. Process-wide rate limit for official services (2026-10-29)
The per-host rate limit lived in each request's gateway, so concurrent answers exceeded it and
Bedesten blocked us. Host state is now shared by the whole process.

## D10. Invite-only registration, daily budget, secure cookie (2026-10-29)
Needed before any public deployment, since every answer spends the shared provider key.

## D9. Short answer first (2026-10-29)
Lawyers asked for the direct answer first ("7 days"), detail only when wanted. The short
answer is at most one line per case; detail sits behind a toggle and is generated on demand.

## D8. Streaming answers over server-sent events (2026-10-29)
Status, sources and answer text appear as they are produced.

## D7. Evidence ledger; the model never writes citation metadata (2026-10-29)
Court, chamber, case and decision numbers, dates and article numbers are rendered from the
source's structured fields. The model only refers to sources by key.

## D6. Local decision archive plus live services (2026-10-29)
The CC0 Hugging Face dataset (11M decisions, August 2026 snapshot) gives history; Bedesten
gives new decisions and legislation. The full corpus does not fit the development machine
(62 GB free); development uses a 6,693-decision subset. A production server would hold the
full corpus with compressed vectors and sync new decisions nightly.

## D5. Own data engine, not Dayanak (2026-10-29)
Dayanak (AGPL) is the most complete open MCP server for Turkish law, but AGPL would oblige
publishing modified code if offered as a service. Source adapters are ported from the MIT
projects `aydincan/turk-hukuku-ictihat-mcp` and `turk-hukuku-mevzuat-mcp` (see `NOTICE`).

## D4. Own web product instead of a Claude setup (2026-10-29)
Not every lawyer uses Claude; the product must be a ChatGPT-simple web app for non-technical
users. Stack: Next.js + FastAPI + Postgres/pgvector.

## D3. Turkish only in content folders (2026-10-29)
Tracked code, comments, docs and commits are English; Turkish is allowed only in
`locales/tr`, `prompts/tr`, `playbooks/tr`, `eval/golden` and test fixtures under
`services/api/tests/fixtures/tr`.

## D2. Product name undecided (2026-10-29)
Working name "Legal Assistant", behind `APP_NAME`. Candidates with free .com and .com.tr
domains (not trademark-checked): atifla, kunyele, gerekcem, hukukra.

## D1. Hosting plan: Cloudflare Tunnel from the development Mac (2026-10-29)
Target `legal.folonto.com`. A dedicated tunnel `legal-folonto` exists
(`~/.cloudflared/legal-folonto.yml`, API path rules to :8100, UI to :3100). Blocked on the
DNS record (the local Cloudflare certificate only covers amxcli.com) and on approval to install
launchd services. A stray record `legal.folonto.com.amxcli.com` was created by mistake and
must be deleted in the amxcli.com zone.
