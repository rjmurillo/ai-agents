"""The bundled library must import on the host's ambient interpreter.

Skill scripts launch with bare `python3`, so the whole import closure of
`github_core.api` has to work at the portability floor, currently 3.10. A
syntax-level check cannot see this: a 3.11-only stdlib API parses clean at
3.10 and fails on import.

Two rounds of review found two separate instances of exactly that
(`datetime.UTC` in `output.py`, `enum.StrEnum` in `review_threads.py`), and
both times the scope was assessed by hand and got it wrong. This scans the
real closure instead (Copilot review on PR #5509).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parents[3]
_LIB = _project_root / ".claude" / "lib"
_COPILOT_LIB = _project_root / "src" / "copilot-cli" / "lib"

# Runtime stdlib names newer than the 3.10 floor. Names, not syntax: the
# floor gate already covers syntax.
_TOO_NEW = {
    "StrEnum": "3.11",
    "ExceptionGroup": "3.11",
    "tomllib": "3.11",
    "TaskGroup": "3.11",
}


def _closure_files(lib_root: Path) -> list[Path]:
    """Every github_core module reachable from the preflight's entry import.

    Walked statically from the source rather than from ``sys.modules``. An
    earlier version read the live module table, which made the result depend
    on what the rest of the suite had already imported and on which path those
    imports resolved through, so it passed alone and failed in a full run. A
    test that reports on collection order cannot report on the floor.
    """
    root = lib_root / "github_core"
    seen: set[str] = set()
    pending = ["api"]
    files: list[Path] = []
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        path = root / f"{name}.py"
        if not path.is_file():
            continue
        files.append(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                pending += [
                    alias.name.split(".", 1)[1]
                    for alias in node.names
                    if alias.name.startswith("github_core.")
                ]
                continue
            if not isinstance(node, ast.ImportFrom):
                continue
            # The mirrors rewrite siblings to relative imports, so absolute
            # matching alone walked exactly one module and proved nothing.
            if node.level and node.module:
                pending.append(node.module)
            elif node.module and node.module.startswith("github_core."):
                pending.append(node.module.split(".", 1)[1])
            elif node.module and node.module.startswith("scripts.github_core."):
                pending.append(node.module.split(".", 2)[2])
    return files


def _violations(path: Path) -> list[str]:
    found = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "datetime":
            found += [
                f"{path.name}: datetime.UTC (3.11)"
                for alias in node.names
                if alias.name == "UTC"
            ]
        if isinstance(node, ast.Attribute) and node.attr in _TOO_NEW:
            found.append(f"{path.name}: {node.attr} ({_TOO_NEW[node.attr]})")
        if isinstance(node, ast.Name) and node.id in _TOO_NEW:
            found.append(f"{path.name}: {node.id} ({_TOO_NEW[node.id]})")
    return found


class TestBundledLibStaysAtTheFloor:
    def test_the_preflight_import_closure_is_floor_clean(self):
        files = _closure_files(_LIB)
        assert len(files) > 5, (
            f"closure walk found only {len(files)} modules; the scan is inert"
        )
        offenders = sorted({v for f in files for v in _violations(f)})
        assert not offenders, (
            "3.11-only stdlib in the bundled import closure; a 3.10 host "
            f"cannot run any bundled skill script: {offenders}"
        )

    @pytest.mark.parametrize("lib", [_LIB, _COPILOT_LIB])
    def test_both_shipped_mirrors_are_floor_clean(self, lib):
        """The mirrors are what consumers actually install."""
        offenders = sorted(
            {v for f in lib.rglob("github_core/*.py") for v in _violations(f)}
        )
        assert not offenders, f"{lib.name} mirror is not floor-clean: {offenders}"

    def test_the_scan_detects_a_planted_violation(self):
        """Negative control: a scan that cannot fail proves nothing."""
        planted = _project_root / "tests" / "skills" / "github" / "_floor_probe.py"
        planted.write_text(
            "import enum\n\n\nclass X(enum.StrEnum):\n    A = 'a'\n", encoding="utf-8"
        )
        try:
            assert _violations(planted), "the scan missed a planted StrEnum"
        finally:
            planted.unlink()
