"""
API key authentication middleware.

When API_KEY is set in the environment, every request (except /health and
/metrics which are safe for scraping) must include the header:

    X-API-Key: <value>

or the query parameter:

    ?api_key=<value>

If API_KEY is empty or unset, authentication is disabled (dev mode).
"""

from __future__ import annotations

import os

from fastapi import Request, HTTPException

_API_KEY = os.environ.get("API_KEY", "").strip()

# Endpoints that bypass auth — health checks and Prometheus scrapes
_PUBLIC_PATHS = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc"}


async def require_api_key(request: Request) -> None:
    """FastAPI dependency — raises 401 if auth is enabled and key is invalid."""
    if not _API_KEY:
        return  # Auth disabled

    if request.url.path in _PUBLIC_PATHS:
        return

    # WebSocket upgrade requests carry the key as a query param
    provided = (
        request.headers.get("X-API-Key")
        or request.query_params.get("api_key")
    )

    if provided != _API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
