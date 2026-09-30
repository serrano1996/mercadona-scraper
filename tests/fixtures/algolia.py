"""T4 — 008-mercadona-scraper-search-completeness: builds the body Mercadona's
Algolia backend returns for a search, so every test mocks the same shape
(Decision D6 in plan.md). Real responses always carry nbHits/nbPages
(verified live 2026-09-30, even for an out-of-range page), so the helper
always sets them too — defaulting to "all hits fit in one page".
"""


def algolia_response(
    hits: list[dict[str, object]], nb_hits: int | None = None, nb_pages: int = 1
) -> dict[str, object]:
    return {
        "results": [
            {
                "hits": hits,
                "nbHits": nb_hits if nb_hits is not None else len(hits),
                "nbPages": nb_pages,
            }
        ]
    }
