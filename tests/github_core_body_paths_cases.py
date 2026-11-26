"""Focused GitHub Core contract cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.github_core import assert_valid_body_file


class TestAssertValidBodyFile:
    def test_raises_when_file_missing(self):
        with pytest.raises(SystemExit) as exc:
            assert_valid_body_file("/nonexistent/path/file.txt")
        assert exc.value.code == 2

    def test_passes_when_file_exists(self, tmp_path: Path):
        f = tmp_path / "body.md"
        f.write_text("hello", encoding="utf-8")
        assert_valid_body_file(str(f), str(tmp_path))

    def test_raises_on_traversal(self, tmp_path: Path):
        # Create file at parent so it exists, but path has traversal
        parent = tmp_path.parent
        f = parent / "body.md"
        f.write_text("hello", encoding="utf-8")
        try:
            traversal_path = str(tmp_path / ".." / "body.md")
            with pytest.raises(SystemExit) as exc:
                assert_valid_body_file(traversal_path, str(tmp_path))
            assert exc.value.code == 2
        finally:
            f.unlink(missing_ok=True)

    def test_accepts_tmpdir_file_when_base_is_none(self, tmp_path: Path, monkeypatch):
        """File under TMPDIR accepted when allowed_base is None (mktemp staging)."""
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        body = tmp_path / "pr-reply.md"
        body.write_text("draft", encoding="utf-8")
        assert_valid_body_file(str(body), None)

    def test_accepts_system_tempfile_when_base_is_none(self, monkeypatch):
        """File under tempfile.gettempdir() accepted when allowed_base is None."""
        import tempfile

        monkeypatch.delenv("TMPDIR", raising=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("draft")
            tmp_file = f.name
        try:
            assert_valid_body_file(tmp_file, None)
        finally:
            Path(tmp_file).unlink(missing_ok=True)

    def test_rejects_file_outside_repo_and_all_tempdirs(self, external_tmp_path: Path, monkeypatch):
        """File outside both repo and every candidate temp root is rejected."""
        outside_dir = external_tmp_path / "not-a-temp-dir"
        outside_dir.mkdir()
        outside_file = outside_dir / "body.md"
        outside_file.write_text("hello", encoding="utf-8")

        unrelated_tmp = external_tmp_path / "unrelated-tmp"
        unrelated_tmp.mkdir()
        monkeypatch.setenv("TMPDIR", str(unrelated_tmp))

        from scripts.github_core import validation as _validation

        monkeypatch.setattr(
            _validation,
            "_candidate_temp_roots",
            lambda: [str(unrelated_tmp.resolve())],
        )

        with pytest.raises(SystemExit) as exc:
            assert_valid_body_file(str(outside_file), None)
        assert exc.value.code == 2


class TestCandidateGitDirRoots:
    """Tests for _candidate_git_dir_roots: git-dir scratch path discovery."""

    def test_returns_git_dir_when_in_repo(self):
        """Returns the resolved git dir when run inside a git repository."""
        from scripts.github_core.validation import _candidate_git_dir_roots

        roots = _candidate_git_dir_roots()
        assert isinstance(roots, list)
        # We are inside a git repository, so at least one root must be returned.
        assert len(roots) >= 1
        from pathlib import Path

        assert all(Path(r).is_dir() for r in roots)

    def test_returns_empty_list_when_git_fails(self, monkeypatch):
        """Returns [] when git exits non-zero (not in a repo)."""
        import subprocess

        from scripts.github_core.validation import _candidate_git_dir_roots

        def fake_run(*args, **kwargs):
            return subprocess.CompletedProcess(args, returncode=128, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert _candidate_git_dir_roots() == []

    def test_returns_empty_list_on_timeout(self, monkeypatch):
        """Returns [] when git subprocess times out."""
        import subprocess

        from scripts.github_core.validation import _candidate_git_dir_roots

        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=["git"], timeout=5)

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert _candidate_git_dir_roots() == []


class TestAssertValidBodyFileGitDir:
    """assert_valid_body_file accepts files stored under the git dir (issue #4276)."""

    def test_accepts_file_under_git_dir(self, monkeypatch):
        """Body file under the worktree git dir is accepted when allowed_base is None."""
        # Create a real temp dir that acts as the fake git dir.
        import tempfile
        from pathlib import Path

        from scripts.github_core import validation as _validation

        with tempfile.TemporaryDirectory() as fake_git_dir:
            body = Path(fake_git_dir) / "reply.md"
            body.write_text("draft reply", encoding="utf-8")

            monkeypatch.setattr(
                _validation,
                "_candidate_git_dir_roots",
                lambda: [str(Path(fake_git_dir).resolve())],
            )
            # Override repo-root check to not accept this path.
            monkeypatch.setattr(
                _validation,
                "_candidate_temp_roots",
                lambda: [],
            )

            monkeypatch.setattr(
                _validation,
                "is_safe_file_path",
                lambda path, base=None: (
                    base is not None
                    and str(Path(path).resolve()).startswith(str(Path(base).resolve()))
                ),
            )
            # This must not raise SystemExit.
            _validation.assert_valid_body_file(str(body), None)

    def test_still_rejects_file_outside_all_allowed_roots(
        self, external_tmp_path: Path, monkeypatch
    ):
        """File outside repo, temp dirs, and git dir is still rejected."""
        from scripts.github_core import validation as _validation

        outside_dir = external_tmp_path / "not-allowed"
        outside_dir.mkdir()
        outside_file = outside_dir / "body.md"
        outside_file.write_text("hello", encoding="utf-8")

        monkeypatch.setattr(_validation, "_candidate_temp_roots", lambda: [])
        monkeypatch.setattr(_validation, "_candidate_git_dir_roots", lambda: [])

        with pytest.raises(SystemExit) as exc:
            assert_valid_body_file(str(outside_file), None)
        assert exc.value.code == 2
