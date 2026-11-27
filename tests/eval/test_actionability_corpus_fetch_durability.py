"""Durability tests for fetch-hunks: partial output, resume, and safe error text.

Plan M1-T8 and M1-T9 follow-up (group 3). Shared helpers:
_actionability_corpus_test_support.py.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.eval._actionability_corpus_test_support import (
    FROZEN_NOW,
    FakeGraphql,
    cc,
    corpus_row,
    read_rows,
    write_corpus,
)

pytestmark = pytest.mark.usefixtures("freeze_actionability_clock")

_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cc, "utc_now_iso", lambda: FROZEN_NOW)


class _RaisingGraphql(FakeGraphql):
    """Answers from the table, then raises ``error`` for the row named ``fail_on``."""

    def __init__(self, hunks: dict[str, str | None], fail_on: str, error: BaseException) -> None:
        super().__init__(hunks, fail_on=None)
        self._fail_on = fail_on
        self._error = error

    def __call__(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        if (variables or {}).get("id") == self._fail_on:
            self.calls.append((query, variables or {}))
            raise self._error
        return super().__call__(query, variables)


def _argv(corpus: Path, out: Path) -> list[str]:
    return ["fetch-hunks", "--corpus", str(corpus), "--output", str(out)]


def _three_rows(tmp_path: Path) -> Path:
    rows = [corpus_row("A"), corpus_row("B"), corpus_row("C")]
    return write_corpus(tmp_path / "c.jsonl", rows)


class TestTransportFailures:
    @pytest.mark.parametrize(
        ("error", "name"),
        [
            (subprocess.TimeoutExpired(cmd="gh", timeout=30), "TimeoutExpired"),
            (FileNotFoundError("gh not installed"), "FileNotFoundError"),
            (PermissionError("denied"), "PermissionError"),
            (RuntimeError("graphql failed"), "RuntimeError"),
        ],
    )
    def test_transport_error_exits_three_and_names_class_and_row(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        error: BaseException,
        name: str,
    ) -> None:
        """Group 3a and 3d: timeout, OSError, and RuntimeError all exit 3 with a safe message."""
        monkeypatch.setattr(cc, "gh_graphql", _RaisingGraphql({"A": "@@ a"}, "B", error))
        out = tmp_path / "o.jsonl"

        code = cc.main(_argv(_three_rows(tmp_path), out))

        err = capsys.readouterr().err
        assert code == 3
        assert "row B" in err
        assert name in err

    def test_error_text_is_never_printed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Group 3d: a GraphQL error can embed a response body, so only the class name prints."""
        leak = RuntimeError(f"response body with {_TOKEN} and SECRETWORD")
        monkeypatch.setattr(cc, "gh_graphql", _RaisingGraphql({}, "A", leak))

        code = cc.main(_argv(_three_rows(tmp_path), tmp_path / "o.jsonl"))

        seen = capsys.readouterr()
        assert code == 3
        assert "SECRETWORD" not in seen.out + seen.err
        assert _TOKEN not in seen.out + seen.err


class TestPartialOutput:
    def test_rows_fetched_before_a_failure_are_written_with_their_status(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Group 3b and 3c: partial output keeps fetched rows and leaves the rest unresolved."""
        error = RuntimeError("down")
        monkeypatch.setattr(cc, "gh_graphql", _RaisingGraphql({"A": "@@ a"}, "B", error))
        out = tmp_path / "o.jsonl"

        code = cc.main(_argv(_three_rows(tmp_path), out))

        rows = read_rows(out)
        assert code == 3
        assert [r["id"] for r in rows] == ["A", "B", "C"]
        assert [r["diff_hunk"] for r in rows] == ["@@ a", None, None]
        assert [r["hunk_status"] for r in rows] == ["fetched", None, None]
        assert "fetched 1 of 3 rows" in capsys.readouterr().err

    def test_a_failure_on_the_first_row_still_writes_a_resumable_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 3b: even zero progress leaves a valid corpus to resume from."""
        monkeypatch.setattr(cc, "gh_graphql", _RaisingGraphql({}, "A", RuntimeError("x")))
        out = tmp_path / "o.jsonl"

        assert cc.main(_argv(_three_rows(tmp_path), out)) == 3
        assert [r["id"] for r in read_rows(out)] == ["A", "B", "C"]

    def test_secret_in_a_fetched_hunk_blocks_the_partial_write(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Group 3b: scan first. A row that fails the scan is never written, even on abort."""
        fake = _RaisingGraphql({"A": f"@@\n+TOKEN = '{_TOKEN}'"}, "B", RuntimeError("down"))
        monkeypatch.setattr(cc, "gh_graphql", fake)
        out = tmp_path / "o.jsonl"

        code = cc.main(_argv(_three_rows(tmp_path), out))

        err = capsys.readouterr().err
        assert code == 1
        assert not out.exists()
        assert "row A" in err
        assert "github-token" in err
        assert "fetched 1 of 3 rows" in err
        assert _TOKEN not in err

    def test_secret_scan_failure_without_a_transport_error_names_progress(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Group 3b: the success path reports progress when the scan blocks the write."""
        monkeypatch.setattr(cc, "gh_graphql", FakeGraphql({"A": _TOKEN, "B": "@@", "C": "@@"}))
        out = tmp_path / "o.jsonl"

        code = cc.main(_argv(_three_rows(tmp_path), out))

        assert code == 1
        assert not out.exists()
        assert "fetched 3 of 3 rows" in capsys.readouterr().err


class TestHunkStatusAndResume:
    def test_status_distinguishes_fetched_no_hunk_and_unresolved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 3c: every row ends with fetched or no_hunk after a clean run."""
        monkeypatch.setattr(cc, "gh_graphql", FakeGraphql({"A": "@@ a", "B": None, "C": ""}))
        out = tmp_path / "o.jsonl"

        assert cc.main(_argv(_three_rows(tmp_path), out)) == 0

        assert [r["hunk_status"] for r in read_rows(out)] == ["fetched", "no_hunk", "no_hunk"]

    def test_rerun_skips_fetched_and_no_hunk_rows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 3c: a row already known to have no hunk is not asked again."""
        rows = [
            corpus_row("A", diff_hunk="@@ a", hunk_status="fetched"),
            corpus_row("B", diff_hunk=None, hunk_status="no_hunk"),
            corpus_row("C"),
        ]
        corpus = write_corpus(tmp_path / "c.jsonl", rows)
        fake = FakeGraphql({"C": "@@ c"})
        monkeypatch.setattr(cc, "gh_graphql", fake)
        out = tmp_path / "o.jsonl"

        assert cc.main(_argv(corpus, out)) == 0

        assert [v["id"] for _, v in fake.calls] == ["C"]
        assert [r["hunk_status"] for r in read_rows(out)] == ["fetched", "no_hunk", "fetched"]

    def test_a_hunk_with_no_status_counts_as_fetched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 3c: a corpus written before hunk_status existed still resumes."""
        corpus = write_corpus(tmp_path / "c.jsonl", [corpus_row("A", diff_hunk="@@ old")])
        fake = FakeGraphql({})
        monkeypatch.setattr(cc, "gh_graphql", fake)
        out = tmp_path / "o.jsonl"

        assert cc.main(_argv(corpus, out)) == 0

        assert fake.calls == []
        assert read_rows(out)[0]["hunk_status"] == "fetched"

    def test_a_failed_run_resumes_from_its_own_partial_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 3b and 3c: rerun on the partial output fetches only what is left."""
        monkeypatch.setattr(
            cc, "gh_graphql", _RaisingGraphql({"A": "@@ a"}, "B", RuntimeError("down"))
        )
        partial = tmp_path / "partial.jsonl"
        assert cc.main(_argv(_three_rows(tmp_path), partial)) == 3
        resumed = FakeGraphql({"B": "@@ b", "C": "@@ c"})
        monkeypatch.setattr(cc, "gh_graphql", resumed)
        final = tmp_path / "final.jsonl"

        assert cc.main(_argv(partial, final)) == 0

        assert [v["id"] for _, v in resumed.calls] == ["B", "C"]
        assert [r["diff_hunk"] for r in read_rows(final)] == ["@@ a", "@@ b", "@@ c"]

    def test_sample_rows_start_with_a_null_hunk_status(self, tmp_path: Path) -> None:
        """Group 3c: sample writes the field so the corpus shape is uniform."""
        from tests.eval._actionability_corpus_test_support import corpus_prs, write_prs

        prs = write_prs(tmp_path / "prs.json", corpus_prs(band=2, outside=0))
        out = tmp_path / "corpus.jsonl"
        argv = ["sample", "--prs", str(prs), "--output", str(out)]

        assert (
            cc.main([*argv, "--band-count", "2", "--outside-count", "0", "--dev-count", "1"]) == 0
        )
        assert {r["hunk_status"] for r in read_rows(out)} == {None}
