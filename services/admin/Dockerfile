# Admin service image.
#
# Built from the repository root so it can copy the shared package alongside its
# own code:
#
#   docker build -f services/admin/Dockerfile -t admin-service .
#
# It copies only src/shared and its own app/ — specifically not src/modules or
# src/main.py. That is the point: this image cannot import the monolith even by
# accident, which is what stops the two drifting back into one deployable.
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /usr/local/bin/uv

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Dependencies from the same lock the platform uses, so the service and the
# monolith cannot end up on different versions of a library that has to agree
# across a Kafka topic.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1

# The shared package lands as `shared/`, not `src/shared/` — hence the relative
# imports inside it.
COPY src/shared/ ./shared/
COPY services/admin/app/ ./app/
COPY services/admin/alembic/ ./alembic/
COPY services/admin/alembic.ini ./alembic.ini

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
