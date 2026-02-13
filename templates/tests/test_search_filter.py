#!/usr/bin/env python3
"""Tests for search quick_filter_title() in search.py and search_quick.py."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "jd"))

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


if __name__ == "__main__":
    unittest.main()
