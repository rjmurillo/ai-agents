"""The report names a partition that ran slower than its baselines."""

from __future__ import annotations

from scripts.testing.duration_compare import Comparison
from scripts.testing.duration_render import render_markdown
from scripts.testing.duration_snapshot import Snapshot


def test_a_slow_partition_is_named_in_the_report() -> None:
    comparison = Comparison(comparable=1, seconds=3.0, baseline=2.0, speeds={"p3": 1.56, "p1": 1.0})

    lines = render_markdown(Snapshot("s", "t"), [], comparison, 1, None)

    assert "Partition `p3` ran 1.56x slower than its baselines" in lines
    assert "Partition `p1`" not in lines


def test_the_note_starts_at_exactly_1_1x() -> None:
    comparison = Comparison(
        comparable=1, seconds=3.0, baseline=2.0, speeds={"edge": 1.1, "below": 1.09}
    )

    lines = render_markdown(Snapshot("s", "t"), [], comparison, 1, None)

    assert "Partition `edge` ran 1.10x slower" in lines
    assert "Partition `below`" not in lines
