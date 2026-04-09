"""Tests for search_helpers — RawJobResult, ScrapeOutcome, and scrape helpers."""
from unittest.mock import MagicMock, call

from search_helpers import (
    RawJobResult,
    SearchPageConfig,
    ScrapeOutcome,
    load_and_scrape_wanted,
    load_and_scrape_remember,
)


class TestRawJobResult:
    def test_wanted_duplicate_keys_single(self):
        r = RawJobResult(
            raw_id="12345", canonical_id="12345",
            title="T", company="C", experience="E",
            url="u", href="h", platform="wanted",
        )
        assert r.duplicate_keys() == ["12345"]

    def test_remember_duplicate_keys_dual(self):
        r = RawJobResult(
            raw_id="67890", canonical_id="remember-67890",
            title="T", company="C", experience="E",
            url="u", href="h", platform="remember",
        )
        keys = r.duplicate_keys()
        assert "remember-67890" in keys
        assert "67890" in keys
        assert len(keys) == 2


class TestScrapeOutcome:
    def test_default_values(self):
        o = ScrapeOutcome()
        assert o.results == []
        assert o.candidate_count == 0
        assert o.timed_out is False
        assert o.no_results is False
        assert o.error is None


def _make_wanted_page(*, timeout=False, no_results=False, links=None):
    """Create a mock page for Wanted search tests."""
    page = MagicMock()

    # Wanted uses chained locators: locator('a[href*="/wd/"]') and
    # locator('text=...').or_(locator(...)).or_(locator(...))
    # We simplify by making locator return a chainable mock

    has_locator = MagicMock()
    no_locator = MagicMock()

    # Chain .or_() calls on no_results locator
    no_locator.or_.return_value = no_locator  # Makes chaining work

    if timeout:
        combined = MagicMock()
        combined.wait_for.side_effect = Exception("timeout")
        has_locator.first.or_.return_value = combined
    elif no_results:
        combined = MagicMock()
        combined.wait_for.return_value = None
        has_locator.first.or_.return_value = combined
        no_locator.count.return_value = 1
        has_locator.count.return_value = 0
    else:
        combined = MagicMock()
        combined.wait_for.return_value = None
        has_locator.first.or_.return_value = combined
        no_locator.count.return_value = 0
        has_locator.count.return_value = 1

    def locator_fn(selector):
        if '/wd/' in selector:
            return has_locator
        return no_locator

    page.locator = MagicMock(side_effect=locator_fn)
    page.query_selector_all = MagicMock(return_value=links or [])
    page.evaluate = MagicMock()

    return page


def _make_remember_page(*, timeout=False, no_results=False, links=None):
    """Create a mock page for Remember search tests."""
    page = MagicMock()

    has_locator = MagicMock()
    no_locator = MagicMock()

    if timeout:
        combined = MagicMock()
        combined.wait_for.side_effect = Exception("timeout")
        has_locator.first.or_.return_value = combined
    elif no_results:
        combined = MagicMock()
        combined.wait_for.return_value = None
        has_locator.first.or_.return_value = combined
        no_locator.count.return_value = 1
        has_locator.count.return_value = 0
    else:
        combined = MagicMock()
        combined.wait_for.return_value = None
        has_locator.first.or_.return_value = combined
        no_locator.count.return_value = 0
        has_locator.count.return_value = 1

    def locator_fn(selector):
        if '/job/posting/' in selector:
            return has_locator
        return no_locator

    page.locator = MagicMock(side_effect=locator_fn)
    page.query_selector_all = MagicMock(return_value=links or [])
    page.evaluate = MagicMock()

    return page


class TestLoadAndScrapeWanted:
    def test_timeout(self):
        page = _make_wanted_page(timeout=True)
        config = SearchPageConfig(base_url="https://www.wanted.co.kr")
        outcome = load_and_scrape_wanted(page, "https://url", config)
        assert outcome.timed_out is True
        assert outcome.results == []

    def test_no_results(self):
        page = _make_wanted_page(no_results=True)
        config = SearchPageConfig(base_url="https://www.wanted.co.kr")
        outcome = load_and_scrape_wanted(page, "https://url", config)
        assert outcome.no_results is True

    def test_extracts_jobs(self):
        link = MagicMock()
        link.get_attribute.return_value = "/wd/12345?query=test"
        link.inner_text.return_value = "Senior Backend\nTestCo\n3년 이상"

        page = _make_wanted_page(links=[link])
        config = SearchPageConfig(
            base_url="https://www.wanted.co.kr",
            post_load_delay=0, scroll_count=0, scroll_sleep=0,
        )
        outcome = load_and_scrape_wanted(page, "https://url", config)

        assert len(outcome.results) == 1
        assert outcome.results[0].raw_id == "12345"
        assert outcome.results[0].canonical_id == "12345"
        assert outcome.results[0].title == "Senior Backend"
        assert outcome.results[0].company == "TestCo"
        assert outcome.results[0].platform == "wanted"
        assert outcome.candidate_count == 1

    def test_dedup_in_page(self):
        link1 = MagicMock()
        link1.get_attribute.return_value = "/wd/12345"
        link1.inner_text.return_value = "Title1\nCo1"
        link2 = MagicMock()
        link2.get_attribute.return_value = "/wd/12345"
        link2.inner_text.return_value = "Title1\nCo1"

        page = _make_wanted_page(links=[link1, link2])
        config = SearchPageConfig(
            base_url="https://www.wanted.co.kr",
            post_load_delay=0, scroll_count=0, scroll_sleep=0,
        )
        outcome = load_and_scrape_wanted(page, "https://url", config)
        assert len(outcome.results) == 1
        assert outcome.candidate_count == 1


class TestLoadAndScrapeRemember:
    def test_filters_jdViewSource(self):
        link_good = MagicMock()
        link_good.get_attribute.return_value = "/job/posting/111?jdViewSource=inweb_list"
        link_good.inner_text.return_value = "CompanyA\nTitle1\n3년 이상"

        link_bad = MagicMock()
        link_bad.get_attribute.return_value = "/job/posting/222"
        link_bad.inner_text.return_value = "CompanyB\nTitle2"

        page = _make_remember_page(links=[link_good, link_bad])
        config = SearchPageConfig(
            base_url="https://career.rememberapp.co.kr",
            post_load_delay=0, scroll_count=0, scroll_sleep=0,
        )
        outcome = load_and_scrape_remember(page, "https://url", config)
        assert len(outcome.results) == 1
        assert outcome.results[0].canonical_id == "remember-111"

    def test_remember_dual_key(self):
        link = MagicMock()
        link.get_attribute.return_value = "/job/posting/555?jdViewSource=inweb_list"
        link.inner_text.return_value = "CompanyX\nDeveloper\n경력 무관"

        page = _make_remember_page(links=[link])
        config = SearchPageConfig(
            base_url="https://career.rememberapp.co.kr",
            post_load_delay=0, scroll_count=0, scroll_sleep=0,
        )
        outcome = load_and_scrape_remember(page, "https://url", config)
        r = outcome.results[0]
        assert r.raw_id == "555"
        assert r.canonical_id == "remember-555"
        assert r.duplicate_keys() == ["remember-555", "555"]

    def test_remember_title_company_order(self):
        link = MagicMock()
        link.get_attribute.return_value = "/job/posting/999?jdViewSource=inweb_list"
        link.inner_text.return_value = "MyCompany\nSenior Dev\n5년 이상"

        page = _make_remember_page(links=[link])
        config = SearchPageConfig(
            base_url="https://career.rememberapp.co.kr",
            post_load_delay=0, scroll_count=0, scroll_sleep=0,
        )
        outcome = load_and_scrape_remember(page, "https://url", config)
        assert outcome.results[0].company == "MyCompany"
        assert outcome.results[0].title == "Senior Dev"

    def test_timeout(self):
        page = _make_remember_page(timeout=True)
        config = SearchPageConfig(base_url="https://career.rememberapp.co.kr")
        outcome = load_and_scrape_remember(page, "https://url", config)
        assert outcome.timed_out is True

    def test_error_captured(self):
        page = MagicMock()
        page.goto.side_effect = RuntimeError("network error")
        config = SearchPageConfig(base_url="https://career.rememberapp.co.kr")
        outcome = load_and_scrape_remember(page, "https://url", config)
        assert outcome.error is not None
        assert isinstance(outcome.error, RuntimeError)
