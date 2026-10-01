# Spec 011 — API REST Mercadona Scraper - Upstream Schema Resilience

## Contexto y objetivo

`RawAlgoliaProduct` (y los modelos anidados `RawPriceInstructions`, `RawProductBadges`, `RawAlgoliaCategoryNode`) exige como obligatorios, con un tipo concreto, todos los campos que Algolia devolvía al capturar la muestra en la spec 001. La app solo usa siete de ellos: `id`, `display_name`, `thumbnail`, `categories[0].name` y, de `price_instructions`, `unit_price`, `bulk_price` y `reference_format` ([`app/mappers/product_mapper.py`](../../app/mappers/product_mapper.py)). Verificado el 2026-10-01:

- **Un cambio en un campo que no se usa tumba todas las búsquedas.** Con la app real y Algolia simulado, quitar `popularity_score`, quitar `objectID`, quitar `badges.is_water` o recibir `selling_method` como texto en vez de entero hace que `GET /api/v1/products` responda **`500`** para cualquier búsqueda, aunque los siete campos usados lleguen correctos.
- **El conjunto de campos que devuelve Algolia lo controla Mercadona**, no este proyecto. Contra el índice real (`products_prod_mad1_es`, 50 resultados de `leche`): con `attributesToRetrieve=*`, que es lo que pide la app, todos los resultados validan; **sin ese parámetro, Algolia omite `popularity_score` y los 50 resultados fallan la validación**. Basta con que Mercadona cambie la configuración de atributos del índice, o los atributos que su clave de búsqueda puede recuperar, para que la API deje de funcionar por un dato que no necesita. Es el mismo tipo de fallo que el bug de `iva` de la spec 001, en más campos.
- **Un campo usado que falta da `500`, no `502`.** Sin `unit_price`, la respuesta también es `500 Internal server error`: `ValidationError` sale de `MercadonaClient.search` y ni `product_search` ni la ruta lo traducen, así que lo recoge el manejador global. Es un fallo del contrato de Mercadona, que la API trata como `502` en el resto de casos (spec 007 RF-10, respuesta de `change-pc` sin cabecera).

Objetivo: que solo un cambio en los datos que la app realmente consume pueda afectar a una búsqueda, y que cuando eso ocurra la API lo comunique como un fallo de Mercadona (`502`), no como un error interno.

## Usuarios / actores

- **Aplicación cliente autorizada** (spec 004): necesita que la búsqueda siga funcionando aunque Mercadona cambie campos que la API no devuelve.
- **Responsable del scraper:** necesita distinguir en los logs y en el código de estado un cambio de Mercadona de un bug propio.

## Historias de usuario

- **H1:** Como aplicación cliente, quiero que las búsquedas sigan funcionando si Mercadona añade, quita o cambia campos que la API no usa, para no perder el servicio por un cambio irrelevante.
- **H2:** Como aplicación cliente, quiero recibir un `502` cuando Mercadona cambia un dato que la API necesita, para saber que el problema es del proveedor y no un error de la API.
- **H3:** Como responsable del scraper, quiero un log que diga qué campo de Mercadona ha cambiado, sin volcar la respuesta completa, para poder adaptar el modelo rápido.

## Requisitos funcionales (criterios de aceptación en EARS)

### Tolerancia a campos no usados

- **RF-1:** CUANDO Algolia devuelva un resultado al que le falte cualquier campo que la app no usa, o en el que ese campo tenga un tipo distinto del esperado, EL SISTEMA procesará el resultado con normalidad y la búsqueda responderá `200`. Para ello, los modelos de la respuesta de Algolia declararán **solo** los campos que la app consume; el resto no forma parte del modelo.
- **RF-2:** CUANDO Algolia devuelva campos nuevos que el modelo no conoce, EL SISTEMA los ignorará (comportamiento actual, que se mantiene).

### Fallo controlado en campos usados

- **RF-3:** SI a un resultado de Algolia le falta, o trae con un tipo no válido, alguno de los campos que la app usa (`id`, `display_name`, `thumbnail`, `categories`, `price_instructions.unit_price`, `price_instructions.bulk_price`, `price_instructions.reference_format`), EL SISTEMA responderá `502` para toda la búsqueda (no devuelve resultados incompletos en silencio, en coherencia con la spec 008), **nunca** `500`, y no guardará nada en cache.
- **RF-4:** SI la respuesta de Algolia no tiene la estructura de búsqueda esperada (`results[0]` con `hits`, `nbHits`, `nbPages`; spec 008 D3), EL SISTEMA responderá `502`, no `500`.
- **RF-5:** CUANDO ocurra el caso de RF-3 o RF-4, EL SISTEMA registrará un `WARNING` que indique qué campo falló y de qué tipo de error se trata, sin volcar el resultado completo ni la respuesta de Algolia.

## Requisitos no funcionales

- **Sin cambios de contrato:** `ProductOut`, `SearchMeta` y los códigos de estado existentes no cambian; solo deja de producirse un `500` en los casos de RF-3 y RF-4.
- **Pydantic v2 y sin `Any`** (constitución #4, #5): la tolerancia se consigue con el modelo, no desactivando la validación ni con `dict` sin tipar.
- **Tests sin red real** (constitución #7): los cambios de forma de Algolia se simulan con `respx` y la fixture real.
- **Sin dependencias nuevas.**

## Casos límite

- **Campo usado con valor `null` donde ya se admite** (`bulk_price`, `reference_format`): sigue siendo válido y produce `price_format: null` (spec 001), no es un fallo de RF-3.
- **`categories` vacía:** sigue produciendo `category: ""` (comportamiento actual del mapper), no es un fallo de RF-3.
- **Un único resultado con un campo usado roto entre 50 válidos:** `502` para toda la búsqueda (RF-3). Se acepta que un solo producto roto deje la búsqueda sin resultados, a cambio de no devolver nunca una lista que no cuadra con `total_results`.
- **Algolia deja de devolver un atributo por su configuración de índice** (verificado: sin `attributesToRetrieve=*` omite `popularity_score`): si es un campo no usado, RF-1; si es usado, RF-3.

## Fuera de alcance

- **Pedir a Algolia solo los atributos que se usan** (`attributesToRetrieve` explícito) en lugar de `*`: reduciría el tamaño de la respuesta, pero cambia lo que se pide a Mercadona y no resuelve por sí solo la validación estricta; se evalúa aparte.
- **Detectar automáticamente cambios de esquema** (alertas, comparación periódica con una muestra).
- **La resolución de almacén** (`change-pc`): ya tiene su propio manejo de respuestas rotas (spec 007 RF-10).

## Criterios de finalización

- RF-1 a RF-5 con tests en verde, sin llamadas reales a Mercadona, incluidos los casos verificados en la investigación: sin `popularity_score`, sin `objectID`, sin `badges.is_water`, `selling_method` como texto (todos ⇒ `200`) y sin `unit_price` (⇒ `502`, nunca `500`).
- La suite completa (specs 001-010) sigue en verde; CI de GitHub en verde; cobertura ≥80%.
- `ruff check .` y `ruff format .` sin errores.
- Verificación contra Algolia real: con `attributesToRetrieve=*` y sin él, los resultados de `leche` validan con el modelo nuevo.

## Dudas abiertas

Todas resueltas por el usuario el 2026-10-01:

1. ~~**¿Cómo hacer tolerantes los campos no usados?**~~ — **RESUELTA: quitarlos del modelo** (RF-1). El modelo solo declara lo que la app consume; Pydantic ya ignora los campos sobrantes. La forma completa queda documentada en la fixture real (`mercadona_algolia_hit_sample.json`). Se descarta hacerlos opcionales: un cambio de tipo en un campo no usado seguiría fallando.
2. ~~**¿Qué hacer si un resultado trae roto un campo que sí se usa?**~~ — **RESUELTA: `502` para toda la búsqueda** (RF-3), coherente con la spec 008 y la spec 007 RF-10. Se descarta descartar el resultado y devolver el resto: la lista no cuadraría con `total_results` sin que el cliente pudiera saberlo.
