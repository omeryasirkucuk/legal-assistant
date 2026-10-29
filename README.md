# Legal Assistant (working name)

A web assistant for Turkish lawyers that answers questions, searches case law and legislation,
and drafts or edits petitions. Every statute article and court decision it cites is retrieved
from an official or public source and rendered by the backend, never written from model memory.

## Layout

| Path | Purpose |
|---|---|
| `apps/web` | Next.js user interface |
| `services/api` | FastAPI backend (`legal_api` package) |
| `prompts/tr`, `playbooks/tr`, `locales/tr` | Turkish-language content (LLM instructions, case checklists, UI strings) |
| `eval/golden` | Evaluation question set |

## Local development

Requirements: Docker, [uv](https://docs.astral.sh/uv/), Node.js 20+.

```bash
cp .env.example .env      # add OPENROUTER_API_KEY
make api                  # starts Postgres (pgvector), runs migrations, serves http://localhost:8000
make web                  # serves http://localhost:3000
make test                 # backend tests
```

See `NOTICE` for third-party data and code attributions.
