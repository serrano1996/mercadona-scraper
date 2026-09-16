# Spec 001 — API REST Mercadona Scraper MVP

## Contexto y objetivo

Actualmente no existe una forma sencilla ni estandarizada de consultar el catálogo de productos, precios y categorías de Mercadona programáticamente sin lidiar directamente con sus mecanismos internos de API. Esta API REST unifica, valida y sirve esta información de forma estructurada y optimizada mediante caché, permitiendo a aplicaciones de terceros o análisis internos acceder a datos actualizados de productos en tiempo real de forma rápida y confiable.

## Usuarios / actores

- **Desarrolladores integradores:** Consumidores de la API que construyen aplicaciones cliente (comparadores de precios, gestores de listas de compra, etc.).
- **Sistema automatizado (Client App):** Servicios backend que requieren consultar datos de productos o categorías de forma periódica.

## Historias de usuario

- **H1:** Como desarrollador cliente, quiero buscar productos por texto clave para obtener un listado filtrado de resultados relevantes.

## Requisitos funcionales (criterios de aceptación en EARS)

- **RF-1:** CUANDO un usuario envíe una petición GET a `/api/v1/products?postal_code=28001&term=leche`, EL SISTEMA obtendrá los datos actualizados del producto desde la API interna de Mercadona, los transformará al esquema Pydantic unificado y responderá con un estado 200 OK y el objeto JSON.
- **RF-2:** SI no se obtiene ningún producto del término solicitado no, ENTONCES EL SISTEMA responderá con una lista vacia (no es un error).
- **RF-3:** MIENTRAS el servicio de Mercadona no responda o devuelva un error HTTP 5xx, EL SISTEMA reintentará la petición hasta 3 veces con *backoff* exponencial antes de devolver un error 502 Bad Gateway.
- **RF-4:** EL SISTEMA guardará en Redis la respuesta de cada producto y categoría con un TTL (Time To Live) de 1 hora para evitar saturar el servicio origen.

## Requisitos no funcionales

- **Rendimiento:** El tiempo de respuesta para peticiones cacheadas en Redis debe ser menor a 50 ms (p95), y menor a 1200 ms para peticiones sin cachear.
- **Formato y Validación:** Todas las respuestas deben devolver contenido `application/json` validado estrictamente mediante schemas de Pydantic v2. Ninguna anotación de tipo usa `Any` (constitución #4).
- **Documentación:** La API debe exponer automáticamente la documentación interactiva OpenAPI (Swagger) en `/docs`.
- **Origen de datos:** Todo dato proviene exclusivamente de los endpoints JSON internos de Mercadona consumidos vía `httpx`; prohibido Playwright, Selenium o BeautifulSoup (constitución #2).
- **Asincronía:** Toda llamada a Mercadona y todo endpoint expuesto son asíncronos (`async def` + `httpx.AsyncClient`) (constitución #3).

## Casos límite

- **Aumento de precios / Cambio de formato:** Si el producto no contiene información de precio por unidad de medida o peso, el sistema responderá con `null` en dicho campo en lugar de fallar la validación.
- **Búsqueda vacía:** Si el parámetro de búsqueda por texto no arroja resultados, el sistema devolverá una lista vacía `[]` con código HTTP 200 OK.
- **Caché inaccesible:** Si el servidor de Redis está caído, la API registrará un advertencia (*warning*) y responderá la petición realizando el scraping directo sin interrumpir el servicio.

## Fuera de alcance

- Gestión de autenticación de usuarios o API Keys en esta primera fase.
- Creación, modificación o simulación del carrito de la compra de Mercadona.
- Histórico de precios/almacenamiento persistente en base de datos relacional (solo caché temporal).

## Criterios de finalización

- Todos los Requisitos Funcionales (RF-1 a RF-4) cuentan con tests de integración (`pytest`) en verde con una cobertura de código superior al 80%.
- `ruff check .` y `ruff format .` sin errores (constitución #8).
- Verificación exitosa del flujo principal ejecutando `uvicorn app.main:app` y consultando manualmente 3 productos reales desde la interfaz de Swagger `/docs`.

## Dudas abiertas

- **[NECESITA ACLARACIÓN]** ¿Es necesario requerir un código postal o identificador de tienda en la API para reflejar variaciones regionales de stock y precios de Mercadona?

## Formato de la respuesta (200 OK)

```json
{
  "search": {
    "postal_code": "28001",
    "term": "leche",
    "warehouse": "mad1",
    "strategy_used": "api",
    "scraped_at": "2026-07-24T10:00:00Z",
    "total_results": 1
  },
  "products": [
    {
      "id": "1",
      "name": "Leche entera",
      "price": 1.05,
      "price_format": "1.05 €/L",
      "image_url": "https://example.com/1.jpg",
      "category": "Lácteos"
    }
  ]
}
```