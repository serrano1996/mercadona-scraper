import asyncio
import logging
import re
from urllib.parse import quote

from ..config import BASE_URL, HEADERS
from .base import SearchStrategy

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None
    PlaywrightError = Exception
    PlaywrightTimeoutError = Exception

# Timeouts (ms)
NAV_TIMEOUT_MS = 45000
POST_NAV_SETTLE_MS = 2000
POST_MODAL_SETTLE_MS = 1500
SEARCH_URL_SETTLE_MS = 3000
SEARCH_SUBMIT_WAIT_MS = 3000
PRODUCT_CARDS_TIMEOUT_MS = 8000
POSTAL_INPUT_VISIBLE_TIMEOUT_MS = 2500
POSTAL_MODAL_HIDDEN_TIMEOUT_MS = 5000
POSTAL_MODAL_HIDDEN_FALLBACK_WAIT_MS = 2500
SEARCH_ICON_VISIBLE_TIMEOUT_MS = 1500
SEARCH_ICON_CLICK_WAIT_MS = 800
SEARCH_INPUT_VISIBLE_TIMEOUT_MS = 2000

# Límite de tarjetas DOM a parsear: Mercadona pagina/virtualiza resultados,
# así que tarjetas extra suelen ser ruido fuera de viewport y solo ralentizan el parseo.
MAX_DOM_CARDS = 60

PRODUCT_CARD_SELECTOR = (
    '[data-testid*="product"], [data-testid*="card"], '
    '.product-cell, article[class*="product" i], li[class*="product" i]'
)

POSTAL_INPUT_SELECTORS = [
    'input[data-testid*="postal"]',
    'input[placeholder*="código postal" i]',
    'input[placeholder*="código" i]',
    'input[name="cp"]',
    'dialog input[type="text"]',
    '[role="dialog"] input[type="text"]',
]

SEARCH_INPUT_SELECTORS = [
    '[data-testid*="search"] input',
    'input[type="search"]',
    'input[placeholder*="buscar" i]',
    'input[aria-label*="buscar" i]',
    'input[placeholder*="Buscar" i]',
]

SEARCH_ICON_SELECTORS = [
    '[data-testid*="search-icon"]',
    '[aria-label*="buscar" i]',
    'button[class*="search" i]',
    '[class*="SearchIcon"]',
]

CARD_SELECTORS = [
    '[data-testid="product-cell"]',
    ".product-cell",
    'article[class*="product" i]',
    'li[class*="product" i]',
    '[class*="ProductCard" i]',
]


class PlaywrightStrategy(SearchStrategy):

    _PRICE_RE = re.compile(r"(\d{1,4}[.,]\d{2})\s?€")

    def __init__(self, term: str, postal_code: str, headless: bool = True):
        self._term = term
        self._postal_code = postal_code
        self._headless = headless
        self._captured: list[dict] = []

    def search(self, warehouse: str) -> list[dict]:  # noqa: ARG002
        return asyncio.run(self._async_search())

    async def _async_search(self) -> list[dict]:
        if async_playwright is None:
            raise ImportError(
                "Playwright no está instalado. Ejecuta:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        self._captured = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self._headless)
            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="es-ES",
                extra_http_headers={"Accept-Language": "es-ES,es;q=0.9"},
            )
            page = await context.new_page()
            page.on("response", self._handle_network_response)
            await self._navigate_and_search(page)
            if not self._captured:
                logger.debug("Playwright: sin datos de red, intentando extracción DOM")
                self._captured = await self._extract_dom(page)
            await browser.close()

        logger.debug(f"Playwright: {len(self._captured)} productos capturados")
        return self._captured

    async def _handle_network_response(self, response) -> None:
        if response.status != 200:
            logger.debug(f"Playwright red: respuesta {response.status} ignorada ({response.url})")
            return
        url = response.url
        if "/api/categories/" in url and "lang=es" in url:
            await self._parse_categories_response(response, url)
        elif "algolia.net/1/indexes" in url:
            await self._parse_algolia_response(response, url)

    async def _parse_categories_response(self, response, url: str) -> None:
        try:
            data = await response.json()
        except (PlaywrightError, ValueError) as exc:
            logger.debug(f"Playwright interceptor error en {url}: {exc}")
            return
        self._collect_from_categories(data, self._term.lower())

    async def _parse_algolia_response(self, response, url: str) -> None:
        try:
            data = await response.json()
        except (PlaywrightError, ValueError) as exc:
            logger.debug(f"Playwright interceptor error en {url}: {exc}")
            return
        self._collect_from_algolia(data, self._term.lower())

    def _maybe_capture(self, product: dict, term_lower: str, category_name: str) -> None:
        if term_lower in product.get("display_name", "").lower():
            product["_category_name"] = category_name
            self._captured.append(product)

    def _collect_from_categories(self, data: dict, term_lower: str) -> None:
        for sub_cat in data.get("categories", []):
            cat_name = sub_cat.get("name", "")
            for product in sub_cat.get("products", []):
                self._maybe_capture(product, term_lower, cat_name)

    def _collect_from_algolia(self, data: dict, term_lower: str) -> None:
        for result in data.get("results", []):
            for hit in result.get("hits", []):
                cats = hit.get("categories", [])
                cat_name = cats[0]["name"] if cats else ""
                self._maybe_capture(hit, term_lower, cat_name)

    async def _navigate_and_search(self, page) -> None:
        logger.debug("Playwright: navegando a tienda.mercadona.es")
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        await page.wait_for_timeout(POST_NAV_SETTLE_MS)
        await self._handle_postal_modal(page)
        await page.wait_for_timeout(POST_MODAL_SETTLE_MS)
        if not await self._do_search(page):
            search_url = f"{BASE_URL}/search?q={quote(self._term)}"
            logger.debug(f"Playwright: navegando a URL de búsqueda {search_url}")
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(SEARCH_URL_SETTLE_MS)
        try:
            await page.wait_for_selector(PRODUCT_CARD_SELECTOR, timeout=PRODUCT_CARDS_TIMEOUT_MS)
            logger.debug("Playwright: tarjetas de producto detectadas en DOM")
        except PlaywrightTimeoutError:
            logger.debug("Playwright: timeout esperando tarjetas — puede que no haya resultados")

    async def _handle_postal_modal(self, page) -> None:
        for selector in POSTAL_INPUT_SELECTORS:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=POSTAL_INPUT_VISIBLE_TIMEOUT_MS):
                    logger.debug(f"Playwright: modal CP detectado ({selector})")
                    await el.fill(self._postal_code)
                    await el.press("Enter")
                    try:
                        await page.locator(selector).wait_for(
                            state="hidden", timeout=POSTAL_MODAL_HIDDEN_TIMEOUT_MS
                        )
                    except PlaywrightTimeoutError:
                        await page.wait_for_timeout(POSTAL_MODAL_HIDDEN_FALLBACK_WAIT_MS)
                    logger.debug("Playwright: modal CP resuelto")
                    return
            except (PlaywrightError, PlaywrightTimeoutError):
                continue
        logger.debug("Playwright: no se detectó modal de CP")

    async def _do_search(self, page) -> bool:
        for icon_sel in SEARCH_ICON_SELECTORS:
            try:
                icon = page.locator(icon_sel).first
                if await icon.is_visible(timeout=SEARCH_ICON_VISIBLE_TIMEOUT_MS):
                    await icon.click()
                    await page.wait_for_timeout(SEARCH_ICON_CLICK_WAIT_MS)
                    break
            except (PlaywrightError, PlaywrightTimeoutError):
                continue
        for selector in SEARCH_INPUT_SELECTORS:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=SEARCH_INPUT_VISIBLE_TIMEOUT_MS):
                    logger.debug(f"Playwright: buscador encontrado ({selector})")
                    await el.fill(self._term)
                    await el.press("Enter")
                    await page.wait_for_timeout(SEARCH_SUBMIT_WAIT_MS)
                    return True
            except (PlaywrightError, PlaywrightTimeoutError):
                continue
        logger.debug("Playwright: buscador no encontrado en la UI")
        return False

    async def _extract_dom(self, page) -> list[dict]:
        cards = await self._find_cards(page)
        if cards is None:
            return []
        count = await cards.count()
        logger.debug(f"Playwright DOM: {count} tarjetas encontradas")
        products: list[dict] = []
        term_lower = self._term.lower()
        for i in range(min(count, MAX_DOM_CARDS)):
            try:
                result = await self._parse_card(cards.nth(i), term_lower)
                if result:
                    products.append(result)
            except (PlaywrightError, PlaywrightTimeoutError, ValueError, TypeError) as exc:
                logger.debug(f"Playwright DOM card[{i}]: {exc}")
        return products

    async def _find_cards(self, page):
        for selector in CARD_SELECTORS:
            locator = page.locator(selector)
            if await locator.count() > 0:
                logger.debug(f"Playwright DOM: tarjetas con selector '{selector}'")
                return locator
        logger.debug("Playwright DOM: sin tarjetas de producto")
        return None

    async def _parse_card(self, card, term_lower: str) -> dict | None:
        card_text = await card.inner_text()
        lines = [ln.strip() for ln in card_text.split("\n") if ln.strip()]
        name = lines[0] if lines else ""
        if term_lower not in name.lower():
            return None
        price = self._parse_price(lines)
        image_url = await self._card_image(card)
        product_id = await self._card_id(card)
        return {
            "id": product_id,
            "display_name": name,
            "_category_name": "",
            "price_instructions": {
                "unit_price": str(price),
                "bulk_price": str(price),
                "reference_price": str(price),
                "reference_format": "",
            },
            "thumbnail": image_url,
            "categories": [],
        }

    @classmethod
    def _parse_price(cls, lines: list[str]) -> float:
        for line in lines:
            m = cls._PRICE_RE.search(line)
            if m:
                return float(m.group(1).replace(",", "."))
        return 0.0

    @staticmethod
    async def _card_image(card) -> str:
        img = card.locator("img").first
        if await img.count() > 0:
            return await img.get_attribute("src") or ""
        return ""

    @staticmethod
    async def _card_id(card) -> str:
        for attr in ["data-id", "data-product-id"]:
            val = await card.get_attribute(attr)
            if val:
                return str(val)
        link = card.locator("a[href*='/product/']").first
        if await link.count() > 0:
            href = await link.get_attribute("href") or ""
            m = re.search(r"/product/(\d+)/", href)
            if m:
                return m.group(1)
        return ""
