class UpstreamUnavailableError(Exception):
    """Raised when Mercadona/Algolia is unreachable or keeps returning 5xx
    after MercadonaClient exhausts its retries (Decision D1/D2 in plan.md,
    RF-3). Lets the API layer (T15) map this to 502 without depending on
    httpx exception types leaking across the service boundary."""
