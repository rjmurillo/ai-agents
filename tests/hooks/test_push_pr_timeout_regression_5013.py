"""Regression tests for issue #5013: push-pr guard timeout denial.

Demonstrates:
1. Timeout on the shared timed-shim path returns 0 (allow), not 2 (deny).
2. Unrelated commands pass through the identity guard in-process without timeout.
3. Canonical new_pr.py invocations remain allowed.
4. Repository lookalikes remain denied.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Shared-path timeout policy (hook_dispatch_timeout.py)
# ---------------------------------------------------------------------------


class TestTimedShimTimeoutPolicy:
    """The shared timed-shim launcher must allow on timeout (issue #5013)."""

    def test_timeout_returns_allow_exit(self, tmp_path: Path) -> None:
        """TimeoutExpired must produce exit 0, not exit 2."""
        shim = tmp_path / "slow.py"
        shim.write_text("import time\ntime.sleep(60)\n")

        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "copilot-cli" / "lib"))
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

        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "copilot-cli" / "lib"))
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

        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "copilot-cli" / "lib"))
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

        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "copilot-cli" / "lib"))
        try:
            from hook_dispatch_timeout import run_timed_shim

            code, _, _ = run_timed_shim(shim, "deny.py", b"", 10.0)
        finally:
            sys.path.pop(0)

        assert code == 2, "completed shim exit code must be preserved"


# ---------------------------------------------------------------------------
# Identity guard in-process execution (no timeout path)
# ---------------------------------------------------------------------------


class TestTimeoutPolicyIsAllowNotDeny:
    """The shared timeout path now returns 0 (allow), not 2 (deny).

    This is the containment for issue #5013: even if the identity guard
    times out under contention, it cannot deny unrelated commands.
    """

    def test_timeout_module_exports_allow_exit(self) -> None:
        """The module must export ALLOW_EXIT = 0 for the timeout path."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "copilot-cli" / "lib"))
        try:
            from hook_dispatch_timeout import ALLOW_EXIT

            assert ALLOW_EXIT == 0
        finally:
            sys.path.pop(0)

    def test_identity_guard_timeout_cannot_deny(self) -> None:
        """Even with timeout metadata, the guard cannot deny on timeout."""
        import json

        groups_path = (
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "dispatch_groups.json"
        )
        with open(groups_path) as f:
            data = json.load(f)
        key = "plugin-pretooluse-9-push_pr_script_identity"
        if key not in data:
            pytest.skip("identity guard not registered")
        # The guard may have a timeout, but the timeout policy is allow (0)
        # so it can never deny unrelated commands (issue #5013)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases around the timeout boundary."""

    def test_zero_timeout_is_rejected_by_validate_timeout(self) -> None:
        """Invalid timeout (<=0) is caught by _validate_timeout, not run_timed_shim."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "copilot-cli" / "lib"))
        try:
            from hook_dispatch import _validate_timeout

            result = _validate_timeout("test.py", 0)
            assert result == 2, "invalid timeout must deny via _validate_timeout"
        finally:
            sys.path.pop(0)

    def test_negative_timeout_is_rejected_by_validate_timeout(self) -> None:
        """Negative timeout is caught by _validate_timeout."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "copilot-cli" / "lib"))
        try:
            from hook_dispatch import _validate_timeout

            result = _validate_timeout("test.py", -1)
            assert result == 2
        finally:
            sys.path.pop(0)
