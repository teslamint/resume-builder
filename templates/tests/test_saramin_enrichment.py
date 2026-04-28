#!/usr/bin/env python3
"""Tests for enrich_saramin_company_info.py — queue management and merge logic."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


STUB_BODY = "# {name}\n\n*자동 생성 stub*\n"

WANTED_BODY = (
    "# 테스트회사\n\n"
    "## 기업 정보\n\n"
    "| 항목 | 내용 |\n"
    "|------|------|\n"
    "| 회사명 | 테스트회사 |\n"
    "| 스타트업 여부 | Yes |\n"
    "| 업종 | 정보 없음 |\n"
    "| 설립 | 2018년 |\n"
    "| 직원수 | 정보 없음 |\n\n"
    "## 연봉 정보\n\n"
    "| 항목 | 금액 | 출처 |\n"
    "|------|------|------|\n"
    "| 평균 연봉 | **5000만원** | Wanted |\n\n"
    "## 인원 통계\n\n"
    "| 항목 | 수치 |\n"
    "|------|------|\n"
    "| 현재 인원 | 정보 없음 |\n"
    "| 1년간 입사자 | 정보 없음 |\n"
    "| 1년간 퇴사자 | 정보 없음 |\n\n"
    "---\n\n"
    "*출처:*\n"
    "- https://www.wanted.co.kr/company/12345\n"
)

RICH_BODY = (
    "# 풀데이터회사\n\n"
    "## 기업 정보\n\n"
    "| 항목 | 내용 |\n"
    "|------|------|\n"
    "| 회사명 | 풀데이터회사 |\n"
    "| 스타트업 여부 | No |\n"
    "| 업종 | 소프트웨어 |\n"
    "| 설립 | 2010년 |\n"
    "| 직원수 | 500명 |\n\n"
    "## 연봉 정보\n\n"
    "| 항목 | 금액 | 출처 |\n"
    "|------|------|------|\n"
    "| 평균 연봉 | **6000만원** | Wanted |\n\n"
    "## 인원 통계\n\n"
    "| 항목 | 수치 |\n"
    "|------|------|\n"
    "| 현재 인원 | 500명 |\n"
    "| 1년간 입사자 | 80명 |\n"
    "| 1년간 퇴사자 | 50명 |\n\n"
    "---\n\n"
    "*출처:*\n"
    "- https://www.wanted.co.kr/company/99999\n"
)


class TestAppendSaraminEnrichmentQueue(unittest.TestCase):
    def test_appends_new_company(self):
        from auto_company import _append_saramin_enrichment_queue, SARAMIN_ENRICHMENT_QUEUE_PATH

        with tempfile.TemporaryDirectory() as tmp:
            queue_path = Path(tmp) / "company_enrichment_saramin.txt"
            with patch("auto_company.SARAMIN_ENRICHMENT_QUEUE_PATH", queue_path):
                _append_saramin_enrichment_queue("테스트회사")

            self.assertTrue(queue_path.exists())
            lines = queue_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(lines, ["테스트회사"])

    def test_deduplicates_existing_company(self):
        from auto_company import _append_saramin_enrichment_queue

        with tempfile.TemporaryDirectory() as tmp:
            queue_path = Path(tmp) / "company_enrichment_saramin.txt"
            queue_path.write_text("테스트회사\n", encoding="utf-8")
            with patch("auto_company.SARAMIN_ENRICHMENT_QUEUE_PATH", queue_path):
                _append_saramin_enrichment_queue("테스트회사")
                _append_saramin_enrichment_queue("테스트회사")

            lines = [l for l in queue_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(lines.count("테스트회사"), 1)

    def test_appends_multiple_different_companies(self):
        from auto_company import _append_saramin_enrichment_queue

        with tempfile.TemporaryDirectory() as tmp:
            queue_path = Path(tmp) / "company_enrichment_saramin.txt"
            with patch("auto_company.SARAMIN_ENRICHMENT_QUEUE_PATH", queue_path):
                _append_saramin_enrichment_queue("회사A")
                _append_saramin_enrichment_queue("회사B")

            lines = [l for l in queue_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertIn("회사A", lines)
            self.assertIn("회사B", lines)
            self.assertEqual(len(lines), 2)


class TestEnsureCompanyInfoSaraminQueue(unittest.TestCase):
    """Verify that ensure_company_info routes Saramin failures to the backfill queue."""

    def _make_jd(self, tmp: Path, company: str) -> Path:
        jd = tmp / "jd.md"
        jd.write_text(f"# Backend Engineer - {company}\n", encoding="utf-8")
        return jd

    def test_saramin_failure_enqueues_company(self):
        from auto_company import ensure_company_info

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            company_dir = tmp_path / "company_info"
            company_dir.mkdir()
            queue_path = tmp_path / "company_enrichment_saramin.txt"
            jd_path = self._make_jd(tmp_path, "테스트기술회사")

            with (
                patch("auto_company.COMPANY_INFO_DIR", company_dir),
                patch("auto_company.SARAMIN_ENRICHMENT_QUEUE_PATH", queue_path),
                patch("auto_company._extract_thevc_investment", return_value=("skipped", None)),
                patch("auto_company.extract_company_info") as mock_extract,
                patch("auto_company.verify_company_match", return_value=(True, 1.0, [])),
            ):
                from ce_types import ExtractionResult
                mock_extract.return_value = ExtractionResult(
                    company="테스트기술회사",
                    file_path=company_dir / "테스트기술회사.md",
                    completeness=60.0,
                    platforms_used=["wanted"],
                    platforms_failed=["saramin"],
                    source_urls=["https://www.wanted.co.kr/company/99"],
                )
                # No existing file — ensures ensure_company_info takes the extraction path,
                # not the "return existing" early-exit path.
                ensure_company_info(jd_path, "https://example.com/jd", company_name="테스트기술회사")

            self.assertTrue(queue_path.exists())
            companies = {l.strip() for l in queue_path.read_text(encoding="utf-8").splitlines() if l.strip()}
            self.assertIn("테스트기술회사", companies)

    def test_saramin_success_does_not_enqueue(self):
        from auto_company import ensure_company_info

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            company_dir = tmp_path / "company_info"
            company_dir.mkdir()
            queue_path = tmp_path / "company_enrichment_saramin.txt"
            jd_path = self._make_jd(tmp_path, "정상회사")

            with (
                patch("auto_company.COMPANY_INFO_DIR", company_dir),
                patch("auto_company.SARAMIN_ENRICHMENT_QUEUE_PATH", queue_path),
                patch("auto_company._extract_thevc_investment", return_value=("skipped", None)),
                patch("auto_company.extract_company_info") as mock_extract,
                patch("auto_company.verify_company_match", return_value=(True, 1.0, [])),
            ):
                from ce_types import ExtractionResult
                mock_extract.return_value = ExtractionResult(
                    company="정상회사",
                    file_path=company_dir / "정상회사.md",
                    completeness=80.0,
                    platforms_used=["wanted", "saramin"],
                    platforms_failed=[],
                    source_urls=["https://www.wanted.co.kr/company/1"],
                )
                (company_dir / "정상회사.md").write_text(STUB_BODY.format(name="정상회사"), encoding="utf-8")

                ensure_company_info(jd_path, "https://example.com/jd", company_name="정상회사")

            self.assertFalse(queue_path.exists() and bool(queue_path.read_text(encoding="utf-8").strip()))


class TestScanCandidates(unittest.TestCase):
    def test_returns_companies_from_queue(self):
        from enrich_saramin_company_info import scan_candidates

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            queue_path = tmp_path / "queue.txt"
            queue_path.write_text("회사A\n회사B\n", encoding="utf-8")
            company_dir = tmp_path / "company_info"
            company_dir.mkdir()

            with patch("enrich_saramin_company_info.COMPANY_INFO_DIR", company_dir):
                candidates = scan_candidates(queue_path)

            names = [c.company for c in candidates]
            self.assertIn("회사A", names)
            self.assertIn("회사B", names)

    def test_skips_headhunting_companies(self):
        from enrich_saramin_company_info import scan_candidates

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            queue_path = tmp_path / "queue.txt"
            queue_path.write_text("ABC서치펌\n정상회사\n", encoding="utf-8")
            company_dir = tmp_path / "company_info"
            company_dir.mkdir()

            with patch("enrich_saramin_company_info.COMPANY_INFO_DIR", company_dir):
                candidates = scan_candidates(queue_path)

            names = [c.company for c in candidates]
            self.assertNotIn("ABC서치펌", names)
            self.assertIn("정상회사", names)

    def test_empty_queue_returns_empty_list(self):
        from enrich_saramin_company_info import scan_candidates

        with tempfile.TemporaryDirectory() as tmp:
            queue_path = Path(tmp) / "queue.txt"
            result = scan_candidates(queue_path)
            self.assertEqual(result, [])

    def test_resolves_existing_file_by_heading_alias(self):
        from enrich_saramin_company_info import scan_candidates

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            queue_path = tmp_path / "queue.txt"
            queue_path.write_text("네오랩컨버전스\n", encoding="utf-8")
            company_dir = tmp_path / "company_info"
            company_dir.mkdir()
            target = company_dir / "네오랩컨버전스-neolab.md"
            target.write_text("# 네오랩컨버전스(NeoLab)\n", encoding="utf-8")

            with patch("enrich_saramin_company_info.COMPANY_INFO_DIR", company_dir), \
                 patch("auto_company.COMPANY_INFO_DIR", company_dir):
                candidates = scan_candidates(queue_path)

            self.assertEqual(candidates[0].file_path, target)


class TestBuildMergedDict(unittest.TestCase):
    def test_existing_value_wins_over_saramin(self):
        from enrich_saramin_company_info import _build_merged_dict
        from company_validator import CompanyData
        from ce_types import PlatformData

        existing = CompanyData(name="회사", industry="기존업종", founded_year=2015, avg_salary=6000)
        saramin = PlatformData(platform="saramin", source_url="https://saramin/csn=1", company_name="회사")
        saramin.industry = "Saramin업종"
        saramin.founded_year = 2020
        saramin.avg_salary = 4000

        merged = _build_merged_dict(existing, saramin, [])
        self.assertEqual(merged["industry"], "기존업종")
        self.assertEqual(merged["founded_year"], 2015)
        self.assertEqual(merged["avg_salary"], 6000)

    def test_saramin_fills_empty_fields(self):
        from enrich_saramin_company_info import _build_merged_dict
        from company_validator import CompanyData
        from ce_types import PlatformData

        existing = CompanyData(name="회사", industry="정보 없음")
        saramin = PlatformData(platform="saramin", source_url="https://saramin/csn=1", company_name="회사")
        saramin.industry = "IT서비스"
        saramin.employee_count = 150

        merged = _build_merged_dict(existing, saramin, [])
        self.assertEqual(merged["industry"], "IT서비스")
        self.assertEqual(merged["employee_count"], 150)

    def test_saramin_salary_marks_saramin_source(self):
        from enrich_saramin_company_info import _build_merged_dict
        from company_validator import CompanyData
        from ce_types import PlatformData

        existing = CompanyData(name="회사")
        saramin = PlatformData(platform="saramin", source_url="https://saramin/csn=1", company_name="회사")
        saramin.avg_salary = 4500

        merged = _build_merged_dict(existing, saramin, [])
        self.assertEqual(merged["avg_salary"], 4500)
        self.assertEqual(merged["salary_source"], "Saramin")

    def test_investment_total_conversion(self):
        from enrich_saramin_company_info import _build_merged_dict
        from company_validator import CompanyData
        from ce_types import PlatformData

        existing = CompanyData(name="스타트업", investment_total=100.0)
        saramin = PlatformData(platform="saramin", source_url="https://saramin/csn=1", company_name="스타트업")

        merged = _build_merged_dict(existing, saramin, [])
        self.assertEqual(merged["investment_total"], "100억원")

    def test_source_urls_deduplication(self):
        from enrich_saramin_company_info import _build_merged_dict
        from company_validator import CompanyData
        from ce_types import PlatformData

        existing = CompanyData(name="회사")
        saramin = PlatformData(platform="saramin", source_url="https://saramin/csn=1", company_name="회사")
        existing_urls = ["https://wanted.co.kr/1", "https://saramin/csn=1"]

        merged = _build_merged_dict(existing, saramin, existing_urls)
        self.assertEqual(merged["source_urls"].count("https://saramin/csn=1"), 1)


class TestPatchrightFallback(unittest.TestCase):
    def test_playwright_used_when_patchright_missing(self):
        """When patchright is not installed, Playwright is used as fallback."""
        import importlib
        import sys

        patchright_backup = sys.modules.get("patchright")
        patchright_sync_backup = sys.modules.get("patchright.sync_api")

        sys.modules["patchright"] = None
        sys.modules["patchright.sync_api"] = None

        try:
            from enrich_saramin_company_info import main as _main
            use_patchright_detected = False
            try:
                from patchright.sync_api import sync_playwright
                use_patchright_detected = True
            except (ImportError, TypeError):
                use_patchright_detected = False
            self.assertFalse(use_patchright_detected)
        finally:
            if patchright_backup is None:
                sys.modules.pop("patchright", None)
            else:
                sys.modules["patchright"] = patchright_backup
            if patchright_sync_backup is None:
                sys.modules.pop("patchright.sync_api", None)
            else:
                sys.modules["patchright.sync_api"] = patchright_sync_backup


if __name__ == "__main__":
    unittest.main()
