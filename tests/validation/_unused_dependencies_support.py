"""Shared loader and helpers for the check_unused_dependencies test modules.

The script is loaded by path once, so every test module patches the same module
object. Kept out of ``conftest.py`` because these are plain helpers, not fixtures.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_MODULE_PATH = REPO / "scripts" / "validation" / "check_unused_dependencies.py"
_spec = importlib.util.spec_from_file_location("check_unused_dependencies", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
cud = importlib.util.module_from_spec(_spec)
sys.modules["check_unused_dependencies"] = cud
_spec.loader.exec_module(cud)


def write_policy(tmp: Path, body: str) -> Path:
    path = tmp / "policy.toml"
    path.write_text(body, encoding="utf-8")
    return path


def git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)


def make_project(tmp: Path, deps: str, source: str) -> Path:
    git_init(tmp)
    (tmp / "pyproject.toml").write_text(
        f'[project]\nname = "fixture"\nversion = "0"\ndependencies = [{deps}]\n', encoding="utf-8"
    )
    (tmp / "app.py").write_text(source, encoding="utf-8")
    (tmp / "sibling.py").write_text("X = 1\n", encoding="utf-8")
    return write_policy(tmp, '[[manifest]]\npath = "."\n')
