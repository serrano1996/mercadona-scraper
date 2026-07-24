from fastapi import FastAPI

from mercadona_scraper.api.routes import router
from mercadona_scraper.logging_config import configure_logging

configure_logging()

app = FastAPI(
    title="Mercadona Scraper API",
    description="API REST para buscar productos en tienda.mercadona.es",
    version="1.0.0",
)
app.include_router(router)
