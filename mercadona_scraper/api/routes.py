import requests
from fastapi import APIRouter, HTTPException, Query

from mercadona_scraper.exceptions import APISchemaError, WarehouseError
from mercadona_scraper.scraper import MercadonaScraper

router = APIRouter(prefix="/api/v1")


@router.get("/products", summary="Buscar productos por código postal y término")
def get_products(
    postal_code: str = Query(..., pattern=r"^\d{5}$", description="CP español de 5 dígitos"),
    term: str = Query(..., min_length=1, description="Término de búsqueda"),
    strategy: str = Query("api", description="Estrategia de scraping: api, playwright o auto"),
):
    try:
        scraper = MercadonaScraper(postal_code=postal_code, term=term, strategy=strategy)
        return scraper.run().to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except WarehouseError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except APISchemaError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except requests.RequestException as e:
        raise HTTPException(
            status_code=503, detail="Mercadona no está disponible en este momento."
        ) from e
