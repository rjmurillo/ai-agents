"""Codex rollout reader tests (issue #5423, concurrency_limit).

Positive cases read the trimmed real rollouts under
`fixtures/harness_capability/codex-0.154.0-rollouts/`. Negative and edge cases
build small synthetic rollouts. No CLI runs.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from tests.eval._harness_capability_test_support import rollout
from tests.eval._rollout_test_support import REFUSAL, ROLLOUTS, line, rollout_lines

T0 = "2026-09-10T02:00:00.000Z"
T1 = "2026-09-10T02:10:00.000Z"
T2 = "2026-09-10T02:20:00.000Z"
T3 = "2026-09-10T02:30:00.000Z"


def _parse(*, start: str, end: str, balanced: bool = True) -> rollout.Rollout:
    return rollout.parse_rollout(rollout_lines("t", start=start, end=end, balanced=balanced))


def _child(
    thread_id: str, start: str, end: str, *, version: str = "0.154.0", balanced: bool = True
) -> rollout.Rollout:
    lines = rollout_lines(
        thread_id, start=start, end=end, parent="p", version=version, balanced=balanced
    )
    return rollout.parse_rollout(lines)


def _recorded() -> tuple[rollout.Rollout, list[rollout.Rollout]]:
    parent = rollout.load_rollout(ROLLOUTS / "parent.rollout.jsonl")
    children = [rollout.load_rollout(path) for path in sorted(ROLLOUTS.glob("child-*"))]
    return parent, children


# --- Recorded captures ---------------------------------------------------------


def test_recorded_children_name_the_parent_and_the_version() -> None:
    parent, children = _recorded()

    assert len(children) == 6
    assert {child.parent_thread_id for child in children} == {parent.thread_id}
    assert {child.cli_version for child in children} == {"0.154.0"}


def test_recorded_capture_peaks_at_six_running_children() -> None:
    _, children = _recorded()

    assert rollout.peak_running_children(children) == 6


def test_recorded_capture_bounds_the_limit_at_exactly_six() -> None:
    parent, children = _recorded()

    ceiling = rollout.spawn_ceiling(parent, children)

    assert ceiling is not None
    assert (ceiling.lower_bound, ceiling.upper_bound, ceiling.refusals) == (6, 6, 3)
    assert ceiling.exact


def test_recorded_compaction_counts_the_record() -> None:
    parsed = rollout.load_rollout(ROLLOUTS / "compaction.rollout.jsonl")

    assert parsed.compacted_records == 1
    assert parsed.context_compacted_events == 0


# --- Parsing -------------------------------------------------------------------


def test_string_and_list_refusal_outputs_both_count() -> None:
    lines = rollout_lines("t", start=T0, end=T1, refusals=(T0,))
    listed = {"type": "custom_tool_call_output", "output": [{"text": f"Script error:\n{REFUSAL}"}]}
    lines.append(line({"timestamp": T1, "type": "response_item", "payload": listed}))

    assert len(rollout.parse_rollout(lines).spawn_refusals) == 2


def test_other_tool_output_is_not_a_refusal() -> None:
    lines = rollout_lines("t", start=T0, end=T1)
    other = {"type": "function_call_output", "output": "spawn ok"}
    lines.append(line({"timestamp": T1, "type": "response_item", "payload": other}))
    echoed = {"type": "message", "output": REFUSAL}
    lines.append(line({"timestamp": T1, "type": "response_item", "payload": echoed}))

    assert rollout.parse_rollout(lines).spawn_refusals == ()


def test_refusal_outside_a_response_item_is_ignored() -> None:
    lines = rollout_lines("t", start=T0, end=T1)
    payload = {"type": "function_call_output", "output": REFUSAL}
    lines.append(line({"timestamp": T1, "type": "event_msg", "payload": payload}))

    assert rollout.parse_rollout(lines).spawn_refusals == ()


def test_parent_is_read_from_the_spawn_source_alone() -> None:
    meta = {
        "id": "c",
        "timestamp": T0,
        "cli_version": "0.154.0",
        "source": {"subagent": {"thread_spawn": {"parent_thread_id": "p"}}},
    }

    parsed = rollout.parse_rollout(
        [line({"timestamp": T0, "type": "session_meta", "payload": meta})]
    )

    assert parsed.parent_thread_id == "p"


def test_a_cli_rooted_thread_has_no_parent() -> None:
    meta = {"id": "c", "timestamp": T0, "cli_version": "0.154.0", "source": "cli"}

    parsed = rollout.parse_rollout(
        [line({"timestamp": T0, "type": "session_meta", "payload": meta})]
    )

    assert parsed.parent_thread_id is None


def test_disagreeing_parent_fields_are_refused() -> None:
    meta = {
        "id": "c",
        "timestamp": T0,
        "cli_version": "0.154.0",
        "parent_thread_id": "a",
        "source": {"subagent": {"thread_spawn": {"parent_thread_id": "b"}}},
    }

    with pytest.raises(rollout.RolloutError, match="disagrees"):
        rollout.parse_rollout([line({"timestamp": T0, "type": "session_meta", "payload": meta})])


def test_blank_lines_are_skipped() -> None:
    lines = ["", *rollout_lines("t", start=T0, end=T1), "   "]

    assert rollout.parse_rollout(lines).thread_id == "t"


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        ([], "empty"),
        (["not json"], "not JSON"),
        (["[1]"], "not a JSON object"),
        ([line({"type": "session_meta", "payload": {}})], "timestamp"),
        ([line({"timestamp": "yesterday", "type": "session_meta"})], "ISO timestamp"),
        ([line({"timestamp": T0, "type": "event_msg"})], "first record"),
        ([line({"timestamp": T0, "type": "session_meta", "payload": {}})], "session_meta.id"),
        (
            [line({"timestamp": T0, "type": "session_meta", "payload": {"id": "t"}})],
            "cli_version",
        ),
        (
            [
                line(
                    {
                        "timestamp": T0,
                        "type": "session_meta",
                        "payload": {"id": "t", "cli_version": "1", "timestamp": 5},
                    }
                )
            ],
            "session_meta.timestamp",
        ),
    ],
)
def test_malformed_rollouts_fail_closed(lines: list[str], message: str) -> None:
    with pytest.raises(rollout.RolloutError, match=message):
        rollout.parse_rollout(lines)


def test_task_complete_without_a_start_is_refused() -> None:
    lines = rollout_lines("t", start=T0, end=T1)
    done = {"type": "task_complete"}
    lines.append(line({"timestamp": T2, "type": "event_msg", "payload": done}))

    with pytest.raises(rollout.RolloutError, match="without a matching"):
        rollout.parse_rollout(lines)


def test_an_unclosed_turn_is_recorded_as_unbalanced() -> None:
    assert _parse(start=T0, end=T1, balanced=False).turns_balanced is False


def test_unreadable_file_is_a_rollout_error(tmp_path: Path) -> None:
    with pytest.raises(rollout.RolloutError, match="could not read"):
        rollout.load_rollout(tmp_path / "missing.jsonl")


# --- Peak running children -----------------------------------------------------


def test_overlapping_children_peak_at_two() -> None:
    children = [_child("a", T0, T2), _child("b", T1, T3)]

    assert rollout.peak_running_children(children) == 2


def test_touching_spans_do_not_overlap() -> None:
    children = [_child("a", T0, T1), _child("b", T1, T2)]

    assert rollout.peak_running_children(children) == 1


def test_no_children_measure_nothing() -> None:
    assert rollout.peak_running_children([]) is None


def test_an_unclosed_child_makes_the_peak_unmeasurable() -> None:
    children = [_child("a", T0, T2), _child("b", T1, T3, balanced=False)]

    assert rollout.peak_running_children(children) is None


# --- Spawn ceiling -------------------------------------------------------------


def _parent(*refusals: str, version: str = "0.154.0") -> rollout.Rollout:
    return rollout.parse_rollout(
        rollout_lines("p", start=T0, end=T3, version=version, refusals=refusals)
    )


def test_no_refusal_gives_no_ceiling() -> None:
    assert rollout.spawn_ceiling(_parent(), [_child("a", T0, T1)]) is None


def test_a_child_of_another_parent_is_refused() -> None:
    stray = rollout.parse_rollout(rollout_lines("a", start=T0, end=T1, parent="other"))

    assert rollout.spawn_ceiling(_parent(T2), [stray]) is None


def test_children_from_another_version_are_refused() -> None:
    other = _child("a", T0, T1, version="0.155.1")

    assert rollout.spawn_ceiling(_parent(T2), [other]) is None


def test_an_unmeasurable_peak_gives_no_ceiling() -> None:
    assert rollout.spawn_ceiling(_parent(T2), [_child("a", T0, T1, balanced=False)]) is None


def test_the_upper_bound_counts_only_children_spawned_before_the_refusal() -> None:
    early = _child("a", T0, T1)
    late = _child("b", T2, T3)

    ceiling = rollout.spawn_ceiling(_parent(T1), [early, late])

    assert ceiling is not None
    assert ceiling.upper_bound == 1


def test_bounds_that_do_not_meet_are_not_exact() -> None:
    kids = [_child("a", T0, T1), _child("b", T1, T2), _child("c", T2, T3)]

    ceiling = rollout.spawn_ceiling(_parent(T3), kids)

    assert ceiling is not None
    assert (ceiling.lower_bound, ceiling.upper_bound) == (1, 3)
    assert not ceiling.exact


def test_the_tightest_refusal_sets_the_upper_bound() -> None:
    kids = [_child("a", T0, T1), _child("b", T1, T2), _child("c", T2, T3)]

    ceiling = rollout.spawn_ceiling(_parent(T1, T3), kids)

    assert ceiling is not None
    assert ceiling.upper_bound == 2


def test_a_refusal_before_the_children_it_bounds_is_inconsistent() -> None:
    running = [_child("a", T1, T3), _child("b", T1, T3)]

    assert rollout.spawn_ceiling(_parent(T0), running) is None


def test_ceiling_carries_the_version_it_was_seen_on() -> None:
    parent = replace(_parent(T2), cli_version="0.154.0")

    ceiling = rollout.spawn_ceiling(parent, [_child("a", T0, T1)])

    assert ceiling is not None
    assert ceiling.cli_version == "0.154.0"


def test_a_review_subagent_source_has_no_parent() -> None:
    meta = {
        "id": "r",
        "timestamp": T0,
        "cli_version": "0.154.0",
        "source": {"subagent": "review"},
    }

    parsed = rollout.parse_rollout(
        [line({"timestamp": T0, "type": "session_meta", "payload": meta})]
    )

    assert parsed.parent_thread_id is None


def test_a_tool_output_with_no_text_is_not_a_refusal() -> None:
    lines = rollout_lines("t", start=T0, end=T1)
    empty = {"type": "function_call_output", "output": None}
    lines.append(line({"timestamp": T1, "type": "response_item", "payload": empty}))

    assert rollout.parse_rollout(lines).spawn_refusals == ()


def test_refusals_at_the_same_instant_bound_once() -> None:
    kids = [_child("a", T0, T1), _child("b", T0, T1)]

    ceiling = rollout.spawn_ceiling(_parent(T1, T1), kids)

    assert ceiling is not None
    assert (ceiling.lower_bound, ceiling.upper_bound, ceiling.refusals) == (2, 2, 2)
