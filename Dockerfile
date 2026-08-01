FROM oven/bun:1.3 AS frontend
WORKDIR /app
COPY package.json bun.lock* ./
RUN bun install --frozen-lockfile
COPY frontend ./frontend
COPY vite.config.js ./
RUN bun run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv-cache
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /uvx /bin/
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev
COPY . .
COPY --from=frontend /app/static/dist ./static/dist
RUN chmod -R a+rX /app \
    && chmod 755 scripts scripts/entrypoint.sh \
    && .venv/bin/python manage.py collectstatic --noinput
ENTRYPOINT ["./scripts/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
