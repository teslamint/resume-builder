"""Shared HTTP+JSON transport for API clients (Wanted, GroupBy, Remember).

Centralizes urllib Request construction, response reading, JSON parsing,
and error wrapping so each client only owns URL building + post-processing.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional


def http_json_request(
    url: str,
    *,
    headers: dict[str, str],
    timeout: int = 15,
    method: str = "GET",
    body: Optional[bytes] = None,
    error_cls: type[Exception] = Exception,
) -> dict:
    """Send an HTTP request and return parsed JSON.

    Raises *error_cls* on HTTP errors, URL errors, or JSON decode failures.
    """
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
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
