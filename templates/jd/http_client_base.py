"""Shared HTTP+JSON transport for API clients (Wanted, GroupBy, Remember).

Centralizes urllib Request construction, response reading, JSON parsing,
and error wrapping so each client only owns URL building + post-processing.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _merge_headers(headers: Optional[dict[str, str]]) -> dict[str, str]:
    merged = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        merged.update(headers)
    return merged


def http_text_request(
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    timeout: int = 15,
    max_bytes: int | None = None,
    method: str = "GET",
    body: Optional[bytes] = None,
    error_cls: type[Exception] | None = None,
) -> str:
    """Send an HTTP request and return decoded response text."""
    req = urllib.request.Request(
        url,
        data=body,
        headers=_merge_headers(headers),
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read(max_bytes) if max_bytes is not None else resp.read()
            if max_bytes is not None:
                resp_body = resp_body[:max_bytes]
            return resp_body.decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        if error_cls is None:
            raise
        raise error_cls(f"HTTP {e.code} for {url}") from e
    except urllib.error.URLError as e:
        if error_cls is None:
            raise
        raise error_cls(f"URL error for {url}: {e.reason}") from e


def http_json_request(
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    timeout: int = 15,
    method: str = "GET",
    body: Optional[bytes] = None,
    error_cls: type[Exception] = Exception,
) -> dict:
    """Send an HTTP request and return parsed JSON.

    Raises *error_cls* on HTTP errors, URL errors, or JSON decode failures.
    """
    req = urllib.request.Request(
        url,
        data=body,
        headers=_merge_headers(headers),
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8")
            try:
                return json.loads(resp_body)
            except json.JSONDecodeError as e:
                raise error_cls(f"Invalid JSON response for {url}") from e
    except urllib.error.HTTPError as e:
        raise error_cls(f"HTTP {e.code} for {url}") from e
    except urllib.error.URLError as e:
        raise error_cls(f"URL error for {url}: {e.reason}") from e
