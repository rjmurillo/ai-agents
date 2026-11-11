"""Tests for bootstrap_review.py: repeated review failures and missed items."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bootstrap_review as br
import pytest

AS_OF = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def thread(
    tid: str,
    *,
    human: bool = True,
    body: str | None = "plain",
    path: str | None = "scripts/ci/x.py",
    age_days: float = 1,
) -> dict[str, Any]:
    created = (AS_OF - timedelta(days=age_days)).isoformat().replace("+00:00", "Z")
    return {"thread_id": tid, "created_at": created, "human": human, "body": body, "path": path}


def item(number: int, **fields: Any) -> dict[str, Any]:
    return {"number": number, "review_rounds": 1, **fields}


def failures(items: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    result: dict[str, Any] = br.mine_review_signals(items, as_of=AS_OF, **kwargs)[0]
    return result


def missed(items: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = br.mine_review_signals(items, as_of=AS_OF)[1]
    return result


def keys(result: dict[str, Any]) -> set[tuple[str, str]]:
    return {(c["signal"], c["key"]) for c in result["clusters"]}


# ----------------------------------------------------------- repeated failures


@pytest.mark.parametrize(("repeats", "clustered"), [(2, False), (3, True), (4, True)])
def test_a_cited_rule_clusters_only_at_three_pull_requests(repeats: int, clustered: bool) -> None:
    items = [
        item(n, review_threads=[thread("t", body="breaks ADR-042", path=None)])
        for n in range(1, repeats + 1)
    ]

    result = failures(items)

    assert (("rule", "ADR-042") in keys(result)) is clustered
    assert result["cluster_count"] == (1 if clustered else 0)


@pytest.mark.parametrize(("repeats", "clustered"), [(2, False), (3, True), (4, True)])
def test_a_file_area_clusters_only_at_three_pull_requests(repeats: int, clustered: bool) -> None:
    items = [item(n, review_threads=[thread("t")]) for n in range(1, repeats + 1)]

    assert (("area", "scripts/ci") in keys(failures(items))) is clustered


def test_a_bot_thread_is_not_a_human_correction() -> None:
    items = [item(n, review_threads=[thread("t", human=False)]) for n in (1, 2, 3)]

    result = failures(items)

    assert result["cluster_count"] == 0
    assert result["examined"]["threads"] == 3
    assert result["examined"]["human_threads"] == 0


def test_two_threads_on_one_pull_request_count_once() -> None:
    items = [
        item(1, review_threads=[thread("a"), thread("b")]),
        item(2, review_threads=[thread("a")]),
    ]

    assert failures(items)["cluster_count"] == 0


def test_the_window_excludes_old_threads() -> None:
    items = [item(n, review_threads=[thread("t", age_days=200)]) for n in (1, 2, 3)]

    result = failures(items)

    assert result["cluster_count"] == 0
    assert result["examined"]["interventions"] == 3
    assert result["examined"]["interventions_in_window"] == 0


def test_disposition_categories_cluster_from_the_registry() -> None:
    registry = {f"{n}:0": {"disposition": "not-applicable", "reason": "r"} for n in range(3)}

    result = failures([item(1)], dispositions=registry)

    assert ("disposition", "not-applicable") in keys(result)


def test_an_export_without_thread_data_says_so() -> None:
    result = failures([item(1), item(2)])

    assert result["thread_data_provided"] is False
    assert result["cluster_count"] == 0
    assert result["examined"]["prs"] == 2
    assert result["examined"]["prs_with_threads"] == 0


def test_an_export_with_threads_and_no_repeats_is_an_explicit_zero() -> None:
    result = failures([item(1, review_threads=[thread("t")]), item(2, review_threads=[])])

    assert result["thread_data_provided"] is True
    assert result["cluster_count"] == 0
    assert result["examined"]["prs_with_threads"] == 2
    assert result["examined"]["human_threads"] == 1


def test_a_null_thread_body_is_accepted() -> None:
    failures([item(1, review_threads=[thread("t", body=None)])])


# ------------------------------------------------------------------ missed items


def test_a_declared_introducer_places_the_fix_in_the_introducing_area() -> None:
    items = [
        item(10, files=["scripts/ci/a.py", "tests/test_a.py"]),
        item(11, introduced_by=[10]),
    ]

    result = missed(items)

    assert [
        (a["area"], a["count"], a["fix_prs"], a["introducer_prs"]) for a in result["areas"]
    ] == [
        ("scripts/ci", 1, [11], [10]),
        ("tests", 1, [11], [10]),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "This was introduced by #10.",
        "Caused by PR #10",
        "broken in #10",
        "regressed by #10",
        "A regression of #10 in the parser",
        "Regression from #10",
        "INTRODUCED BY #10",
    ],
)
def test_an_explicit_phrase_in_the_description_is_a_fix_link(text: str) -> None:
    items = [item(10, files=["src/a.py"]), item(11, body=text)]

    assert missed(items)["areas"][0]["introducer_prs"] == [10]


def test_a_phrase_in_a_commit_message_is_a_fix_link() -> None:
    items = [item(10, files=["src/a.py"]), item(11, commit_messages=["fix: introduced by #10"])]

    assert missed(items)["area_count"] == 1


@pytest.mark.parametrize(
    "text", ["Fixes #10", "See #10", "similar to #10", "closes #10", "after #10 landed"]
)
def test_a_closing_keyword_or_mention_is_not_a_fix_link(text: str) -> None:
    items = [item(10, files=["src/a.py"]), item(11, body=text)]

    result = missed(items)

    assert result["area_count"] == 0
    assert result["examined"]["fix_links"] == 0


def test_a_link_to_itself_is_ignored() -> None:
    result = missed([item(10, files=["src/a.py"], body="introduced by #10")])

    assert result["examined"]["fix_links"] == 0


def test_an_introducer_outside_the_export_is_counted_as_unresolved() -> None:
    result = missed([item(11, body="introduced by #999")])

    assert result["area_count"] == 0
    assert result["examined"] == {
        "prs": 1,
        "prs_with_files": 0,
        "fix_links": 1,
        "fix_links_resolved": 0,
        "fix_links_unresolved": 1,
    }


def test_an_introducer_without_files_is_unresolved() -> None:
    result = missed([item(10), item(11, introduced_by=[10])])

    assert result["examined"]["fix_links_unresolved"] == 1
    assert result["area_count"] == 0


def test_an_area_counts_distinct_fix_pull_requests() -> None:
    items = [
        item(10, files=["src/a.py"]),
        item(11, introduced_by=[10]),
        item(12, introduced_by=[10], body="introduced by #10"),
    ]

    area = missed(items)["areas"][0]

    assert area["count"] == 2
    assert area["fix_prs"] == [11, 12]


def test_areas_sort_by_count_then_name() -> None:
    items = [
        item(1, files=["b/x.py"]),
        item(2, files=["a/x.py"]),
        item(3, files=["c/x.py"]),
        item(4, introduced_by=[1]),
        item(5, introduced_by=[1, 2]),
        item(6, introduced_by=[3]),
    ]

    assert [(a["area"], a["count"]) for a in missed(items)["areas"]] == [
        ("b", 2),
        ("a", 1),
        ("c", 1),
    ]


def test_an_unsafe_path_gives_no_area() -> None:
    items = [item(10, files=["src/ün/x.py"]), item(11, introduced_by=[10])]

    assert missed(items)["area_count"] == 0


def test_a_null_description_is_accepted() -> None:
    assert missed([item(1, body=None)])["area_count"] == 0


# ---------------------------------------------------------------- malformed input


@pytest.mark.parametrize(
    "bad",
    [
        {"review_threads": "nope"},
        {"review_threads": ["nope"]},
        {
            "review_threads": [
                {"thread_id": "", "human": True, "created_at": "2026-11-01T00:00:00Z"}
            ]
        },
        {"review_threads": [{"thread_id": "t", "created_at": "2026-11-01T00:00:00Z"}]},
        {
            "review_threads": [
                {"thread_id": "t", "human": "yes", "created_at": "2026-11-01T00:00:00Z"}
            ]
        },
        {"review_threads": [{"thread_id": "t", "human": True, "created_at": "yesterday"}]},
        {"review_threads": [{"thread_id": "t", "human": True}]},
        {
            "review_threads": [
                {"thread_id": "t", "human": True, "created_at": "2026-11-01T00:00:00Z", "body": 3}
            ]
        },
        {
            "review_threads": [
                {"thread_id": "t", "human": True, "created_at": "2026-11-01T00:00:00Z", "path": 3}
            ]
        },
        {"files": "a.py"},
        {"files": [1]},
        {"introduced_by": ["10"]},
        {"introduced_by": [True]},
        {"introduced_by": 10},
        {"commit_messages": "x"},
        {"body": 5},
    ],
)
def test_a_malformed_review_field_raises_instead_of_reading_as_no_signal(
    bad: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        br.mine_review_signals([item(1, **bad)], as_of=AS_OF)


@pytest.mark.parametrize("number", [None, "1", True, -1])
def test_an_item_needs_an_integer_number(number: Any) -> None:
    with pytest.raises(ValueError, match="integer `number`"):
        br.mine_review_signals([{"number": number}], as_of=AS_OF)


def test_a_repeated_thread_id_on_one_pull_request_raises() -> None:
    with pytest.raises(ValueError, match="duplicate thread"):
        failures([item(1, review_threads=[thread("t"), thread("t")])])


def test_the_default_as_of_is_now() -> None:
    result, _ = br.mine_review_signals([item(1)])

    assert datetime.fromisoformat(result["as_of"]).tzinfo is not None
