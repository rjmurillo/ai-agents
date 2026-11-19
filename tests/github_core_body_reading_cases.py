"""Focused GitHub Core contract cases."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core import is_allowed_body_file_path, read_body_file_text


class TestIsAllowedBodyFilePath:
    """is_allowed_body_file_path is the one containment rule (issue #6667)."""

    def test_accepts_scratchpad_path_under_temp_root(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        scratch = tmp_path / "claude-1000" / "scratchpad"
        scratch.mkdir(parents=True)
        body = scratch / "close5369.md"
        body.write_text("body", encoding="utf-8")
        assert is_allowed_body_file_path(str(body)) is True

    def test_accepts_path_under_repo_root(self):
        assert is_allowed_body_file_path(str(Path(__file__).resolve())) is True

    def test_rejects_path_outside_every_root(self, external_tmp_path: Path, monkeypatch):
        from scripts.github_core import validation as _validation

        monkeypatch.setattr(_validation, "_candidate_temp_roots", lambda: [])
        monkeypatch.setattr(_validation, "_candidate_git_dir_roots", lambda: [])
        outside = external_tmp_path / "body.md"
        outside.write_text("x", encoding="utf-8")
        assert is_allowed_body_file_path(str(outside)) is False

    def test_symlink_in_temp_root_pointing_outside_is_rejected(
        self, tmp_path: Path, external_tmp_path: Path, monkeypatch
    ):
        from scripts.github_core import validation as _validation

        monkeypatch.setattr(_validation, "_candidate_temp_roots", lambda: [str(tmp_path.resolve())])
        monkeypatch.setattr(_validation, "_candidate_git_dir_roots", lambda: [])
        target = external_tmp_path / "secret.md"
        target.write_text("secret", encoding="utf-8")
        link = tmp_path / "link.md"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("symlinks unavailable")
        assert is_allowed_body_file_path(str(link)) is False

    def test_rejects_parent_traversal_pattern(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        (tmp_path / "sub").mkdir()
        assert is_allowed_body_file_path(str(tmp_path / "sub" / ".." / "x.md")) is False

    def test_takes_only_the_path(self):
        import inspect

        assert list(inspect.signature(is_allowed_body_file_path).parameters) == ["path"]

    def test_never_exits_for_missing_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        assert is_allowed_body_file_path(str(tmp_path / "missing.md")) is True


class TestReadBodyFileText:
    """read_body_file_text applies the shared rule, then reads safely (issue #6667)."""

    @pytest.fixture(autouse=True)
    def _pin_roots(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        from scripts.github_core import validation as _validation

        monkeypatch.setattr(_validation, "_candidate_temp_roots", lambda: [str(tmp_path.resolve())])
        monkeypatch.setattr(_validation, "_candidate_git_dir_roots", lambda: [])

    def test_reads_scratchpad_file_under_temp_root(self, tmp_path: Path):
        # A real session scratchpad is owner-only at every level below /tmp.
        scratch = tmp_path / "claude-1000" / "scratchpad"
        scratch.mkdir(mode=0o700, parents=True)
        scratch.parent.chmod(0o700)
        body = scratch / "pr7.md"
        body.write_text("## Summary\nscratch body", encoding="utf-8")

        assert read_body_file_text(str(body)) == "## Summary\nscratch body"

    def test_relative_path_resolves_against_base(self, tmp_path: Path):
        (tmp_path / "body.md").write_text("relative body", encoding="utf-8")

        assert read_body_file_text("body.md", tmp_path) == "relative body"

    def test_rejects_path_outside_every_root(self, external_tmp_path: Path):
        outside = external_tmp_path / "body.md"
        outside.write_text("x", encoding="utf-8")

        with pytest.raises(ValueError, match="must be under the repo root"):
            read_body_file_text(str(outside))

    def test_rejects_parent_traversal_pattern(self, tmp_path: Path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "body.md").write_text("x", encoding="utf-8")

        with pytest.raises(ValueError, match="parent-directory segment"):
            read_body_file_text(str(tmp_path / "sub" / ".." / "body.md"))

    def test_rejects_symlink_pointing_outside_every_root(
        self, tmp_path: Path, external_tmp_path: Path
    ):
        target = external_tmp_path / "secret.md"
        target.write_text("secret", encoding="utf-8")
        link = tmp_path / "link.md"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("symlinks unavailable")

        # The file name is not resolved, so the link itself is refused.
        with pytest.raises(ValueError, match="symlink"):
            read_body_file_text(str(link))

    def test_refuses_symlink_swapped_in_for_the_final_component(self, tmp_path: Path):
        """O_NOFOLLOW refuses a final-component symlink that appears after the check."""
        if not hasattr(os, "O_NOFOLLOW"):
            pytest.skip("O_NOFOLLOW unavailable")
        real = tmp_path / "real.md"
        real.write_text("real", encoding="utf-8")
        link = tmp_path / "link.md"
        try:
            link.symlink_to(real)
        except OSError:
            pytest.skip("symlinks unavailable")
        from scripts.github_core import validation as _validation

        # Resolve is skipped to model a link created after the resolve step.
        with patch.object(_validation.Path, "resolve", lambda self, *a, **k: self):
            with pytest.raises(ValueError, match="symlink"):
                read_body_file_text(str(link))

    def test_missing_file_raises_oserror(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_body_file_text(str(tmp_path / "missing.md"))

    def test_directory_is_not_a_regular_file(self, tmp_path: Path):
        with pytest.raises(ValueError, match="regular file"):
            read_body_file_text(str(tmp_path))

    @pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs unavailable")
    def test_fifo_is_refused_without_blocking(self, tmp_path: Path):
        fifo = tmp_path / "pipe.md"
        os.mkfifo(fifo)

        with pytest.raises(ValueError, match="regular file"):
            read_body_file_text(str(fifo))

    def test_non_utf8_file_raises_unicode_error(self, tmp_path: Path):
        body = tmp_path / "bad.md"
        body.write_bytes(b"\xff\xfe\x00bad")

        with pytest.raises(UnicodeError):
            read_body_file_text(str(body))
