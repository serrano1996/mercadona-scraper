# mercadona-scraper

Scraper de productos de [tienda.mercadona.es](https://tienda.mercadona.es), dado un código postal y un término de búsqueda.

Resuelve el almacén asociado a un código postal español y busca productos usando, según convenga, la API interna de Mercadona, su índice de Algolia, o automatización de navegador (Playwright) como último recurso. Expone dos interfaces sobre la misma lógica: un CLI y una API REST.

## Instalación

Requiere Python ≥ 3.10.

```bash
pip install -e .[test]
playwright install chromium
```

`-e .[test]` instala el paquete en modo editable junto con las dependencias de test (`pytest`, `pytest-asyncio`, `responses`). Si solo necesitas ejecutar el proyecto, sin correr los tests, `pip install -e .` basta.

## Uso — CLI

```bash
mercadona-scraper --postal-code 28001 --product "leche entera"
```

Si no has instalado el paquete, `cli.py` en la raíz funciona igual sin necesidad de `pip install`:

```bash
python cli.py --postal-code 28001 --product "leche entera"
```

Opciones:

| Flag | Descripción |
|---|---|
| `--postal-code CP` | Código postal español de 5 dígitos (requerido) |
| `--product TERM` | Término de búsqueda (requerido) |
| `--strategy` | `api` (por defecto, ~15s), `playwright` (~30-60s), `auto` (API con fallback a Playwright) |
| `--output FILE` | Guarda el resultado en JSON en vez de imprimir por stdout |
| `--headless` / `--no-headless` | Con `--strategy playwright`, mostrar u ocultar la ventana del navegador |
| `--verbose`, `-v` | Logs de depuración |

Ejemplos:

```bash
mercadona-scraper --postal-code 28001 --product "leche" --strategy playwright
mercadona-scraper --postal-code 08001 --product pan --strategy playwright --no-headless
mercadona-scraper --postal-code 46001 --product yogur --output resultados.json
```

## Uso — API REST

```bash
uvicorn mercadona_scraper.api.main:app --reload
```

Documentación interactiva (Swagger) en `http://127.0.0.1:8000/docs`.

```bash
curl "http://127.0.0.1:8000/api/v1/products?postal_code=28001&term=leche&strategy=api"
```

| Método | Ruta | Parámetros |
|---|---|---|
| `GET` | `/api/v1/products` | `postal_code` (5 dígitos, requerido), `term` (requerido), `strategy` (`api`/`playwright`/`auto`, opcional, por defecto `api`) |

Respuestas de error:

| Código | Causa |
|---|---|
| `422` | Parámetros inválidos (CP mal formado, término vacío, estrategia desconocida) |
| `400` | Código postal válido pero no reconocido por Mercadona |
| `502` | La API o el índice de Algolia de Mercadona cambiaron de estructura |
| `503` | Mercadona no está disponible (red, timeout) |

## Arquitectura

```
mercadona_scraper/
    cli.py              # entrypoint CLI (argparse)
    api/                # entrypoint API REST (FastAPI)
        main.py
        routes.py
    scraper.py           # orquesta resolución de almacén + estrategia de búsqueda
    warehouse.py          # resuelve almacén a partir del código postal (con fallback)
    strategies/           # estrategias de búsqueda intercambiables (Strategy pattern)
        base.py            # SearchStrategy (ABC)
        algolia.py         # vía índice Algolia (rápida, credenciales extraídas del bundle JS)
        api.py              # vía API interna, escaneo de categorías (fallback de Algolia)
        playwright.py       # vía navegador real (último recurso)
    http_client.py        # cliente HTTP con reintentos y backoff exponencial
    formatters.py          # mapea respuestas crudas de Mercadona al modelo de salida
    models.py               # dataclasses de resultado
    exceptions.py            # jerarquía de errores del dominio
    config.py                 # constantes: URLs, headers, mapeo CP → almacén
```

`scraper.py` no busca productos: resuelve el almacén (`warehouse.py`) y delega la búsqueda en una `SearchStrategy`. Con `--strategy api`, intenta primero Algolia y cae a escaneo de categorías si falla; con `auto`, además cae a Playwright si la API no devuelve nada.

## Tests

```bash
pytest
```

130 tests, sin red real ni navegador real — HTTP mockeado con `responses`, Playwright mockeado con `unittest.mock`. Los flujos de automatización de navegador real (`strategies/playwright.py`) no están cubiertos a nivel de integración: necesitarían un Chromium real.
