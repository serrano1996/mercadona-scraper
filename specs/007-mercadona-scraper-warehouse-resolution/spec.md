# Spec 007 — API REST Mercadona Scraper - Warehouse Resolution

## Contexto y objetivo

Mercadona no sirve el mismo catálogo ni los mismos precios en todo el país: cada código postal se resuelve internamente a un almacén ("wh") y ese almacén determina qué productos existen y a qué precio. Verificado en vivo el 2026-09-24 contra `PUT https://tienda.mercadona.es/api/postal-codes/actions/change-pc/` (body `{"new_postal_code": "NNNNN"}`), que devuelve el almacén en la cabecera de respuesta `x-customer-wh`:

- `28001` -> `mad3`, `46001` -> `vlc1`, `08001` -> `bcn1`, `41001` -> `svq1`, `35001` -> `4701`, `07001` -> `3842`.
- En la categoría Fruta (27): 31 de 44 productos compartidos entre mad1/mad3/vlc1/bcn1/svq1 tenían precio distinto según almacén — incluso mad1 y mad3 difieren entre sí pese a ser ambos "Madrid". El tamaño del catálogo también varía (entre 47 y 51 productos según almacén).
- Canarias (`4701`) es más barato en productos envasados (previsiblemente por tributar IGIC en vez de IVA) y tiene un catálogo más pequeño.

`GET /api/v1/products` hoy no resuelve nada de esto: [`app/api/v1/products.py:29`](../../app/api/v1/products.py) fija `_DEFAULT_WAREHOUSE = "mad1"` como constante y lo pasa a `search_products` sin mirar el `postal_code` recibido. El código postal viaja hasta `product_search.py` únicamente para construir la clave de cache — [`app/services/product_search.py:23`](../../app/services/product_search.py): `search:{postal_code}:{term}` — y para el campo `SearchMeta.postal_code` de la respuesta. Consecuencia real y ya confirmada: **toda consulta, sea cual sea el código postal, recibe precios y catálogo de `mad1`**, cacheados bajo una clave que aparenta ser específica del código postal pero no lo es — dos códigos postales de almacenes distintos (p.ej. `28001` y `46001`) obtienen resultados idénticos e incorrectos para uno de los dos, y ese resultado incorrecto queda cacheado con la etiqueta del código postal equivocado hasta que expira el TTL.

Objetivo: resolver el almacén real a partir del `postal_code` en cada petición contra el endpoint de Mercadona, cachear esa resolución para no pagar su coste en cada búsqueda, y usar el almacén (no el código postal) como base de la clave de cache de productos — para que dos códigos postales del mismo almacén compartan cache y dos códigos postales de almacenes distintos nunca se mezclen.

## Usuarios / actores

- **Aplicación cliente autorizada** (spec 004): consume `GET /api/v1/products` con un `postal_code` real y espera precios/catálogo del almacén que de verdad le correspondería en Mercadona, no los de `mad1` por defecto.
- **Sistema:** resuelve `postal_code -> warehouse` contra Mercadona antes de buscar productos, y reutiliza esa resolución desde Redis mientras sea válida.

## Historias de usuario

- **H1:** Como aplicación cliente, quiero que `GET /api/v1/products?postal_code=X` devuelva precios y catálogo del almacén real de ese código postal, para no mostrar a mis usuarios datos de un almacén equivocado (hoy siempre `mad1`).
- **H2:** Como aplicación cliente, quiero que un código postal con formato inválido sea rechazado de forma explícita antes de golpear Mercadona, para detectar errores de integración pronto.
- **H3:** Como responsable de mantener el scraper, quiero que la resolución `postal_code -> warehouse` se cachee con una TTL configurable, para no pagar una petición extra a Mercadona en cada búsqueda de un código postal ya resuelto recientemente.
- **H4:** Como responsable de mantener el scraper, quiero que dos códigos postales que resuelven al mismo almacén compartan cache de productos, y que dos que resuelven a almacenes distintos nunca lo compartan, para que el cache de productos sea correcto por construcción.

## Requisitos funcionales (criterios de aceptación en EARS)

### Validación de entrada

- **RF-1:** CUANDO `GET /api/v1/products` reciba un `postal_code` que no sean exactamente 5 dígitos, EL SISTEMA responderá `422 Unprocessable Entity` mediante la validación de `ProductQuery` (Pydantic v2), sin realizar ninguna petición a Mercadona.

### Resolución de almacén

- **RF-2:** CUANDO `GET /api/v1/products` reciba un `postal_code` con formato válido, EL SISTEMA resolverá el almacén correspondiente contra el endpoint `PUT {MERCADONA_BASE_URL}/api/postal-codes/actions/change-pc/` de Mercadona (body `{"new_postal_code": postal_code}`), leyendo el valor del almacén de la cabecera de respuesta `x-customer-wh`, en lugar de usar un almacén fijo.
- **RF-3:** EL SISTEMA cacheará en Redis la resolución `postal_code -> warehouse` bajo una clave dedicada (p.ej. `postal-code-wh:{postal_code}`), con una TTL configurable vía `Settings` independiente de `CACHE_TTL_SECONDS`: `WAREHOUSE_CACHE_TTL_SECONDS: int = 86400` (24h), reflejando que la asignación de almacén cambia con mucha menos frecuencia que el catálogo/precios.
- **RF-4:** CUANDO exista una resolución de almacén cacheada y vigente para el `postal_code` recibido, EL SISTEMA la reutilizará en lugar de repetir la petición `change-pc` contra Mercadona.
- **RF-5:** EL SISTEMA usará el almacén resuelto (RF-2/RF-4) como argumento `warehouse` de `search_products`/`MercadonaClient.search()`, reemplazando el uso de una constante fija (`_DEFAULT_WAREHOUSE`).

### Cache de búsqueda de productos por almacén

- **RF-6:** EL SISTEMA construirá la clave de cache de resultados de búsqueda como `search:{warehouse}:{term}` (almacén resuelto, no código postal), de forma que dos códigos postales que resuelvan al mismo almacén compartan resultado cacheado y dos que resuelvan a almacenes distintos nunca lo compartan.
- **RF-7:** El campo `SearchMeta.warehouse` de la respuesta reflejará el almacén real resuelto (RF-2/RF-4), no un valor fijo — el campo `SearchMeta.postal_code` seguirá reflejando el código postal recibido en la petición, sin cambios de contrato.

### Errores

- **RF-8:** SI la petición `change-pc` a Mercadona falla por transporte o por un error 5xx/429 tras agotar los reintentos de la política de spec 002 (`RETRY_MAX_ATTEMPTS`, backoff, `Retry-After`), EL SISTEMA responderá `502 Bad Gateway`, igual que el comportamiento ya existente de `UpstreamUnavailableError` para la búsqueda de productos.
- **RF-9:** SI Mercadona responde a `change-pc` con `404 Not Found` (código postal fuera de su zona de servicio; verificado en vivo el 2026-09-24, cuerpo `{"error_msg":"This zip code is outside of our working area"}`), EL SISTEMA responderá `404 Not Found` con un `detail` propio (p.ej. `"Postal code not served by Mercadona"`), sin reenviar el `error_msg` de Mercadona y sin reintentar la petición (un `404` es una respuesta definitiva, no un fallo transitorio de la política de spec 002).
- **RF-10:** SI Mercadona responde a `change-pc` con `2xx` pero sin la cabecera `x-customer-wh` (no observado en vivo; indicaría un cambio de contrato del endpoint), EL SISTEMA responderá `502 Bad Gateway` y registrará un log `WARNING`, sin interpretarlo como "código postal sin servicio" y sin cachear resultado alguno.
- **RF-11:** EL SISTEMA cacheará en Redis la no-resolución de RF-9 (código postal sin servicio) bajo una clave distinguible de una resolución válida, con una TTL corta y configurable vía `Settings` independiente de la TTL de RF-3 (`WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS: int = 3600`, 1h), de forma que peticiones repetidas para ese código postal dentro de la TTL respondan `404` sin repetir `change-pc` contra Mercadona.
- **RF-12:** EL SISTEMA registrará cada resolución de almacén (cache hit, cache miss resuelto, o fallo) a nivel `INFO`/`WARNING` siguiendo spec 003, incluyendo `postal_code` y `warehouse` cuando exista, sin loguear cabeceras ni cuerpos completos de la respuesta de Mercadona que puedan contener datos no relevantes para el diagnóstico.
- **RF-13:** SI Mercadona responde a `change-pc` con un `4xx` distinto de `404` y `429` (p.ej. `400`, o `403` por un posible bloqueo del WAF), EL SISTEMA responderá `502 Bad Gateway`, sin reintentar (misma política de spec 002: sólo se reintentan `5xx`, `429` y errores de transporte) y sin cachear resultado alguno. Con el código postal ya validado por RF-1 es un fallo del upstream, no del cliente.

## Requisitos no funcionales

- **Async y tipado estricto:** la resolución de almacén es `async def` sobre `httpx.AsyncClient`, sin `Any` en anotaciones (constitución #3, #4).
- **Validación Pydantic v2:** el formato de `postal_code` (5 dígitos) se valida en `ProductQuery`, no con checks manuales dispersos (constitución #5).
- **Reutiliza política anti-baneo existente:** la petición `change-pc` pasa por el mismo `_request_with_retry` (o equivalente) de spec 002 — mismos `RETRY_MAX_ATTEMPTS`, backoff exponencial, respeto de `Retry-After` — sin una política de reintentos paralela y distinta.
- **Sin dependencias nuevas:** se implementa con el stack ya fijado — `httpx`, Redis, Pydantic v2 (constitución #1).
- **Sin secretos en logs:** ningún log de resolución de almacén incluye cabeceras completas de la respuesta de Mercadona más allá de `x-customer-wh` (constitución #10 vía spec 003).
- **Compatibilidad de contrato:** la forma de la respuesta (`ProductSearchResponse`, `SearchMeta`, `ProductOut`) no cambia — sólo el valor de `SearchMeta.warehouse` pasa de ser siempre `"mad1"` a ser el almacén real.

## Casos límite

- **Dos códigos postales del mismo almacén** (p.ej. dos códigos postales de Madrid capital que ambos resuelven a `mad3`): comparten entrada de cache de productos (`search:mad3:{term}`) — es el comportamiento deseado, no una colisión (cubre H4).
- **Cache de `postal_code -> warehouse` expira entre dos peticiones consecutivas del mismo código postal:** la segunda petición repite `change-pc` contra Mercadona (RF-4 sólo aplica con cache vigente); no hay stale-while-revalidate — se resuelve de nuevo de forma síncrona antes de responder.
- **Redis no disponible para la resolución de almacén:** mismo criterio que `CacheRepository` ya aplica a resultados de búsqueda (spec 001) — un fallo de Redis no debe tumbar la petición; se degrada a resolver contra Mercadona en cada llamada, logueando `WARNING`, no `502`.
- **Canarias (`4701`) y otros almacenes con formato de código no numérico de 4 dígitos** (visto en los ejemplos: `4701`, `3842`): el valor de `warehouse` es un identificier opaco de Mercadona, no se asume ningún formato (ni "3 letras + 1 dígito" ni longitud fija) al construir `index_{warehouse}_es` en `MercadonaClient` — ya es así hoy, este spec no lo cambia.
- **Petición `change-pc` para un código postal donde Mercadona no tiene servicio** (p.ej. `00000`, `99999`): Mercadona responde `404` → RF-9 y RF-11. Ceuta (`51001` → `4436`), Melilla (`52001` → `4402`) y Álava (`01001` → `4697`) sí tienen servicio (verificado el 2026-09-24).
- **Mercadona empieza a dar servicio a un código postal cacheado como "sin servicio":** se acepta la ventana de staleness de la TTL corta de RF-11.

## Fuera de alcance

- **Comparación de precios entre almacenes** — este spec resuelve un único almacén por petición; no construye ningún endpoint ni lógica que compare catálogos/precios entre almacenes.
- **Tabla estática de prefijos de código postal -> almacén** — se descarta explícitamente; la resolución siempre pasa por el endpoint real de Mercadona (con cache, RF-3/RF-4), nunca por un mapeo hardcodeado que quedaría desactualizado.
- **Invalidación proactiva del cache de almacén** (p.ej. si Mercadona reasigna un código postal a otro almacén antes de que expire la TTL) — se acepta la ventana de staleness que define la TTL configurable (RF-3); no se construye un mecanismo de invalidación por evento.
- **Persistencia propia de la relación código postal -> almacén** más allá del cache con TTL — coherente con el límite de responsabilidad de la constitución (#11): el scraper es un proxy inteligente, no la fuente de verdad.
- **Protección frente a enumeración de códigos postales** (p.ej. un cliente recorriendo `00001`…`99999`): el cache negativo de RF-11 sólo evita repetir el mismo código, no frena peticiones con códigos distintos, cada uno de los cuales llega una vez a Mercadona. Se acepta el riesgo porque `/api/v1/*` exige `X-API-Key` (spec 004) y sólo lo usan clientes conocidos; el rate limiting queda para un spec futuro. Se descarta validar contra una lista estática de códigos postales españoles por el mismo motivo que la tabla de prefijos.

## Criterios de finalización

- RF-1 a RF-13 cuentan con tests en verde con HTTP mockeado (sin llamadas reales a Mercadona en la suite), cobertura ≥80% del código nuevo/modificado (mismo criterio que specs 001-006).
- La suite completa existente (specs 001-006) sigue en verde.
- `ruff check .` y `ruff format .` sin errores (constitución #8).
- Verificación manual: dos códigos postales de almacenes distintos conocidos (p.ej. `28001` y `46001`) devuelven `SearchMeta.warehouse` distinto (`mad3` y `vlc1` respectivamente) y resultados de catálogo/precio distintos; un `postal_code` con formato inválido (`"1234"`, `"abcde"`) responde `422`; repetir la misma petición dentro de la TTL de `WAREHOUSE_CACHE_TTL_SECONDS` no repite la llamada `change-pc` (verificado por `call_count` sobre el mock, nunca contra Mercadona real).

## Dudas abiertas

1. ~~**Comportamiento exacto de `change-pc` para un código postal sin servicio**~~ — **RESUELTA (2026-09-24):** verificado en vivo, Mercadona responde `404` con `{"error_msg":"This zip code is outside of our working area"}` y sin `x-customer-wh` (probado con `00000`, `99999`, `1234`, `abcde`). Decisión: RF-9 (`404` propio, sin reintento), RF-10 (`2xx` sin cabecera → `502`) y RF-11 (cache negativo con TTL corta).

2. ~~**Nombres y valores por defecto de las TTL**~~ — **RESUELTA (2026-09-24):** `WAREHOUSE_CACHE_TTL_SECONDS = 86400` (24h, RF-3) y `WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS = 3600` (1h, RF-11), con el mismo patrón de nombres que `CACHE_TTL_SECONDS`. Motivo de 24h frente a 7 días: volver a resolver cuesta un único `PUT` por código postal y día, mientras que un almacén desactualizado sirve precios incorrectos durante toda la TTL; 24h sigue siendo unas 24 veces la TTL de productos (1h). Motivo de 1h para el cache negativo: los `404` son casi siempre códigos inexistentes que no cambian, una apertura nueva de Mercadona tolera 1h de retraso, y queda alineado con `CACHE_TTL_SECONDS`.
