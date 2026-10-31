"""PR_BODY_FILE for scripts/ci/spec_coverage_verdict.py (issue #6506).

On workflow_dispatch the Extract Spec References step reads the pull request
body. The verdict step grades that saved body instead of fetching a second one,
which could return a body edited in between.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci import spec_coverage_verdict as verdict_module
from scripts.ci.spec_coverage_verdict import EXIT_CONFIG, EXIT_FAIL, EXIT_OK, main, run

ALL_CHECKED = "## Acceptance criteria\n\n- [x] one\n- [X] two\n"
ONE_UNCHECKED = "## Acceptance criteria\n\n- [x] one\n- [ ] two\n- [ ] three\n"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "HAS_SPECS",
        "PR_BODY",
        "PR_BODY_FILE",
        "EVENT_NAME",
        "PR_NUMBER",
        "GITHUB_REPOSITORY",
        "GITHUB_STEP_SUMMARY",
    ):
        monkeypatch.delenv(name, raising=False)


class TestSavedBodyFile:
    """One body for both steps: the verdict reads what Extract Spec References read."""

    def _env(self, monkeypatch: pytest.MonkeyPatch, saved: Path) -> None:
        monkeypatch.setenv("HAS_SPECS", "true")
        monkeypatch.setenv("EVENT_NAME", "workflow_dispatch")
        monkeypatch.setenv("PR_BODY_FILE", str(saved))

    def test_dispatch_grades_the_saved_body_without_a_second_fetch(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        saved = tmp_path / "body.txt"
        saved.write_text(ALL_CHECKED + "\n", encoding="utf-8")
        self._env(monkeypatch, saved)
        assert run() == EXIT_OK
        assert not hasattr(verdict_module, "_OPENER")

    def test_saved_body_wins_over_a_different_live_body(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The race: the live PR now has checked boxes, the graded body had none."""
        saved = tmp_path / "body.txt"
        saved.write_text(ONE_UNCHECKED + "\n", encoding="utf-8")
        self._env(monkeypatch, saved)
        assert run() == EXIT_FAIL

    def test_exactly_one_trailing_newline_is_removed(self, tmp_path: Path) -> None:
        saved = tmp_path / "body.txt"
        saved.write_text("text\n\n\n", encoding="utf-8")
        assert verdict_module._read_body_file(str(saved)) == "text\n\n"

    def test_body_without_trailing_newline_is_unchanged(self, tmp_path: Path) -> None:
        saved = tmp_path / "body.txt"
        saved.write_text("text", encoding="utf-8")
        assert verdict_module._read_body_file(str(saved)) == "text"

    def test_empty_saved_body_with_spec_fails_instead_of_refetching(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        saved = tmp_path / "body.txt"
        saved.write_text("\n", encoding="utf-8")
        self._env(monkeypatch, saved)
        assert run() == EXIT_FAIL

    def test_env_body_still_wins_over_the_saved_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        saved = tmp_path / "body.txt"
        saved.write_text(ONE_UNCHECKED + "\n", encoding="utf-8")
        self._env(monkeypatch, saved)
        monkeypatch.setenv("PR_BODY", ALL_CHECKED)
        assert run() == EXIT_OK

    def test_unreadable_saved_body_is_a_config_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._env(monkeypatch, tmp_path / "missing.txt")
        assert run() == EXIT_CONFIG
        assert "saved pull request body failed" in capsys.readouterr().err

    def test_undecodable_saved_body_is_a_config_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        saved = tmp_path / "body.txt"
        saved.write_bytes(b"\xff\xfe\x00bad")
        self._env(monkeypatch, saved)
        assert run() == EXIT_CONFIG

    def test_main_returns_config_code_for_an_unreadable_saved_body(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        self._env(monkeypatch, tmp_path / "missing.txt")
        assert main() == EXIT_CONFIG
