"""fetch-hunks writes its progress as it goes (review finding 6).

Plan M1-T8. Progress used to live in memory until the end, so an unexpected exception or a
Ctrl-C threw away every hunk already fetched. Shared helpers:
_actionability_corpus_test_support.py.
"""

from __future__ import annotations

import os
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

_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cc, "utc_now_iso", lambda: FROZEN_NOW)


class _Scripted(FakeGraphql):
    """Answers every id with a hunk, runs ``hook(call_number, id)`` before each answer."""

    def __init__(self, hook: Any, secret_on: str | None = None) -> None:
        super().__init__({})
        self._hook = hook
        self._secret_on = secret_on

    def __call__(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        node_id = (variables or {})["id"]
        self.calls.append((query, variables or {}))
        self._hook(len(self.calls), node_id)
        hunk = f"+TOKEN = '{_TOKEN}'" if node_id == self._secret_on else f"@@ hunk {node_id}"
        return {"node": {"diffHunk": hunk}}


def _corpus(tmp_path: Path, count: int) -> Path:
    return write_corpus(tmp_path / "c.jsonl", [corpus_row(f"R{i:02d}") for i in range(count)])


def _argv(corpus: Path, out: Path) -> list[str]:
    return ["fetch-hunks", "--corpus", str(corpus), "--output", str(out)]


def _resolved(path: Path) -> int:
    return sum(1 for r in read_rows(path) if r["hunk_status"] is not None)


class TestCrashKeepsProgress:
    def test_an_unexpected_exception_leaves_the_fetched_rows_on_disk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An error the loop does not map to exit 3 still saves what was fetched."""

        def hook(call: int, _node: str) -> None:
            if call == 3:
                raise ZeroDivisionError("bug")

        monkeypatch.setattr(cc, "gh_graphql", _Scripted(hook))
        out = tmp_path / "o.jsonl"

        with pytest.raises(ZeroDivisionError):
            cc.main(_argv(_corpus(tmp_path, 5), out))

        rows = read_rows(out)
        assert [r["id"] for r in rows] == [f"R{i:02d}" for i in range(5)]
        assert [r["hunk_status"] for r in rows] == ["fetched", "fetched", None, None, None]
        assert rows[0]["diff_hunk"] == "@@ hunk R00"

    def test_a_keyboard_interrupt_saves_progress_and_is_re_raised(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ctrl-C must not cost the hunks already fetched, and must still stop the program."""

        def hook(call: int, _node: str) -> None:
            if call == 2:
                raise KeyboardInterrupt

        monkeypatch.setattr(cc, "gh_graphql", _Scripted(hook))
        out = tmp_path / "o.jsonl"

        with pytest.raises(KeyboardInterrupt):
            cc.main(_argv(_corpus(tmp_path, 4), out))

        assert [r["hunk_status"] for r in read_rows(out)] == ["fetched", None, None, None]

    def test_a_rerun_on_the_saved_output_fetches_only_what_is_left(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The point of saving: the next run resumes."""

        def crash_on_four(call: int, _node: str) -> None:
            if call == 4:
                raise ZeroDivisionError

        monkeypatch.setattr(cc, "gh_graphql", _Scripted(crash_on_four))
        saved = tmp_path / "saved.jsonl"
        with pytest.raises(ZeroDivisionError):
            cc.main(_argv(_corpus(tmp_path, 6), saved))
        resumed = _Scripted(lambda _c, _n: None)
        monkeypatch.setattr(cc, "gh_graphql", resumed)
        final = tmp_path / "final.jsonl"

        assert cc.main(_argv(saved, final)) == 0

        assert [v["id"] for _, v in resumed.calls] == ["R03", "R04", "R05"]
        assert _resolved(final) == 6

    def test_no_temp_files_are_left_behind(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Atomic writes clean up after themselves, including on the crash path."""

        def hook(call: int, _node: str) -> None:
            if call == 2:
                raise ZeroDivisionError

        monkeypatch.setattr(cc, "gh_graphql", _Scripted(hook))
        corpus = _corpus(tmp_path, 3)

        with pytest.raises(ZeroDivisionError):
            cc.main(_argv(corpus, tmp_path / "o.jsonl"))

        assert sorted(p.name for p in tmp_path.iterdir()) == ["c.jsonl", "o.jsonl"]


class TestPeriodicCheckpoint:
    def test_the_output_is_written_every_25_resolved_rows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Group 6: after 25 and after 50 rows, before the run ends."""
        out = tmp_path / "o.jsonl"
        seen: dict[int, int | None] = {}

        def hook(call: int, _node: str) -> None:
            seen[call] = _resolved(out) if out.exists() else None

        monkeypatch.setattr(cc, "gh_graphql", _Scripted(hook))

        assert cc.main(_argv(_corpus(tmp_path, 60), out)) == 0

        assert seen[25] is None
        assert seen[26] == 25
        assert seen[50] == 25
        assert seen[51] == 50
        assert seen[60] == 50
        assert _resolved(out) == 60

    def test_a_run_shorter_than_25_rows_writes_once_at_the_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No checkpoint noise for a small corpus."""
        out = tmp_path / "o.jsonl"
        existed: list[bool] = []
        monkeypatch.setattr(
            cc, "gh_graphql", _Scripted(lambda _c, _n: existed.append(out.exists()))
        )

        assert cc.main(_argv(_corpus(tmp_path, 10), out)) == 0

        assert existed == [False] * 10
        assert _resolved(out) == 10

    def test_checkpoints_use_the_atomic_writer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A checkpoint that fails to swap in leaves the previous file whole."""
        out = tmp_path / "o.jsonl"
        out.write_text("PREVIOUS\n", encoding="utf-8")
        monkeypatch.setattr(cc, "gh_graphql", _Scripted(lambda _c, _n: None))

        def boom(*_a: object, **_k: object) -> None:
            raise OSError("replace failed")

        monkeypatch.setattr(os, "replace", boom)

        with pytest.raises(OSError, match="replace failed"):
            cc.main(_argv(_corpus(tmp_path, 30), out))

        assert out.read_text(encoding="utf-8") == "PREVIOUS\n"


class TestSecretsNeverReachACheckpoint:
    def test_a_secret_hunk_blocks_every_checkpoint_and_the_final_write(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Scan first: no checkpoint writes rows that fail the scan."""
        out = tmp_path / "o.jsonl"
        existed: list[bool] = []
        fake = _Scripted(lambda _c, _n: existed.append(out.exists()), secret_on="R01")
        monkeypatch.setattr(cc, "gh_graphql", fake)

        code = cc.main(_argv(_corpus(tmp_path, 60), out))

        assert code == 1
        assert not any(existed)
        assert not out.exists()
        assert "row R01" in capsys.readouterr().err

    def test_a_crash_after_a_secret_row_writes_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The crash path scans too, and the original exception still surfaces."""

        def hook(call: int, _node: str) -> None:
            if call == 3:
                raise ZeroDivisionError

        monkeypatch.setattr(cc, "gh_graphql", _Scripted(hook, secret_on="R00"))
        out = tmp_path / "o.jsonl"

        with pytest.raises(ZeroDivisionError):
            cc.main(_argv(_corpus(tmp_path, 5), out))

        assert not out.exists()

    def test_a_failed_crash_save_does_not_mask_the_original_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the disk is the problem, the caller still sees the first exception."""

        def hook(call: int, _node: str) -> None:
            if call == 2:
                raise ZeroDivisionError("first")

        monkeypatch.setattr(cc, "gh_graphql", _Scripted(hook))

        def boom(*_a: object, **_k: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", boom)

        with pytest.raises(ZeroDivisionError, match="first"):
            cc.main(_argv(_corpus(tmp_path, 3), tmp_path / "o.jsonl"))
