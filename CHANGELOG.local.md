# Local changelog

## 0.1.2 · 2026-11-26

- Compatible writers now emit a contiguous passage for each citation. The API strips provider tags from the live stream.
- Citation checks use the exact source excerpt sent to the writer and assess cited claims against the selected sources.
- Existing message content and evidence stay readable with a legacy verification label.

## 0.1.1 · 2026-11-26

- Run `make setup` to install the web and API lockfiles and `make migrate` to backfill recorded chat spend.
- Run `make corpus` to load or refresh the required core laws. Check `GET /ready` for missing laws.
- The Tiptap 3 upgrade preserves existing document JSON, formatting controls and citation nodes.
- ESLint now skips the generated `.next-prod` directory.
