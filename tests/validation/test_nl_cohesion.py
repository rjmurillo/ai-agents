"""Tests for the rule cohesion measure and its ratchet (issue #5397)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_nl_structural_debt as gate
import nl_cohesion as coh

_ROOTS = ["a", "b", "c", "d", "e"]
_BROAD = "templates/rules/broad.md"


def _rule(paths: list[str]) -> str:
    items = "".join(f'  - "{p}"\n' for p in paths)
    return f"---\npaths:\n{items}---\nBody of the rule.\n"


def _tree(root: Path, rules: dict[str, list[str]], baseline: dict | None = None) -> None:
    for subdir in ("templates/skills", "templates/agents", "templates/rules"):
        (root / subdir).mkdir(parents=True, exist_ok=True)
    for name, paths in rules.items():
        (root / f"templates/rules/{name}.md").write_text(_rule(paths), encoding="utf-8")
    base = {"duplicate_blocks": {}, "cardinality": {}, **(baseline or {})}
    target = root / gate.BASELINE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(base), encoding="utf-8")


def _globs(roots: list[str]) -> list[str]:
    return [f"{r}/**" for r in roots]


def test_spread_counts_distinct_top_level_roots() -> None:
    assert coh.path_spread(_rule(_globs(_ROOTS))) == 5


def test_wildcard_globs_share_one_root() -> None:
    text = _rule(["**/Auth/**", "*.env*", "**/*.secrets.*", "src/**"])
    assert coh.path_spread(text) == 2


def test_dot_directory_and_plain_directory_are_distinct_roots() -> None:
    assert coh.path_spread(_rule([".claude/**", "claude/**", "./src/**", "src/**"])) == 3


def test_nested_paths_under_one_root_do_not_spread() -> None:
    assert coh.path_spread(_rule([f"src/{r}/**" for r in _ROOTS])) == 1


@pytest.mark.parametrize(
    "text",
    [
        "no frontmatter",
        "---\nnever closed\n",
        "---\n: : [\n---\nbody",
        "---\n- a\n- b\n---\nbody",
        "---\nname: x\n---\nbody",
        "---\npaths: 5\n---\nbody",
    ],
)
def test_missing_or_malformed_scope_has_zero_spread(text: str) -> None:
    assert coh.path_spread(text) == 0


def test_string_paths_value_counts_as_one_root() -> None:
    assert coh.path_spread("---\npaths: src/**\n---\nbody") == 1


def test_non_string_entries_are_ignored() -> None:
    assert coh.path_spread("---\npaths:\n  - 3\n  - src/**\n---\nbody") == 1


def test_rule_below_floor_is_not_reported(tmp_path: Path) -> None:
    _tree(tmp_path, {"narrow": _globs(_ROOTS[:4])})
    assert gate.measure(tmp_path)["cohesion"] == {}
    assert gate.run(tmp_path, update=False) == 0


def test_rule_at_floor_fails_without_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _tree(tmp_path, {"broad": _globs(_ROOTS)})
    assert gate.run(tmp_path, update=False) == 1
    assert f"low cohesion {_BROAD}: 5 unrelated roots" in capsys.readouterr().err


def test_baselined_debt_passes_and_growth_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _tree(tmp_path, {"broad": _globs(_ROOTS)}, {"cohesion": {_BROAD: 5}})
    assert gate.run(tmp_path, update=False) == 0
    (tmp_path / _BROAD).write_text(_rule(_globs([*_ROOTS, "f"])), encoding="utf-8")
    assert gate.run(tmp_path, update=False) == 1
    assert "6 unrelated roots, baseline 5" in capsys.readouterr().err


def test_split_rule_demands_baseline_update(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _tree(tmp_path, {"broad": ["a/**"]}, {"cohesion": {_BROAD: 5}})
    assert gate.run(tmp_path, update=False) == 1
    assert "shrank below baseline 5" in capsys.readouterr().err


def test_baseline_without_cohesion_section_is_accepted(tmp_path: Path) -> None:
    _tree(tmp_path, {"narrow": ["a/**"]})
    assert gate.run(tmp_path, update=False) == 0


@pytest.mark.parametrize("value", [0, "5", True])
def test_invalid_cohesion_baseline_is_a_config_error(tmp_path: Path, value: object) -> None:
    _tree(tmp_path, {"narrow": ["a/**"]}, {"cohesion": {_BROAD: value}})
    assert gate.run(tmp_path, update=False) == 2


def test_unknown_baseline_section_is_a_config_error(tmp_path: Path) -> None:
    _tree(tmp_path, {"narrow": ["a/**"]}, {"bogus": {}})
    assert gate.run(tmp_path, update=False) == 2


def test_generated_rule_copy_is_not_scanned(tmp_path: Path) -> None:
    _tree(tmp_path, {"narrow": ["a/**"]})
    generated = tmp_path / ".claude/rules"
    generated.mkdir(parents=True)
    (generated / "broad.md").write_text(_rule(_globs(_ROOTS)), encoding="utf-8")
    assert gate.measure(tmp_path)["cohesion"] == {}


def test_live_repo_cohesion_matches_baseline() -> None:
    baseline = json.loads((_REPO_ROOT / gate.BASELINE_PATH).read_text(encoding="utf-8"))
    assert gate.measure(_REPO_ROOT)["cohesion"] == baseline["cohesion"]
