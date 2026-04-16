"""Regression tests for GroupBy queueing and API error handling."""
from unittest.mock import patch

import pytest

from groupby_client import GroupByAPIError, _request
from search_helpers import RawJobResult, ScrapeOutcome
from search_quick import run_quick_search


class _DummyResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.payload


class _DummyBrowser:
    def new_context(self, **kwargs):
        return object()

    def close(self):
        return None


class _DummyChromium:
    def launch(self, **kwargs):
        return _DummyBrowser()


class _DummyPlaywright:
    chromium = _DummyChromium()


class _DummySyncPlaywright:
    def __enter__(self):
        return _DummyPlaywright()

    def __exit__(self, exc_type, exc, tb):
        return False


def test_request_wraps_json_decode_failure():
    with patch("urllib.request.urlopen", return_value=_DummyResponse(b"<html>proxy error</html>")):
        with pytest.raises(GroupByAPIError, match="Invalid JSON response"):
            _request("/startup-positions")


def test_run_quick_search_groupby_populates_queue_item_fields():
    config = {
        "search_queries": ["ignored"],
        "platforms": {
            "wanted": {"enabled": False},
            "remember": {"enabled": False},
            "groupby": {"enabled": True, "position_types": [2]},
        },
    }
    raw = RawJobResult(
        raw_id="8807",
        canonical_id="groupby-8807",
        title="Backend Engineer",
        company="GroupBy Co",
        experience="경력 3년 이상",
        url="https://groupby.kr/positions/8807",
        href="/positions/8807",
        platform="groupby",
    )
    outcome = ScrapeOutcome(results=[raw])

    with patch("search_quick.load_config", return_value=config), \
         patch("search_quick.get_rejected_companies", return_value=set()), \
         patch("search_quick.load_seen_ids", return_value=set()), \
         patch("search_quick.load_queue", return_value=[]), \
         patch("search_quick.groupby_fetch_positions", return_value=[{"id": 8807}]), \
         patch("search_quick.convert_groupby_to_raw_results", return_value=outcome), \
         patch("search_quick.groupby_experience_values", return_value=(3, None)), \
         patch("search_quick.is_duplicate", return_value=(False, None)), \
         patch("playwright.sync_api.sync_playwright", return_value=_DummySyncPlaywright()):
        items, stats = run_quick_search(dry_run=True)

    assert len(items) == 1
    assert items[0].job_id == "groupby-8807"
    assert items[0].experience == "경력 3년 이상"
    assert items[0].query == "(groupby)"
    assert items[0].platform == "groupby"
    assert stats["new"] == 1
