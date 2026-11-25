"""A review thread never spans splits (review finding 3).

The predict prompt carries the other comments of a row's thread. A dev prediction for one
comment therefore shows the text of a heldout comment from the same thread unless the split
keeps the thread whole.
"""

from __future__ import annotations

import importlib
import random
from typing import Any

from tests.eval._actionability_arms_test_support import make_row

cc = importlib.import_module("scripts.eval.actionability_corpus")


def _thread_rows(prefix: str, bodies: list[str], pr_number: int) -> list[dict[str, Any]]:
    """One row per body, each carrying the other bodies as thread replies."""
    return [
        make_row(
            f"{prefix}{i}",
            pr_number=pr_number,
            body=body,
            thread_replies=[other for j, other in enumerate(bodies) if j != i],
        )
        for i, body in enumerate(bodies)
    ]


def _split_of(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {row["id"]: row["split"] for row in rows}


class TestThreadsStayWhole:
    def test_two_rows_of_one_thread_share_a_split_for_every_seed(self) -> None:
        """With dev-count 2 and a two-row thread among singles, the thread is never cut."""
        for seed in range(30):
            band = [
                *_thread_rows("T", ["fix this", "and that"], 1),
                *_thread_rows("S", ["alone one"], 2),
                *_thread_rows("U", ["alone two"], 3),
            ]

            cc.assign_splits(band, [], 2, random.Random(seed))

            split = _split_of(band)
            assert split["T0"] == split["T1"], seed

    def test_dev_rows_hold_no_heldout_comment_in_their_replies(self) -> None:
        """The leak itself: no dev row quotes a heldout row's body."""
        for seed in range(30):
            band = [
                *_thread_rows("T", ["a one", "a two", "a three"], 1),
                *_thread_rows("S", ["s one", "s two"], 2),
                *_thread_rows("U", ["u one"], 3),
            ]

            cc.assign_splits(band, [], 3, random.Random(seed))

            heldout_bodies = {r["body"] for r in band if r["split"] == "heldout"}
            for row in band:
                if row["split"] == "dev":
                    assert not heldout_bodies & set(row["thread_replies"]), seed

    def test_single_row_threads_still_fill_dev_count_exactly(self) -> None:
        """No over-fire: unrelated rows keep the old exact dev-count behavior."""
        band = [make_row(f"R{i}", pr_number=i + 1, body=f"b{i}") for i in range(8)]

        cc.assign_splits(band, [], 3, random.Random(1))

        splits = [row["split"] for row in band]
        assert splits.count("dev") == 3
        assert splits.count("heldout") == 5

    def test_same_body_in_other_prs_is_a_different_thread(self) -> None:
        """Two PRs that both say LGTM are separate threads and can split."""
        band = [
            make_row("P1", pr_number=1, body="LGTM"),
            make_row("P2", pr_number=2, body="LGTM"),
        ]

        cc.assign_splits(band, [], 1, random.Random(0))

        assert sorted(_split_of(band).values()) == ["dev", "heldout"]

    def test_a_thread_that_does_not_fit_leaves_dev_short(self) -> None:
        """Edge: dev-count 1 with only two-row threads takes no dev row."""
        band = [*_thread_rows("T", ["x one", "x two"], 1), *_thread_rows("S", ["y", "z"], 2)]

        cc.assign_splits(band, [], 1, random.Random(0))

        assert {r["split"] for r in band} == {"heldout"}

    def test_a_thread_shared_with_an_outside_row_stays_heldout(self) -> None:
        """A dev prompt must not show an outside comment either."""
        shared = _thread_rows("T", ["in band", "outside one"], 1)
        band, outside = [shared[0]], [shared[1]]
        other = make_row("S0", pr_number=2, body="solo")
        band.append(other)

        cc.assign_splits(band, outside, 2, random.Random(0))

        assert band[0]["split"] == "heldout"
        assert outside[0]["split"] == "outside"
        assert other["split"] == "dev"
