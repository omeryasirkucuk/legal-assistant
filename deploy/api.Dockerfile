FROM ghcr.io/astral-sh/uv:0.11.13 AS uv
FROM python:3.12-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app/services/api
ENV UV_LINK_MODE=copy PATH="/app/services/api/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY services/api/pyproject.toml services/api/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY services/api/ ./
RUN mkdir -p /app/var/model-cache \
    && chown -R 10001:10001 /app/var
COPY locales /app/locales
COPY prompts /app/prompts
COPY playbooks /app/playbooks
# Keep the package at its source location so its repo-root data paths resolve.
ENV PYTHONPATH=/app/services/api HF_HOME=/app/var/model-cache
USER 10001:10001
CMD ["uvicorn", "legal_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
