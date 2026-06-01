#!/usr/bin/env python3
"""Characterization tests for JD pipeline routing helpers."""

import shutil

import pytest

import pipeline
from pipeline import (
    ProcessResult,
    ProcessedItem,
    classify_file,
    migrate_status,
    process_urls_from_file,
)

RECOMMEND = "\uc9c0\uc6d0 \ucd94\ucc9c"
HOLD = "\uc9c0\uc6d0 \ubcf4\ub958"
REJECT = "\uc9c0\uc6d0 \ube44\ucd94\ucc9c"
FINAL_VERDICT = "\ucd5c\uc885 \ud310\uc815"
VERDICT_LABEL = "\ud310\uc815"


@pytest.fixture
def isolated_pipeline_dirs(tmp_path, monkeypatch):
    job_postings_dir = tmp_path / "job_postings"
    screening_dir = tmp_path / "jd_analysis" / "screening"
    job_postings_dir.mkdir()
    screening_dir.mkdir(parents=True)

    monkeypatch.setattr(pipeline, "JOB_POSTINGS_DIR", job_postings_dir)
    monkeypatch.setattr(pipeline, "SCREENING_DIR", screening_dir)

    def move_to_temp_folder(file_path, target_folder):
        destination = job_postings_dir / target_folder / file_path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if file_path != destination:
            shutil.move(str(file_path), str(destination))
        return destination

    monkeypatch.setattr(pipeline, "move_to_folder", move_to_temp_folder)
    return job_postings_dir, screening_dir


def _jd_with_verdict(verdict):
    return f"# Backend Engineer\n\n## {FINAL_VERDICT}\n> {VERDICT_LABEL}: {verdict}\n"


class TestClassifyFile:
    def test_classifies_embedded_recommend_verdict_to_high_folder(self, isolated_pipeline_dirs):
        job_postings_dir, _ = isolated_pipeline_dirs
        jd_path = job_postings_dir / "123456-acme-backend.md"
        jd_path.write_text(_jd_with_verdict(RECOMMEND), encoding="utf-8")

        result = classify_file(jd_path, dry_run=True)

        assert result == ProcessedItem(
            url_or_path=str(jd_path),
            job_id="123456",
            result=ProcessResult.SUCCESS,
            message=f"[DRY-RUN] {RECOMMEND} \u2192 conditional/high",
            target_folder="conditional/high",
            current_folder="root",
            verdict=RECOMMEND,
            verdict_source="jd",
        )

    def test_uses_matching_screening_file_when_jd_has_no_verdict(self, isolated_pipeline_dirs):
        job_postings_dir, screening_dir = isolated_pipeline_dirs
        jd_path = job_postings_dir / "123457-acme-backend.md"
        jd_path.write_text("# Backend Engineer\n\nNo verdict here.\n", encoding="utf-8")
        screening_path = screening_dir / "123457-acme-backend.md"
        screening_path.write_text(_jd_with_verdict(HOLD), encoding="utf-8")

        result = classify_file(jd_path, dry_run=True)

        assert result.result == ProcessResult.SUCCESS
        assert result.job_id == "123457"
        assert result.target_folder == "conditional/hold"
        assert result.current_folder == "root"
        assert result.verdict == HOLD
        assert result.verdict_source == "screening:123457-acme-backend.md"

    def test_skips_protected_status_even_when_verdict_exists(self, isolated_pipeline_dirs):
        job_postings_dir, _ = isolated_pipeline_dirs
        jd_path = job_postings_dir / "123458-acme-backend.md"
        jd_path.write_text(
            "---\nstatus: applied\n---\n\n" + _jd_with_verdict(RECOMMEND),
            encoding="utf-8",
        )

        result = classify_file(jd_path, dry_run=True)

        assert result.result == ProcessResult.SKIPPED
        assert result.job_id == "123458"
        assert result.current_folder == "root"
        assert result.skip_reason == "protected_status"
        assert result.protected_status == "applied"
        assert result.target_folder is None

    def test_missing_file_returns_error_with_missing_file_reason(self, isolated_pipeline_dirs):
        job_postings_dir, _ = isolated_pipeline_dirs
        missing_path = job_postings_dir / "123459-acme-backend.md"

        result = classify_file(missing_path, dry_run=True)

        assert result.result == ProcessResult.ERROR
        assert result.job_id == "123459"
        assert result.current_folder == "root"
        assert result.skip_reason == "missing_file"

    def test_skips_when_neither_jd_nor_screening_has_verdict(self, isolated_pipeline_dirs):
        job_postings_dir, _ = isolated_pipeline_dirs
        jd_path = job_postings_dir / "123460-acme-backend.md"
        jd_path.write_text("# Backend Engineer\n\nNo verdict here.\n", encoding="utf-8")

        result = classify_file(jd_path, dry_run=True)

        assert result.result == ProcessResult.SKIPPED
        assert result.job_id == "123460"
        assert result.skip_reason == "missing_verdict"
        assert result.target_folder is None

    def test_skips_unmapped_verdict_from_parser(self, isolated_pipeline_dirs, monkeypatch):
        job_postings_dir, _ = isolated_pipeline_dirs
        jd_path = job_postings_dir / "123461-acme-backend.md"
        jd_path.write_text("# Backend Engineer\n\nSynthetic parser output.\n", encoding="utf-8")
        monkeypatch.setattr(pipeline, "parse_verdict_from_screening", lambda _: "unmapped")

        result = classify_file(jd_path, dry_run=True)

        assert result.result == ProcessResult.SKIPPED
        assert result.job_id == "123461"
        assert result.verdict == "unmapped"
        assert result.verdict_source == "jd"
        assert result.skip_reason == "unmapped_verdict"
        assert result.target_folder is None

    def test_real_mode_moves_file_to_classified_folder(self, isolated_pipeline_dirs):
        job_postings_dir, _ = isolated_pipeline_dirs
        jd_path = job_postings_dir / "123462-acme-backend.md"
        jd_path.write_text(_jd_with_verdict(REJECT), encoding="utf-8")

        result = classify_file(jd_path, dry_run=False)

        moved_path = job_postings_dir / "pass" / "123462-acme-backend.md"
        assert result.result == ProcessResult.SUCCESS
        assert result.target_folder == "pass"
        assert result.current_folder == "root"
        assert result.verdict == REJECT
        assert result.message == f"{REJECT} \u2192 pass/123462-acme-backend.md"
        assert not jd_path.exists()
        assert moved_path.read_text(encoding="utf-8") == _jd_with_verdict(REJECT)


class TestMigrateStatus:
    def test_dry_run_reports_status_updates_without_changing_files(self, tmp_path):
        base_dir = tmp_path / "job_postings"
        applied_dir = base_dir / "applied"
        rejected_dir = base_dir / "rejected"
        applied_dir.mkdir(parents=True)
        rejected_dir.mkdir(parents=True)
        applied_file = applied_dir / "111111-acme-backend.md"
        rejected_file = rejected_dir / "222222-beta-backend.md"
        existing_status_file = rejected_dir / "333333-gamma-backend.md"
        applied_file.write_text("# Applied\n", encoding="utf-8")
        rejected_file.write_text("# Rejected\n", encoding="utf-8")
        existing_status_file.write_text("---\nstatus: rejected\n---\n# Existing\n", encoding="utf-8")

        results = migrate_status(base_dir, dry_run=True)

        assert [(item.job_id, item.result) for item in results] == [
            ("111111", ProcessResult.SUCCESS),
            ("222222", ProcessResult.SUCCESS),
            ("333333", ProcessResult.SKIPPED),
        ]
        assert "status:" not in applied_file.read_text(encoding="utf-8")
        assert "status:" not in rejected_file.read_text(encoding="utf-8")

    def test_real_mode_adds_frontmatter_status_from_folder(self, tmp_path):
        base_dir = tmp_path / "job_postings"
        applied_dir = base_dir / "applied"
        rejected_dir = base_dir / "rejected"
        applied_dir.mkdir(parents=True)
        rejected_dir.mkdir(parents=True)
        applied_file = applied_dir / "111111-acme-backend.md"
        rejected_file = rejected_dir / "222222-beta-backend.md"
        applied_file.write_text("# Applied\n", encoding="utf-8")
        rejected_file.write_text("# Rejected\n", encoding="utf-8")

        results = migrate_status(base_dir, dry_run=False)

        assert [(item.job_id, item.result) for item in results] == [
            ("111111", ProcessResult.SUCCESS),
            ("222222", ProcessResult.SUCCESS),
        ]
        assert "status: applied" in applied_file.read_text(encoding="utf-8")
        assert "status: rejected" in rejected_file.read_text(encoding="utf-8")


class TestProcessUrlsFromFile:
    def test_processes_non_empty_non_comment_urls_with_check_url(self, tmp_path, monkeypatch):
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text(
            "\n"
            "# skipped comment\n"
            "https://wanted.co.kr/wd/123456\n"
            "  https://groupby.kr/positions/8807  \n",
            encoding="utf-8",
        )
        seen_urls = []

        def fake_check_url(url):
            seen_urls.append(url)
            return ProcessedItem(
                url_or_path=url,
                job_id=url.rsplit("/", 1)[-1],
                result=ProcessResult.NEEDS_MANUAL,
                message="checked",
            )

        monkeypatch.setattr(pipeline, "check_url", fake_check_url)

        results = process_urls_from_file(urls_file)

        assert seen_urls == [
            "https://wanted.co.kr/wd/123456",
            "https://groupby.kr/positions/8807",
        ]
        assert [item.job_id for item in results] == ["123456", "8807"]
        assert all(item.result == ProcessResult.NEEDS_MANUAL for item in results)

    def test_missing_urls_file_returns_empty_result(self, tmp_path):
        assert process_urls_from_file(tmp_path / "missing.txt") == []
