# Changelog

## 0.4.0 · 2026-11-27

- Handle standalone greetings, acknowledgments and capability questions directly. Classify topic switches and preserve the last substantive answer for corrections and reformats. Keep the latest message separate from earlier facts when extracting updated calculation inputs. Present citation checks more compactly.
- Check cited claims against the matched quotations and the facts supplied by the user. Open the cited source directly from a warning.


## 0.3.6 · 2026-11-26

- Reduce the analysis response grammar to restore chat answers when a provider rejects a complex schema. If a provider rejects grammar compilation, retry with schema-guided JSON and validate it in the backend.
- Preserve current-period estimates when a request refers to past employment without identifying a different date.

## 0.3.5 · 2026-11-26

- Format amount-focused answers around the result, the assumptions that affect it and the relevant gross and net figures. Retain the original question when writing a follow-up.
- Narrow default research for amount questions while preserving legal sources, explicitly requested precedent and deep research.
- Check formatted Turkish amounts as whole values. Keep paired references and citation-only fragments from generating false warnings.
- Include the verified combined gross amount in severance and notice evidence when both payments are due.

## 0.3.4 · 2026-11-26

- Pass model-extracted service duration and gross pay to the severance calculator even when employment dates are incomplete. Explain date assumptions and cite the applicable official ceiling period.
- Give calculation results and their source documents priority in answers. Keep unsupported periods from producing an uncapped severance result.
- Batch citation support checks for claims using the same sources and give the verifier the surrounding paragraph for each claim.
- Use model-based input extraction instead of matching question phrases during provider outages. Preserve completed calculations if the writer is unavailable.

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
