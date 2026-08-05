# Contributing Guide

## Development Setup

### Prerequisites
- Python 3.11+
- Docker and Docker Compose
- Git

### Local Setup

1. Clone the repository:
   ```bash
   git clone <repo-url>
   cd food-delivery-system
   ```

2. Copy environment file:
   ```bash
   cp .env.example .env
   ```

3. Start Docker services:
   ```bash
   docker compose -f infra/compose/docker-compose.yml up -d
   ```

4. Install dependencies with [uv](https://docs.astral.sh/uv/):
   ```bash
   uv sync --extra dev --no-install-project
   ```
   Dependencies are declared once in `pyproject.toml` and pinned — including every
   transitive one — in `uv.lock`. Commit `uv.lock` whenever you change a dependency;
   CI installs with `--frozen` and fails rather than re-resolving.

5. Run the application:
   ```bash
   uv run uvicorn src.main:app --reload
   ```

The API will be available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

## Code Style

- Use Black for code formatting
- Use flake8 for linting
- Use mypy for type checking
- Follow PEP 8 conventions

## Testing

Run tests with coverage:
```bash
pytest --cov=src
```

## Project Structure

```
src/
  ├── main.py                 # FastAPI application entry point
  ├── config.py              # Configuration management
  ├── core/                  # Core utilities and shared code
  │   ├── exceptions.py      # Custom exceptions
  │   ├── schemas.py         # Pydantic schemas
  │   └── jwt.py            # JWT utilities
  ├── infrastructure/        # External service integrations
  │   ├── database.py       # SQLAlchemy setup
  │   ├── redis.py          # Redis client
  │   └── kafka.py          # Kafka producer/consumer
  └── modules/              # Business modules
      ├── auth/             # Authentication
      ├── users/            # User management
      ├── restaurants/      # Restaurant management
      ├── cart/             # Shopping cart
      ├── orders/           # Order management
      ├── payments/         # Payment processing
      ├── delivery/         # Delivery management
      └── notifications/    # Notifications
```

## Branching Strategy

- `main` - Production-ready code
- `develop` - Integration branch
- `feature/*` - Feature branches
- `fix/*` - Bug fix branches
- `init/*` - Initial setup branches

## Commit Messages

Use conventional commit format:
```
<type>(<scope>): <subject>

<body>
<footer>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`
