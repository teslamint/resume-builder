"""Remember API client — centralized HTTP layer for career-api.rememberapp.co.kr.

Handles pagination, response validation, and experience formatting.
Uses POST-based search (unlike Wanted/GroupBy which use GET).
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

REMEMBER_API_BASE = "https://career-api.rememberapp.co.kr"
REMEMBER_BASE_URL = "https://career.rememberapp.co.kr"
REMEMBER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": REMEMBER_BASE_URL,
    "Referer": f"{REMEMBER_BASE_URL}/",
}
REMEMBER_DEFAULT_PER_PAGE = 30
REMEMBER_REQUEST_TIMEOUT = 15


class RememberAPIError(Exception):
    """Raised when the Remember API returns a non-200 status or unexpected shape."""


def _request_post(path: str, body: dict) -> dict:
    url = f"{REMEMBER_API_BASE}{path}"
    data_bytes = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=REMEMBER_HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=REMEMBER_REQUEST_TIMEOUT) as resp:
            resp_body = resp.read().decode("utf-8")
            try:
                data = json.loads(resp_body)
            except json.JSONDecodeError as e:
                raise RememberAPIError(f"Invalid JSON response for {url}") from e
    except urllib.error.HTTPError as e:
        raise RememberAPIError(f"HTTP {e.code} for {url}") from e
    except urllib.error.URLError as e:
        raise RememberAPIError(f"URL error for {url}: {e.reason}") from e

    return data


def search_jobs(
    keywords: list[str],
    *,
    max_items: int = 60,
    per_page: int = REMEMBER_DEFAULT_PER_PAGE,
    page_delay: float = 0.5,
) -> tuple[list[dict], int]:
    """Search Remember jobs by keywords with automatic pagination.

    Returns (raw item dicts, total_count) from the API.
    """
    all_items: list[dict] = []
    page = 1
    total_count = 0

    while len(all_items) < max_items:
        body = {
            "page": page,
            "per": per_page,
            "search": {"keywords": keywords},
        }

        try:
            data = _request_post("/job_postings/search", body)
        except RememberAPIError as e:
            logger.warning("Remember API error at page %d: %s", page, e)
            break

        items = data.get("data", [])
        meta = data.get("meta", {})
        total_count = meta.get("total_count", 0)
        total_pages = meta.get("total_pages", 1)

        if not items:
            break

        all_items.extend(items)

        if page >= total_pages:
            break

        page += 1
        if page_delay > 0 and len(all_items) < max_items:
            time.sleep(page_delay)

    return all_items[:max_items], total_count


def format_experience(item: dict) -> str:
    """Convert Remember API item to display-only Korean experience string.

    API fields: min_experience (int|null), max_experience (int|null).
    """
    min_year = item.get("min_experience")
    max_year = item.get("max_experience")

    if min_year is not None and max_year is not None:
        if min_year == 0 and max_year == 0:
            return "경력 무관"
        if min_year == 0:
            return f"신입~{max_year}년"
        return f"경력 {min_year}~{max_year}년"

    if min_year is not None and min_year > 0:
        return f"경력 {min_year}년 이상"

    return ""


def experience_values(item: dict) -> tuple[int | None, int | None]:
    """Extract structured (min_years, max_years) from Remember API item."""
    min_year = item.get("min_experience")
    max_year = item.get("max_experience")

    if min_year == 0 and max_year == 0:
        return None, None

    return (
        min_year if min_year and min_year > 0 else None,
        max_year if max_year and max_year > 0 else None,
    )
