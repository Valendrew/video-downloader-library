FROM denoland/deno:2.5.6 AS deno
FROM ghcr.io/astral-sh/uv:0.12.10 AS uv
FROM python:3.11-slim-bookworm

COPY --from=uv /uv /uvx /usr/local/bin/
COPY --from=deno /usr/bin/deno /usr/local/bin/deno
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DENO_NO_UPDATE_CHECK=1
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY demo ./demo
RUN uv sync --locked --extra all --group demo --no-editable \
    && useradd --create-home --uid 10001 demo
USER demo
EXPOSE 10000
CMD ["sh", "-c", "exec /app/.venv/bin/uvicorn demo.server:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --no-access-log"]
