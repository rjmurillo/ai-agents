"""Skip-or-fail policy for the CLI smokes (owner decision D26).

Classifies a blocked Copilot or Claude run (spent budget, auth, rate limit,
transport, latency) and turns it into a loud skip or a CI failure. The Copilot
block classifiers live in ``copilot_hook_probe``; this module imports them.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal, NoReturn

import pytest

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
_original_sys_path = sys.path.copy()
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from copilot_hook_probe import (
        copilot_quota_exhausted,
        copilot_run_blocked,
        copilot_run_blocked_headline,
    )
finally:
    sys.path[:] = _original_sys_path

# Prefix of a skip reason for budget exhaustion only (owner decision D26): a
# spent Copilot monthly quota (HTTP 402) or a spent Claude credit balance. The
# Copilot and Claude CI legs pass it to
# scripts/validation/assert_smoke_ran.py --allow-skip-marker, so a prompt-based
# best-effort test that hits an exhausted budget does not fail the gate.
# Copilot auth, rate limit, transport, and latency blocks never carry it: in CI
# they fail the test, and locally they skip loudly without the marker, so the
# gate still turns red on any of them. A Claude 429 does carry it: the CLI
# cannot tell a usage limit from a rate limit, so it counts as quota. Any other
# skip still fails the gate.
QUOTA_SKIP_MARKER = "QUOTA_SKIP:"


def running_in_ci() -> bool:
    """True under GitHub Actions or any runner that exports ``CI``."""
    return os.environ.get("GITHUB_ACTIONS") == "true" or bool(os.environ.get("CI"))


def copilot_block_skip_reason(result: subprocess.CompletedProcess[str]) -> str:
    """Skip reason for a classified block.

    Only budget exhaustion (``quota_exhausted``) leads with
    :data:`QUOTA_SKIP_MARKER`. A rate limit is transient and is re-run, so it
    is deliberately not marker-skippable: the Copilot classifier tells a rate
    limit from a spent quota.
    """
    headline = copilot_run_blocked_headline(result)
    if copilot_quota_exhausted(result):
        return f"{QUOTA_SKIP_MARKER} {headline}"
    return headline


def skip_or_fail_unmarked(message: str) -> NoReturn:
    """Fail in CI, skip loudly without the marker elsewhere (no quota marker seen)."""
    if running_in_ci():
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


def skip_or_fail_on_copilot_block(result: subprocess.CompletedProcess[str]) -> None:
    """Apply the D26 policy to a Copilot run: no-op unless a classified block.

    Quota exhaustion skips with the marker everywhere. Every other classified
    block (auth, rate limit, transport) fails in CI and skips unmarked locally.
    """
    if not copilot_run_blocked(result):
        return
    if copilot_quota_exhausted(result):
        pytest.skip(copilot_block_skip_reason(result))
    skip_or_fail_unmarked(copilot_block_skip_reason(result))


# Claude CLI external-block markers (issue #4861), lowercased regexes. Auth is
# checked first, as before. The 429 status is ambiguous: the CLI reports a
# usage limit and a rate limit the same way, so the classifier cannot tell
# them apart, so 429 is treated as quota and marker-skippable. This differs from
# Copilot, where a rate limit fails because its classifier can separate it from
# a spent quota (D26: only exhausted quota or credit is marker-skipped).
# "credit balance is too low" is the exhausted-credit message.
CLAUDE_AUTH_BLOCK_PATTERNS: tuple[str, ...] = (
    "oauth session expired",
    "failed to authenticate",
    "could not be refreshed",
)
CLAUDE_QUOTA_BLOCK_PATTERNS: tuple[str, ...] = (
    "monthly spend limit",
    "weekly limit resets",
    r'"api_error_status"\s*:\s*429',
    "credit balance is too low",
)

ClaudeBlockReason = Literal["auth", "quota"]


def claude_block_reason(run: subprocess.CompletedProcess[str]) -> ClaudeBlockReason | None:
    """Classify a failed Claude run; a successful run is never blocked."""
    if run.returncode == 0:
        return None
    haystack = f"{run.stderr or ''}\n{run.stdout or ''}".lower()
    if any(re.search(pattern, haystack) for pattern in CLAUDE_AUTH_BLOCK_PATTERNS):
        return "auth"
    if any(re.search(pattern, haystack) for pattern in CLAUDE_QUOTA_BLOCK_PATTERNS):
        return "quota"
    return None


def skip_or_fail_on_claude_block(run: subprocess.CompletedProcess[str], subject: str) -> None:
    """Apply the D26 policy to a Claude run: no-op unless a classified block."""
    reason = claude_block_reason(run)
    if reason is None:
        return
    if reason == "quota":
        pytest.skip(
            f"{QUOTA_SKIP_MARKER} Claude quota, credit, or rate limit (429) hit for "
            f"{subject}. The Claude CLI does not distinguish quota, credit, and rate "
            "limit, so this skip may be a transient rate limit and not an exhausted "
            "budget. Re-run after the budget resets or the rate limit clears."
        )
    skip_or_fail_unmarked(
        f"Claude OAuth session expired or could not authenticate for {subject}; "
        "rotate the credential."
    )
