"""Tests for extract_company_info orchestration logic.

These tests monkeypatch platform extractors to verify the orchestrator's
error handling, platform ordering, and JD-always-attempted behavior
without needing a real browser.

Note: HTTP_EXTRACTORS / BROWSER_EXTRACTORS capture function references at
module load time, so we must patch the dict itself (not module-level names).
"""
from unittest.mock import MagicMock, patch

from ce_types import PlatformData
from company_extractor import BROWSER_EXTRACTORS, HTTP_EXTRACTORS, extract_company_info


def _make_platform_data(platform: str) -> PlatformData:
    return PlatformData(
        platform=platform,
        source_url=f"https://example.com/{platform}",
        company_name="테스트회사",
    )


def _make_mock(val):
    if isinstance(val, Exception):
        return MagicMock(side_effect=val)
    return MagicMock(return_value=val)


class TestBrowserExtractorsOrder:
    """Verify BROWSER_EXTRACTORS dict maintains expected insertion order."""

    def test_platform_order(self):
        assert list(HTTP_EXTRACTORS.keys()) == ["wanted"]
        assert list(BROWSER_EXTRACTORS.keys()) == ["saramin", "thevc"]


class TestExtractCompanyInfoOrchestration:
    """Test the orchestrator loop behavior."""

    def test_success_case(self):
        wanted_data = _make_platform_data("wanted")
        mock_http_extractors = {
            "wanted": _make_mock(wanted_data),
        }

        with patch.dict("company_extractor.HTTP_EXTRACTORS", mock_http_extractors, clear=True), \
             patch.dict("company_extractor.BROWSER_EXTRACTORS", {}, clear=True), \
             patch("company_extractor.extract_from_jd_files", return_value=None):
            result = extract_company_info(
                "테스트회사",
                platforms=["wanted"],
                dry_run=True,
            )

        assert "wanted" in result.platforms_used
        assert "wanted" not in result.platforms_failed

    def test_none_result_goes_to_failed(self):
        mock_http_extractors = {
            "wanted": _make_mock(None),
        }

        with patch.dict("company_extractor.HTTP_EXTRACTORS", mock_http_extractors, clear=True), \
             patch.dict("company_extractor.BROWSER_EXTRACTORS", {}, clear=True), \
             patch("company_extractor.extract_from_jd_files", return_value=None):
            result = extract_company_info(
                "테스트회사",
                platforms=["wanted"],
                dry_run=True,
            )

        assert "wanted" in result.platforms_failed
        assert result.completeness == 0.0

    def test_exception_goes_to_failed_no_crash(self):
        mock_http_extractors = {
            "wanted": _make_mock(RuntimeError("network error")),
        }

        with patch.dict("company_extractor.HTTP_EXTRACTORS", mock_http_extractors, clear=True), \
             patch.dict("company_extractor.BROWSER_EXTRACTORS", {}, clear=True), \
             patch("company_extractor.extract_from_jd_files", return_value=None):
            result = extract_company_info(
                "테스트회사",
                platforms=["wanted"],
                dry_run=True,
            )

        assert "wanted" in result.platforms_failed

    def test_jd_always_attempted_even_when_all_browser_fail(self):
        jd_data = _make_platform_data("jd")
        mock_http_extractors = {
            "wanted": _make_mock(RuntimeError("fail")),
        }
        mock_browser_extractors = {
            "saramin": _make_mock(RuntimeError("fail")),
            "thevc": _make_mock(RuntimeError("fail")),
        }

        with patch.dict("company_extractor.HTTP_EXTRACTORS", mock_http_extractors, clear=True), \
             patch.dict("company_extractor.BROWSER_EXTRACTORS", mock_browser_extractors, clear=True), \
             patch("company_extractor.extract_from_jd_files", return_value=jd_data):
            result = extract_company_info(
                "테스트회사",
                browser_context=MagicMock(),
                platforms=["wanted", "saramin", "thevc"],
                dry_run=True,
            )

        assert "jd" in result.platforms_used
        assert all(p in result.platforms_failed for p in ["wanted", "saramin", "thevc"])

    def test_unrecognized_platforms_skip_browser_extractors(self):
        """When platforms list contains no known browser platforms,
        none of the browser extractors should be called."""
        jd_data = _make_platform_data("jd")
        m_saramin = _make_mock(None)
        m_thevc = _make_mock(None)
        mock_http_extractors = {
            "wanted": _make_mock(None),
        }
        mock_browser_extractors = {
            "saramin": m_saramin,
            "thevc": m_thevc,
        }

        with patch.dict("company_extractor.HTTP_EXTRACTORS", mock_http_extractors, clear=True), \
             patch.dict("company_extractor.BROWSER_EXTRACTORS", mock_browser_extractors, clear=True), \
             patch("company_extractor.extract_from_jd_files", return_value=jd_data):
            result = extract_company_info(
                "테스트회사",
                browser_context=MagicMock(),
                platforms=["nonexistent_platform"],
                dry_run=True,
            )

        assert "jd" in result.platforms_used
        m_saramin.assert_not_called()
        m_thevc.assert_not_called()

    def test_wanted_http_runs_without_browser_context(self):
        wanted_data = _make_platform_data("wanted")
        mock_http_extractors = {
            "wanted": _make_mock(wanted_data),
        }

        with patch.dict("company_extractor.HTTP_EXTRACTORS", mock_http_extractors, clear=True), \
             patch.dict("company_extractor.BROWSER_EXTRACTORS", {}, clear=True), \
             patch("company_extractor.extract_from_jd_files", return_value=None):
            result = extract_company_info(
                "테스트회사",
                platforms=["wanted"],
                dry_run=True,
            )

        assert result.platforms_used == ["wanted"]

    def test_browser_only_failures_do_not_block_wanted_http(self):
        wanted_data = _make_platform_data("wanted")
        mock_http_extractors = {
            "wanted": _make_mock(wanted_data),
        }
        mock_browser_extractors = {
            "saramin": _make_mock(RuntimeError("browser fail")),
            "thevc": _make_mock(RuntimeError("browser fail")),
        }

        with patch.dict("company_extractor.HTTP_EXTRACTORS", mock_http_extractors, clear=True), \
             patch.dict("company_extractor.BROWSER_EXTRACTORS", mock_browser_extractors, clear=True), \
             patch("company_extractor.extract_from_jd_files", return_value=None):
            result = extract_company_info(
                "테스트회사",
                browser_context=MagicMock(),
                platforms=["wanted", "saramin", "thevc"],
                dry_run=True,
            )

        assert "wanted" in result.platforms_used
        assert "saramin" in result.platforms_failed
        assert "thevc" in result.platforms_failed


class TestHttpFallbackAfterBrowserFailure:
    """Test per-platform HTTP fallback when browser extraction fails."""

    def test_http_fallback_on_browser_none(self):
        """When browser extractor returns None, HTTP fallback should recover."""
        http_data = _make_platform_data("wanted")
        mock_browser = {"wanted": _make_mock(None), "saramin": _make_mock(None), "thevc": _make_mock(None)}
        mock_http = {"wanted": _make_mock(http_data)}

        with patch.dict("company_extractor.BROWSER_EXTRACTORS", mock_browser), \
             patch.dict("company_extractor.HTTP_EXTRACTORS", mock_http), \
             patch("company_extractor.extract_from_jd_files", return_value=None):
            result = extract_company_info(
                "테스트회사",
                browser_context=MagicMock(),
                platforms=["wanted"],
                dry_run=True,
            )

        assert "wanted" in result.platforms_used
        assert "wanted" not in result.platforms_failed

    def test_http_fallback_on_browser_exception(self):
        """When browser extractor raises, HTTP fallback should recover."""
        http_data = _make_platform_data("wanted")
        mock_browser = {"wanted": _make_mock(RuntimeError("timeout")), "saramin": _make_mock(None), "thevc": _make_mock(None)}
        mock_http = {"wanted": _make_mock(http_data)}

        with patch.dict("company_extractor.BROWSER_EXTRACTORS", mock_browser), \
             patch.dict("company_extractor.HTTP_EXTRACTORS", mock_http), \
             patch("company_extractor.extract_from_jd_files", return_value=None):
            result = extract_company_info(
                "테스트회사",
                browser_context=MagicMock(),
                platforms=["wanted"],
                dry_run=True,
            )

        assert "wanted" in result.platforms_used
        assert "wanted" not in result.platforms_failed

    def test_no_http_fallback_for_saramin(self):
        """Saramin has no HTTP fallback, should stay in platforms_failed."""
        mock_browser = {"wanted": _make_mock(None), "saramin": _make_mock(None), "thevc": _make_mock(None)}

        with patch.dict("company_extractor.BROWSER_EXTRACTORS", mock_browser), \
             patch.dict("company_extractor.HTTP_EXTRACTORS", {}), \
             patch("company_extractor.extract_from_jd_files", return_value=None):
            result = extract_company_info(
                "테스트회사",
                browser_context=MagicMock(),
                platforms=["saramin"],
                dry_run=True,
            )

        assert "saramin" in result.platforms_failed

    def test_http_fallback_not_called_when_browser_succeeds(self):
        """When browser extraction succeeds, per-platform HTTP fallback should not re-call."""
        browser_data = _make_platform_data("wanted")
        http_mock = _make_mock(_make_platform_data("wanted"))
        mock_browser = {"wanted": _make_mock(browser_data)}
        mock_http = {"wanted": http_mock}

        with patch.dict("company_extractor.BROWSER_EXTRACTORS", mock_browser, clear=True), \
             patch.dict("company_extractor.HTTP_EXTRACTORS", mock_http, clear=True), \
             patch("company_extractor.extract_from_jd_files", return_value=None):
            result = extract_company_info(
                "테스트회사",
                browser_context=MagicMock(),
                platforms=["wanted"],
                dry_run=True,
            )

        assert "wanted" in result.platforms_used
        assert http_mock.call_count == 1
