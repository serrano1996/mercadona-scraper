# Spec 008 — API REST Mercadona Scraper - Search Completeness

## Contexto y objetivo

`GET /api/v1/products` devuelve hoy como mucho 50 productos y además informa mal de cuántos hay. Verificado en vivo el 2026-09-30 contra el backend de búsqueda real de Mercadona (Algolia, índice `products_prod_mad1_es`):

- **El total es falso.** Para `term=leche` Algolia informa `nbHits: 233` repartidos en `nbPages: 5` de 50. La API pide una única página de 50 ([`app/scrapers/mercadona_client.py:33`](../../app/scrapers/mercadona_client.py), `_ALGOLIA_HITS_PER_PAGE = 50`) y construye `SearchMeta.total_results` como `len(products)` ([`app/services/product_search.py:55`](../../app/services/product_search.py)), así que responde `total_results: 50` y descarta 183 productos sin avisar. Para un análisis de precios eso es un sesgo silencioso: el consumidor cree que tiene el catálogo completo de la búsqueda.
- **El término no se valida.** `ProductQuery.term` es `str` sin restricciones ([`app/models/query.py:8`](../../app/models/query.py)). Un `term` vacío o de solo espacios devuelve `nbHits: 4299`, es decir, **todo el catálogo del almacén**, y la API lo aceptaría.
- **El término no se normaliza, y eso cambia los resultados.** Algolia ignora mayúsculas (`Leche` y `leche` → 233) y los espacios repetidos internos (`leche entera` y `leche   entera` → 15), pero **no** los espacios de los extremos: `"  leche  "` → 197, no 233. Además, `Leche`, `leche` y `leche ` generan hoy tres claves de cache distintas ([`app/services/product_search.py:27`](../../app/services/product_search.py)), tres llamadas a Mercadona para la misma búsqueda.
- **Paginación de Algolia**, observada en la misma verificación: la página es 0-based (`page: 0`); una página fuera de rango devuelve `hits: []` **y `nbHits: 0`**, no el total; con término vacío `nbHits: 4299` pero `nbPages: 20` con 50 por página, es decir, Algolia solo deja paginar los primeros 1000 resultados; `hitsPerPage=1000` devuelve los 233 de `leche` en una sola llamada.

Objetivo: que la API diga la verdad sobre cuántos productos hay, permita recorrerlos todos por páginas, y rechace o normalice los términos que hoy producen resultados erróneos o caches duplicadas.

## Usuarios / actores

- **Aplicación cliente autorizada** (spec 004): necesita el total real de una búsqueda y poder recorrer todas sus páginas para comparar precios sin sesgo.
- **Sistema:** normaliza el término, consulta la página pedida a Algolia y cachea cada página por separado.

## Historias de usuario

- **H1:** Como aplicación cliente, quiero que `total_results` sea el número real de productos que coinciden con mi búsqueda, para saber si estoy viendo todos o solo una parte.
- **H2:** Como aplicación cliente, quiero pedir páginas sucesivas de una búsqueda, para obtener todos los productos y no solo los 50 primeros.
- **H3:** Como aplicación cliente, quiero que un término vacío o absurdo sea rechazado de forma explícita, para no recibir el catálogo entero por un error de integración.
- **H4:** Como responsable del scraper, quiero que `Leche`, `leche` y `leche ` se traten como la misma búsqueda, para no pagar tres llamadas a Mercadona ni devolver resultados distintos por un espacio.

## Requisitos funcionales (criterios de aceptación en EARS)

### Validación y normalización del término

- **RF-1:** SI `term` está vacío o contiene solo espacios en blanco, EL SISTEMA responderá `422 Unprocessable Entity` mediante la validación de `ProductQuery` (Pydantic v2), sin realizar ninguna petición a Mercadona.
- **RF-2:** SI `term`, tras normalizarlo (RF-3), supera los 100 caracteres, EL SISTEMA responderá `422 Unprocessable Entity` sin realizar ninguna petición a Mercadona.
- **RF-3:** CUANDO `GET /api/v1/products` reciba un `term` válido, EL SISTEMA lo normalizará antes de consultar a Mercadona y antes de construir la clave de cache: eliminar espacios en blanco de los extremos, reducir cualquier secuencia de espacios internos a uno solo y pasar a minúsculas. Motivo verificado en vivo: los extremos alteran los resultados de Algolia (197 frente a 233) y las mayúsculas/espacios internos no, así que la normalización nunca empeora un resultado.
- **RF-4:** El campo `SearchMeta.term` de la respuesta reflejará el término **normalizado** que se usó realmente en la búsqueda, no el recibido.

### Total real y paginación

- **RF-5:** EL SISTEMA aceptará dos parámetros de query opcionales: `page` (entero ≥ 1, por defecto `1`) y `page_size` (entero entre 1 y 100, por defecto `50`). SI alguno está fuera de rango, EL SISTEMA responderá `422` sin llamar a Mercadona. La página pública es 1-based aunque Algolia sea 0-based.
- **RF-6:** CUANDO se sirva una búsqueda, `SearchMeta.total_results` contendrá el número total de productos que coinciden según Mercadona (`nbHits` de Algolia), no el número de productos incluidos en esta respuesta.
- **RF-7:** `SearchMeta` incluirá tres campos nuevos: `page` (la página servida), `page_size` (el tamaño de página aplicado) y `total_pages` (tomado de `nbPages` de Algolia, que ya refleja el límite de paginación de Algolia, no calculado como `ceil(total_results / page_size)`).
- **RF-8:** CUANDO no se envíen `page` ni `page_size`, EL SISTEMA devolverá exactamente los mismos productos que antes de este spec (primera página de 50), de forma que los clientes existentes siguen funcionando sin cambios.
- **RF-9:** SI la página pedida es mayor que 1 y Mercadona devuelve cero resultados para ella, EL SISTEMA responderá `404 Not Found` con `detail: "Page out of range"`, sin realizar ninguna petición adicional a Mercadona y sin cachear esa respuesta. El `nbHits: 0` que Algolia devuelve en ese caso nunca se expone como total. La página 1 sin resultados sigue siendo un `200` con lista vacía (spec 001 RF-2).

### Cache

- **RF-10:** EL SISTEMA construirá la clave de cache de búsqueda como `search:{warehouse}:{term_normalizado}:{page}:{page_size}`, de forma que cada página se cachea por separado y dos variantes del mismo término (RF-3) comparten entrada.

## Requisitos no funcionales

- **Compatibilidad de contrato:** `ProductOut` no cambia. `SearchMeta` solo **añade** campos (`page`, `page_size`, `total_pages`); `total_results` conserva nombre y tipo, pero cambia su valor para que sea correcto (RF-6). Es un cambio de semántica asumido: hoy no hay consumidores externos.
- **Validación Pydantic v2:** `term`, `page` y `page_size` se validan en `ProductQuery`, que la ruta ya recibe en su firma (`Annotated[ProductQuery, Query()]`, spec 007 D7), así que un valor inválido da `422` y no `500`.
- **Sin llamadas extra en el caso normal:** servir una página cuesta exactamente una petición a Algolia, igual que hoy. Ninguna solución de RF-9 puede añadir peticiones al camino normal.
- **Anti-baneo sin cambios:** mismas cabeceras, reintentos y `Retry-After` de spec 002.
- **Async, tipado estricto y sin `Any`** (constitución #3, #4).

## Casos límite

- **Término de solo espacios** (`"   "`): Algolia devuelve 4299 resultados (todo el catálogo); la API lo rechaza con `422` (RF-1).
- **Búsqueda muy amplia (más de 1000 resultados):** Algolia solo deja paginar los primeros 1000. `total_results` muestra el total real (p. ej. 4299) y `total_pages` el número de páginas realmente accesibles (p. ej. 20 con 50 por página). El consumidor puede detectar el límite porque `total_pages × page_size < total_results`.
- **Última página incompleta:** `leche` con 50 por página da 5 páginas; la página 5 trae 33 productos. Es el comportamiento normal, no un error.
- **Página fuera de rango:** `404` (RF-9). Incluye el caso de un término sin ningún resultado pedido con `page=2`: tampoco existe esa página.
- **Entradas de cache antiguas** con el formato `search:{warehouse}:{term}`: dejan de leerse y caducan solas en `CACHE_TTL_SECONDS` (1 h); no hace falta limpiarlas.
- **Tildes:** `lácteos` frente a `lacteos` **no se normaliza** en este spec. No se ha verificado cómo lo trata Algolia; ver Fuera de alcance.

## Fuera de alcance

- **Normalización de tildes y otros caracteres Unicode:** no verificado en vivo; si Algolia ya los trata como equivalentes, normalizarlos no aporta nada y podría alterar búsquedas. Se evalúa en un spec futuro con evidencia.
- **Filtros y ordenación** (por precio, categoría, marca).
- **Devolver todos los resultados en una sola llamada** (Algolia lo permite con `hitsPerPage=1000`): se descarta para mantener respuestas acotadas y predecibles; el consumidor pagina.
- **Cambiar `price` de `float` a `Decimal`:** es otro cambio de contrato, independiente de este.

## Criterios de finalización

- RF-1 a RF-10 cuentan con tests en verde con HTTP mockeado (sin llamadas reales a Mercadona en la suite), cobertura ≥80% del código nuevo o modificado.
- La suite completa existente (specs 001-007) sigue en verde.
- `ruff check .` y `ruff format .` sin errores.
- Verificación manual con Algolia mockeado: `term=leche` sin `page` devuelve 50 productos con `total_results: 233`, `total_pages: 5`, `page: 1`; `page=5` devuelve 33 productos; `page=6` → `404`; `page_size=101` → `422`; `term=%20%20` → `422`; `term=Leche` y `term=leche%20` reutilizan la misma entrada de cache (una sola llamada a Algolia); `/docs` muestra `page` y `page_size` con sus límites.

## Dudas abiertas

Todas resueltas por el usuario el 2026-09-30:

1. ~~**¿`SearchMeta.term` devuelve el término normalizado o el original?**~~ — **RESUELTA:** el normalizado (RF-4). Es el que se buscó de verdad, y devolver el original obligaría a reescribirlo en cada hit de cache compartida, como ya se hace con `postal_code` (spec 007 RF-7).
2. ~~**¿Qué responde la API ante una página fuera de rango?**~~ — **RESUELTA:** `404` con `detail: "Page out of range"` (RF-9). Algolia devuelve `nbHits: 0` en ese caso (verificado con `page=99`), así que responder `200` con total 0 sería falso, y hacer una segunda llamada para recuperar el total añadiría peticiones justo en el caso que puede provocar un cliente en bucle.
3. ~~**¿Máximo de `page_size` en 100?**~~ — **RESUELTA:** sí, 100 (RF-5). Mantiene respuestas y entradas de cache acotadas; el valor por defecto sigue siendo 50.
