"""Characterization tests for heading extraction — proves equivalence
between auto_company._read_first_heading and company_match_verify._extract_heading_company,
then validates the unified jd_content.extract_heading_company.
"""

import tempfile
from pathlib import Path

import pytest

from templates.jd.auto_company import _read_first_heading
from templates.jd.company_match_verify import _extract_heading_company as cmv_extract
from templates.jd.jd_content import extract_heading_company


CASES = [
    ("# Acme Corp\n\nBody text.", "acme corp"),
    ("# 캐처스 (Catchers)\n\nBody.", "캐처스"),
    ("# Hello (World) (Test)\n\nBody.", "hello"),
    ("## Not a top-level heading\n\nBody.", ""),
    ("No heading at all.\n\nJust text.", ""),
    ("   # Indented\n\nBody.", ""),
    ("# Simple\n", "simple"),
    ("# Trailing Spaces   \n", "trailing spaces"),
    ("```\n# Inside Fenced\n```\n# Real Heading\n", "inside fenced"),
    ("# UPPER Case (주)\nBody.", "upper case"),
]


class TestEquivalence:
    """Prove the two original functions produce identical output on the same content."""

    @pytest.mark.parametrize("content, expected", CASES)
    def test_cmv_extract(self, content, expected):
        assert cmv_extract(content) == expected

    @pytest.mark.parametrize("content, expected", CASES)
    def test_read_first_heading_via_file(self, content, expected, tmp_path):
        p = tmp_path / "test.md"
        p.write_text(content, encoding="utf-8")
        assert _read_first_heading(p) == expected


class TestUnifiedFunction:
    """Validate the new extract_heading_company in jd_content."""

    @pytest.mark.parametrize("content, expected", CASES)
    def test_extract_heading_company(self, content, expected):
        assert extract_heading_company(content) == expected


class TestReadFirstHeadingEdgeCases:
    def test_nonexistent_file(self):
        assert _read_first_heading(Path("/nonexistent/file.md")) == ""

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.md"
        p.write_text("", encoding="utf-8")
        assert _read_first_heading(p) == ""
