"""
Scraper de productos Mercadona
==============================
Busca productos en tienda.mercadona.es dado un código postal y un término de búsqueda.
Devuelve los resultados como JSON estructurado.

Estrategias disponibles (--strategy):
  api        — llamadas HTTP directas a la API interna (~15s)  [por defecto]
  playwright — automatización de navegador Chromium  (~30-60s)
  auto       — prueba API primero; si no encuentra resultados, usa Playwright

Uso:
    python cli.py --postal-code 28001 --product "leche entera"
    python cli.py --postal-code 28001 --product "leche" --strategy playwright
    python cli.py --postal-code 08001 --product yogur --output resultados.json
    python cli.py --postal-code 28001 --product pan --strategy playwright --no-headless

Dependencias:
    pip install requests playwright
    playwright install chromium
"""

import argparse
import json
import logging
import sys

try:
    import requests  # noqa: F401 — comprobación temprana de dependencia
except ImportError:
    sys.exit("ERROR: Falta la librería 'requests'. Ejecuta: pip install requests")

from .exceptions import MercadonaScraperError
from .scraper import MercadonaScraper


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scraper de productos Mercadona",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Estrategia API (por defecto, ~15s)
  python cli.py --postal-code 28001 --product "leche entera"

  # Estrategia Playwright — automatiza un navegador real (~30-60s)
  python cli.py --postal-code 28001 --product "leche" --strategy playwright

  # Playwright con navegador visible (útil para demostraciones del TFM)
  python cli.py --postal-code 08001 --product pan --strategy playwright --no-headless

  # Guardar resultado en fichero
  python cli.py --postal-code 46001 --product yogur --output resultados.json
        """,
    )
    parser.add_argument(
        "--postal-code",
        required=True,
        metavar="CP",
        help="Código postal español de 5 dígitos (ej: 28001)",
    )
    parser.add_argument(
        "--product",
        required=True,
        metavar="TERM",
        help="Término de búsqueda del producto (ej: 'leche entera')",
    )
    parser.add_argument(
        "--strategy",
        choices=["api", "playwright", "auto"],
        default="api",
        help="Estrategia de scraping: api (por defecto), playwright, auto",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Guardar resultado en un fichero JSON (por defecto: stdout)",
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Ejecutar Playwright en modo headless (usa --no-headless para mostrar la ventana)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Mostrar logs detallados de depuración",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    if not args.postal_code.isdigit() or len(args.postal_code) != 5:
        parser.error(
            f"--postal-code debe ser un número de exactamente 5 dígitos "
            f"(recibido: '{args.postal_code}')"
        )

    scraper = MercadonaScraper(
        postal_code=args.postal_code,
        term=args.product,
        headless=args.headless,
        strategy=args.strategy,
    )

    try:
        result = scraper.run()
    except (MercadonaScraperError, requests.RequestException) as exc:
        sys.exit(f"ERROR: {exc}")

    json_str = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)

    try:
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(json_str)
            print(
                f"Resultados guardados en: {args.output} "
                f"({result.search.total_results} productos)",
                file=sys.stderr,
            )
        else:
            print(json_str)
    except OSError as exc:
        sys.exit(f"ERROR: No se pudo escribir en '{args.output}': {exc}")


if __name__ == "__main__":
    main()
