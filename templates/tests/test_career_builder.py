#!/usr/bin/env python3
"""Tests for career_builder.py — smoke tests using example/ and unit tests with tmp_path."""

import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build"))

from resume_builder import _BASE_DIR

from career_builder import (
    build_career,
    build_career_project,
    build_contact,
    discover_all_companies,
    resolve_base_dir,
)


EXAMPLE_BASE = _BASE_DIR / "example"


class TestSmokeExampleBuild(unittest.TestCase):
    def test_build_career_md_not_empty(self):
        result = build_career(base_dir=EXAMPLE_BASE, format_type="md")
        self.assertTrue(len(result) > 0)
        self.assertIn("경력기술서", result)

    def test_example_career_includes_company_and_projects(self):
        result = build_career(base_dir=EXAMPLE_BASE, format_type="md")
        self.assertIn("테크코프 주식회사", result)
        self.assertIn("프로젝트 1: API 성능 최적화", result)
        self.assertIn("프로젝트 2: 결제 시스템 개발", result)
        self.assertIn("응답 시간 30% 개선", result)

    def test_discover_all_companies_sorted(self):
        companies = discover_all_companies(EXAMPLE_BASE)
        self.assertGreater(len(companies), 0)
        # All returned paths should have a profile.md
        for c in companies:
            self.assertTrue((c / "profile.md").exists())


class TestResolveBaseDir(unittest.TestCase):
    def test_default_uses_private_data_root(self):
        self.assertEqual(resolve_base_dir(example=False), _BASE_DIR / "private")

    def test_example_uses_example_data_root(self):
        self.assertEqual(resolve_base_dir(example=True), _BASE_DIR / "example")


class TestBuildContact(unittest.TestCase):
    def test_extracts_contact_fields(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            profile_dir = base / "profile"
            profile_dir.mkdir()
            (profile_dir / "contact.md").write_text(
                "# Contact\n\n- Name: 홍길동\n- Email: test@example.com\n- Phone: 010-1234-5678\n",
                encoding="utf-8",
            )
            result = build_contact(base)
            self.assertIn("이름: 홍길동", result)
            self.assertIn("이메일: test@example.com", result)
            self.assertIn("연락처: 010-1234-5678", result)

    def test_returns_empty_when_no_contact(self):
        with tempfile.TemporaryDirectory() as td:
            result = build_contact(Path(td))
            self.assertEqual(result, "")


class TestBuildCareerProject(unittest.TestCase):
    def test_basic_project(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "project.md"
            p.write_text(
                "# My Project\n\n"
                "## Overview\n\n"
                "- Period: 2023.01 - 2023.12\n"
                "- Type: Backend\n\n"
                "## Summary\n\nBuilt a backend service.\n\n"
                "## Tech Stack\n\n- Python\n- PostgreSQL\n",
                encoding="utf-8",
            )
            result = build_career_project(p, 1)
            self.assertIn("프로젝트 1: My Project", result)
            self.assertIn("기간:", result)
            self.assertIn("기술스택:", result)
            self.assertIn("Python", result)

    def test_project_accepts_double_hash_title_and_period_section(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "project.md"
            p.write_text(
                "## Internal Project\n\n"
                "### Period\n\n2024.01 - 2024.03\n\n"
                "### Responsibilities\n\n- Built an internal API\n",
                encoding="utf-8",
            )
            result = build_career_project(p, 1)
            self.assertIn("프로젝트 1: Internal Project", result)
            self.assertIn("기간: 2024.01 - 2024.03", result)
            self.assertIn("Built an internal API", result)


class TestDiscoverAllCompanies(unittest.TestCase):
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "companies").mkdir()
            result = discover_all_companies(base)
            self.assertEqual(result, [])

    def test_sort_order(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            companies_dir = base / "companies"

            for name, period in [("OldCo", "2018.01 - 2020.12"), ("NewCo", "2023.01 - Present")]:
                d = companies_dir / name
                d.mkdir(parents=True)
                (d / "profile.md").write_text(
                    f"# {name}\n\n## Overview\n\n- Period: {period}\n- Role: Engineer\n",
                    encoding="utf-8",
                )

            result = discover_all_companies(base)
            names = [r.name for r in result]
            self.assertEqual(names, ["NewCo", "OldCo"])

    def test_malformed_period_does_not_crash(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            d = base / "companies" / "BadCo"
            d.mkdir(parents=True)
            (d / "profile.md").write_text(
                "# BadCo\n\n## Overview\n\n- Period: invalid\n- Role: Engineer\n",
                encoding="utf-8",
            )
            result = discover_all_companies(base)
            self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
