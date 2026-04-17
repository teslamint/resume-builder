"""GroupBy API client — centralized HTTP layer for api.groupby.kr.

Handles headers, pagination, response validation, and HTML→text conversion.
Used by both search_helpers (listing) and auto_extractors (detail).
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.request
import urllib.error
from typing import Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

GROUPBY_API_BASE = "https://api.groupby.kr"
GROUPBY_BASE_URL = "https://groupby.kr"
GROUPBY_HEADERS = {
    "Origin": GROUPBY_BASE_URL,
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
GROUPBY_MAX_LIMIT = 10
GROUPBY_REQUEST_TIMEOUT = 15


class GroupByAPIError(Exception):
    """Raised when the GroupBy API returns a non-200 status or unexpected shape."""


def _request(path: str, params: Optional[dict] = None) -> dict:
    """Make a GET request to the GroupBy API.

    Returns the parsed JSON response dict.
    Raises GroupByAPIError on non-200 status or missing data key.
    """
    url = f"{GROUPBY_API_BASE}{path}"
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"

    req = urllib.request.Request(url, headers=GROUPBY_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=GROUPBY_REQUEST_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            try:
                data = json.loads(body)
            except json.JSONDecodeError as e:
                raise GroupByAPIError(f"Invalid JSON response for {url}") from e
    except urllib.error.HTTPError as e:
        raise GroupByAPIError(f"HTTP {e.code} for {url}") from e
    except urllib.error.URLError as e:
        raise GroupByAPIError(f"URL error for {url}: {e.reason}") from e

    if data.get("status") != 200:
        raise GroupByAPIError(
            f"API status {data.get('status')}: {data.get('msg', 'unknown error')}"
        )
    if "data" not in data:
        raise GroupByAPIError(f"Missing 'data' key in response for {url}")

    return data["data"]


def fetch_positions(
    position_types: list[int],
    *,
    max_pages: int = 20,
    page_delay: float = 0.5,
) -> list[dict]:
    """Fetch all positions matching given position types.

    Automatically paginates (limit=10 per page).
    Returns the raw item dicts from the API.
    """
    all_items: list[dict] = []
    offset = 0

    params = {
        "isAdvertising": "false",
        "limit": GROUPBY_MAX_LIMIT,
        "orderBy": "-updatedAt",
        "positionTypes": ",".join(str(t) for t in position_types),
    }

    for page in range(max_pages):
        params["offset"] = offset
        try:
            data = _request("/startup-positions", params)
        except GroupByAPIError as e:
            logger.warning("GroupBy API error at offset %d: %s", offset, e)
            break

        items = data.get("items", [])
        total = data.get("total", 0)
        all_items.extend(items)

        if not items or offset + len(items) >= total:
            break

        offset += len(items)
        if page_delay > 0:
            time.sleep(page_delay)

    return all_items


def fetch_position_detail(position_id: int | str) -> dict:
    """Fetch a single position's full details."""
    return _request(f"/startup-positions/{position_id}")


def html_to_text(html: str | None) -> str:
    """Convert GroupBy HTML content to plain text.

    Handles <p>, <br/>, <li>, and strips remaining tags.
    """
    if not html:
        return ""

    text = html
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"</p>", "\n", text)
    text = re.sub(r"<p[^>]*>", "", text)
    text = re.sub(r"<li[^>]*>", "- ", text)
    text = re.sub(r"</li>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
