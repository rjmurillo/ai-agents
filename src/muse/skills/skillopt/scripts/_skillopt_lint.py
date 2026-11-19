"""Deterministic frontmatter and size lint for skillopt candidates.

`apply` runs skillforge's `lint_skill_frontmatter.py` on the incumbent and the
candidate. A candidate that adds a MUST failure the incumbent did not have is
refused: an optimizer may inherit a failure, never introduce one. Typical
causes are an edit that pushes SKILL.md over the byte cap, writes a flow
mapping the stdlib parser refuses, or breaks a Handoff line. SHOULD findings
the candidate adds are printed as warnings and do not block.

The linter is loaded from the skillforge skill in the same plugin. When it is
absent, the check says so on stderr and does not pretend to have run.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from _skillopt_patching import SkillOptError

_LINT = Path(__file__).resolve().parents[2] / "skillforge" / "scripts" / "lint_skill_frontmatter.py"


def _load_lint() -> ModuleType | None:
    """Import the linter, then restore sys.path and drop skillforge's sibling modules.

    The linter imports `_conformance_parse` and `_path_guard` from its own
    directory. Leaving either cached would shadow another tree's copy later.
    """
    if not _LINT.is_file():
        return None
    saved_path = list(sys.path)
    saved_modules = set(sys.modules)
    sys.path.insert(0, str(_LINT.parent))
    try:
        spec = importlib.util.spec_from_file_location("_skillopt_frontmatter_lint", _LINT)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = saved_path
        for added in set(sys.modules) - saved_modules:
            origin = getattr(sys.modules[added], "__file__", None)
            if origin and Path(origin).resolve().parent == _LINT.parent:
                del sys.modules[added]


def check_candidate(incumbent: str, candidate: str) -> None:
    """Raise SkillOptError when the candidate adds a MUST lint failure."""
    lint = _load_lint()
    if lint is None:
        sys.stderr.write(
            "WARNING: frontmatter lint NOT RUN: skillforge's lint_skill_frontmatter.py "
            "is not installed beside skillopt\n"
        )
        return
    before = lint.lint_text(incumbent)
    after = lint.lint_text(candidate)
    added = lint.added_failures(before, after)
    before_warn = {r.rule.id for r in before if r.status == "WARN"}
    for result in after:
        if result.status == "WARN" and result.rule.id not in before_warn:
            for message in result.messages:
                sys.stderr.write(f"WARNING: {result.rule.id}: {message}\n")
    if added:
        details = "; ".join(f"{r.rule.id}: {' '.join(r.messages)}" for r in added)
        raise SkillOptError(f"candidate adds frontmatter lint failures: {details}")
