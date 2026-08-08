# Orders service image.
#
# Built from the repository root so it can copy the shared package alongside its
# own code:
#
#   docker build -f services/orders/Dockerfile -t orders-service .
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
COPY services/orders/app/ ./app/
COPY services/orders/alembic/ ./alembic/
COPY services/orders/alembic.ini ./alembic.ini

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
