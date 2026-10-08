"""Tests for the full-run CI pytest partition runner.

Issue #6239 acceptance criteria covered here:

- AC1: no file imports ``scripts.test_selection``.
- AC2: every pytest CI leg runs its full share on every event.
- AC4: the parallel legs are duration-balanced split groups over one pool.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts.ci import run_pytest_partition as mod

_MODULE_PATH = Path(mod.__file__)

_SPLIT_PARTITIONS = ("split-1", "split-2", "split-3", "split-4")

_EXPECTED_PARTITIONS = {*_SPLIT_PARTITIONS, "safe-push", "pr-autofix"}

_POOL_EXCLUDED = {
    "tests/test_ai_review.py",
    "tests/test_verdict.py",
    "tests/test_quality_gate.py",
    "tests/skills/github/test_wait_for_unresolved_zero.py",
    "tests/test_safe_push_pr_branch.py",
    "tests/test_mutation_workspace_signals.py",
    "tests/test_pr_autofix_late_live_state_gate.py",
}


def _flag_value(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


def _capture_runner(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_main(argv: list[str]) -> int:
        calls.append(list(argv))
        return 0

    monkeypatch.setattr(mod.run_pytest_non_tmp, "main", fake_main)
    return calls


def test_partition_names_are_the_ci_matrix_set() -> None:
    assert set(mod._PARTITION_FULL_ARGS) == _EXPECTED_PARTITIONS


def test_split_count_is_four_and_names_follow_it() -> None:
    assert mod.SPLIT_COUNT == 4
    assert mod.split_names() == list(_SPLIT_PARTITIONS)


def test_distribution_mode_is_loadfile() -> None:
    assert mod.PYTEST_DIST_MODE == "loadfile"
    assert mod._PARALLEL == ["-n", "auto", "--dist", mod.PYTEST_DIST_MODE]


@pytest.mark.parametrize("partition", sorted(_EXPECTED_PARTITIONS))
def test_main_runs_the_full_partition_args(partition: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC2: each partition hands its whole table entry to the runner."""
    calls = _capture_runner(monkeypatch)
    assert mod.main(["--partition", partition]) == 0
    assert calls == [mod._PARTITION_FULL_ARGS[partition]]


@pytest.mark.parametrize("partition", sorted(mod._PARALLEL_PARTITIONS))
def test_parallel_partitions_start_with_the_parallel_flags(partition: str) -> None:
    assert mod._PARTITION_FULL_ARGS[partition][:4] == mod._PARALLEL


@pytest.mark.parametrize("partition", ["safe-push", "pr-autofix"])
def test_serial_partitions_carry_no_parallel_flags(partition: str) -> None:
    assert "-n" not in mod._PARTITION_FULL_ARGS[partition]
    assert "--dist" not in mod._PARTITION_FULL_ARGS[partition]


def test_passthrough_args_precede_the_partition_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_runner(monkeypatch)
    mod.main(["--partition", "split-2", "--cov", "--junitxml=out.xml"])
    assert calls == [["--cov", "--junitxml=out.xml", *mod._PARTITION_FULL_ARGS["split-2"]]]


def test_unknown_partition_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        mod.main(["--partition", "nope"])
    assert excinfo.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_missing_partition_exits_2() -> None:
    with pytest.raises(SystemExit) as excinfo:
        mod.main([])
    assert excinfo.value.code == 2


def test_runner_failure_code_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.run_pytest_non_tmp, "main", lambda _argv: 1)
    assert mod.main(["--partition", "split-1"]) == 1


def test_summary_line_reports_full_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _capture_runner(monkeypatch)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    mod.main(["--partition", "split-1"])
    assert capsys.readouterr().err.strip() == "partition=split-1 mode=full"


@pytest.mark.parametrize("event", ["pull_request", "push", "merge_group", "workflow_dispatch"])
def test_event_and_selection_env_never_change_the_args(
    event: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2: the event name and any leftover PYTEST_SELECT_* env are ignored."""
    calls = _capture_runner(monkeypatch)
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("PYTEST_SELECT_BASE", "a" * 40)
    monkeypatch.setenv("PYTEST_SELECT_HEAD", "b" * 40)
    mod.main(["--partition", "split-3"])
    assert calls == [mod._PARTITION_FULL_ARGS["split-3"]]


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("tests/test_leaf.py", "split"),
        ("tests/ci/test_thing.py", "split"),
        ("tests/validation/test_thing.py", "split"),
        ("tests/mutation/test_x.py", "split"),
        ("tests/skills/github/test_wait_for_unresolved_zero.py", None),
        ("tests/test_safe_push_pr_branch.py", "safe-push"),
        ("tests/test_pr_autofix_late_live_state_gate.py", "pr-autofix"),
        ("tests/test_verdict.py", None),
    ],
)
def test_classify_partition(rel: str, expected: str | None) -> None:
    assert mod.classify_partition(rel) == expected


@pytest.mark.parametrize("index", range(1, 5))
def test_split_group_flags(index: int) -> None:
    """AC4: group i of N runs the shared pool by recorded duration."""
    args = mod._PARTITION_FULL_ARGS[f"split-{index}"]
    assert _flag_value(args, "--splits") == "4"
    assert _flag_value(args, "--group") == str(index)
    assert _flag_value(args, "--splitting-algorithm") == "duration_based_chunks"
    assert _flag_value(args, "--durations-path") == "tests/.test_durations"
    assert args[-1] == "tests/"


def test_split_groups_differ_only_in_the_group_number() -> None:
    """AC4: one pool, so no group can leave a file out or take it twice."""

    def without_group(args: list[str]) -> list[str]:
        position = args.index("--group")
        return args[:position] + args[position + 2 :]

    shapes = {tuple(without_group(mod._PARTITION_FULL_ARGS[n])) for n in _SPLIT_PARTITIONS}
    assert len(shapes) == 1


@pytest.mark.parametrize("partition", _SPLIT_PARTITIONS)
def test_split_groups_ignore_exactly_the_dedicated_and_pinned_files(partition: str) -> None:
    args = mod._PARTITION_FULL_ARGS[partition]
    ignored = {a.removeprefix("--ignore=") for a in args if a.startswith("--ignore=")}
    assert ignored == _POOL_EXCLUDED
    assert not [a for a in args if a.startswith("--ignore-glob")]


def test_durations_file_lives_beside_the_tests() -> None:
    assert mod.DURATIONS_PATH == "tests/.test_durations"


def test_dedicated_legs_run_only_their_files() -> None:
    assert mod._PARTITION_FULL_ARGS["safe-push"] == [
        "tests/test_safe_push_pr_branch.py",
        "tests/test_mutation_workspace_signals.py",
    ]
    assert mod._PARTITION_FULL_ARGS["pr-autofix"] == [
        "tests/test_pr_autofix_late_live_state_gate.py"
    ]


def test_module_never_imports_the_selector() -> None:
    """AC1: the runner has no import of scripts.test_selection."""
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            imported.append(base)
            imported.extend(f"{base}.{alias.name}" for alias in node.names)
    assert not [name for name in imported if "test_selection" in name], imported


def test_module_reads_no_selection_env_or_git() -> None:
    source = _MODULE_PATH.read_text(encoding="utf-8")
    assert "PYTEST_SELECT_" not in source
    assert "subprocess" not in source
