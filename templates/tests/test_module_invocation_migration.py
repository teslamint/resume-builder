from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

COMMAND_PATTERN = re.compile(
    r"(?<![\w./-])(?:uv run )?python(?:3)?\s+templates/(?:jd|build)/[A-Za-z0-9_]+\.py\b"
)

TOP_LEVEL_IMPORT_FALLBACK_PATTERN = re.compile(
    r"(?m)^try:\n(?:(?:    |\t).*\n)+^except ImportError:\n"
)

ALLOWED_TOP_LEVEL_IMPORT_FALLBACKS = {
    "templates/build/career_builder.py",
    "templates/jd/browser_utils.py",
    "templates/jd/auto.py",
    "templates/jd/auto_company.py",
    "templates/jd/auto_processor.py",
    "templates/jd/auto_screening.py",
    "templates/jd/auto_state.py",
    "templates/jd/pipeline.py",
    "templates/jd/search.py",
    "templates/jd/search_helpers.py",
    "templates/jd/search_quick.py",
}

TEXT_GLOBS = (
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "README.md",
    "Makefile",
    "build.sh",
    ".github/workflows/*.yml",
    ".claude/**/*.md",
    "docs/**/*.md",
    "templates/**/*.py",
)


def _iter_audit_files() -> list[Path]:
    files: set[Path] = set()
    for pattern in TEXT_GLOBS:
        files.update(REPO_ROOT.glob(pattern))
    return sorted(path for path in files if path.is_file())


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def test_caller_surfaces_use_python_m_form() -> None:
    matches: list[str] = []
    for path in _iter_audit_files():
        text = path.read_text(encoding="utf-8")
        for match in COMMAND_PATTERN.finditer(text):
            rel = path.relative_to(REPO_ROOT)
            line = _line_number(text, match.start())
            matches.append(f"{rel}:{line}: {match.group(0)}")

    assert matches == []


def test_top_level_importerror_fallbacks_are_core_only() -> None:
    unexpected: list[str] = []
    for path in sorted((REPO_ROOT / "templates").glob("**/*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        prefix = "\n".join(text.splitlines()[:80]) + "\n"
        if not TOP_LEVEL_IMPORT_FALLBACK_PATTERN.search(prefix):
            continue
        if rel not in ALLOWED_TOP_LEVEL_IMPORT_FALLBACKS:
            unexpected.append(rel)

    assert unexpected == []


def test_importerror_fallback_count_stays_bounded() -> None:
    count = 0
    for path in sorted((REPO_ROOT / "templates").glob("jd/*.py")):
        count += path.read_text(encoding="utf-8").count("except ImportError")
    for path in sorted((REPO_ROOT / "templates").glob("build/*.py")):
        count += path.read_text(encoding="utf-8").count("except ImportError")

    assert count <= 15


def test_auto_cli_help_works_via_direct_script_invocation() -> None:
    result = subprocess.run(
        [sys.executable, "templates/jd/auto.py", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
