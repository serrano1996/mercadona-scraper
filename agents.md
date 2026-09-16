# AGENTS.md

## Proyecto

API REST asíncrona construida con Python y FastAPI que extrae, procesa y sirve información de productos de Mercadona. Consulta las APIs internas/endpoints de Mercadona (usando `httpx`), valida y transforma los datos con Pydantic y cachea los resultados con Redis para minimizar peticiones innecesarias.

## Comandos

- **Ejecutar:** `uvicorn app.main:app --reload`
- **Tests:** `pytest`
- **Lint/formato:** `ruff check . && ruff format .`

## Estilo y convenciones

- **Lenguaje:** Python 3.11+ con *type hints* explícitos.
- **Idioma:** Código, docstrings y mensajes de commit en inglés; documentación técnica en español.
- **Nombres:**
  - `snake_case` para funciones, variables, nombres de archivos y módulos.
  - `PascalCase` para clases y modelos de Pydantic.
  - `UPPER_SNAKE_CASE` para constantes y variables de entorno.
- **Estructura:** Modular orientada a FastAPI (`app/api/`, `app/services/`, `app/models/`, `app/scrapers/`).

## Reglas

- Lee `docs/constitution.md` and la spec activa antes de tocar código.
- **Asincronía obligatoria:** Todos los endpoints y llamadas externas deben ser asíncronas (`async def` y `httpx.AsyncClient`).
- **Dependencias:** No añadas librerías como Playwright, Selenium o BeautifulSoup sin consultar; prioriza el consumo de los endpoints JSON internos de Mercadona.
- **Validación:** Toda entrada y salida de datos debe validarse usando schemas de **Pydantic v2**. Prohibido usar `Any` en las anotaciones de tipos.

## Al terminar cualquier tarea

- Ejecuta `ruff check .` y `pytest` para garantizar que el código cumple con el estándar y pasa las pruebas de integración.
- Comprueba que la documentación automática de Swagger (`/docs`) cargue correctamente y muestre los esquemas actualizados.