# Spec 010 — API REST Mercadona Scraper - Operational Robustness

## Contexto y objetivo

Las specs 001 y 007 definen que, si Redis no está disponible, la API sigue funcionando sin cache: `CacheRepository` y `WarehouseCacheRepository` capturan `RedisError`, registran un `WARNING` y se comportan como un fallo de cache. Esa degradación **solo funciona si Redis falla rápido**. Verificado el 2026-10-01:

- **El cliente de Redis no tiene tiempo límite.** `Redis.from_url(settings.REDIS_URL)` ([`app/main.py`](../../app/main.py)) crea el cliente con `socket_timeout: None` y `socket_connect_timeout: None`: espera indefinidamente.
- **Un Redis que acepta la conexión pero no responde cuelga la petición.** Con un servidor local que acepta conexiones TCP y nunca contesta (el comportamiento de un Redis remoto con la red degradada), `CacheRepository.get` seguía esperando a los 5 s, cortado por el test, no por la app. Con `socket_timeout=0.5` el mismo `get` devolvió `None` a los 0,50 s y registró `Redis unavailable, skipping cache read`: la degradación existente funcionó sin cambios, porque `redis.exceptions.TimeoutError` es subclase de `RedisError`.
- **Los tests no lo detectan:** `fakeredis` y los dobles con `side_effect=RedisConnectionError` fallan al instante; ningún test simula un Redis que no responde.
- **Esto importa más con un Redis gestionado remoto** (p. ej. Upstash), donde la latencia y los cortes de red son más probables que con un Redis local.
- **El timeout HTTP hacia Mercadona/Algolia es implícito:** `httpx.AsyncClient` usa 5 s por defecto ([`app/scrapers/http_client_factory.py`](../../app/scrapers/http_client_factory.py)), sin que el código lo declare ni se pueda configurar.
- **`/health` no refleja el estado de Redis:** responde `{"status": "ok"}` aunque Redis esté caído o colgado. Es correcto como prueba de vida (spec 005, `HEALTHCHECK` de Docker), pero no hay forma de saber si la instancia puede servir con cache.

Objetivo: que ninguna operación contra Redis o contra Mercadona pueda colgar una petición indefinidamente, que esos límites sean configurables, y que exista un endpoint que indique si las dependencias propias de la instancia (Redis) están disponibles.

## Usuarios / actores

- **Aplicación cliente autorizada** (spec 004): espera una respuesta (con o sin cache) en un tiempo acotado, nunca una petición colgada.
- **Operador / orquestador** (Docker, plataforma de despliegue): necesita saber si la instancia está viva (`/health`) y si está lista para servir con cache (`/ready`).
- **Sistema:** aplica los tiempos límite y degrada a "sin cache" cuando Redis no responde a tiempo.

## Historias de usuario

- **H1:** Como aplicación cliente, quiero que una petición termine en un tiempo acotado aunque Redis no responda, para no quedarme esperando indefinidamente.
- **H2:** Como operador, quiero configurar los tiempos límite de Redis y de las peticiones a Mercadona sin tocar código, para ajustarlos a la latencia del entorno (Redis local o gestionado remoto).
- **H3:** Como operador, quiero un endpoint que indique si la instancia puede usar Redis, para detectar un Redis caído sin que la prueba de vida reinicie un proceso que está sano.

## Requisitos funcionales (criterios de aceptación en EARS)

### Tiempos límite de Redis

- **RF-1:** EL SISTEMA creará el cliente de Redis con un tiempo límite de conexión y un tiempo límite de operación, ambos tomados de una única variable de `Settings`, `REDIS_TIMEOUT_SECONDS: float = 1.0`, que debe ser mayor que 0.
- **RF-2:** SI Redis acepta la conexión pero no responde a una operación de cache dentro del tiempo límite, EL SISTEMA tratará el caso como Redis no disponible: la operación se comportará como un fallo de cache (lectura) o como una escritura omitida, con un `WARNING`, exactamente como hoy ante `RedisError` (specs 001 y 007), y la petición continuará.
- **RF-3:** SI Redis no responde durante toda una petición de búsqueda, EL SISTEMA responderá igualmente (resolviendo el almacén y buscando directamente en Mercadona), en un tiempo acotado por los tiempos límite configurados y no indefinido.

### Tiempo límite HTTP

- **RF-4:** EL SISTEMA declarará explícitamente el tiempo límite de las peticiones HTTP a Mercadona y Algolia con `HTTP_TIMEOUT_SECONDS: float = 5.0` en `Settings` (mayor que 0), aplicado a conexión, lectura, escritura y espera de conexión del pool. El valor por defecto es el mismo que el implícito actual de `httpx`, así que sin configuración el comportamiento no cambia.
- **RF-5:** CUANDO una petición HTTP a Mercadona o Algolia supere ese tiempo límite, EL SISTEMA la tratará como hoy trata un error de transporte: se reintenta según la política de spec 002 y, si se agotan los reintentos, responde `502`.

### Disponibilidad

- **RF-6:** EL SISTEMA expondrá `GET /ready`, público como `/health` (sin `X-API-Key`), que comprobará que Redis responde (`PING`) dentro del tiempo límite de RF-1.
- **RF-7:** CUANDO Redis responda, `GET /ready` devolverá `200` con `{"status": "ready"}`. SI Redis no responde o falla, devolverá `503` con `{"status": "unavailable", "redis": "unreachable"}`, sin incluir la URL de Redis, credenciales ni detalles del error.
- **RF-8:** `GET /health` no cambiará: seguirá respondiendo `200` sin comprobar dependencias, porque es la prueba de vida que usa el `HEALTHCHECK` de Docker (spec 005) y no debe fallar por una dependencia externa caída.

## Requisitos no funcionales

- **Sin cambios de contrato en `/api/v1/products`:** misma respuesta, mismos códigos de estado.
- **Sin dependencias nuevas** (constitución #1): `redis-py` y `httpx` ya soportan tiempos límite.
- **Tests sin red real** (constitución #7): el caso "Redis no responde" se prueba con un servidor local que acepta conexiones y nunca contesta, o con un doble equivalente; nunca contra un Redis o Mercadona reales.
- **Sin secretos en logs ni respuestas:** ni la URL de Redis (puede contener la contraseña de Upstash) ni el mensaje del error de conexión aparecen en `/ready`; en los logs, solo el tipo de fallo.
- **Async y tipado estricto, sin `Any`** (constitución #3, #4).

## Casos límite

- **Redis lento pero vivo:** si responde después del tiempo límite, esa operación se trata como fallo de cache; la siguiente vuelve a intentarlo. No hay "circuito abierto" que deje de intentarlo durante un tiempo (fuera de alcance).
- **Latencia máxima añadida con Redis colgado:** una búsqueda hace hasta cuatro operaciones de cache (leer y escribir almacén, leer y escribir resultado), así que puede tardar hasta unas cuatro veces el tiempo límite de Redis más la llamada a Mercadona. Es acotado, que es lo que pide RF-3; el valor por defecto debe elegirse con esto en cuenta.
- **Redis rechaza la conexión** (caso que ya funciona hoy): falla al instante con `ConnectionError`, sin esperar al tiempo límite.
- **`/ready` con Mercadona caída:** sigue respondiendo `200` si Redis responde. Mercadona es un tercero; una caída suya no debe marcar la instancia como no lista (ver Fuera de alcance).
- **Tiempo límite de Redis mal configurado** (0 o negativo): `Settings` lo rechaza al arrancar, igual que cualquier otra variable inválida.

## Fuera de alcance

- **Comprobar Mercadona/Algolia en `/ready`:** depender de un tercero en la comprobación de disponibilidad haría que todas las instancias se marquen como no listas a la vez por un problema ajeno.
- **Circuit breaker** (dejar de llamar a Redis durante un tiempo tras varios fallos).
- **Peticiones idénticas concurrentes** (mejora 5 del análisis): spec aparte.
- **Cambiar el `HEALTHCHECK` de Docker a `/ready`.**
- **Tiempo límite global por petición** (además de los de cada operación).

## Criterios de finalización

- RF-1 a RF-8 con tests en verde, sin Redis ni Mercadona reales; incluido un test que demuestre que, con un Redis que no responde, `GET /api/v1/products` termina en un tiempo acotado y con `200`.
- La suite completa (specs 001-009) sigue en verde, la CI de GitHub en verde y la cobertura ≥80%.
- `ruff check .` y `ruff format .` sin errores.
- `README.md` y `.env.example` documentan las variables nuevas y `/ready`.
- Verificación manual: con el contenedor de Docker y un Redis inaccesible, `/health` responde `200`, `/ready` responde `503` y una búsqueda responde sin colgarse.

## Dudas abiertas

Todas resueltas por el usuario el 2026-10-01:

1. ~~**¿Qué tiempo límite por defecto para Redis?**~~ — **RESUELTA: 1 s** (RF-1). Con Redis colgado añade como mucho unos 4 s a una búsqueda. Se descartan 0,5 s (falsos fallos de cache con una red regular) y 2 s (hasta unos 8 s añadidos). La latencia típica de Upstash (decenas de milisegundos) no se ha verificado contra una cuenta real.
2. ~~**¿Una variable o dos para Redis?**~~ — **RESUELTA: una**, `REDIS_TIMEOUT_SECONDS`, aplicada a conexión y operación (RF-1). Ningún caso del proyecto necesita distinguirlas.
3. ~~**¿Cómo llamar al tiempo límite HTTP?**~~ — **RESUELTA:** `HTTP_TIMEOUT_SECONDS`, por defecto `5.0` (RF-4).
