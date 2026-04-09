"""Tests for ce_thevc — H1 format contract for English name extraction."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from ce_thevc import get_english_name_from_company_info


class TestGetEnglishNameFromCompanyInfo:
    """H1 format contract: '# 회사명 (EnglishName)' → extracts parenthetical English name."""

    def test_extracts_english_name_from_h1(self, tmp_path):
        md_file = tmp_path / "test-company.md"
        md_file.write_text("# 테스트회사 (TestCompany)\n\n## Overview\n", encoding="utf-8")

        with patch("ce_thevc.COMPANY_INFO_DIR", tmp_path), \
             patch("ce_thevc.slugify_company", return_value="test-company"):
            result = get_english_name_from_company_info("테스트회사")
            assert result == "TestCompany"

    def test_returns_none_when_no_english_name_in_h1(self, tmp_path):
        md_file = tmp_path / "test-company.md"
        md_file.write_text("# 테스트회사\n\n## Overview\n", encoding="utf-8")

        with patch("ce_thevc.COMPANY_INFO_DIR", tmp_path), \
             patch("ce_thevc.slugify_company", return_value="test-company"):
            result = get_english_name_from_company_info("테스트회사")
            assert result is None

    def test_returns_none_when_file_missing(self, tmp_path):
        with patch("ce_thevc.COMPANY_INFO_DIR", tmp_path), \
             patch("ce_thevc.slugify_company", return_value="nonexistent"):
            result = get_english_name_from_company_info("존재하지않는회사")
            assert result is None

    def test_handles_complex_english_name(self, tmp_path):
        md_file = tmp_path / "test-company.md"
        md_file.write_text("# 네이버 (NAVER Corp.)\n\n## Overview\n", encoding="utf-8")

        with patch("ce_thevc.COMPANY_INFO_DIR", tmp_path), \
             patch("ce_thevc.slugify_company", return_value="test-company"):
            result = get_english_name_from_company_info("네이버")
            assert result == "NAVER Corp."

    def test_handles_name_with_ampersand(self, tmp_path):
        md_file = tmp_path / "test-company.md"
        md_file.write_text("# 에이비씨 (A&B Partners)\n\n## Overview\n", encoding="utf-8")

        with patch("ce_thevc.COMPANY_INFO_DIR", tmp_path), \
             patch("ce_thevc.slugify_company", return_value="test-company"):
            result = get_english_name_from_company_info("에이비씨")
            assert result == "A&B Partners"
