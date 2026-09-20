import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.api.v1.products import router as products_router
from app.core.config import Settings
from app.core.logging_config import configure_logging
from app.core.security import verify_api_key
from app.middleware.request_logging import RequestLoggingMiddleware
from app.scrapers.http_client_factory import build_mercadona_http_client
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    configure_logging(settings.LOG_LEVEL)
    http_client = build_mercadona_http_client()
    redis_client = Redis.from_url(settings.REDIS_URL)

    app.state.settings = settings
    app.state.cache_repository = CacheRepository(redis_client)
    app.state.mercadona_client = MercadonaClient(http_client, settings)

    yield

    await http_client.aclose()
    await redis_client.aclose()


app = FastAPI(lifespan=lifespan)
app.add_middleware(RequestLoggingMiddleware)
app.include_router(products_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error processing %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
