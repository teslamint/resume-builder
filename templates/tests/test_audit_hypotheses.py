#!/usr/bin/env python3
"""Tests for JD audit hypothesis helpers."""

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
        "middle": tmp_path / "conditional" / "middle",
        "low": tmp_path / "conditional" / "low",
        "rejected": tmp_path / "rejected",
    }
    for label, folder in folder_map.items():
        folder.mkdir(parents=True)
        (folder / f"123-{label}-backend.md").write_text("# JD\n", encoding="utf-8")

    monkeypatch.setattr(audit, "JOB_POSTING_DIRS", folder_map)

    locations = audit.load_file_locations()

    assert locations["123-middle-backend.md"] == "middle"
    assert locations["123-low-backend.md"] == "low"
    assert locations["123-rejected-backend.md"] == "rejected"
