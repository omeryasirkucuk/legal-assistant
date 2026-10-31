# Petition drafting

Design of the drafting feature: the assistant writes a petition (dava dilekçesi, cevap,
istinaf, itiraz, ihtarname ...) for a case the lawyer describes, in the lawyer's own style, and
learns that style over time.

## Why

Lawyers who tried other tools say drafts read "AI-like" and the length is wrong: some want
short petitions, some long; some write plain sentences, some a formal, ornate register
("ağdalı"). A lawyer should not have to write instructions to fix either. The system must be
capable from the first draft (correct structure, required contents, grounded legal reasons)
and then move toward the direction each lawyer wants.

## Goals

- A first draft that has the parts the law requires for its type, legal reasons cited from
  the statute index and decisions (the same grounding as answers), facts left as bracketed
  placeholders when unknown, and a checklist of what is still missing.
- Style learnt from the lawyer's own petitions: length, sentence length, register, headings,
  opening and closing formulas, how decisions are cited.
- Style that follows the lawyer's corrections: one-click changes on a draft (shorter, longer,
  plainer, more formal) and the lawyer's own edits move the profile.
- Export to DOCX (UDF later).

## Non-goals (for now)

- Filing through UYAP, e-signature.
- Copying petitions from law-firm websites into the system (see Sources).
- Contracts and other non-court documents beyond the warning letter (ihtarname).

## Anti-goals

- A draft that invents a fact, a decision or a statute.
- A draft whose style is the model's default voice rather than the lawyer's.
- Style controls the lawyer must understand or configure before the first draft.

## Sources of drafting knowledge

1. **Required contents from the law (grounded).** The articles that set what a petition must
   contain are in the statute index: HMK 119 (statement of claim), 121 (documents), 129
   (answer), 194 (facts and evidence), 342 (appeal to the regional court), 364 (appeal to the
   Court of Cassation), İYUK 3 (administrative action), İİK 62 (objection to a payment
   order), CMK 273 (criminal appeal), HUAK 18/B (mediation before suit). Each petition type
   lists its articles; the checklist is read from them and cited.
2. **Petition-type outlines** (`playbooks/tr/petitions/*.md`): sections and their order,
   standard formulas, usual evidence and annexes, per type. Written in our own words from the
   law and common practice; to be reviewed by the lawyer.
3. **Legal reasons** from the existing research pipeline (statutes, references, decisions).
4. **The lawyer's own petitions** ("Örnek dilekçelerim"): the main source of style.
5. Later: claim summaries in court decisions ("davacı vekili dava dilekçesinde özetle ..."),
   which show what was claimed in similar cases (decisions are free to reuse, FSEK art. 31;
   the local archive is CC0), and official forms published by the ministry.

Published samples (law-firm and lawyers' sites, shared to be used) are learnt from, not
copied into the product: `drafting/study.py` reads the pages listed in
`playbooks/tr/petitions/sources.json` (robots.txt respected, one request per second per host,
sites that refuse automated access skipped), keeps their text only in `var/petition_samples`,
has the cheap model note each sample's sections, formulas, requests, evidence, procedure
points, common mistakes and style, and merges the notes of a type into
`playbooks/tr/petitions/<type>.practice.md` in its own words. The writer gets these notes as
practice, not as a legal source; the lawyer's own style comes first. The one Hugging Face
"petitions" set found (eminecg/petitions-ds) has no license and holds Constitutional Court
decision texts, so it is not used.

## Style profile

Per user, overall and per petition type, built from their samples and updated by feedback:

- **Measured** (code, no model): words and pages, words per sentence, paragraphs per page,
  headings used and their order, numbering style, opening and closing formulas, decision
  citation pattern, rate of formal/archaic words ("işbu, mezkur, binaenaleyh, müvekkil")
  from a locale lexicon (`locales/tr/style_lexicon.json`) as a register score.
- **Described** (cheap model, once per sample): a short description of the voice and the
  argument order, merged across samples.
- **Rules** the lawyer states ("Yargıtay kararlarını tam künyeyle yaz"), kept as a list they
  can see and edit.
- **Preferences** moved by feedback: a target length and a register target, each a running
  value that every action and accepted edit shifts.

Drafting is conditioned on the profile and on the one or two most similar own samples
(embedding similarity on the case description), with the instruction to take their style and
structure, never their facts.

## Learning the direction

- Buttons on a draft and on a selected paragraph: Kısalt, Genişlet, Sadeleştir,
  Resmîleştir. Each rewrites only that part, keeps citations and placeholders, and moves the
  matching preference.
- The lawyer edits the draft in place; on save, the difference between the draft and the
  saved text (length, register) updates the preferences. A saved draft is not added as a
  sample by itself (that would count the same correction twice); the lawyer uploads the
  final petition when they want it learnt as a sample.
- The profile is shown in plain Turkish ("Dilekçelerin genelde 4-5 sayfa, cümlelerin kısa,
  kararları tam künyeyle veriyorsun") and can be corrected.

## Flow

Yaz mode: the lawyer describes the case and the petition wanted → understanding (existing,
task "drafting") picks the type → research gathers the legal reasons → the writer drafts
section by section for long petitions → checks: numbers and claims against sources (existing),
required contents against the type's articles → the draft opens in a document panel beside
the chat, with the checklist, the buttons and DOCX export.

## Phases

1. Petition types with required-content checklists; style profile from uploaded or pasted
   samples (DOCX, PDF, text); drafting conditioned on profile; the four buttons; document
   panel; DOCX export.
2. Learning from edits; similar-sample selection; decision claim summaries; UDF export.
3. Suggestions mode (accept/reject edits), per-paragraph history.

## Measuring

- Style fidelity: distance between a draft's measured features and the lawyer's samples.
- Required contents: share of the type's checklist present.
- Grounding: the existing checks (flagged sentences, uncited legal statements).
- Blind test with the lawyer: our draft against their own petition for the same case.

## Cost

A petition drafted by the Sonnet writer is expected to cost about $0.10-0.20 (longer output
than an answer); a style description of a sample about $0.002 (cheap model).

## State (2026-10-30, phase 1)

Built: five petition types (`dava`, `cevap`, `istinaf`, `icra-itiraz`, `ihtarname`) with
outlines and required-content articles; the understanding step picks the type; the type's
articles are added to the sources; style measured from uploaded DOCX/PDF/TXT samples
(`drafting/style.py`), targets per type (`drafting/profile.py`), the four buttons and edits
moving the preferences (`drafting/feedback.py`), stated rules; drafts saved per answer
(`drafts` table) and opened in a panel beside the chat; Word export of the petition part.
Not built yet: the voice description of samples by a model, choosing the most similar sample
by meaning (the longest sample of the same type is used), learning from edits beyond length
and register, UDF export, suggestions mode.

First run (kira eviction case, formal sample): $0.08; the draft took the sample's headings,
closing formula and register (27 formal words per 1,000 against the sample's 40+), chose the
civil court of peace by HMK art. 4 although the sample named the general civil court, left
unknown facts in brackets and ended with a cited checklist. "Sadeleştir" on it: register
27 -> 6.9, citations kept, $0.017.

Practice notes (2026-10-30): 24 of 29 listed pages read (one site answers automated access
with 403 and was skipped), $0.08. The same eviction case drafted with no own sample ($0.17):
the claim now also asked for the overdue rent with interest and occupation compensation, gave
the evidence after each fact paragraph and numbered annexes, all from the practice notes;
register plain (2.3 formal words per 1,000), closing "saygıyla arz ve talep ederiz". The
"dava" notes lean to eviction suits (4 of 7 samples).

Known limits: the editor shows the citation markers ([[E3]]) as text; adjustment costs are
recorded on the draft but not counted in the daily budget; the outlines are not yet reviewed
by a lawyer.

## Learnt preferences (D44)

Besides the measured numbers, the lawyer's habits are learnt as short sentences from their
saved edits, kept with meaning vectors, used after two separate edits show them, and chosen
per case by meaning (at most six), so the prompt does not grow with the lawyer's history. They
can be seen, forgotten one by one, or reset with everything else learnt.

## Delivery

A petition is a file, not chat text (D41): Word unless the message names another format or
the lawyer has asked for one format more often than any other; PDF and UDF also offered on
the file card. The UDF writer follows the documented structure of UYAP's format and must be
checked once by opening a file in UYAP's editor.

## Decided

- Drafting lives in the existing app and pipeline.
- Published samples are learnt from (practice notes per type), their text is not stored in
  the repository or shown to users; style comes from the lawyer's own petitions first.
- The four adjustment buttons replace tone and length settings.
