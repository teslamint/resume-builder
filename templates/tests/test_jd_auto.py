#!/usr/bin/env python3
"""Tests for JD auto pipeline helpers.

Run:
    python3 templates/tests/test_jd_auto.py -v
"""

import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch


class TestAutoCompany(unittest.TestCase):
    def test_slugify_company(self):
        from auto_company import slugify_company

        self.assertEqual(slugify_company("(주) Deep Search AI"), "deep-search-ai")

    def test_ensure_company_info_existing_file_reused(self):
        from auto_company import ensure_company_info

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            company_dir = tmp_path / "company_info"
            company_dir.mkdir()

            existing = company_dir / "deepsearch.md"
            existing.write_text(
                "# DeepSearch\n\n## 기업 정보\n\n| 항목 | 내용 |\n|------|------|\n| 회사명 | DeepSearch |\n| 설립 | 2020년 |\n| 직원수 | 10명 |\n\n## 연봉 정보\n\n| 항목 | 금액 | 출처 |\n|------|------|------|\n| 평균 연봉 | **5000만원** | test |\n",
                encoding="utf-8",
            )

            jd = tmp_path / "jd.md"
            jd.write_text(
                "# Backend\n\n## 기본 정보\n\n| 항목 | 내용 |\n|------|------|\n| 회사명 | DeepSearch |\n| 출처 | [Wanted](https://wanted.co.kr/wd/1) |\n",
                encoding="utf-8",
            )

            with patch("auto_company.COMPANY_INFO_DIR", company_dir):
                result = ensure_company_info(
                    jd_path=jd,
                    jd_url="https://wanted.co.kr/wd/1",
                    company_name="DeepSearch",
                    thevc_mode="auto",
                    dry_run=False,
                )

            self.assertTrue(result.used_existing)
            self.assertEqual(result.file_path, existing)

    def test_ensure_company_info_min_completeness_triggers_recollection(self):
        from auto_company import ensure_company_info

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            company_dir = tmp_path / "company_info"
            company_dir.mkdir()

            # stub file: all fields are '정보 없음' → completeness ~0%
            stub = company_dir / "stubco.md"
            stub.write_text(
                "# StubCo\n\n## 기업 정보\n\n| 항목 | 내용 |\n|------|------|\n"
                "| 회사명 | StubCo |\n| 업종 | 정보 없음 |\n| 설립 | 정보 없음 |\n| 직원수 | 정보 없음 |\n\n"
                "## 연봉 정보\n\n| 항목 | 금액 | 출처 |\n|------|------|------|\n"
                "| 평균 연봉 | 정보 없음 | 정보 없음 |\n\n"
                "## 인원 통계\n\n| 항목 | 수치 |\n|------|------|\n"
                "| 현재 인원 | 정보 없음 |\n| 1년간 입사자 | 정보 없음 |\n| 1년간 퇴사자 | 정보 없음 |\n",
                encoding="utf-8",
            )

            jd = tmp_path / "jd.md"
            jd.write_text(
                "# Backend\n\n## 기본 정보\n\n| 항목 | 내용 |\n|------|------|\n"
                "| 회사명 | StubCo |\n| 출처 | [Wanted](https://wanted.co.kr/wd/9) |\n",
                encoding="utf-8",
            )

            with patch("auto_company.COMPANY_INFO_DIR", company_dir), patch(
                "auto_company._extract_thevc_investment", return_value=("skipped", None)
            ):
                result = ensure_company_info(
                    jd_path=jd,
                    jd_url="https://wanted.co.kr/wd/9",
                    company_name="StubCo",
                    thevc_mode="skip",
                    dry_run=False,
                    min_completeness=30.0,
                )

            self.assertFalse(result.used_existing)

    def test_ensure_company_info_require_mode_fails_when_thevc_not_logged_in(self):
        from auto_company import ensure_company_info

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            company_dir = tmp_path / "company_info"
            company_dir.mkdir()

            jd = tmp_path / "jd.md"
            jd.write_text(
                "# Backend\n\n## 기본 정보\n\n| 항목 | 내용 |\n|------|------|\n| 회사명 | StartupCo |\n| 출처 | [Wanted](https://wanted.co.kr/wd/2) |\n\n투자 시리즈 B\n",
                encoding="utf-8",
            )

            with patch("auto_company.COMPANY_INFO_DIR", company_dir), patch(
                "auto_company._extract_thevc_investment", return_value=("not_logged_in", None)
            ):
                with self.assertRaises(RuntimeError):
                    ensure_company_info(
                        jd_path=jd,
                        jd_url="https://wanted.co.kr/wd/2",
                        company_name="StartupCo",
                        thevc_mode="require",
                        dry_run=False,
                    )


class TestAutoScreening(unittest.TestCase):
    def test_run_screening_fallback_when_llm_fails(self):
        from auto_screening import run_screening

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            jd = tmp_path / "123-testco-backend.md"
            jd.write_text(
                "# Backend\n\n## 기본 정보\n\n| 항목 | 내용 |\n|------|------|\n| 회사명 | TestCo |\n| 포지션 | Backend |\n| 출처 | [Wanted](https://wanted.co.kr/wd/123) |\n",
                encoding="utf-8",
            )

            screening_dir = tmp_path / "screening"
            with patch("auto_screening.SCREENING_DIR", screening_dir), patch(
                "auto_screening._run_llm", side_effect=RuntimeError("no llm")
            ), patch("auto_screening.update_summary"):
                result = run_screening(jd_path=jd, company_file=None, dry_run=False)

            self.assertEqual(result.verdict, "지원 보류")
            self.assertTrue(result.used_fallback)
            self.assertTrue(result.screening_path.exists())


class TestAutoNotifications(unittest.TestCase):
    def test_send_notification_uses_openclaw_send_with_target(self):
        from auto import send_notification

        config = {
            "notifications": {
                "channel": "slack",
                "target": "channel:C0123456789",
                "account": "default",
            }
        }

        with patch(
            "auto.subprocess.run",
            return_value=CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ) as mock_run:
            ok = send_notification("hello", config)

        self.assertTrue(ok)
        mock_run.assert_called_once_with(
            [
                "openclaw",
                "message",
                "send",
                "--channel",
                "slack",
                "--target",
                "channel:C0123456789",
                "--message",
                "hello",
                "--account",
                "default",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_send_notification_skips_without_target(self):
        from auto import send_notification

        config = {"notifications": {"channel": "slack"}}

        with patch("auto.subprocess.run") as mock_run:
            ok = send_notification("hello", config)

        self.assertFalse(ok)
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
