#!/usr/bin/env python3
"""Tests for the Obsidian dashboard sync script."""

import importlib.util
from pathlib import Path


def _load_sync_dashboard_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "scripts" / "sync_dashboard.py"
    spec = importlib.util.spec_from_file_location("sync_dashboard", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scan_job_postings_excludes_retired_conditional_tier_buckets(tmp_path, monkeypatch):
    sync_dashboard = _load_sync_dashboard_module()
    monkeypatch.setattr(sync_dashboard, "JOB_POSTINGS", tmp_path)

    for folder, filename in (
        ("conditional/high", "111-high-backend.md"),
        ("conditional/hold", "222-hold-backend.md"),
        ("conditional/middle", "333-middle-backend.md"),
        ("conditional/low", "444-low-backend.md"),
    ):
        path = tmp_path / folder
        path.mkdir(parents=True)
        (path / filename).write_text("# JD\n", encoding="utf-8")

    jobs = sync_dashboard.scan_job_postings()

    assert "111" in jobs
    assert "222" in jobs
    assert "333" not in jobs
    assert "444" not in jobs


def test_from_obsidian_resolves_retired_conditional_tier_buckets_for_moves(
    tmp_path,
    monkeypatch,
):
    sync_dashboard = _load_sync_dashboard_module()
    monkeypatch.setattr(sync_dashboard, "JOB_POSTINGS", tmp_path / "job_postings")

    retired_dir = sync_dashboard.JOB_POSTINGS / "conditional" / "middle"
    retired_dir.mkdir(parents=True)
    source = retired_dir / "333-middle-backend.md"
    source.write_text("# JD\n", encoding="utf-8")

    dashboard = tmp_path / "dashboard.md"
    dashboard.write_text(
        "\n".join(
            [
                "| ID | 회사 | 포지션 | 최종 판단 | 핵심 사유 |",
                "| --- | --- | --- | --- | --- |",
                "| 333 | MiddleCo | Backend | 지원 | dashboard update |",
            ]
        ),
        encoding="utf-8",
    )

    sync_dashboard.from_obsidian(dry_run=False, dashboard_path=dashboard)

    target = sync_dashboard.JOB_POSTINGS / "applied" / source.name
    assert not source.exists()
    assert target.exists()


def test_from_obsidian_prefers_active_posting_over_retired_lookup_copy(
    tmp_path,
    monkeypatch,
):
    sync_dashboard = _load_sync_dashboard_module()
    monkeypatch.setattr(sync_dashboard, "JOB_POSTINGS", tmp_path / "job_postings")

    active_dir = sync_dashboard.JOB_POSTINGS / "pass"
    retired_dir = sync_dashboard.JOB_POSTINGS / "conditional" / "middle"
    active_dir.mkdir(parents=True)
    retired_dir.mkdir(parents=True)

    active = active_dir / "333-active-backend.md"
    retired = retired_dir / "333-retired-backend.md"
    active.write_text("# Active JD\n", encoding="utf-8")
    retired.write_text("# Retired JD\n", encoding="utf-8")

    dashboard = tmp_path / "dashboard.md"
    dashboard.write_text(
        "\n".join(
            [
                "| ID | 회사 | 포지션 | 최종 판단 | 핵심 사유 |",
                "| --- | --- | --- | --- | --- |",
                "| 333 | ActiveCo | Backend | 지원 | dashboard update |",
            ]
        ),
        encoding="utf-8",
    )

    sync_dashboard.from_obsidian(dry_run=False, dashboard_path=dashboard)

    assert not active.exists()
    assert (sync_dashboard.JOB_POSTINGS / "applied" / active.name).exists()
    assert retired.exists()


def test_to_obsidian_prunes_dashboard_rows_absent_from_active_scan(tmp_path, monkeypatch):
    sync_dashboard = _load_sync_dashboard_module()
    monkeypatch.setattr(sync_dashboard, "JOB_POSTINGS", tmp_path / "job_postings")

    retired_dir = sync_dashboard.JOB_POSTINGS / "conditional" / "middle"
    retired_dir.mkdir(parents=True)
    (retired_dir / "333-retired-backend.md").write_text("# Retired JD\n", encoding="utf-8")

    dashboard = tmp_path / "dashboard.md"
    dashboard.write_text(
        "\n".join(
            [
                "# Jobs",
                "## 📊 지원 현황 요약",
                "| **ID** / 플랫폼 | **회사** | **포지션** | **최종 판단** | **핵심 사유 요약** |",
                "| --- | --- | --- | --- | --- |",
                "| - | - | - | - | - |",
                "## 검토 현황 요약",
                "| **ID** / 플랫폼 | **회사** | **포지션** | **최종 판단** | **핵심 사유 요약** |",
                "| --- | --- | --- | --- | --- |",
                "| [333](https://example.com/333) / - | RetiredCo | Backend | 검토중 | stale retired row |",
                "| 444 / - | RetiredPlainCo | Backend | 검토중 | stale retired plain row |",
                "## 🧠 판단 기준",
                "criteria",
            ]
        ),
        encoding="utf-8",
    )

    sync_dashboard.to_obsidian(dry_run=False, force=False, dashboard_path=dashboard)

    updated = dashboard.read_text(encoding="utf-8")
    assert "333" not in updated
    assert "444" not in updated


def test_to_obsidian_preserves_active_id_rows_when_url_is_missing(
    tmp_path,
    monkeypatch,
):
    sync_dashboard = _load_sync_dashboard_module()
    monkeypatch.setattr(sync_dashboard, "JOB_POSTINGS", tmp_path / "job_postings")

    pass_dir = sync_dashboard.JOB_POSTINGS / "pass"
    pass_dir.mkdir(parents=True)
    (pass_dir / "333-active-backend.md").write_text("# Active JD\n", encoding="utf-8")

    dashboard = tmp_path / "dashboard.md"
    dashboard.write_text(
        "\n".join(
            [
                "# Jobs",
                "## 📊 지원 현황 요약",
                "| **ID** / 플랫폼 | **회사** | **포지션** | **최종 판단** | **핵심 사유 요약** |",
                "| --- | --- | --- | --- | --- |",
                "| - | - | - | - | - |",
                "## 검토 현황 요약",
                "| **ID** / 플랫폼 | **회사** | **포지션** | **최종 판단** | **핵심 사유 요약** |",
                "| --- | --- | --- | --- | --- |",
                "| [333](https://example.com/333) / - | ManualCo | Manual Role | 수동 상태 | keep this reason |",
                "## 🧠 판단 기준",
                "criteria",
            ]
        ),
        encoding="utf-8",
    )

    sync_dashboard.to_obsidian(dry_run=False, force=False, dashboard_path=dashboard)

    updated = dashboard.read_text(encoding="utf-8")
    assert "[333](https://example.com/333)" in updated
    assert "keep this reason" in updated
    assert "333 / -" not in updated


def test_to_obsidian_adds_active_plain_id_rows_when_url_is_missing(
    tmp_path,
    monkeypatch,
):
    sync_dashboard = _load_sync_dashboard_module()
    monkeypatch.setattr(sync_dashboard, "JOB_POSTINGS", tmp_path / "job_postings")

    pass_dir = sync_dashboard.JOB_POSTINGS / "pass"
    pass_dir.mkdir(parents=True)
    (pass_dir / "444-active-backend.md").write_text(
        "\n".join(
            [
                "---",
                "company: PlainIdCo",
                "position: Backend",
                "status: 패스",
                "reason: active without URL",
                "---",
                "# Active JD",
            ]
        ),
        encoding="utf-8",
    )

    dashboard = tmp_path / "dashboard.md"
    dashboard.write_text(
        "\n".join(
            [
                "# Jobs",
                "## 📊 지원 현황 요약",
                "| **ID** / 플랫폼 | **회사** | **포지션** | **최종 판단** | **핵심 사유 요약** |",
                "| --- | --- | --- | --- | --- |",
                "| - | - | - | - | - |",
                "## 검토 현황 요약",
                "| **ID** / 플랫폼 | **회사** | **포지션** | **최종 판단** | **핵심 사유 요약** |",
                "| --- | --- | --- | --- | --- |",
                "| - | - | - | - | - |",
                "## 🧠 판단 기준",
                "criteria",
            ]
        ),
        encoding="utf-8",
    )

    sync_dashboard.to_obsidian(dry_run=False, force=False, dashboard_path=dashboard)

    updated = dashboard.read_text(encoding="utf-8")
    assert "444 / -" in updated
    assert "PlainIdCo" in updated
    assert "active without URL" in updated


def test_to_obsidian_upgrades_legacy_anonymous_rows_when_plain_id_is_generated(
    tmp_path,
    monkeypatch,
):
    sync_dashboard = _load_sync_dashboard_module()
    monkeypatch.setattr(sync_dashboard, "JOB_POSTINGS", tmp_path / "job_postings")

    pass_dir = sync_dashboard.JOB_POSTINGS / "pass"
    pass_dir.mkdir(parents=True)
    (pass_dir / "555-active-backend.md").write_text(
        "\n".join(
            [
                "---",
                "company: LegacyNoUrlCo",
                "position: Backend",
                "status: 패스",
                "reason: generated reason",
                "---",
                "# Active JD",
            ]
        ),
        encoding="utf-8",
    )

    dashboard = tmp_path / "dashboard.md"
    dashboard.write_text(
        "\n".join(
            [
                "# Jobs",
                "## 📊 지원 현황 요약",
                "| **ID** / 플랫폼 | **회사** | **포지션** | **최종 판단** | **핵심 사유 요약** |",
                "| --- | --- | --- | --- | --- |",
                "| - | - | - | - | - |",
                "## 검토 현황 요약",
                "| **ID** / 플랫폼 | **회사** | **포지션** | **최종 판단** | **핵심 사유 요약** |",
                "| --- | --- | --- | --- | --- |",
                "| - / - | LegacyNoUrlCo | Backend | 수동 상태 | keep manual reason |",
                "## 🧠 판단 기준",
                "criteria",
            ]
        ),
        encoding="utf-8",
    )

    sync_dashboard.to_obsidian(dry_run=False, force=False, dashboard_path=dashboard)

    updated = dashboard.read_text(encoding="utf-8")
    assert "555 / -" in updated
    assert "수동 상태" in updated
    assert "keep manual reason" in updated
    assert "- / - | LegacyNoUrlCo" not in updated
    assert updated.count("LegacyNoUrlCo") == 1


def test_to_obsidian_prunes_anonymous_retired_rows_absent_from_active_scan(
    tmp_path,
    monkeypatch,
):
    sync_dashboard = _load_sync_dashboard_module()
    monkeypatch.setattr(sync_dashboard, "JOB_POSTINGS", tmp_path / "job_postings")

    retired_dir = sync_dashboard.JOB_POSTINGS / "conditional" / "middle"
    retired_dir.mkdir(parents=True)
    (retired_dir / "legacy-no-id-backend.md").write_text("# Retired JD\n", encoding="utf-8")

    dashboard = tmp_path / "dashboard.md"
    dashboard.write_text(
        "\n".join(
            [
                "# Jobs",
                "## 📊 지원 현황 요약",
                "| **ID** / 플랫폼 | **회사** | **포지션** | **최종 판단** | **핵심 사유 요약** |",
                "| --- | --- | --- | --- | --- |",
                "| - | - | - | - | - |",
                "## 검토 현황 요약",
                "| **ID** / 플랫폼 | **회사** | **포지션** | **최종 판단** | **핵심 사유 요약** |",
                "| --- | --- | --- | --- | --- |",
                "| - / - | RetiredAnonCo | Backend | 검토중 | stale anonymous retired row |",
                "## 🧠 판단 기준",
                "criteria",
            ]
        ),
        encoding="utf-8",
    )

    sync_dashboard.to_obsidian(dry_run=False, force=False, dashboard_path=dashboard)

    updated = dashboard.read_text(encoding="utf-8")
    assert "RetiredAnonCo" not in updated
    assert "stale anonymous retired row" not in updated
