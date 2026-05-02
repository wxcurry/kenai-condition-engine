"""HTTP client helper."""

from __future__ import annotations

import httpx

from kenai_engine.config import Settings


def build_http_client(settings: Settings) -> httpx.Client:
    """Build a configured HTTP client for future source adapters."""

    return httpx.Client(
        headers={"User-Agent": settings.user_agent},
        timeout=settings.fetch_timeout_seconds,
        follow_redirects=True,
    )
