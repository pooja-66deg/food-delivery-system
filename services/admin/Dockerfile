# Admin service image.
#
# Built from the repository root so it can copy the shared package alongside its
# own code:
#
#   docker build -f services/admin/Dockerfile -t admin-service .
#
# It copies only the shared package and its own app/ — never another service's.
# That is the point: an image cannot import a sibling even by accident.
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

# Lands as `shared/`, the same name it has in the repository — so an import
# reads identically in a test run and inside the image.
COPY shared/ ./shared/
COPY services/admin/app/ ./app/
COPY services/admin/alembic/ ./alembic/
COPY services/admin/alembic.ini ./alembic.ini

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
