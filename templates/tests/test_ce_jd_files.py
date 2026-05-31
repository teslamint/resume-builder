"""Tests for ce_jd_files — offline JD file extraction and narrow company name normalization."""
from ce_types import PlatformData


class TestNormalizeCompanyNameNarrow:
    def test_strips_ju(self):
        from ce_jd_files import normalize_company_name_narrow
        assert normalize_company_name_narrow("(주)카카오") == "카카오"

    def test_strips_yu(self):
        from ce_jd_files import normalize_company_name_narrow
        assert normalize_company_name_narrow("(유)네이버") == "네이버"

    def test_strips_sa(self):
        from ce_jd_files import normalize_company_name_narrow
        assert normalize_company_name_narrow("(사)비영리단체") == "비영리단체"

    def test_strips_all_spaces(self):
        from ce_jd_files import normalize_company_name_narrow
        assert normalize_company_name_narrow("삼성 전자") == "삼성전자"

    def test_keeps_english_suffix(self):
        from ce_jd_files import normalize_company_name_narrow
        result = normalize_company_name_narrow("LINE Plus Corp.")
        assert "corp" in result

    def test_empty_string(self):
        from ce_jd_files import normalize_company_name_narrow
        assert normalize_company_name_narrow("") == ""


class TestExtractFromJdFiles:
    def test_returns_none_when_no_jd_files(self):
        from ce_jd_files import extract_from_jd_files
        result = extract_from_jd_files("NONEXISTENT_TEST_COMPANY_12345")
        assert result is None
