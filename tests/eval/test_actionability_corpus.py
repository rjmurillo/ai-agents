"""Tests for sample and the secret scan in scripts/eval/actionability_corpus.py.

Plan M1-T7 and M1-T9. Shared helpers: _actionability_corpus_test_support.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tests.eval._actionability_corpus_test_support import (
    BAND_BODY,
    FROZEN_NOW,
    SHA40,
    cc,
    corpus_prs,
    make_node,
    make_pr,
    make_thread,
    read_rows,
    sample_args,
    write_prs,
)

pytestmark = pytest.mark.usefixtures("freeze_actionability_clock")


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cc, "utc_now_iso", lambda: FROZEN_NOW)


class TestBuildRows:
    def test_row_stores_score_reasons_band_and_node_id_at_sampling_time(self) -> None:
        """Plan M1-T7, premortem R1: score and reasons are stored on the row."""
        prs = [make_pr(7, make_thread(make_node("PRRC_1", f"{BAND_BODY} x")))]

        rows, skipped = cc.build_rows(prs, FROZEN_NOW)

        assert len(rows) == 1
        row = rows[0]
        assert row["id"] == "PRRC_1"
        assert row["pr_number"] == 7
        assert row["reviewer"] == "alice"
        assert row["thread_position"] == 0
        assert row["path"] == "src/a.py"
        assert row["heuristic_score"] == 0.5
        assert row["heuristic_reasons"] == []
        assert row["in_band"] is True
        assert row["diff_hunk"] is None
        assert row["label"] is None
        assert row["sampled_at"] == FROZEN_NOW
        assert skipped.unknown_position == 0

    def test_thread_replies_hold_the_other_nodes_in_order(self) -> None:
        """Plan M1-T7: replies are stored for arm C input only."""
        opener = make_node("N0", "Opening comment here", created_at="2026-11-20T00:00:00Z")
        mid = make_node("N1", "Middle reply", login="bob", created_at="2026-11-21T00:00:00Z")
        last = make_node("N2", "Last reply", login="carol", created_at="2026-11-22T00:00:00Z")
        prs = [make_pr(1, make_thread(opener, mid, last))]

        rows, _ = cc.build_rows(prs, FROZEN_NOW)
        by_id = {r["id"]: r for r in rows}

        assert by_id["N1"]["thread_position"] == 1
        assert by_id["N1"]["thread_replies"] == ["Opening comment here", "Last reply"]
        assert by_id["N0"]["thread_replies"] == ["Middle reply", "Last reply"]

    def test_unknown_position_is_skipped_and_counted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Plan M1-T7: comments whose thread position is unknown are skipped and counted."""
        monkeypatch.setattr(cc, "thread_position", lambda _comment: cc.UNKNOWN_POSITION)

        rows, skipped = cc.build_rows(corpus_prs(band=2, outside=0), FROZEN_NOW)

        assert rows == []
        assert skipped.unknown_position == 2

    def test_duplicate_node_id_is_skipped_and_counted(self) -> None:
        """Plan M1-T7: two comments that resolve to one node id yield one row."""
        twin_a = make_node("DUP", "Same body here", created_at="2026-11-20T00:00:00Z")
        twin_b = make_node("OTHER", "Same body here", created_at="2026-11-20T00:00:00Z")
        prs = [make_pr(1, make_thread(twin_a, twin_b))]

        rows, skipped = cc.build_rows(prs, FROZEN_NOW)

        assert [r["id"] for r in rows] == ["DUP"]
        assert skipped.duplicate_id == 1

    def test_node_without_id_is_skipped_and_counted(self) -> None:
        """Plan M1-T7: a row needs a node id to be labeled and fetched."""
        node = make_node("", f"{BAND_BODY} y")
        del node["id"]

        rows, skipped = cc.build_rows([make_pr(1, make_thread(node))], FROZEN_NOW)

        assert rows == []
        assert skipped.missing_id == 1


class TestSampleCli:
    def test_writes_rows_with_split_counts_and_returns_zero(self, tmp_path: Path) -> None:
        """Plan M1-T7: dev-count band rows are dev, the rest heldout, outside rows outside."""
        prs = write_prs(tmp_path / "prs.json", corpus_prs())
        out = tmp_path / "corpus.jsonl"

        code = cc.main(sample_args(prs, out))

        assert code == 0
        rows = read_rows(out)
        splits = [r["split"] for r in rows]
        assert splits.count("dev") == 2
        assert splits.count("heldout") == 2
        assert splits.count("outside") == 4
        assert all(r["in_band"] for r in rows if r["split"] in ("dev", "heldout"))
        assert not any(r["in_band"] for r in rows if r["split"] == "outside")
        assert len({r["id"] for r in rows}) == len(rows)

    def test_every_reviewer_is_present_in_each_stratum(self, tmp_path: Path) -> None:
        """Plan M1-T7: every reviewer appears when the count allows it."""
        prs = write_prs(tmp_path / "prs.json", corpus_prs(band=9, outside=9))
        out = tmp_path / "corpus.jsonl"

        code = cc.main(sample_args(prs, out, **{"band-count": 3, "outside-count": 3}))

        assert code == 0
        rows = read_rows(out)
        for in_band in (True, False):
            reviewers = {r["reviewer"] for r in rows if r["in_band"] is in_band}
            assert reviewers == {"alice", "bob", "carol"}

    def test_same_seed_and_input_give_byte_identical_output(self, tmp_path: Path) -> None:
        """Plan M1-T7: seeded sampling is reproducible."""
        prs = write_prs(tmp_path / "prs.json", corpus_prs(band=12, outside=12))
        first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"

        assert cc.main(sample_args(prs, first, **{"seed": 5})) == 0
        assert cc.main(sample_args(prs, second, **{"seed": 5})) == 0

        assert first.read_bytes() == second.read_bytes()

    def test_different_seed_changes_the_selection(self, tmp_path: Path) -> None:
        """Plan M1-T7: the seed drives the pick."""
        prs = write_prs(tmp_path / "prs.json", corpus_prs(band=12, outside=12))
        first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"

        assert cc.main(sample_args(prs, first, **{"seed": 1})) == 0
        assert cc.main(sample_args(prs, second, **{"seed": 2})) == 0

        assert first.read_bytes() != second.read_bytes()

    def test_shortfall_takes_all_rows_warns_and_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Plan M1-T7: a stratum with fewer rows than requested keeps all and warns."""
        prs = write_prs(tmp_path / "prs.json", corpus_prs(band=3, outside=3))
        out = tmp_path / "corpus.jsonl"

        code = cc.main(sample_args(prs, out, **{"band-count": 10, "outside-count": 10}))

        assert code == 0
        assert len(read_rows(out)) == 6
        assert "warning" in capsys.readouterr().err.lower()

    def test_returns_two_on_unreadable_prs(self, tmp_path: Path) -> None:
        """Plan M1-T7: an unreadable --prs file is a config error."""
        out = tmp_path / "corpus.jsonl"

        code = cc.main(sample_args(tmp_path / "missing.json", out))

        assert code == 2
        assert not out.exists()

    def test_returns_two_when_prs_is_not_a_list(self, tmp_path: Path) -> None:
        """Plan M1-T7: --prs must hold a JSON array."""
        prs = write_prs(tmp_path / "prs.json", {"not": "a list"})
        out = tmp_path / "corpus.jsonl"

        assert cc.main(sample_args(prs, out)) == 2
        assert not out.exists()

    def test_returns_two_on_negative_count(self, tmp_path: Path) -> None:
        """Plan M1-T7: a negative count is a config error."""
        prs = write_prs(tmp_path / "prs.json", corpus_prs())

        code = cc.main(sample_args(prs, tmp_path / "o.jsonl", **{"band-count": -1}))

        assert code == 2


class TestSecretScan:
    def _prs_with_body(self, body: str) -> list[dict[str, Any]]:
        return [make_pr(1, make_thread(make_node("PRRC_SECRET", body)))]

    def test_github_token_fails_with_exit_one_and_no_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Plan M1-T9, premortem R4: a planted token blocks the corpus."""
        token = "ghp_" + "A1b2C3d4" * 5
        prs = write_prs(tmp_path / "prs.json", self._prs_with_body(f"use {token} here"))
        out = tmp_path / "corpus.jsonl"

        code = cc.main(sample_args(prs, out, **{"dev-count": 0}))

        err = capsys.readouterr().err
        assert code == 1
        assert not out.exists()
        assert "PRRC_SECRET" in err
        assert "github-token" in err
        assert token not in err

    def test_secret_in_a_reply_fails_too(self, tmp_path: Path) -> None:
        """Plan M1-T9: replies feed arm C, so they are scanned."""
        token = "ghp_" + "Z9y8X7w6" * 5
        now = datetime.now(UTC)
        opener = make_node(
            "O1",
            f"{BAND_BODY} q",
            created_at=(now - timedelta(hours=2)).isoformat(),
        )
        reply = make_node(
            "R1",
            f"my token {token}",
            login="bob",
            created_at=(now - timedelta(hours=1)).isoformat(),
        )
        prs = write_prs(tmp_path / "prs.json", [make_pr(1, make_thread(opener, reply))])
        out = tmp_path / "corpus.jsonl"

        assert cc.main(sample_args(prs, out, **{"outside-count": 0, "dev-count": 0})) == 1
        assert not out.exists()

    def test_commit_sha_passes_and_is_reported_for_review(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Plan M1-T9, premortem R4: hex-only hits do not fail and are listed."""
        body = f"{BAND_BODY} see commit {SHA40}"
        prs = write_prs(tmp_path / "prs.json", self._prs_with_body(body))
        out = tmp_path / "corpus.jsonl"

        code = cc.main(sample_args(prs, out, **{"dev-count": 0}))

        err = capsys.readouterr().err
        assert code == 0
        assert out.exists()
        assert "review: hex-like strings in rows" in err
        assert "PRRC_SECRET" in err
        assert SHA40 not in err
