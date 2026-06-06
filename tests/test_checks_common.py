"""Tests for scripts.validation.checks_common module.

Tests the shared infrastructure for pre-PR validation including subprocess
wrapper, base ref resolution, and the remote-refresh helper added for issue #2453.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from scripts.validation.checks_common import (
    MissingScriptSkip,
    _gh_base_ref,
    _refresh_remote_base,
    _resolve_branch_base_ref,
    _run_build_script_gate,
    _run_subprocess,
)


# ---------------------------------------------------------------------------
# _run_subprocess
# ---------------------------------------------------------------------------


class TestRunSubprocess:
    """Tests for subprocess wrapper."""

    def test_successful_command(self) -> None:
        exit_code, stdout, stderr = _run_subprocess(["echo", "hello"])
        assert exit_code == 0
        assert "hello" in stdout

    def test_command_not_found(self) -> None:
        exit_code, stdout, stderr = _run_subprocess(["nonexistent_command_xyz_123"])
        assert exit_code == -1
        assert "Command not found" in stderr

    def test_timeout(self) -> None:
        exit_code, stdout, stderr = _run_subprocess(["sleep", "10"], timeout=1)
        assert exit_code == -1
        assert "timed out" in stderr.lower()


# ---------------------------------------------------------------------------
# _refresh_remote_base (Issue #2453)
# ---------------------------------------------------------------------------


class TestRefreshRemoteBase:
    """Tests for _refresh_remote_base helper added for issue #2453."""

    def test_returns_none_for_non_origin_ref(self, tmp_path: Path) -> None:
        """Should skip fetch for non-origin/<branch> refs."""
        assert _refresh_remote_base("@{u}", tmp_path) is None
        assert _refresh_remote_base("refs/remotes/origin/HEAD", tmp_path) is None
        assert _refresh_remote_base("HEAD", tmp_path) is None
        assert _refresh_remote_base("main", tmp_path) is None

    def test_returns_none_for_pathological_branch_names(self, tmp_path: Path) -> None:
        """Should refuse origin/<branch> refs with path separators or empty branch."""
        assert _refresh_remote_base("origin/", tmp_path) is None
        assert _refresh_remote_base("origin/feat/sub-branch", tmp_path) is None
        assert _refresh_remote_base("origin/foo/bar/baz", tmp_path) is None

    def test_returns_none_when_ci_env_true(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        """Should skip fetch when CI=true (CI already fetched)."""
        monkeypatch.setenv("CI", "true")
        with patch("scripts.validation.checks_common._run_subprocess") as mock_run:
            result = _refresh_remote_base("origin/main", tmp_path)
            assert result is None
            mock_run.assert_not_called()

    def test_returns_none_when_ci_env_one(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        """Should skip fetch when CI=1."""
        monkeypatch.setenv("CI", "1")
        with patch("scripts.validation.checks_common._run_subprocess") as mock_run:
            result = _refresh_remote_base("origin/main", tmp_path)
            assert result is None
            mock_run.assert_not_called()

    def test_returns_none_when_github_actions_true(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        """Should skip fetch when GITHUB_ACTIONS=true."""
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        with patch("scripts.validation.checks_common._run_subprocess") as mock_run:
            result = _refresh_remote_base("origin/main", tmp_path)
            assert result is None
            mock_run.assert_not_called()

    def test_returns_none_when_github_actions_one(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        """Should skip fetch when GITHUB_ACTIONS=1."""
        monkeypatch.setenv("GITHUB_ACTIONS", "1")
        with patch("scripts.validation.checks_common._run_subprocess") as mock_run:
            result = _refresh_remote_base("origin/main", tmp_path)
            assert result is None
            mock_run.assert_not_called()

    def test_returns_empty_string_on_successful_fetch(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        """Should return empty string on successful git fetch."""
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        with patch(
            "scripts.validation.checks_common._run_subprocess", return_value=(0, "", "")
        ) as mock_run:
            result = _refresh_remote_base("origin/main", tmp_path)
            assert result == ""
            mock_run.assert_called_once_with(
                [
                    "git",
                    "-C",
                    str(tmp_path),
                    "fetch",
                    "--no-tags",
                    "--quiet",
                    "origin",
                    "main",
                ],
                timeout=15,
            )

    def test_returns_error_string_on_failed_fetch(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        """Should return error string on failed git fetch."""
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        with patch(
            "scripts.validation.checks_common._run_subprocess",
            return_value=(128, "", "fatal: remote origin not found"),
        ) as mock_run:
            result = _refresh_remote_base("origin/main", tmp_path)
            assert result == "fatal: remote origin not found"
            mock_run.assert_called_once()

    def test_returns_exit_code_message_when_stderr_empty(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        """Should return exit code message when stderr is empty."""
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        with patch(
            "scripts.validation.checks_common._run_subprocess",
            return_value=(1, "", ""),
        ) as mock_run:
            result = _refresh_remote_base("origin/main", tmp_path)
            assert result == "git fetch exit 1"


# ---------------------------------------------------------------------------
# _run_build_script_gate integration with _refresh_remote_base
# ---------------------------------------------------------------------------


class TestRunBuildScriptGate:
    """Tests for _run_build_script_gate with remote refresh."""

    def test_fetches_origin_branch_before_validation(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any  # noqa: ANN401
    ) -> None:
        """Should call _refresh_remote_base before invoking the validator."""
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

        script = tmp_path / "build" / "scripts" / "test_validator.py"
        script.parent.mkdir(parents=True)
        script.write_text(
            "#!/usr/bin/env python3\nimport sys\nsys.exit(0)", encoding="utf-8"
        )
        script.chmod(0o755)

        with patch(
            "scripts.validation.checks_common._resolve_branch_base_ref",
            return_value="origin/main",
        ), patch(
            "scripts.validation.checks_common._refresh_remote_base",
            return_value="",
        ) as mock_refresh, patch(
            "scripts.validation.checks_common._run_subprocess",
            return_value=(0, "", ""),
        ):
            result = _run_build_script_gate(tmp_path, "test_validator.py", "test-gate")
            assert result is True
            mock_refresh.assert_called_once_with("origin/main", tmp_path)

    def test_warns_on_fetch_failure_and_proceeds(
        self, tmp_path: Path, monkeypatch: Any, capsys: Any  # noqa: ANN401
    ) -> None:
        """Should emit warning on fetch failure but proceed with validation."""
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

        script = tmp_path / "build" / "scripts" / "test_validator.py"
        script.parent.mkdir(parents=True)
        script.write_text(
            "#!/usr/bin/env python3\nimport sys\nsys.exit(0)", encoding="utf-8"
        )

        with patch(
            "scripts.validation.checks_common._resolve_branch_base_ref",
            return_value="origin/main",
        ), patch(
            "scripts.validation.checks_common._refresh_remote_base",
            return_value="timeout after 15s",
        ), patch(
            "scripts.validation.checks_common._run_subprocess",
            return_value=(0, "", ""),
        ):
            result = _run_build_script_gate(tmp_path, "test_validator.py", "test-gate")
            assert result is True
            captured = capsys.readouterr()
            assert "[WARN]" in captured.err
            assert "could not refresh origin/main" in captured.err
            assert "timeout after 15s" in captured.err

    def test_does_not_fetch_for_non_origin_ref(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        """Should not fetch when base_ref is not origin/<branch>."""
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

        script = tmp_path / "build" / "scripts" / "test_validator.py"
        script.parent.mkdir(parents=True)
        script.write_text(
            "#!/usr/bin/env python3\nimport sys\nsys.exit(0)", encoding="utf-8"
        )

        with patch(
            "scripts.validation.checks_common._resolve_branch_base_ref",
            return_value="@{u}",
        ), patch(
            "scripts.validation.checks_common._refresh_remote_base",
            return_value=None,
        ) as mock_refresh, patch(
            "scripts.validation.checks_common._run_subprocess",
            return_value=(0, "", ""),
        ):
            result = _run_build_script_gate(tmp_path, "test_validator.py", "test-gate")
            assert result is True
            # Should have been called but returned None (skipped)
            mock_refresh.assert_called_once_with("@{u}", tmp_path)


# ---------------------------------------------------------------------------
# Integration test: stale origin/main false-PASS regression (Issue #2453)
# ---------------------------------------------------------------------------


class TestStaleOriginMainRegression:
    """End-to-end regression test for issue #2453."""

    def test_stale_origin_main_no_longer_false_passes(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        """Issue #2453: stale local origin/main refreshed before validator.

        Without the fix, a validator comparing against a stale local origin/main
        would false-PASS a bump that is actually insufficient. With the fix,
        the wrapper fetches origin/main before invoking the validator, so the
        validator sees the true remote head.
        """
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

        # 1. Set up a "remote" repo with "main" as the default branch
        remote_repo = tmp_path / "remote"
        remote_repo.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main"], cwd=remote_repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=remote_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=remote_repo,
            check=True,
            capture_output=True,
        )

        # Create initial plugin.json at 0.5.113 in remote
        plugin_dir = remote_repo / ".claude-plugin"
        plugin_dir.mkdir()
        plugin_file = plugin_dir / "plugin.json"
        plugin_file.write_text(json.dumps({"version": "0.5.113"}), encoding="utf-8")
        subprocess.run(
            ["git", "add", "."],
            cwd=remote_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "init: plugin at 0.5.113"],
            cwd=remote_repo,
            check=True,
            capture_output=True,
        )

        # 2. Clone to local
        local_repo = tmp_path / "local"
        subprocess.run(
            ["git", "clone", str(remote_repo), str(local_repo)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=local_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=local_repo,
            check=True,
            capture_output=True,
        )

        # 3. Advance remote to 0.5.128 (without local fetching)
        plugin_file_remote = remote_repo / ".claude-plugin" / "plugin.json"
        plugin_file_remote.write_text(
            json.dumps({"version": "0.5.128"}), encoding="utf-8"
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=remote_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "chore: bump to 0.5.128"],
            cwd=remote_repo,
            check=True,
            capture_output=True,
        )

        # 4. In local (which still sees 0.5.113), create a branch with 0.5.114
        subprocess.run(
            ["git", "checkout", "-b", "feat/test"],
            cwd=local_repo,
            check=True,
            capture_output=True,
        )
        plugin_file_local = local_repo / ".claude-plugin" / "plugin.json"
        plugin_file_local.write_text(
            json.dumps({"version": "0.5.114"}), encoding="utf-8"
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=local_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "feat: bump to 0.5.114"],
            cwd=local_repo,
            check=True,
            capture_output=True,
        )

        # 5. Create a mock validator script
        build_scripts = local_repo / "build" / "scripts"
        build_scripts.mkdir(parents=True)
        validator = build_scripts / "validate_plugin_version_bump.py"
        validator.write_text(
            """\
#!/usr/bin/env python3
import json
import subprocess
import sys

# Read base ref from --base argument
base_ref = sys.argv[sys.argv.index("--base") + 1]

# Get plugin.json version at base
result = subprocess.run(
    ["git", "show", f"{base_ref}:.claude-plugin/plugin.json"],
    capture_output=True,
    text=True,
)
base_version = json.loads(result.stdout)["version"]

# Get current plugin.json version
with open(".claude-plugin/plugin.json") as f:
    current_version = json.load(f)["version"]

# Parse semver (simplified: just compare as tuples)
def parse_version(v):
    return tuple(map(int, v.split(".")))

base_v = parse_version(base_version)
current_v = parse_version(current_version)

if current_v <= base_v:
    print(f"FAIL: version {current_version} not greater than {base_version}")
    sys.exit(1)
else:
    print(f"OK: version {current_version} > {base_version}")
    sys.exit(0)
""",
            encoding="utf-8",
        )
        validator.chmod(0o755)

        # 6. Verify precondition: local origin/main is stale at 0.5.113
        result = subprocess.run(
            ["git", "show", "origin/main:.claude-plugin/plugin.json"],
            cwd=local_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        stale_version = json.loads(result.stdout)["version"]
        assert stale_version == "0.5.113", "Precondition: local origin/main is stale"

        # 7. Invoke _run_build_script_gate which should:
        #    - Detect base_ref is origin/main
        #    - Fetch origin/main (refreshing to 0.5.128)
        #    - Run validator which compares 0.5.114 vs 0.5.128
        #
        # Mock _resolve_branch_base_ref to force "origin/main" so we test the
        # fetch path explicitly
        with patch(
            "scripts.validation.checks_common._resolve_branch_base_ref",
            return_value="origin/main",
        ):
            result = _run_build_script_gate(
                local_repo, "validate_plugin_version_bump.py", "plugin-version-bump"
            )

        # With the fix, the gate should FAIL (0.5.114 < 0.5.128)
        assert result is False, "Expected FAIL: 0.5.114 < 0.5.128 after fetch"

        # 8. Verify that origin/main was indeed refreshed to 0.5.128
        result = subprocess.run(
            ["git", "show", "origin/main:.claude-plugin/plugin.json"],
            cwd=local_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        refreshed_version = json.loads(result.stdout)["version"]
        assert (
            refreshed_version == "0.5.128"
        ), "origin/main should be refreshed to 0.5.128"
