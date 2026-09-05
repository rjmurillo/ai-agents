"""Tests for the import-graph-narrowed CI pytest runner."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.ci import run_pytest_selected as mod
from scripts.test_selection.select_tests import Selection

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("tests/test_leaf.py", "bulk"),
        ("tests/ci/test_thing.py", "bulk-nested"),
        ("tests/mutation/test_x.py", "mutation"),
        ("tests/test_safe_push_pr_branch.py", "safe-push"),
        ("tests/test_mutation_workspace_signals.py", "safe-push"),
        ("tests/test_pr_autofix_late_live_state_gate.py", "pr-autofix"),
        ("tests/test_verdict.py", None),
        ("tests/skills/github/test_wait_for_unresolved_zero.py", None),
    ],
)
def test_classify_partition(rel: str, expected: str | None) -> None:
    assert mod.classify_partition(rel) == expected


def test_full_args_carry_the_matrix_shape() -> None:
    assert mod._PARTITION_FULL_ARGS["bulk"][-1] == "tests/"
    assert "--ignore-glob=tests/*/*" in mod._PARTITION_FULL_ARGS["bulk"]
    assert mod._PARTITION_FULL_ARGS["mutation"] == [
        "-n",
        "auto",
        "--dist",
        "loadfile",
        "tests/mutation",
    ]


def test_resolve_merge_group_runs_full() -> None:
    args, reason = mod.resolve_partition_args("bulk", "merge_group", "origin/main", _REPO_ROOT)
    assert args == mod._PARTITION_FULL_ARGS["bulk"]
    assert reason.startswith("full")


def test_resolve_full_when_diff_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.select_tests, "changed_from_git", lambda *_: None)
    args, reason = mod.resolve_partition_args("bulk", "push", "origin/main", _REPO_ROOT)
    assert args == mod._PARTITION_FULL_ARGS["bulk"]
    assert "could not diff" in reason


def test_resolve_full_on_fail_safe_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.select_tests, "changed_from_git", lambda *_: ["README.md"])
    monkeypatch.setattr(
        mod.select_tests, "select", lambda *_a, **_k: Selection(full=True, reason="non-Python")
    )
    args, _ = mod.resolve_partition_args("bulk", "push", "origin/main", _REPO_ROOT)
    assert args == mod._PARTITION_FULL_ARGS["bulk"]


def test_resolve_subset_for_owning_partition(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.select_tests, "changed_from_git", lambda *_: ["pkg/x.py"])
    monkeypatch.setattr(
        mod.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=False, reason="subset", tests=("tests/test_leaf.py",)),
    )
    args, reason = mod.resolve_partition_args("bulk", "push", "origin/main", _REPO_ROOT)
    assert args == ["-n", "auto", "--dist", "loadfile", "tests/test_leaf.py"]
    assert reason.startswith("subset")


def test_resolve_full_for_partition_without_affected_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.select_tests, "changed_from_git", lambda *_: ["pkg/x.py"])
    monkeypatch.setattr(
        mod.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=False, reason="subset", tests=("tests/test_leaf.py",)),
    )
    args, _ = mod.resolve_partition_args("mutation", "push", "origin/main", _REPO_ROOT)
    assert args == mod._PARTITION_FULL_ARGS["mutation"]


def test_resolve_full_when_unpartitioned_test_is_affected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.select_tests, "changed_from_git", lambda *_: ["pkg/x.py"])
    monkeypatch.setattr(
        mod.select_tests,
        "select",
        lambda *_a, **_k: Selection(
            full=False, reason="subset", tests=("tests/test_leaf.py", "tests/test_verdict.py")
        ),
    )
    args, _ = mod.resolve_partition_args("bulk", "push", "origin/main", _REPO_ROOT)
    assert args == mod._PARTITION_FULL_ARGS["bulk"]


def test_serial_partition_subset_has_no_parallel_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.select_tests, "changed_from_git", lambda *_: ["scripts/x.py"])
    monkeypatch.setattr(
        mod.select_tests,
        "select",
        lambda *_a, **_k: Selection(
            full=False, reason="subset", tests=("tests/test_safe_push_pr_branch.py",)
        ),
    )
    args, _ = mod.resolve_partition_args("safe-push", "push", "origin/main", _REPO_ROOT)
    assert args == ["tests/test_safe_push_pr_branch.py"]


def _capture_diff_args(monkeypatch: pytest.MonkeyPatch, changed: list[str]) -> list[tuple]:
    """Record every changed_from_git call and answer with ``changed``."""
    calls: list[tuple] = []

    def _fake(*args: object) -> list[str]:
        calls.append(args)
        return changed

    monkeypatch.setattr(mod.select_tests, "changed_from_git", _fake)
    return calls


def test_pull_request_diffs_the_explicit_base_and_head_shas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, head = "a" * 40, "b" * 40
    calls = _capture_diff_args(monkeypatch, ["pkg/x.py"])
    monkeypatch.setattr(
        mod.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=False, reason="subset", tests=("tests/test_leaf.py",)),
    )
    args, reason = mod.resolve_partition_args("bulk", "pull_request", base, _REPO_ROOT, head)
    assert args == ["-n", "auto", "--dist", "loadfile", "tests/test_leaf.py"]
    assert calls == [(_REPO_ROOT, base, head)]
    assert reason == f"subset: 1 affected test file(s) [{base}...{head}]"


def test_pull_request_without_head_sha_runs_full_without_diffing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_diff_args(monkeypatch, ["pkg/x.py"])
    args, reason = mod.resolve_partition_args("bulk", "pull_request", "a" * 40, _REPO_ROOT, "")
    assert args == mod._PARTITION_FULL_ARGS["bulk"]
    assert reason == "full: pull_request without explicit base and head SHAs"
    assert calls == []


def test_pull_request_without_base_sha_runs_full_without_diffing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_diff_args(monkeypatch, ["pkg/x.py"])
    args, reason = mod.resolve_partition_args("bulk", "pull_request", "", _REPO_ROOT, "b" * 40)
    assert args == mod._PARTITION_FULL_ARGS["bulk"]
    assert reason == "full: pull_request without explicit base and head SHAs"
    assert calls == []


def test_push_without_head_sha_still_diffs_against_the_checkout_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_diff_args(monkeypatch, ["pkg/x.py"])
    monkeypatch.setattr(
        mod.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=False, reason="subset", tests=("tests/test_leaf.py",)),
    )
    _, reason = mod.resolve_partition_args("bulk", "push", "c" * 40, _REPO_ROOT)
    assert calls == [(_REPO_ROOT, "c" * 40, "HEAD")]
    assert reason.endswith(f"[{'c' * 40}...HEAD]")


def test_empty_base_falls_back_to_the_default_branch_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_diff_args(monkeypatch, ["pkg/x.py"])
    monkeypatch.setattr(
        mod.select_tests, "select", lambda *_a, **_k: Selection(full=True, reason="non-Python")
    )
    args, reason = mod.resolve_partition_args("bulk", "workflow_dispatch", "", _REPO_ROOT)
    assert args == mod._PARTITION_FULL_ARGS["bulk"]
    assert calls == [(_REPO_ROOT, mod._DEFAULT_BASE, "HEAD")]
    assert reason == f"full: non-Python [{mod._DEFAULT_BASE}...HEAD]"


def test_unfetchable_commit_names_both_ends_of_the_span(monkeypatch: pytest.MonkeyPatch) -> None:
    base, head = "a" * 40, "b" * 40
    monkeypatch.setattr(mod.select_tests, "changed_from_git", lambda *_: None)
    args, reason = mod.resolve_partition_args("bulk", "pull_request", base, _REPO_ROOT, head)
    assert args == mod._PARTITION_FULL_ARGS["bulk"]
    assert reason == f"full: could not diff {base}...{head}"


def test_main_reads_the_head_sha_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    base, head = "a" * 40, "b" * 40
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("PYTEST_SELECT_BASE", base)
    monkeypatch.setenv("PYTEST_SELECT_HEAD", head)
    calls = _capture_diff_args(monkeypatch, ["pkg/x.py"])
    monkeypatch.setattr(
        mod.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=False, reason="subset", tests=("tests/test_leaf.py",)),
    )
    monkeypatch.setattr(mod.run_pytest_non_tmp, "main", lambda _argv: 0)
    assert mod.main(["--partition", "bulk"]) == 0
    assert calls == [(mod._PROJECT_ROOT, base, head)]


def test_main_runs_full_when_the_pull_request_head_sha_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, list[str]] = {}
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("PYTEST_SELECT_BASE", "a" * 40)
    monkeypatch.delenv("PYTEST_SELECT_HEAD", raising=False)
    calls = _capture_diff_args(monkeypatch, ["pkg/x.py"])
    monkeypatch.setattr(
        mod.run_pytest_non_tmp, "main", lambda argv: captured.setdefault("argv", argv) and 0 or 0
    )
    assert mod.main(["--partition", "bulk"]) == 0
    assert captured["argv"] == mod._PARTITION_FULL_ARGS["bulk"]
    assert calls == []


def test_main_reports_the_span_and_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base, head = "a" * 40, "b" * 40
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("PYTEST_SELECT_BASE", base)
    monkeypatch.setenv("PYTEST_SELECT_HEAD", head)
    _capture_diff_args(monkeypatch, ["pkg/x.py"])
    monkeypatch.setattr(
        mod.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=False, reason="subset", tests=("tests/test_leaf.py",)),
    )
    monkeypatch.setattr(mod.run_pytest_non_tmp, "main", lambda _argv: 0)
    mod.main(["--partition", "bulk"])
    err = capsys.readouterr().err
    assert "mode=subset" in err
    assert f"{base}...{head}" in err


def test_main_returns_runner_failure_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "merge_group")
    monkeypatch.setattr(mod.run_pytest_non_tmp, "main", lambda _argv: 3)
    assert mod.main(["--partition", "bulk"]) == 3


def test_main_delegates_built_argv_to_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setattr(mod.select_tests, "changed_from_git", lambda *_: ["pkg/x.py"])
    monkeypatch.setattr(
        mod.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=False, reason="subset", tests=("tests/test_leaf.py",)),
    )
    monkeypatch.setattr(
        mod.run_pytest_non_tmp, "main", lambda argv: captured.setdefault("argv", argv) and 0 or 0
    )
    code = mod.main(["--partition", "bulk", "--cov", "--junitxml=out.xml"])
    assert code == 0
    assert captured["argv"] == [
        "--cov",
        "--junitxml=out.xml",
        "-n",
        "auto",
        "--dist",
        "loadfile",
        "tests/test_leaf.py",
    ]


def test_workflow_partitions_match_runner_definitions() -> None:
    workflow = yaml.safe_load((_REPO_ROOT / ".github/workflows/pytest.yml").read_text())
    include = workflow["jobs"]["test"]["strategy"]["matrix"]["include"]
    partitions = {entry["partition"] for entry in include}
    assert partitions == set(mod._PARTITION_FULL_ARGS)
