# Status

State as of 2026-10-30 (evening). Update this page whenever the state changes.

## Working

- Login and registration with invite code; chats with generated titles, history search
  that matches partial words, mid-word text and titles,
  deletion; today's answer count and average time in the sidebar.
- Answers keep running when the lawyer switches chats or reloads; the chat re-attaches.
- Answers stream branch by branch with a live step list and clock, through the atomic sub-question pipeline (see ARCHITECTURE.md), short
  answer first, detail on demand, citation chips, source drawer with full text and official
  link, admin model settings.
- Follow-up routing: reformat requests answered from the previous answer without retrieval;
  follow-up questions retrieved together with the question they follow.
- Decision search mode without an LLM.
- Statute index (17 laws, 5,973 articles) and a 6,693-decision local archive with embeddings.
- Live official sources: Bedesten decisions and legislation, Constitutional Court.

## Measurements

Full evaluation set (11 questions, graded on the short answer, Haiku + decision model):

| Run (2026-10-30) | Questions fully covered | Points covered | Median time | Cost |
|---|---|---|---|---|
| after D20-D21 | 3/11 | 20/31 | 19 s | $0.06 |
| after D23 statute phrases, retry, no-answer message | 6/11 | 27/31 | 24 s | $0.07 |
| after D22/D23 final changes (three runs) | 4-5/11 | 23-25/31 | 22 s | $0.07 |

The spread between runs of unchanged code is about 4 points: plans and sub-answers still vary.
Remaining misses are mostly secondary details the short answer leaves out (a 20% rate, "special
statutes are reserved", "before the enforcement ends") and grading strictness (the 30-day
period is present but called a notice period). The expected points were written without a
lawyer.

Chat scenario (question, then "make these shorter"): routed as reformat, answered from the
previous sub-answers in about 1 s for $0.0002-0.0005.

## Probe: decision model as candidate screener (2026-10-30; in the pipeline since D18)

`typesafe/jev-1.13` through OpenRouter's Decisions API, one yes/no question per candidate
article with its full text ("does this article state a rule that answers the question?").
15 candidates per question, about $0.0005 per question, a few seconds.

- Payment-order objection period: yes (p >= 0.9) for enforcement law arts. 60, 62, 150, 168,
  171, 269, i.e. every regime the answer needs, including art. 168 that the decomposer had
  dropped. Two runs differed by at most 0.06 per article and no decision crossed 0.5.
- Two justified notices: only obligations law art. 352 above 0.9; enforcement law art. 269 at
  0.62; every other candidate below 0.1.
- Not solved by screening: the 30-day payment period (obligations law art. 315) is not among
  the candidates, so it must come from following the reference in art. 269.

## Known issues

1. **Run-to-run variance.** The planner still varies (branch grouping, labels, which side
   questions it asks); coverage moved between 23 and 27 of 31 points across runs. Branch
   coverage is now tied to screened articles (D22), but grouping and wording are not.
2. **Case law is thin.** The local archive is a 6,693-decision subset; live search (D23) finds
   decisions on point only sometimes (the proof-of-cohabitation question missed it in most
   runs). Decision passages are used when a sub-question asks for practice.
3. **Successor picking for repealed-law references** is a majority vote and can still miss
   (the 30-day period was missing in one of the last runs).
4. **Short answers drop side details** the evaluation expects; the full detail is under
   "details".
5. **Latency** 20-45 s per question; live decision search adds a few seconds per sub-question
   that asks for case law (one request per second to the service).
6. `eval/golden` expected points were drafted without a lawyer; they need review.
7. The local decision archive is a small development subset.
8. Answer runs are kept in API process memory (D25): restarting the API during an answer
   loses that answer; several API workers would need a shared store.
9. **Ask and Search are two separate modes**, which the user considers wrong: a lawyer should
   not have to choose. Search covers only the local decision archive (no live search, no
   statutes). Decided by the user on 2026-10-30 to merge them later, not now.
10. **The system is built for one task: short fact lookups.** Lawyers will use it for
    everything: case consultation, statute and decision search, drafting petitions, advice.
    Every message goes through the same lookup pipeline (split into cases and 25-word
    sub-questions, answer each from one article, compress to gists), which breaks reasoning
    over facts. Reproduced with `eval/golden` `kira-3` (2026-10-30): a tenant has not paid
    three months, the landlord sent one notarised notice, nothing was paid; "how do we evict,
    is enforcement mandatory or can we sue directly?" The answer:
    - missed obligations law art. 315 (default: a notice with at least 30 days and a
      termination warning is enough for termination and an eviction suit), the provision this
      case turns on; it was never a candidate (screening confirmed only enforcement law
      art. 269/a);
    - stated "two justified notices are needed, one notice is not enough" for a direct suit,
      which is wrong advice here (that is the separate route of art. 352/2);
    - mixed in enforcement law art. 275 (eviction after the lease term ends, notarised
      contract, renewal document), a different regime;
    - did not answer the explicit question (enforcement is optional: two routes);
    - left out mandatory mediation before an eviction suit (mediation law art. 18/B; the
      enforcement route is exempt), which decides between the routes;
    - asked nothing about missing facts (does the notice give 30 days and warn of
      termination? residence or roofed workplace? same lease year?);
    - read as fragments, not as a colleague's advice (answer, routes with conditions and
      steps, which fits this case, prerequisites).
    Root causes: no task understanding (consultation vs lookup vs drafting vs search), no
    legal characterisation of the facts before retrieval (this is "tenant default"), and an
    answer format designed for single facts.
11. **Answers are not written like an expert's answer.** Compared on `eval/golden` `ceza-2`
    ("provocation reduction in intentional killing", 2026-10-30) with ChatGPT, Gemini and
    Claude, which are not specialised for law but all answer better:
    - they open with the ruling and its basis ("under criminal code art. 29 the reduction
      depends on the penalty"); ours starts with bullets and names the basis only in a chip;
    - they give numbers as digits and bold (18-24 years); ours copies statute wording
      ("onsekiz yıldan yirmidört yıla"). Cause found: the number check did not parse
      joined number words (onsekiz, yirmidört, oniki), so digit gists were rejected and lines
      fell back to the sub-answer text (2 of 3 lines). Fixed 2026-10-30 (grounding/numbers.py
      reads joined words; the stored sub-answers now accept "18-24 yıl"). Fractions
      ("dörtte birinden" and "1/4") are read too since the same day;
    - they map the tiers to the concrete offences (qualified killing art. 82, basic art. 81);
      we never retrieved arts. 81-82: only the rule asked about is searched, not the articles
      of the concepts the question names (here the offence);
    - our third line, "intentional killing in other cases", is a category that does not
      exist (the planner's framing); the others explain "other cases" as fixed-term
      penalties, e.g. attempt;
    - they add what a lawyer must know: the judge's discretion by the provocation's weight,
      exclusions (premeditation, provocation started by the offender), the separate
      discretionary reduction (art. 62, one sixth), checking recent amendments; ours cannot,
      because the answer is assembled only from one-sentence sub-answers;
    - our "details" repeat the short answer instead of giving reasons, conditions,
      exceptions or case law;
    - screening confirmed no article (answering: 0); art. 29 came only through the planner's
      memory and the retry; 31 s versus a few seconds.
    Root cause shared with issue 10: no step writes the answer as a whole (ruling, cases,
    conditions, exceptions, practical notes, basis) with presentation rules; the answer is
    the side-by-side assembly of fragments.
12. **Finding earlier work is hard** (user, 2026-10-30, deferred). The sidebar search now
    matches partial words, but a lawyer also needs to find past work by meaning from inside a
    chat: "I wrote such a petition a while ago, bring it", "which chat was that one about
    ...". Needs search across chats by content and purpose, usable from a new chat, and
    search within the open chat.
13. Short-answer lines sometimes repeat the case name inside the gist ("Haciz yolu ödeme
    emri: Haciz yolu: ..."). Quantities are now always digits (number words before a unit
    such as gün, ay, yıl are converted in code, 2026-10-30).
14. API tests leave test users and empty chats titled "x" in the development database.

## Deployment

`legal.folonto.com` is not live. See D1 in DECISIONS.md for what is ready and what blocks it.

## Spend

Anthropic test key spend so far is about $7.3, plus about $0.65 on 2026-10-30 (Haiku and the decision model together, mostly full evaluation runs); the working budget for this phase is $1 (mostly two Opus evaluation runs on
2026-10-29). Working budget set by the user for the current phase: $1 on Haiku.
