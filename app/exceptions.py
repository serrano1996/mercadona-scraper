class UpstreamUnavailableError(Exception):
    """Raised when Mercadona/Algolia is unreachable or keeps returning 5xx
    after MercadonaClient exhausts its retries (Decision D1/D2 in plan.md,
    RF-3). Lets the API layer (T15) map this to 502 without depending on
    httpx exception types leaking across the service boundary."""


class PostalCodeNotServedError(Exception):
    """Raised when Mercadona has no warehouse for a given postal_code (404
    from change-pc). Lets the API layer map this to 404 without depending
    on Mercadona's own error_msg (spec 007 RF-9, Decision D4 in plan.md)."""
