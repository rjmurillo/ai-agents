"""Tests for the Serena worktree scope guard (issue #4917).

Validates that:
- Write tools are blocked when worktree != Serena project root
- Read tools are always allowed
- Matching worktrees pass through
- Missing git or .serena/ fails open
- SERENA_PROJECT_ROOT env var overrides discovery
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the guard module
_GUARD_PATH = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(_GUARD_PATH))

import invoke_serena_worktree_scope_guard as guard


@pytest.fixture()
def fake_git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with .serena/project.yml."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    serena_dir = tmp_path / ".serena"
    serena_dir.mkdir()
    (serena_dir / "project.yml").write_text('project_name: "test"\n')
    return tmp_path


@pytest.fixture()
def external_worktree(fake_git_repo: Path, tmp_path: Path) -> Path:
    """Create an external worktree from the fake repo."""
    wt_path = tmp_path / "external-wt"
    subprocess.run(
        ["git", "-C", str(fake_git_repo), "commit", "--allow-empty", "-m", "init"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(fake_git_repo), "worktree", "add", str(wt_path), "-b", "test-branch"],
        capture_output=True,
        check=True,
    )
    return wt_path


class TestScopeMatch:
    """Write tools allowed when worktree matches Serena project."""

    def test_write_tool_same_worktree(self, fake_git_repo: Path) -> None:
        """Write tool passes when CWD worktree == Serena project root."""
        with patch.object(guard, "_git_toplevel", return_value=fake_git_repo):
            with patch.object(guard, "_serena_project_root", return_value=fake_git_repo):
                with patch.object(
                    guard,
                    "_read_payload",
                    return_value=("serena-replace_content", fake_git_repo),
                ):
                    assert guard.main() == 0

    def test_read_tool_always_allowed(self, fake_git_repo: Path) -> None:
        """Read tools pass regardless of scope."""
        with patch.object(
            guard,
            "_read_payload",
            return_value=("serena-find_symbol", fake_git_repo),
        ):
            assert guard.main() == 0


class TestScopeMismatch:
    """Write tools blocked when worktree differs from Serena project."""

    def test_write_tool_different_worktree(
        self, fake_git_repo: Path, external_worktree: Path
    ) -> None:
        """Write tool blocked when CWD worktree != Serena project root."""
        with patch.object(guard, "_git_toplevel", return_value=external_worktree):
            with patch.object(guard, "_serena_project_root", return_value=fake_git_repo):
                with patch.object(
                    guard,
                    "_read_payload",
                    return_value=("serena-replace_content", external_worktree),
                ):
                    assert guard.main() == 2

    @pytest.mark.parametrize(
        "tool",
        [
            "serena-replace_content",
            "serena-replace_symbol_body",
            "serena-insert_before_symbol",
            "serena-insert_after_symbol",
            "serena-replace_in_files",
            "serena-safe_delete_symbol",
            "serena-rename_symbol",
        ],
    )
    def test_all_write_tools_blocked(
        self, fake_git_repo: Path, external_worktree: Path, tool: str
    ) -> None:
        """Every write tool is blocked on scope mismatch."""
        with patch.object(guard, "_git_toplevel", return_value=external_worktree):
            with patch.object(guard, "_serena_project_root", return_value=fake_git_repo):
                with patch.object(
                    guard,
                    "_read_payload",
                    return_value=(tool, external_worktree),
                ):
                    assert guard.main() == 2


class TestFailOpen:
    """Guard fails open when it cannot determine scope."""

    def test_no_git_repo(self, tmp_path: Path) -> None:
        """Fails open when git toplevel cannot be determined."""
        with patch.object(guard, "_git_toplevel", return_value=None):
            with patch.object(
                guard,
                "_read_payload",
                return_value=("serena-replace_content", tmp_path),
            ):
                assert guard.main() == 0

    def test_no_serena_config(self, tmp_path: Path) -> None:
        """Fails open when no .serena/project.yml found."""
        with patch.object(guard, "_git_toplevel", return_value=tmp_path):
            with patch.object(guard, "_serena_project_root", return_value=None):
                with patch.object(
                    guard,
                    "_read_payload",
                    return_value=("serena-replace_content", tmp_path),
                ):
                    assert guard.main() == 0


class TestEnvOverride:
    """SERENA_PROJECT_ROOT env var overrides discovery."""

    def test_env_override_matches_worktree(
        self, fake_git_repo: Path, external_worktree: Path
    ) -> None:
        """Setting SERENA_PROJECT_ROOT to worktree path allows writes."""
        # Create .serena/project.yml in the external worktree
        serena_dir = external_worktree / ".serena"
        serena_dir.mkdir(exist_ok=True)
        (serena_dir / "project.yml").write_text('project_name: "test"\n')

        with patch.dict(os.environ, {"SERENA_PROJECT_ROOT": str(external_worktree)}):
            with patch.object(guard, "_git_toplevel", return_value=external_worktree):
                with patch.object(
                    guard,
                    "_read_payload",
                    return_value=("serena-replace_content", external_worktree),
                ):
                    assert guard.main() == 0

    def test_env_override_without_marker_ignored(
        self, fake_git_repo: Path, tmp_path: Path
    ) -> None:
        """SERENA_PROJECT_ROOT ignored if no .serena/project.yml there."""
        no_serena = tmp_path / "no-serena"
        no_serena.mkdir()
        with patch.dict(os.environ, {"SERENA_PROJECT_ROOT": str(no_serena)}):
            # Falls through to walk-up discovery
            result = guard._serena_project_root()
            # Should not return the invalid path
            assert result != no_serena


class TestPayloadParsing:
    """Verify stdin JSON parsing."""

    def test_valid_payload(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Parses tool_name and cwd from stdin."""
        payload = json.dumps({
            "tool_name": "serena-replace_content",
            "tool_input": {
                "relative_path": "foo.py", "needle": "x",
                "repl": "y", "mode": "literal",
            },
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
        tool_name, cwd = guard._read_payload()
        assert tool_name == "serena-replace_content"
        assert cwd == tmp_path.resolve()

    def test_empty_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty stdin returns empty tool_name (fail open)."""
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(""))
        tool_name, _ = guard._read_payload()
        assert tool_name == ""


class TestIntegrationWorktreeIsolation:
    """End-to-end test proving the guard blocks writes in wrong worktree."""

    def test_guard_blocks_write_in_external_worktree(
        self, fake_git_repo: Path, external_worktree: Path
    ) -> None:
        """Invoke the guard as a subprocess with real worktree paths.

        Proves that a relative edit targeting the external worktree is
        blocked when Serena project root points to the primary checkout.
        """
        # Create .serena/project.yml only in primary repo (not worktree)
        # (already created by fake_git_repo fixture)
        assert (fake_git_repo / ".serena" / "project.yml").is_file()
        assert not (external_worktree / ".serena" / "project.yml").is_file()

        # Create a file in both trees to track mutation
        (fake_git_repo / "target.py").write_text("original")
        (external_worktree / "target.py").write_text("original")

        # Simulate the guard invocation from the external worktree
        payload = json.dumps({
            "tool_name": "serena-replace_content",
            "tool_input": {
                "relative_path": "target.py",
                "needle": "original",
                "repl": "modified",
                "mode": "literal",
            },
            "cwd": str(external_worktree),
        })

        result = subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).resolve().parents[2]
                    / ".claude"
                    / "hooks"
                    / "PreToolUse"
                    / "invoke_serena_worktree_scope_guard.py"
                ),
            ],
            input=payload,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(external_worktree),
            env={
                **os.environ,
                "CLAUDE_PROJECT_DIR": str(fake_git_repo),
            },
        )

        # Guard should block (exit 2) because worktree != Serena root
        assert result.returncode == 2, (
            f"Expected block (exit 2), got {result.returncode}. "
            f"stderr: {result.stderr}"
        )

        # Verify neither file was mutated (guard blocked before edit)
        assert (fake_git_repo / "target.py").read_text() == "original"
        assert (external_worktree / "target.py").read_text() == "original"

    def test_guard_allows_write_in_matching_worktree(
        self, fake_git_repo: Path
    ) -> None:
        """Guard allows write when CWD worktree matches Serena root."""
        payload = json.dumps({
            "tool_name": "serena-replace_content",
            "tool_input": {
                "relative_path": "target.py",
                "needle": "x",
                "repl": "y",
                "mode": "literal",
            },
            "cwd": str(fake_git_repo),
        })

        result = subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).resolve().parents[2]
                    / ".claude"
                    / "hooks"
                    / "PreToolUse"
                    / "invoke_serena_worktree_scope_guard.py"
                ),
            ],
            input=payload,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(fake_git_repo),
            env={
                **os.environ,
                "CLAUDE_PROJECT_DIR": str(fake_git_repo),
            },
        )

        # Guard should allow (exit 0)
        assert result.returncode == 0
