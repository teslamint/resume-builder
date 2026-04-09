"""Tests for extract_company_info orchestration logic.

These tests monkeypatch platform extractors to verify the orchestrator's
error handling, platform ordering, and JD-always-attempted behavior
without needing a real browser.
"""
from unittest.mock import MagicMock, patch

from ce_types import PlatformData
from company_extractor import extract_company_info


def _make_platform_data(platform: str) -> PlatformData:
    return PlatformData(
        platform=platform,
        source_url=f"https://example.com/{platform}",
        company_name="테스트회사",
    )


def _patch_all(wanted=None, saramin=None, thevc=None, jd=None):
    """Create a combined context manager that patches all 4 extractors."""
    def _to_mock(val):
        if callable(val) and isinstance(val, type) and issubclass(val, Exception):
            return MagicMock(side_effect=val("error"))
        if isinstance(val, Exception):
            return MagicMock(side_effect=val)
        return MagicMock(return_value=val)

    return (
        patch("company_extractor._extract_wanted", _to_mock(wanted)),
        patch("company_extractor._extract_saramin", _to_mock(saramin)),
        patch("company_extractor._extract_thevc", _to_mock(thevc)),
        patch("company_extractor._extract_from_jd_files", _to_mock(jd)),
    )


class TestExtractCompanyInfoOrchestration:
    """Test the orchestrator loop behavior."""

    def test_success_case(self):
        wanted_data = _make_platform_data("wanted")
        p1, p2, p3, p4 = _patch_all(wanted=wanted_data, jd=None)

        with p1, p2, p3, p4:
            result = extract_company_info(
                "테스트회사",
                browser_context=MagicMock(),
                platforms=["wanted"],
                dry_run=True,
            )

        assert "wanted" in result.platforms_used
        assert "wanted" not in result.platforms_failed

    def test_none_result_goes_to_failed(self):
        p1, p2, p3, p4 = _patch_all(wanted=None, jd=None)

        with p1, p2, p3, p4:
            result = extract_company_info(
                "테스트회사",
                browser_context=MagicMock(),
                platforms=["wanted"],
                dry_run=True,
            )

        assert "wanted" in result.platforms_failed
        assert result.completeness == 0.0

    def test_exception_goes_to_failed_no_crash(self):
        p1, p2, p3, p4 = _patch_all(
            wanted=RuntimeError("network error"), jd=None
        )

        with p1, p2, p3, p4:
            result = extract_company_info(
                "테스트회사",
                browser_context=MagicMock(),
                platforms=["wanted"],
                dry_run=True,
            )

        assert "wanted" in result.platforms_failed

    def test_jd_always_attempted_even_when_all_browser_fail(self):
        jd_data = _make_platform_data("jd")
        p1, p2, p3, p4 = _patch_all(
            wanted=RuntimeError("fail"),
            saramin=RuntimeError("fail"),
            thevc=RuntimeError("fail"),
            jd=jd_data,
        )

        with p1, p2, p3, p4:
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
        p1, p2, p3, p4 = _patch_all(jd=jd_data)

        with p1 as m1, p2 as m2, p3 as m3, p4:
            result = extract_company_info(
                "테스트회사",
                browser_context=MagicMock(),
                platforms=["nonexistent_platform"],
                dry_run=True,
            )

        assert "jd" in result.platforms_used
        m1.assert_not_called()
        m2.assert_not_called()
        m3.assert_not_called()
