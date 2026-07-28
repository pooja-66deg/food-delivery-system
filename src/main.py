"""Main FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from src.config import settings
from src.infrastructure.database import engine
from src.infrastructure.redis import init_redis, close_redis
from src.infrastructure.kafka import init_kafka, close_kafka
from src.core.exceptions import AppException
from src.modules.users.router import auth_router, users_router
from src.modules.restaurants.router import router as restaurants_router
from src.modules.cart.router import router as cart_router
from src.modules.orders.router import router as orders_router
from src.modules.payments.router import router as payments_router

# Ensure all domain models are imported so create_all/migrations see them.
import src.modules.users.models  # noqa: F401
import src.modules.restaurants.models  # noqa: F401
import src.modules.orders.models  # noqa: F401
import src.modules.payments.models  # noqa: F401

# Configure logging
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context for startup and shutdown events."""
    # Startup
    # Schema is managed by Alembic migrations (`alembic upgrade head`), run as a
    # deploy/start step — not created at runtime. See README "Database migrations".
    logger.info("Starting up...")
    await init_redis()
    init_kafka()
    logger.info("Application started successfully")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await close_redis()
    close_kafka()
    await engine.dispose()
    logger.info("Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    lifespan=lifespan,
)

# CORS middleware — explicit origin allowlist (never "*" together with credentials).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(AppException)
async def app_exception_handler(request, exc: AppException):
    """Handle application exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "errors": exc.details,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """Handle validation errors."""
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            # jsonable_encoder sanitizes non-serializable bits (e.g. a ctx
            # ValueError from a custom field validator) that plain json can't.
            "errors": jsonable_encoder(exc.errors()),
        },
    )


# Routers
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(restaurants_router)
app.include_router(cart_router)
app.include_router(orders_router)
app.include_router(payments_router)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "environment": settings.environment}


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to Food Delivery Platform",
        "version": settings.api_version,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
