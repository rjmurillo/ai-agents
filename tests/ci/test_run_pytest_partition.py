"""The CI pytest partition runner passes its table entry through to pytest.

Issue #6239 acceptance criteria covered here:

- AC2: every pytest CI leg runs its full share on every event.
"""

from __future__ import annotations

import pytest

from scripts.ci import run_pytest_partition as mod

_EXPECTED_PARTITIONS = {"split-1", "split-2", "split-3", "split-4", "safe-push", "pr-autofix"}


def _capture_runner(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_main(argv: list[str]) -> int:
        calls.append(list(argv))
        return 0

    monkeypatch.setattr(mod.run_pytest_non_tmp, "main", fake_main)
    return calls


def test_partition_names_are_the_ci_matrix_set() -> None:
    assert set(mod._PARTITION_FULL_ARGS) == _EXPECTED_PARTITIONS


@pytest.mark.parametrize("partition", sorted(_EXPECTED_PARTITIONS))
def test_main_runs_the_full_partition_args(partition: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC2: each partition hands its whole table entry to the runner."""
    calls = _capture_runner(monkeypatch)
    assert mod.main(["--partition", partition]) == 0
    assert calls == [mod._PARTITION_FULL_ARGS[partition]]


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
