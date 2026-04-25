#!/usr/bin/env python3
"""Tests for JD audit hypothesis helpers."""

import csv
from pathlib import Path

import audit_hypotheses as audit


def test_salary_tier_prefers_t1_when_t2_phrase_is_also_present():
    text = """
    최종 판정: 🔴 지원 비추천
    연봉 구조 ❌ 평균 연봉 **6,000만원** (Wanted)
    시니어 연봉 추정 × 1.5 적용 시 하한 미달
    """

    result = audit.classify_salary_tier(text)

    assert result["has_salary_cut"] is True
    assert result["t1"] is True
    assert result["t2"] is True
    assert result["tier"] == "T1"


def test_load_file_locations_includes_all_tracked_posting_folders(tmp_path, monkeypatch):
    folder_map = {
        "hold": (
            tmp_path / "conditional",
            tmp_path / "conditional" / "hold",
        ),
        "middle": tmp_path / "conditional" / "middle",
        "low": tmp_path / "conditional" / "low",
        "rejected": tmp_path / "rejected",
    }
    for label, paths in folder_map.items():
        if isinstance(paths, Path):
            paths = (paths,)
        for folder in paths:
            folder.mkdir(parents=True)
            (folder / f"123-{label}-{folder.name}-backend.md").write_text(
                "# JD\n",
                encoding="utf-8",
            )

    monkeypatch.setattr(audit, "JOB_POSTING_DIRS", folder_map)

    locations = audit.load_file_locations()

    assert locations["123-hold-conditional-backend.md"] == "hold"
    assert locations["123-hold-hold-backend.md"] == "hold"
    assert locations["123-middle-middle-backend.md"] == "middle"
    assert locations["123-low-low-backend.md"] == "low"
    assert locations["123-rejected-rejected-backend.md"] == "rejected"


def test_pass_folder_cut_scope_uses_folder_ground_truth():
    assert audit.is_pass_folder_cut("pass") is True
    assert audit.is_pass_folder_cut("hold") is False


def test_main_counts_pass_folder_cut_even_with_stale_screening_verdict(tmp_path, monkeypatch):
    repo_root = tmp_path
    screening_dir = repo_root / "private" / "jd_analysis" / "screening"
    company_dir = repo_root / "private" / "company_info"
    pass_dir = repo_root / "private" / "job_postings" / "pass"
    screening_dir.mkdir(parents=True)
    company_dir.mkdir(parents=True)
    pass_dir.mkdir(parents=True)

    filename = "123-acme-backend.md"
    (pass_dir / filename).write_text("# JD\n", encoding="utf-8")
    (screening_dir / filename).write_text(
        """
        최종 판정: 🟡 지원 보류
        연봉 구조 ❌ 평균 연봉 **6,000만원**
        """,
        encoding="utf-8",
    )
    (screening_dir / "SUMMARY.md").write_text("", encoding="utf-8")
    (company_dir / "acme.md").write_text(
        """
        # Acme
        평균 연봉 **6,000만원**
        현재 인원 10명
        매출액 1억
        현재 라운드 Seed
        """,
        encoding="utf-8",
    )

    monkeypatch.setattr(audit, "REPO_ROOT", repo_root)
    monkeypatch.setattr(audit, "SCREENING_DIR", screening_dir)
    monkeypatch.setattr(audit, "COMPANY_INFO_DIR", company_dir)
    monkeypatch.setattr(audit, "SUMMARY_MD", screening_dir / "SUMMARY.md")
    monkeypatch.setattr(audit, "JOB_POSTING_DIRS", {"pass": pass_dir})

    assert audit.main() == 0

    h1_path = next((repo_root / "private" / "jd_analysis").glob("r2_h1_company_info_gaps_*.csv"))
    h2_path = next((repo_root / "private" / "jd_analysis").glob("r2_h2_salary_evidence_*.csv"))
    h1_rows = list(csv.DictReader(h1_path.open(encoding="utf-8")))
    h2_rows = list(csv.DictReader(h2_path.open(encoding="utf-8")))

    assert [row["filename"] for row in h1_rows] == [filename]
    assert [row["filename"] for row in h2_rows] == [filename]
    assert h2_rows[0]["tier"] == "T1"
