"""
Tests for .agents/projects/v0.3.0/scripts/orchestrate.sh

Smoke tests validating script syntax, help output, and basic command execution.
These tests do NOT execute agents but verify the orchestration harness itself.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

# Get paths relative to repo root
REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / ".agents" / "projects" / "v0.3.0" / "scripts" / "orchestrate.sh"
PROJECT_DIR = REPO_ROOT / ".agents" / "projects" / "v0.3.0"


class TestOrchestrateShSyntax:
    """Validate bash script syntax and structure."""

    def test_script_exists(self):
        """Script file exists at expected location."""
        assert SCRIPT_PATH.exists(), f"Script not found at {SCRIPT_PATH}"

    def test_script_is_executable(self):
        """Script has executable permission."""
        assert os.access(SCRIPT_PATH, os.X_OK), "Script is not executable"

    def test_bash_syntax_valid(self):
        """Script passes bash -n syntax check."""
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_shebang_is_bash(self):
        """Script uses bash shebang."""
        with open(SCRIPT_PATH, "r") as f:
            first_line = f.readline().strip()
        assert first_line == "#!/bin/bash", f"Expected bash shebang, got: {first_line}"

    def test_strict_mode_enabled(self):
        """Script enables strict mode (set -euo pipefail)."""
        content = SCRIPT_PATH.read_text()
        assert "set -euo pipefail" in content, "Missing strict mode"


class TestOrchestrateShHelp:
    """Test help command output."""

    def test_help_command_succeeds(self):
        """Help command exits with code 0."""
        result = subprocess.run(
            [str(SCRIPT_PATH), "help"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"Help failed: {result.stderr}"

    def test_help_shows_commands(self):
        """Help output lists available commands."""
        result = subprocess.run(
            [str(SCRIPT_PATH), "help"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        expected_commands = ["start", "resume", "status", "chain", "setup", "cleanup", "interactive"]
        for cmd in expected_commands:
            assert cmd in result.stdout, f"Missing command '{cmd}' in help output"

    def test_help_shows_usage(self):
        """Help output includes usage information."""
        result = subprocess.run(
            [str(SCRIPT_PATH), "help"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert "Usage:" in result.stdout or "usage:" in result.stdout.lower()


class TestOrchestrateShStatus:
    """Test status command functionality."""

    def test_status_command_succeeds(self):
        """Status command exits successfully with valid state file."""
        result = subprocess.run(
            [str(SCRIPT_PATH), "status"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        # Status may return 0 (success) or non-zero if state is empty
        # Just verify it doesn't crash
        assert result.returncode in [0, 1], f"Unexpected exit code: {result.returncode}, stderr: {result.stderr}"

    def test_status_shows_chain_info(self):
        """Status output includes chain information."""
        result = subprocess.run(
            [str(SCRIPT_PATH), "status"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        # Should mention chains even if state is empty
        combined_output = result.stdout + result.stderr
        assert "chain" in combined_output.lower() or "Chain" in combined_output


class TestOrchestrateShChainDefinitions:
    """Validate chain configuration in script."""

    def test_all_six_chains_defined(self):
        """All 6 chains are defined in CHAINS array."""
        content = SCRIPT_PATH.read_text()
        for i in range(1, 7):
            assert f"CHAINS[{i}]=" in content, f"Chain {i} not defined"

    def test_all_chain_branches_defined(self):
        """All chain branches are defined."""
        content = SCRIPT_PATH.read_text()
        expected_branches = [
            "chain1/memory-enhancement",
            "chain2/memory-optimization",
            "chain3/traceability",
            "chain4/quality-testing",
            "chain5/skill-quality",
            "chain6/ci-docs",
        ]
        for branch in expected_branches:
            assert branch in content, f"Branch '{branch}' not defined"

    def test_chain_start_weeks_defined(self):
        """Chain start weeks are configured."""
        content = SCRIPT_PATH.read_text()
        for i in range(1, 7):
            assert f"CHAIN_START_WEEK[{i}]=" in content, f"Start week for chain {i} not defined"


class TestOrchestrateShStateFile:
    """Test state file handling."""

    def test_state_file_exists(self):
        """State file exists in expected location."""
        state_file = PROJECT_DIR / "state" / "orchestrator.json"
        assert state_file.exists(), f"State file not found at {state_file}"

    def test_state_file_is_valid_json(self):
        """State file contains valid JSON."""
        state_file = PROJECT_DIR / "state" / "orchestrator.json"
        with open(state_file, "r") as f:
            data = json.load(f)
        assert isinstance(data, dict), "State file root should be an object"

    def test_state_file_has_required_fields(self):
        """State file has required top-level fields."""
        state_file = PROJECT_DIR / "state" / "orchestrator.json"
        with open(state_file, "r") as f:
            data = json.load(f)
        required_fields = ["version", "current_week", "chains", "issues"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"


class TestOrchestrateShDirectoryStructure:
    """Validate project directory structure."""

    def test_logs_directory_exists(self):
        """Logs directory exists."""
        logs_dir = PROJECT_DIR / "logs"
        assert logs_dir.exists() and logs_dir.is_dir()

    def test_messages_directories_exist(self):
        """Message inbox/outbox directories exist."""
        inbox = PROJECT_DIR / "messages" / "inbox"
        outbox = PROJECT_DIR / "messages" / "outbox"
        assert inbox.exists() and inbox.is_dir(), "Inbox directory missing"
        assert outbox.exists() and outbox.is_dir(), "Outbox directory missing"

    def test_worktrees_directory_exists(self):
        """Worktrees directory exists."""
        worktrees = PROJECT_DIR / "worktrees"
        assert worktrees.exists() and worktrees.is_dir()


class TestOrchestrateShInputValidation:
    """Test input validation behavior."""

    def test_invalid_chain_number_rejected(self):
        """Invalid chain number (0, 7, abc) is rejected."""
        invalid_inputs = ["0", "7", "abc", "-1", ""]
        for invalid in invalid_inputs:
            if not invalid:
                continue  # Skip empty string for this test
            result = subprocess.run(
                [str(SCRIPT_PATH), "chain", invalid],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
            )
            # Should fail with non-zero exit code
            assert result.returncode != 0, f"Should reject invalid chain number: {invalid}"

    def test_valid_chain_numbers_accepted(self):
        """Valid chain numbers 1-6 pass validation."""
        content = SCRIPT_PATH.read_text()
        # Verify regex validation pattern exists
        assert '^[1-6]$' in content, "Chain validation regex not found"


class TestOrchestrateShErrorHandling:
    """Verify error handling patterns are present."""

    def test_file_locking_implemented(self):
        """State file updates use file locking."""
        content = SCRIPT_PATH.read_text()
        assert "flock" in content, "File locking (flock) not implemented"

    def test_temp_file_cleanup_on_error(self):
        """Temp files are cleaned up on error paths."""
        content = SCRIPT_PATH.read_text()
        # Should have rm commands for temp files in error paths
        assert 'rm -f "${tmp}"' in content or "rm -f" in content

    def test_subshell_exit_codes_captured(self):
        """Subshell exit codes are properly captured."""
        content = SCRIPT_PATH.read_text()
        # Should capture exit codes from subshells
        assert "subshell_exit=$?" in content or "_exit=$?" in content


class TestOrchestrateShAgentConfiguration:
    """Test agent configuration options."""

    def test_default_agent_is_claude(self):
        """Default agent command is claude."""
        content = SCRIPT_PATH.read_text()
        assert 'AGENT_CMD="${AGENT_CMD:-claude}"' in content

    def test_copilot_mode_documented_as_experimental(self):
        """Copilot mode is documented as experimental."""
        content = SCRIPT_PATH.read_text()
        assert "experimental" in content.lower() and "copilot" in content.lower()

    def test_parallel_chains_configurable(self):
        """Parallel chains count is configurable via environment variable."""
        content = SCRIPT_PATH.read_text()
        assert "PARALLEL_CHAINS" in content
