#!/usr/bin/env python3
"""Regression tests for pre_screen_helpers — extracted from auto.py."""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent / "jd"
sys.path.insert(0, str(ROOT))


class TestPreScreenHelpers(unittest.TestCase):
    def test_is_closed_jd_detects_marker(self):
        from pre_screen_helpers import _is_closed_jd
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "111-x-be.md"
            p.write_text("# Backend\n채용 마감\n", encoding="utf-8")
            self.assertTrue(_is_closed_jd(p))

    def test_is_closed_jd_returns_false_for_open(self):
        from pre_screen_helpers import _is_closed_jd
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "111-x-be.md"
            p.write_text("# Backend\n## 포지션\nBackend Engineer\n", encoding="utf-8")
            self.assertFalse(_is_closed_jd(p))

    def test_extract_company_slug_from_table(self):
        from pre_screen_helpers import _extract_company_slug
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "111-acme-be.md"
            p.write_text("| 회사명 | Acme Corp |\n", encoding="utf-8")
            slug = _extract_company_slug(p)
            self.assertIsNotNone(slug)
            self.assertIn("acme", slug.lower())

    def test_check_prior_application_none_when_no_history(self):
        from pre_screen_helpers import _check_prior_application
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "111-uniqueco-be.md"
            p.write_text("**회사**: UniqueCo\n", encoding="utf-8")
            # No applied/rejected/submitted folders → None
            self.assertIsNone(_check_prior_application(p))

    def test_closed_markers_constant_exposed(self):
        from pre_screen_helpers import _CLOSED_MARKERS
        self.assertIn("채용 마감", _CLOSED_MARKERS)
        self.assertIsInstance(_CLOSED_MARKERS, tuple)


if __name__ == "__main__":
    unittest.main()
