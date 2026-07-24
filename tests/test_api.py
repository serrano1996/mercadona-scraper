from unittest.mock import MagicMock

import pytest
import requests
from fastapi.testclient import TestClient

from mercadona_scraper.api.main import app
from mercadona_scraper.exceptions import APISchemaError, WarehouseError

VALID_PARAMS = {"postal_code": "28001", "term": "leche"}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_scraper(monkeypatch):
    mock_cls = MagicMock()
    monkeypatch.setattr("mercadona_scraper.api.routes.MercadonaScraper", mock_cls)
    return mock_cls


def test_get_products_success_returns_scraper_result(client, mock_scraper):
    mock_scraper.return_value.run.return_value.to_dict.return_value = {
        "search": {"postal_code": "28001", "term": "leche", "total_results": 1},
        "products": [{"id": "1", "name": "Leche entera"}],
    }

    resp = client.get("/api/v1/products", params=VALID_PARAMS)

    assert resp.status_code == 200
    assert resp.json()["products"][0]["name"] == "Leche entera"


def test_get_products_passes_query_params_to_scraper(client, mock_scraper):
    mock_scraper.return_value.run.return_value.to_dict.return_value = {}

    client.get("/api/v1/products", params={**VALID_PARAMS, "strategy": "playwright"})

    mock_scraper.assert_called_once_with(
        postal_code="28001", term="leche", strategy="playwright"
    )


def test_get_products_defaults_strategy_to_api(client, mock_scraper):
    mock_scraper.return_value.run.return_value.to_dict.return_value = {}

    client.get("/api/v1/products", params=VALID_PARAMS)

    assert mock_scraper.call_args.kwargs["strategy"] == "api"


def test_get_products_invalid_postal_code_returns_422(client):
    resp = client.get("/api/v1/products", params={"postal_code": "abc", "term": "leche"})
    assert resp.status_code == 422


def test_get_products_short_postal_code_returns_422(client):
    resp = client.get("/api/v1/products", params={"postal_code": "2800", "term": "leche"})
    assert resp.status_code == 422


def test_get_products_missing_term_returns_422(client):
    resp = client.get("/api/v1/products", params={"postal_code": "28001"})
    assert resp.status_code == 422


def test_get_products_invalid_strategy_returns_422(client):
    resp = client.get(
        "/api/v1/products", params={**VALID_PARAMS, "strategy": "not-a-strategy"}
    )
    assert resp.status_code == 422


def test_get_products_warehouse_error_returns_400(client, mock_scraper):
    mock_scraper.return_value.run.side_effect = WarehouseError("CP no reconocido")

    resp = client.get("/api/v1/products", params=VALID_PARAMS)

    assert resp.status_code == 400
    assert resp.json()["detail"] == "CP no reconocido"


def test_get_products_api_schema_error_returns_502(client, mock_scraper):
    mock_scraper.return_value.run.side_effect = APISchemaError("La API cambió de estructura")

    resp = client.get("/api/v1/products", params=VALID_PARAMS)

    assert resp.status_code == 502
    assert resp.json()["detail"] == "La API cambió de estructura"


def test_get_products_connection_error_returns_503_without_leaking_details(
    client, mock_scraper
):
    mock_scraper.return_value.run.side_effect = requests.ConnectionError(
        "No se pudo conectar a http://internal-secret-host/api tras 3 intentos"
    )

    resp = client.get("/api/v1/products", params=VALID_PARAMS)

    assert resp.status_code == 503
    assert "internal-secret-host" not in resp.json()["detail"]


def test_get_products_unexpected_error_does_not_leak_message(mock_scraper):
    mock_scraper.return_value.run.side_effect = RuntimeError("secret internal detail")
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/v1/products", params=VALID_PARAMS)

    assert resp.status_code == 500
    assert "secret internal detail" not in resp.text
