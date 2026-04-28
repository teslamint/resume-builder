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


if __name__ == "__main__":
    unittest.main()
