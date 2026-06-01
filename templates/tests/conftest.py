"""Pytest import bridge for legacy top-level module imports."""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _referenced_test_modules() -> set[str]:
    names: set[str] = set()
    for path in (REPO_ROOT / "templates" / "tests").rglob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


TEST_IMPORT_NAMES = _referenced_test_modules()


def _alias_package_modules(package: str) -> None:
    package_dir = REPO_ROOT / "templates" / package
    for path in package_dir.glob("*.py"):
        if path.name == "__init__.py":
            continue
        alias = path.stem
        if alias not in TEST_IMPORT_NAMES:
            continue
        target = f"templates.{package}.{alias}"
        sys.modules.setdefault(alias, importlib.import_module(target))


for package_name in ("jd", "build"):
    _alias_package_modules(package_name)
