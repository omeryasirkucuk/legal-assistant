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
cp .env.example .env      # configure an LLM provider and its API key
make api                  # starts Postgres (pgvector), runs migrations, serves http://localhost:8000
make web                  # serves http://localhost:3000
make test                 # backend tests
```

The API supports Anthropic and OpenAI-compatible chat-completions providers. Set `SECRET_KEY`
to a random value of at least 32 characters in `.env` so saved provider credentials can be
encrypted. The first account
is the administrator and can configure Open WebUI from **Model settings** in the UI. Set the
Open WebUI base URL ending in `/api` (for example, `http://localhost:8080/api`), an API key, and
the model IDs shown by your instance. The key is encrypted in the database and never returned
by the settings API. Open WebUI's API key must have chat-completions access enabled. Compatible
answers are shown only when they cite a source ID and include an exact quote found in that source.
For headless setup, the equivalent provider, endpoint, key, and model defaults can be set in
`.env`. For metered compatible providers, set the optional input and output price-per-million-token
variables so the per-user budget can account for their usage.

See `NOTICE` for third-party data and code attributions.
