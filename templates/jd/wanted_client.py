"""Wanted API client — centralized HTTP layer for www.wanted.co.kr/api/v4.

Handles pagination, response validation, and experience formatting.
Used by search_helpers (listing) and potentially auto_extractors (detail).
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
from typing import Optional
from urllib.parse import urlencode

try:
    from .http_client_base import http_json_request, http_text_request
except ImportError:
    from http_client_base import http_json_request, http_text_request

logger = logging.getLogger(__name__)

WANTED_API_BASE = "https://www.wanted.co.kr/api/v4"
WANTED_BASE_URL = "https://www.wanted.co.kr"
WANTED_HEADERS = {
    "Accept": "application/json",
    "Referer": f"{WANTED_BASE_URL}/",
}
WANTED_DEFAULT_LIMIT = 20
WANTED_REQUEST_TIMEOUT = 15


class WantedAPIError(Exception):
    """Raised when the Wanted API returns a non-200 status or unexpected shape."""


def _request(path: str, params: Optional[dict] = None) -> dict:
    url = f"{WANTED_API_BASE}{path}"
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"
    return http_json_request(
        url, headers=WANTED_HEADERS, timeout=WANTED_REQUEST_TIMEOUT,
        error_cls=WantedAPIError,
    )


def search_jobs(
    query: str,
    *,
    max_items: int = 60,
    page_delay: float = 0.5,
    country: str = "kr",
    years: int = -1,
) -> list[dict]:
    """Search Wanted jobs by keyword with automatic pagination.

    Returns raw item dicts from the API (up to max_items).
    """
    all_items: list[dict] = []
    offset = 0

    params = {
        "country": country,
        "search": query,
        "job_sort": "job.latest_order",
        "locations": "all",
        "years": years,
        "limit": WANTED_DEFAULT_LIMIT,
    }

    while len(all_items) < max_items:
        params["offset"] = offset
        try:
            data = _request("/jobs", params)
        except WantedAPIError as e:
            if not all_items:
                raise
            logger.warning("Wanted API error at offset %d (returning %d partial items): %s", offset, len(all_items), e)
            break

        items = data.get("data", [])
        if not items:
            break

        all_items.extend(items)
        offset += len(items)

        if not data.get("links", {}).get("next"):
            break

        if page_delay > 0 and len(all_items) < max_items:
            time.sleep(page_delay)

    return all_items[:max_items]


def _fetch_html(url: str) -> str:
    try:
        return http_text_request(
            url,
            headers={
                **WANTED_HEADERS,
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=WANTED_REQUEST_TIMEOUT,
        )
    except urllib.error.HTTPError as e:
        raise WantedAPIError(f"HTTP {e.code} for {url}") from e
    except urllib.error.URLError as e:
        raise WantedAPIError(f"URL error for {url}: {e.reason}") from e


def search_company(name: str) -> tuple[str, str] | None:
    """Search Wanted for a company by name. Returns (id, matched_name) or None."""
    data = _request("/search", {"query": name, "type": "company", "country": "kr"})
    companies = data.get("data", {}).get("companies", [])
    if not companies:
        return None
    first = companies[0]
    return str(first["id"]), first.get("name", name)


def fetch_company_html(company_id: str) -> str:
    """Fetch Wanted company page HTML (SSR, includes __NEXT_DATA__)."""
    return _fetch_html(f"{WANTED_BASE_URL}/company/{company_id}")


def format_experience(item: dict) -> str:
    """Convert Wanted API item to display-only Korean experience string."""
    annual_from = item.get("annual_from")
    annual_to = item.get("annual_to")

    if annual_from is not None and annual_to is not None:
        if annual_from == 0 and annual_to == 0:
            return "신입"
        if annual_from == 0:
            return f"신입~{annual_to}년"
        return f"{annual_from}~{annual_to}년"

    if annual_from is not None and annual_from > 0:
        return f"{annual_from}년 이상"

    return ""


def experience_values(item: dict) -> tuple[int | None, int | None]:
    """Extract structured (min_years, max_years) from Wanted API item."""
    annual_from = item.get("annual_from")
    annual_to = item.get("annual_to")

    if annual_from == 0 and annual_to == 0:
        return 0, 0

    return (
        annual_from if annual_from and annual_from > 0 else None,
        annual_to if annual_to and annual_to > 0 else None,
    )
