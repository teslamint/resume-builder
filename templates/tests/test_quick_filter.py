#!/usr/bin/env python3
"""Tests for quick_filter yaml externalization."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent / "jd"
sys.path.insert(0, str(ROOT))


class TestQuickFilterConfigLoad(unittest.TestCase):
    def test_load_config_reads_yaml_when_present(self):
        from quick_filter import load_config
        yaml_text = """
quick_filters:
  title_include: ["Backend", "엔지니어"]
  title_exclude: ["프론트엔드", "iOS", "신규키워드"]
"""
        with tempfile.TemporaryDirectory() as t:
            yaml_path = Path(t) / "search_config.yaml"
            yaml_path.write_text(yaml_text, encoding="utf-8")
            with patch("quick_filter._CONFIG_PATH", yaml_path):
                cfg = load_config()
        self.assertIn("신규키워드", cfg["quick_filters"]["title_exclude"])
        self.assertEqual(cfg["quick_filters"]["title_include"], ["Backend", "엔지니어"])

    def test_load_config_fallback_when_yaml_missing(self):
        from quick_filter import load_config
        with patch("quick_filter._CONFIG_PATH", Path("/nonexistent/path.yaml")):
            cfg = load_config()
        self.assertIn("title_include", cfg["quick_filters"])
        self.assertIn("프론트엔드", cfg["quick_filters"]["title_exclude"])

    def test_apply_quick_filter_uses_loaded_exclude(self):
        from quick_filter import apply_quick_filter
        cfg = {"quick_filters": {
            "title_include": ["백엔드"],
            "title_exclude": ["새단어"],
        }}
        ok, reason = apply_quick_filter({"title": "새단어 엔지니어", "leader": False}, cfg)
        self.assertFalse(ok)
        self.assertIn("새단어", reason)


if __name__ == "__main__":
    unittest.main()
