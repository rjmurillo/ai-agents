"""The CI pytest partition runner passes its table entry through to pytest.

Issue #6239 acceptance criteria covered here:

- AC2: every pytest CI leg runs its full share on every event.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci import run_pytest_partition as mod
from tests.ci.run_pytest_partition_helpers import capture_runner

_EXPECTED_PARTITIONS = {"split-1", "split-2", "split-3", "split-4", "safe-push", "pr-autofix"}


@pytest.fixture(autouse=True)
def _temp_project_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """main() copies the restored timings to artifacts/durations-<leg>.json.

    Against the real root, a split-1 leg running these tests wrote copies for
    legs 2 to 4 into its own artifact. The trend job then extracted two files
    to one path at once and read invalid JSON (PR #6213, run 38111808133).
    """
    monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
    return tmp_path


def test_partition_names_are_the_ci_matrix_set() -> None:
    assert set(mod._PARTITION_FULL_ARGS) == _EXPECTED_PARTITIONS


@pytest.mark.parametrize("partition", sorted(_EXPECTED_PARTITIONS))
def test_main_runs_the_full_partition_args(partition: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC2: each partition hands its whole table entry to the runner."""
    calls = capture_runner(monkeypatch)
    assert mod.main(["--partition", partition]) == 0
    assert calls == [mod._PARTITION_FULL_ARGS[partition]]


def test_passthrough_args_precede_the_partition_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = capture_runner(monkeypatch)
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


@pytest.mark.parametrize("event", ["pull_request", "push", "merge_group", "workflow_dispatch"])
def test_event_and_selection_env_never_change_the_args(
    event: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2: the event name and any leftover PYTEST_SELECT_* env are ignored."""
    calls = capture_runner(monkeypatch)
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("PYTEST_SELECT_BASE", "a" * 40)
    monkeypatch.setenv("PYTEST_SELECT_HEAD", "b" * 40)
    mod.main(["--partition", "split-3"])
    assert calls == [mod._PARTITION_FULL_ARGS["split-3"]]


def test_main_writes_leg_timings_under_its_project_root(
    monkeypatch: pytest.MonkeyPatch, _temp_project_root: Path
) -> None:
    capture_runner(monkeypatch)
    restored = _temp_project_root / mod.DURATIONS_RESTORE_PATH
    restored.parent.mkdir(parents=True)
    restored.write_text("{}", encoding="utf-8")
    mod.main(["--partition", "split-2"])
    assert (_temp_project_root / "artifacts" / "durations-split-2.json").read_text(
        encoding="utf-8"
    ) == "{}"
