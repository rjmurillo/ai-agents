#!/usr/bin/env python3
"""Block false completion claims without verification evidence.

Claude Code PreToolUse hook that detects when agents claim "done", "fixed",
etc. in commit messages or PR operations without prior verification evidence
(test/build runs) in the session log.

Addresses 44 false completion mentions across 80+ retrospectives.

Gate triggers on:
- git commit messages containing completion signals
- gh pr create commands with completion language

Evidence requirements (any one satisfies):
1. Test run in session log (pytest, npm test, etc.)
2. Build verification in session log (tsc --noEmit, etc.)
3. PR checks verified (gh pr checks)

Bypass conditions:
- SKIP_COMPLETION_GATE=true environment variable
- Documentation-only changes (*.md files only)
- No session log present (fail-open)
- Non-commit/non-PR commands

Hook Type: PreToolUse (blocking on match)
Exit Codes (Claude Hook Semantics):
    0 = Allow (evidence exists or not a completion claim)
    2 = Block (completion claim without verification)

References:
    - Issue #1703 (lifecycle hook infrastructure)
    - Issue #1673 (false completion)
    - ADR-008 (protocol automation)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# --- Standard hook boilerplate ---
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
if os.path.isdir(_lib_dir) and _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities import get_project_directory, get_today_session_log
    from hook_utilities.guards import skip_if_consumer_repo
except ImportError:

    def get_project_directory() -> str:
        env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
        if env_dir:
            return str(Path(env_dir).resolve())
        return str(Path.cwd())

    def get_today_session_log(sessions_dir: str, date: str | None = None) -> Path | None:
        if date is None:
            date = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        sessions_path = Path(sessions_dir)
        if not sessions_path.is_dir():
            return None
        try:
            logs = sorted(
                sessions_path.glob(f"{date}-session-*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return None
        return logs[0] if logs else None

    def skip_if_consumer_repo(hook_name: str) -> bool:
        agents_path = Path(get_project_directory()) / ".agents"
        if not agents_path.is_dir():
            print(f"[SKIP] {hook_name}: .agents/ not found (consumer repo)", file=sys.stderr)
            return True
        return False


HOOK_NAME = "false-completion-gate"

# Completion signal patterns in commit messages / PR titles
COMPLETION_SIGNALS = re.compile(
    r"\b(done|fixed|complete[ds]?|finished|resolved|merged|shipped|closes?\s+#\d+)\b",
    re.IGNORECASE,
)

# Verification evidence patterns in session logs
VERIFICATION_PATTERNS = [
    re.compile(r"pytest", re.IGNORECASE),
    re.compile(r"npm\s+test", re.IGNORECASE),
    re.compile(r"npm\s+run\s+test", re.IGNORECASE),
    re.compile(r"pnpm\s+test", re.IGNORECASE),
    re.compile(r"yarn\s+test", re.IGNORECASE),
    re.compile(r"tsc\s+--noEmit", re.IGNORECASE),
    re.compile(r"dotnet\s+test", re.IGNORECASE),
    re.compile(r"go\s+test", re.IGNORECASE),
    re.compile(r"gh\s+pr\s+checks", re.IGNORECASE),
    re.compile(r"Invoke-Pester", re.IGNORECASE),
    re.compile(r"uv\s+run\s+pytest", re.IGNORECASE),
    re.compile(r"make\s+test", re.IGNORECASE),
]


def _read_stdin_json() -> dict | None:
    """Read and parse JSON from stdin (Claude hook input)."""
    if sys.stdin.isatty():
        return None
    try:
        data = sys.stdin.read().strip()
        if not data:
            return None
        return json.loads(data)
    except (json.JSONDecodeError, OSError):
        return None


def _extract_command(hook_input: dict) -> str:
    """Extract the command string from hook input.

    Defends against malformed input where ``hook_input``, ``tool_input``,
    or ``tool_input["command"]`` is not a string. Returning an empty
    string lets the caller fall through to the no-op path instead of
    raising a ``TypeError`` inside the regex search and being swallowed
    by the top-level fail-open handler.
    """
    if not isinstance(hook_input, dict):
        return ""
    tool_input = hook_input.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return ""
    command = tool_input.get("command", "")
    if not isinstance(command, str):
        return ""
    return command


def _is_completion_claim(command: str) -> bool:
    """Check if a command contains completion signals."""
    return COMPLETION_SIGNALS.search(command) is not None


_GIT_TIMEOUT_SECONDS = 5


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str] | None:
    """Run a git subcommand bound to the project directory with a timeout.

    Returns ``None`` when git fails to launch or exceeds the timeout so
    callers can choose how to fall back instead of stalling the gate.
    """
    project_dir = get_project_directory()
    try:
        return subprocess.run(
            ["git", "-C", project_dir, *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _resolve_pr_base_branch() -> str | None:
    """Discover the base branch a ``gh pr create`` would target.

    Tries ``origin/HEAD`` symbolic ref first, then common default-branch
    names as a fallback. Returns ``None`` if nothing resolves so the
    caller can fall back to staged changes.

    Note: We intentionally skip ``@{u}`` (upstream tracking) because after
    ``git push -u origin feature-branch``, it resolves to ``origin/feature-branch``
    — the push target, not the PR merge target (e.g., ``main``).
    """

    head_ref = _run_git(["symbolic-ref", "refs/remotes/origin/HEAD"])
    if head_ref and head_ref.returncode == 0:
        ref = head_ref.stdout.strip()
        if ref:
            return ref.removeprefix("refs/remotes/")

    for default_branch in ("origin/main", "origin/master", "origin/develop",
                           "main", "master", "develop"):
        rev = _run_git(["rev-parse", "--verify", "--quiet", default_branch])
        if rev and rev.returncode == 0:
            return default_branch
    return None


def _changed_files_for_pr(current_branch: str) -> list[str] | None:
    """Return files changed against the resolved PR base, or None if unresolved.

    When the user is already on the default branch the merge-base degenerates
    to HEAD and produces an empty diff, which would falsely classify normal
    changes as non-documentation-only. The caller treats ``None`` as
    "fall through to staged diff."
    """
    base_branch = _resolve_pr_base_branch()
    if base_branch is None:
        return None

    # If we are sitting on the same ref as the resolved base, skip the
    # merge-base dance: comparing main..HEAD on main returns nothing.
    base_short = base_branch.removeprefix("origin/")
    if current_branch and current_branch == base_short:
        return None

    merge_base = _run_git(["merge-base", base_branch, "HEAD"])
    if not merge_base or merge_base.returncode != 0:
        return None

    diff = _run_git(
        ["diff", "--name-only", merge_base.stdout.strip(), "HEAD"]
    )
    if not diff or diff.returncode != 0:
        return None
    return [f.strip() for f in diff.stdout.strip().split("\n") if f.strip()]


def _is_documentation_only(is_pr_create: bool) -> bool:
    """Check if the relevant changed files are documentation-only.

    For ``git commit`` we look at the index. For ``gh pr create`` we
    resolve the actual base branch (upstream / origin/HEAD / common
    defaults) and diff the branch against the merge base. If no base
    can be resolved we fall back to the staged diff so docs-only PRs
    keep their bypass when possible.
    """
    if is_pr_create:
        head_branch_result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        if head_branch_result is None or head_branch_result.returncode != 0:
            return False
        current_branch = head_branch_result.stdout.strip()

        files = _changed_files_for_pr(current_branch)
        if files is None:
            staged = _run_git(["diff", "--cached", "--name-only"])
            if staged is None or staged.returncode != 0:
                return False
            files = [f.strip() for f in staged.stdout.strip().split("\n") if f.strip()]
    else:
        staged = _run_git(["diff", "--cached", "--name-only"])
        if staged is None or staged.returncode != 0:
            return False
        files = [f.strip() for f in staged.stdout.strip().split("\n") if f.strip()]

    if not files:
        return False
    return all(f.endswith(".md") for f in files)


def _has_verification_evidence(session_log: Path) -> bool:
    """Check session log for test/build verification evidence.

    Streams the log line-by-line and returns on first match so a large
    session log does not balloon hook memory. This blocking PreToolUse
    gate runs on every gated commit/PR-create, so the memory and I/O
    cost matters in the hot path.

    Args:
        session_log: Path to the session log file. Caller must ensure
            this is not None.
    """
    try:
        with session_log.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                for pattern in VERIFICATION_PATTERNS:
                    if pattern.search(line):
                        return True
    except OSError:
        return False
    return False


def _write_audit_log(project_dir: str, command: str, decision: str, reason: str) -> None:
    """Write audit entry for false completion gate decisions."""
    try:
        audit_dir = Path(project_dir) / ".agents" / ".hook-state"
        audit_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        timestamp = datetime.now(tz=UTC).isoformat()
        audit_file = audit_dir / f"false-completion-gate-{today}.log"

        # Truncate command for audit (avoid huge log entries)
        cmd_preview = command[:200] + "..." if len(command) > 200 else command

        with audit_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {decision}: {reason} | cmd: {cmd_preview}\n")
    except OSError:
        pass


def main() -> None:
    """Check for false completion claims without verification."""
    if skip_if_consumer_repo(HOOK_NAME):
        sys.exit(0)

    # Bypass via environment variable
    if os.environ.get("SKIP_COMPLETION_GATE", "").lower() == "true":
        sys.exit(0)

    hook_input = _read_stdin_json()
    if hook_input is None:
        sys.exit(0)

    command = _extract_command(hook_input)
    if not command:
        sys.exit(0)

    # Only gate on `git commit`/`git ci` and `gh pr create` commands.
    # The trailing boundary keeps neighbours like `git commit-tree` or
    # `gh pr create-checkout` from accidentally matching.
    is_commit = re.search(r"(?:^|\s)git\s+(commit|ci)(?:\s|$)", command)
    is_pr_create = re.search(r"(?:^|\s)gh\s+pr\s+create(?:\s|$)", command)
    if not is_commit and not is_pr_create:
        sys.exit(0)

    # Check if the command/message contains completion signals
    if not _is_completion_claim(command):
        sys.exit(0)

    project_dir = get_project_directory()

    # Bypass for documentation-only changes
    if _is_documentation_only(is_pr_create=bool(is_pr_create)):
        _write_audit_log(project_dir, command, "ALLOW", "documentation-only changes")
        sys.exit(0)

    # Check for verification evidence in session log
    sessions_dir = str(Path(project_dir) / ".agents" / "sessions")
    session_log = get_today_session_log(sessions_dir)

    # Fail-open when no session log exists
    if session_log is None:
        _write_audit_log(project_dir, command, "ALLOW", "no session log (fail-open)")
        sys.exit(0)

    if _has_verification_evidence(session_log):
        _write_audit_log(project_dir, command, "ALLOW", "verification evidence found")
        sys.exit(0)

    # Block: completion claim without verification
    _write_audit_log(project_dir, command, "BLOCK", "completion claim without verification")

    block_response = json.dumps({
        "decision": "block",
        "reason": (
            "⛔ FALSE COMPLETION GATE: You claimed completion "
            "(done/fixed/complete/etc.) but no verification evidence "
            "(test run, build check, PR checks) was found in the session log. "
            "Run tests or build verification before claiming completion."
        ),
    })
    print(block_response)
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Fail-open on unexpected errors
        print(f"[WARNING] {HOOK_NAME} error: {exc}", file=sys.stderr)
        sys.exit(0)
