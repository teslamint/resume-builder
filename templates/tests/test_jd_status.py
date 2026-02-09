#!/usr/bin/env python3
"""Tests for JD status management.

Run with:
    python3 templates/tests/test_jd_status.py
    python3 templates/tests/test_jd_status.py -v  # verbose

Or with pytest (if installed):
    pytest templates/tests/test_jd_status.py -v
"""

import sys
import unittest
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "jd"))


class TestParseFrontmatter(unittest.TestCase):
    """Step 2: parse_frontmatter tests."""

    def test_parse_frontmatter_with_status(self):
        from utils import parse_frontmatter

        content = """---
status: rejected
status_updated: 2026-01-24
---
# JD 내용"""
        result = parse_frontmatter(content)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["status_updated"], "2026-01-24")

    def test_parse_frontmatter_empty(self):
        from utils import parse_frontmatter

        content = "# JD 내용 (frontmatter 없음)"
        result = parse_frontmatter(content)
        self.assertEqual(result, {})

    def test_parse_frontmatter_with_reason(self):
        from utils import parse_frontmatter

        content = """---
status: rejected
status_reason: 채용 프로세스 부담
---
# JD"""
        result = parse_frontmatter(content)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["status_reason"], "채용 프로세스 부담")

    def test_parse_frontmatter_partial(self):
        from utils import parse_frontmatter

        content = """---
status: applied
---
# JD 내용"""
        result = parse_frontmatter(content)
        self.assertEqual(result["status"], "applied")
        self.assertNotIn("status_updated", result)


class TestGetUserStatus(unittest.TestCase):
    """Step 3: get_user_status tests."""

    def test_get_user_status_exists(self):
        from utils import get_user_status

        content = "---\nstatus: applied\n---\n# JD"
        self.assertEqual(get_user_status(content), "applied")

    def test_get_user_status_none(self):
        from utils import get_user_status

        content = "# JD without frontmatter"
        self.assertIsNone(get_user_status(content))

    def test_get_user_status_pending(self):
        from utils import get_user_status

        content = "---\nstatus: pending\n---\n# JD"
        self.assertEqual(get_user_status(content), "pending")


class TestIsProtectedStatus(unittest.TestCase):
    """Step 4: is_protected_status tests."""

    def test_protected_rejected(self):
        from utils import is_protected_status

        self.assertTrue(is_protected_status("rejected"))

    def test_protected_applied(self):
        from utils import is_protected_status

        self.assertTrue(is_protected_status("applied"))

    def test_protected_interview(self):
        from utils import is_protected_status

        self.assertTrue(is_protected_status("interview"))

    def test_protected_offer(self):
        from utils import is_protected_status

        self.assertTrue(is_protected_status("offer"))

    def test_not_protected_pending(self):
        from utils import is_protected_status

        self.assertFalse(is_protected_status("pending"))

    def test_not_protected_none(self):
        from utils import is_protected_status

        self.assertFalse(is_protected_status(None))

    def test_protected_legacy_pass_alias(self):
        from utils import is_protected_status

        self.assertTrue(is_protected_status("패스"))

    def test_not_protected_legacy_hold_alias(self):
        from utils import is_protected_status

        self.assertFalse(is_protected_status("조건부(하)"))


class TestVerdictParsing(unittest.TestCase):
    """Verdict parser/mapping regression tests."""

    def test_parse_heading_colon(self):
        from utils import parse_verdict_from_screening

        content = "### 최종 판정: 🟢 지원 추천"
        self.assertEqual(parse_verdict_from_screening(content), "지원 추천")

    def test_parse_section_pass_heading(self):
        from utils import parse_verdict_from_screening

        content = """## 판정

### 🔴 **PASS**
"""
        self.assertEqual(parse_verdict_from_screening(content), "지원 비추천")

    def test_parse_section_table_worst_case(self):
        from utils import parse_verdict_from_screening

        content = """## 최종 판정

| 포지션 | 판정 | 사유 |
|--------|------|------|
| Senior Backend | 🟡 지원 보류 | 조건부 |
| Backend Lead | 🔴 지원 비추천 | 리드 역할 |
"""
        self.assertEqual(parse_verdict_from_screening(content), "지원 비추천")

    def test_parse_ignores_table_header(self):
        from utils import parse_verdict_from_screening

        content = """## 최종 판정

| 포지션 | 판정 | 사유 |
|--------|------|------|
"""
        self.assertIsNone(parse_verdict_from_screening(content))

    def test_classify_by_verdict_handles_legacy(self):
        from utils import classify_by_verdict

        self.assertEqual(classify_by_verdict("조건부(상)"), "conditional/hold")
        self.assertEqual(classify_by_verdict("강력 추천"), "conditional/high")
        self.assertEqual(classify_by_verdict("PASS"), "pass")


class TestAddFrontmatterStatus(unittest.TestCase):
    """Step 5: add_frontmatter_status tests."""

    def test_add_frontmatter_to_new(self):
        from utils import add_frontmatter_status

        content = "# JD 내용"
        result = add_frontmatter_status(content, "rejected")
        self.assertIn("---", result)
        self.assertIn("status: rejected", result)
        self.assertIn("# JD 내용", result)

    def test_add_frontmatter_update_existing(self):
        from utils import add_frontmatter_status

        content = "---\nstatus: pending\n---\n# JD"
        result = add_frontmatter_status(content, "rejected", "면접 거절")
        self.assertIn("status: rejected", result)
        self.assertIn("status_reason: 면접 거절", result)
        self.assertNotIn("status: pending", result)

    def test_add_frontmatter_preserves_other_fields(self):
        from utils import add_frontmatter_status

        content = "---\nstatus: pending\ncustom_field: value\n---\n# JD"
        result = add_frontmatter_status(content, "applied")
        self.assertIn("status: applied", result)
        self.assertIn("custom_field: value", result)

    def test_add_frontmatter_adds_timestamp(self):
        from utils import add_frontmatter_status

        content = "# JD 내용"
        result = add_frontmatter_status(content, "rejected")
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertIn(f"status_updated: {today}", result)


class TestClassifyFileProtection(unittest.TestCase):
    """Step 6: classify_file protection tests."""

    def test_classify_file_skips_protected_rejected(self):
        from pipeline import classify_file, ProcessResult

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            jd_file = tmp_path / "123-test-company.md"
            jd_file.write_text("---\nstatus: rejected\n---\n# JD 내용")

            result = classify_file(jd_file)
            self.assertEqual(result.result, ProcessResult.SKIPPED)
            self.assertIn("보호", result.message)

    def test_classify_file_skips_protected_applied(self):
        from pipeline import classify_file, ProcessResult

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            jd_file = tmp_path / "123-test-company.md"
            jd_file.write_text("---\nstatus: applied\n---\n# JD 내용")

            result = classify_file(jd_file)
            self.assertEqual(result.result, ProcessResult.SKIPPED)
            self.assertIn("보호", result.message)

    def test_classify_file_allows_pending(self):
        from pipeline import classify_file, ProcessResult

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            jd_file = tmp_path / "123-test-company.md"
            jd_file.write_text("---\nstatus: pending\n---\n# JD 내용\n### 최종 판정: 지원 추천")

            result = classify_file(jd_file, dry_run=True)
            # pending은 보호되지 않으므로 SKIPPED가 아니거나 보호 메시지가 없어야 함
            is_not_protected = result.result != ProcessResult.SKIPPED or "보호" not in result.message
            self.assertTrue(is_not_protected, f"pending should not be protected: {result}")

    def test_classify_file_allows_no_status(self):
        from pipeline import classify_file, ProcessResult

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            jd_file = tmp_path / "123-test-company.md"
            jd_file.write_text("# JD 내용\n### 최종 판정: 지원 추천")

            result = classify_file(jd_file, dry_run=True)
            # status 없으면 정상 처리
            is_not_protected = result.result == ProcessResult.SUCCESS or "보호" not in result.message
            self.assertTrue(is_not_protected)


class TestMigrateStatus(unittest.TestCase):
    """Step 7: migrate_status tests."""

    def test_migrate_applied_folder(self):
        from pipeline import migrate_status

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            applied = tmp_path / "applied"
            applied.mkdir()
            jd = applied / "123-company.md"
            jd.write_text("# JD without status")

            migrate_status(tmp_path, dry_run=False)

            content = jd.read_text()
            self.assertIn("status: applied", content)

    def test_migrate_rejected_folder(self):
        from pipeline import migrate_status

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            rejected = tmp_path / "rejected"
            rejected.mkdir()
            jd = rejected / "456-company.md"
            jd.write_text("# JD without status")

            migrate_status(tmp_path, dry_run=False)

            content = jd.read_text()
            self.assertIn("status: rejected", content)

    def test_migrate_skips_existing_status(self):
        from pipeline import migrate_status

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            applied = tmp_path / "applied"
            applied.mkdir()
            jd = applied / "123-company.md"
            jd.write_text("---\nstatus: interview\n---\n# JD")

            migrate_status(tmp_path, dry_run=False)

            content = jd.read_text()
            self.assertIn("status: interview", content)
            self.assertEqual(content.count("status:"), 1)

    def test_migrate_dry_run(self):
        from pipeline import migrate_status

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            applied = tmp_path / "applied"
            applied.mkdir()
            jd = applied / "123-company.md"
            original_content = "# JD without status"
            jd.write_text(original_content)

            migrate_status(tmp_path, dry_run=True)

            self.assertEqual(jd.read_text(), original_content)


class TestDryRunReport(unittest.TestCase):
    """Dry-run report generation tests."""

    def test_build_dry_run_report_summary(self):
        from pipeline import build_dry_run_report, ProcessedItem, ProcessResult

        results = [
            ProcessedItem(
                url_or_path="job_postings/conditional/hold/1-a.md",
                job_id="1",
                result=ProcessResult.SUCCESS,
                message="[DRY-RUN] 지원 비추천 → pass",
                target_folder="pass",
                current_folder="conditional/hold",
                verdict="지원 비추천",
                verdict_source="screening:1-a.md",
            ),
            ProcessedItem(
                url_or_path="job_postings/conditional/hold/2-b.md",
                job_id="2",
                result=ProcessResult.SKIPPED,
                message="보호된 상태 (패스 → rejected): 재분류 스킵",
                current_folder="conditional/hold",
                skip_reason="protected_status",
                protected_status="패스 → rejected",
            ),
        ]
        report = build_dry_run_report(results, Path("job_postings/conditional/hold"), "rescreen")

        self.assertEqual(report["summary"]["total"], 2)
        self.assertEqual(report["summary"]["success"], 1)
        self.assertEqual(report["summary"]["skipped"], 1)
        self.assertEqual(report["summary"]["move_candidates"], 1)
        self.assertEqual(report["skip_reasons"]["protected_status"], 1)
        self.assertIn("1", report["move_candidates"])
        self.assertIn("2", report["skipped_job_ids"])

    def test_write_dry_run_report_creates_json_and_md(self):
        from pipeline import write_dry_run_report

        report = {
            "generated_at": "2026-02-04T00:00:00",
            "action": "rescreen",
            "folder": "job_postings/conditional/hold",
            "summary": {
                "total": 1,
                "success": 1,
                "skipped": 0,
                "error": 0,
                "duplicate": 0,
                "needs_manual": 0,
                "move_candidates": 1,
                "no_change": 0,
            },
            "target_folders": {"pass": 1},
            "skip_reasons": {},
            "recommendations": {"next_command": "python3 templates/jd/pipeline.py --rescreen job_postings/conditional/hold"},
            "move_candidates": ["1"],
            "skipped_job_ids": [],
            "items": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "reports"
            paths = write_dry_run_report(
                report,
                Path("job_postings/conditional/hold"),
                str(output_dir),
                "both",
            )
            self.assertEqual(len(paths), 2)
            self.assertTrue(any(p.suffix == ".json" for p in paths))
            self.assertTrue(any(p.suffix == ".md" for p in paths))
            for p in paths:
                self.assertTrue(p.exists())


class TestNormalizeCompanyName(unittest.TestCase):
    """_normalize_company_name tests."""

    def test_removes_legal_suffixes_korean(self):
        from utils import _normalize_company_name

        self.assertEqual(_normalize_company_name("(주)크몽"), "크몽")
        self.assertEqual(_normalize_company_name("주식회사 컬리"), "컬리")
        self.assertEqual(_normalize_company_name("㈜무신사"), "무신사")

    def test_removes_legal_suffixes_english(self):
        from utils import _normalize_company_name

        self.assertEqual(_normalize_company_name("ACME Corp."), "acme")
        self.assertEqual(_normalize_company_name("Foo Inc"), "foo")
        self.assertEqual(_normalize_company_name("Bar Co., Ltd."), "bar")

    def test_strips_and_lowercases(self):
        from utils import _normalize_company_name

        self.assertEqual(_normalize_company_name("  MyCompany  "), "mycompany")
        self.assertEqual(_normalize_company_name("ABC"), "abc")

    def test_empty_string(self):
        from utils import _normalize_company_name

        self.assertEqual(_normalize_company_name(""), "")


class TestIsRejectedCompany(unittest.TestCase):
    """is_rejected_company tests."""

    def test_exact_match(self):
        from utils import is_rejected_company

        rejected = {"크몽", "컬리", "무신사"}
        self.assertTrue(is_rejected_company("크몽", rejected))
        self.assertTrue(is_rejected_company("(주)크몽", rejected))

    def test_no_substring_match(self):
        from utils import is_rejected_company

        rejected = {"무신사"}
        self.assertFalse(is_rejected_company("무신사페이먼츠", rejected))

    def test_config_excludes(self):
        from utils import is_rejected_company

        rejected = set()
        self.assertTrue(is_rejected_company("BadCo", rejected, ["BadCo"]))
        self.assertFalse(is_rejected_company("GoodCo", rejected, ["BadCo"]))

    def test_empty_company(self):
        from utils import is_rejected_company

        self.assertFalse(is_rejected_company("", {"크몽"}))

    def test_combined_sources(self):
        from utils import is_rejected_company

        rejected = {"크몽"}
        config_excludes = ["엘박스"]
        self.assertTrue(is_rejected_company("크몽", rejected, config_excludes))
        self.assertTrue(is_rejected_company("엘박스", rejected, config_excludes))
        self.assertFalse(is_rejected_company("네이버", rejected, config_excludes))


class TestGetRejectedCompanies(unittest.TestCase):
    """get_rejected_companies integration test with temp directory."""

    def test_collects_from_rejected_folder(self):
        from utils import get_rejected_companies, JOB_POSTINGS_DIR
        import utils as jd_utils

        original_dir = jd_utils.JOB_POSTINGS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                jd_utils.JOB_POSTINGS_DIR = tmp_path

                rejected_dir = tmp_path / "rejected"
                rejected_dir.mkdir()

                jd = rejected_dir / "123-testco-backend.md"
                jd.write_text(
                    "# JD\n\n| 회사명 | TestCo |\n| 포지션 | Backend |",
                    encoding="utf-8",
                )

                result = get_rejected_companies()
                self.assertIn("testco", result)
        finally:
            jd_utils.JOB_POSTINGS_DIR = original_dir

    def test_collects_from_status_rejected(self):
        from utils import get_rejected_companies
        import utils as jd_utils

        original_dir = jd_utils.JOB_POSTINGS_DIR
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                jd_utils.JOB_POSTINGS_DIR = tmp_path

                hold_dir = tmp_path / "conditional" / "hold"
                hold_dir.mkdir(parents=True)

                jd = hold_dir / "456-otherco-dev.md"
                jd.write_text(
                    "---\nstatus: rejected\n---\n# JD\n\n| 회사명 | OtherCo |\n| 포지션 | Dev |",
                    encoding="utf-8",
                )

                result = get_rejected_companies()
                self.assertIn("otherco", result)
        finally:
            jd_utils.JOB_POSTINGS_DIR = original_dir


if __name__ == "__main__":
    unittest.main()
