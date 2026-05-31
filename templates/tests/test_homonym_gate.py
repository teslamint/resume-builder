"""Tests for homonym company-info gate — confidence < 0.3 invalidates completeness."""
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestHomonymGate:
    def test_low_confidence_zeroes_completeness(self, tmp_path):
        from auto_company import ensure_company_info

        jd_path = tmp_path / "groupby-10488-옥토스-리드-ai-에이전트.md"
        jd_path.write_text("# 리드 AI 에이전트 엔지니어\n| 회사명 | 옥토스 |\n", encoding="utf-8")

        company_file = tmp_path / "옥토스.md"
        company_file.write_text(
            "# 옥토스케이프\n## 기업 정보\n| 항목 | 내용 |\n| 회사명 | 옥토스케이프 |\n| 직원수 | 50명 |\n",
            encoding="utf-8",
        )

        mock_result = MagicMock()
        mock_result.completeness_score = 67.0

        with patch("auto_company.COMPANY_INFO_DIR", tmp_path), \
             patch("auto_company.extract_company_info", side_effect=Exception("skip")), \
             patch("auto_company._extract_thevc_investment", return_value=("none", None)), \
             patch("auto_company.parse_company_file") as mock_parse, \
             patch("auto_company.validate_company", return_value=mock_result), \
             patch("auto_company.verify_company_match", return_value=(False, 0.0, ["옥토스케이프"])), \
             patch("auto_company.slugify_company", return_value="옥토스"), \
             patch("auto_company._find_existing_company_file", return_value=None):
            result = ensure_company_info(
                company_name="옥토스",
                jd_url="https://groupby.kr/positions/10488",
                jd_path=jd_path,
            )
            assert result.completeness == 0.0

    def test_high_confidence_keeps_completeness(self, tmp_path):
        from auto_company import ensure_company_info

        jd_path = tmp_path / "364573-에어스메디컬-backend-engineer.md"
        jd_path.write_text("# Backend Engineer\n| 회사명 | 에어스메디컬 |\n", encoding="utf-8")

        company_file = tmp_path / "에어스메디컬.md"
        company_file.write_text(
            "# 에어스메디컬\n## 기업 정보\n| 항목 | 내용 |\n| 회사명 | 에어스메디컬 |\n| 직원수 | 97명 |\n",
            encoding="utf-8",
        )

        mock_result = MagicMock()
        mock_result.completeness_score = 67.0

        with patch("auto_company.COMPANY_INFO_DIR", tmp_path), \
             patch("auto_company.extract_company_info", side_effect=Exception("skip")), \
             patch("auto_company._extract_thevc_investment", return_value=("none", None)), \
             patch("auto_company.parse_company_file") as mock_parse, \
             patch("auto_company.validate_company", return_value=mock_result), \
             patch("auto_company.verify_company_match", return_value=(True, 0.9, [])), \
             patch("auto_company.slugify_company", return_value="에어스메디컬"), \
             patch("auto_company._find_existing_company_file", return_value=None):
            result = ensure_company_info(
                company_name="에어스메디컬",
                jd_url="https://www.wanted.co.kr/wd/364573",
                jd_path=jd_path,
            )
            assert result.completeness == 67.0
