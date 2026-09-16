# Constitución del proyecto

1. **Stack fijo:** Python 3.11+, FastAPI, Pydantic v2, httpx async, Redis cache. No añadir libs fuera de esto sin discutirlo.
2. **Scraping:** solo endpoints JSON internos de Mercadona. Prohibido Playwright/Selenium/BeautifulSoup.
3. **Async obligatorio:** todo endpoint y llamada externa usa `async def` + `httpx.AsyncClient`. Sync bloqueante = rechazo.
4. **Tipado estricto:** type hints explícitos en toda función pública. `Any` prohibido en anotaciones.
5. **Validación:** toda entrada/salida por la API pasa por schema Pydantic v2. Sin validar = bug.
6. **Cache:** llamadas repetidas a Mercadona pasan por Redis antes de golpear la red.
7. **Tests:** `pytest` obligatorio para cada endpoint y cada scraper nuevo. PR sin test = no mergea.
8. **Lint:** `ruff check . && ruff format .` limpio antes de cualquier commit.
9. **Docs vivas:** Swagger (`/docs`) debe reflejar los schemas reales, sin endpoints huérfanos.
10. **Idioma:** código/docstrings/commits en inglés; docs técnicas en español.
11. **Límite de responsabilidad:** el scraper no persiste datos propios más allá del cache — no es la fuente de verdad, es un proxy inteligente sobre Mercadona.
