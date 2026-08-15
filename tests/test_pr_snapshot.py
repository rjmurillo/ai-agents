"""Tests for immutable PR snapshot module.

Covers: positive (capture, verify, changed paths), negative (auth failure,
bad SHA, shallow clone), edge cases (force-push/head movement staleness,
caller checkout unchanged).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Load module from skills path
_SCRIPT = Path(__file__).resolve().parents[1] / (
    "src/copilot-cli/skills/doc-accuracy/scripts/pr_snapshot.py"
)
_spec = importlib.util.spec_from_file_location("pr_snapshot", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules["pr_snapshot"] = _mod
_spec.loader.exec_module(_mod)

from pr_snapshot import (  # noqa: E402
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_STALE,
    ExternalError,
    PrIdentity,
    StaleError,
    VerifyError,
    _compute_changed_paths,
    _verify_object,
    check_staleness,
    main,
    resolve_pr_identity,
    verify_caller_unchanged,
)

IDENTITY = PrIdentity(
    owner="owner",
    repo="repo",
    number=42,
    head_sha="a" * 40,
    base_sha="b" * 40,
    base_branch="main",
)


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------


class TestPositive:
    """Tests for successful operations."""

    def test_identity_to_dict_roundtrip(self) -> None:
        """PrIdentity serializes and contains all fields."""
        d = IDENTITY.to_dict()
        assert d["owner"] == "owner"
        assert d["head_sha"] == "a" * 40
        assert d["number"] == 42

    @patch("pr_snapshot.subprocess.run")
    def test_resolve_pr_identity(self, mock_run: MagicMock) -> None:
        """resolve_pr_identity extracts head/base/branch from API."""
        mock_run.return_value = MagicMock(
            stdout=f"{'a' * 40} {'b' * 40} main\n",
            returncode=0,
        )
        result = resolve_pr_identity("owner", "repo", 42)
        assert result.head_sha == "a" * 40
        assert result.base_sha == "b" * 40
        assert result.base_branch == "main"

    @patch("pr_snapshot._run_git")
    def test_verify_object_commit(self, mock_git: MagicMock) -> None:
        """_verify_object passes for commit type."""
        mock_git.return_value = MagicMock(returncode=0, stdout="commit\n")
        _verify_object(Path("/tmp"), "a" * 40, "head")  # Should not raise

    @patch("pr_snapshot._run_git")
    def test_compute_changed_paths_nul_delimited(
        self, mock_git: MagicMock
    ) -> None:
        """Changed paths correctly split on NUL."""
        mock_git.return_value = MagicMock(
            stdout="file1.py\0dir/file2.md\0",
            returncode=0,
        )
        paths = _compute_changed_paths(Path("/tmp"), "b" * 40, "a" * 40)
        assert paths == ["file1.py", "dir/file2.md"]

    @patch("pr_snapshot._run_git")
    def test_compute_changed_paths_empty(self, mock_git: MagicMock) -> None:
        """Empty diff returns empty list."""
        mock_git.return_value = MagicMock(stdout="", returncode=0)
        paths = _compute_changed_paths(Path("/tmp"), "b" * 40, "a" * 40)
        assert paths == []

    @patch("pr_snapshot._run_git")
    def test_verify_caller_unchanged_clean(self, mock_git: MagicMock) -> None:
        """Clean caller repo does not raise."""
        mock_git.return_value = MagicMock(stdout="", returncode=0)
        verify_caller_unchanged(Path("/tmp/repo"))  # Should not raise


# ---------------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------------


class TestNegative:
    """Tests for error scenarios."""

    @patch("pr_snapshot.subprocess.run")
    def test_resolve_auth_failure(self, mock_run: MagicMock) -> None:
        """Auth failure raises ExternalError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "gh", stderr="could not read Username"
        )
        with pytest.raises(ExternalError, match="Failed to resolve"):
            resolve_pr_identity("owner", "repo", 42)

    @patch("pr_snapshot.subprocess.run")
    def test_resolve_invalid_sha_length(self, mock_run: MagicMock) -> None:
        """Short SHA raises VerifyError."""
        mock_run.return_value = MagicMock(
            stdout="short_sha base_sha main\n",
            returncode=0,
        )
        with pytest.raises(VerifyError, match="Invalid SHA lengths"):
            resolve_pr_identity("owner", "repo", 42)

    @patch("pr_snapshot._run_git")
    def test_verify_object_not_found(self, mock_git: MagicMock) -> None:
        """Missing object raises VerifyError."""
        mock_git.return_value = MagicMock(returncode=1, stdout="")
        with pytest.raises(VerifyError, match="Object not fetched"):
            _verify_object(Path("/tmp"), "a" * 40, "head")

    @patch("pr_snapshot._run_git")
    def test_verify_object_wrong_type(self, mock_git: MagicMock) -> None:
        """Non-commit object raises VerifyError."""
        mock_git.return_value = MagicMock(returncode=0, stdout="blob\n")
        with pytest.raises(VerifyError, match="Expected commit.*got blob"):
            _verify_object(Path("/tmp"), "a" * 40, "head")

    @patch("pr_snapshot._run_git")
    def test_verify_caller_dirty(self, mock_git: MagicMock) -> None:
        """Dirty caller checkout raises VerifyError."""
        mock_git.return_value = MagicMock(
            stdout=" M dirty_file.py\n", returncode=0
        )
        with pytest.raises(VerifyError, match="Caller checkout modified"):
            verify_caller_unchanged(Path("/tmp/repo"))

    @patch("pr_snapshot.subprocess.run")
    def test_resolve_gh_not_found(self, mock_run: MagicMock) -> None:
        """Missing gh CLI raises ExternalError."""
        mock_run.side_effect = FileNotFoundError("gh")
        with pytest.raises(ExternalError, match="gh CLI not available"):
            resolve_pr_identity("owner", "repo", 42)


# ---------------------------------------------------------------------------
# Edge case tests: force-push / head movement
# ---------------------------------------------------------------------------


class TestStaleness:
    """Tests for force-push and head movement detection."""

    @patch("pr_snapshot.resolve_pr_identity")
    def test_head_changed_raises_stale(
        self, mock_resolve: MagicMock
    ) -> None:
        """Head SHA change detected as stale."""
        mock_resolve.return_value = PrIdentity(
            owner="owner",
            repo="repo",
            number=42,
            head_sha="c" * 40,  # Changed from 'a' * 40
            base_sha="b" * 40,
            base_branch="main",
        )
        with pytest.raises(StaleError, match="changed"):
            check_staleness(IDENTITY)

    @patch("pr_snapshot.resolve_pr_identity")
    def test_base_changed_raises_stale(
        self, mock_resolve: MagicMock
    ) -> None:
        """Base SHA change detected as stale."""
        mock_resolve.return_value = PrIdentity(
            owner="owner",
            repo="repo",
            number=42,
            head_sha="a" * 40,
            base_sha="d" * 40,  # Changed from 'b' * 40
            base_branch="main",
        )
        with pytest.raises(StaleError, match="changed"):
            check_staleness(IDENTITY)

    @patch("pr_snapshot.resolve_pr_identity")
    def test_unchanged_returns_none(self, mock_resolve: MagicMock) -> None:
        """Unchanged PR returns None (not stale)."""
        mock_resolve.return_value = IDENTITY
        result = check_staleness(IDENTITY)
        assert result is None

    @patch("pr_snapshot.resolve_pr_identity")
    def test_network_failure_raises_stale(
        self, mock_resolve: MagicMock
    ) -> None:
        """Network failure during staleness check raises StaleError (fail closed)."""
        mock_resolve.side_effect = ExternalError("timeout")
        with pytest.raises(StaleError, match="Cannot verify"):
            check_staleness(IDENTITY)

    def test_cli_check_stale_no_identity_file(self) -> None:
        """CLI --check-stale without --identity-file returns config error."""
        code = main(["--owner", "o", "--repo", "r", "--pull-request", "1", "--check-stale"])
        assert code == EXIT_CONFIG

    @patch("pr_snapshot.resolve_pr_identity")
    def test_cli_check_stale_with_identity(
        self, mock_resolve: MagicMock, tmp_path: Path
    ) -> None:
        """CLI --check-stale with valid identity file returns OK when current."""
        mock_resolve.return_value = IDENTITY
        id_file = tmp_path / "identity.json"
        id_file.write_text(json.dumps(IDENTITY.to_dict()))
        code = main([
            "--owner", "owner", "--repo", "repo", "--pull-request", "42",
            "--check-stale", "--identity-file", str(id_file),
        ])
        assert code == EXIT_OK

    @patch("pr_snapshot.resolve_pr_identity")
    def test_cli_check_stale_detects_force_push(
        self, mock_resolve: MagicMock, tmp_path: Path
    ) -> None:
        """CLI --check-stale returns EXIT_STALE on force-push."""
        mock_resolve.return_value = PrIdentity(
            owner="owner",
            repo="repo",
            number=42,
            head_sha="f" * 40,  # Force-pushed
            base_sha="b" * 40,
            base_branch="main",
        )
        id_file = tmp_path / "identity.json"
        id_file.write_text(json.dumps(IDENTITY.to_dict()))
        code = main([
            "--owner", "owner", "--repo", "repo", "--pull-request", "42",
            "--check-stale", "--identity-file", str(id_file),
        ])
        assert code == EXIT_STALE
