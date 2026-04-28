#!/usr/bin/env python3
"""Tests for JD auto pipeline helpers.

Run:
    python3 templates/tests/test_jd_auto.py -v
"""

import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch


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

            mock_extraction = MagicMock()
            mock_extraction.platforms_used = ["wanted"]
            mock_extraction.file_path = company_dir / "stubco.md"

            with patch("auto_company.COMPANY_INFO_DIR", company_dir), \
                 patch("auto_company._extract_thevc_investment", return_value=("skipped", None)), \
                 patch("auto_company.extract_company_info", return_value=mock_extraction):
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


    def test_ensure_company_info_calls_extract_company_info(self):
        from auto_company import ensure_company_info

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            company_dir = tmp_path / "company_info"
            company_dir.mkdir()

            jd = tmp_path / "jd.md"
            jd.write_text(
                "# Dev\n\n## 기본 정보\n\n| 항목 | 내용 |\n|------|------|\n| 회사명 | NewCo |\n",
                encoding="utf-8",
            )

            # Don't pre-create the company file — we want extraction to be called
            output_file = company_dir / "newco.md"

            mock_extraction = MagicMock()
            mock_extraction.platforms_used = ["wanted", "saramin"]
            mock_extraction.file_path = output_file
            # Simulate extract_company_info writing the file
            def side_effect(**kwargs):
                output_file.write_text("# NewCo\n\n## 기업 정보\n\n| 항목 | 내용 |\n|------|------|\n| 회사명 | NewCo |\n| 업종 | IT |\n", encoding="utf-8")
                return mock_extraction

            with patch("auto_company.COMPANY_INFO_DIR", company_dir), \
                 patch("auto_company.extract_company_info", side_effect=side_effect) as mock_extract:
                result = ensure_company_info(
                    jd_path=jd,
                    jd_url="https://wanted.co.kr/wd/99",
                    company_name="NewCo",
                    thevc_mode="skip",
                    dry_run=False,
                )

            mock_extract.assert_called_once()
            call_kwargs = mock_extract.call_args
            self.assertEqual(call_kwargs.kwargs.get("platforms") or call_kwargs[1].get("platforms"), ["wanted", "saramin"])
            self.assertFalse(result.used_existing)

    def test_ensure_company_info_dry_run_skips_extraction(self):
        from auto_company import ensure_company_info

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            company_dir = tmp_path / "company_info"
            company_dir.mkdir()

            jd = tmp_path / "jd.md"
            jd.write_text(
                "# Dev\n\n## 기본 정보\n\n| 항목 | 내용 |\n|------|------|\n| 회사명 | DryCo |\n",
                encoding="utf-8",
            )

            with patch("auto_company.COMPANY_INFO_DIR", company_dir), \
                 patch("auto_company.extract_company_info") as mock_extract:
                result = ensure_company_info(
                    jd_path=jd,
                    jd_url="https://wanted.co.kr/wd/88",
                    company_name="DryCo",
                    thevc_mode="skip",
                    dry_run=True,
                )

            mock_extract.assert_not_called()

    def test_ensure_company_info_require_mode_fails_before_extraction(self):
        """thevc_mode=require should raise BEFORE extract_company_info is called."""
        from auto_company import ensure_company_info

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            company_dir = tmp_path / "company_info"
            company_dir.mkdir()

            jd = tmp_path / "jd.md"
            jd.write_text(
                "# Dev\n\n투자 시리즈 A 스타트업\n\n## 기본 정보\n\n| 항목 | 내용 |\n|------|------|\n| 회사명 | FailCo |\n",
                encoding="utf-8",
            )

            with patch("auto_company.COMPANY_INFO_DIR", company_dir), \
                 patch("auto_company._extract_thevc_investment", return_value=("not_logged_in", None)), \
                 patch("auto_company.extract_company_info") as mock_extract:
                with self.assertRaises(RuntimeError):
                    ensure_company_info(
                        jd_path=jd,
                        jd_url="https://wanted.co.kr/wd/77",
                        company_name="FailCo",
                        thevc_mode="require",
                        dry_run=False,
                    )

            mock_extract.assert_not_called()


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
        from notifications import send_notification

        config = {
            "notifications": {
                "channel": "slack",
                "target": "channel:C0123456789",
                "account": "default",
            }
        }

        with patch(
            "notifications.subprocess.run",
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
        from notifications import send_notification

        config = {"notifications": {"channel": "slack"}}

        with patch("notifications.subprocess.run") as mock_run:
            ok = send_notification("hello", config)

        self.assertFalse(ok)
        mock_run.assert_not_called()


class TestScreeningOnlyFindsUnprocessed(unittest.TestCase):
    """Verify Issue #2: _resolve_jd_path_for_screening finds JDs in unprocessed/ via find_jd_anywhere."""

    def test_resolve_jd_for_screening_finds_unprocessed_jd(self):
        from auto import _resolve_jd_path_for_screening

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            unprocessed_dir = tmp_path / "unprocessed"
            unprocessed_dir.mkdir()
            jd = unprocessed_dir / "999020-testco-backend.md"
            jd.write_text("# Backend\n", encoding="utf-8")

            with patch("path_utils.JOB_POSTINGS_DIR", tmp_path):
                result = _resolve_jd_path_for_screening("https://www.wanted.co.kr/wd/999020")

        self.assertEqual(result, jd)

    def test_find_existing_jd_does_not_search_unprocessed(self):
        """Dedup check (find_existing_jd) must NOT find JDs in unprocessed/."""
        from path_utils import find_existing_jd

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            unprocessed_dir = tmp_path / "unprocessed"
            unprocessed_dir.mkdir()
            jd = unprocessed_dir / "999021-testco-backend.md"
            jd.write_text("# Backend\n", encoding="utf-8")

            with patch("path_utils.JOB_POSTINGS_DIR", tmp_path):
                result = find_existing_jd("999021")

        self.assertIsNone(result)


class TestAutoJdPathAfterClassify(unittest.TestCase):
    """Verify that jd_path in result row reflects post-classification file location."""

    def test_jd_path_updated_after_classification(self):
        from auto import run_auto

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            unprocessed_path = tmp_path / "999010-testco-backend.md"
            unprocessed_path.write_text(
                "# Backend\n\n## 기본 정보\n\n| 항목 | 내용 |\n|------|------|\n| 회사명 | TestCo |\n",
                encoding="utf-8",
            )
            pass_path = tmp_path / "pass" / "999010-testco-backend.md"
            pass_path.parent.mkdir(parents=True, exist_ok=True)
            pass_path.write_text("# Backend (classified)\n", encoding="utf-8")

            company_file = tmp_path / "company_info" / "testco.md"
            company_file.parent.mkdir()
            company_file.write_text("# TestCo\n", encoding="utf-8")

            urls = tmp_path / "urls.txt"
            urls.write_text("https://www.wanted.co.kr/wd/999010\n", encoding="utf-8")

            extracted = MagicMock(output_path=unprocessed_path, company="TestCo", title="Backend")
            company_info = MagicMock(
                company="TestCo",
                file_path=company_file,
                completeness=100.0,
                thevc_attempted=False,
                thevc_status="skipped",
                investment_data_source="none",
            )
            screening = MagicMock(
                screening_path=tmp_path / "screening.md",
                verdict="지원 추천",
                used_fallback=False,
            )

            with patch("auto.STATE_DIR", tmp_path / "state"), \
                 patch("auto.JOB_POSTINGS_DIR", tmp_path), \
                 patch("auto.load_config", return_value={"notifications": {}}), \
                 patch("auto.find_existing_jd", return_value=None), \
                 patch("auto.extract_jd_from_url", return_value=extracted), \
                 patch("auto.ensure_company_info", return_value=company_info), \
                 patch("auto.run_screening", return_value=screening), \
                 patch("auto._classify", return_value=("지원 추천", "pass")):
                results, summary = run_auto(
                    from_urls=urls,
                    run_id="test-jd-path-after-classify",
                )

            self.assertEqual(summary.failed, 0)
            self.assertEqual(results[0].jd_path, str(pass_path))


if __name__ == "__main__":
    unittest.main()
