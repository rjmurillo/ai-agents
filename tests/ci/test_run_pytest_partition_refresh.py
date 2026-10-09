"""`--refresh-durations` rewrites the committed durations file in one run.

Issue #6239: the refresh runs the whole split pool once, never splits, and is
mutually exclusive with `--partition`.
"""

from __future__ import annotations

import pytest

from scripts.ci import run_pytest_partition as mod
from tests.ci.run_pytest_partition_helpers import capture_runner


def test_refresh_durations_runs_the_whole_pool_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = capture_runner(monkeypatch)
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
    calls = capture_runner(monkeypatch)
    mod.main(["--refresh-durations"])
    assert not {"--splits", "--group", "--splitting-algorithm"} & set(calls[0])


def test_refresh_durations_passes_extra_args_through(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = capture_runner(monkeypatch)
    mod.main(["--refresh-durations", "-q"])
    assert calls[0][0] == "-q"


def test_refresh_durations_summary_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    capture_runner(monkeypatch)
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
