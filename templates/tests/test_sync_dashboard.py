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
