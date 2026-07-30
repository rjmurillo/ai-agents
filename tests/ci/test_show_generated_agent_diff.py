"""Tests for ``scripts/ci/show_generated_agent_diff.py``.

The script runs after the generated-agent validation fails, so its only job is
to explain the failure accurately. The tests below cover the two outcomes that
matter: files differ, and nothing differs (which means the validation failed
for a reason this script cannot see).
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.ci import show_generated_agent_diff as sgad


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


class TestChangedFiles:
    def test_it_returns_one_entry_per_line(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sgad, "_run", lambda *_a, **_k: _completed("a.md\nb.md\n"))
        assert sgad.changed_files(Path(".")) == ["a.md", "b.md"]

    def test_it_drops_blank_lines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sgad, "_run", lambda *_a, **_k: _completed("a.md\n\n  \nb.md\n"))
        assert sgad.changed_files(Path(".")) == ["a.md", "b.md"]

    def test_no_output_means_no_files(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sgad, "_run", lambda *_a, **_k: _completed(""))
        assert sgad.changed_files(Path(".")) == []


class TestMain:
    def test_it_regenerates_before_diffing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The diff is meaningless unless the generator has run first."""
        seen: list[list[str]] = []

        def _run(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            seen.append(list(argv))
            return _completed()

        monkeypatch.setattr(sgad, "_run", _run)
        assert sgad.main([]) == 0
        assert seen[0] == list(sgad._GENERATOR)
        assert seen[1] == ["git", "diff", "--name-only"]

    def test_it_names_every_changed_file_and_the_remedy(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def _run(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            if list(argv)[:3] == ["git", "diff", "--name-only"]:
                return _completed(".github/agents/a.md\n.claude/agents/b.md\n")
            if list(argv) == ["git", "diff"]:
                return _completed("--- a/x\n+++ b/x\n")
            return _completed()

        monkeypatch.setattr(sgad, "_run", _run)
        assert sgad.main([]) == 0
        out = capsys.readouterr().out
        assert "  - .github/agents/a.md" in out
        assert "  - .claude/agents/b.md" in out
        assert "uv run python build/generate_agents.py" in out
        assert "=== Detailed diff ===" in out
        assert "+++ b/x" in out

    def test_no_differences_says_so_instead_of_claiming_edits(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sgad, "_run", lambda *_a, **_k: _completed(""))
        assert sgad.main([]) == 0
        out = capsys.readouterr().out
        assert "No differences detected" in out
        assert "were manually edited" not in out
        assert "=== Detailed diff ===" not in out

    def test_it_always_succeeds_so_it_cannot_mask_the_real_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """This step runs under ``if: failure()``; its own exit code is noise."""
        monkeypatch.setattr(sgad, "_run", lambda *_a, **_k: _completed("x\n", returncode=1))
        assert sgad.main([]) == 0

    def test_repo_root_is_forwarded_to_git(self, monkeypatch: pytest.MonkeyPatch) -> None:
        roots: list[Path] = []

        def _run(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
            roots.append(cwd)
            return _completed()

        monkeypatch.setattr(sgad, "_run", _run)
        assert sgad.main(["--repo-root", "/tmp/elsewhere"]) == 0
        assert roots and all(str(root) == "/tmp/elsewhere" for root in roots)


class TestWiring:
    def test_the_workflow_invokes_this_script(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[2] / ".github/workflows/validate-generated-agents.yml"
        ).read_text(encoding="utf-8")
        assert "scripts/ci/show_generated_agent_diff.py" in workflow

    def test_the_workflow_no_longer_carries_the_shell_it_replaced(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[2] / ".github/workflows/validate-generated-agents.yml"
        ).read_text(encoding="utf-8")
        assert "CHANGED_FILES=$(git diff --name-only)" not in workflow
        assert 'echo "should-run-agents=false"' not in workflow
