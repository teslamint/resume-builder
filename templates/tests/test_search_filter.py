#!/usr/bin/env python3
"""Tests for search filters: quick_filter_title() and experience filtering."""

import unittest
from pathlib import Path

from experience_filter import filter_experience, parse_experience_range
from search import quick_filter_title as search_filter
from search_quick import quick_filter_title as quick_filter


CONFIG = {
    "quick_filters": {
        "title_exclude": ["리더", "팀장", "Lead", "CTO", "인턴"],
        "title_include": [
            "백엔드", "Backend", "Back-end", "Back End",
            "개발자", "Developer", "엔지니어", "Engineer",
            "서버", "Server", "Software",
        ],
        "title_prefer": ["시니어", "Senior"],
    }
}


class TestSearchQuickFilterTitle(unittest.TestCase):
    """search.py quick_filter_title() — returns 'pass' | 'prefer' | None."""

    # --- Include 게이트 ---

    def test_include_passes_backend_korean(self):
        assert search_filter("백엔드 개발 (Senior)", CONFIG) != "pass"

    def test_include_passes_backend_english(self):
        assert search_filter("Backend Engineer(코어)", CONFIG) != "pass"

    def test_include_passes_developer_korean(self):
        assert search_filter("Node.js 개발자", CONFIG) != "pass"

    def test_include_passes_developer_english(self):
        assert search_filter("Python Developer", CONFIG) != "pass"

    def test_include_blocks_planner(self):
        assert search_filter("솔루션 신상품 기획팀(기획/설계)", CONFIG) == "pass"

    def test_include_blocks_bd_manager(self):
        assert search_filter("사업 개발 및 제휴 매니저(Business Development Manager)", CONFIG) == "pass"

    def test_include_blocks_marketing(self):
        assert search_filter("디지털 마케팅 매니저", CONFIG) == "pass"

    # --- Exclude 우선순위 ---

    def test_exclude_overrides_include(self):
        assert search_filter("백엔드 팀장", CONFIG) == "pass"

    def test_exclude_lead_title(self):
        assert search_filter("Backend Lead Engineer", CONFIG) == "pass"

    # --- Prefer ---

    def test_prefer_senior_korean(self):
        assert search_filter("시니어 백엔드 엔지니어", CONFIG) == "prefer"

    def test_prefer_senior_english(self):
        assert search_filter("Senior Backend Engineer", CONFIG) == "prefer"

    # --- 빈 include = 비활성 (하위 호환) ---

    def test_empty_include_passes_all(self):
        config = {"quick_filters": {"title_exclude": [], "title_include": []}}
        assert search_filter("아무 제목이나", config) is None

    def test_no_include_key_passes_all(self):
        config = {"quick_filters": {"title_exclude": []}}
        assert search_filter("아무 제목이나", config) is None

    # --- 배치 회귀 ---

    def test_batch_regression_meatbox(self):
        assert search_filter("Back-end 개발자(시니어)", CONFIG) == "prefer"

    def test_batch_regression_ridi(self):
        assert search_filter("Backend Engineer", CONFIG) is None

    def test_batch_regression_rga_researcher(self):
        assert search_filter("상황 인식/음성 AI 연구·개발자", CONFIG) != "pass"

    def test_batch_regression_broadcast(self):
        assert search_filter("송출 시스템 개발(2년 이상)", CONFIG) == "pass"


class TestSearchQuickQuickFilterTitle(unittest.TestCase):
    """search_quick.py quick_filter_title() — returns True (skip) | False (pass)."""

    # --- Include 게이트 ---

    def test_include_passes_backend_korean(self):
        assert quick_filter("백엔드 개발 (Senior)", CONFIG) is False

    def test_include_passes_backend_english(self):
        assert quick_filter("Backend Engineer(코어)", CONFIG) is False

    def test_include_passes_developer_korean(self):
        assert quick_filter("Node.js 개발자", CONFIG) is False

    def test_include_passes_developer_english(self):
        assert quick_filter("Python Developer", CONFIG) is False

    def test_include_blocks_planner(self):
        assert quick_filter("솔루션 신상품 기획팀(기획/설계)", CONFIG) is True

    def test_include_blocks_bd_manager(self):
        assert quick_filter("사업 개발 및 제휴 매니저(Business Development Manager)", CONFIG) is True

    def test_include_blocks_marketing(self):
        assert quick_filter("디지털 마케팅 매니저", CONFIG) is True

    # --- Exclude 우선순위 ---

    def test_exclude_overrides_include(self):
        assert quick_filter("백엔드 팀장", CONFIG) is True

    def test_exclude_lead_title(self):
        assert quick_filter("Backend Lead Engineer", CONFIG) is True

    # --- 빈 include = 비활성 (하위 호환) ---

    def test_empty_include_passes_all(self):
        config = {"quick_filters": {"title_exclude": [], "title_include": []}}
        assert quick_filter("아무 제목이나", config) is False

    def test_no_include_key_passes_all(self):
        config = {"quick_filters": {"title_exclude": []}}
        assert quick_filter("아무 제목이나", config) is False

    # --- 배치 회귀 ---

    def test_batch_regression_meatbox(self):
        assert quick_filter("Back-end 개발자(시니어)", CONFIG) is False

    def test_batch_regression_ridi(self):
        assert quick_filter("Backend Engineer", CONFIG) is False

    def test_batch_regression_rga_researcher(self):
        assert quick_filter("상황 인식/음성 AI 연구·개발자", CONFIG) is False

    def test_batch_regression_broadcast(self):
        assert quick_filter("송출 시스템 개발(2년 이상)", CONFIG) is True


FILTER_CONFIG = {
    "filters": {
        "min_experience_upper": 14,
        "max_experience": 15,
    }
}


class TestParseExperienceRange(unittest.TestCase):
    """parse_experience_range() — Korean experience string → (min, max) tuple."""

    def test_range_hyphen(self):
        assert parse_experience_range("경력 5-10년") == (5, 10)

    def test_range_tilde(self):
        assert parse_experience_range("5~10년") == (5, 10)

    def test_range_remember_cha_suffix(self):
        assert parse_experience_range("3년~9년 차") == (3, 9)

    def test_range_unrealistic_max(self):
        assert parse_experience_range("5~100년") == (5, None)

    def test_compound_range(self):
        assert parse_experience_range("경력 7년 이상 14년 이하") == (7, 14)

    def test_compound_range_miman(self):
        assert parse_experience_range("5년 이상 15년 미만") == (5, 14)

    def test_compound_range_tilde_separator(self):
        assert parse_experience_range("경력 8년 이상 ~ 12년 이하") == (8, 12)

    def test_compound_range_tilde_miman(self):
        assert parse_experience_range("경력 2년 이상 ~ 5년 미만") == (2, 4)

    def test_open_ended_arrow(self):
        assert parse_experience_range("경력 3년↑") == (3, None)

    def test_open_ended_isang(self):
        assert parse_experience_range("3년 이상") == (3, None)

    def test_open_ended_plus(self):
        assert parse_experience_range("5년+") == (5, None)

    def test_markdown_bold(self):
        assert parse_experience_range("**5년 이상**") == (5, None)

    def test_exact(self):
        assert parse_experience_range("경력 3년") == (3, 3)

    def test_career_only(self):
        assert parse_experience_range("경력") == (None, None)

    def test_mugwan(self):
        assert parse_experience_range("경력 무관") == (None, None)

    def test_empty(self):
        assert parse_experience_range("") == (None, None)

    def test_none(self):
        assert parse_experience_range(None) == (None, None)

    def test_sinip_career_no_false_match(self):
        assert parse_experience_range("신입/경력") == (None, None)

    def test_cha_isang(self):
        assert parse_experience_range("경력 3년차 이상") == (3, None)

    def test_mixed_sinip_career_range(self):
        assert parse_experience_range("신입/경력 3년 이상") == (3, None)

    def test_compound_unrealistic_max(self):
        assert parse_experience_range("3년 이상 999년 이하") == (3, None)

    def test_upper_only_iha(self):
        assert parse_experience_range("경력 5년 이하") == (None, 5)

    def test_upper_only_miman(self):
        assert parse_experience_range("10년 미만") == (None, 9)

    def test_upper_only_with_prefix(self):
        assert parse_experience_range("경력 10년 미만") == (None, 9)

    def test_upper_only_cha_suffix(self):
        assert parse_experience_range("10년차 이하") == (None, 10)

    def test_compound_not_false_captured(self):
        assert parse_experience_range("5년 이상 15년 미만") == (5, 14)


class TestFilterExperience(unittest.TestCase):
    """filter_experience() — returns True if JD should be skipped."""

    def test_skip_low_upper(self):
        assert filter_experience("경력 5-12년", FILTER_CONFIG) is True

    def test_keep_sufficient_upper(self):
        assert filter_experience("경력 5-15년", FILTER_CONFIG) is False

    def test_keep_open_ended_low_min(self):
        assert filter_experience("경력 3년↑", FILTER_CONFIG) is False

    def test_skip_high_min_open_ended(self):
        assert filter_experience("경력 20년 이상", FILTER_CONFIG) is True

    def test_skip_high_min_range(self):
        assert filter_experience("경력 16-20년", FILTER_CONFIG) is True

    def test_skip_remember_cha_low_upper(self):
        assert filter_experience("3년~9년 차", FILTER_CONFIG) is True

    def test_keep_unrealistic_max(self):
        assert filter_experience("5~100년", FILTER_CONFIG) is False

    def test_keep_mugwan(self):
        assert filter_experience("경력 무관", FILTER_CONFIG) is False

    def test_keep_empty(self):
        assert filter_experience("", FILTER_CONFIG) is False

    def test_no_max_experience_config(self):
        config = {"filters": {"min_experience_upper": 14}}
        assert filter_experience("경력 20년 이상", config) is False

    def test_exact_boundary(self):
        assert filter_experience("경력 5-14년", FILTER_CONFIG) is False

    def test_exact_max_boundary(self):
        assert filter_experience("경력 15년 이상", FILTER_CONFIG) is False

    def test_over_max_boundary(self):
        assert filter_experience("경력 16년 이상", FILTER_CONFIG) is True

    def test_exact_at_min_upper(self):
        assert filter_experience("경력 14년", FILTER_CONFIG) is False

    def test_empty_config_defaults_apply(self):
        # empty config → default min_experience_upper=14, max 12 < 14 → skip
        assert filter_experience("경력 5-12년", {}) is True

    def test_empty_config_passes_sufficient_range(self):
        assert filter_experience("경력 5-15년", {}) is False

    def test_skip_upper_only_low(self):
        assert filter_experience("경력 5년 이하", FILTER_CONFIG) is True

    def test_keep_upper_only_sufficient(self):
        assert filter_experience("경력 15년 이하", FILTER_CONFIG) is False

    def test_skip_upper_only_miman(self):
        assert filter_experience("10년 미만", FILTER_CONFIG) is True

    def test_keep_upper_only_miman_sufficient(self):
        assert filter_experience("15년 미만", FILTER_CONFIG) is False


if __name__ == "__main__":
    unittest.main()
