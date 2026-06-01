from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_search_helpers_and_auto_processor_import_without_browser_utils() -> None:
    script = """
import builtins
import importlib
import sys

original_import = builtins.__import__

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    package = (globals or {}).get("__package__")
    if name == "browser_utils" and package == "templates.jd" and level == 1:
        raise ModuleNotFoundError("browser deps intentionally unavailable")
    if name in {
        "browser_utils",
        "templates.jd.browser_utils",
        "patchright",
        "patchright.sync_api",
        "playwright",
        "playwright.sync_api",
    }:
        raise ModuleNotFoundError(f"{name} intentionally unavailable")
    return original_import(name, globals, locals, fromlist, level)

builtins.__import__ = guarded_import
for name in [
    "templates.jd.search_helpers",
    "search_helpers",
    "templates.jd.auto_processor",
    "auto_processor",
]:
    sys.modules.pop(name, None)

search_helpers = importlib.import_module("templates.jd.search_helpers")
auto_processor = importlib.import_module("templates.jd.auto_processor")

assert search_helpers.__name__ == "templates.jd.search_helpers"
assert search_helpers._is_timeout_exception(TimeoutError())
assert auto_processor.__name__ == "templates.jd.auto_processor"
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_pytest_import_bridge_does_not_eagerly_import_modules() -> None:
    conftest_path = REPO_ROOT / "templates" / "tests" / "conftest.py"
    script = f"""
import importlib
import importlib.util
import sys

calls = []

def fail_import(name, package=None):
    calls.append(name if package is None else f"{{package}}:{{name}}")
    raise AssertionError(f"unexpected eager import: {{name}}")

importlib.import_module = fail_import
spec = importlib.util.spec_from_file_location("isolated_test_conftest", {str(conftest_path)!r})
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert calls == []
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
