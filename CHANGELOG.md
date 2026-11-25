# Changelog

## 0.3.0 · 2026-11-26

- Added an AI calculation workflow in chat that can research an unfamiliar method, bind its inputs and rules to source passages, and run a reproducible calculation.
- Added saved calculation revisions with visible input and result changes, optional formula-based Excel output, and sourced inline answers and tables.
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
