"""Scope, call identity and read bounds of the native Copilot journal reader (issue #7357).

Every journal here is synthetic. The cases pin the decisions from the PR review:
one working directory per context event, a truncated or failed read is never
available, and lines are bounded before they are decoded.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _copilot_journal_helpers import assert_unavailable as _assert_unavailable
from _copilot_journal_helpers import (
    complete,
    context_event,
    journal_mod,
    session_start,
    start,
    write_journal,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = (tmp_path / "repo").resolve()
    root.mkdir()
    return root


@pytest.fixture
def journal_path(tmp_path: Path) -> Path:
    return tmp_path / "copilot-home" / "session-state" / "s1" / "events.jsonl"


# Scope rule: a context event records one working directory, cwd else gitRoot.


def _available(report: dict) -> bool:
    return report["available"] is True and report["reason"] == ""


def test_cwd_inside_with_git_root_equal_to_the_repo_is_in_scope(
    repo: Path, journal_path: Path
) -> None:
    rows = [context_event("session.start", repo, repo), start("c1"), complete("c1")]
    write_journal(journal_path, rows)

    assert _available(journal_mod.extract_receipts(journal_path, repo))


def test_cwd_in_a_subdirectory_is_in_scope_when_project_dir_is_that_subdirectory(
    repo: Path, journal_path: Path
) -> None:
    sub = repo / "pkg"
    sub.mkdir()
    rows = [context_event("session.start", sub, repo), start("c1"), complete("c1")]
    write_journal(journal_path, rows)

    assert _available(journal_mod.extract_receipts(journal_path, sub))


def test_cwd_outside_is_out_of_scope_even_when_git_root_is_inside(
    repo: Path, tmp_path: Path, journal_path: Path
) -> None:
    rows = [context_event("session.start", tmp_path, repo), start("c1"), complete("c1")]
    write_journal(journal_path, rows)

    _assert_unavailable(journal_mod.extract_receipts(journal_path, repo), "outside the repository")


def test_git_root_elsewhere_does_not_override_a_cwd_inside(
    repo: Path, tmp_path: Path, journal_path: Path
) -> None:
    elsewhere = (tmp_path / "elsewhere").resolve()
    elsewhere.mkdir()
    rows = [context_event("session.start", repo, elsewhere), start("c1"), complete("c1")]
    write_journal(journal_path, rows)

    assert _available(journal_mod.extract_receipts(journal_path, repo))


def test_git_root_is_the_directory_only_when_cwd_is_absent(
    repo: Path, tmp_path: Path, journal_path: Path
) -> None:
    inside = write_journal(
        journal_path, [context_event("session.start", None, repo), start("c1"), complete("c1")]
    )
    outside = write_journal(
        tmp_path / "second" / "events.jsonl",
        [context_event("session.start", None, tmp_path), start("c1"), complete("c1")],
    )

    assert _available(journal_mod.extract_receipts(inside, repo))
    _assert_unavailable(journal_mod.extract_receipts(outside, repo), "outside the repository")


@pytest.mark.parametrize(
    "data",
    [
        {"context": {"cwd": "/a", "gitRoot": "/b"}},
        {"context": {"gitRoot": "/b"}},
        {"context": {"cwd": "", "gitRoot": "/b"}},
        {"context": {"cwd": 7, "gitRoot": "/b"}},
        {"context": {}},
        {"context": "not-a-dict"},
        {"cwd": "/a", "gitRoot": "/b"},
    ],
)
def test_recorded_cwd_matches_skill_doctor(data: dict) -> None:
    parser = journal_mod._load_doctor()[1]
    meta: dict[str, Any] = {"cwd": None, "cwd_history": [], "started_at": None}

    parser._copilot_context(meta, data, None)

    assert journal_mod._recorded_cwd(data) == meta["cwd"]


# Call identity: matching uses the full id, display uses a bounded one.


def test_call_ids_sharing_a_long_prefix_stay_two_calls(repo: Path, journal_path: Path) -> None:
    prefix = "x" * (journal_mod._MAX_FIELD_CHARS + 10)
    first, second = prefix + "-first", prefix + "-second"
    rows = [
        session_start(repo),
        start(first),
        start(second),
        complete(first, True),
        complete(second, False),
    ]
    write_journal(journal_path, rows)

    report = journal_mod.extract_receipts(journal_path, repo)

    assert [r["outcome"] for r in report["receipts"]] == ["succeeded", "failed"]
    assert all(len(r["call_id"]) <= journal_mod._MAX_FIELD_CHARS for r in report["receipts"])
    assert report["completions_without_retained_start"] == 0


# Read budget: malformed, blank and oversized lines count before decoding.


def test_malformed_lines_count_against_the_line_budget(
    repo: Path, journal_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(journal_mod, "MAX_LINES", 5)
    write_journal(journal_path, [session_start(repo), *["{bad"] * 20])

    report = journal_mod.extract_receipts(journal_path, repo)

    _assert_unavailable(report, "read cap")
    assert report["lines_read"] == 5
    assert report["records_truncated"] is True
    assert report["malformed_lines"] == 4


def test_a_journal_exactly_at_the_line_budget_is_not_truncated(
    repo: Path, journal_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(journal_mod, "MAX_LINES", 3)
    write_journal(journal_path, [session_start(repo), start("c1"), complete("c1")])

    report = journal_mod.extract_receipts(journal_path, repo)

    assert _available(report)
    assert report["lines_read"] == 3
    assert report["records_truncated"] is False


def test_a_line_over_the_length_cap_makes_the_journal_unavailable(
    repo: Path, journal_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(journal_mod, "MAX_LINE_CHARS", 200)
    huge = json.dumps(start("huge", "bash", {"command": "y" * 5000}))
    write_journal(journal_path, [session_start(repo), huge, start("c1"), complete("c1")])

    report = journal_mod.extract_receipts(journal_path, repo)

    _assert_unavailable(report, "over the length cap")
    assert report["oversized_lines"] == 1


def test_reading_stops_at_the_first_oversized_line(
    repo: Path, journal_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(journal_mod, "MAX_LINE_CHARS", 200)
    huge = json.dumps(start("huge", "bash", {"command": "y" * 50_000}))
    rows = [session_start(repo), huge] + [start(f"c{i}") for i in range(5)]
    write_journal(journal_path, rows)

    report = journal_mod.extract_receipts(journal_path, repo)

    _assert_unavailable(report, "over the length cap")
    assert report["lines_read"] == 2
    assert report["oversized_lines"] == 1


def test_an_oversized_context_change_cannot_hide_an_outside_directory(
    repo: Path, journal_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(journal_mod, "MAX_LINE_CHARS", 300)
    outside = str(tmp_path / "elsewhere")
    hidden = {
        "type": "session.context_changed",
        "timestamp": "t",
        "data": {"context": {"cwd": outside}, "pad": "z" * 1000},
    }
    write_journal(
        journal_path,
        [session_start(repo), json.dumps(hidden), start("c1"), complete("c1")],
    )

    report = journal_mod.extract_receipts(journal_path, repo)

    _assert_unavailable(report, "over the length cap")


def test_a_line_exactly_at_the_length_cap_is_still_parsed(
    repo: Path, journal_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = start("c1", arguments={"pad": ""})
    pad = 300 - len(json.dumps(row))
    row = start("c1", arguments={"pad": "p" * pad})
    assert len(json.dumps(row)) == 300
    monkeypatch.setattr(journal_mod, "MAX_LINE_CHARS", 300)
    write_journal(journal_path, [session_start(repo), row, complete("c1")])

    report = journal_mod.extract_receipts(journal_path, repo)

    assert _available(report)
    assert report["oversized_lines"] == 0


def test_deeply_nested_json_is_counted_malformed_not_a_crash(
    repo: Path, journal_path: Path
) -> None:
    deep = "[" * 200_000 + "]" * 200_000
    write_journal(journal_path, [session_start(repo), deep, start("c1"), complete("c1")])

    report = journal_mod.extract_receipts(journal_path, repo)

    assert _available(report)
    assert report["malformed_lines"] == 1


# Truncation and read failures never read as complete.


def test_record_cap_before_an_outside_context_change_is_not_in_scope(
    repo: Path, tmp_path: Path, journal_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moved = context_event("session.context_changed", tmp_path)
    write_journal(journal_path, [session_start(repo), start("c1"), complete("c1"), moved])

    full = journal_mod.extract_receipts(journal_path, repo)
    monkeypatch.setattr(journal_mod, "MAX_RECORDS", 3)
    capped = journal_mod.extract_receipts(journal_path, repo)

    _assert_unavailable(full, "outside the repository")
    _assert_unavailable(capped, "read cap")


class _FailingStream:
    """Serve the journal lines, then fail the way a dropped disk or share does."""

    def __init__(self, text: str) -> None:
        self._lines = text.splitlines(keepends=True)

    def __enter__(self) -> _FailingStream:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def readline(self, size: int | None = -1) -> str:
        if not self._lines:
            raise OSError(5, "Input/output error")
        return self._lines.pop(0)


def test_read_failure_after_valid_events_is_unavailable(
    repo: Path, journal_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_journal(journal_path, [session_start(repo), start("c1"), complete("c1")])
    real_open = Path.open
    target = journal_path.resolve()
    text = journal_path.read_text(encoding="utf-8")

    def flaky_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == target:
            return _FailingStream(text)
        return real_open(self, *args, **kwargs)

    control = journal_mod.extract_receipts(journal_path, repo)
    monkeypatch.setattr(Path, "open", flaky_open)
    failed = journal_mod.extract_receipts(journal_path, repo)

    assert _available(control)
    _assert_unavailable(failed, "read failed: OSError")
    assert failed["records_read"] == 3
