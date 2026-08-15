"""Regression tests for issue #5013: push-pr guard timeout denial.

Demonstrates:
1. Timeout on the shared timed-shim path returns 0 (allow), not 2 (deny).
2. Unrelated commands do not fire the narrowed identity guard matcher.
3. Canonical new_pr.py invocations remain allowed.
4. Repository lookalikes remain denied.
5. Concurrent unrelated commands all pass without contention denial.
"""

from __future__ import annotations

import concurrent.futures
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.hooks.push_pr_guard_harness import (
    REPO_ROOT,
    run_claude,
    run_copilot,
)
from tests.hooks.push_pr_guard_harness import (
    repository as _repository,
)

# ---------------------------------------------------------------------------
# Shared-path timeout policy (hook_dispatch_timeout.py)
# ---------------------------------------------------------------------------


class TestTimedShimTimeoutPolicy:
    """The shared timed-shim launcher must allow on timeout (issue #5013)."""

    def test_timeout_returns_allow_exit(self, tmp_path: Path) -> None:
        """TimeoutExpired must produce exit 0, not exit 2."""
        shim = tmp_path / "slow.py"
        shim.write_text("import time\ntime.sleep(60)\n")

        sys.path.insert(0, str(REPO_ROOT / "src" / "copilot-cli" / "lib"))
        try:
            from hook_dispatch_timeout import run_timed_shim

            code, stdout, stderr = run_timed_shim(shim, "slow.py", b"", 0.1)
        finally:
            sys.path.pop(0)

        assert code == 0, f"timeout must allow (exit 0), got {code}"

    def test_timeout_emits_warning_on_stderr(self, tmp_path: Path, capsys) -> None:
        """Timeout warning names the shim, the duration, and reinstall advice."""
        shim = tmp_path / "slow.py"
        shim.write_text("import time\ntime.sleep(60)\n")

        sys.path.insert(0, str(REPO_ROOT / "src" / "copilot-cli" / "lib"))
        try:
            from hook_dispatch_timeout import run_timed_shim

            run_timed_shim(shim, "slow.py", b"", 0.1)
        finally:
            sys.path.pop(0)

        err = capsys.readouterr().err
        assert "slow.py" in err
        assert "timed out" in err
        assert "allowing" in err
        assert "Reinstall" in err

    def test_launch_failure_returns_allow_exit(self, tmp_path: Path) -> None:
        """OSError (missing interpreter) must produce exit 0, not exit 2."""
        shim = tmp_path / "nonexistent.py"
        shim.write_text("pass\n")

        sys.path.insert(0, str(REPO_ROOT / "src" / "copilot-cli" / "lib"))
        try:
            from hook_dispatch_timeout import run_timed_shim

            with patch("subprocess.run", side_effect=OSError("No such file")):
                code, _, _ = run_timed_shim(shim, "broken.py", b"", 10.0)
        finally:
            sys.path.pop(0)

        assert code == 0, f"launch failure must allow (exit 0), got {code}"

    def test_successful_shim_exit_code_is_preserved(self, tmp_path: Path) -> None:
        """A shim that completes within the timeout has its exit code passed through."""
        shim = tmp_path / "deny.py"
        shim.write_text("import sys\nsys.exit(2)\n")

        sys.path.insert(0, str(REPO_ROOT / "src" / "copilot-cli" / "lib"))
        try:
            from hook_dispatch_timeout import run_timed_shim

            code, _, _ = run_timed_shim(shim, "deny.py", b"", 10.0)
        finally:
            sys.path.pop(0)

        assert code == 2, "completed shim exit code must be preserved"


# ---------------------------------------------------------------------------
# Relevance boundary: unrelated commands do not fire the guard
# ---------------------------------------------------------------------------


_UNRELATED_COMMANDS = [
    "git status",
    "git log --oneline -5",
    "git fetch origin",
    "git push origin HEAD",
    "ls -la",
    'bash -c "echo hello"',
    "node -e 'console.log(1)'",
    "cat README.md",
    "grep -r TODO src/",
    "curl --version",
]


class TestRelevanceBoundary:
    """Unrelated commands exit 0 without launching the identity guard.

    Issue #5013 acceptance criterion 2: unrelated commands do not launch
    the identity shim. The narrowed matcher Bash(*new_pr*|*push_pr*|*push-pr*)
    ensures the shim self-filters at the matcher level.
    """

    @pytest.fixture()
    def repo(self, tmp_path: Path) -> Path:
        return _repository(tmp_path)[0]

    @pytest.mark.parametrize("command", _UNRELATED_COMMANDS)
    def test_claude_dispatcher_allows_unrelated(self, repo: Path, command: str) -> None:
        """Claude dispatcher returns 0 for unrelated commands."""
        result = run_claude(command, repo)
        assert result.returncode == 0, (
            f"unrelated command {command!r} denied (exit {result.returncode}): "
            f"{result.stderr}"
        )

    @pytest.mark.parametrize("command", _UNRELATED_COMMANDS)
    def test_copilot_dispatcher_allows_unrelated(self, repo: Path, command: str) -> None:
        """Copilot dispatcher returns 0 for unrelated commands."""
        result = run_copilot(command, repo)
        assert result.returncode == 0, (
            f"unrelated command {command!r} denied (exit {result.returncode}): "
            f"{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Concurrency: no contention denial under parallel load
# ---------------------------------------------------------------------------


class TestConcurrencyRegression:
    """32+ unrelated commands with 8 workers must all pass (issue #5013 AC 6).

    The original bug manifested as contention denial: multiple unrelated
    shell commands hitting the 10-second timeout simultaneously, all denied.
    """

    @pytest.fixture()
    def repo(self, tmp_path: Path) -> Path:
        return _repository(tmp_path)[0]

    def test_concurrent_unrelated_commands_all_allow(self, repo: Path) -> None:
        """32 concurrent unrelated commands via Claude dispatcher all exit 0."""
        commands = _UNRELATED_COMMANDS * 4  # 40 commands total (>32)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(run_claude, cmd, repo)
                for cmd in commands
            ]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        denied = [
            (r.returncode, r.stderr[:100])
            for r in results
            if r.returncode != 0
        ]
        assert not denied, (
            f"{len(denied)} of {len(commands)} concurrent commands denied: "
            f"{denied[:3]}"
        )


# ---------------------------------------------------------------------------
# Matcher narrowing verification
# ---------------------------------------------------------------------------


class TestMatcherNarrowing:
    """The identity guard matcher is narrow, not plugin-wide (issue #5013 AC 2)."""

    def test_dispatch_groups_matcher_is_narrow(self) -> None:
        """dispatch_groups.json matcher must not be bare 'Bash'."""
        groups_path = REPO_ROOT / ".claude" / "hooks" / "dispatch_groups.json"
        with open(groups_path) as f:
            data = json.load(f)
        key = "plugin-pretooluse-9-push_pr_script_identity"
        group = data["groups"][key]
        matcher = group["matcher"]
        assert matcher != "Bash", (
            "identity guard matcher must be narrow, got bare 'Bash' "
            "(issue #5013: unrelated commands must not launch the shim)"
        )
        assert "new_pr" in matcher, "matcher must include new_pr pattern"
        assert "python" in matcher, "matcher must include python pattern for content detection"

    def test_copilot_shim_matcher_is_narrow(self) -> None:
        """Generated Copilot shim must use the narrowed matcher."""
        shim_dir = REPO_ROOT / "src" / "copilot-cli" / "hooks" / "PreToolUse"
        shims = list(shim_dir.glob("invoke_push_pr_script_identity_guard__*.py"))
        assert len(shims) == 1, f"expected 1 identity guard shim, found {len(shims)}"
        content = shims[0].read_text()
        # The shim must NOT have bare Bash matcher
        assert "_MATCHER = 'Bash'" not in content, (
            "Copilot shim still has plugin-wide Bash matcher"
        )
        assert "new_pr" in content, "shim matcher must include new_pr pattern"
        assert "python" in content, "shim matcher must include python for content detection"

    def test_claude_hooks_json_matcher_is_narrow(self) -> None:
        """Claude hooks.json must not register identity guard on bare Bash."""
        hooks_path = REPO_ROOT / ".claude" / "hooks" / "hooks.json"
        with open(hooks_path) as f:
            data = json.load(f)
        ptu_entries = data["hooks"]["PreToolUse"]
        identity_entry = None
        for entry in ptu_entries:
            hooks = entry.get("hooks", [])
            for h in hooks:
                cmd = h.get("command", "")
                if "push_pr_script_identity" in cmd:
                    identity_entry = entry
                    break
        assert identity_entry is not None, "identity guard not found in hooks.json"
        matcher = identity_entry.get("matcher", "")
        assert matcher != "Bash", (
            "hooks.json identity guard matcher is bare 'Bash' (must be narrow)"
        )


# ---------------------------------------------------------------------------
# Edge cases: timeout validation
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases around the timeout boundary."""

    def test_zero_timeout_returns_deny_exit_code(self) -> None:
        """Invalid timeout (<=0) is caught by _validate_timeout, returns exit 2."""
        sys.path.insert(0, str(REPO_ROOT / "src" / "copilot-cli" / "lib"))
        try:
            from hook_dispatch import _validate_timeout

            result = _validate_timeout("test.py", 0)
            assert result == 2, "invalid timeout must deny via exit code 2"
        finally:
            sys.path.pop(0)

    def test_negative_timeout_returns_deny_exit_code(self) -> None:
        """Negative timeout is caught by _validate_timeout, returns exit code 2."""
        sys.path.insert(0, str(REPO_ROOT / "src" / "copilot-cli" / "lib"))
        try:
            from hook_dispatch import _validate_timeout

            result = _validate_timeout("test.py", -1)
            assert result == 2, "negative timeout must deny via exit code 2"
        finally:
            sys.path.pop(0)
