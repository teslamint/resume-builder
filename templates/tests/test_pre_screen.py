#!/usr/bin/env python3
"""Tests for pre_screen module — 4-tier LLM short-circuit."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).parent.parent / "jd"
sys.path.insert(0, str(ROOT))


class TestPreScreenJD(unittest.TestCase):
    def _make_jd(self, tmp: Path, name: str, body: str) -> Path:
        p = tmp / name
        p.write_text(body, encoding="utf-8")
        return p

    def test_closed_marker_hits_first(self):
        from pre_screen import pre_screen_jd
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            jd = self._make_jd(tmp, "111-x-be.md",
                "# Backend\n채용 마감\n## 포지션\nBackend Engineer")
            cfg = {"quick_filters": {"title_include": ["Backend"], "title_exclude": []}}
            with patch("pre_screen.classify_domain") as mock_dom:
                r = pre_screen_jd(jd, cfg)
            self.assertTrue(r.hit)
            self.assertEqual(r.reason_code, "closed")
            self.assertEqual(r.target_folder, "closed")
            mock_dom.assert_not_called()

    def test_title_exclude_hits_after_closed(self):
        from pre_screen import pre_screen_jd
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            jd = self._make_jd(tmp, "222-x-frontend.md",
                "# Frontend\n## 기본 정보\n\n| 항목 | 내용 |\n|------|------|\n| 포지션 | 프론트엔드 개발자 |")
            cfg = {"quick_filters": {
                "title_include": ["Backend", "프론트엔드"],
                "title_exclude": ["프론트엔드"],
            }}
            with patch("pre_screen._check_prior_application", return_value=None):
                r = pre_screen_jd(jd, cfg)
            self.assertTrue(r.hit)
            self.assertEqual(r.reason_code, "title_exclude")
            self.assertEqual(r.target_folder, "pass")

    def test_domain_delete_action(self):
        from pre_screen import pre_screen_jd
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            jd = self._make_jd(tmp, "333-x-ios.md",
                "# iOS\n## 기본 정보\n\n| 항목 | 내용 |\n|------|------|\n| 포지션 | iOS Developer |")
            cfg = {"quick_filters": {"title_include": [], "title_exclude": []}}
            mock_cls = MagicMock(action="delete", category="mobile",
                                 tier_used=2, reason="position: iOS")
            with patch("pre_screen._check_prior_application", return_value=None), \
                 patch("pre_screen.classify_domain", return_value=mock_cls):
                r = pre_screen_jd(jd, cfg)
            self.assertTrue(r.hit)
            self.assertEqual(r.reason_code, "domain_mobile")
            self.assertEqual(r.target_folder, "pass")
            self.assertFalse(r.is_review)

    def test_domain_needs_manual_routes_to_review(self):
        from pre_screen import pre_screen_jd
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            jd = self._make_jd(tmp, "444-x-frontend-be.md",
                "# Frontend\n## 기본 정보\n\n| 항목 | 내용 |\n|------|------|\n| 포지션 | Frontend Backend Engineer |")
            cfg = {"quick_filters": {"title_include": [], "title_exclude": []}}
            mock_cls = MagicMock(action="needs_manual", category="frontend",
                                 tier_used=2, reason="frontend + counter")
            with patch("pre_screen._check_prior_application", return_value=None), \
                 patch("pre_screen.classify_domain", return_value=mock_cls):
                r = pre_screen_jd(jd, cfg)
            self.assertTrue(r.hit)
            self.assertEqual(r.reason_code, "domain_frontend")
            self.assertEqual(r.target_folder, "conditional/hold")
            self.assertTrue(r.is_review)

    def test_no_match_returns_no_hit(self):
        from pre_screen import pre_screen_jd
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            jd = self._make_jd(tmp, "555-x-be.md",
                "# Backend\n## 기본 정보\n\n| 항목 | 내용 |\n|------|------|\n| 포지션 | Backend Engineer |")
            cfg = {"quick_filters": {"title_include": ["Backend"],
                                      "title_exclude": []}}
            mock_cls = MagicMock(action="skip", category=None,
                                 tier_used=None, reason="backend match")
            with patch("pre_screen._check_prior_application", return_value=None), \
                 patch("pre_screen.classify_domain", return_value=mock_cls):
                r = pre_screen_jd(jd, cfg)
            self.assertFalse(r.hit)
            self.assertEqual(r.reason_code, "")

    def test_substring_match_intent_lead_matches_leader(self):
        """search.quick_filter_title의 부분 문자열 매칭은 의도된 동작.
        검색 단계와 일관성 유지를 위해 pre_screen도 동일 의미론 차용.
        Lead가 exclude 목록에 있으면 Leader도 매칭 — 둘 다 시니어 IC가 아니라 무해.
        """
        from pre_screen import pre_screen_jd
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            jd = self._make_jd(tmp, "666-x-leader.md",
                "# Leader\n## 기본 정보\n\n| 항목 | 내용 |\n|------|------|\n| 포지션 | Backend Team Leader |")
            cfg = {"quick_filters": {
                "title_include": ["Backend"],
                "title_exclude": ["Lead"],
            }}
            with patch("pre_screen._check_prior_application", return_value=None):
                r = pre_screen_jd(jd, cfg)
            self.assertTrue(r.hit)
            self.assertEqual(r.reason_code, "title_exclude")


if __name__ == "__main__":
    unittest.main()
