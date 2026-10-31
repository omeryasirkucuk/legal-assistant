# Status

State as of 2026-10-31 (after PR #3). Update this page whenever the state changes.

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
- Petition drafting (D45-D60): case kinds and guides, asking only when key facts are missing,
  a sample library (Word, PDF, UDF) with duplicate detection, style learning, requests settled
  before writing; fast/balanced petitions written through OpenRouter, deep by Claude.
- Calculators in code with sourced tables (D61, D62, D64, D65): procedural periods (holidays,
  judicial recess by branch, electronic service), severance and notice pay, statutory and
  advance interest; cited in answers as calculations.
- Cases ("Davalar", D63, D66-D67): details, notes, documents and deadlines; a case's documents
  go with its questions; a chat outside a case asks first when a case is named exactly.
- Calendar (D63): month grid with holidays and the recess, month/year picker, list view.
- Editor (D69): A4 word-processor editor with autosave; formatting reaches Word, PDF and UDF;
  files carry the petition title.
- Phone and tablet layouts (D72): sidebar as a drawer with a top bar, touch-visible controls,
  phone calendar with dots and a list, stacked dialogs; checked at 360/390/1024/1440.
- Calendar in chats (D71): "what is due this week?" and "the next deadline in this case" are
  answered from the recorded deadlines, cited as the lawyer's calendar; a case chat sees only its own.
- My files (D70): a page with nested folders, list/icon views, upload, in-app preview, rename,
  multi-select move/copy/delete, "add to case".
- Sidebar search (D68) covers cases and their documents as well as chats.

## Measurements

Full evaluation set (11 questions, graded on the short answer, Haiku + decision model):

| Run (2026-10-30) | Questions fully covered | Points covered | Median time | Cost |
|---|---|---|---|---|
| after D20-D21 | 3/11 | 20/31 | 19 s | $0.06 |
| after D23 statute phrases, retry, no-answer message | 6/11 | 27/31 | 24 s | $0.07 |
| after D22/D23 final changes (three runs) | 4-5/11 | 23-25/31 | 22 s | $0.07 |
| D26 understand -> research -> write, 13 questions incl. kira-3 and ceza-2 | 4/13 pass (flags) | 37/42 | 16 s | $0.05 |
| D28 section paths, all results judged, Sonnet writer | 7/13 | 37/42 | 21 s | $0.57 |

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

0. Files are stored on the local disk (var/storage) with a 5 GB quota per user (D43);
   moving them to object storage is left for deployment. Images are not read as text (no OCR)
   but are shown to the model; old Word (.doc) and PowerPoint files are kept but not read.
   File filters (D45) label kind and area of law by a word list; a scan with no text is
   labelled by its name only, and each file gets one area. Files have no backup and are not
   encrypted at rest; both are needed before real client files are stored.

1. **Run-to-run variance** of the earlier pipeline's plans no longer applies to chat answers
   (D26); in the new pipeline, retrieval and the written reasoning still vary (see 10).
2. **Case law is thin.** The local archive is a 6,693-decision subset; live search (D23) finds
   decisions on point only sometimes (the proof-of-cohabitation question missed it in most
   runs). Decision passages are used when a sub-question asks for practice.
3. **Successor picking for repealed-law references** is a majority vote and can still miss
   (the 30-day period was missing in one of the last runs).
4. The earlier pipeline's gist lines (dropped side details, repeated case names) no longer
   apply to chat answers (D26).
5. **Latency** 10-40 s per question (median 16 s on the golden set, D26); live decision search adds a few seconds per sub-question
   that asks for case law (one request per second to the service).
6. `eval/golden` expected points were drafted without a lawyer; they need review.
7. The local decision archive is a small development subset.
8. Answer runs are kept in API process memory (D25): restarting the API during an answer
   loses that answer (the question can be asked again with one click, D34); several API
   workers would need a shared store.
9. **Ask and Search are two separate modes**, which the user considers wrong: a lawyer should
   not have to choose. Search covers only the local decision archive (no live search, no
   statutes). Decided by the user on 2026-10-30 to merge them later, not now.
10. **Lookup-only design (eviction example, `kira-3`) and non-expert answers (provocation
    example, `ceza-2`)** were addressed by D26: the answer is written as a whole in the task's
    structure. Still open:
    - (D38: the writer is told to apply the fitting tier and not contradict itself; three
      runs each on is-1 and kira-3 had no contradiction) the reasoning on facts can contradict its own routes (one browser run
      said "one notice may not be enough for a suit" next to the art. 315 route that needs one);
    - wrong-case errors ("10 days for workplaces" where the code says 30 for roofed
      workplaces) are not caught: the decision model scores them about 0.67, correct
      sentences about 0.9, and a threshold between them flagged correct long paragraphs too;
    - retrieval still varies between runs (enforcement law art. 269 missing in one run);
    - drafting, search and review tasks have structures in the prompt but were not evaluated.
    Detailed history of both problems: DECISIONS D20-D26 and the eval questions.
11. Decision-model screening thresholds were set on a few probes, not tuned on a dataset.
12. Regime confusion (art. 362 of the usufructuary-lease chapter applied to a residential
    lease) and outdated law from old decisions were addressed by D28 (section paths, decision
    dates); the Sonnet-written eviction answer itself warned that art. 362 does not apply.
    Not yet measured on more cases.
13. The Sonnet writer costs about $0.044 per question (Haiku: $0.004); the daily per-user
    budget (DAILY_USER_BUDGET_USD, default 3) allows about 70 answers.
14. Remaining misses on the golden set (run of 2026-10-30, D37: 8/17 passed, 52/60 points; 51 with the stricter grader):
    the payment period of the rent enforcement form (icra-0), proof by any evidence for
    cohabitation (aile-2, needs case law), (the partition article, tasinmaz-1, is found since D36), the judge's discretion (ceza-2), the two-notice point (kira-3, wording).
    In icra-0 the enforcement article with the 30-day payment period (art. 269) is among the
    sources but the answer keeps to the objection periods asked for; in aile-2 two decisions
    were found but their passages do not state proof by any evidence.
    Several answers fail only on a flagged sentence (for example a decision heading whose
    case numbers are checked without a citation).
15. Used-car defect case (golden ayip-1, ayip-2, 2026-10-30): after D29 the answers follow the
    lawyer's questions and give a stage-by-stage plan; still missing: the general civil court
    for a private sale, the inspection firm's own liability, alternative (terditli) claims.
    Evaluation questions added from ChatGPT's and another tool's answers; not lawyer-reviewed.
16. **Drafting is in phase 1** (D39-D40, docs/DRAFTING.md): petitions of five types are drafted
    in the lawyer's measured style with required contents, practice notes learnt from 24
    published samples, and a checklist; edited beside the
    chat, adjusted with four buttons, delivered as a Word, PDF or UDF file in the lawyer's
    usual format (D41; the UDF file is not yet checked in UYAP's editor). Case kinds
    (contested divorce, labour receivables, eviction) add their facts, requests and writing;
    a thin request is answered with a few questions first, adapting to the lawyer's habit,
    and each ground gets its own precedent (D46). Not yet: more case kinds, a model-written
    description of the lawyer's voice, suggestions mode, lawyer review of the outlines and
    case kinds. (Citation markers now show as chips in the editor, D69.) Drafts stay shorter than the
    lawyer's own (about 1,000 words against 1,800) where the facts given are fewer.
17. **Finding earlier work is hard** (user, 2026-10-30, deferred). The sidebar search now
    matches partial words, but a lawyer also needs to find past work by meaning from inside a
    chat: "I wrote such a petition a while ago, bring it", "which chat was that one about
    ...". Needs search across chats by content and purpose, usable from a new chat, and
    search within the open chat.
18. 260 test users and their empty chats titled "x" from earlier test runs are still in the
    development database; the tests now delete what they create (D34).
19. One-click rewrites (shorter, longer, plainer, formal) rebuild the editor document from the
    text: bold survives, italics, sizes and alignment of the rewritten part do not (D69).
20. Court fees and the yearly revalued appeal thresholds have no calculator yet; yearly table
    upkeep is manual (religious holidays, severance ceilings, TCMB advance rates).
21. UDF output has not been opened in UYAP's own editor yet.
22. Deleting in My files uses the browser's confirm dialog; the files filters (D45) are still
    word-list based.
23. Some older tracked files still contain Turkish text outside the allowed folders
    (DECISIONS.md quotes UI strings; some tests and code comments).

## Deployment

`legal.folonto.com` is not live. See D1 in DECISIONS.md for what is ready and what blocks it.

## Spend

Anthropic test key spend so far is about $7.3, plus about $2.2 on 2026-10-30 (evaluation runs $1.41, answers in the app $0.75) (Haiku, Sonnet writer and the decision model, mostly full evaluation runs); the working budget was raised to $2 by the user (mostly two Opus evaluation runs on
2026-10-29). Working budget set by the user for the current phase: $1 on Haiku.
