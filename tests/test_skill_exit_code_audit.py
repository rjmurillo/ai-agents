"""Repo-wide audit: no skill script passes an ADR-035 reserved exit code (issue #5303).

write_skill_error rejects 5-99 at run time. This test finds the same mistake
statically, so a script that only reaches the bad call on a rare error path
fails here instead of raising ValueError in production.

It inspects literal integer arguments of the envelope emitters and of
merge_pr's _MergeFailureError. A code passed through a variable is covered by
the run-time guard.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_ROOT = REPO_ROOT / ".claude" / "skills"
EMITTERS = {"write_skill_error", "_emit_error", "_exit_with_error", "_MergeFailureError"}
# Second and third positional args and these keywords can carry the exit code.
CODE_KEYWORDS = {"exit_code", "code"}


def _called_name(node: ast.Call) -> str:
    func = node.func
    return getattr(func, "id", getattr(func, "attr", ""))


def _literal_ints(node: ast.Call) -> list[int]:
    candidates = list(node.args[1:3]) + [k.value for k in node.keywords if k.arg in CODE_KEYWORDS]
    return [
        c.value
        for c in candidates
        if isinstance(c, ast.Constant)
        and isinstance(c.value, int)
        and not isinstance(c.value, bool)
    ]


def _is_usable(code: int) -> bool:
    return 0 <= code <= 4 or 100 <= code <= 255


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _called_name(node) in EMITTERS:
            for code in _literal_ints(node):
                if not _is_usable(code):
                    found.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} exit code {code}")
    return found


def test_no_skill_script_passes_a_reserved_or_out_of_range_exit_code() -> None:
    scripts = sorted(SKILLS_ROOT.rglob("*.py"))
    assert scripts, "no skill scripts found; the audit would pass vacuously"
    violations = [v for path in scripts for v in _violations(path)]
    assert violations == []


def test_audit_detects_a_reserved_code(tmp_path: Path) -> None:
    sample = tmp_path / "bad.py"
    sample.write_text("write_skill_error('x', 6)\n_emit_error('x', code=7)\n", encoding="utf-8")
    tree = ast.parse(sample.read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert sorted(c for call in calls for c in _literal_ints(call)) == [6, 7]
    assert not _is_usable(6)
    assert not _is_usable(7)


def test_audit_accepts_standard_and_script_specific_codes() -> None:
    assert all(_is_usable(c) for c in (0, 1, 2, 3, 4, 100, 255))
    assert not any(_is_usable(c) for c in (-1, 5, 99, 256))
