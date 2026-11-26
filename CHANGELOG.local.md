# Local changelog

## 0.3.5 · 2026-11-26

- Restart the API after updating the backend and prompts. No database migration is required.
- Run `uv run --locked pytest tests/test_severance.py tests/test_write_clean.py tests/test_screen.py` from `services/api` to reproduce the amount answer, citation checks and focused research with mocked model responses.

## 0.3.4 · 2026-11-26

- The backend and model prompts changed. Restart the API after updating. This release requires no database migration.
- The built-in severance table covers 2022–2026. Update its coverage from the official publication when the next period is announced.
- Run `uv run --locked pytest tests/test_severance.py tests/test_write_clean.py` from `services/api` to check the calculation and citation batching with model calls mocked.

## 0.3.3 · 2026-11-26

- Set the writer and optional credit-budget fallback in `.env` with `WRITE_ROUTE` and `WRITE_FALLBACK_ROUTE`. Restart the API after changing either setting.

## 0.3.2 · 2026-11-26

- No database migration is required. Restart the API to pick up the response-budget recovery and compact-question handling. Test a hypothetical dismissal with a stated tenure and gross pay, including when model analysis or writing is unavailable.

## 0.3.1 · 2026-11-26

- Check input-only revisions by replacing a verified amount in chat and confirming that the original rule and the previous result remain viewable. No database migration is needed.

## 0.3.0 · 2026-11-26

- Refresh both installations with `make setup`. Calculation revisions use existing chat and file tables.
- Continue refreshing the local corpus for case work. Development deployments can set `BRAVE_SEARCH_API_KEY` to discover official public sources.
- For a smoke test, calculate from a readable document, open its evidence, request a different output format, and add a replacement document to verify the new revision. The workbook can be recalculated in a compatible spreadsheet application.

## 0.2.0 · 2026-11-26

- Run `make migrate` before deploying. Stop API writes and run `uv run --locked python -m legal_api.files.encrypt` from `services/api` with the document key configured to seal existing files.
- Configure a reviewed private model endpoint, HTTPS, encrypted Postgres storage and an encrypted backup with tested recovery before using protected mode with client records.
- Use `make api-protected` after migration to start without logging request URLs.
- Keep the document key, the server secret and the backup recovery key in separate operator-controlled storage.
- Internal retrieval notes cannot generate a verified source chip.
- Interest stops at the last verified table date. Advance the coverage when publishing verified rate updates.

## 0.1.2 · 2026-11-26

- Compatible writers now emit a contiguous passage for each citation. The API strips provider tags from the live stream.
- Citation checks use the exact source excerpt sent to the writer and assess cited claims against the selected sources.
- Existing message content and evidence stay readable with a legacy verification label.

## 0.1.1 · 2026-11-26

- Run `make setup` to install the web and API lockfiles and `make migrate` to backfill recorded chat spend.
- Run `make corpus` to load or refresh the required core laws. Check `GET /ready` for missing laws.
- The Tiptap 3 upgrade preserves existing document JSON, formatting controls and citation nodes.
- ESLint now skips the generated `.next-prod` directory.
