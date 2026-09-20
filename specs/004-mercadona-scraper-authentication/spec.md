# Spec 004 — API REST Mercadona Scraper - Authentication

## Contexto y objetivo

Hoy `GET /api/v1/products` no exige ninguna credencial: cualquiera que conozca la URL puede consumir la API, incluyendo terceros no autorizados. Eso expone dos riesgos reales:

- **Coste ajeno:** cada petición de un tercero dispara, en el peor caso (cache miss), tráfico real contra Mercadona/Algolia — el mismo tráfico que las medidas anti-baneo de spec 002 intentan mantener bajo control. Un tercero sin límites propios puede agotar el presupuesto de peticiones "seguras" que nos hemos dado a nosotros mismos.
- **Superficie no controlada:** no hay forma de saber quién consume la API ni de revocar acceso a un cliente concreto sin cambiar la URL o tumbar el servicio para todos.

Objetivo: que sólo nuestras propias aplicaciones (conocedoras de un token compartido) puedan usar la API — un control de acceso servicio-a-servicio simple, sin cuentas de usuario ni dependencias nuevas (constitución #1).

## Usuarios / actores

- **Aplicación cliente autorizada:** un servicio nuestro que consume la API, conoce el token válido y lo envía en cada petición.
- **Tercero no autorizado:** cualquier llamante que no conozca un token válido — debe ser rechazado sin excepción.
- **Responsable de mantener el scraper en producción:** configura y rota los tokens válidos vía variables de entorno, sin desplegar código nuevo.

## Historias de usuario

- **H1:** Como responsable de mantener el scraper en producción, quiero que la API rechace cualquier petición sin un token válido, para que sólo nuestras aplicaciones puedan consumirla y no terceros.
- **H2:** Como responsable de mantener el scraper en producción, quiero poder rotar o revocar un token sin desplegar código nuevo, para reaccionar rápido si un token se filtra.

## Requisitos funcionales (criterios de aceptación en EARS)

- **RF-1:** CUANDO una petición llegue a cualquier endpoint bajo `/api/v1/`, EL SISTEMA exigirá la cabecera `X-API-Key` con un valor que coincida con alguno de los tokens válidos configurados, antes de ejecutar cualquier lógica de negocio.
- **RF-2:** SI la cabecera `X-API-Key` está ausente o vacía, EL SISTEMA responderá `401 Unauthorized` con un cuerpo JSON de error, sin ejecutar la lógica del endpoint.
- **RF-3:** SI la cabecera `X-API-Key` está presente pero no coincide con ningún token válido configurado, EL SISTEMA responderá `401 Unauthorized` (mismo formato de respuesta que RF-2 — sin distinguir "ausente" de "inválido" en el cuerpo de la respuesta, para no dar pistas a quien intenta adivinar un token).
- **RF-4:** EL SISTEMA comparará el token recibido contra los tokens válidos mediante comparación en tiempo constante (`secrets.compare_digest` de la librería estándar o equivalente), para no filtrar información del token por temporización.
- **RF-5:** EL SISTEMA leerá la lista de tokens válidos desde `Settings.API_KEYS` (variable de entorno con valores separados por coma), nunca hardcodeados en el código — permite revocar o rotar un token de una app concreta sin afectar a las demás ni desplegar código nuevo (cubre H2).
- **RF-6:** CUANDO una petición sea rechazada por autenticación (401), EL SISTEMA registrará el evento a nivel `WARNING` con la ruta solicitada — integrando con el logging de spec 003 — sin loguear jamás el valor de la cabecera `X-API-Key` recibida, válida o no.

## Requisitos no funcionales

- **Sin dependencias nuevas:** la validación usa `fastapi.security` (ya incluido con FastAPI) y `secrets` de la librería estándar — nada de librerías de OAuth2/JWT (constitución #1).
- **Nunca loguear el token:** ninguna línea de log, en ningún nivel, incluirá el valor de `X-API-Key` — mismo criterio que spec 003 aplicó a las credenciales de Algolia.
- **Tipado estricto:** cualquier dependencia/utilidad nueva usa type hints explícitos, sin `Any` (constitución #4).
- **Docs vivas:** el esquema OpenAPI (`/docs`) reflejará el requisito de la cabecera `X-API-Key` en los endpoints protegidos (constitución #9).

## Casos límite

- **Cabecera presente pero vacía** (`X-API-Key: `): se trata igual que ausente (RF-2), no como "inválida" (RF-3) — evita ambigüedad en el criterio de aceptación.
- **Token válido pero con espacios/mayúsculas distintas:** se compara el valor exacto recibido, sin `strip()` ni normalización — un token es un secreto opaco, no texto a interpretar.
- **Múltiples tokens válidos simultáneos** (rotación sin downtime: token antiguo y nuevo coexistiendo durante un despliegue): cubierto por RF-1/RF-5 — `API_KEYS` acepta varios valores.
- **`/docs` y `/openapi.json` sin cabecera:** responden normalmente (200), no exigen `X-API-Key` — sólo los endpoints bajo `/api/v1/` están protegidos (RF-1).

## Fuera de alcance

- **OAuth2, JWT, refresh tokens o cuentas de usuario** — esto es autenticación servicio-a-servicio con un secreto compartido, no autenticación de usuarios finales.
- **Rate limiting o cuotas por token** — no pedido; spec 002 ya cubre el tráfico saliente hacia Mercadona, esto protege el acceso entrante a nuestra propia API.
- **Rotación automática o gestión de tokens vía panel/API** — los tokens se gestionan manualmente vía variable de entorno; no se construye infraestructura de gestión.
- **HTTPS/TLS** — se asume gestionado por el reverse proxy/infraestructura de despliegue, no por la aplicación.

## Criterios de finalización

- RF-1 a RF-6 cuentan con tests en verde, cobertura ≥80% del código nuevo/modificado (mismo criterio que specs 001-003).
- `ruff check .` y `ruff format .` sin errores (constitución #8).
- Verificación manual: petición sin cabecera, con cabecera inválida y con cabecera válida contra la app real (uvicorn), confirmando `401`/`200` según corresponda y que ningún log expone el token.

## Dudas abiertas

Ninguna — resueltas:

1. **Lista de tokens válidos** (no un único token compartido): variable de entorno `API_KEYS` con valores separados por coma, permite revocar el acceso de una app concreta sin afectar a las demás y rotar sin downtime.
2. **`/docs` y `/openapi.json` quedan públicos** — sólo se protegen los endpoints bajo `/api/v1/`.
3. **Cabecera `X-API-Key`** (no `Authorization: Bearer`).
