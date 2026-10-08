"""The CI pytest partition runner passes its table entry through to pytest.

Issue #6239 acceptance criteria covered here:

- AC2: every pytest CI leg runs its full share on every event.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.ci import run_pytest_non_tmp
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


def test_summary_line_for_a_dedicated_leg_is_partition_and_mode_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _capture_runner(monkeypatch)
    mod.main(["--partition", "safe-push"])
    assert capsys.readouterr().err.strip() == "partition=safe-push mode=full"


def test_summary_line_for_a_split_leg_names_the_split_and_durations_hash(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _capture_runner(monkeypatch)
    durations = tmp_path / "durations"
    durations.write_bytes(b'{"a::t": 1.0}')
    monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(mod, "DURATIONS_PATH", "durations")
    digest = hashlib.sha256(b'{"a::t": 1.0}').hexdigest()[:12]
    mod.main(["--partition", "split-3"])
    assert capsys.readouterr().err.strip() == (
        "partition=split-3 mode=full splits=4 group=3 "
        f"durations=durations durations_sha256={digest}"
    )


def test_summary_line_reports_a_missing_durations_file(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _capture_runner(monkeypatch)
    monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
    mod.main(["--partition", "split-1"])
    assert capsys.readouterr().err.strip().endswith("durations_sha256=missing")


def test_a_directory_at_the_durations_path_reports_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / mod.DURATIONS_PATH).mkdir()
    monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
    assert mod._durations_digest() == "missing"


def test_relative_durations_path_resolves_because_the_runner_sets_cwd_to_the_root() -> None:
    """pytest receives the relative path; run_pytest_non_tmp runs it from the root.

    tests/ci/test_pytest_non_tmp_policy.py pins cwd == PROJECT_ROOT for the
    subprocess call. This pins the other half: both modules agree on the root
    and the committed file exists beneath it.
    """
    assert run_pytest_non_tmp.PROJECT_ROOT == mod._PROJECT_ROOT
    assert (run_pytest_non_tmp.PROJECT_ROOT / mod.DURATIONS_PATH).is_file()


def test_refresh_durations_runs_the_whole_pool_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_runner(monkeypatch)
    assert mod.main(["--refresh-durations"]) == 0
    assert calls == [
        [
            "-n",
            "auto",
            "--dist",
            "loadfile",
            "--store-durations",
            "--clean-durations",
            "--durations-path",
            mod.DURATIONS_PATH,
            *mod._POOL_IGNORES,
            "tests/",
        ]
    ]


def test_refresh_durations_never_splits(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_runner(monkeypatch)
    mod.main(["--refresh-durations"])
    assert not {"--splits", "--group", "--splitting-algorithm"} & set(calls[0])


def test_refresh_durations_passes_extra_args_through(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_runner(monkeypatch)
    mod.main(["--refresh-durations", "-q"])
    assert calls[0][0] == "-q"


def test_refresh_durations_summary_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _capture_runner(monkeypatch)
    mod.main(["--refresh-durations"])
    assert capsys.readouterr().err.strip() == (
        f"refresh-durations mode=refresh durations={mod.DURATIONS_PATH}"
    )


def test_refresh_durations_and_partition_are_mutually_exclusive(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        mod.main(["--refresh-durations", "--partition", "split-1"])
    assert excinfo.value.code == 2
    assert "not allowed with" in capsys.readouterr().err


def test_refresh_durations_failure_code_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod.run_pytest_non_tmp, "main", lambda _argv: 5)
    assert mod.main(["--refresh-durations"]) == 5


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
