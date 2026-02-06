#!/usr/bin/env python3
"""Tests for JD status management.

Run with:
    python3 templates/test_jd_status.py
    python3 templates/test_jd_status.py -v  # verbose

Or with pytest (if installed):
    pytest templates/test_jd_status.py -v
"""

import unittest
import tempfile
from pathlib import Path
from datetime import datetime


class TestParseFrontmatter(unittest.TestCase):
    """Step 2: parse_frontmatter tests."""

    def test_parse_frontmatter_with_status(self):
        from jd_utils import parse_frontmatter

        content = """---
status: rejected
status_updated: 2026-01-24
---
# JD 내용"""
        result = parse_frontmatter(content)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["status_updated"], "2026-01-24")

    def test_parse_frontmatter_empty(self):
        from jd_utils import parse_frontmatter

        content = "# JD 내용 (frontmatter 없음)"
        result = parse_frontmatter(content)
        self.assertEqual(result, {})

    def test_parse_frontmatter_with_reason(self):
        from jd_utils import parse_frontmatter

        content = """---
status: rejected
status_reason: 채용 프로세스 부담
---
# JD"""
        result = parse_frontmatter(content)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["status_reason"], "채용 프로세스 부담")

    def test_parse_frontmatter_partial(self):
        from jd_utils import parse_frontmatter

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
        from jd_utils import get_user_status

        content = "---\nstatus: applied\n---\n# JD"
        self.assertEqual(get_user_status(content), "applied")

    def test_get_user_status_none(self):
        from jd_utils import get_user_status

        content = "# JD without frontmatter"
        self.assertIsNone(get_user_status(content))

    def test_get_user_status_pending(self):
        from jd_utils import get_user_status

        content = "---\nstatus: pending\n---\n# JD"
        self.assertEqual(get_user_status(content), "pending")


class TestIsProtectedStatus(unittest.TestCase):
    """Step 4: is_protected_status tests."""

    def test_protected_rejected(self):
        from jd_utils import is_protected_status

        self.assertTrue(is_protected_status("rejected"))

    def test_protected_applied(self):
        from jd_utils import is_protected_status

        self.assertTrue(is_protected_status("applied"))

    def test_protected_interview(self):
        from jd_utils import is_protected_status

        self.assertTrue(is_protected_status("interview"))

    def test_protected_offer(self):
        from jd_utils import is_protected_status

        self.assertTrue(is_protected_status("offer"))

    def test_not_protected_pending(self):
        from jd_utils import is_protected_status

        self.assertFalse(is_protected_status("pending"))

    def test_not_protected_none(self):
        from jd_utils import is_protected_status

        self.assertFalse(is_protected_status(None))

    def test_protected_legacy_pass_alias(self):
        from jd_utils import is_protected_status

        self.assertTrue(is_protected_status("패스"))

    def test_not_protected_legacy_hold_alias(self):
        from jd_utils import is_protected_status

        self.assertFalse(is_protected_status("조건부(하)"))


class TestVerdictParsing(unittest.TestCase):
    """Verdict parser/mapping regression tests."""

    def test_parse_heading_colon(self):
        from jd_utils import parse_verdict_from_screening

        content = "### 최종 판정: 🟢 지원 추천"
        self.assertEqual(parse_verdict_from_screening(content), "지원 추천")

    def test_parse_section_pass_heading(self):
        from jd_utils import parse_verdict_from_screening

        content = """## 판정

### 🔴 **PASS**
"""
        self.assertEqual(parse_verdict_from_screening(content), "지원 비추천")

    def test_parse_section_table_worst_case(self):
        from jd_utils import parse_verdict_from_screening

        content = """## 최종 판정

| 포지션 | 판정 | 사유 |
|--------|------|------|
| Senior Backend | 🟡 지원 보류 | 조건부 |
| Backend Lead | 🔴 지원 비추천 | 리드 역할 |
"""
        self.assertEqual(parse_verdict_from_screening(content), "지원 비추천")

    def test_parse_ignores_table_header(self):
        from jd_utils import parse_verdict_from_screening

        content = """## 최종 판정

| 포지션 | 판정 | 사유 |
|--------|------|------|
"""
        self.assertIsNone(parse_verdict_from_screening(content))

    def test_classify_by_verdict_handles_legacy(self):
        from jd_utils import classify_by_verdict

        self.assertEqual(classify_by_verdict("조건부(상)"), "conditional/hold")
        self.assertEqual(classify_by_verdict("강력 추천"), "conditional/high")
        self.assertEqual(classify_by_verdict("PASS"), "pass")


class TestAddFrontmatterStatus(unittest.TestCase):
    """Step 5: add_frontmatter_status tests."""

    def test_add_frontmatter_to_new(self):
        from jd_utils import add_frontmatter_status

        content = "# JD 내용"
        result = add_frontmatter_status(content, "rejected")
        self.assertIn("---", result)
        self.assertIn("status: rejected", result)
        self.assertIn("# JD 내용", result)

    def test_add_frontmatter_update_existing(self):
        from jd_utils import add_frontmatter_status

        content = "---\nstatus: pending\n---\n# JD"
        result = add_frontmatter_status(content, "rejected", "면접 거절")
        self.assertIn("status: rejected", result)
        self.assertIn("status_reason: 면접 거절", result)
        self.assertNotIn("status: pending", result)

    def test_add_frontmatter_preserves_other_fields(self):
        from jd_utils import add_frontmatter_status

        content = "---\nstatus: pending\ncustom_field: value\n---\n# JD"
        result = add_frontmatter_status(content, "applied")
        self.assertIn("status: applied", result)
        self.assertIn("custom_field: value", result)

    def test_add_frontmatter_adds_timestamp(self):
        from jd_utils import add_frontmatter_status

        content = "# JD 내용"
        result = add_frontmatter_status(content, "rejected")
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertIn(f"status_updated: {today}", result)


class TestClassifyFileProtection(unittest.TestCase):
    """Step 6: classify_file protection tests."""

    def test_classify_file_skips_protected_rejected(self):
        from jd_pipeline import classify_file, ProcessResult

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            jd_file = tmp_path / "123-test-company.md"
            jd_file.write_text("---\nstatus: rejected\n---\n# JD 내용")

            result = classify_file(jd_file)
            self.assertEqual(result.result, ProcessResult.SKIPPED)
            self.assertIn("보호", result.message)

    def test_classify_file_skips_protected_applied(self):
        from jd_pipeline import classify_file, ProcessResult

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            jd_file = tmp_path / "123-test-company.md"
            jd_file.write_text("---\nstatus: applied\n---\n# JD 내용")

            result = classify_file(jd_file)
            self.assertEqual(result.result, ProcessResult.SKIPPED)
            self.assertIn("보호", result.message)

    def test_classify_file_allows_pending(self):
        from jd_pipeline import classify_file, ProcessResult

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            jd_file = tmp_path / "123-test-company.md"
            jd_file.write_text("---\nstatus: pending\n---\n# JD 내용\n### 최종 판정: 지원 추천")

            result = classify_file(jd_file, dry_run=True)
            # pending은 보호되지 않으므로 SKIPPED가 아니거나 보호 메시지가 없어야 함
            is_not_protected = result.result != ProcessResult.SKIPPED or "보호" not in result.message
            self.assertTrue(is_not_protected, f"pending should not be protected: {result}")

    def test_classify_file_allows_no_status(self):
        from jd_pipeline import classify_file, ProcessResult

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
        from jd_pipeline import migrate_status

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
        from jd_pipeline import migrate_status

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
        from jd_pipeline import migrate_status

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
        from jd_pipeline import migrate_status

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
        from jd_pipeline import build_dry_run_report, ProcessedItem, ProcessResult

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
        from jd_pipeline import write_dry_run_report

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
            "recommendations": {"next_command": "python3 templates/jd_pipeline.py --rescreen job_postings/conditional/hold"},
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


if __name__ == "__main__":
    unittest.main()
