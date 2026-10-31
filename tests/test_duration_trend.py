"""Verdicts and outputs of the duration trend CLI.

Exit-code failure paths live in ``test_duration_trend_exit_codes.py``; the
comparison rules live in ``test_duration_compare.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.testing import duration_trend as trend
from tests.duration_test_helpers import write_history, write_junit


def test_no_regression_exits_zero_and_writes_summary_and_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = write_junit(tmp_path, "pytest-results", {"tests.test_alpha": [5.0, 5.0]}, 10.0)
    summary, snap = tmp_path / "summary.md", tmp_path / "snap.json"

    rc = trend.main(
        [
            str(report),
            "--history",
            str(write_history(tmp_path, [10.0])),
            "--summary",
            str(summary),
            "--snapshot-out",
            str(snap),
            "--sha",
            "c0ffee",
        ]
    )

    assert rc == 0
    text = summary.read_text(encoding="utf-8")
    assert "No duration regression." in text
    assert "| `pytest-results` | 2 | 10.0 |" in text
    assert json.loads(snap.read_text(encoding="utf-8"))["sha"] == "c0ffee"
    assert "::warning" not in capsys.readouterr().out


def test_a_regression_exits_one_annotates_it_and_still_writes_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [20.0, 20.0]}, 40.0)
    out = tmp_path / "out.json"

    rc = trend.main(
        [
            str(report),
            "--history",
            str(write_history(tmp_path, [10.0, 12.0])),
            "--write-history",
            str(out),
        ]
    )

    assert rc == 1
    captured = capsys.readouterr()
    assert (
        "::warning title=Test duration regression::tests/test_alpha.py took 40.0s "
        "against a 11.0s median baseline (3.64x, 2 samples)"
    ) in captured.out
    assert "duration: 1 regressions in 1 comparable modules" in captured.err
    assert len(json.loads(out.read_text(encoding="utf-8"))["snapshots"]) == 3


def test_no_history_exits_zero_and_says_there_is_no_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [500.0]}, 500.0)

    assert trend.main([str(report), "--history", str(tmp_path / "absent.json")]) == 0
    assert "No comparable baseline: 0 snapshots" in capsys.readouterr().out


def test_a_malformed_history_note_reaches_the_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [1.0]}, 1.0)
    bad = tmp_path / "history.json"
    bad.write_text("{", encoding="utf-8")

    assert trend.main([str(report), "--history", str(bad)]) == 0
    assert "Note: history unreadable, starting fresh" in capsys.readouterr().out


def test_a_lower_custom_threshold_turns_a_slowdown_into_a_regression(tmp_path: Path) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [6.0, 6.0]}, 12.0)
    history = str(write_history(tmp_path, [10.0]))

    assert trend.main([str(report), "--history", history]) == 0
    assert (
        trend.main(
            [str(report), "--history", history, "--module-ratio", "1.1", "--module-min-delta", "1"]
        )
        == 1
    )


def test_the_script_runs_under_a_bare_interpreter_from_another_directory(tmp_path: Path) -> None:
    """The workflow may call it with any interpreter; the sibling imports must resolve."""
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [1.0]}, 1.0)
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "GITHUB_ACTIONS", "CI"}}

    result = subprocess.run(
        [sys.executable, "-I", str(Path(trend.__file__).resolve()), str(report)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "1 tests, 1.0 test seconds across 1 partitions." in result.stdout


@pytest.mark.parametrize(
    ("event", "ref"),
    [
        ("pull_request", "refs/pull/6244/merge"),
        ("push", "refs/heads/feature"),
        ("merge_group", "refs/heads/main"),
        ("workflow_dispatch", "refs/heads/main"),
    ],
)
def test_a_regression_outside_a_push_to_main_warns_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], event: str, ref: str
) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [20.0, 20.0]}, 40.0)
    history = str(write_history(tmp_path, [10.0, 12.0]))

    summary = tmp_path / "summary.md"

    rc = trend.main(
        [
            str(report),
            "--history",
            history,
            "--event",
            event,
            "--ref",
            ref,
            "--summary",
            str(summary),
        ]
    )

    assert rc == 0
    assert f"Advisory run ({event} on {ref})" in summary.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    assert "::warning title=Test duration regression::tests/test_alpha.py" in captured.out
    assert f"duration: advisory on event={event} ref={ref}" in captured.err


def test_a_regression_on_a_push_to_main_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [20.0, 20.0]}, 40.0)
    history = str(write_history(tmp_path, [10.0, 12.0]))

    summary = tmp_path / "summary.md"

    rc = trend.main(
        [
            str(report),
            "--history",
            history,
            "--summary",
            str(summary),
            "--event",
            "push",
            "--ref",
            "refs/heads/main",
        ]
    )

    assert rc == 1
    assert "Advisory run" not in summary.read_text(encoding="utf-8")
    assert "advisory" not in capsys.readouterr().err


@pytest.mark.parametrize(
    ("event", "ref", "enforced"),
    [
        (None, None, True),
        ("push", "refs/heads/main", True),
        ("pull_request", "refs/heads/main", False),
    ],
)
def test_only_a_push_to_main_or_an_unnamed_run_is_enforced(
    event: str | None, ref: str | None, enforced: bool
) -> None:
    assert trend.is_enforced(event, ref) is enforced


@pytest.mark.parametrize(
    ("event", "ref"),
    [
        ("push", None),
        (None, "refs/heads/main"),
        ("", "refs/heads/main"),
        ("push", ""),
        ("  ", "refs/heads/main"),
        ("push", " "),
        ("", ""),
    ],
)
def test_a_missing_or_empty_event_or_ref_is_a_config_error(
    event: str | None, ref: str | None
) -> None:
    with pytest.raises(ValueError):
        trend.is_enforced(event, ref)


@pytest.mark.parametrize(
    "named",
    [
        ["--event", "push"],
        ["--ref", "refs/heads/main"],
        ["--event", "", "--ref", "refs/heads/main"],
        ["--event", "push", "--ref", ""],
    ],
)
def test_main_exits_two_for_a_partial_or_empty_run_identity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], named: list[str]
) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [20.0, 20.0]}, 40.0)
    history = str(write_history(tmp_path, [10.0, 12.0]))

    rc = trend.main([str(report), "--history", history, *named])

    assert rc == 2
    assert "bad run identity" in capsys.readouterr().err


def test_main_still_runs_when_neither_event_nor_ref_is_given(tmp_path: Path) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [1.0]}, 1.0)

    assert trend.main([str(report)]) == 0
