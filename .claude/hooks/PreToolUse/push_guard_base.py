#!/usr/bin/env python3
"""Shared framework for pre-push guard hooks.

Provides one public entry point: :func:`run_guard`. Hooks call it with a
validator function, the path globs that activate them, and a short name
used in log lines and error codes. The framework owns:

- bootstrap of ``hook_utilities``
- consumer-repo skip
- stdin parsing (with size cap)
- ``git diff --name-only @{push}..HEAD`` with ``origin/main...HEAD``
  fallback
- glob filtering (single-segment via fnmatch, multi-segment via prefix
  plus suffix string check; see issue 1884 pre-mortem R-E)
- structured stdout block on violation
- a machine-parseable ``EVENT=<json>`` line on stderr for every block
- fail-open on infrastructure errors

Hook Type: PreToolUse

Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (no matching files, validator clean, infra fallback)
    2 = Block (validator returned violations OR bootstrap failed)

Bootstrap failures (missing plugin lib) exit 2, NOT fail-open. A guard
that cannot find its lib is a hard misconfiguration; allowing pushes
silently in that state would defeat the framework. This is the only
non-fail-open path.

Naming convention:
    The ``name`` argument becomes ``E_<NAME_UPPER>`` in the error code,
    with hyphens converted to underscores. Examples:
        name="markdown-lint"  -> E_MARKDOWN_LINT
        name="manifest-count" -> E_MANIFEST_COUNT
        name="session-log"    -> E_SESSION_LOG

When NOT to use this framework:
    - PostToolUse hooks (different hook semantics).
    - Hooks that do not consult ``git diff`` (this framework is push-time
      specific).
    - Hooks that need different exit code semantics (e.g., must always
      block on infrastructure errors). Those should compose differently
      or stay self-contained.
"""

from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

# Bootstrap: find lib directory via env var or manifest walk-up.
# CLAUDE_PLUGIN_ROOT honored when set; otherwise walk up from __file__
# looking for .claude-plugin/plugin.json (the plugin marker). Sibling
# lib/ is the plugin's lib dir. Layout-independent: works in source
# tree (.claude/) and in the deeper src/<provider>/hooks/<event>/ copy.
_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _cur = Path(__file__).resolve().parent
    _lib_dir = None
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir} (CLAUDE_PLUGIN_ROOT={_plugin_root!r})", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import get_project_directory  # noqa: E402
from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402

GIT_DIFF_TIMEOUT = 10

# Cap stdin read so a malicious or buggy upstream cannot OOM the hook
# (CWE-400). Real Claude Code tool_input commands are well below 1 MiB.
MAX_STDIN_BYTES = 1_048_576


def _match_glob(path: str, pattern: str) -> bool:
    """Match path against a glob pattern.

    Two distinct shapes by design:

    1. Single-segment patterns (no /): use fnmatch. ``*.md`` matches any
       ``.md`` file at any depth (e.g., ``foo.md`` and ``a/b/c.md`` both
       match). This is the right semantics for whole-tree validators
       like markdownlint.

    2. Multi-segment patterns (contains /): use prefix+suffix matching
       with the ``*`` constrained to a single path segment. ``.claude/skills/*/SKILL.md``
       matches ``.claude/skills/foo/SKILL.md`` but NOT
       ``.claude/skills/foo/bar/SKILL.md``. This is the right semantics
       for structured-tree validators like manifest count.

    fnmatch and pathlib.match both fail to anchor ``*`` to a single
    segment, which is why multi-segment patterns are handled manually.
    See issue 1884 pre-mortem R-E.

    The two shapes match different intents on purpose. Callers should
    pick the shape that matches their semantics: simple suffix matching
    via ``*.ext`` for "anywhere in the tree", or full prefix+single-segment
    matching for "exact directory structure".
    """
    if "/" not in pattern:
        return fnmatch.fnmatch(path, pattern)
    star_count = pattern.count("*")
    if star_count != 1:
        return fnmatch.fnmatch(path, pattern)
    prefix, suffix = pattern.split("*", 1)
    if not path.startswith(prefix):
        return False
    if not path.endswith(suffix):
        return False
    if len(path) < len(prefix) + len(suffix):
        return False
    middle = path[len(prefix):len(path) - len(suffix)] if suffix else path[len(prefix):]
    if "/" in middle:
        return False
    return True


def _filter_by_globs(paths: list[str], globs: list[str]) -> list[str]:
    matched: list[str] = []
    for path in paths:
        for pattern in globs:
            if _match_glob(path, pattern):
                matched.append(path)
                break
    return matched


def _run_git_diff(args: list[str], cwd: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GIT_DIFF_TIMEOUT,
            shell=False,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return proc.returncode, proc.stdout


def _changed_files(cwd: str, name: str = "guard") -> list[str] | None:
    """Return added/modified files committed but not yet pushed.

    Uses ``git diff --name-only --diff-filter=AM @{push}..HEAD`` so deleted
    files are excluded (validators read files; missing paths would raise
    FileNotFoundError). Falls back to ``origin/main...HEAD`` ONLY when the
    primary command fails (non-zero exit, e.g., no upstream tracking).

    A successful primary command with empty output means "nothing committed
    beyond the remote tip" and is returned as an empty list. Falling back to
    ``origin/main...HEAD`` in that case would reintroduce all branch history
    and trip validators on previously-pushed work.

    Returns:
        - List of A/M paths (possibly empty) when the diff command succeeded.
        - None only when both the primary and the fallback commands failed.
    """
    # ACMR includes Add/Copy/Modify/Rename so renamed files are still
    # validated (their new path is on disk and should be checked).
    # Excludes only Deleted and Type-change so validators do not see
    # paths that vanished. See PR #1887 review round 2.
    args = ["--name-only", "--diff-filter=ACMR"]
    rc, out = _run_git_diff(["git", "diff", *args, "@{push}..HEAD"], cwd=cwd)
    if rc == 0:
        return [line for line in out.splitlines() if line.strip()]
    primary_reason = out.splitlines()[0] if out else "non-zero exit"
    rc2, out2 = _run_git_diff(
        ["git", "diff", *args, "origin/main...HEAD"], cwd=cwd
    )
    if rc2 == 0:
        return [line for line in out2.splitlines() if line.strip()]
    fallback_reason = out2.splitlines()[0] if out2 else "non-zero exit"
    print(
        f"[{name}] git diff failed on both refs; allowing push (fail-open). "
        f"primary=@{{push}}..HEAD: {primary_reason}; "
        f"fallback=origin/main...HEAD: {fallback_reason}",
        file=sys.stderr,
    )
    return None


def _read_stdin_command() -> str | None:
    if sys.stdin.isatty():
        return None
    raw = sys.stdin.read(MAX_STDIN_BYTES + 1)
    if len(raw) > MAX_STDIN_BYTES:
        return None
    if not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return None
    return command


def _emit_violations(
    name: str,
    violations: list[str],
    matching_count: int,
    all_changed_count: int,
) -> None:
    code = name.upper().replace("-", "_")
    header = f"\n## BLOCKED [E_{code}]: {name}\n"
    body = "\n".join(violations)
    footer = "\nFix and re-push.\n"
    print(f"{header}\n{body}\n{footer}")
    print(
        f"[E_{code}] {name} blocked: {len(violations)} violation(s) "
        f"matched={matching_count}/{all_changed_count} files",
        file=sys.stderr,
    )
    event = {
        "guard": name,
        "code": f"E_{code}",
        "outcome": "block",
        "violations": len(violations),
        "matched_files": matching_count,
        "changed_files": all_changed_count,
    }
    print(f"EVENT={json.dumps(event, separators=(',', ':'))}", file=sys.stderr)


def run_guard(
    validator_fn: Callable[[list[str], list[str]], list[str]],
    globs: list[str],
    name: str,
) -> int:
    """Execute a pre-push guard.

    Args:
        validator_fn: Called as ``validator_fn(matching_files, all_changed)``.
            Returns a list of violation lines. Empty list means clean.
        globs: Path patterns that activate the validator.
        name: Short guard name. Becomes ``E_<NAME_UPPER>`` in error code.

    Returns:
        Exit code: 0 to allow, 2 to block.
    """
    if skip_if_consumer_repo(name):
        return 0
    try:
        command = _read_stdin_command()
        if command is None:
            return 0
        # Defense in depth: even when the harness matcher is `Bash(git push*)`,
        # confirm the command shape before doing any work. A misregistered
        # matcher or a future change in matcher semantics should not turn this
        # framework into a generic Bash interceptor.
        if not command.lstrip().startswith("git push"):
            return 0

        project_dir = get_project_directory()
        all_changed = _changed_files(project_dir, name=name)
        if all_changed is None:
            return 0

        matching = _filter_by_globs(all_changed, globs)
        if not matching:
            return 0

        violations = validator_fn(matching, all_changed)
        if not violations:
            return 0

        _emit_violations(name, violations, len(matching), len(all_changed))
        return 2

    except Exception as exc:
        print(
            f"{name} guard error: {type(exc).__name__}: {exc}; "
            f"check validator implementation and changed-file paths. "
            f"Allowing push (fail-open).",
            file=sys.stderr,
        )
        return 0


def main() -> int:
    """Entry point when invoked directly.

    The base module has no validator of its own; running it without a
    concrete guard is a misconfiguration. Fail-open with a stderr note.
    """
    print(
        "push_guard_base.py is a framework module; invoke a concrete guard "
        "instead. Allowing push (fail-open).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
