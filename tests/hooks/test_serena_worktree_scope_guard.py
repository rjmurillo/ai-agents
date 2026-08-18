"""Tests for the Serena worktree scope guard (issue #4917).

Validates that:
- Write tools are blocked when worktree != Serena project root
- Read tools are always allowed
- Matching worktrees pass through
- Missing CLAUDE_PROJECT_DIR fails closed for writes (blocks)
- Missing git toplevel on CWD fails open (not in a git repo)
- SERENA_PROJECT_ROOT env var overrides discovery
- Both harnesses' real tool-name prefixes ("mcp__serena__*" for Claude Code,
  "serena-*" for Copilot CLI) normalize to the same bare-name check (#5036:
  the original guard tested only "serena-*" tool names against itself, which
  never proved either harness's real matcher or tool-name convention would
  ever reach this script -- see TestMatcherRegressionGuard and
  TestGeneratedShimIntegration below for the tests that would have caught it)
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the guard module
_GUARD_PATH = REPO_ROOT / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(_GUARD_PATH))

import invoke_serena_worktree_scope_guard as guard

# The two real harness prefixes a write tool name arrives with. Anything
# fixture or test below that needs "a write tool name" is parametrized over
# both so neither harness silently loses coverage the way the "serena-*"
# only pre-#5036 suite did.
_HARNESS_PREFIXES = ("mcp__serena__", "serena-")


@pytest.fixture()
def fake_git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with .serena/project.yml."""
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@test.local"],
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
        capture_output=True, check=True,
    )
    serena_dir = tmp_path / ".serena"
    serena_dir.mkdir()
    (serena_dir / "project.yml").write_text('project_name: "test"\n')
    return tmp_path


@pytest.fixture()
def external_worktree(fake_git_repo: Path, tmp_path: Path) -> Path:
    """Create an external worktree from the fake repo."""
    wt_path = tmp_path / "external-wt"
    # Fixture-local identity via `git -c`, independent of the local config
    # fake_git_repo already wrote (#5036 review: a clean CI runner with no
    # global user.name/user.email must not depend on config-write ordering
    # to make this commit succeed).
    subprocess.run(
        [
            "git", "-c", "user.email=test@test.local", "-c", "user.name=Test",
            "-C", str(fake_git_repo), "commit", "--allow-empty", "-m", "init",
        ],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(fake_git_repo), "worktree", "add", str(wt_path), "-b", "test-branch"],
        capture_output=True,
        check=True,
    )
    return wt_path


class TestNormalizeToolName:
    """_normalize_tool_name strips either harness prefix to a bare name."""

    @pytest.mark.parametrize("prefix", _HARNESS_PREFIXES)
    def test_strips_known_prefix(self, prefix: str) -> None:
        assert guard._normalize_tool_name(f"{prefix}replace_content") == "replace_content"

    @pytest.mark.parametrize(
        "tool_name",
        ["Bash", "Read", "Grep", "Task", "mcp__other_server__write", "", "serenax-foo"],
    )
    def test_non_serena_tool_returns_none(self, tool_name: str) -> None:
        """A tool carrying neither prefix is not a Serena call (#5036 defense in depth)."""
        assert guard._normalize_tool_name(tool_name) is None


class TestScopeMatch:
    """Write tools allowed when worktree matches Serena project."""

    @pytest.mark.parametrize("prefix", _HARNESS_PREFIXES)
    def test_write_tool_same_worktree(self, fake_git_repo: Path, prefix: str) -> None:
        """Write tool passes when CWD worktree == Serena project root, either harness."""
        with patch.object(guard, "_git_toplevel", return_value=fake_git_repo):
            with patch.object(guard, "_serena_project_root", return_value=fake_git_repo):
                with patch.object(
                    guard,
                    "_read_payload",
                    return_value=(f"{prefix}replace_content", fake_git_repo),
                ):
                    assert guard.main() == 0

    @pytest.mark.parametrize("prefix", _HARNESS_PREFIXES)
    def test_read_tool_always_allowed(self, fake_git_repo: Path, prefix: str) -> None:
        """Read tools pass regardless of scope, either harness."""
        with patch.object(
            guard,
            "_read_payload",
            return_value=(f"{prefix}find_symbol", fake_git_repo),
        ):
            assert guard.main() == 0


class TestMatcherContract:
    """Negative controls: tools outside the write set are never blocked."""

    def test_unrelated_tool_passes(self, fake_git_repo: Path) -> None:
        """Non-serena tool (Bash) always passes regardless of scope."""
        with patch.object(
            guard, "_read_payload", return_value=("Bash", fake_git_repo)
        ):
            assert guard.main() == 0

    def test_other_mcp_server_passes(self, fake_git_repo: Path) -> None:
        """A different MCP server's tool never matches the Serena prefix check."""
        with patch.object(
            guard,
            "_read_payload",
            return_value=("mcp__deepwiki__ask_question", fake_git_repo),
        ):
            assert guard.main() == 0

    @pytest.mark.parametrize("prefix", _HARNESS_PREFIXES)
    def test_unknown_serena_variant_passes(self, fake_git_repo: Path, prefix: str) -> None:
        """Tool name not in WRITE_TOOLS passes (e.g. future read tool)."""
        with patch.object(
            guard, "_read_payload", return_value=(f"{prefix}unknown_tool", fake_git_repo)
        ):
            assert guard.main() == 0


class TestScopeMismatch:
    """Write tools blocked when worktree differs from Serena project."""

    @pytest.mark.parametrize("prefix", _HARNESS_PREFIXES)
    def test_write_tool_different_worktree(
        self, fake_git_repo: Path, external_worktree: Path, prefix: str
    ) -> None:
        """Write tool blocked when CWD worktree != Serena project root, either harness."""
        with patch.object(guard, "_git_toplevel", return_value=external_worktree):
            with patch.object(guard, "_serena_project_root", return_value=fake_git_repo):
                with patch.object(
                    guard,
                    "_read_payload",
                    return_value=(f"{prefix}replace_content", external_worktree),
                ):
                    assert guard.main() == 2

    @pytest.mark.parametrize("bare_tool", sorted(guard._WRITE_TOOLS))
    @pytest.mark.parametrize("prefix", _HARNESS_PREFIXES)
    def test_all_write_tools_blocked(
        self, fake_git_repo: Path, external_worktree: Path, prefix: str, bare_tool: str
    ) -> None:
        """Every write tool in the current inventory is blocked on scope
        mismatch, under both harness prefixes. Sourced from
        oraios/serena's ToolMarkerCanEdit/ToolMarkerSymbolicEdit classes
        (#5036 review: write_memory and edit_memory were previously
        missing from this inventory)."""
        with patch.object(guard, "_git_toplevel", return_value=external_worktree):
            with patch.object(guard, "_serena_project_root", return_value=fake_git_repo):
                with patch.object(
                    guard,
                    "_read_payload",
                    return_value=(f"{prefix}{bare_tool}", external_worktree),
                ):
                    assert guard.main() == 2


class TestEdgeCases:
    """Guard fails open when it cannot determine scope."""

    def test_no_git_repo(self, tmp_path: Path) -> None:
        """Fails open when git toplevel cannot be determined."""
        with patch.object(guard, "_git_toplevel", return_value=None):
            with patch.object(
                guard,
                "_read_payload",
                return_value=("mcp__serena__replace_content", tmp_path),
            ):
                assert guard.main() == 0

    def test_no_serena_config(self, tmp_path: Path) -> None:
        """Fails closed when no .serena/project.yml found (write safety)."""
        with patch.object(guard, "_git_toplevel", return_value=tmp_path):
            with patch.object(guard, "_serena_project_root", return_value=None):
                with patch.object(
                    guard,
                    "_read_payload",
                    return_value=("mcp__serena__replace_content", tmp_path),
                ):
                    assert guard.main() == 2


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
                    return_value=("mcp__serena__replace_content", external_worktree),
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

    def test_env_override_warns_on_stderr(
        self, fake_git_repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Using the override prints a manual-attestation warning (#5036
        review: SERENA_PROJECT_ROOT changes this guard's belief, not
        Serena's live state, and misuse must be visible)."""
        with patch.dict(os.environ, {"SERENA_PROJECT_ROOT": str(fake_git_repo)}):
            guard._serena_project_root()
        captured = capsys.readouterr()
        assert "SERENA_PROJECT_ROOT override in effect" in captured.err
        assert "does not move" in captured.err


class TestPayloadParsing:
    """Verify stdin JSON parsing."""

    def test_valid_payload(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Parses tool_name and cwd from stdin."""
        payload = json.dumps({
            "tool_name": "mcp__serena__replace_content",
            "tool_input": {
                "relative_path": "foo.py", "needle": "x",
                "repl": "y", "mode": "literal",
            },
            "cwd": str(tmp_path),
        })
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
        tool_name, cwd = guard._read_payload()
        assert tool_name == "mcp__serena__replace_content"
        assert cwd == tmp_path.resolve()

    def test_empty_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty stdin returns empty tool_name (fail open)."""
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(""))
        tool_name, _ = guard._read_payload()
        assert tool_name == ""


class TestMatcherRegressionGuard:
    """Proves the *committed matcher configuration*, not a mocked stand-in,
    actually selects real tool names on both harnesses (#5036 root cause:
    the matcher ``^serena-`` was never anchored at the end, so a native
    Claude-format matcher compiled as ``^(?:^serena-)$`` matched only the
    literal string "serena-" and the guard silently never fired; the
    Copilot shim generator likewise classifies an unanchored pattern as a
    bare literal tool name. Both defects were invisible to the pre-#5036
    suite because every test there called ``guard.main()`` directly and
    never exercised matcher selection at all.

    These tests read the live manifest rather than duplicating its
    literals, so they fail the moment the manifest regresses without
    needing an update themselves.
    """

    @staticmethod
    def _dispatch_group() -> dict:
        manifest = json.loads(
            (REPO_ROOT / ".claude" / "hooks" / "dispatch_groups.json").read_text()
        )
        return manifest["groups"]["plugin-pretooluse-11-serena_worktree_scope"]

    def test_claude_matcher_is_fully_anchored_and_selects_real_tool_names(self) -> None:
        group = self._dispatch_group()
        pattern = group["matcher"]
        assert pattern.startswith("^") and pattern.endswith("$"), (
            f"Claude matcher {pattern!r} is not fully anchored; a native "
            "PreToolUse matcher compiles as ^(?:PATTERN)$, so an unanchored "
            "prefix silently never fires (#5036)."
        )
        compiled = re.compile(f"^(?:{pattern})$")
        assert compiled.match("mcp__serena__replace_content")
        assert compiled.match("mcp__serena__write_memory")
        assert not compiled.match("serena-replace_content")
        assert not compiled.match("Bash")

    def test_copilot_matcher_is_fully_anchored_and_selects_real_tool_names(self) -> None:
        group = self._dispatch_group()
        pattern = group["shims"][0]["copilotMatcher"]
        sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
        from generate_hooks_shim import classify_matcher

        kind, params = classify_matcher(pattern)
        assert kind == "regex", (
            f"Copilot matcher {pattern!r} classified as {kind!r}, not "
            "'regex'; the shim generator treats anything not starting with "
            "'^' AND ending with '$' as a bare literal tool name, which "
            "never matches a real serena-* call (#5036)."
        )

        # Reproduces the generated shim's own regex-kind evaluation verbatim
        # (build/scripts/generate_hooks_shim.py:413, inlined at runtime as
        # _shim_match_candidate): `_re.fullmatch(params["pattern"], tool_name)`.
        def _fires(tool_name: str) -> bool:
            return re.fullmatch(params["pattern"], tool_name) is not None

        assert _fires("serena-replace_content")
        assert _fires("serena-write_memory")
        assert not _fires("mcp__serena__replace_content")
        assert not _fires("Bash")


class TestGeneratedShimIntegration:
    """End-to-end test proving the guard blocks writes in wrong worktree.

    Drives the ACTUAL generated Copilot shim on disk (not the source
    script directly), which is the artifact a Copilot CLI install
    actually executes. #5036 review: prior tests mocked
    ``_serena_project_root``/``_git_toplevel``, which proves the
    unwrapped logic works but proves nothing about whether the committed
    matcher or the generated shim wrapper ever delivers a call to that
    logic in the first place.
    """

    @staticmethod
    def _generated_shim_path() -> Path:
        matches = sorted(
            glob.glob(
                str(
                    REPO_ROOT
                    / "src"
                    / "copilot-cli"
                    / "hooks"
                    / "PreToolUse"
                    / "invoke_serena_worktree_scope_guard__serena_*.py"
                )
            )
        )
        assert matches, (
            "no generated Copilot shim found; run "
            "`uv run python build/scripts/generate_hooks.py`"
        )
        return Path(matches[-1])

    def test_guard_blocks_write_in_external_worktree(
        self, fake_git_repo: Path, external_worktree: Path
    ) -> None:
        """A relative edit targeting the external worktree is blocked when
        Serena project root points to the primary checkout."""
        assert (fake_git_repo / ".serena" / "project.yml").is_file()
        assert not (external_worktree / ".serena" / "project.yml").is_file()

        (fake_git_repo / "target.py").write_text("original")
        (external_worktree / "target.py").write_text("original")

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
            [sys.executable, str(self._generated_shim_path())],
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

        assert result.returncode == 2, (
            f"Expected block (exit 2), got {result.returncode}. "
            f"stdout: {result.stdout} stderr: {result.stderr}"
        )
        assert (fake_git_repo / "target.py").read_text() == "original"
        assert (external_worktree / "target.py").read_text() == "original"

    def test_generated_shim_no_ops_for_unrelated_tool(
        self, fake_git_repo: Path, external_worktree: Path
    ) -> None:
        """Negative control: an unrelated tool (Bash) reaching the same
        generated shim (dispatcher fan-out with no host-side matcher) is a
        no-op, exit 0, and never reaches the write-tool check."""
        payload = json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "echo hi"},
            "cwd": str(external_worktree),
        })

        result = subprocess.run(
            [sys.executable, str(self._generated_shim_path())],
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
        assert result.returncode == 0, (
            f"Unrelated tool must no-op, got {result.returncode}. "
            f"stderr: {result.stderr}"
        )

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
            [sys.executable, str(self._generated_shim_path())],
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
        assert result.returncode == 0

    def test_guard_blocks_even_when_marker_exists_in_worktree(
        self, fake_git_repo: Path, external_worktree: Path
    ) -> None:
        """Guard blocks writes in external worktree even when
        .serena/project.yml exists there (as happens when the marker is
        tracked in git). Proves the guard uses CLAUDE_PROJECT_DIR's git
        toplevel, not .serena/project.yml discovery, as the canonical root.
        """
        serena_dir = external_worktree / ".serena"
        serena_dir.mkdir(exist_ok=True)
        (serena_dir / "project.yml").write_text('project_name: "test"\n')
        assert (fake_git_repo / ".serena" / "project.yml").is_file()
        assert (external_worktree / ".serena" / "project.yml").is_file()

        payload = json.dumps({
            "tool_name": "serena-replace_content",
            "tool_input": {"relative_path": "x.py", "needle": "a", "repl": "b", "mode": "literal"},
            "cwd": str(external_worktree),
        })

        result = subprocess.run(
            [sys.executable, str(self._generated_shim_path())],
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

        assert result.returncode == 2, (
            f"Expected block (exit 2) even with .serena in worktree, got {result.returncode}. "
            f"stderr: {result.stderr}"
        )
