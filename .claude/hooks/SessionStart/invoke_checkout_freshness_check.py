#!/usr/bin/env python3
"""Report how far the local checkout is behind origin/main at session start.

Claude Code SessionStart hook that fetches origin/main and states the commit
gap before any triage or investigation work begins. Silence is the failure
mode this exists to close: without a stated number, a stale checkout looks
identical to a fresh one, and conclusions drawn against it are drawn against
dead code.

Fires for a linked worktree the same as a primary checkout: git resolves HEAD
and the origin/main remote-tracking ref relative to whichever working tree
this process runs in, so no worktree-specific branch is needed here.

Hook Type: SessionStart (non-blocking, fail-open)
Exit Codes:
    0 = Success (always, fail-open)

References:
    - Issue #4689 (no session-start gate detects a stale local checkout)
    - .serena/memories/decision-measure-against-fresh-worktree-not-stale-checkout.md
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# --- Standard hook boilerplate: resolve lib directory ---
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if os.path.isdir(_lib_dir) and _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities import get_project_directory
    from hook_utilities.guards import skip_if_consumer_repo
except ImportError:

    def get_project_directory() -> str:
        env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
        if env_dir:
            return str(Path(env_dir).resolve())
        return str(Path.cwd())

    def skip_if_consumer_repo(hook_name: str) -> bool:
        agents_path = Path(get_project_directory()) / ".agents"
        if not agents_path.is_dir():
            print(f"[SKIP] {hook_name}: .agents/ not found (consumer repo)", file=sys.stderr)
            return True
        return False


HOOK_NAME = "checkout-freshness-check"

# Network fetch and local ref-count both bounded, so a slow or unreachable
# remote degrades to a stale-but-stated answer instead of hanging session start.
GIT_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class FreshnessCheck:
    """Result of comparing HEAD against origin/main.

    ``commits_behind`` is None only when origin/main could not be resolved at
    all (no remote, ref never fetched, git missing) per issue #4689's
    acceptance criterion that this case reports failure rather than zero.
    """

    commits_behind: int | None
    fetch_succeeded: bool
    error: str | None


def _run_git(
    args: list[str], cwd: str, timeout: float = GIT_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def check_checkout_freshness(cwd: str) -> FreshnessCheck:
    """Report how many commits HEAD is behind origin/main, after a fetch.

    A fetch failure (offline, network error, timeout) does not abort the
    check: a stale local origin/main ref still answers the question, flagged
    as possibly stale. Only an unresolvable origin/main ref (no remote, never
    fetched, git missing) is a hard failure, per #4689's acceptance criteria.
    """
    fetch_succeeded = True
    try:
        fetch_result = _run_git(["fetch", "origin", "main", "--quiet"], cwd)
        fetch_succeeded = fetch_result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        fetch_succeeded = False

    try:
        count_result = _run_git(["rev-list", "--count", "HEAD..origin/main"], cwd)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return FreshnessCheck(commits_behind=None, fetch_succeeded=fetch_succeeded, error=str(exc))

    if count_result.returncode != 0:
        detail = count_result.stderr.strip() or f"git rev-list exited {count_result.returncode}"
        return FreshnessCheck(commits_behind=None, fetch_succeeded=fetch_succeeded, error=detail)

    raw = count_result.stdout.strip()
    if not raw.isdigit():
        return FreshnessCheck(
            commits_behind=None,
            fetch_succeeded=fetch_succeeded,
            error=f"unexpected git rev-list output: {raw!r}",
        )

    return FreshnessCheck(commits_behind=int(raw), fetch_succeeded=fetch_succeeded, error=None)


def _format_message(check: FreshnessCheck) -> str:
    header = "## Checkout Freshness Check\n\n"

    if check.commits_behind is None:
        return (
            header
            + f"**FAILED to resolve origin/main.** {check.error}\n\n"
            + "Cannot determine how many commits behind origin/main this checkout "
            + "is. Treat prior conclusions as suspect until this is fixed "
            + "(`git fetch origin main` by hand, then re-check)."
        )

    stale_note = " (fetch failed, this count may be stale)" if not check.fetch_succeeded else ""

    if check.commits_behind == 0:
        return header + f"Checkout is 0 commits behind `origin/main`{stale_note}."

    return (
        header
        + f"**Checkout is {check.commits_behind} commit(s) behind `origin/main`"
        + f"{stale_note}.** Investigation or triage against this tree may be "
        + "reasoning about dead code. Run `git fetch origin main` and "
        + "`git rev-list --count HEAD..origin/main` to re-check, or work from a "
        + "fresh worktree instead."
    )


def _write_audit_log(project_dir: str, check: FreshnessCheck) -> None:
    """Write a brief audit entry for the freshness check (best-effort)."""
    try:
        audit_dir = Path(project_dir) / ".agents" / ".hook-state"
        audit_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        timestamp = datetime.now(tz=UTC).isoformat()
        audit_file = audit_dir / f"checkout-freshness-{today}.log"

        with audit_file.open("a", encoding="utf-8") as f:
            f.write(
                f"[{timestamp}] commits_behind={check.commits_behind} "
                f"fetch_succeeded={check.fetch_succeeded} error={check.error!r}\n"
            )
    except OSError:
        pass  # Fail-open: audit is best-effort


def _drain_stdin() -> None:
    """Drain stdin to prevent pipe buffer blocking on the harness side."""
    if not sys.stdin.isatty():
        try:
            sys.stdin.read()
        except OSError:
            pass


def _emit_utf8(text: str) -> None:
    """Prefer UTF-8 protocol output, with an ambient-encoding text fallback."""
    stream = sys.stdout
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="strict", newline="\n")
        except (
            AttributeError,
            TypeError,
            ValueError,
            io.UnsupportedOperation,
            OSError,
        ):
            pass
        else:
            stream.write(text + "\n")
            stream.flush()
            return

    payload = bytes(f"{text}\n", encoding="utf-8")
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(payload)
        buffer.flush()
        return

    stream.write(text + "\n")
    stream.flush()


def main() -> None:
    """Fetch origin/main, compare against HEAD, and inject the stated gap."""
    _drain_stdin()

    if skip_if_consumer_repo(HOOK_NAME):
        sys.exit(0)

    project_dir = get_project_directory()
    check = check_checkout_freshness(project_dir)
    _emit_utf8(_format_message(check))
    _write_audit_log(project_dir, check)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Fail-open: never block session start
        print(f"[WARNING] {HOOK_NAME} error: {exc}", file=sys.stderr)
        sys.exit(0)
