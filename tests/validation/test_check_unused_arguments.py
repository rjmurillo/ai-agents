"""Tests for scripts/validation/check_unused_arguments.py: scan, compare, and scope.

The gate compares ruff's ARG findings with a shrink-only baseline. These tests
drive ``main(argv)`` against small fixture repositories and assert on the exit
code and the printed findings.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

from check_unused_arguments import SCAN_ROOTS, GateConfigError, compare, parse_baseline, scan

from tests.validation.unused_arguments_helpers import (
    DEFINED_TWICE,
    UNUSED,
    UNUSED_KEY,
    add_file,
    git,
    make_repo,
    run_gate,
    scan_keys,
    write_baseline,
)


def test_parse_baseline_skips_comments_and_blank_lines() -> None:
    assert parse_baseline("# note\n\n a.py: ARG001 x \n") == ["a.py: ARG001 x"]


@pytest.mark.parametrize("line", ["no separator here", ": ARG001 x", "a.py: "])
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
    repo = make_repo(tmp_path)

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 0
    assert "Scanned 1 Python file(s); 1 finding(s)" in capsys.readouterr().out


def test_main_passes_on_clean_tree_with_empty_baseline(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, source="def f(path):\n    return path\n")

    assert run_gate(repo, write_baseline(tmp_path)) == 0


def test_main_fails_on_new_finding(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo(tmp_path)

    assert run_gate(repo, write_baseline(tmp_path)) == 1
    assert f"new unused argument: {UNUSED_KEY}" in capsys.readouterr().err


def test_main_fails_on_stale_baseline_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    stale = "scripts/mod.py: ARG001 gone"

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY, stale)) == 1
    assert f"stale baseline entry: {stale}" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["path", "args"])
def test_common_name_is_reported_even_when_another_function_reads_it(
    tmp_path: Path, name: str
) -> None:
    # vulture matched names across the whole tree, so a name any function read
    # hid every unused parameter of that name. ruff resolves per function.
    source = f"def reads({name}):\n    return {name}\n\n\ndef ignores({name}):\n    return 1\n"
    repo = make_repo(tmp_path, source=source)

    assert scan_keys(repo) == [f"scripts/mod.py: ARG001 {name} in ignores"]
    assert run_gate(repo, write_baseline(tmp_path)) == 1


def test_scan_reports_method_and_lambda_arguments(tmp_path: Path) -> None:
    source = (
        "class C:\n    def m(self, unused):\n        return 1\n\n\ng = lambda x: 1  # noqa: E731\n"
    )
    repo = make_repo(tmp_path, source=source)

    assert scan_keys(repo) == [
        "scripts/mod.py: ARG002 unused in C.m",
        "scripts/mod.py: ARG005 x in <lambda>",
    ]


def test_scan_ignores_used_and_underscore_prefixed_arguments(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, source="def f(_unused, used):\n    return used\n")

    assert scan_keys(repo) == []


def test_key_has_no_line_number_so_unrelated_edits_keep_it_valid(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    baseline = write_baseline(tmp_path, UNUSED_KEY)
    add_file(repo, "scripts/mod.py", "# header\n\n\n" + UNUSED)

    assert run_gate(repo, baseline) == 0


def test_same_argument_name_in_two_functions_gets_two_different_keys(tmp_path: Path) -> None:
    source = UNUSED + "\n\ndef h(path):\n    return 2\n"
    repo = make_repo(tmp_path, source=source)
    other_key = "scripts/mod.py: ARG001 path in h"

    assert scan_keys(repo) == [UNUSED_KEY, other_key]
    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 1
    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY, other_key)) == 0


def test_a_function_defined_twice_in_one_scope_needs_one_baseline_line_each(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path, source=DEFINED_TWICE)

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 1
    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY, UNUSED_KEY)) == 0


@pytest.mark.parametrize(
    "relpath",
    [
        "scripts/tests/test_mod.py",
        "src/claude/hooks/hook.py",
        "src/claude/lib/github_core/core.py",
        "src/claude/lib/shim_loader.py",
    ],
)
def test_main_skips_excluded_paths(tmp_path: Path, relpath: str) -> None:
    repo = make_repo(tmp_path)
    add_file(repo, relpath, UNUSED)

    assert scan_keys(repo) == [UNUSED_KEY]


def test_main_scans_every_root(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    for root in SCAN_ROOTS[1:]:
        add_file(repo, f"{root}/extra.py", UNUSED)

    assert len(scan_keys(repo)) == len(SCAN_ROOTS)


def test_main_ignores_python_files_outside_the_roots(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    add_file(repo, "other/mod.py", UNUSED)

    assert scan(repo).scanned_files == 1


def test_main_ignores_untracked_python_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    (repo / "scripts" / "draft.py").write_text(UNUSED, encoding="utf-8")

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 0
    assert "Scanned 1 Python file(s); 1 finding(s)" in capsys.readouterr().out


def test_main_reports_the_same_file_once_it_is_tracked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    add_file(repo, "scripts/draft.py", "def g(args):\n    return 1\n")

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 1
    assert "new unused argument: scripts/draft.py: ARG001 args in g" in capsys.readouterr().err


def test_main_skips_a_tracked_file_deleted_from_the_work_tree(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    gone = add_file(repo, "scripts/gone.py", "def g(args):\n    return 1\n")
    gone.unlink()

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 0


def test_main_skips_tracked_symlinks(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    try:
        (repo / "scripts" / "link.py").symlink_to("mod.py")
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks are not available here: {exc}")
    git(repo, "add", "scripts/link.py")

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 0


def test_main_strips_leaked_git_env_vars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "nowhere"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "nowhere"))

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 0


def test_new_finding_output_carries_ruff_line_number(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path, source="# one\n# two\n\n\ndef f(path):\n    return 1\n")

    assert run_gate(repo, write_baseline(tmp_path)) == 1
    assert f"new unused argument: {UNUSED_KEY} (line 5)" in capsys.readouterr().err


def test_scan_records_one_row_per_finding(tmp_path: Path) -> None:
    source = UNUSED + "\n\ndef h(path):\n    return 2\n"
    repo = make_repo(tmp_path, source=source)

    assert scan(repo).rows == {UNUSED_KEY: [1], "scripts/mod.py: ARG001 path in h": [5]}


def test_listed_key_with_a_new_duplicate_prints_every_candidate_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # One function defined twice in a scope gives two findings under one key. A
    # baseline that lists one must show which lines to look at.
    repo = make_repo(tmp_path, source=DEFINED_TWICE)

    assert run_gate(repo, write_baseline(tmp_path, UNUSED_KEY)) == 1
    assert f"{UNUSED_KEY} (line 2, 5; the baseline lists 1 of 2)" in capsys.readouterr().err


@pytest.mark.parametrize("comment", ["noqa", "noqa: ARG001", "noqa:ARG001", "ruff: noqa", "NOQA"])
def test_noqa_comment_on_a_def_line_does_not_hide_a_finding(tmp_path: Path, comment: str) -> None:
    repo = make_repo(tmp_path, source=f"def f(path):  # {comment}\n    return 1\n")

    assert scan_keys(repo) == [UNUSED_KEY]


def test_scan_roots_include_the_repo_local_skills_tree(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    add_file(repo, ".claude/skills/demo/scripts/probe.py", "def g(args):\n    return 1\n")

    assert ".claude/skills" in SCAN_ROOTS
    assert ".claude/skills/demo/scripts/probe.py: ARG001 args in g" in scan_keys(repo)
