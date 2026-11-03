"""Tests for scripts/validation/check_dead_code.py.

The gate compares vulture's findings with a shrink-only baseline. These tests
drive ``main(argv)`` against small fixture repositories and assert on the exit
code, then check the real baseline: it is sorted, matches the live tree, and
holds exactly the pinned number of lines.
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

import pytest
import tomllib
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

import check_dead_code
from check_dead_code import (
    BASELINE_RELPATH,
    REPO_ROOT,
    GateConfigError,
    compare,
    load_baseline,
    main,
    parse_baseline,
    validate_dead_code,
)

BASELINE = REPO_ROOT / BASELINE_RELPATH

# Shrink-only pin. Lower it when you delete a baseline line; never raise it to
# make a new finding fit. A new line fails the length test until this moves.
EXPECTED_DEAD_CODE_BASELINE_ENTRIES = 9

SCRIPT = "scripts/validation/check_dead_code.py"
DEAD_KEY = "src/mod.py: unused function 'dead'"


def _repo(tmp_path: Path, *, paths: str = '["src"]', source: str | None = None) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""\
            [tool.vulture]
            paths = {paths}
            min_confidence = 60
            exclude = ["*/tests/*"]
            """
        ),
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    body = source if source is not None else "def dead():\n    return 1\n"
    (src / "mod.py").write_text(body, encoding="utf-8")
    return tmp_path


def _baseline(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "baseline.txt"
    path.write_text("# comment\n\n" + "".join(f"{line}\n" for line in lines), encoding="utf-8")
    return path


def _run(repo: Path, baseline: Path) -> int:
    return main(["--repo-root", str(repo), "--baseline", str(baseline)])


def test_parse_baseline_skips_comments_and_blank_lines() -> None:
    assert parse_baseline("# note\n\n a.py: unused import 'x' \n") == ["a.py: unused import 'x'"]


@pytest.mark.parametrize("line", ["no separator here", ": unused import 'x'", "a.py: "])
def test_parse_baseline_rejects_malformed_line(line: str) -> None:
    with pytest.raises(GateConfigError, match="line 1"):
        parse_baseline(line)


def test_compare_equal_multisets_is_clean() -> None:
    outcome = compare(["a: x", "b: y"], ["b: y", "a: x"])

    assert (outcome.new, outcome.stale) == ([], [])


def test_compare_reports_new_and_stale() -> None:
    outcome = compare(["a: x", "c: z"], ["a: x", "b: y"])

    assert (outcome.new, outcome.stale) == (["c: z"], ["b: y"])


def test_compare_counts_duplicates() -> None:
    assert compare(["a: x", "a: x"], ["a: x"]).new == ["a: x"]
    assert compare(["a: x"], ["a: x", "a: x"]).stale == ["a: x"]


def test_main_passes_when_findings_equal_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)

    assert _run(repo, _baseline(tmp_path, DEAD_KEY)) == 0
    assert "Scanned 1 Python file(s); 1 finding(s)" in capsys.readouterr().out


def test_main_passes_on_clean_tree_with_empty_baseline(tmp_path: Path) -> None:
    repo = _repo(tmp_path, source="def used():\n    return 1\n\n\nused()\n")

    assert _run(repo, _baseline(tmp_path)) == 0


def test_main_fails_on_new_finding(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)

    assert _run(repo, _baseline(tmp_path)) == 1
    assert f"new dead code: {DEAD_KEY}" in capsys.readouterr().err


def test_main_fails_on_stale_baseline_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    stale = "src/mod.py: unused import 'gone'"

    assert _run(repo, _baseline(tmp_path, DEAD_KEY, stale)) == 1
    assert f"stale baseline entry: {stale}" in capsys.readouterr().err


def test_main_honors_exclude_patterns(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    tests_dir = repo / "src" / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_mod.py").write_text("def also_dead():\n    pass\n", encoding="utf-8")

    assert _run(repo, _baseline(tmp_path, DEAD_KEY)) == 0


def test_main_config_error_when_baseline_missing(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    assert _run(repo, tmp_path / "absent.txt") == 2


def test_main_config_error_when_baseline_malformed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    assert _run(repo, _baseline(tmp_path, "not a key")) == 2


def test_main_config_error_on_syntax_error_source(tmp_path: Path) -> None:
    repo = _repo(tmp_path, source="def broken(:\n")

    assert _run(repo, _baseline(tmp_path)) == 2


def test_main_config_error_when_scan_path_missing(tmp_path: Path) -> None:
    repo = _repo(tmp_path, paths='["absent"]')

    assert _run(repo, _baseline(tmp_path)) == 2


def test_main_config_error_when_nothing_scanned(tmp_path: Path) -> None:
    repo = _repo(tmp_path, paths='["empty"]')
    (repo / "empty").mkdir()

    assert _run(repo, _baseline(tmp_path)) == 2


def test_main_config_error_when_pyproject_missing(tmp_path: Path) -> None:
    assert _run(tmp_path, _baseline(tmp_path)) == 2


def test_main_external_error_when_vulture_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    for name in ("vulture", "vulture.config", "vulture.core"):
        monkeypatch.setitem(sys.modules, name, None)

    assert _run(repo, _baseline(tmp_path, DEAD_KEY)) == 3


def test_repository_findings_equal_the_committed_baseline() -> None:
    assert main([]) == 0


def test_main_defaults_baseline_to_the_repo_root(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    baseline = repo / BASELINE_RELPATH
    baseline.parent.mkdir(parents=True)
    baseline.write_text(f"{DEAD_KEY}\n", encoding="utf-8")

    assert main(["--repo-root", str(repo)]) == 0


def test_validate_dead_code_returns_true_when_baseline_matches(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    baseline = repo / BASELINE_RELPATH
    baseline.parent.mkdir(parents=True)
    baseline.write_text(f"{DEAD_KEY}\n", encoding="utf-8")

    assert validate_dead_code(repo) is True


def test_validate_dead_code_fails_closed_without_baseline(tmp_path: Path) -> None:
    assert validate_dead_code(_repo(tmp_path)) is False


def test_validate_dead_code_fails_closed_without_vulture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    baseline = repo / BASELINE_RELPATH
    baseline.parent.mkdir(parents=True)
    baseline.write_text(f"{DEAD_KEY}\n", encoding="utf-8")
    for name in ("vulture", "vulture.config", "vulture.core"):
        monkeypatch.setitem(sys.modules, name, None)

    assert validate_dead_code(repo) is False


def test_pre_pr_sequence_runs_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    import pre_pr_sequence

    calls: list[Path] = []

    def fake(root: Path) -> bool:
        calls.append(root)
        return False

    monkeypatch.setattr(pre_pr_sequence, "validate_dead_code", fake)
    gates = [g for g in pre_pr_sequence._SEQUENCE if g.name == "Dead Code Detection"]

    assert len(gates) == 1
    assert gates[0].run(REPO_ROOT, argparse.Namespace()) is False
    assert calls == [REPO_ROOT]


def test_baseline_is_sorted_so_removals_diff_cleanly() -> None:
    keys = load_baseline(BASELINE)

    assert keys == sorted(keys)


def test_baseline_length_matches_the_pinned_constant() -> None:
    keys = load_baseline(BASELINE)

    assert len(keys) == EXPECTED_DEAD_CODE_BASELINE_ENTRIES, (
        f"{BASELINE.name} holds {len(keys)} entries, pinned at "
        f"{EXPECTED_DEAD_CODE_BASELINE_ENTRIES}. Lower the constant when you delete a "
        "line; never raise it. Remove new dead code instead of listing it."
    )


def test_vulture_config_keeps_the_confidence_floor() -> None:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert config["tool"]["vulture"]["min_confidence"] >= 80


def _run_commands(node: object) -> list[str]:
    if isinstance(node, dict):
        found = [node["run"]] if isinstance(node.get("run"), str) else []
        return found + [cmd for value in node.values() for cmd in _run_commands(value)]
    if isinstance(node, list):
        return [cmd for item in node for cmd in _run_commands(item)]
    return []


def test_pre_push_hook_runs_the_gate() -> None:
    lefthook = yaml.safe_load((REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))

    assert any(SCRIPT in cmd for cmd in _run_commands(lefthook["pre-push"]))


def test_pytest_workflow_runs_the_gate() -> None:
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "pytest.yml").read_text(encoding="utf-8")
    )

    assert any(SCRIPT in cmd for cmd in _run_commands(workflow["jobs"]))


def test_baseline_sits_next_to_the_script() -> None:
    assert BASELINE == Path(check_dead_code.__file__).resolve().parent / "dead_code_baseline.txt"
