# Spec 009 — API REST Mercadona Scraper - Continuous Integration

## Contexto y objetivo

Hoy la única garantía de que el código funciona es que alguien ejecute `pytest` y `ruff` en su máquina antes de subir. Eso ya ha fallado en este proyecto:

- **Nunca se ha probado la versión que se despliega.** El `Dockerfile` usa `python:3.11-slim`; la suite se ha ejecutado siempre en Python 3.14 (entorno local). Verificado el 2026-09-30 en un entorno limpio de Python 3.11.16: la suite pasa (217 tests) y `ruff` está limpio, pero es la primera vez que se comprueba.
- **Las versiones de las dependencias no son reproducibles.** `pyproject.toml` solo fija mínimos (`fastapi>=0.115`, etc.) y no hay lockfile. En la misma fecha, una instalación limpia resolvió `fastapi 0.142.2` y `starlette 1.7.0`, frente a `0.139.2` y `1.1.0` del entorno local. La nueva Starlette ya emite `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`. Hoy pasa; una versión futura puede romper la suite o producción sin ningún cambio en este repositorio.
- **Entorno incompleto sin detectar.** Al empezar la spec 007, `pytest` no arrancaba en local porque faltaban `fakeredis` y `respx`, aunque estaban declarados en el extra `dev`.
- **Commits intermedios en rojo.** El commit `bd537a8` (T1 de la spec 008) está en `main` con tests pero sin su implementación: por sí solo, la suite falla. Nadie lo detectó al subirlo.

Objetivo: que cada cambio que llegue al repositorio se compruebe automáticamente en una máquina limpia, con Python 3.11 y con las mismas versiones exactas de dependencias que se despliegan, y que el resultado sea visible en GitHub.

## Usuarios / actores

- **Desarrollador del scraper:** sube cambios y quiere saber, sin depender de su propio entorno, si rompen algo.
- **Evaluador del TFM:** quiere evidencia objetiva de que la versión desplegada está probada.
- **Sistema (GitHub Actions):** ejecuta las comprobaciones y publica el resultado en cada commit y PR.

## Historias de usuario

- **H1:** Como desarrollador, quiero que cada `push` y cada PR ejecuten lint, formato y tests automáticamente, para enterarme de un fallo antes de que llegue a `main` y no después.
- **H2:** Como desarrollador, quiero que esas comprobaciones usen Python 3.11 y las mismas versiones exactas de dependencias que la imagen Docker, para que "pasa en CI" signifique "funciona en producción".
- **H3:** Como desarrollador, quiero poder reproducir en local exactamente el entorno de CI con un solo comando, para investigar un fallo sin adivinar versiones.
- **H4:** Como evaluador del TFM, quiero ver en GitHub el resultado de cada commit de `main`, para comprobar que el código entregado pasa sus propios tests.

## Requisitos funcionales (criterios de aceptación en EARS)

### Versiones reproducibles

- **RF-1:** EL SISTEMA dispondrá de un lockfile versionado en el repositorio que fije la versión exacta de cada dependencia, directa y transitiva, de producción y del extra `dev`, resuelto a partir de `pyproject.toml`.
- **RF-2:** SI el lockfile no está sincronizado con `pyproject.toml` (se añade o cambia una dependencia sin regenerarlo), EL SISTEMA hará fallar la CI en lugar de instalar versiones distintas de las fijadas.
- **RF-3:** EL SISTEMA permitirá reproducir en local el entorno exacto de CI con un solo comando documentado.
- **RF-4:** La imagen Docker instalará las dependencias de producción desde el mismo lockfile (RF-1), sin el extra `dev`, de forma que la imagen desplegada lleva exactamente las versiones que ha probado la CI.
- **RF-5:** El lockfile inicial fijará las últimas versiones compatibles con `pyproject.toml` en el momento de generarlo (a 2026-09-30: `fastapi 0.142.2`, `starlette 1.7.0`), con las que ya se ha verificado que la suite pasa en Python 3.11.

### Pipeline de CI

- **RF-6:** CUANDO se haga `push` a `main` o se abra o actualice un PR contra `main`, EL SISTEMA ejecutará automáticamente la CI en GitHub Actions.
- **RF-7:** La CI usará únicamente Python 3.11, la misma versión menor que la imagen del `Dockerfile`, e instalará las dependencias exclusivamente desde el lockfile (RF-1).
- **RF-8:** La CI ejecutará, en este orden, `ruff check .`, `ruff format --check .` y la suite completa de `pytest` con cobertura sobre `app/`. SI cualquiera de los tres falla, EL SISTEMA marcará la ejecución como fallida.
- **RF-9:** SI la cobertura total de `app/` baja del 80%, EL SISTEMA marcará la ejecución como fallida (mismo umbral que los criterios de finalización de las specs 001-008).
- **RF-10:** La CI no necesitará secretos, credenciales ni servicios externos: sin Redis real, sin llamadas a Mercadona ni a Algolia (la suite ya usa `fakeredis` y `respx`, constitución #7), y con permisos de solo lectura sobre el repositorio.

### Visibilidad

- **RF-11:** El resultado de la CI será visible en GitHub junto a cada commit y cada PR, y `README.md` mostrará el estado de la CI de `main`.

## Requisitos no funcionales

- **Sin dependencias nuevas en la app:** la herramienta de lockfile es de desarrollo y CI; no añade nada a `dependencies` de producción (constitución #1).
- **Tiempo razonable:** una ejecución de CI no debería superar unos pocos minutos; la suite local tarda unos 15 s.
- **Mantenimiento mínimo:** actualizar dependencias es un paso explícito (regenerar el lockfile), nunca un efecto lateral de instalar.
- **Coste:** GitHub Actions en un repositorio público no tiene coste.

## Casos límite

- **Actualización de una dependencia que rompe algo:** el fallo aparece en el PR que regenera el lockfile, no en un `push` cualquiera de meses después.
- **Aviso de Starlette sobre `TestClient` con `httpx`:** con el lockfile, la versión queda fijada y el aviso es controlado; resolverlo (migrar a lo que Starlette recomiende) queda fuera de alcance.
- **PR desde un fork:** la CI se ejecuta igual, porque no necesita secretos (RF-10).
- **Commit intermedio en rojo dentro de un PR con varios commits:** la CI de un `push` solo prueba el último commit enviado. Un commit intermedio en rojo, como `bd537a8`, puede seguir colándose si se suben varios a la vez. Se acepta: la protección real es no fusionar un PR con la CI en rojo.

## Fuera de alcance

- **Despliegue continuo (CD):** construir y publicar la imagen Docker o desplegar automáticamente.
- **Protección de rama en GitHub** (impedir fusionar PRs con la CI en rojo): es configuración del repositorio en GitHub, no código. Se documenta como paso manual en el README.
- **Matriz de varias versiones de Python:** solo se prueba la que se despliega, 3.11 (RF-7). Probar también la versión local (3.14) duplicaría el tiempo de CI sin proteger nada desplegado hoy.
- **Análisis de seguridad de dependencias** (Dependabot, `pip-audit`) y actualización automática del lockfile.
- **Resolver el aviso de obsolescencia de Starlette.**

## Criterios de finalización

- Existe el lockfile y la CI instala desde él; modificar `pyproject.toml` sin regenerarlo hace fallar la CI (verificado en una rama de prueba).
- La imagen Docker se construye desde el lockfile y lleva las mismas versiones de producción que la CI (p. ej. `fastapi 0.142.2` dentro del contenedor), y su `HEALTHCHECK` sigue respondiendo.
- Un `push` a `main` ejecuta la CI en GitHub Actions con Python 3.11 y termina en verde con `ruff check`, `ruff format --check`, `pytest` y cobertura ≥80%.
- Un PR con un fallo deliberado (un test roto) termina en rojo y el fallo es visible en GitHub.
- `README.md` documenta el comando para reproducir el entorno de CI, muestra el estado de la CI y describe el paso manual de protección de rama.
- `ruff check .` y `ruff format .` sin errores; la suite completa sigue en verde.

## Dudas abiertas

Todas resueltas por el usuario el 2026-09-30:

1. ~~**¿El `Dockerfile` instala también desde el lockfile?**~~ — **RESUELTA: sí** (RF-4). Hoy hace `pip install .`, que resuelve versiones al construir la imagen, así que la CI probaría unas versiones y la imagen podría llevar otras. Es la única forma de que H2 se cumpla de verdad. Implica tocar el `Dockerfile` de la spec 005.
2. ~~**¿Solo Python 3.11, o también la versión local (3.14)?**~~ — **RESUELTA: solo 3.11** (RF-7). Es la que se despliega.
3. ~~**¿Qué versiones fija el lockfile inicial?**~~ — **RESUELTA: las últimas compatibles** al generarlo (RF-5), ya verificadas en 3.11. Se descarta fijar las del entorno local (`fastapi 0.139.2`).
