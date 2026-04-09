"""Tests for ce_jd_files — offline JD file extraction and company name normalization."""
from ce_types import PlatformData


class TestNormalizeCompanyName:
    def test_strips_ju(self):
        from ce_jd_files import normalize_company_name
        assert normalize_company_name("(주)카카오") == "카카오"

    def test_strips_yu(self):
        from ce_jd_files import normalize_company_name
        assert normalize_company_name("(유)네이버") == "네이버"

    def test_strips_sa(self):
        from ce_jd_files import normalize_company_name
        assert normalize_company_name("(사)비영리단체") == "비영리단체"

    def test_strips_all_spaces(self):
        from ce_jd_files import normalize_company_name
        assert normalize_company_name("삼성 전자") == "삼성전자"

    def test_keeps_english_suffix(self):
        from ce_jd_files import normalize_company_name
        result = normalize_company_name("LINE Plus Corp.")
        assert "corp" in result

    def test_empty_string(self):
        from ce_jd_files import normalize_company_name
        assert normalize_company_name("") == ""


class TestExtractFromJdFiles:
    def test_returns_none_when_no_jd_files(self):
        from ce_jd_files import extract_from_jd_files
        result = extract_from_jd_files("NONEXISTENT_TEST_COMPANY_12345")
        assert result is None
