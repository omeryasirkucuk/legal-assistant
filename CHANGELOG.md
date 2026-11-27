# Changelog

## 0.9.3 · 2026-11-27

- Restore the compact citation verification notice in the Folonto chat. Its details retain readable statement formatting and open numbered sources directly.


## 0.9.2 · 2026-11-27

- Load the local petition style model only for requests classified as drafting.
- Reply directly to standalone greetings, thanks and capability questions.
- Return the text and source of an explicitly requested indexed article directly from the local index.
- Run legislation and case-law searches concurrently. Use cached embedding model files and move query encoding off the server event loop.
- Save completed answers without waiting for a slow title. Preserve the first answer with citation warnings if the citation retry stalls.
- Bound chat generation to 60 seconds, or 105 seconds in deep research, and report timeouts with a retry action. Record time to first text and total generation time.

## 0.9.1 · 2026-11-27

- Center the chat welcome screen, conversation and message box in the workspace.
- Keep the chat input focus highlight on the rounded message box.

## 0.9.0 · 2026-11-27

- Keep admin invitation codes in the admin panel with active, used and expired states. New codes expire after 24 hours and remain bound to the specified email address.
- Let administrators set daily and monthly USD limits per user. Show current-month spend and apply limits to chat and drafting.
- Populate admin model settings with the effective provider and role models, including the answer writer. Show the assigned model for each response preset in chat.
- Add the Folonto Legal name and monogram to navigation, the chat landing view, sign-in and the favicon.

## 0.8.1 · 2026-11-27

- Adapt sign-in, navigation, chat, calendar, case files, document editing and account panels to phones and tablets. Keep wide answers and file menus within the viewport.
- Make the administrator invitation form usable on narrow screens.

## 0.8.0 · 2026-11-27

- Generate unique, single-use registration codes tied to the recipient's email address from the admin panel.
- Reserve the environment's bootstrap code for the first administrator on a fresh database.

## 0.7.0 · 2026-11-27

- Create, edit, complete and delete hearings, meetings, personal reminders and other events from the calendar. Link entries to cases when needed and manage them from the case page.
- Add case deadlines directly from the calendar, with an entered date or the existing notice calculator. Browse the month, selected day or grouped list, and filter by type, case and completion status.
- Show scheduled in-app reminders across signed-in screens, and export individual events and their active alarms as iCalendar files.
- Include event types, dates and times in calendar answers in chat with the current case scope respected.

## 0.6.0 · 2026-11-27

- Added self-service password changes to the account menu for all users. Changing a password signs out other sessions for the same account.

## 0.5.0 · 2026-11-27

- Added an administrator panel for registered accounts, daily and lifetime model spend, and role changes with last-administrator protection.

## 0.4.0 · 2026-11-27

- Added ARM production deployment under `legal.folonto.com` and optional encrypted S3 storage for uploads and exports.

## 0.3.3 · 2026-11-26

- Allow an explicitly chosen OpenRouter answer writer to use a separately configured model when the affordable response budget is too small.

## 0.3.2 · 2026-11-26

- Recover rejected OpenRouter requests with a smaller affordable response budget and use the existing main model when the default writer cannot produce a usable reply. Report unrecoverable provider failures accurately and use a smaller analysis budget for short questions. Return completed calculations with their evidence if the writer is unavailable, and recognize explicit hypothetical severance inputs during an analysis outage. Calculate severance and notice from a stated duration and an explicit date or today scenario.

## 0.3.1 · 2026-11-26

- Verify numeric corrections against their replacement source and rerun the existing approved method when the legal basis and event dates stay the same.

## 0.3.0 · 2026-11-26

- Added an AI calculation workflow in chat that can research an unfamiliar method, bind its inputs and rules to source passages, and run a reproducible calculation.
- Added saved calculation revisions with visible input and result changes, optional formula-based Excel output with its source excerpts, and sourced inline answers and tables.
- Added checked amount replacements in Word copies with access to the original and previous outputs.
- Added optional public-law web discovery for development and preserved local research in protected mode.

## 0.2.0 · 2026-11-26

- Added protected mode with authenticated encryption for document files and a fixed private model connection.
- Kept case research in local indexes in protected mode, with a ranked-source fallback if a screener is unavailable.
- Added a resumable migration for existing files, safer downloads, and a protected server command and recovery runbook.
- Check citations against the stored original passage as well as the excerpt given to the model.
- Report gaps in dated calculation tables without emitting fee or severance estimates for uncovered periods.

## 0.1.2 · 2026-11-26

- Require a matching passage before showing a source chip for a compatible model's citation.
- Show missing citations and uncertain support alongside the answer, with clearer verification labels.

## 0.1.1 · 2026-11-26

- Updated Next.js, the petition editor and affected transitive dependencies to patched versions.
- Added lockfile-based setup, a core statute import command and a research readiness endpoint.
- Made backend tests independent of the downloaded statute corpus.
- Retained recorded model spend after a chat is deleted.
