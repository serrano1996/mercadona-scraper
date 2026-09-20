"""API-key authentication for /api/v1/* (spec 004-mercadona-scraper-
authentication) — a shared token sent in the X-API-Key header, so only
our own apps can use the API, not third parties.
"""

import logging
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
    api_key: Annotated[str | None, Security(_api_key_header)] = None,
    settings: Annotated[Settings, Depends(_get_settings)] = None,  # type: ignore[assignment]
) -> None:
    # Token comparison against settings.api_keys lands in T3 (plan.md
    # Decision D3, constant-time via secrets.compare_digest); this task
    # (T2) only covers the missing/empty-header case (spec.md RF-2).
    if not api_key:
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED_DETAIL)
