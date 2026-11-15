"""Shared loader and fixture builders for the agentskills.io conformance tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = PROJECT_ROOT / ".claude" / "skills" / "skillforge" / "scripts"
SKILLS_DIR = PROJECT_ROOT / "src" / "claude" / "skills"


def _drop_script_modules(saved: set[str]) -> None:
    """Drop only modules loaded from the skillforge script dir.

    Third-party modules stay cached; evicting them would split class identity
    for later importers.
    """
    script_dir = SCRIPT_DIR.resolve()
    for added in set(sys.modules) - saved:
        origin = getattr(sys.modules[added], "__file__", None)
        if origin and Path(origin).resolve().parent == script_dir:
            del sys.modules[added]


def load(name: str, filename: str):
    """Import one skillforge script without leaving its siblings in sys.modules."""
    saved_path = list(sys.path)
    saved_modules = set(sys.modules)
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / filename)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved_path
        _drop_script_modules(saved_modules)
    return module


conformance = load("skillforge_conformance_under_test", "conformance.py")
RULES = conformance.RULES
RULES_BY_ID = conformance.RULES_BY_ID

DEFAULT_BODY = "# Release notes\n\nSteps go here.\n"
DESCRIPTION = "Format release notes from merged pull requests. Use when drafting a release."


def make_skill(
    root: Path,
    name: str = "release-notes",
    *,
    frontmatter: str | None = None,
    body: str = DEFAULT_BODY,
    files: dict[str, str] | None = None,
    directory: str | None = None,
) -> Path:
    """Write a skill directory. frontmatter replaces the default name and description."""
    skill = root / (directory or name)
    skill.mkdir(parents=True, exist_ok=True)
    if frontmatter is None:
        frontmatter = f"name: {name}\ndescription: {DESCRIPTION}\n"
    (skill / "SKILL.md").write_text(f"---\n{frontmatter}---\n\n{body}", encoding="utf-8")
    for relative, text in (files or {}).items():
        path = skill / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return skill


def results(skill: Path, profile: str = "spec", waived: set[str] | None = None) -> dict[str, Any]:
    """Return {rule_id: Result} for one skill directory."""
    found, _notes = conformance.evaluate(skill, profile, waived or set())
    return {result.rule.id: result for result in found}
