# Decisions

Each entry: what was decided, why, and what it replaced. Newest first.

## D70 — My files: adding files, folders, list or icons, in-app preview (2026-10-31)

At the user's request. "Open in the browser" downloaded Word and UDF files, which browsers
cannot show, so a file now opens in an in-app preview (`components/files/FilePreview.tsx`,
`GET /files/{id}/preview`): a PDF in the browser's viewer, an image as itself, any other
readable document (a petition by its draft) as an A4 page rendered from the editor's schema.
Files are added on the page (button or drop onto the page) through the same upload as
attachments, so each is read and labelled at once; the folder open at the time receives them.
Folders (`file_folders`, `stored_files.folder_id`, migration `e2f6c9d4a1b7`,
`api/folders.py`) nest; files and folders move by drag and drop onto a folder or the path,
or through "Taşı"; a folder cannot go inside itself; deleting a folder moves what it held up
one level. The page shows a list or icons (remembered per browser). A file can be given to a
case ("Davaya ekle", `PATCH /files/{id}` with `matter_id`), which makes it material in that
case's chats (D66). While a filter is set, matching files are shown from every folder.
Delete asks with the browser's confirm dialog.
Then several items at once (`components/files/useSelection.ts`, `SelectionBar.tsx`): tick
boxes on hover, Cmd/Ctrl-click to add, Shift-click for a range, Cmd/Ctrl+A for what is shown,
Esc to clear; a bar offers move, copy, give to a case and delete; dragging a selected item
moves the selection. Copying (`POST /files/{id}/copy`) makes a file of its own in the chosen
folder, read and labelled again, with " (2)", " (3)"... when the name is taken there; it
applies to files (folders are moved or deleted).

## D69 — A word-processor editor for petitions; "Dosyalarım" as a page (2026-10-31)

The user asked for Word-like editing of petitions and for "Dosyalarım" to be a page where
files can be edited, not a drawer.

Editor (`components/PetitionEditor.tsx`, TipTap 2.27.2, MIT): an A4 sheet in Times New Roman
12 with undo/redo, size, bold, italic, underline, four alignments and bullet/numbered lists.
Citation markers show as small numbered chips that cannot be typed over. The draft's text
stays the record (answers, the four one-click buttons, style learning read it); the editor's
document is kept beside it in `drafts.meta.doc` with a fingerprint of the petition it was made
from (`drafting/rich.py`). While the petition is unchanged, Word, PDF and UDF are made from the
document, so italics, underline, sizes, alignment and lists reach the files; the export runs
now carry these (`export.Run`). A one-click change rewrites the text, and the document is
made again from it (bold survives through **, other formatting of the rewritten part does
not). The buttons act on a selection by its text (`drafting/locate.py`, matching without **
and with any whitespace). Saving sends the document (`PUT /drafts/{id}` with `doc`); the
note and checklist around the petition are kept. Beside a chat the editor is a side panel
with a "Tam sayfada aç" button; the chat's layout now follows its own width (container
queries), so the sources column drops below the answer when the panel is open.

"Dosyalarım" is a page in the main area (`components/FilesView.tsx`): rename (the
extension stays; a petition's file renames its draft), open in the browser, download, delete,
and "Düzenle", which opens a petition's draft, or for a document the lawyer added an
editable copy made once (`POST /drafts/from-file/{id}`) so the original stays. Edits to such
a copy do not teach the style profile.
Then, at the user's request: the editor saves as the lawyer types (a one-second pause; saves
never overlap; a failed save is retried; pending changes are saved when the editor closes or
the tab goes away, `lib/editor/useAutosave.ts`), and the Save button became a saving / saved
state. Autosaves (`learn: false`) do not learn the style, since learning reads the change
with a model and would run every few seconds; the text before the session is kept
(`meta.learn_base`) and the style is learnt once from the whole session when the editor
closes (`POST /drafts/{id}/learn`). PDF and Word files now carry the petition's title (PDF
viewers showed reportlab's default author, "anonymous").

## D68 — The sidebar search covers files and their documents (2026-10-31)

The search box looked only in chats. It now also finds case files by their details (client,
subject, other side, court, case number, notes) and the documents in them by name or text
(`matters/search.py`, `GET /matters/search`; a document is in a file when added to it or
attached in one of its chats), with the chat search's matching (Turkish casefold, partial
words, every term must match). Results come in three groups, files, documents and chats
(`components/SearchResults.tsx`); a file or document opens the file. The box moved below
"Takvim", is labelled "Ara", and snippets no longer show Markdown marks.
Then, at the user's request: a case file is called a "dava" on screen (the section is
"Davalar"; "Yeni dava", "Davaya ekle", "Davayla sor"...), so it is not confused with
"Dosyalarım" (the lawyer's uploaded and generated files), which moved from the user menu
to the sidebar under "Takvim". The order is Yeni sohbet, Takvim, Dosyalarım, Ara. "Dosya
türü" for a deadline's branch stays, as UYAP names it so. Code and API keep "matter".

## D67 — A chat outside any file asks before using a file it names (2026-10-31)

The user asked that a chat outside the files can reach them, but without noise and never
tying a message to the wrong file. So nothing is inferred: a message counts as naming a file
only when it contains an open file's client name in full (at least two words, in order, as
whole words, Turkish case-insensitive) or the file's case number exactly (`lib/matterMatch.ts`);
a first name, a surname, a longer word that starts with the name, or a nearby number does
not count, and closed files are skipped. When a file is named, the message is held and the
lawyer chooses (`components/MatterSuggest.tsx`): "Dosyayla sor" moves the chat into the file
(so D66's details and documents go with it) and sends; "Dosyasız sor" sends as is and the
chat is not asked again. Several named files are listed for the lawyer to pick. No model call
is made for this.

## D66 — A case file's documents are read in its chats (2026-10-31)

Until now a question in a case file carried the file's details, notes and only the names of
its documents; a report uploaded to the file was not seen unless attached again. Now the
documents themselves go with the question (`matters/documents.py`): whole when all of them
together are short (12,000 characters), otherwise only the chunks nearest the question
(paragraph chunks, the local embedding model, at most 8 chunks / 10,000 characters, in
document order), so no model call is spent choosing them and the cost per question stays
about the same. They go as case material like an attached document, not as legal sources.
Chunk vectors are cached per document. Files attached to the message itself and images are
left to the existing attachment path. Live test with a made-up report in a temporary file
(deleted afterwards): the answer gave the report's fault shares and amount correctly.
A chat outside any file still sees no file.

## D65 — A deadline computed from the notice (2026-10-31)

Adding a deadline to a file opens a dialog (`components/DeadlineForm.tsx`) that, by default,
asks what is on the notice instead of the last day: when it came and how (electronic, at a
hearing, by hand), the period (number and day/week/month, with 1 week / 2 weeks / 1 month
shortcuts) and the branch (civil, criminal, enforcement, administrative, arbitration,
remembered per file). The server computes the last day (`POST /deadlines/calculate`,
`calc/notice.py`) with the existing period calculator and shows each step before saving.
Rules, with sources, in `locales/tr/deadline_rules.json`: electronic service counts at the end
of the fifth day after it reached the address (Tebligat K. 7/a); a period ending in the
recess is extended 7 days in civil (HMK 104) and administrative (İYUK 8/3) matters, 3 days
in criminal ones (CMK 331/4, with a note that detention matters are not extended), not at
all in enforcement; arbitration is not extended and the lawyer is told it depends on the
agreed rules. "Son günü biliyorum" keeps the old direct entry. Suggested by the user from
another app's form; work types with preset periods were left out until each period can be
sourced.
Later the same day: the branch is chosen in both modes and saved with the deadline
(`matter_deadlines.branch`, migration `d1e5b8c3f9a2`), shown beside its date in the file and
the calendar list, since a lawyer who knows the last day may still want it recorded; the
period box got small up/down buttons (and arrow keys).

## D64 — Interest calculator (2026-10-31)

Interest on a sum is computed in code, never by the model (`calc/interest.py`,
`calc/interest_text.py`), the same way as periods and severance. Rates live in
`locales/tr/interest.json` with their sources: the statutory rate (3095 art. 1: 9% from
2006-06-01, 24% from 2024-06-01 by Presidential Decision 8485, 31% from 2026-07-31 by Law
7589 art. 10) and the central bank's advance rates from 2018 (TCMB table, read 2026-10-31),
for commercial matters (3095 art. 2/2). Simple interest, 365-day year, split where the rate
changed, starting the day after default. Days before the first listed rate, or after the
date the tables were last checked, are flagged in the text. The understanding step gets an
`interest` field (principal, start, end, kind); when it cannot tell whether the matter is
commercial both results are given and the answer says which facts decide. The calculation
is cited like a source (evidence kind "calculation"). Live test: one question, $0.039.

## D63. Case files ("Dosyalar") with their deadlines, and a calendar (2026-10-31)
Lawyers work by file ("müvekkil X'in boşanma dosyası"), and competitors offer case and
deadline management; chats and files were loose. Now:
- Tables `matters` (client, subject, other side, court, docket number, notes, closed) and
  `matter_deadlines` (label, due date, done, the answer it came from); chats and stored
  files can belong to a matter (`matter_id`, migration `c9d4a7b2e8f1`). API in
  `api/matters.py`: files list with each one's next deadline, a file's chats, documents,
  petitions and deadlines, edit and delete (its chats and documents stay, outside any
  file), documents added straight to a file, deadlines added, ticked done or removed, the
  calendar of every open file's deadlines, and a chat moved into or out of a file.
- Every question in a file brings the file with it (`matters/service.py: context`, given as
  material like an attachment): parties, court, docket number, the lawyer's notes and the
  names of its documents, so the case is not told again in each chat.
- A period computed in an answer (D61) is kept in the answer's trace with its last day; in
  a file's chat the answer offers to put it in the file's deadlines with one click (both
  days when the judicial recess decides).
- Web: the sidebar lists open files above the loose chats, each with a badge for a deadline
  within two weeks (amber within three days, red when missed), plus "Takvim". A file's
  page: the client in serif with subject, court, docket number and other side; its chats
  and its documents and petitions as plain ruled lists; on the right, on the desk colour,
  the next deadline set large as days left, the others with a tick for done, adding one,
  and the notes; the message box below asks in the file. The calendar groups open deadlines
  as missed, this week, next week and later, the day large on the left. A chat in a file
  shows the way back to it; a loose chat can be put in a file.
Checked with screenshots of a test file (headless Chrome, as the browser extension was not
connected) and one question asked in it at "fast" ($0.005): the answer used the file's
other side and court, computed 3 November 2026 for the appeal, and its deadline went into
the file with one click. The test file is left in the demo account as an example.
Added the same day at the user's request (the calendar read as a list): a month view, the
default, beside the list (`components/MonthGrid.tsx`): weeks from Monday, today marked, each
day's deadlines as two-line labels (what, whose file) coloured by nearness and opening the
file, weekends and official holidays set back with the holiday's name, half-day eves noted,
the judicial recess hatched from its first day; arrows move by month and "Bugün" returns.
Holidays and the recess come from the period calculator's own data (`GET /holidays/{year}`),
and a year without its religious holidays is said to be so.
The title is two buttons (`components/PeriodPicker.tsx`): the month opens the twelve months,
the year opens a page of twelve years with arrows, so a date a year away is two clicks.
A click on an open deadline's circle no longer hides it at once: it opens "Tamamlandı / Sil / ×"
under the line (`components/DeadlineActions.tsx`), in the file panel and the calendar list,
because a slip of the mouse moved deadlines out of sight.

## D62. Severance and notice pay computed in code (2026-10-31)
Second calculator (after periods, D61). `calc/severance.py`: service counted in whole
calendar years, months and days with both ends included (1 March to 31 August is six
months); severance pay thirty days' pay per full year and pro rata beyond, on the gross pay
with regular extras capped at the ceiling in force on the last day; none under one year;
stamp duty (binde 7,59) shown deducted; notice pay of 2/4/6/8 weeks by service under 6, 18,
36 months or longer, on the uncapped pay, shown gross (its income tax depends on the year's
earlier pay). Ceilings for 2025-2026 are in `locales/tr/severance.json` with their sources
(the ministry's 1980-2025 table and the Treasury circulars; 73,729.87 TL from July 2026, not
the 73,729.84 some sites print); an unlisted period is flagged, never guessed, and each new
half-year's ceiling has to be added there. The understanding step gives start and end
dates, gross pay and regular extras; `calc/severance_text.py` writes the result out step by
step in Turkish money format, cited with 1475 art. 14 and 4857 art. 17. Whether the way the
contract ended gives the right is left to the answer, the calculation says so. One real
question at "fast", $0.009: 1 March 2023 - 31 August 2026, 60,000 TL + 5,000 TL extras:
3 years 6 months, 227,500.00 TL gross severance, 1,726.73 TL stamp duty, 121,333.33 TL
notice pay for 8 weeks, all as computed by hand.

## D61. Procedural periods computed in code and cited as a source (2026-10-30)
First of the calculators the user put before deployment work (periods, then severance and
notice pay, interest, fees). A model computing dates is the one place a confident wrong
answer costs a lawyer a case, so dates are computed in code:
- `calc/deadlines.py`: a period in days ends `amount` days after its start; in weeks,
  months or years on the day of the same name or number (end of a short month); a last day
  in the judicial recess moves to one week after it ends; a last day on a weekend or an
  official holiday moves to the next working day; a half-day eve is flagged, not decided; a
  year whose religious holidays are not listed is flagged, never assumed.
- `calc/calendar.py` with `locales/tr/calendar.json`: fixed holidays, half-day eves, the
  2026 and 2027 religious holidays (checked across several published calendars) and the
  recess, each with its source. Each new year's religious holidays have to be added there.
- The understanding step names each period asked about (label, start date read against
  today's date, now given to it, length, law and article); `calc/sources.py` computes it,
  fetches the article and checks that its text states that length (number word or digit
  with the unit), and adds the result as a source of kind "calculation" written out step by
  step, cited like an article (`EvidenceLedger.add_calculation`). Whether the recess
  applies is not taken from the model (it called a money claim exempt): when the recess
  changes the last day both days are given with civil procedure arts. 103-104.
- The writer copies dates from the calculation and says its warnings; a "Süreler
  hesaplanıyor" step shows in the progress list.
Two real questions at "fast", $0.009 and $0.007: notice served 7 March 2026, appeal period
two weeks (HMK 345, confirmed in its text), calendar end Saturday 21 March in the Ramadan
holiday, answer Monday 23 March with art. 93; served 7 July 2026, calendar end 21 July in
the recess, both days given, answer 7 September, explaining that a money claim is not among
the matters handled in the recess. Seen in passing: the appeal threshold quoted from the
statute text (3,000 TL) is the original figure, not the yearly revalued one; to be handled
with the fee calculator.

## D60. Request lines above the court set at the top right (2026-10-30)
User question about the "İHTİYATİ TEDBİR TALEPLİDİR" line: it belongs above the court, but
the files centred it as if it were the court's heading. The lawyer's own petitions set such
a line ("ADLİ YARDIM TALEPLİDİR") at the top right. A heading line ending in
"...TALEPLİDİR" before the court (word in `locales/tr/style.json`, "request_flag") is now
right-aligned in Word, PDF and UDF, and the court below it centred; body paragraphs are
justified in Word too, as they already were in PDF and UDF. Checked on the latest divorce
petition's PDF.

## D59. Option questions answered from the message box, with the typed answer (2026-10-30)
User report: the option questions sat under the answer with their own send button, so a
lawyer who sent the chosen options could not also answer, in words, the questions the
answer asked in its text. The last answer's option questions (and the "write without
them" action of a question turn) now sit in the message box above the text
(`components/AnswerChoices.tsx`); choosing only marks an option, and one send carries the
chosen answers ("Question? Answer" lines) followed by what was typed. Redesigned the same
day after the user rejected two versions (all questions stacked with form-like boxes; a
separate card with a vertical list): a compact strip docked to the top of the box, one
question per line with a 1/3 counter and arrows, options as small choices (the chosen one
dark with a tick), moving on to the next unanswered question when one is chosen, and no
instruction text. They are cleared by
a new answer and can be closed. Checked in the browser: choosing an option enables send.
The running step's dot now beats (two beats and a rest) instead of standing still.

## D58. An edited copy of a sample asks to replace the old one (2026-10-30)
User question: a petition uploaded again with one paragraph changed was added as a second,
separate sample (only identical text was caught), so one petition counted twice and the old
wording could still be imitated. Now a new sample is compared word by word with the
lawyer's samples (`drafting/store.py: similar_sample`, no model call, about 10 ms); above
an overlap of 0.55 the upload stops before the model reads it and the lawyer is asked
whether it is the updated version of that petition: "replace the old one" (the old sample
is deleted, the new one takes its place, its type kept if the reading finds none) or "keep
both". Measured on the lawyer's six divorce petitions: different petitions shared at most
0.43 of their words; a copy with one paragraph rewritten 0.87-0.90, with half rewritten
0.58-0.61. Tried in the browser with a test petition and its edited copy (two model
readings, about $0.001); the test sample was then removed.

## D57. The lawyer's samples are read by the model, not sorted by word lists (2026-10-30)
User direction: no rule-based sorting; whatever makes the understanding accurate. The word
list of D56 typed petitions by counting words, scored a divorce petition that told of
violence nearly as criminal as family (19 against 21), and could not tell an agreed divorce
from a contested one, though they are written very differently.
- Each sample is read once when added by the cheap model (`drafting/sample_profile.py`,
  prompt `sample_profile`): whether it is a petition, its petition type, its area of law,
  its case kind (`drafting/cases.py`; "contested divorce" excludes an agreed one) and the
  matter in a few words without names or amounts. Kept in `style_samples.profile`
  (migration `b8c3f6a1e7d2`); samples kept earlier are read when the list is next opened.
  The sample's meaning vector is now taken from the matter and the opening, not the opening
  alone (mostly court, parties and addresses).
- The case's area comes from the understanding step (new `area` field), not a word count of
  the request; its case kind was already there.
- The sample imitated is of the case's kind first, then of its area; a sample of the same
  area but another kind (an agreed divorce for a contested one) or of another area is given
  for its language only.
- The petition-type word list and request-area threshold of D45/D52/D56 are removed; the
  file filters (D45) still use the word list.
The lawyer's six UYAP samples, read for $0.003 in all: two agreed divorces (no case kind),
four contested divorces (case kind "bosanma") with their grounds and requests as matter.
Tests stand in for the model's reading by file name (the first run after the change called
the model for about half a cent).

## D56. Many petitions added at once, each read and sorted (2026-10-30)
User request: add many of one's own petitions at once, in mixed formats, and have each read
and sorted by type and matter. "My petitions" now takes several files at once (picked or
dropped; Word, UDF, PDF, ODT, RTF, text), uploads them one after another and shows a line
per file. Each is sorted on the server with no model call: its petition type from a
weighted word list on its title (`petition_types` in `locales/tr/document_labels.json`,
`files/labels.py: petition_type`; title words count in the first 250 characters, since a
short suit petition named a notice in its evidence within 800), its area of law (D45) and
its format. A clear petition with a weak type signal takes its best type (a lawyer's divorce
petition scored only its court address). Refused with the reason shown: a document
recognisably not a petition (a decision, a payment order, a contract), the same text twice,
a file with no text (a scan), a damaged or unsupported file, a text too short. The list is
grouped by petition type with each sample's matter and format, and a wrongly sorted one is
corrected in place (`PUT /drafting/samples/{id}`). Measured: 22 of 23 published samples
typed as their folder says (the other left unknown), the lawyer's petition typed "dava".
In the browser, of four files (a UDF suit, a text labour suit, its copy, a decision) two
were added and two refused with their reasons; the UDF suit was first typed as a notice,
which the title rule fixed. Dropping files on the panel no longer reaches the chat box.

## D55. UYAP (.udf) petitions accepted as the lawyer's samples (2026-10-30)
Reported by the user: a UDF petition could not be added under "my petitions". The server
reads UDF (D43), but the sample picker only offered .docx, .pdf and .txt. It now offers
.docx, .udf, .pdf, .odt, .rtf and .txt; a damaged archive or a file with no text is refused
with a clear error instead of a server error. Tested with a UDF made by our own exporter;
a UDF saved by UYAP's editor has not been tried.

## D54. Petition structure: requests settled first, rules kept in code (2026-10-30)
User direction after D53: the problem is the structure, not the model. What changed:
- The petition's requests are settled before it is written: the facts check (D46, same
  cheap call, `draft_gaps`) also returns what the petition asks the court for, from what
  the lawyer wants and the case kind's requests; the writer gets them as
  `<requests_to_make>` and writes each as its own numbered request. Left to the writer, the
  same divorce request got the car's interim measure in one run and not in the next. The
  call's limit rose to 6,000 tokens (the longer answer was cut off at 2,500), and an
  unreadable answer now lets the petition be written without asking instead of failing.
- Rules a writer was told and broke are applied in code after every model-written draft
  or button rewrite (`drafting/tidy.py`): long bracket notes move to the checklist leaving
  the bracket's name; sentences about the petition itself are dropped (patterns in
  `locales/tr/style.json`); a petition that asks for an interim measure gets the line above
  its heading.
- The statutes on a petition's contents are now to be met by its structure (parties,
  evidence after each paragraph, numbered requests), not by saying they are met; each claim
  the lawyer made is pleaded on its own ground even when details are missing, which go to
  the checklist (one run had argued only the general ground).
- A citation marker from a writer without document citations cites only the sentence
  before it, so headings and signature blocks are no longer judged and flagged.
Same request, three reruns at $0.015-0.019 each (two more stopped at the facts check for
under a cent): the last had all three grounds with decisions, the car's measure and the
reserved claims among its seven requests, no self-talk and no bracket notes; the header,
missing from it, is now added in code (checked on that draft without a model call).

## D53. No negative headings or explanations in brackets; courts named by case kind (2026-10-30)
A lawyer rejected a Luna petition (divorce, written without the facts asked for) that opened
with "[İHTİYATİ TEDBİR TALEBİ YOKTUR]", left the court as "[GÖREVLİ MAHKEMESİ]", put an
explanation inside the value's brackets, and asked for nothing about the car the client
wanted. Rules added: a conditional heading or section is left out when its condition does
not hold, never written as "none"; brackets only name a missing short datum; the court is
written by name when the case guide or sources give it. Each case guide now names its
court (family, labour, civil court of peace), and the divorce guide asks for an interim
measure on an asset the client wants even when no risk of its sale was stated (the basis
goes to the checklist). The same request rerun once ($0.015): interim-measure header,
family court by name, the car's measure requested. Left: Luna still writes one sentence
about the petition itself, two longer bracket notes, and argued only the general ground
(the special grounds' time limits went to the checklist).

## D52. The lawyer's sample to imitate is chosen by area of law first (2026-10-30)
User question: with samples of different matters uploaded, could a labour petition be
written from the divorce sample? Measured with the local embedding model (no cost): the
right sample was closest for a dismissal, a divorce and an eviction request, but for the
dismissal by 0.859 against the divorce sample's 0.849, and with no sample of the case's
matter the closest of another matter was handed over as the example. Now each sample and
the request get an area of law from the word list of D45 (`files/labels.py`; a request is
read with a lower threshold, `REQUEST_MIN_AREA` = 3, since it names its matter once).
Samples of the request's area are preferred, then closeness in meaning; a sample of
another area is still given for the lawyer's language but marked `kind="other_area"`, and
the writer is told to take only its language, forms of address and closing, not its
sections, requests or law. A request whose area cannot be told is matched by meaning.

## D51. Questions never ask for what was already said; none under a petition (2026-10-30)
Found by the user on an unfair-dismissal petition: under the petition, the old
"to sharpen the answer" box asked how many employees the workplace has, while the request
said "about 40-50". The facts check (D46) had judged the request complete (score 1.12) and
written straight away; the box came from the understanding step's clarifying questions.
The understanding prompt now forbids asking (or listing as missing) anything the message,
attachments or earlier chat state, approximate figures included; and a petition written
without asking shows no question box, since what is missing is in its checklist. Checked
once on the same facts as a consultation ($0.001): it asked only for the dismissal and
mediation dates.

## D50. Three petition levels that differ in what the lawyer gets (2026-10-30)
With Luna writing fast and balanced petitions (D48), the two differed only in how many
sources were read, which a lawyer could not see; the user chose to keep three levels and
make "fast" clearly different. A fast petition searches no court decisions (neither per
ground nor in research) and reads fewer articles; balanced searches a decision for each
ground; deep adds sources and decisions and is written by Sonnet. The level hints say so.

## D49. No Sor/Ara switch: what a message asks for is understood from it (2026-10-30)
User request: lawyers prefer a system that works out what to do from the chat. The
understanding step already names the task (answer, consultation, petition, search for
decisions or articles, review) and a search task always searches decisions (D33), so the
switch is gone from the message box and every message goes through the chat. The old
"Ara" view (decision cards from `/search/decisions`, not kept in the chat) is removed from
the web app; the route stays in the API. A search now answers in the chat with its
sources, so it is kept, can be followed up, and is metered like any answer.

## D48. Petitions written by GPT-6 Luna except at "deep" (2026-10-30)
Chosen by the user after D47. Not a fine-tune (no training set of good petitions, and a
tuned model is not served through OpenRouter); Luna is tuned by how the system uses it:
- Citations for writers without document citations: the writer puts [[E#]] after the
  sentence (prompt `quote_citations`); the text is cut into segments at the markers
  (`agent/atoms.py: openai_segments_from`), a marker for a source not given is dropped, and
  every cited segment with no verified quote is judged against its sources by `check`
  (JEV), as numbered sentences already were. The old inline quote form is still read, but
  its words no longer stay in the prose (they broke GLM's and Terra's sentences).
- Each ground's decision is given to the writer with its citation and the passage that
  bears on the ground (`<ground_precedents>`, 900 characters each): given keys only, Luna
  cited no decision.
- `draft_route` (default `openai/gpt-6-luna`) sends the petition writer to OpenRouter
  (hosts that may train on prompts excluded) at fast and balanced; "deep" keeps Sonnet.
  Without an OpenRouter key petitions are written as before.
Measured on the D46 case at "balanced": $0.017 in all (writing $0.003, the citation check
$0.004), 1,070 words, family court, interim-measure header, three decisions quoted with
their citation, interim custody and maintenance, the car's annotation with the
regime's claims reserved, no invented facts; one decision quoted under the wrong ground,
one paragraph about the petition itself, and the children named as witnesses (the divorce
guide now says not to). Sonnet cost $0.157 on the same case.

## D47. Cheaper petition writer: Haiku 5.5, GLM-5.3, Qwen3.7 Plus, GPT-6 Luna and GPT-6.1 Terra tried, Sonnet kept (2026-10-30)
Asked to cut cost with a cheaper writer (one candidate per role, one test, budget tight).
The other roles already run on Claude Haiku 5.5 ($0.10/$0.50 per MTok), as cheap as any
listed alternative; the writer (Sonnet 5.5) was about 85% of a petition's cost. The same
divorce case (D46 facts) was written once per candidate:
- Sonnet 5.5 (earlier run): $0.157, 1,011 words, right court, every ground with a quoted
  decision, interim measures complete.
- Haiku 5.5: $0.021. Named the civil court of first instance instead of the family court,
  left out interim maintenance and temporary custody, a time-limit sentence inside the
  petition, facts and law separated.
- GLM-5.3 through OpenRouter (`write_route`): $0.028. Applied a decision about another
  couple's facts to the client ("the defendant's health ... fault lies with the husband"),
  called the client "less at fault", discussed time limits in the petition, and statute
  quotes ran into sentences without punctuation (partly our quote-marker format for
  non-Claude writers, which has the writer inline exact quotes).
- Qwen3.7 Plus through OpenRouter: $0.028, 1,119 words; the closest to Sonnet: right
  court, a quoted decision per ground, complete interim measures, nothing against the
  client in the petition. But it added facts the lawyer never gave ("the messages show
  their meeting plans", "having learnt of the suit, the defendant tried to sell the car"),
  asked for the car to be "seized" (haciz) instead of an annotation against transfer, and
  kept a mediation section. A check of the petition's facts against the conversation
  would be needed before a writer like this is trusted.
- GPT-6 Luna through OpenRouter: $0.015 in all ($0.003 for writing), 1,024 words; family
  court, interim measures (including interim maintenance) and the car's annotation right,
  no invented facts, risks left to the checklist; but no court decision cited (statute
  quotes only) and two sentences about the petition itself.
- GPT-6.1 Terra: $0.047, 718 words; correct content and quoted decisions, but the court
  left as a placeholder and citation fragments appended after sentences and in the note.
Non-Claude writers are handicapped by our citation format for them (inline
<quote ref> tags, kept as "quote [[E#]]"): GLM's and Terra's sentences broke around it.
Sonnet stays the petition writer; at the planned price a petition still leaves about 60%
gross margin. Kept from the attempt: `write_route` sends only the writer to OpenRouter
(hosts that may train on prompts excluded); the non-Claude citation parser now keeps the
text and drops only citations it cannot verify (it had discarded a whole petition for one
malformed marker); a routed reasoning model gets the answer's effort level (left at its
default, GLM spent all 16,000 tokens thinking and wrote nothing). Those two failures cost
$0.13 before the working run. Chat answers on a cheaper writer were not tested.

## D46. Petitions by kind of case; ask for facts only when the request is thin (2026-10-30)
A lawyer judged a contested-divorce draft from a four-line request unusable and sent one of
their own petitions (about 1,800 words, "even this is sometimes short"). Our draft (590 words)
was a form full of placeholders, argued against its own client ("the party who forgave has no
right to sue"), explained why mediation did not apply, summarised statutes as bullets, cited
no decision, and asked for the car to be "given" to the client where a lawyer asks for an
interim measure against its sale. The user rejected asking questions every time.
- Case kinds (`drafting/cases.py`, `playbooks/tr/petitions/cases/*.md`: contested divorce,
  labour receivables, eviction; `_genel.md` for the rest): the facts the petition rests on
  ("!" marks essential ones), the usual requests (with interim measures) and how it is
  written, with a default length. No statute articles there: they come from the sources.
  The understanding step names the case kind; the list is read from the playbooks.
- Ask or write (`drafting/asking.py`): the cheap model marks each fact given, partly given or
  missing over the whole conversation (prompt `draft_gaps`). Score: essential missing 1,
  partly 0.5; other facts a quarter of that. Asked at 2.0 (the four-line request scored
  2.75-2.88 over five runs). The threshold follows the lawyer's replies (profile
  `preferences.asking`): two more skips than answers -> asked only when about nothing
  essential is known; two more answers -> asked at 1.25. Never twice in a row, never when
  the message says to write without questions (`write_now`; a plain "write a petition" is
  not that: the first prompt wording made it so and nothing was ever asked). A question
  turn does no research and cost $0.001-0.002; it offers one-click answers and a "write
  without them" button. The reply is answered together with the original request.
- A decision for each ground (`drafting/prepare.py`): each issue is searched for a precedent
  of its own (2/4/6 grounds by power) and the writer is told which decision supports which
  ground (`<ground_precedents>`).
- Writing rules (`prompts/tr/draft_brief.md`): placeholders only for short data, never for a
  narrative; nothing that works against the client (forgiveness, time limits go to the
  checklist); no conditional hedging of the client's claims; per ground: facts, why they meet
  it, the decision's own words quoted, evidence; no empty decision summaries; no sentences
  about the petition itself; no self-correction; omit sections that do not apply (the suit
  outline's mediation section now says so; the legal grounds list no longer summarises).
Measured on the same request with test answers: asked 5 questions ($0.0016), then a 1,011-word
petition ($0.157) with an interim-measure header, four grounds each with a quoted decision,
the car handled by an interim measure, and forgiveness, time limits and the weak proof of
adultery by messages in the checklist. The lawyer's own petition was read only; it holds
personal data and was not stored or added to the repository.
- Found in use (same day): "Genişlet" without a selection rewrote the whole stored text, and
  the model dropped the one-line note with its dashes, so the checklist went into the
  petition file; and "İndir" stayed active while the change ran, so the lawyer downloaded the
  file from before it. Now a button without a selection rewrites only the petition
  (`drafting/style.py: petition_span`), a rewrite that changes the dashes is rejected, and
  the download waits for the change and saves pending edits first. The expansion itself
  added about 210 words (957 -> 1,171) for $0.11.

## D45. File filters: format, kind of document, area of law (2026-10-30)
User request: two filters in the files panel, format and content, ideally by type of case.
- Format comes from the file name (word, pdf, udf, image, spreadsheet, email, text, other);
  it is computed when listed, not stored.
- Kind (petition, notice, decision, contract, expert report, enforcement paper, power of
  attorney, minutes) and area (labour, tenancy, family, enforcement, criminal, commercial,
  consumer, administrative, inheritance, property, compensation) are chosen by a weighted word
  list (`locales/tr/document_labels.json`, `files/labels.py`) over the file name and the first
  12,000 characters of the text already read: no model call, no cost, a few milliseconds.
  Kind title words count only in the first 800 characters; area words count up to three
  occurrences each, so the matter outweighs a passing mention. No clear winner gives "other".
- Labels are stored on `stored_files` (`kind`, `area`; migration `a7b2e5f9d4c6`) when a file is
  saved; files kept earlier are labelled the first time the list is opened. A drafted
  petition keeps the kind it was made as (notice for ihtarname, otherwise petition).
- The panel shows three dropdowns (Format, Belge türü, Dava türü) offering only values present,
  each with the count the other choices would leave; each file shows its kind and area.
Rejected: a model call per file (cost per upload, and the word list was right on all test
documents); embedding similarity to area descriptions (less predictable for short files).
Known limits: scans with no text are labelled by their name only; one area per file.

## D44. Learnt preferences chosen by meaning, with confirmation and reset (2026-10-30)
User question: is the learning rule-based or semantic? With rules only, every prompt would in
time carry a long list about the lawyer. Answer and change: the measured style stays a fixed
set of numbers (length, register, headings, closing; buttons and edits move two values), so it
does not grow; preferences that are not numbers are now learnt as sentences and chosen by
meaning. Conditions set by the user: no drift, a reset, no extra latency or cost.
- When a draft is saved, the cheap model compares it as written and as saved and states at most
  three general writing preferences (`drafting/memory.py`, prompt `style_extract`), after the
  response, in the background. Sentences with a number (amounts, dates, articles) and anything
  marked as specific to the case are dropped; legal rules are not preferences.
- Each preference is stored with a meaning vector (table `style_memories`); the same preference
  found again (cosine >= 0.92) is counted, not stored twice; at most 60 kept. A preference is
  used only after two separate edits showed it.
- When drafting, the six confirmed preferences closest in meaning to the case are given as
  <learned_preferences>; the writer is told legal rules, required contents and citations come
  first. The sample to imitate is now the lawyer's petition of the same type closest in
  meaning to the case (sample vectors stored at upload), not the longest.
- The style panel lists what was learnt ("kullanılıyor" or "bir kez görüldü"), each can be
  forgotten, and "Öğrendiklerini sıfırla" forgets all learnt preferences, the length and
  language chosen and the formats counted (own petitions and written wishes stay).
Measured: a simulated edit gave three preferences ("müvekkil" for "davacı", "kiracı davalı",
a procedural section) and correctly ignored an address correction; $0.0006, 3 s in the
background; choosing by meaning adds about 16 ms (local model) to an answer.

## D43. Attachments, a file space per user, answer power, usage meter (2026-10-30)
User: a composer laid out like an IDE chat box: a choice of how hard to work (no model names),
deep research included; a usage indicator that opens on a click; another control instead of the
send button; an attachment button, drag and drop and paste, many formats; attachments and the
files the system makes kept per user in a 5 GB space (chats not counted), managed in one place;
local storage for now.
- Files: table `stored_files` (origin upload or generated, links to chat, message and draft,
  size, sha256, text read from it), files on disk under var/storage/users/<user>/<file>/;
  quota `USER_STORAGE_BYTES` (5 GB), 50 MB per file; routes /files (upload, list, usage,
  download, delete). Read: docx, pdf, udf, odt, rtf, xlsx, eml, html and text formats; images
  are given to the model as images (png, jpeg, gif, webp); other files are kept but not read.
- A message may carry file ids; they are linked to the message, given to the understanding
  step as excerpts and to the writer in full as the case's material, not as legal sources;
  a message with attachments is not treated as a reformat.
- Generated petitions are stored in the user's space in their format (and in other formats
  when downloaded), made again when the draft changes.
- Power (`agent/power.py`): Hızlı (cheaper model writes, 8 articles, decisions only when
  needed), Dengeli (default), Derin araştırma (16 articles, decisions always, 8 read and 4
  kept, the writer thinks longer); remembered in the browser.
- UI: the composer has an attachment button, chips for attachments, page-wide drop and paste,
  the mode, the power menu, a round send/stop button; a usage ring under it opens today's
  answers and spend against the daily limit and the file space; "Dosyalarım" (from the
  account menu or the usage panel) lists, filters, downloads and deletes files. The composer
  is pinned inside the scrolling area so its menus are not cut and its edges match the text.
Checked: tests, the browser (menus, usage, files panel), and one fast answer with an attached
notice through the API ($0.014; the answer used the notice's own period).

## D42. Interface rework: collapsible desk, account menu, plain-language style (2026-10-30)
User: the interface was too plain; the sidebar must collapse and keep new chat, search and
the account as icons; the account must open a menu as in ChatGPT and Claude, holding the
petition samples; the samples panel was too technical for lawyers; the composer did not line
up with the chat. Changes: the sidebar (a darker "desk" tone) collapses to an icon rail
(state kept in the browser), chats are grouped by today, yesterday, this week and older; the
account menu holds "Yazım tarzım", model settings (admins) and sign out; "Yazım tarzım" shows
the current style as one sentence and lets the lawyer pick length (short, medium, long) and
language (plain, balanced, formal) or leave both to be learnt (`PUT /drafting/profile/style`;
a choice replaces what the samples show and the buttons and edits move on from it), adds own
petitions and written wishes. The composer shares the answer column's grid (it was 42rem
against a column squeezed to about 40.5rem) and both areas reserve the scrollbar width (the
scrolling area was shifted by half a scrollbar). Icons: lucide-react 1.55.0. Checked in the
browser: alignment, the menu from the row and from the rail, the style choices, collapse.

## D41. A petition is delivered as a file in the lawyer's format (2026-10-30)
User: asking for a petition must give a petition file, not text to copy; Word for a first
petition, else the format the lawyer asked for before (learnt across chats), the most asked
one, Word on a tie. Now: the understanding step reads a format named in the message
(docx, pdf, udf); every such mention is counted in the lawyer's profile, in any chat
(`drafting/formats.py`: named format, else most asked, Word when none or tied). A drafting
answer is not streamed; the chat shows the one-line note, the checklist and a file card
(download, other formats, edit), the file holds only the petition. Files: Word
(python-docx), PDF (reportlab, a system serif font with the Turkish letters: Times New Roman,
else DejaVu or Liberation Serif), UDF (UYAP editor format 1.8: ZIP with content.xml, the text
in one CDATA block, paragraphs pointing into it by offset; written from the structure the
UDF-Toolkit project documents, no published specification, not yet opened in UYAP's editor).
Named by the chat title. Checked through the running API ($0.20): no text streamed, PDF
chosen from the message, all three files produced; the PDF reads as a court petition.

## D40. Drafting practice learnt from published samples (2026-10-30)
The user: published samples are shared to be used, learning from them is lawful. Changed D39:
`drafting/study.py` fetches the sample pages listed per type (robots.txt, one request per
second per host; a site refusing automated access is skipped, not worked around), keeps the
text in var/ only, and the cheap model turns them into per-type practice notes
(`playbooks/tr/petitions/<type>.practice.md`, own words, at most 450 words) that the writer
gets beside the outline. 24 samples, $0.08. A draft of the eviction case without an own
sample then added the rent claim, occupation compensation, evidence per fact and numbered
annexes ($0.17); details in DRAFTING.md.

## D39. Petition drafting, phase 1 (2026-10-30)
User request: drafting is the next feature; samples are the key; the system must learn each
lawyer's style (length, plain or ornate) over time and be capable from the start. Research:
law-firm sample sites are the firms' copyrighted work (FSEK art. 31 frees statutes and court
decisions, not petitions), so they are not copied; the one Hugging Face "petitions" set has no
license and holds Constitutional Court decision texts. Design in docs/DRAFTING.md: required
contents come from the statutes that set them (HMK 119, 129, 342 ...), outlines per type in
playbooks/tr/petitions, style from the lawyer's own petitions measured by code (length,
sentence length, register from a formal-word lexicon, headings, closing formula), moved by
four buttons (shorter, longer, plainer, more formal) and by the lawyer's saved edits, plus
rules the lawyer writes. Built as phase 1 (tables style_samples, style_profiles, drafts;
routes under /drafting and /drafts; panels "Örnek dilekçelerim" and the draft editor). One
end-to-end draft and one adjustment checked ($0.10, results in DRAFTING.md).

## D38. The writer applies the tier that fits the facts and does not correct itself (2026-10-30)
A labour answer wrote "the notice period for 4 years of service is 6 weeks (1.5-3 years) not,
over 3 years it is 8 weeks": the tier was chosen while writing and corrected mid-sentence
(the writer streams and cannot revise); earlier runs also had a route next to a sentence
calling that route's condition insufficient. The write prompt now asks to determine, before
writing, which tier or case of a graded rule fits the facts (or give the options with their
conditions when a fact is unknown), not to correct a statement within the sentence, and not to
contradict a recommended route elsewhere. One run each ($0.22): is-1 stated 8 weeks directly
(4/5; the missing point is the one-year minimum for severance pay), kira-3 gave the 10/30-day
periods by the kind of premises (5/6). Two more runs each ($0.39): no answer corrected itself
or contradicted its routes; is-1 stated 8 weeks for 4 years each time and once noted that the
code-of-obligations periods do not apply to a worker under the labour law (3/5 and 4/5:
missing the one-year minimum, once the written-notice point); kira-3 5/6 both times (a
different missing point each time).

## D37. Issue sources from the issue's own results; statutes are current; stricter grader (2026-10-30)
Full golden run after D35-D36: 8/17 passed, 52/60 points (50 before), median 21.5 s, $0.84;
tasinmaz-1 2/2 and kira-1 3/3, but is-1 lost severance pay and is-2 found no decision.
- Severance pay: law 1475 art. 14 is first in its issue's search but judged 0.53; the issue's
  guaranteed source was the best-judged of all its results, the notice-period article another
  issue had already brought. The source is now the best-judged of the issue's own top 3
  results (at least 0.3), else the best of all its results.
- The writer then cited art. 14 but called its validity into question (an old law). The write
  prompt now states that statute documents are the current texts in force from the official
  database, and an old law can have articles still in force; the next answer stated the
  30 days' pay per year from art. 14.
- is-2's miss was not reproduced (3 and 4 decisions in two later runs); in the full run, three
  answers searched live decisions at once through the one-request-per-second queue.
- Grader: a reply with too few verdicts was padded with "not covered" (a good answer scored
  0/5), and a bare list of booleans missed points stated in so many words. The grader now
  returns, per point, the answer's sentence that states it (a point without one is not
  covered) and is asked again when the count is wrong. Regrading the full run: 51/60 (52 with
  the old grader); stricter on icra-2 and kira-3, fairer on is-1.
Cost of these checks about $0.40.

## D36. Neighbours of the best kept articles are judged too (2026-10-30)
Follows D35's partition miss: a code keeps related rules side by side, and the answering
article can use other words than the lawyer. After selection, the articles within 3 of the
4 best kept ones (same law, not yet judged) are screened with the same instruction; up to 3
judged at least 0.6 are added. tasinmaz-1 went from 0/2 to 2/2 (civil code art. 699 found
next to art. 696); icra-0 (3/4) and kira-1 (2/3) unchanged; $0.14 for the three. Adds about
20 decision-model calls per question (well under $0.01).

## D35. Precedent requests find decisions; document keys become citations (2026-10-30)
Golden set extended with a labour-law case (is-1) and its follow-up "is there a precedent of
the Court of Cassation on this?" with the earlier turns (is-2; the runner now passes an item's
"history"). Run of 17 questions: 8 passed, 50/60 points, median 26 s, $0.85; every answer cited
its sources (D32 holds) and is-1 covered severance pay from law 1475 (5/5). is-2 got no
decision although live search returned six on point. Causes and changes:
- followed references and decision passages were judged against the follow-up as written,
  which does not state the case; they are now judged against the question with its legal
  characterisation, as statute candidates already were;
- decisions were judged by whether they "answer the sub-question" (0.55-0.64 for decisions on
  point); when the lawyer asks for decisions they are judged as precedents for one of the
  case's issues (0.90-0.94 on point, 0.15 for a procedure-only passage).
is-2 then cited four decisions and covered both points ($0.08). The answer named documents by
their internal keys ("the closest are E10 and E12"); keys written into the prose now become
citation markers, shown as chips.
Partition (tasinmaz-1, 0/2) was diagnosed, not fixed: the question and the issue phrases use
practice words ("aynen taksim", "ortaklığın giderilmesi"), the civil code says "paylaşma" and
"aynen bölünme"; TMK 699 ranks 61st in the text search (rank has no term rarity weighting) and
outside the vector results. A rarity-weighted rank moved it to 19th (12 results are read per
search) and took 1 s per search, so it was not adopted. A prompt asking the understanding step to always name the governing
article was tried once ($0.06): it named TMK 690 instead of 699 (the cheapest model does not
recall the number), coverage rose to 1/2 only through decisions; reverted. A fix has to come
from retrieval (vocabulary of the code, or reading the paylı mülkiyet articles as a group),
not from the model's memory.

## D34. Unanswered questions are dropped and can be asked again; tests clean up (2026-10-30)
A question whose answer failed, or was being answered when the API restarted (runs live in
process memory, D25; the development server restarts on every code change), stayed in the
chat with nothing under it, and the next question sent it to the model as a second user turn
in a row. Now asking in a chat first removes a last question without an answer (no run is
active then, so it can never be answered), and the chat shows "this question could not be
answered" with an "ask again" button under such a question and under a failed answer. The
chat API tests delete the users they create (chats go with them by cascade); 260 users left
by earlier runs are still in the development database.

## D33. A request for decisions always searches decisions (2026-10-30)
User test: "is there a precedent of the Court of Cassation on this?" after a labour-law answer
was understood as a search task, but no decision was searched (the case-law step ran only for
consultations or when the understanding step wrote a case-law query, and it left the query
empty), so the answer said no decision was among the sources. Now a search task always
searches decisions (query: the case-law query, else the legal characterisation), reads up to
6 live decisions and keeps up to 5 screened passages (2 otherwise); the understanding prompt
must fill the case-law query whenever decisions or precedents are asked for. Not yet verified
with a new answer (day's spend over budget).

## D32. Answers must cite; severance pay law indexed; chat cost moved (2026-10-30)
User report: a labour-law answer showed no citation chips and no sources in the margin, said
"no provision on severance pay was found", and the sidebar titles were cut short. Causes: the
Sonnet writer returned one uncited block (the prompt said source references "are added
automatically", which can read as "do not cite"); severance pay is still governed by art. 14
of the 1971 labour law no. 1475, which was not indexed; the per-chat cost column took the
titles' width. Changes: the prompt asks for a citation in every paragraph, and an answer
citing nothing is written once more with a note (not for OpenAI-compatible providers, which
have no citations API); law 1475 added to CORE_LAWS and synced (6 articles); the per-chat cost
left the sidebar and is shown once at the end of the open chat. Not yet verified with a new
answer: the day's spend had passed the $2 budget.

## D31. Costs are shown: per answer, per chat, per day (2026-10-30)
User request: see what each kind of work costs. Each answer shows its LLM spend next to its
duration (answer plus opened detail, as stored in messages.meta); each chat in the sidebar
shows its total (GET /chats returns cost_usd); the sidebar footer shows today's answers,
average time and total spend (GET /chats/stats/today returns cost_usd). Costs include routing,
the title and every pipeline step of the answer; evaluation runs outside the app are not
included.

## D30. Clarifying answers are chosen, then sent together; a stopped question is removed (2026-10-30)
User feedback: choosing one clarifying option sent it at once and started a new answer,
before the lawyer could answer (or decide not to answer) the other questions; stopping that
answer left the unanswered question in the chat. Options are now toggled per question and sent
together with "Seçimlerimi gönder" (any number, none required). When an answer is stopped, its
question is deleted on the server and the chat reloads; the cancel call waits up to 5 s for
the run to finish that cleanup.

## D29. Answers shaped by the lawyer's questions; procedure; clarifying options (2026-10-30)
Compared with ChatGPT and a Turkish legal AI tool on a used-car defect case (golden ayip-1) and
its follow-up "at which stage should I do what?" (ayip-2): ours was legally sound but forced
every answer into the routes template, said "mediation was not found in the sources" where the
consumer law requires it, ignored the inspection firm named in the facts, lacked procedure
(evidence preservation, pre-suit steps, competent court), and answered the follow-up by
repeating the first answer (the router took it for a reformat request, which also crashed).
Changes: the understanding step returns the lawyer's own questions, the answer shape (single,
answers, routes, plan, draft, list), procedural and third-party issues, and up to 3
clarifying questions with options; the writer builds the answer on the lawyer's questions,
has a stage-by-stage plan shape, may use tables, and must not turn "not found in the sources"
into "not required"; the router counts "what to do next / steps / procedure" as a follow-up;
the UI renders tables (remark-gfm), groups citation chips at the end of each paragraph, and
shows the clarifying questions as one-click answers on the latest reply; zero-width characters
are stripped. Measured in the chat: the first answer follows the three questions with
"Hayır." under "does the seller's ignorance remove liability"; the follow-up is a 7-stage plan
with evidence preservation (HMK 400, 402), notice, consumer mediation (TKHK 73/A), the
consumer court and a table of legal bases ($0.075 and $0.088, about 40 s each). Still missing:
the general civil court for private sales, the inspection firm's liability, alternative
(terditli) claims.

## D28. Chapter context, decision dates, every result judged, Sonnet writes (2026-10-30)
Remaining errors after D27 had general causes:
- Regime confusion: the answer applied obligations law art. 362 (usufructuary lease, 60 days)
  to a residential lease. The index kept only an article's own heading. Each article now
  stores its section path (books, parts, chapters, sub-chapters and "bap" divisions, e.g.
  "Kira Sözleşmesi > Ürün Kirası"), parsed at sync (the service's text uses CRLF line
  endings, normalised first; migration c3d9a7e1f2b4); the path is shown to the screening
  model and at the top of every article the writer reads, and the prompt says to tell
  regimes apart by it.
- Outdated law from old decisions: the writer is told that decisions apply the law of their
  date and not to present a repealed rule as current.
- The enforcement route kept disappearing: the understanding step now sees the indexed laws
  (it had named the enforcement article under the civil procedure law's number) and must list
  every alternative route of a consultation as its own issue; every result of every search is
  judged (cutting the fused list lost the article whenever only one search ranked it), and an
  issue's guaranteed source is its best-judged result. Two research runs gave the same sources.
- Writing moved to claude-sonnet-5-5 (role "write"), with the user's approval as an exception
  to the cheapest-model rule: Haiku's answers contradicted their own routes. Other steps stay on
  Haiku and the decision model.
Measured on all 13 golden questions: 37/42 points, 7/13 fully passed (Haiku writer: 4/13),
eviction consultation 5/6 with both routes and the enforcement steps, median 21 s, about $0.044
per question ($0.57 for the set, $0.51 of it the write step).

## D27. Consultation answers as procedures; every issue keeps a source (2026-10-30)
Lawyer feedback: ChatGPT's answer to the eviction case was better. Its strengths: the ruling
and the deciding fact first, each route as numbered procedural steps with periods, the
route's precondition and advantage, typical mistakes, how to proceed, conclusion, critical
question, list of provisions. Ours lacked the enforcement route entirely in one run. Changes:
the consultation structure in prompts/tr/write.md now asks for exactly that; research keeps,
in order, the articles judged to answer, the best result of every issue (so a route is not
left without a source), the named articles unless judged unrelated (a named article can carry
a wrong law number), then the rest; the lettered articles continuing a procedure are added
(269 -> 269/a, 269/b ...); the write step may use 8,000 tokens (4,000 cut an answer off).
Measured on kira-3: enforcement route complete, structure as expected, 4/6 points, 50 s,
$0.014. Two legal errors remain (STATUS 12-13).

## D26. Understand, research, write: one answer written as a whole (2026-10-30)
The decompose -> one-sentence sub-answers -> gists pipeline could only put facts side by side:
it failed case consultations (eviction example, STATUS issue 10) and wrote nothing like an
expert's answer (provocation example, issue 11). The chat now answers in three steps
(agent/pipeline.py): a cheap call understands the message (task: lookup, consultation,
drafting, search, review; legal characterisation; issues with statute-language phrases;
articles known to apply; case-law query; missing facts); research searches the question and
every issue, reads the named articles, keeps what the decision model judges a complete answer
needs (rule, route, precondition, time limit, competent court), follows references and adds
screened case law; one streamed call writes the whole answer from all sources in the task's
structure (prompts/tr/write.md) with the Citations API. Sentences stating quantities are
checked (numbers present in a source; the decision model judging them supported in their
paragraph against all sources, flagging only clear contradictions: at a stricter threshold
correct sentences in long paragraphs were flagged too). Also: Anthropic requests time out after
120 s (the SDK default of 10 minutes, retried, let a stalled request hold an evaluation for
half an hour) and live case-law search has a 15 s budget.
Measured on all 13 golden questions (Haiku, 2026-10-30): 37/42 points, eviction consultation
6/6 (was about 1/6), provocation 4/5, median 16 s (was 22 s), $0.05 for the set. The earlier
pipeline is kept in agent/answer.py for comparison.

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
