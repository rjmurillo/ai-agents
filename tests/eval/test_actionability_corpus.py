"""Tests for scripts/eval/actionability_corpus.py (plan M1-T7 to M1-T10)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval" / "actionability_corpus.py"
_FROZEN_NOW = "2026-11-24T12:00:00+00:00"
_SHA40 = "a" * 40


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("actionability_corpus", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cc = _load_module()


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cc, "utc_now_iso", lambda: _FROZEN_NOW)


def _node(
    node_id: str,
    body: str,
    login: str = "alice",
    created_at: str = "2026-11-20T00:00:00Z",
) -> dict[str, Any]:
    return {
        "id": node_id,
        "body": body,
        "author": {"login": login},
        "createdAt": created_at,
        "path": "src/a.py",
    }


def _thread(*nodes: dict[str, Any]) -> dict[str, Any]:
    return {"isResolved": False, "isOutdated": False, "comments": {"nodes": list(nodes)}}


def _pr(number: int, *threads: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": number,
        "author": {"login": "owner"},
        "reviewThreads": {"nodes": list(threads)},
    }


_BAND_BODY = "Consider a helper here"
_OUTSIDE_BODY = "Critical security vulnerability: injection"


def _corpus_prs(band: int = 6, outside: int = 6) -> list[dict[str, Any]]:
    """Reviewers alice, bob, carol; band rows score 0.5, outside rows score far from it."""
    logins = ["alice", "bob", "carol"]
    threads = []
    for i in range(band):
        node = _node(f"B{i}", f"{_BAND_BODY} {i}", login=logins[i % 3])
        threads.append(_thread(node))
    for i in range(outside):
        node = _node(f"O{i}", f"{_OUTSIDE_BODY} {i}", login=logins[i % 3])
        threads.append(_thread(node))
    return [_pr(1, *threads)]


def _write_prs(path: Path, prs: Any) -> Path:
    path.write_text(json.dumps(prs), encoding="utf-8")
    return path


def _read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _sample_args(prs: Path, out: Path, **overrides: Any) -> list[str]:
    opts: dict[str, Any] = {"band-count": 4, "outside-count": 4, "dev-count": 2}
    opts.update(overrides)
    argv = ["sample", "--prs", str(prs), "--output", str(out)]
    for key, value in opts.items():
        argv += [f"--{key}", str(value)]
    return argv


class TestBuildRows:
    def test_row_stores_score_reasons_band_and_node_id_at_sampling_time(self) -> None:
        """Plan M1-T7, premortem R1: score and reasons are stored on the row."""
        prs = [_pr(7, _thread(_node("PRRC_1", f"{_BAND_BODY} x")))]

        rows, skipped = cc.build_rows(prs, _FROZEN_NOW)

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
        assert row["sampled_at"] == _FROZEN_NOW
        assert skipped.unknown_position == 0

    def test_thread_replies_hold_the_other_nodes_in_order(self) -> None:
        """Plan M1-T7: replies are stored for arm C input only."""
        opener = _node("N0", "Opening comment here", created_at="2026-11-20T00:00:00Z")
        mid = _node("N1", "Middle reply", login="bob", created_at="2026-11-21T00:00:00Z")
        last = _node("N2", "Last reply", login="carol", created_at="2026-11-22T00:00:00Z")
        prs = [_pr(1, _thread(opener, mid, last))]

        rows, _ = cc.build_rows(prs, _FROZEN_NOW)
        by_id = {r["id"]: r for r in rows}

        assert by_id["N1"]["thread_position"] == 1
        assert by_id["N1"]["thread_replies"] == ["Opening comment here", "Last reply"]
        assert by_id["N0"]["thread_replies"] == ["Middle reply", "Last reply"]

    def test_unknown_position_is_skipped_and_counted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Plan M1-T7: comments whose thread position is unknown are skipped and counted."""
        monkeypatch.setattr(cc, "thread_position", lambda _comment: cc.UNKNOWN_POSITION)

        rows, skipped = cc.build_rows(_corpus_prs(band=2, outside=0), _FROZEN_NOW)

        assert rows == []
        assert skipped.unknown_position == 2

    def test_duplicate_node_id_is_skipped_and_counted(self) -> None:
        """Plan M1-T7: two comments that resolve to one node id yield one row."""
        twin_a = _node("DUP", "Same body here", created_at="2026-11-20T00:00:00Z")
        twin_b = _node("OTHER", "Same body here", created_at="2026-11-20T00:00:00Z")
        prs = [_pr(1, _thread(twin_a, twin_b))]

        rows, skipped = cc.build_rows(prs, _FROZEN_NOW)

        assert [r["id"] for r in rows] == ["DUP"]
        assert skipped.duplicate_id == 1

    def test_node_without_id_is_skipped_and_counted(self) -> None:
        """Plan M1-T7: a row needs a node id to be labeled and fetched."""
        node = _node("", f"{_BAND_BODY} y")
        del node["id"]

        rows, skipped = cc.build_rows([_pr(1, _thread(node))], _FROZEN_NOW)

        assert rows == []
        assert skipped.missing_id == 1


class TestSampleCli:
    def test_writes_rows_with_split_counts_and_returns_zero(self, tmp_path: Path) -> None:
        """Plan M1-T7: dev-count band rows are dev, the rest heldout, outside rows outside."""
        prs = _write_prs(tmp_path / "prs.json", _corpus_prs())
        out = tmp_path / "corpus.jsonl"

        code = cc.main(_sample_args(prs, out))

        assert code == 0
        rows = _read_rows(out)
        splits = [r["split"] for r in rows]
        assert splits.count("dev") == 2
        assert splits.count("heldout") == 2
        assert splits.count("outside") == 4
        assert all(r["in_band"] for r in rows if r["split"] in ("dev", "heldout"))
        assert not any(r["in_band"] for r in rows if r["split"] == "outside")
        assert len({r["id"] for r in rows}) == len(rows)

    def test_every_reviewer_is_present_in_each_stratum(self, tmp_path: Path) -> None:
        """Plan M1-T7: every reviewer appears when the count allows it."""
        prs = _write_prs(tmp_path / "prs.json", _corpus_prs(band=9, outside=9))
        out = tmp_path / "corpus.jsonl"

        code = cc.main(_sample_args(prs, out, **{"band-count": 3, "outside-count": 3}))

        assert code == 0
        rows = _read_rows(out)
        for in_band in (True, False):
            reviewers = {r["reviewer"] for r in rows if r["in_band"] is in_band}
            assert reviewers == {"alice", "bob", "carol"}

    def test_same_seed_and_input_give_byte_identical_output(self, tmp_path: Path) -> None:
        """Plan M1-T7: seeded sampling is reproducible."""
        prs = _write_prs(tmp_path / "prs.json", _corpus_prs(band=12, outside=12))
        first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"

        assert cc.main(_sample_args(prs, first, **{"seed": 5})) == 0
        assert cc.main(_sample_args(prs, second, **{"seed": 5})) == 0

        assert first.read_bytes() == second.read_bytes()

    def test_different_seed_changes_the_selection(self, tmp_path: Path) -> None:
        """Plan M1-T7: the seed drives the pick."""
        prs = _write_prs(tmp_path / "prs.json", _corpus_prs(band=12, outside=12))
        first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"

        assert cc.main(_sample_args(prs, first, **{"seed": 1})) == 0
        assert cc.main(_sample_args(prs, second, **{"seed": 2})) == 0

        assert first.read_bytes() != second.read_bytes()

    def test_shortfall_takes_all_rows_warns_and_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Plan M1-T7: a stratum with fewer rows than requested keeps all and warns."""
        prs = _write_prs(tmp_path / "prs.json", _corpus_prs(band=3, outside=3))
        out = tmp_path / "corpus.jsonl"

        code = cc.main(_sample_args(prs, out, **{"band-count": 10, "outside-count": 10}))

        assert code == 0
        assert len(_read_rows(out)) == 6
        assert "warning" in capsys.readouterr().err.lower()

    def test_returns_two_on_unreadable_prs(self, tmp_path: Path) -> None:
        """Plan M1-T7: an unreadable --prs file is a config error."""
        out = tmp_path / "corpus.jsonl"

        code = cc.main(_sample_args(tmp_path / "missing.json", out))

        assert code == 2
        assert not out.exists()

    def test_returns_two_when_prs_is_not_a_list(self, tmp_path: Path) -> None:
        """Plan M1-T7: --prs must hold a JSON array."""
        prs = _write_prs(tmp_path / "prs.json", {"not": "a list"})
        out = tmp_path / "corpus.jsonl"

        assert cc.main(_sample_args(prs, out)) == 2
        assert not out.exists()

    def test_returns_two_on_negative_count(self, tmp_path: Path) -> None:
        """Plan M1-T7: a negative count is a config error."""
        prs = _write_prs(tmp_path / "prs.json", _corpus_prs())

        code = cc.main(_sample_args(prs, tmp_path / "o.jsonl", **{"band-count": -1}))

        assert code == 2


class TestSecretScan:
    def _prs_with_body(self, body: str) -> list[dict[str, Any]]:
        return [_pr(1, _thread(_node("PRRC_SECRET", body)))]

    def test_github_token_fails_with_exit_one_and_no_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Plan M1-T9, premortem R4: a planted token blocks the corpus."""
        token = "ghp_" + "A1b2C3d4" * 5
        prs = _write_prs(tmp_path / "prs.json", self._prs_with_body(f"use {token} here"))
        out = tmp_path / "corpus.jsonl"

        code = cc.main(_sample_args(prs, out))

        err = capsys.readouterr().err
        assert code == 1
        assert not out.exists()
        assert "PRRC_SECRET" in err
        assert "github-token" in err
        assert token not in err

    def test_secret_in_a_reply_fails_too(self, tmp_path: Path) -> None:
        """Plan M1-T9: replies feed arm C, so they are scanned."""
        token = "ghp_" + "Z9y8X7w6" * 5
        opener = _node("O1", f"{_BAND_BODY} q", created_at="2026-11-20T00:00:00Z")
        reply = _node("R1", f"my token {token}", login="bob", created_at="2026-11-21T00:00:00Z")
        prs = _write_prs(tmp_path / "prs.json", [_pr(1, _thread(opener, reply))])
        out = tmp_path / "corpus.jsonl"

        assert cc.main(_sample_args(prs, out, **{"outside-count": 0})) == 1
        assert not out.exists()

    def test_commit_sha_passes_and_is_reported_for_review(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Plan M1-T9, premortem R4: hex-only hits do not fail and are listed."""
        body = f"{_BAND_BODY} see commit {_SHA40}"
        prs = _write_prs(tmp_path / "prs.json", self._prs_with_body(body))
        out = tmp_path / "corpus.jsonl"

        code = cc.main(_sample_args(prs, out))

        err = capsys.readouterr().err
        assert code == 0
        assert out.exists()
        assert "review: hex-like strings in rows" in err
        assert "PRRC_SECRET" in err
        assert _SHA40 not in err
