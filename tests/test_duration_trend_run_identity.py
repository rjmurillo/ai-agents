"""duration_trend run identity: a partial, empty, or malformed event/ref exits 2.

Issue #6506 (fail-open checks): a missing or mangled CI variable used to make
the run advisory, which muted the gate on main.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.testing import duration_trend as trend
from tests.duration_test_helpers import write_history, write_junit


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
    ("event", "ref", "message"),
    [
        ("push", " refs/heads/main", "surrounding whitespace"),
        ("push ", "refs/heads/main", "surrounding whitespace"),
        ("push", "main", "must start with refs/"),
        ("push", "heads/main", "must start with refs/"),
        ("Push", "refs/heads/main", "must be a GitHub event name"),
        ("push;rm", "refs/heads/main", "must be a GitHub event name"),
        ("pull request", "refs/heads/main", "must be a GitHub event name"),
    ],
)
def test_a_malformed_event_or_ref_is_a_config_error(event: str, ref: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        trend.is_enforced(event, ref)


@pytest.mark.parametrize(
    ("event", "ref", "enforced"),
    [
        ("push", "refs/heads/main", True),
        ("pull_request", "refs/pull/12/merge", False),
        ("workflow_dispatch", "refs/heads/main", False),
        ("push", "refs/tags/v1.0.0", False),
    ],
)
def test_well_formed_identities_still_classify(event: str, ref: str, enforced: bool) -> None:
    assert trend.is_enforced(event, ref) is enforced


@pytest.mark.parametrize(
    "named",
    [
        ["--event", "push"],
        ["--ref", "refs/heads/main"],
        ["--event", "", "--ref", "refs/heads/main"],
        ["--event", "push", "--ref", ""],
        ["--event", "push", "--ref", "main"],
        ["--event", "Push", "--ref", "refs/heads/main"],
    ],
)
def test_main_exits_two_for_a_partial_empty_or_malformed_run_identity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], named: list[str]
) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [20.0, 20.0]}, 40.0)
    history = str(write_history(tmp_path, [10.0, 12.0]))

    rc = trend.main([str(report), "--history", history, *named])

    assert rc == 2
    assert "bad run identity" in capsys.readouterr().err


@pytest.mark.parametrize(
    "named",
    [
        ["--event", "push", "--ref", ""],
        ["--event", "push", "--ref", " "],
        ["--event", "", "--ref", "refs/heads/main"],
        ["--event", " ", "--ref", "refs/heads/main"],
        ["--event", "", "--ref", ""],
        ["--event", "push", "--ref", "main"],
    ],
)
def test_main_exits_two_for_a_blank_or_malformed_run_identity_under_consecutive_main(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    named: list[str],
) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "")
    monkeypatch.setenv("GITHUB_REF", "")
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [20.0, 20.0]}, 40.0)
    history = str(write_history(tmp_path, [10.0, 12.0]))

    rc = trend.main(
        [str(report), "--history", history, "--breach-policy", "consecutive-main", *named]
    )

    assert rc == 2
    assert "bad run identity" in capsys.readouterr().err


@pytest.mark.parametrize(
    "named",
    [["--event", ""], ["--ref", ""], ["--event", " push"], ["--ref", "refs/heads/main "]],
)
def test_empty_flag_is_not_replaced_by_the_github_environment(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    named: list[str],
) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/1/merge")
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [20.0, 20.0]}, 40.0)
    history = str(write_history(tmp_path, [10.0, 12.0]))

    rc = trend.main(
        [str(report), "--history", history, "--breach-policy", "consecutive-main", *named]
    )

    assert rc == 2
    assert "bad run identity" in capsys.readouterr().err


def test_main_still_runs_when_neither_event_nor_ref_is_given(tmp_path: Path) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [1.0]}, 1.0)

    assert trend.main([str(report)]) == 0
