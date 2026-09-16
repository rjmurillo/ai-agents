"""Percentile arithmetic for gate_latency (REQ-027 AC-04, AC-05).

Split from ``test_gate_latency.py`` so both stay under the 400-line taste
warning threshold, and because these exercise ``gate_latency_stats``, which
is its own module: pure functions over sample lists, no subprocess and no
clock, so the expectations below are hand-computed rather than observed.
"""

from __future__ import annotations

import pytest

from scripts.metrics import gate_latency_stats as gls

# --- Percentiles (nearest-rank, 1-indexed) -----------------------------------


@pytest.mark.parametrize(
    ("values", "p50", "p95"),
    [
        ([5.0], 5.0, 5.0),
        ([1.0, 2.0], 1.0, 2.0),
        ([1.0, 2.0, 3.0], 2.0, 3.0),
        ([1.0, 2.0, 3.0, 4.0, 5.0], 3.0, 5.0),
        (list(range(1, 21)), 10.0, 19.0),
    ],
)
def test_positive_nearest_rank_percentile_hand_computed(
    values: list[float], p50: float, p95: float
) -> None:
    assert gls._nearest_rank_percentile(values, 50) == p50
    assert gls._nearest_rank_percentile(values, 95) == p95


def test_negative_percentile_of_empty_sample_raises() -> None:
    with pytest.raises(ValueError, match="empty sample"):
        gls._nearest_rank_percentile([], 50)


@pytest.mark.parametrize("n", [1, 2, 3, 5, 19])
def test_positive_percentile_note_present_below_20(n: int) -> None:
    note = gls._percentile_note(n)
    assert note is not None
    assert "upper-order statistic" in note


@pytest.mark.parametrize("n", [20, 21, 100])
def test_negative_percentile_note_absent_at_or_above_20(n: int) -> None:
    assert gls._percentile_note(n) is None




def test_positive_a_group_row_is_flagged_by_its_deeper_successor() -> None:
    """lefthook prints a group's own row above its members, indented less."""
    from scripts.metrics import lefthook_summary as ls

    stdout = (
        "summary: (done in 10.00 seconds)\n"
        "✓ group (7) (18.000 seconds)\n"
        "  ✓ child-a (10.000 seconds)\n"
        "  ✓ child-b (8.000 seconds)\n"
        "✓ leaf-job (1.000 seconds)\n"
    )

    samples, _ = ls.parse_summary(stdout)

    by_name = {s.name: s for s in samples}
    assert by_name["group (7)"].is_group is True
    assert by_name["child-a"].is_group is False
    assert by_name["child-b"].is_group is False
    assert by_name["leaf-job"].is_group is False


def test_positive_a_group_total_can_exceed_the_hook_wall_clock_and_is_labelled() -> None:
    """The reason the label exists: the sum of a parallel group's members.

    ci-scripts.md MUST-17 records that lefthook reports a group's duration as
    the sum of its members regardless of scheduling, so a parallel group can
    report more seconds than the whole hook took. Without a label, that row
    reads as a job costing more than the run that contained it.
    """
    from scripts.metrics import gate_latency_models as models
    from scripts.metrics import lefthook_summary as ls

    stdout = (
        "summary: (done in 10.00 seconds)\n"
        "✓ group (7) (18.000 seconds)\n"
        "  ✓ child-a (10.000 seconds)\n"
        "  ✓ child-b (8.000 seconds)\n"
    )
    samples, _ = ls.parse_summary(stdout)
    run = models.HookRun(
        repetition_index=0,
        exit_code=0,
        wall_clock_seconds=10.0,
        lefthook_reported_seconds=10.0,
        jobs_parsed=len(samples),
        tree_mutated=False,
        unknown_status_count=0,
        samples=samples,
    )

    summaries = gls._build_summaries([run])

    by_scope = {s.scope: s for s in summaries}
    assert by_scope["group (7)"].max > by_scope["__hook__"].max
    assert by_scope["group (7)"].is_group is True
    assert by_scope["child-a"].is_group is False
