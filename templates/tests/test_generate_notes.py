#!/usr/bin/env python3
"""Tests for generate_notes.py output path handling."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "generate_notes",
    Path(__file__).parent.parent / "build" / "generate_notes.py",
)
generate_notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generate_notes)


class TestGenerateNotesOutputPath(unittest.TestCase):
    def run_main(self, args: list[str], cwd: Path | None = None) -> tuple[int, str]:
        stdout = io.StringIO()
        original_cwd = Path.cwd()
        try:
            if cwd is not None:
                os.chdir(cwd)
            with patch("sys.argv", ["generate_notes.py", *args]), redirect_stdout(stdout):
                result = generate_notes.main()
        finally:
            os.chdir(original_cwd)
        return result, stdout.getvalue()

    def test_uses_private_build_default_output_path(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            base_path = temp_dir / "resume-job-base.md"
            current_path = temp_dir / "resume-job.md"
            base_path.write_text("# Base\n", encoding="utf-8")
            current_path.write_text("# Current\n", encoding="utf-8")

            result, stdout = self.run_main(
                ["--base", str(base_path), "--current", str(current_path), "--target", "CompanyA"],
                cwd=temp_dir,
            )

            output_path = temp_dir / "private/build/resume-job-notes.md"
            self.assertEqual(result, 0)
            self.assertTrue(output_path.exists())
            self.assertIn("Created: private/build/resume-job-notes.md", stdout)
            self.assertIn("Target: CompanyA", output_path.read_text(encoding="utf-8"))

    def test_creates_parent_dirs_for_custom_output_path(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            base_path = temp_dir / "resume-job-base.md"
            current_path = temp_dir / "resume-job.md"
            output_path = temp_dir / "nested/output/resume-job-notes.md"
            base_path.write_text("# Base\n", encoding="utf-8")
            current_path.write_text("# Current\n", encoding="utf-8")

            result, stdout = self.run_main(
                [
                    "--base",
                    str(base_path),
                    "--current",
                    str(current_path),
                    "--output",
                    str(output_path),
                ]
            )

            self.assertEqual(result, 0)
            self.assertTrue(output_path.exists())
            self.assertIn(f"Created: {output_path}", stdout)


if __name__ == "__main__":
    unittest.main()
