# API image. Dependencies come from pyproject.toml + uv.lock, which is now the
# only place they are declared — there is no requirements.txt to drift from it.
FROM python:3.11-slim

# Pinned, not :latest — an image rebuild must not change the installer itself.
COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /usr/local/bin/uv

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Dependencies in their own layer, before the source, so editing application code
# does not reinstall them.
#
# --frozen              install exactly what uv.lock says and fail rather than
#                       re-resolve, so the image cannot drift from the committed lock.
# --no-install-project  install the dependencies but not the app itself. The app is
#                       imported as `src.main:app` from /app below — the same way
#                       pytest and alembic reach it. Installing this src-layout
#                       package would instead expose `core`, `modules` and `main` as
#                       top-level names and break every `src.` import.
# --no-dev              belt and braces; dev tooling is an opt-in extra, so it is
#                       already excluded.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# uv installs into a project virtualenv. Put it first on PATH so `uvicorn` and
# `alembic` resolve to it with no activation step.
ENV PATH="/app/.venv/bin:$PATH"

COPY . .

# Honor $PORT (Cloud Run injects it, default 8080); falls back to 8000 locally.
# docker-compose overrides this command with its own --reload invocation.
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
