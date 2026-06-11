"""Tests for scripts.validation.checks_common module.

Tests the shared infrastructure for pre-PR validation including subprocess
wrapper, base ref resolution, and the remote-refresh helper added for issue #2453.
"""

from __future__ import annotations

import json
import os
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
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            assert args[0] == [
                "git",
                "-C",
                str(tmp_path),
                "fetch",
                "--no-tags",
                "--quiet",
                "origin",
                "main",
            ]
            assert kwargs["timeout"] == 15
            clean_env = kwargs["env"]
            assert clean_env["LC_ALL"] == "C"
            assert "GIT_DIR" not in clean_env
            assert "GIT_WORK_TREE" not in clean_env
            assert "GIT_COMMON_DIR" not in clean_env
            assert "GIT_INDEX_FILE" not in clean_env

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
            encoding="utf-8",
            env={**os.environ, "LC_ALL": "C"},
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
            encoding="utf-8",
            env={**os.environ, "LC_ALL": "C"},
            check=True,
        )
        refreshed_version = json.loads(result.stdout)["version"]
        assert (
            refreshed_version == "0.5.128"
        ), "origin/main should be refreshed to 0.5.128"


# ---------------------------------------------------------------------------
# _resolve_branch_base_ref self-tracking upstream regression (Issue #2571)
# ---------------------------------------------------------------------------


def _init_git_repo(
    path: Path,
    *,
    bare: bool = False,
    initial_branch: str = "main",
) -> None:
    """Initialise a git repo with deterministic identity for tests."""
    args = ["git", "init"]
    if bare:
        args.append("--bare")
    args.extend(["-b", initial_branch])
    subprocess.run(args, cwd=path, check=True, capture_output=True)
    if not bare:
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=path,
            check=True,
            capture_output=True,
        )


def _commit(repo: Path, file_rel: str, contents: str, message: str) -> None:
    target = repo / file_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contents, encoding="utf-8")
    subprocess.run(
        ["git", "add", "--", file_rel],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo,
        check=True,
        capture_output=True,
    )


class TestResolveBranchBaseRefSelfTracking:
    """Issue #2571: pre_pr.py missed changed workflow files that pre-push detected.

    When ``git push -u origin HEAD`` is used (the default workflow that VS Code,
    the GitHub CLI, and the documented contributor flow all rely on), the
    branch's upstream (``@{u}``) is the branch's own remote-tracking ref
    (e.g. ``origin/fix/2551-renovate-secret-guard``). After the push, that ref
    matches HEAD, so ``git diff --name-only @{u}...HEAD`` returns nothing and
    every gate that scoped itself to "changes since base" silently no-ops.

    The pre-push hook is unaffected because it computes the diff against the
    merge-base with ``origin/main`` directly from the push refs git provides on
    stdin, never the branch's configured upstream.

    The fix in ``_resolve_branch_base_ref`` is to skip ``@{u}`` when it
    resolves to the current branch's own remote-tracking ref and fall through
    to ``refs/remotes/origin/HEAD`` / ``origin/main``. Other ``@{u}`` values
    (e.g. a derivative branch tracking its parent feature branch) are still
    honoured.
    """

    def _make_clone_with_self_tracking_upstream(self, tmp_path: Path) -> Path:
        """Build a clone whose feature branch upstream is itself, post-push.

        Returns the local repo path. Layout:

          - ``remote/`` -- bare repo with one commit on ``main`` and a feature
            branch ``fix/2571-demo`` that already contains a workflow change.
          - ``local/`` -- clone of the bare remote with ``fix/2571-demo``
            checked out and configured to track ``origin/fix/2571-demo``.
        """
        remote_bare = tmp_path / "remote"
        remote_bare.mkdir()
        _init_git_repo(remote_bare, bare=True)

        seed = tmp_path / "seed"
        subprocess.run(
            ["git", "clone", str(remote_bare), str(seed)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        _commit(seed, "README.md", "seed\n", "chore: seed")
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=seed,
            check=True,
            capture_output=True,
        )

        # Branch off, change a workflow file, push -u (the default workflow).
        subprocess.run(
            ["git", "checkout", "-b", "fix/2571-demo"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        _commit(
            seed,
            ".github/workflows/dependabot-approve-and-auto-merge.yml",
            "name: demo\non: push\njobs: {}\n",
            "ci: add workflow",
        )
        subprocess.run(
            ["git", "push", "-u", "origin", "fix/2571-demo"],
            cwd=seed,
            check=True,
            capture_output=True,
        )

        # Now produce the working clone that contributors actually run pre_pr from.
        local = tmp_path / "local"
        subprocess.run(
            ["git", "clone", str(remote_bare), str(local)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=local,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=local,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", "-b", "fix/2571-demo", "origin/fix/2571-demo"],
            cwd=local,
            check=True,
            capture_output=True,
        )
        # ``checkout -b ... origin/<branch>`` already sets upstream to
        # origin/<branch>; assert that as a precondition for the test.
        upstream = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=local,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert upstream == "origin/fix/2571-demo", (
            f"precondition: branch must self-track, got {upstream!r}"
        )
        return local

    def test_falls_through_self_tracking_upstream_so_diff_sees_branch_changes(
        self, tmp_path: Path
    ) -> None:
        """RED for Issue #2571: a self-tracking upstream must not be the diff base.

        With the bug, ``_resolve_branch_base_ref`` returns ``@{u}`` even when
        ``@{u}`` is the branch's own ``origin/<branch>``, and the resulting
        ``git diff <base>...HEAD`` returns no files -- pre_pr's workflow gate
        false-PASSes the changed ``.github/workflows/*.yml`` file. The fix
        falls through to ``refs/remotes/origin/HEAD`` (which resolves to
        ``origin/main`` here) so the diff actually shows the workflow file.
        """
        local = self._make_clone_with_self_tracking_upstream(tmp_path)

        # Sanity: with the buggy resolution (@{u}=origin/fix/2571-demo) the
        # diff is empty. With the correct resolution it contains the workflow.
        diff_against_self = subprocess.run(
            ["git", "diff", "--name-only", "origin/fix/2571-demo...HEAD"],
            cwd=local,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert diff_against_self == "", (
            "precondition: self-tracking diff is empty, so the gate that "
            "uses this base would falsely report no changes"
        )

        base_ref = _resolve_branch_base_ref(local)

        # The point of the fix: do not hand back the branch's own
        # origin/<branch> ref, because that produces a useless diff range
        # post-push. Either of the trunk-pointing fallbacks is acceptable.
        assert base_ref not in (
            "@{u}",
            "origin/fix/2571-demo",
        ), (
            f"_resolve_branch_base_ref returned a self-tracking upstream "
            f"({base_ref!r}); pre_pr would compute an empty diff and miss "
            "changed workflow files (Issue #2571)."
        )

        # Verify the resolved base produces a non-empty diff containing the
        # workflow file (the contract callers depend on).
        diff_against_resolved = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            cwd=local,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip().splitlines()
        assert (
            ".github/workflows/dependabot-approve-and-auto-merge.yml"
            in diff_against_resolved
        ), (
            "Resolved base ref must yield a diff range that contains the "
            "changed workflow file; got: "
            f"{diff_against_resolved!r}"
        )

    def test_honours_non_self_tracking_upstream(self, tmp_path: Path) -> None:
        """Derivative branches tracking a parent feature branch must still use @{u}.

        Counter-test for the fix: if a branch's upstream is some OTHER ref
        (the parent feature branch in a derivative-PR workflow), the resolver
        must still return ``@{u}``. Falling all the way through to
        ``origin/main`` here would pull in the parent feature branch's
        commits as "changes" and false-PASS / false-FAIL downstream gates.
        """
        remote_bare = tmp_path / "remote"
        remote_bare.mkdir()
        _init_git_repo(remote_bare, bare=True)

        seed = tmp_path / "seed"
        subprocess.run(
            ["git", "clone", str(remote_bare), str(seed)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        _commit(seed, "README.md", "seed\n", "chore: seed")
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=seed,
            check=True,
            capture_output=True,
        )

        # Build a parent feature branch and a derivative branch off it.
        subprocess.run(
            ["git", "checkout", "-b", "feat/parent"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        _commit(seed, "parent.txt", "parent\n", "feat: parent work")
        subprocess.run(
            ["git", "push", "-u", "origin", "feat/parent"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", "-b", "feat/derivative"],
            cwd=seed,
            check=True,
            capture_output=True,
        )
        _commit(seed, "derivative.txt", "derivative\n", "feat: derivative")
        # The derivative branch tracks feat/parent, NOT itself.
        subprocess.run(
            [
                "git",
                "branch",
                "--set-upstream-to=origin/feat/parent",
                "feat/derivative",
            ],
            cwd=seed,
            check=True,
            capture_output=True,
        )

        upstream = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=seed,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert upstream == "origin/feat/parent", (
            f"precondition: derivative branch must track parent feature, got {upstream!r}"
        )

        base_ref = _resolve_branch_base_ref(seed)
        assert base_ref == "@{u}", (
            f"Derivative branches with a non-self upstream must keep using "
            f"@{{u}}; got {base_ref!r}. Otherwise the parent feature branch's "
            "commits get counted as part of the derivative's diff."
        )
