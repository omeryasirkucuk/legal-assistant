# Local changelog

## Unreleased

- Use `sudo bash deploy/release.sh` on the Oracle VM for production builds. Run it with `--cleanup-only` to verify the serving release and clean up older images without building. Local application setup is unchanged.

## 0.9.10 · 2026-11-27

- Rebuild the API and web images. The API image installs DejaVu and renders a Turkish PDF at build time. Existing saved drafts can be downloaded without resubmitting a question.

## 0.9.9 · 2026-11-27

- Restart the API and rebuild the web client. No database migration is required. Test with a split decision and verify that the precedent label follows the majority while the source viewer still shows the complete text. Repeat with a different payment fact and check that it stays outside the direct results.

## 0.9.8 · 2026-11-27

- Restart the API and rebuild the web client. No database migration is required. Verify the configured production model can process a legal prompt and produce a precedent plan before testing the saved chat output. Confirm a previously indexed public decision is available when the live decision source is throttled.

## 0.9.7 · 2026-11-27

- Run `make setup`, restart the API and rebuild the web client. No database migration is required.
- Ask for a petition and a precedent search using a synthetic case. Verify that a different procedural outcome or payment fact is marked as a related decision and that a search with no verified direct match says so explicitly.
- Compare the `research_stages_s` saved in the answer trace with `timings.total_s` and `timings.first_delta_s`. The statute and case-law durations can overlap.

## 0.9.6 · 2026-11-27

- Run `make setup`, restart the API and rebuild the web client. No database migration is required.
- Ask a general legal question such as `Ev sahibim beni evden hangi şartlarda çıkarabilir`. Check streamed text, the saved answer and its citations. A slow citation support check should open a review notice while preserving the answer.

## 0.9.5 · 2026-11-27

- Run `make setup`, restart the API and rebuild the web client. No database migration is required.
- Check a new out-of-scope request, a legal follow-up and a request near midnight Istanbul time. View responses with and without sources at desktop and mobile widths.

## 0.9.4 · 2026-11-27

- Update and restart the API. Test a new and a previously saved `Nasılsın?` turn. This release needs no database migration or web rebuild.

## 0.9.3 · 2026-11-27

- Rebuild and reload the web client. Open citation details at desktop and phone widths and check that a numbered source opens. This release needs only a web rebuild.


## 0.9.2 · 2026-11-27

- Run `make setup`, restart the API and reload the rebuilt web client. No database migration is required.
- Check `timings.first_delta_s` and `timings.total_s` on chat final events to compare response latency. A cold local search uses cached embedding weights when available. Direct replies and indexed article lookups do not load the embedding model.

## 0.9.1 · 2026-11-27

- Rebuild the web client and check chat alignment on desktop and mobile. Click or tab into
  the message box to check its focus border. This update requires no database migration.

## 0.9.0 · 2026-11-27

- Run `make setup` and `make migrate` before restarting the API and rebuilding the web app. The migration adds invite history, account budget overrides and the saved writer model.
- Reissue any unused invitation made before this release. Its original code and creation time were unavailable in storage.
- Keep the same `SECRET_KEY` across restarts to retain access to encrypted invite codes and saved model credentials.

## 0.8.1 · 2026-11-27

- Rebuild the web client for the mobile layout update. Upgrading from 0.8.0 uses the existing database schema.

## 0.8.0 · 2026-11-27

- Run `make setup` and `make migrate` before restarting the API and rebuilding the web client. The migration adds the invitation table.
- For an existing installation, issue new codes under **Yönetim paneli → Yeni kullanıcı daveti**. Clear any leftover `INVITE_CODE` from the environment.

## 0.7.0 · 2026-11-27

- Run `make setup` and `make migrate`, then restart the API and rebuild the web app. The migration adds `calendar_events` and preserves existing case deadlines.
- For Folonto production, migrate with the updated API image before recreating the API and web containers. Follow the [deployment runbook](docs/DEPLOYMENT.md).
- Smoke-test a personal reminder and a case-linked hearing in both calendar views. Verify that an alert becomes visible while signed in, dismissal persists, and rescheduling arms the reminder again.
- Reminders use Europe/Istanbul time. In-app alerts appear when the app is open or reopened. An exported ICS file is a snapshot and the destination calendar handles its alarms.

## 0.6.0 · 2026-11-27

- Run the database migration before starting the updated API. Existing sessions remain valid until the user changes their password or the session expires.

## 0.5.0 · 2026-11-27

- Rebuild the web app and API for the administrator panel. The panel reads the existing model spend ledger and roles. No database migration is required.

## 0.4.0 · 2026-11-27

- Use the Oracle VM Compose runbook to deploy, migrate Postgres and index the core statutes. Configure a private S3 bucket and a separate document key for new production uploads and exports.

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
