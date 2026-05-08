#!/usr/bin/env python3
"""Tests for domain_filter module."""

import textwrap
from pathlib import Path

import pytest

from templates.jd.domain_filter import (
    DomainMatch,
    detect_from_filename,
    detect_from_position,
    detect_from_screening,
    has_counter_indicator,
    classify_domain,
    scan_folder,
)


class TestDetectFromScreening:
    def test_domain_mismatch_basic(self):
        assert detect_from_screening("도메인 불일치") == "domain_mismatch"

    def test_domain_mismatch_with_cut(self):
        assert detect_from_screening("**도메인 불일치 (즉시 컷)**") == "domain_mismatch"

    def test_domain_differs(self):
        assert detect_from_screening("도메인 자체가 다름") == "domain_mismatch"

    def test_domain_cut(self):
        assert detect_from_screening("도메인 컷으로 평가 불필요") == "domain_mismatch"

    def test_domain_match_not_triggered(self):
        assert detect_from_screening("도메인 일치: 백엔드") is None

    def test_no_domain_text(self):
        assert detect_from_screening("연봉 미달로 지원 비추천") is None


class TestDetectFromPosition:
    @pytest.mark.parametrize("position,expected_cat", [
        ("iOS 개발자", "mobile"),
        ("Android Engineer", "mobile"),
        ("Flutter Developer", "mobile"),
        ("모바일 앱 개발자", "mobile"),
        ("ML Engineer", "ai_ml"),
        ("MLOps 엔지니어", "ai_ml"),
        ("AI Engineer", "ai_ml"),
        ("Embedded Systems Engineer", "hardware_embedded"),
        ("FPGA Engineer", "hardware_embedded"),
        ("DevOps Engineer", "devops_sre"),
        ("SRE", "devops_sre"),
        ("Frontend Developer", "frontend"),
        ("프론트엔드 개발자", "frontend"),
        ("Data Engineer", "data_engineering"),
        ("데이터 엔지니어", "data_engineering"),
        ("QA Engineer", "qa_pm"),
        ("Product Manager", "qa_pm"),
    ])
    def test_positive_matches(self, position, expected_cat):
        result = detect_from_position(position)
        assert result is not None
        assert result.category == expected_cat

    @pytest.mark.parametrize("position", [
        "Backend Developer",
        "서버 개발자",
        "백엔드 엔지니어",
        "Software Engineer",
        "Java Developer",
    ])
    def test_backend_not_matched(self, position):
        assert detect_from_position(position) is None


class TestDetectFromFilename:
    @pytest.mark.parametrize("filename,expected_cat", [
        ("123456-company-ios-개발자.md", "mobile"),
        ("123456-company-android-developer.md", "mobile"),
        ("123456-company-flutter-engineer.md", "mobile"),
        ("123456-company-react-native-dev.md", "mobile"),
        ("123456-company-mlops-engineer.md", "ai_ml"),
        ("123456-company-embedded-engineer.md", "hardware_embedded"),
        ("123456-company-fpga-engineer.md", "hardware_embedded"),
        ("123456-company-devops-engineer.md", "devops_sre"),
        ("123456-company-sre-engineer.md", "devops_sre"),
        ("123456-company-frontend-developer.md", "frontend"),
        ("123456-company-front-end-engineer.md", "frontend"),
        ("123456-company-프론트-개발자.md", "frontend"),
        ("123456-company-data-engineer-senior.md", "data_engineering"),
        ("123456-company-데이터-엔지니어.md", "data_engineering"),
        ("123456-company-qa-engineer.md", "qa_pm"),
    ])
    def test_positive_matches(self, filename, expected_cat):
        result = detect_from_filename(filename)
        assert result is not None, f"Expected {expected_cat} for {filename}"
        assert result.category == expected_cat

    @pytest.mark.parametrize("filename", [
        "123456-company-backend-developer.md",
        "123456-company-서버-개발자.md",
        "123456-company-java-engineer.md",
        "123456-company-데이터베이스-엔지니어.md",
    ])
    def test_backend_not_matched(self, filename):
        assert detect_from_filename(filename) is None

    def test_pm_pl_grade_not_matched(self):
        """pm-pl급 is a developer grade, not Product Manager."""
        result = detect_from_filename("116149-에이엘에이엔-backend-개발자-pm-pl급.md")
        assert result is None or result.category != "qa_pm"


class TestCounterIndicator:
    def test_backend_in_filename(self):
        assert has_counter_indicator("mlops-플랫폼-백엔드-개발자.md", None) is True

    def test_server_in_filename(self):
        assert has_counter_indicator("ai-backend-engineer.md", None) is True

    def test_backend_in_position(self):
        assert has_counter_indicator("mlops-engineer.md", "MLOps 백엔드 개발자") is True

    def test_no_counter_indicator(self):
        assert has_counter_indicator("mlops-engineer.md", "MLOps Engineer") is False

    def test_fullstack_blocks_frontend(self):
        assert has_counter_indicator("fullstack-engineer.md", None, "frontend") is True

    def test_category_specific_counter(self):
        assert has_counter_indicator("data-engineer.md", "Data Engineer 서버", "data_engineering") is True


class TestClassifyDomain:
    def test_backend_jd_skipped(self, tmp_path):
        jd = tmp_path / "123456-company-backend-developer.md"
        jd.write_text("| 포지션 | Backend Developer |", encoding="utf-8")
        result = classify_domain(jd)
        assert result.action == "skip"

    def test_protected_status_skipped(self, tmp_path):
        jd = tmp_path / "123456-company-ios-developer.md"
        jd.write_text("---\nstatus: applied\n---\n| 포지션 | iOS Developer |", encoding="utf-8")
        result = classify_domain(jd)
        assert result.action == "skip"
        assert "보호된 상태" in result.reason

    def test_non_backend_detected(self, tmp_path):
        jd = tmp_path / "123456-company-ios-개발자.md"
        jd.write_text("| 포지션 | iOS 개발자 |", encoding="utf-8")
        result = classify_domain(jd)
        assert result.action == "delete"
        assert result.category == "mobile"

    def test_counter_indicator_needs_manual(self, tmp_path):
        jd = tmp_path / "123456-company-모바일-백엔드-개발자.md"
        jd.write_text("| 포지션 | 모바일 백엔드 개발자 |", encoding="utf-8")
        result = classify_domain(jd)
        assert result.action == "needs_manual"

    def test_data_engineer_deleted(self, tmp_path):
        jd = tmp_path / "123456-company-data-engineer.md"
        jd.write_text("| 포지션 | Data Engineer |", encoding="utf-8")
        result = classify_domain(jd)
        assert result.action == "delete"
        assert result.category == "data_engineering"


class TestScanFolder:
    def test_scan_empty_folder(self, tmp_path):
        results = scan_folder(tmp_path, dry_run=True)
        assert results == []

    def test_scan_with_mixed_files(self, tmp_path):
        (tmp_path / "111111-company-backend-dev.md").write_text(
            "| 포지션 | Backend Developer |", encoding="utf-8")
        (tmp_path / "222222-company-ios-dev.md").write_text(
            "| 포지션 | iOS Developer |", encoding="utf-8")
        (tmp_path / "333333-company-data-engineer.md").write_text(
            "| 포지션 | Data Engineer |", encoding="utf-8")

        results = scan_folder(tmp_path, dry_run=True)
        assert len(results) == 2
        actions = {Path(r.jd_path).name: r.action for r in results}
        assert actions["222222-company-ios-dev.md"] == "delete"
        assert actions["333333-company-data-engineer.md"] == "delete"

    def test_scan_dry_run_no_delete(self, tmp_path):
        jd = tmp_path / "222222-company-ios-dev.md"
        jd.write_text("| 포지션 | iOS Developer |", encoding="utf-8")
        scan_folder(tmp_path, dry_run=True)
        assert jd.exists()

    def test_scan_delete_mode(self, tmp_path):
        jd = tmp_path / "222222-company-ios-dev.md"
        jd.write_text("| 포지션 | iOS Developer |", encoding="utf-8")
        scan_folder(tmp_path, dry_run=False, delete=True)
        assert not jd.exists()

    def test_backend_jd_survives_deletion(self, tmp_path):
        """Backend JD in pass/ (rejected for non-domain reasons) must survive."""
        jd = tmp_path / "290025-데이터라이즈-backend-engineer.md"
        jd.write_text("| 포지션 | Backend Engineer |", encoding="utf-8")
        scan_folder(tmp_path, dry_run=False, delete=True)
        assert jd.exists()
