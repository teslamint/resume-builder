#!/usr/bin/env python3
"""Tests for _resolve_company_alias — hangul/english slug alias resolution.

Run:
    python3 -m pytest templates/tests/test_auto_company_alias.py -v
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


RICH_BODY = (
    "# {name}\n\n"
    "## 기업 정보\n\n"
    "| 항목 | 내용 |\n"
    "|------|------|\n"
    "| 회사명 | {name} |\n"
    "| 설립 | 2015년 |\n"
    "| 직원수 | 320명 |\n\n"
    "## 연봉 정보\n\n"
    "| 항목 | 금액 | 출처 |\n"
    "|------|------|------|\n"
    "| 평균 연봉 | **5000만원** | test |\n"
)

STUB_BODY = "# {name}\n\n*자동 생성 stub*\n"

STARTUP_BODY = (
    "# 래브라도랩스\n\n"
    "## 기업 정보\n\n"
    "| 항목 | 내용 |\n"
    "|------|------|\n"
    "| 회사명 | 래브라도랩스 |\n"
    "| 스타트업 여부 | Yes |\n"
    "| 업종 | IT |\n"
    "| 설립 | 2018년 |\n"
    "| 직원수 | 36명 |\n\n"
    "## 연봉 정보\n\n"
    "| 항목 | 금액 | 출처 |\n"
    "|------|------|------|\n"
    "| 평균 연봉 | **5680만원** | Wanted |\n\n"
    "## 인원 통계\n\n"
    "| 항목 | 수치 |\n"
    "|------|------|\n"
    "| 현재 인원 | 36명 |\n"
    "| 1년간 입사자 | 15명 |\n"
    "| 1년간 퇴사자 | 11명 |\n\n"
    "## 투자 정보\n\n"
    "| 항목 | 내용 |\n"
    "|------|------|\n"
    "| 현재 라운드 | Series B |\n"
    "| 누적 투자금 | 100억원 |\n\n"
    "## 태그\n"
    "- 인원 급성장\n\n"
    "## 회사 소개\n\n"
    "기존 소개 보존 대상.\n\n"
    "---\n\n"
    "*출처:*\n"
    "- https://www.wanted.co.kr/company/11881\n"
)


class TestResolveCompanyAlias(unittest.TestCase):
    def _setup_dir(self, files: dict[str, str]) -> tuple[tempfile.TemporaryDirectory, Path]:
        tmp = tempfile.TemporaryDirectory()
        company_dir = Path(tmp.name) / "company_info"
        company_dir.mkdir()
        for name, body in files.items():
            (company_dir / name).write_text(body, encoding="utf-8")
        return tmp, company_dir

    def test_picks_rich_english_slug_over_hangul_stub(self):
        """컬리 입력 + kurly.md(rich) + 컬리.md(stub) 존재 → kurly.md 반환."""
        from auto_company import _resolve_company_alias

        tmp, company_dir = self._setup_dir({
            "kurly.md": RICH_BODY.format(name="컬리"),
            "컬리.md": STUB_BODY.format(name="컬리"),
        })
        try:
            with patch("auto_company.COMPANY_INFO_DIR", company_dir):
                result = _resolve_company_alias("컬리")
            self.assertIsNotNone(result)
            self.assertEqual(result.name, "kurly.md")
        finally:
            tmp.cleanup()

    def test_returns_hangul_when_only_hangul_rich(self):
        """컬리 입력 + 컬리.md(rich)만 → 컬리.md 반환."""
        from auto_company import _resolve_company_alias

        tmp, company_dir = self._setup_dir({
            "컬리.md": RICH_BODY.format(name="컬리"),
        })
        try:
            with patch("auto_company.COMPANY_INFO_DIR", company_dir):
                result = _resolve_company_alias("컬리")
            self.assertIsNotNone(result)
            self.assertEqual(result.name, "컬리.md")
        finally:
            tmp.cleanup()

    def test_returns_none_when_no_candidates(self):
        """신규회사 입력 + 파일 없음 → None."""
        from auto_company import _resolve_company_alias

        tmp, company_dir = self._setup_dir({})
        try:
            with patch("auto_company.COMPANY_INFO_DIR", company_dir):
                result = _resolve_company_alias("신규회사")
            self.assertIsNone(result)
        finally:
            tmp.cleanup()


class TestExistingThevcEnrichment(unittest.TestCase):
    def test_complete_startup_without_thevc_is_enriched_in_place(self):
        from auto_company import ensure_company_info

        tmp, company_dir = TestResolveCompanyAlias()._setup_dir({
            "래브라도랩스.md": STARTUP_BODY,
        })
        jd_path = Path(tmp.name) / "jd.md"
        jd_path.write_text("# Backend - 래브라도랩스\n", encoding="utf-8")
        try:
            with patch("auto_company.COMPANY_INFO_DIR", company_dir), \
                 patch("auto_company._extract_thevc_investment") as extract_mock:
                extract_mock.return_value = (
                    "success",
                    {
                        "round": "Series B",
                        "total": "100억원",
                        "investors": ["KB인베스트먼트"],
                        "source": "https://thevc.kr/labradorlabs",
                    },
                )

                result = ensure_company_info(
                    jd_path,
                    "https://example.com/jd",
                    company_name="래브라도랩스",
                    min_completeness=70,
                )

            text = (company_dir / "래브라도랩스.md").read_text(encoding="utf-8")
            self.assertTrue(result.used_existing)
            self.assertTrue(result.thevc_attempted)
            self.assertEqual(result.investment_data_source, "thevc")
            self.assertIn("| 주요 투자자 | KB인베스트먼트 |", text)
            self.assertIn("https://thevc.kr/labradorlabs", text)
            self.assertIn("기존 소개 보존 대상.", text)
            self.assertIn("- 인원 급성장", text)
        finally:
            tmp.cleanup()

    def test_skip_mode_does_not_attempt_thevc_for_existing_startup(self):
        from auto_company import ensure_company_info

        tmp, company_dir = TestResolveCompanyAlias()._setup_dir({
            "래브라도랩스.md": STARTUP_BODY,
        })
        jd_path = Path(tmp.name) / "jd.md"
        jd_path.write_text("# Backend - 래브라도랩스\n", encoding="utf-8")
        try:
            with patch("auto_company.COMPANY_INFO_DIR", company_dir), \
                 patch("auto_company._extract_thevc_investment") as extract_mock, \
                 patch("auto_company.verify_company_match", return_value=(True, 1.0, [])):
                result = ensure_company_info(
                    jd_path,
                    "https://example.com/jd",
                    company_name="래브라도랩스",
                    thevc_mode="skip",
                    min_completeness=70,
                )

            extract_mock.assert_not_called()
            self.assertEqual(result.thevc_status, "skipped")
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
