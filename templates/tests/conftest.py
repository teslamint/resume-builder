"""Pytest import bridge for legacy top-level module imports."""

from __future__ import annotations

import ast
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys
from types import ModuleType
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _ensure_package(name: str, path: Path) -> None:
    if name in sys.modules:
        return
    module = ModuleType(name)
    module.__file__ = str(path / "__init__.py")
    module.__path__ = [str(path)]
    module.__package__ = name
    spec = importlib.machinery.ModuleSpec(name, loader=None, is_package=True)
    spec.submodule_search_locations = [str(path)]
    module.__spec__ = spec
    sys.modules[name] = module


_ensure_package("templates", REPO_ROOT / "templates")
_ensure_package("templates.build", REPO_ROOT / "templates" / "build")
_ensure_package("templates.jd", REPO_ROOT / "templates" / "jd")


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


def _build_alias_map() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for package in ("jd", "build"):
        package_dir = REPO_ROOT / "templates" / package
        for path in package_dir.glob("*.py"):
            if path.name == "__init__.py":
                continue
            alias = path.stem
            aliases.setdefault(alias, f"templates.{package}.{alias}")
    return aliases


TEST_IMPORT_NAMES = _referenced_test_modules()
PACKAGE_ALIASES = {
    alias: target
    for alias, target in _build_alias_map().items()
    if alias in TEST_IMPORT_NAMES
}


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, alias: str, target: str, path: Path) -> None:
        self.alias = alias
        self.target = target
        self.path = path

    def create_module(self, spec):
        if existing := sys.modules.get(self.target):
            setattr(existing, "__codex_alias_existing__", True)
            sys.modules[self.alias] = existing
            return existing
        return None

    def exec_module(self, module) -> None:
        if getattr(module, "__codex_alias_existing__", False):
            delattr(module, "__codex_alias_existing__")
            sys.modules[self.alias] = module
            return
        module.__name__ = self.target
        module.__file__ = str(self.path)
        module.__package__ = self.target.rpartition(".")[0]
        module.__loader__ = self
        module.__spec__ = importlib.util.spec_from_loader(self.target, self)
        sys.modules[self.alias] = module
        sys.modules[self.target] = module
        code = compile(self.path.read_text(encoding="utf-8"), str(self.path), "exec")
        exec(code, module.__dict__)


class _AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path=None, target=None):
        if path is not None or "." in fullname:
            return None
        target_name = PACKAGE_ALIASES.get(fullname)
        if target_name is None:
            return None
        package = target_name.split(".")[1]
        module_path = REPO_ROOT / "templates" / package / f"{fullname}.py"
        return importlib.util.spec_from_loader(
            fullname,
            _AliasLoader(fullname, target_name, module_path),
        )


if not any(isinstance(finder, _AliasFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _AliasFinder())
