"""Tests for review_clusters.py: explicit-signal clustering of review interventions."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "claude"
    / "skills"
    / "skill-bootstrap"
    / "scripts"
    / "review_clusters.py"
)
_spec = importlib.util.spec_from_file_location("review_clusters_under_test", _SCRIPT)
assert _spec is not None and _spec.loader is not None
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def _iv(
    pr: int,
    *,
    thread: str | None = None,
    body: str = "please fix",
    path: str | None = "scripts/ci/tool.py",
    age_days: float = 1,
) -> dict[str, Any]:
    created = NOW - timedelta(days=age_days)
    return {
        "pr": pr,
        "thread_id": thread or f"T{pr}",
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "body": body,
        "path": path,
    }


def _run(interventions: list[dict[str, Any]], dispositions: dict[str, Any] | None = None):
    return rc.cluster_interventions(interventions, dispositions, now=NOW)


def _keys(report: dict[str, Any]) -> set[tuple[str, str]]:
    return {(c["signal"], c["key"]) for c in report["clusters"]}


def test_constants_match_the_written_definition() -> None:
    assert rc.THRESHOLD == 3
    assert rc.WINDOW_DAYS == 90
    assert "THRESHOLD`` is 3" in rc.__doc__
    assert "trailing ``WINDOW_DAYS`` days" in rc.__doc__


@pytest.mark.parametrize(
    ("repeats", "clustered"),
    [(2, False), (3, True), (4, True)],
)
def test_rule_cluster_forms_only_at_threshold(repeats: int, clustered: bool) -> None:
    items = [_iv(n, body="violates ADR-042", path=f"d{n}/x.py") for n in range(1, repeats + 1)]

    report = _run(items)

    assert (("rule", "ADR-042") in _keys(report)) is clustered
    assert report["cluster_count"] == (1 if clustered else 0)
    if clustered:
        cluster = report["clusters"][0]
        assert cluster["count"] == repeats
        assert cluster["unit"] == "pull_request"
        assert [e["pr"] for e in cluster["evidence"]] == list(range(1, repeats + 1))


@pytest.mark.parametrize(("repeats", "clustered"), [(2, False), (3, True), (4, True)])
def test_area_cluster_forms_only_at_threshold(repeats: int, clustered: bool) -> None:
    items = [_iv(n, path="scripts/ci/a.py") for n in range(1, repeats + 1)]

    report = _run(items)

    assert (("area", "scripts/ci") in _keys(report)) is clustered


def test_zero_clusters_still_reports_what_was_examined() -> None:
    report = _run([_iv(1), _iv(2)])

    assert report["cluster_count"] == 0
    assert report["clusters"] == []
    assert report["examined"] == {
        "interventions": 2,
        "interventions_in_window": 2,
        "dispositions": 0,
    }


def test_empty_input_is_zero_clusters_in_zero_interventions() -> None:
    report = _run([])

    assert report["cluster_count"] == 0
    assert report["examined"]["interventions"] == 0


def test_two_threads_on_one_pr_count_once() -> None:
    items = [
        _iv(1, thread="A", body="ADR-042", path=None),
        _iv(1, thread="B", body="ADR-042", path=None),
        _iv(2, thread="C", body="ADR-042", path=None),
    ]

    report = _run(items)

    assert report["cluster_count"] == 0


def test_evidence_lists_every_thread_on_each_pr() -> None:
    items = [
        _iv(1, thread="A", body="ADR-042", path=None),
        _iv(1, thread="B", body="ADR-042", path=None),
        _iv(2, thread="C", body="ADR-042", path=None),
        _iv(3, thread="D", body="ADR-042", path=None),
    ]

    cluster = _run(items)["clusters"][0]

    assert cluster["count"] == 3
    assert cluster["evidence"][0] == {"pr": 1, "threads": ["A", "B"]}


def test_window_excludes_old_interventions_and_keeps_the_boundary() -> None:
    items = [
        _iv(1, body="ADR-042", path=None, age_days=89.9),
        _iv(2, body="ADR-042", path=None, age_days=90),
        _iv(3, body="ADR-042", path=None, age_days=90.1),
    ]

    report = _run(items)

    assert report["examined"]["interventions"] == 3
    assert report["examined"]["interventions_in_window"] == 2
    assert report["cluster_count"] == 0


def test_old_interventions_cannot_complete_a_cluster() -> None:
    items = [
        _iv(1, body="ADR-042", path=None),
        _iv(2, body="ADR-042", path=None),
        _iv(3, body="ADR-042", path=None, age_days=200),
    ]

    assert _run(items)["cluster_count"] == 0


def test_rules_cited_finds_adr_and_rule_paths_only() -> None:
    body = "See adr 07, ADR-0042, `rules/universal.md` and README.md and voice.md."

    assert rc.rules_cited(body) == ["ADR-007", "ADR-042", "rules/universal"]


def test_rules_cited_ignores_free_text_resemblance() -> None:
    assert rc.rules_cited("this resembles the earlier correction about naming") == []


def test_one_comment_citing_two_rules_feeds_both_clusters() -> None:
    items = [_iv(n, body="ADR-042 and ADR-006", path=None) for n in (1, 2, 3)]

    assert _keys(_run(items)) == {("rule", "ADR-006"), ("rule", "ADR-042")}


@pytest.mark.parametrize(
    ("path", "area"),
    [
        ("scripts/ci/x.py", "scripts/ci"),
        ("src/claude/skills/pr-review/scripts/deep/x.py", "src/claude/skills/pr-review"),
        ("README.md", "(repo root)"),
        ("a\\b\\c.py", "a/b"),
        ("./tests/x.py", "tests"),
        (None, None),
        ("", None),
    ],
)
def test_file_area_truncates_to_depth(path: str | None, area: str | None) -> None:
    assert rc.file_area(path) == area


def test_thread_without_path_gives_no_area_signal() -> None:
    items = [_iv(n, path=None) for n in (1, 2, 3)]

    assert _run(items)["cluster_count"] == 0


@pytest.mark.parametrize(("entries", "clustered"), [(2, False), (3, True), (4, True)])
def test_disposition_tally_clusters_at_threshold(entries: int, clustered: bool) -> None:
    dispositions = {
        f"{n}:0": {"disposition": "not-applicable", "reason": "r"} for n in range(entries)
    }
    dispositions["99:0"] = {"disposition": "addressed-by-pr-metadata", "reason": "r"}

    report = _run([], dispositions)

    assert report["examined"]["dispositions"] == entries + 1
    assert (("disposition", "not-applicable") in _keys(report)) is clustered
    if clustered:
        cluster = report["clusters"][0]
        assert cluster["unit"] == "disposition_entry"
        assert cluster["count"] == entries


def test_empty_dispositions_registry_is_not_an_error() -> None:
    assert _run([_iv(1)], {})["examined"]["dispositions"] == 0
    assert _run([_iv(1)], None)["examined"]["dispositions"] == 0


def test_clusters_sort_by_count_then_signal_then_key() -> None:
    items = [_iv(n, body="ADR-042", path="a/b.py") for n in (1, 2, 3, 4)]
    items += [_iv(n, body="ADR-006", path=None, thread=f"X{n}") for n in (5, 6, 7)]

    report = _run(items)

    assert [(c["signal"], c["key"], c["count"]) for c in report["clusters"]] == [
        ("area", "a", 4),
        ("rule", "ADR-042", 4),
        ("rule", "ADR-006", 3),
    ]


@pytest.mark.parametrize(
    "bad",
    [
        "not-an-object",
        {"pr": "1", "thread_id": "T", "created_at": "2026-11-01T00:00:00Z", "body": ""},
        {"pr": True, "thread_id": "T", "created_at": "2026-11-01T00:00:00Z", "body": ""},
        {"pr": 1, "thread_id": "", "created_at": "2026-11-01T00:00:00Z", "body": ""},
        {"pr": 1, "thread_id": "T", "created_at": "2026-11-01T00:00:00Z", "body": None},
        {"pr": 1, "thread_id": "T", "created_at": "2026-11-01T00:00:00Z", "body": "", "path": 3},
        {"pr": 1, "thread_id": "T", "created_at": "yesterday", "body": ""},
        {"pr": 1, "thread_id": "T", "created_at": None, "body": ""},
    ],
)
def test_malformed_intervention_raises_instead_of_being_skipped(bad: Any) -> None:
    with pytest.raises(ValueError):
        _run([bad])


def test_duplicate_thread_raises() -> None:
    with pytest.raises(ValueError, match="duplicate thread"):
        _run([_iv(1, thread="A"), _iv(1, thread="A")])


@pytest.mark.parametrize(
    "dispositions",
    [{"1:0": "text"}, {"1:0": {"reason": "x"}}, {"1:0": {"disposition": "  "}}],
)
def test_malformed_disposition_raises(dispositions: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _run([], dispositions)


@pytest.mark.parametrize(("threshold", "window"), [(0, 90), (3, 0)])
def test_nonpositive_parameters_raise(threshold: int, window: int) -> None:
    with pytest.raises(ValueError):
        rc.cluster_interventions([], None, now=NOW, threshold=threshold, window_days=window)


def test_naive_timestamp_is_treated_as_utc() -> None:
    assert rc.parse_timestamp("2026-11-01T00:00:00") == datetime(2026, 11, 1, tzinfo=timezone.utc)
