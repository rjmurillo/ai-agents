"""Always-on tests for the D26 block policy inside the hook-resolution smokes.

Each test drives the real smoke body (``test_cli_hook_e2e``) with a stubbed CLI
run that returns a classified block, then asserts the skip or fail outcome.
No CLI, auth, or credits are needed. The smokes themselves stay in
``test_cli_hook_e2e.py`` so ``plugin-cli-smoke.yml`` still selects them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import smoke_skip_policy

from tests.e2e import test_cli_hook_e2e as hook_e2e

_QUOTA_STDERR = "You have exceeded your monthly quota (Request ID: C612:60CD4)"
_RATE_LIMIT_STDERR = "API rate limit exceeded for user ID 12345."
_TRANSPORT_STDERR = "Failed to fetch PAT user login: connection reset by peer."


def _set_ci(monkeypatch: pytest.MonkeyPatch, *, ci: bool) -> None:
    monkeypatch.delenv("CI", raising=False)
    if ci:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
    else:
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def _run_vendor_consumer_with_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, blocked_phase: str, stderr: str
) -> None:
    """Run the vendor-consumer smoke with one phase returning a blocked Copilot run."""
    success = subprocess.CompletedProcess(["copilot"], 0, stdout="", stderr="")
    blocked = subprocess.CompletedProcess(["copilot"], 1, stdout="", stderr=stderr)

    def fake_run(argv: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        is_install = "plugin" in argv and "install" in argv
        if blocked_phase == "install":
            return blocked if is_install else success
        return success if is_install else blocked

    monkeypatch.setattr("tests.e2e.test_cli_hook_e2e._copilot_command", lambda *a: a)
    monkeypatch.setattr("tests.e2e.test_cli_hook_e2e.subprocess.run", fake_run)
    hook_e2e.test_copilot_vendor_install_hook_resolves(tmp_path)


@pytest.mark.parametrize("blocked_phase", ["install", "run"])
@pytest.mark.parametrize("ci", [True, False], ids=["ci", "local"])
def test_copilot_vendor_consumer_skips_a_spent_quota_with_the_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, blocked_phase: str, ci: bool
) -> None:
    _set_ci(monkeypatch, ci=ci)
    with pytest.raises(pytest.skip.Exception) as skipped:
        _run_vendor_consumer_with_block(monkeypatch, tmp_path, blocked_phase, _QUOTA_STDERR)
    assert str(skipped.value).startswith(smoke_skip_policy.QUOTA_SKIP_MARKER)


@pytest.mark.parametrize("blocked_phase", ["install", "run"])
@pytest.mark.parametrize("stderr", [_RATE_LIMIT_STDERR, _TRANSPORT_STDERR])
def test_copilot_vendor_consumer_fails_in_ci_on_a_non_quota_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, blocked_phase: str, stderr: str
) -> None:
    _set_ci(monkeypatch, ci=True)
    with pytest.raises(pytest.fail.Exception):
        _run_vendor_consumer_with_block(monkeypatch, tmp_path, blocked_phase, stderr)


@pytest.mark.parametrize("blocked_phase", ["install", "run"])
@pytest.mark.parametrize("stderr", [_RATE_LIMIT_STDERR, _TRANSPORT_STDERR])
def test_copilot_vendor_consumer_skips_unmarked_locally_on_a_non_quota_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, blocked_phase: str, stderr: str
) -> None:
    _set_ci(monkeypatch, ci=False)
    with pytest.raises(pytest.skip.Exception) as skipped:
        _run_vendor_consumer_with_block(monkeypatch, tmp_path, blocked_phase, stderr)
    assert smoke_skip_policy.QUOTA_SKIP_MARKER not in str(skipped.value)


def _run_claude_hook_with_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stdout: str
) -> None:
    blocked = subprocess.CompletedProcess(["claude"], 1, stdout=stdout, stderr="")
    monkeypatch.setattr("tests.e2e.test_cli_hook_e2e.subprocess.run", lambda *a, **kw: blocked)
    hook_e2e.test_claude_plugin_dir_hook_resolves(tmp_path)


def test_claude_hook_e2e_skips_with_the_marker_on_a_spent_credit_balance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_ci(monkeypatch, ci=True)
    with pytest.raises(pytest.skip.Exception) as skipped:
        _run_claude_hook_with_output(monkeypatch, tmp_path, "Credit balance is too low")
    assert str(skipped.value).startswith(smoke_skip_policy.QUOTA_SKIP_MARKER)


def test_claude_hook_e2e_fails_in_ci_on_an_auth_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _set_ci(monkeypatch, ci=True)
    with pytest.raises(pytest.fail.Exception):
        _run_claude_hook_with_output(monkeypatch, tmp_path, "oauth session expired")


def test_claude_hook_e2e_still_asserts_the_marker_on_an_unclassified_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with pytest.raises(AssertionError, match="hook never ran"):
        _run_claude_hook_with_output(monkeypatch, tmp_path, "boom")
