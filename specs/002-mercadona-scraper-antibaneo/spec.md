# Spec 002 — API REST Mercadona Scraper - Medidas antibaneo

## Contexto y objetivo

El scraper (spec 001) golpea a Mercadona/Algolia con un `httpx.AsyncClient()` sin cabeceras propias — sale con el User-Agent por defecto de httpx (`python-httpx/x.x.x`), sin `Accept-Language`/`Referer`/`Origin`, y sin distinguir un `429 Too Many Requests` de cualquier otro 4xx (hoy: no se reintenta, D2 de plan.md 001). Un volumen de tráfico con ese fingerprint, sin jitter en los reintentos, es fácilmente detectable y bloqueable por un sistema anti-bot.

Objetivo: reducir el riesgo de que Mercadona banee o limite al scraper, sin cambiar el stack fijo (constitución #1) ni añadir Playwright/Selenium (constitución #2).

## Usuarios / actores

- **Sistema (MercadonaClient):** aplica las medidas antibaneo en cada petición saliente hacia `tienda.mercadona.es` / `*.algolia.net`.
- **Desarrollador integrador:** consume la API REST (spec 001) sin necesitar saber que estas mitigaciones existen — son invisibles desde fuera, salvo en la latencia ante un 429.

## Historias de usuario

- **H1:** Como responsable de mantener el scraper en producción, quiero que las peticiones salientes parezcan tráfico de un navegador real y absorban limitaciones temporales de Mercadona, para minimizar la probabilidad de que la IP/fingerprint del servicio quede bloqueada.

## Requisitos funcionales (criterios de aceptación en EARS)

- **RF-1:** CUANDO el sistema construya el `httpx.AsyncClient` usado por `MercadonaClient`, EL SISTEMA fijará un `User-Agent` elegido al azar del siguiente pool (nuevo para este proyecto, no reutiliza el de `mercadona-scraper-old/`), una única vez por instancia de cliente (no por petición) — rotar el UA dentro de la misma sesión sería en sí misma una señal de bot más fuerte que usar uno fijo:

  ```python
  USER_AGENTS = [
      # Chrome / Windows
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
      # Chrome / macOS
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
      # Firefox / Windows
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
      # Edge / Windows
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Edg/130.0.0.0 Safari/537.36",
      # Safari / macOS
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.5 Safari/605.1.15",
      # Chrome / Linux
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
  ]
  ```

  El cliente enviará además `Accept-Language: es-ES,es;q=0.9`, `Referer` y `Origin` coherentes con una petición real originada en `https://tienda.mercadona.es/`.
- **RF-2:** SI Mercadona o Algolia responden `429 Too Many Requests` Y quedan intentos disponibles (`attempt < RETRY_MAX_ATTEMPTS`), ENTONCES EL SISTEMA reintentará la petición esperando el tiempo indicado por la cabecera `Retry-After` (soportando los dos formatos del estándar HTTP: segundos o fecha), en vez de tratarlo como un 4xx no reintentable (excepción explícita a la Decisión D2 de plan.md 001, que sigue aplicando sin cambios al resto de 4xx).
- **RF-3:** SI la cabecera `Retry-After` está ausente o no se puede interpretar en ninguno de los dos formatos soportados, ENTONCES EL SISTEMA calculará la espera con el mismo backoff exponencial que ya usa para 5xx/timeout/conexión (D1 de plan.md 001).
- **RF-4:** EL SISTEMA limitará cualquier espera derivada de un `429` (`Retry-After` o backoff) a un máximo de 60s, para no colgar indefinidamente el proceso ante un valor desproporcionado o malicioso del servidor.
- **RF-5:** CUANDO el sistema calcule el tiempo de espera antes de un reintento (por 5xx, timeout, error de conexión o 429), EL SISTEMA añadirá un jitter aleatorio a ese tiempo, para que el patrón de reintentos no sea perfectamente regular y por tanto más difícil de identificar por análisis de tráfico.
- **RF-6:** SI se agotan los intentos con `429` persistente, ENTONCES EL SISTEMA lo tratará igual que un 5xx agotado (`UpstreamUnavailableError` → 502 en la API pública, T13/T15 de spec 001) — el cliente de nuestra API no necesita distinguir si Mercadona devolvió 5xx o 429, en ambos casos "el origen no está disponible ahora mismo".

## Requisitos no funcionales

- **Compatibilidad con RF-3 de spec 001:** el manejo de `429` es una extensión de `MercadonaClient._request_with_retry` (T10), no un mecanismo paralelo — reutiliza `RETRY_MAX_ATTEMPTS`/`RETRY_BASE_DELAY` de `Settings`, no introduce configuración nueva salvo lo estrictamente necesario para el jitter.
- **Asincronía:** toda esta lógica vive en `MercadonaClient`, ya 100% async (constitución #3) — ninguna medida antibaneo puede introducir I/O bloqueante (`time.sleep` prohibido, usar `asyncio.sleep`).
- **Sin Playwright/Selenium:** estas medidas actúan sólo sobre `httpx.AsyncClient` (constitución #2); no se contempla un fallback a navegador real dentro de esta spec.
- **Tipado estricto:** el pool de User-Agents y cualquier configuración nueva usa type hints explícitos, sin `Any` (constitución #4).

## Casos límite

- **`Retry-After` por encima del tope:** se limita a 60s (RF-4), no se espera el valor literal del servidor.
- **`429` en la primera llamada de la cadena (`asset-manifest.json`) vs. en la llamada a Algolia:** el mecanismo es el mismo para las tres llamadas encadenadas de `MercadonaClient` (manifest → bundle → Algolia), ya que todas pasan por `_request_with_retry`.
- **Cliente HTTP inyectado externamente (tests):** el User-Agent aleatorio sólo se fija cuando `MercadonaClient`/la app construye su propio `httpx.AsyncClient` en `main.py`; los tests que inyectan su propio cliente (`httpx.AsyncClient()` en `tests/scrapers/test_mercadona_client*.py`) no se ven afectados salvo que se les añadan las cabeceras explícitamente.

## Fuera de alcance

- **Rotación de IP / soporte de proxy.** Fuera de los límites de este proyecto, no sólo de esta spec — decisión definitiva, no pendiente. Ninguna medida de esta spec cambia la IP de salida, sólo el fingerprint HTTP (headers) y el patrón de tráfico (retries/jitter); eso no cambia en el futuro. Se evaluaron dos caminos en `mercadona-scraper-old/` (proxy rotativo de proveedor de pago, o Tor auto-alojado) y ninguno se implementa aquí ni se retomará.
- **CAPTCHA solving** o cualquier mitigación que requiera interacción humana o servicios de terceros de resolución de CAPTCHA.
- **Cambios en la estrategia de búsqueda** (Algolia, Decisión D7 de plan.md 001) — esta spec no reabre esa decisión.

## Criterios de finalización

- RF-1 a RF-6 cuentan con tests (unitarios sobre `MercadonaClient` + integración) en verde, cobertura ≥80% del código nuevo/modificado (mismo criterio que spec 001).
- `ruff check .` y `ruff format .` sin errores (constitución #8).
- Verificación manual: forzar un `429` real o simulado y confirmar que el scraper espera y reintenta en vez de fallar de inmediato.

## Dudas abiertas

Ninguna — resueltas ambas (pool de User-Agents propio, sin proxy/rotación de IP).
