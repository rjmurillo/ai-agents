#!/usr/bin/env python3
"""Block Serena memory mutations aimed at a checkout other than the caller's.

Issue #5061: a subagent running inside a git worktree called
``mcp__serena__write_memory``. The Serena MCP server resolves its memory
directory from the project it was started with (``.mcp.json`` starts it with
``--project ${workspaceFolder:-.}``), not from the caller's cwd, so the file
landed in the main checkout's ``.serena/memories/`` tree. The memory was
invisible to the subagent's own branch, and the subagent silently modified a
working tree it was supposed to be isolated from.

Why this guard is not covered by the guard proposed for issue #4917
(PR #5036, ``.claude/hooks/PreToolUse/invoke_serena_worktree_scope_guard.py``
on branch ``fix/4917-serena-worktree-scope``, commit 96521be). That guard
declares, verbatim:

    _WRITE_TOOLS: frozenset[str] = frozenset(
        {
            "serena-replace_content",
            "serena-replace_symbol_body",
            "serena-insert_before_symbol",
            "serena-insert_after_symbol",
            "serena-replace_in_files",
            "serena-safe_delete_symbol",
            "serena-rename_symbol",
        }
    )

and registers on ``"matcher": "^serena-"`` in
``.claude/hooks/dispatch_groups.json``. Two gaps follow. The tool set holds no
memory tool, so ``write_memory`` and ``delete_memory`` pass it unexamined. And
``^serena-`` is the Copilot CLI tool naming; Claude Code names the same server's
tools ``mcp__serena__*``, which this repository already relies on at
``.claude/settings.json`` (``"matcher": "mcp__serena__write_memory"`` on the
observation-sync PostToolUse entry). This guard therefore matches both namings.

Different than that guard: it gates memory tools only, and it names the
in-worktree write path in its block message, because a memory write is
addressed by name rather than by path and so gives the caller no path-level
signal that the target sits in another checkout.

Hook Type: PreToolUse
Matcher: mcp__serena__(write|delete)_memory|serena-(write|delete)_memory

Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (unrelated tool, scope matches, or caller is not in a git repo)
    2 = Block (memory mutation whose target checkout is not the caller's)

Fail-closed for mutations whose session root cannot be resolved, whose caller
worktree cannot be resolved (git failed to launch, timed out, or returned
unusable output), or whose stdin payload was too large to parse safely: each
is a state in which a stray write cannot be ruled out. Fail-open only when
git ran and confirmed the caller is not inside any git worktree at all,
because no worktree isolation claim exists to violate there.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_MAX_STDIN_BYTES = 128 * 1024
_GIT_TIMEOUT_SECONDS = 5

# Serena tools that mutate the activated project's .serena/memories/ tree.
# Both harness namings: Claude Code exposes MCP tools as mcp__<server>__<tool>,
# Copilot CLI as <server>-<tool>.
_MEMORY_WRITE_TOOLS: frozenset[str] = frozenset(
    {
        "mcp__serena__write_memory",
        "mcp__serena__delete_memory",
        "serena-write_memory",
        "serena-delete_memory",
    }
)

_OVERRIDE_ENV = "SERENA_PROJECT_ROOT"
_SESSION_ENV = "CLAUDE_PROJECT_DIR"


class _GitUnresolvableError(Exception):
    """Raised when git could not be run at all (not when it ran and said no).

    A caller genuinely outside any git repository gets a clean nonzero
    ``git`` exit; that is a real answer, not an unresolvable state. A
    launch failure, a timeout, or an unreadable result tells us nothing
    about whether the caller is inside a worktree, so it cannot be treated
    the same as a confirmed "not in a repo" answer.
    """


def _git_toplevel(start: Path) -> Path | None:
    """Return the git worktree root containing *start*, or None.

    Raises :class:`_GitUnresolvableError` when ``git`` could not be launched, hit
    its timeout, or returned output we could not resolve, so a caller that
    needs to distinguish "confirmed outside a repo" from "we do not know"
    can fail closed on the latter instead of silently allowing it.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise _GitUnresolvableError(str(error)) from error
    if result.returncode != 0:
        return None
    toplevel = result.stdout.strip()
    if not toplevel:
        raise _GitUnresolvableError("git rev-parse --show-toplevel returned no output")
    try:
        return Path(toplevel).resolve()
    except OSError as error:
        raise _GitUnresolvableError(str(error)) from error


def _resolved_dir(raw: str) -> Path | None:
    """Resolve *raw* to an existing directory, or None."""
    candidate = raw.strip()
    if not candidate or "\x00" in candidate:
        return None
    try:
        path = Path(candidate).expanduser().resolve()
    except (OSError, RuntimeError):
        return None
    return path if path.is_dir() else None


def _serena_memory_root() -> Path | None:
    """Return the checkout whose .serena/memories/ tree Serena actually writes.

    The Serena server binds its project once, at start. ``SERENA_PROJECT_ROOT``
    is the operator's explicit statement of that binding after a re-activation;
    otherwise the session's own project dir is the best available proxy, since
    ``.mcp.json`` starts the server with the session workspace folder.
    """
    override = _resolved_dir(os.environ.get(_OVERRIDE_ENV, ""))
    if override is not None:
        try:
            return _git_toplevel(override) or override
        except _GitUnresolvableError:
            return override

    session_dir = _resolved_dir(os.environ.get(_SESSION_ENV, ""))
    if session_dir is not None:
        try:
            return _git_toplevel(session_dir)
        except _GitUnresolvableError:
            # An unresolvable git state here still yields no answer, and the
            # caller (main) already fails closed on a None memory root.
            return None

    return None


def _payload_cwd(payload: dict[str, object]) -> Path:
    """Return the caller's cwd from *payload*, falling back to this process."""
    raw = payload.get("cwd")
    if not isinstance(raw, str) or not raw.strip():
        return Path.cwd().resolve()
    candidate = Path(raw.strip())
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    try:
        return candidate.resolve()
    except (OSError, RuntimeError):
        return Path.cwd().resolve()


class _StdinTooLargeError(Exception):
    """Raised when the hook payload exceeds ``_MAX_STDIN_BYTES``.

    The read itself is already bounded (``read(_MAX_STDIN_BYTES + 1)``), so
    there is no unbounded-read risk in accepting a larger payload; the limit
    exists to bound JSON-parse cost. A payload this size cannot be reliably
    parsed to confirm it is unrelated to a memory write, and a large memory
    body is a realistic, more consequential case, not an edge case to wave
    through. Callers fail closed on this instead of the generic
    can't-parse-so-allow fallback.
    """


def _read_payload() -> tuple[str, Path]:
    """Return (tool_name, caller_cwd) from the hook stdin payload."""
    fallback = ("", Path.cwd().resolve())
    if sys.stdin.isatty():
        return fallback
    raw = sys.stdin.read(_MAX_STDIN_BYTES + 1)
    if len(raw) > _MAX_STDIN_BYTES:
        raise _StdinTooLargeError(f"payload exceeds {_MAX_STDIN_BYTES} bytes")
    if not raw.strip():
        return fallback
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return fallback
    if not isinstance(payload, dict):
        return fallback

    name = payload.get("tool_name") or payload.get("toolName") or ""
    if not isinstance(name, str):
        return fallback
    return name, _payload_cwd(payload)


def _block_message(worktree: Path, memory_root: Path) -> str:
    """Return the stderr guidance shown when a memory mutation is blocked."""
    return (
        "BLOCKED: Serena memory mutation would land outside your worktree "
        "(issue #5061).\n"
        f"  Your worktree:        {worktree}\n"
        f"  Serena memory target: {memory_root}\n"
        "The Serena server binds its project at start, so write_memory and "
        "delete_memory always resolve against the target above, not your cwd.\n"
        "Do one of:\n"
        f"  1. Write the file directly with the Write tool: "
        f"{worktree / '.serena' / 'memories'}/<name>.md\n"
        f"  2. Re-activate Serena for this worktree, then set "
        f"{_OVERRIDE_ENV}={worktree}\n"
    )


def main() -> int:
    """Entry point. Returns 0 (allow) or 2 (block)."""
    try:
        tool_name, caller_cwd = _read_payload()
    except _StdinTooLargeError as error:
        print(
            f"BLOCKED: cannot verify Serena memory scope (issue #5061): {error}. "
            "A payload this size cannot be confirmed unrelated to a memory "
            "write. Write the memory file directly with the Write tool, or "
            "retry with a smaller call.",
            file=sys.stderr,
        )
        return 2
    if tool_name not in _MEMORY_WRITE_TOOLS:
        return 0

    try:
        worktree = _git_toplevel(caller_cwd)
    except _GitUnresolvableError as error:
        print(
            "BLOCKED: could not determine your git worktree (issue #5061): "
            f"{error}. Set {_OVERRIDE_ENV} to your worktree, or write the "
            "memory file directly with the Write tool.",
            file=sys.stderr,
        )
        return 2
    if worktree is None:
        # git ran and confirmed the caller is not inside a git worktree at
        # all, so there is no isolation claim to violate. Fail open.
        return 0

    memory_root = _serena_memory_root()
    if memory_root is None:
        print(
            "BLOCKED: cannot determine which checkout Serena writes memories "
            f"to (issue #5061). Set {_OVERRIDE_ENV} to that checkout, or write "
            "the memory file directly with the Write tool.",
            file=sys.stderr,
        )
        return 2

    if worktree == memory_root:
        return 0

    print(_block_message(worktree, memory_root), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
