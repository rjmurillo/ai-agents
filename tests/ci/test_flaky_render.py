"""Tests for scripts/ci/_flaky_render.py: the step summary block."""

from __future__ import annotations

from scripts.ci import _flaky_render as fr
from scripts.ci._flaky_classify import Outcome, classify
from scripts.ci._flaky_inputs import JunitCounts
from tests.ci.flaky_test_helpers import make_state


def _outcome() -> Outcome:
    return classify(JunitCounts(10, 2), "failure", make_state(), JunitCounts(2, 1))


def test_summary_escapes_pipes_and_shows_note():
    text = fr.render_summary("split-1", _outcome(), "stale cache")
    assert "| `tests/test_a.py::test_broken[a\\|b]` | failed | failed | consistent |" in text
    assert "> stale cache" in text
    assert "a rerun never turns a leg green" in text


def test_summary_without_rows_has_no_table():
    text = fr.render_summary("split-1", Outcome(1, "headline"), "")
    assert "| Test |" not in text
    assert "[!NOTE]" not in text


def test_cache_note_only_when_cache_exceeds_junit():
    assert fr.cache_note(JunitCounts(5, 1), ["a", "b"]) != ""
    assert fr.cache_note(JunitCounts(5, 2), ["a", "b"]) == ""


def test_emit_summary_appends_to_file(tmp_path, monkeypatch):
    summary = tmp_path / "s.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert fr.emit_summary("one\n") is True
    assert fr.emit_summary("two\n") is True
    assert summary.read_text(encoding="utf-8") == "one\ntwo\n"


def test_emit_summary_unwritable_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "missing-dir" / "s.md"))
    assert fr.emit_summary("x") is False
    assert "could not write the step summary" in capsys.readouterr().err


def test_emit_summary_without_env_prints(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert fr.emit_summary("hello\n") is True
    assert capsys.readouterr().out == "hello\n"
