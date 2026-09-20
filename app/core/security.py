"""API-key authentication for /api/v1/* (spec 004-mercadona-scraper-
authentication) — a shared token sent in the X-API-Key header, so only
our own apps can use the API, not third parties.
"""

import logging
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from app.core.config import Settings

logger = logging.getLogger(__name__)

_UNAUTHORIZED_DETAIL = "Missing or invalid API key"

# auto_error=False: gives us None instead of raising, so a single function
# (verify_api_key) decides the status code/body for both "missing" and
# "invalid" cases (plan.md Decision D2) — keeps RF-2/RF-3 identical.
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_settings(request: Request) -> Settings:
    return request.app.state.settings


def verify_api_key(
    request: Request,
    api_key: Annotated[str | None, Security(_api_key_header)] = None,
    settings: Annotated[Settings, Depends(_get_settings)] = None,  # type: ignore[assignment]
) -> None:
    # secrets.compare_digest per candidate token (plan.md Decision D3):
    # constant-time, so a mismatch doesn't leak timing information about
    # how many leading characters matched (RF-4). Same 401/detail for
    # "missing" and "invalid" (RF-2/RF-3) — no hint to a guesser.
    if not api_key or not any(
        secrets.compare_digest(api_key, valid_key) for valid_key in settings.api_keys
    ):
        # Never log `api_key` itself (plan.md Decision D5, spec.md RF-6) —
        # only the path, same as T7-T9 of spec 003 never logging secrets.
        logger.warning("Rejected unauthenticated request to %s", request.url.path)
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED_DETAIL)
