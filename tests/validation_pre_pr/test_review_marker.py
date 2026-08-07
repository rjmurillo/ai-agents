"""Review marker validation tests for pre-PR checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.validation.pre_pr import validate_review_marker


class TestValidateReviewMarker:
    """Tests for the SHA-bound /review marker advisory check.

    Behavior contract:

    - Script missing, ``REVIEW_MARKER_ENFORCED`` unset / 0: returns ``True``
      (advisory skip; never blocks pre-PR).
    - Script missing, ``REVIEW_MARKER_ENFORCED=1``: returns ``False``.
    - Script present, HEAD has a binding marker: returns ``True`` regardless
      of enforcement.
    - Script present, HEAD has no marker, advisory: returns ``True``.
    - Script present, HEAD has no marker, enforced: returns ``False``.
    """

    import subprocess as _subprocess

    @staticmethod
    def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
        result = TestValidateReviewMarker._subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            input=stdin,
            check=True,
        )
        return result.stdout.strip()

    def _make_repo(self, tmp_path: Path, with_script: bool) -> Path:
        """Build a fake repo: real validator script (optionally) + git history."""
        repo = tmp_path / "repo"
        repo.mkdir()
        if with_script:
            dest = repo / "scripts" / "validation"
            dest.mkdir(parents=True)
            real = (
                Path(__file__).resolve().parents[2]
                / "scripts"
                / "validation"
                / "validate_review_marker.py"
            )
            (dest / "validate_review_marker.py").write_text(
                real.read_text(encoding="utf-8"), encoding="utf-8"
            )
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@example.com")
        self._git(repo, "config", "user.name", "Tester")
        self._git(repo, "config", "commit.gpgsign", "false")
        (repo / "a.txt").write_text("x\n", encoding="utf-8")
        self._git(repo, "add", "a.txt")
        self._git(repo, "commit", "-q", "-m", "feat: one")
        (repo / "b.txt").write_text("y\n", encoding="utf-8")
        self._git(repo, "add", "b.txt")
        self._git(repo, "commit", "-q", "-m", "feat: two")
        return repo

    def _add_marker(self, repo: Path) -> None:
        """Add an empty /review marker commit binding the current tip."""
        tip = self._git(repo, "rev-parse", "HEAD")
        self._git(
            repo,
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "review: marker",
            "--trailer",
            f"Reviewed-By: /review@analyst,security on {tip}",
        )

    def test_missing_script_advisory_returns_true(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=False)
        monkeypatch.delenv("REVIEW_MARKER_ENFORCED", raising=False)
        assert validate_review_marker(repo) is True

    def test_missing_script_enforced_returns_false(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=False)
        monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "1")
        assert validate_review_marker(repo) is False

    def test_no_marker_advisory_returns_true(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        monkeypatch.delenv("REVIEW_MARKER_ENFORCED", raising=False)
        assert validate_review_marker(repo) is True

    def test_no_marker_enforced_returns_false(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "1")
        assert validate_review_marker(repo) is False

    def test_valid_marker_passes_advisory(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        self._add_marker(repo)
        monkeypatch.delenv("REVIEW_MARKER_ENFORCED", raising=False)
        assert validate_review_marker(repo) is True

    def test_valid_marker_passes_enforced(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        self._add_marker(repo)
        monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "1")
        assert validate_review_marker(repo) is True
