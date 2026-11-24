"""Tests for atomic output writes in the actionability eval tools.

Hygiene 6c. Wiring tests drive each consumer's real entry point with os.replace
failing, so a consumer that stops using the atomic helper fails its own test.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.eval._actionability_arms_test_support import (
    aa,
    make_prediction,
    make_row,
    write_jsonl_file,
)
from tests.eval._actionability_corpus_test_support import cc

_BAND_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "eval" / "measure_actionability_band.py"
)


def _fail_replace(*_args: object, **_kwargs: object) -> None:
    raise OSError("replace failed")


def _leftovers(directory: Path, keep: set[str]) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if p.name not in keep)


class TestAtomicWriteText:
    def test_writes_text_and_creates_parent_directories(self, tmp_path: Path) -> None:
        """Hygiene 6c: the helper creates missing parents and writes the text."""
        from scripts.eval.actionability_io import atomic_write_text

        target = tmp_path / "a" / "b" / "out.txt"

        atomic_write_text(target, "hello\n")

        assert target.read_text(encoding="utf-8") == "hello\n"
        assert _leftovers(target.parent, {"out.txt"}) == []

    def test_failed_replace_keeps_the_old_file_and_removes_the_temp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hygiene 6c: a crash before the swap leaves the previous output whole."""
        from scripts.eval.actionability_io import atomic_write_text

        target = tmp_path / "out.txt"
        target.write_text("old\n", encoding="utf-8")
        monkeypatch.setattr(os, "replace", _fail_replace)

        with pytest.raises(OSError, match="replace failed"):
            atomic_write_text(target, "new\n")

        assert target.read_text(encoding="utf-8") == "old\n"
        assert _leftovers(tmp_path, {"out.txt"}) == []


class TestConsumersWriteAtomically:
    def test_write_jsonl_is_atomic(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Hygiene 6c: corpus, hunks, sheet, merge outputs all go through write_jsonl."""
        target = tmp_path / "corpus.jsonl"
        target.write_text('{"old": true}\n', encoding="utf-8")
        monkeypatch.setattr(os, "replace", _fail_replace)

        with pytest.raises(OSError, match="replace failed"):
            cc.write_jsonl(target, [{"new": True}])

        assert target.read_text(encoding="utf-8") == '{"old": true}\n'

    def test_score_report_is_atomic(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Hygiene 6c: the score report write goes through the helper."""
        rows: list[dict[str, Any]] = [make_row(f"H{i}", label="actionable") for i in range(3)]
        corpus = write_jsonl_file(tmp_path / "c.jsonl", rows)
        preds = write_jsonl_file(tmp_path / "p.jsonl", [make_prediction("H0")])
        out = tmp_path / "report.json"
        out.write_text("{}\n", encoding="utf-8")
        monkeypatch.setattr(os, "replace", _fail_replace)
        argv = ["score", "--corpus", str(corpus), "--predictions", str(preds)]

        with pytest.raises(OSError, match="replace failed"):
            aa.main([*argv, "--output", str(out), "--bootstrap", "10"])

        assert out.read_text(encoding="utf-8") == "{}\n"

    def test_band_script_writes_result_and_saved_prs_atomically(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hygiene 6c: measure_actionability_band output and --save-prs use the helper."""
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location("mab_io_probe", _BAND_SCRIPT)
        assert spec is not None and spec.loader is not None
        mab = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mab
        spec.loader.exec_module(mab)
        written: list[Path] = []

        def _spy(path: Path, text: str) -> None:
            written.append(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        monkeypatch.setattr(mab, "atomic_write_text", _spy)
        source = tmp_path / "prs.json"
        source.write_text(json.dumps([]), encoding="utf-8")
        saved, out = tmp_path / "saved.json", tmp_path / "result.json"

        code = mab.main(
            ["--from-json", str(source), "--save-prs", str(saved), "--output", str(out)]
        )

        assert code == 0
        assert written == [saved, out]
