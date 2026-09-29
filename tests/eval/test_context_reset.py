"""Context compaction reader tests (issue #5423, context_reset_observability).

Positive cases read trimmed real Copilot `events.jsonl` files. Negative and
edge cases build small synthetic streams. No CLI runs.
"""

from __future__ import annotations

import pytest

from tests.eval._harness_capability_test_support import context_reset, rollout
from tests.eval._rollout_test_support import FIXTURES, ROLLOUTS, line, rollout_lines, session_start

T0 = "2026-09-10T02:00:00.000Z"


def _lines(name: str) -> list[str]:
    return (FIXTURES / name).read_text(encoding="utf-8").splitlines()


def _complete(success: object) -> str:
    return line({"type": "session.compaction_complete", "data": {"success": success}})


# --- Recorded captures ---------------------------------------------------------


def test_recorded_copilot_compaction_is_counted_with_its_version() -> None:
    observed = context_reset.observe_copilot_events(
        _lines("copilot-1.0.79-9/compaction.events.jsonl")
    )

    assert (observed.harness, observed.cli_version) == ("copilot", "1.0.79-9")
    assert (observed.compactions, observed.failed_compactions, observed.truncations) == (1, 0, 0)
    assert observed.captured_on == "2026-08-11"


def test_recorded_copilot_truncation_is_counted_apart_from_compaction() -> None:
    observed = context_reset.observe_copilot_events(
        _lines("copilot-1.0.74-0/truncation.events.jsonl")
    )

    assert (observed.compactions, observed.truncations) == (0, 1)
    assert observed.resets == 1
    assert observed.captured_on == "2026-07-27"


def test_recorded_codex_rollout_counts_its_compaction() -> None:
    parsed = rollout.load_rollout(ROLLOUTS / "compaction.rollout.jsonl")

    observed = context_reset.observe_codex_rollout(parsed)

    assert (observed.harness, observed.cli_version, observed.compactions) == ("codex", "0.154.0", 1)
    assert observed.captured_on == parsed.started_at.date().isoformat()


# --- Copilot parsing -----------------------------------------------------------


def test_a_failed_compaction_is_not_a_compaction() -> None:
    observed = context_reset.observe_copilot_events(
        [session_start(), _complete(False), _complete(True)]
    )

    assert (observed.compactions, observed.failed_compactions) == (1, 1)
    assert observed.resets == 1


def test_a_failed_compaction_alone_is_not_a_reset() -> None:
    observed = context_reset.observe_copilot_events([session_start(), _complete(False)])

    assert (observed.failed_compactions, observed.resets) == (1, 0)


def test_a_started_compaction_that_never_completes_is_not_counted() -> None:
    start = line({"type": "session.compaction_start", "data": {}})

    observed = context_reset.observe_copilot_events([session_start(), start])

    assert observed.resets == 0


def test_a_quiet_session_has_no_events() -> None:
    assert context_reset.observe_copilot_events([session_start(), "", "  "]).resets == 0


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        ([], "empty"),
        (["not json"], "not JSON"),
        (["[]"], "not a JSON object"),
        ([_complete(True)], "first event must be session.start"),
        ([line({"type": "session.start", "data": {}})], "copilotVersion"),
        ([line({"type": "session.start"})], "copilotVersion"),
        ([line({"type": "session.start", "data": {"copilotVersion": "1"}})], "timestamp"),
        ([line({"type": "session.start", "data": {"copilotVersion": " "}})], "copilotVersion"),
        ([session_start(), _complete("yes")], "boolean"),
        ([session_start(), line({"type": "session.compaction_complete"})], "boolean"),
    ],
)
def test_malformed_copilot_streams_fail_closed(lines: list[str], message: str) -> None:
    with pytest.raises(context_reset.ContextResetError, match=message):
        context_reset.observe_copilot_events(lines)


# --- Codex counting ------------------------------------------------------------


def _codex(records: int, events: int) -> rollout.Rollout:
    lines = rollout_lines("t", start=T0, end=T0)
    lines += [line({"timestamp": T0, "type": "compacted", "payload": {}})] * records
    event = {"type": "context_compacted"}
    lines += [line({"timestamp": T0, "type": "event_msg", "payload": event})] * events
    return rollout.parse_rollout(lines)


@pytest.mark.parametrize(
    ("records", "events", "expected"),
    [(0, 0, 0), (2, 0, 2), (0, 3, 3), (1, 1, 1), (2, 1, 2)],
)
def test_codex_compactions_are_the_larger_of_record_and_event(
    records: int, events: int, expected: int
) -> None:
    assert context_reset.observe_codex_rollout(_codex(records, events)).compactions == expected
