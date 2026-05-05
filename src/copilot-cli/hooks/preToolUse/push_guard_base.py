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

Operations and telemetry:
    Every block emits ``EVENT={...}`` to stderr with a fixed schema
    (``guard``, ``code``, ``outcome="block"``, ``violations``,
    ``matched_files``, ``changed_files``). Every fail-open path also emits
    ``EVENT={...}`` with ``outcome="fail_open"`` plus a ``reason`` and a
    free-form ``detail``. A telemetry pipeline that greps for ``^EVENT=``
    sees both classes of events; ratios of fail-opens to blocks are the
    primary signal that a guard is degraded. See PR #1887 and issue #1884
    for the behavior contract; a dedicated runbook is tracked as a
    follow-up.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
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

# Re-export for sibling guards that delegate plugin path resolution to
# _bootstrap. They import via this module so the static path-resolution
# tests (ADR-047) recognize the canonical pattern.
__all__ = ["run_guard", "get_project_directory"]

GIT_DIFF_TIMEOUT = 10

# Cap stdin read so a malicious or buggy upstream cannot OOM the hook
# (CWE-400). Real Claude Code tool_input commands are well below 1 MiB.
MAX_STDIN_BYTES = 1_048_576

# Match git push at the start of the command, with any whitespace
# between ``git`` and ``push``. The Copilot shim collapses runs of
# whitespace before matching ``Bash(git push*)``, so the literal prefix
# ``git push`` is too strict. ``re.match`` anchors at the start, but
# accept optional leading whitespace too for robustness.
_GIT_PUSH_RE = re.compile(r"\s*git\s+push(\s|$)")


def _match_double_star(path: str, pattern: str) -> bool:
    """Multi-segment pattern with ``/**/`` (e.g., ``.claude/hooks/**/*.py``).

    Path must start with the prefix; the tail is then matched against any
    contiguous sequence of segments in the remainder. Single-segment tails
    use a fast basename match; multi-segment tails use a sliding-window
    fnmatch over segment groups.
    """
    prefix, tail = pattern.split("/**/", 1)
    if not path.startswith(prefix + "/"):
        return False
    suffix = path[len(prefix) + 1:]
    if "/" not in tail:
        basename = suffix.rsplit("/", 1)[-1]
        return fnmatch.fnmatch(basename, tail)
    tail_parts = tail.split("/")
    suffix_parts = suffix.split("/")
    if len(suffix_parts) < len(tail_parts):
        return False
    for start in range(len(suffix_parts) - len(tail_parts) + 1):
        if all(
            fnmatch.fnmatch(suffix_parts[start + j], tail_parts[j])
            for j in range(len(tail_parts))
        ):
            return True
    return False


def _match_single_star_path(path: str, pattern: str) -> bool:
    """Multi-segment pattern with exactly one ``*`` (e.g., ``.claude/skills/*/SKILL.md``).

    The ``*`` is constrained to a single path segment via prefix+suffix
    matching with an overlap guard. fnmatch alone would let ``*`` cross
    path separators; pathlib.match has the same limitation.
    """
    prefix, suffix = pattern.split("*", 1)
    if not path.startswith(prefix) or not path.endswith(suffix):
        return False
    if len(path) < len(prefix) + len(suffix):
        return False
    middle = path[len(prefix):len(path) - len(suffix)] if suffix else path[len(prefix):]
    return "/" not in middle


def _match_glob(path: str, pattern: str) -> bool:
    """Match path against a glob pattern.

    Three shapes by design:

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
    if "/**/" in pattern:
        return _match_double_star(path, pattern)
    if pattern.count("*") != 1:
        return fnmatch.fnmatch(path, pattern)
    return _match_single_star_path(path, pattern)


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
    if proc.returncode != 0:
        # On non-zero, return stderr (where git writes "fatal: ..." messages)
        # so the caller can report the real cause instead of just "non-zero exit".
        msg = (proc.stderr or proc.stdout).strip() or "non-zero exit"
        return proc.returncode, msg
    return proc.returncode, proc.stdout


def _changed_files(
    cwd: str,
    name: str = "guard",
    include_deletions: bool = False,
) -> list[str] | None:
    """Return changed files committed but not yet pushed.

    Default filter is ``--diff-filter=ACMR`` (Add/Copy/Modify/Rename). Renames
    are included so the post-rename path reaches the validator. Deletions and
    type-changes are excluded so validators that read the file do not hit
    FileNotFoundError. Falls back to ``origin/main...HEAD`` ONLY when the
    primary command fails (non-zero exit, e.g., no upstream tracking).

    When ``include_deletions=True`` the filter becomes ``ACMRD`` so guards
    that need to fire on deletion-only pushes (e.g., the marketplace count
    guard, which derives counts from the filesystem regardless of the diff
    contents) still see those changes. Such guards must not read the listed
    paths, since deleted files are gone from the working tree.

    A successful primary command with empty output means "nothing committed
    beyond the remote tip" and is returned as an empty list. Falling back to
    ``origin/main...HEAD`` in that case would reintroduce all branch history
    and trip validators on previously-pushed work.

    Returns:
        - List of A/C/M/R paths (possibly empty) when the diff command succeeded.
        - None only when both the primary and the fallback commands failed.
    """
    # ACMR includes Add/Copy/Modify/Rename so renamed files are still
    # validated (their new path is on disk and should be checked).
    # Excludes Deleted and Type-change so validators do not see paths
    # that vanished. include_deletions=True opts back into ACMRD for
    # guards that fire on deletion-only pushes (PR #1887 review round 9).
    diff_filter = "ACMRD" if include_deletions else "ACMR"
    args = ["--name-only", f"--diff-filter={diff_filter}"]
    rc, out = _run_git_diff(["git", "diff", *args, "@{push}..HEAD"], cwd=cwd)
    if rc == 0:
        return [line for line in out.splitlines() if line.strip()]
    primary_reason = out.splitlines()[0] if out else "non-zero exit"
    fallback_ref = _detect_default_base_ref(cwd)
    rc2, out2 = _run_git_diff(
        ["git", "diff", *args, f"{fallback_ref}...HEAD"], cwd=cwd
    )
    if rc2 == 0:
        return [line for line in out2.splitlines() if line.strip()]
    fallback_reason = out2.splitlines()[0] if out2 else "non-zero exit"
    print(
        f"[{name}] git diff failed on both refs; allowing push (fail-open). "
        f"primary=@{{push}}..HEAD: {primary_reason}; "
        f"fallback={fallback_ref}...HEAD: {fallback_reason}",
        file=sys.stderr,
    )
    _emit_fail_open(name, "diff_failed", f"primary: {primary_reason}; fallback: {fallback_reason}")
    return None


def _detect_default_base_ref(cwd: str) -> str:
    """Resolve the right base ref to diff against when ``@{push}`` is unset.

    The fallback hierarchy mirrors what a careful engineer would inspect by
    hand:

    1. The current branch's configured upstream (``@{u}``). When the user has
       set tracking explicitly (``git branch --set-upstream-to=...``), this
       is the right answer for both mainline branches and *derivative PRs*
       that target a parent feature branch rather than ``main``. Hardcoding
       ``origin/main`` here would pull in the parent branch's history and
       fire guards on files that are not part of the outgoing push.
    2. The remote's default branch via ``refs/remotes/origin/HEAD``. This is
       the documented "what does the remote consider default" answer and
       handles the common case of a brand-new feature branch with no
       upstream set yet.
    3. ``origin/main`` as a last-resort literal so a misconfigured clone
       still produces a sensible (if imperfect) reference.
    """
    rc, out = _run_git_diff(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        cwd=cwd,
    )
    if rc == 0:
        ref = out.strip()
        # rev-parse prints "@{upstream}" verbatim when no upstream is set;
        # filter that out so we do not feed an unresolvable ref to git diff.
        if ref and "@" not in ref:
            return ref
    rc, out = _run_git_diff(
        ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        cwd=cwd,
    )
    if rc == 0:
        ref = out.strip()
        if ref:
            return ref
    return "origin/main"


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


def _emit_fail_open(name: str, reason: str, detail: str) -> None:
    """Emit a structured EVENT line when the framework allows a push without
    running (or completing) the validator. Pairs with the block-time EVENT
    so a telemetry pipeline can count fail-opens per guard per day; without
    this signal a hostile or buggy validator could silently allow every push.
    """
    code = name.upper().replace("-", "_")
    event = {
        "guard": name,
        "code": f"E_{code}",
        "outcome": "fail_open",
        "reason": reason,
        "detail": detail,
    }
    print(f"EVENT={json.dumps(event, separators=(',', ':'))}", file=sys.stderr)


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
    include_deletions: bool = False,
) -> int:
    """Execute a pre-push guard.

    Args:
        validator_fn: Called as ``validator_fn(matching_files, all_changed)``.
            Returns a list of violation lines. Empty list means clean.
        globs: Path patterns that activate the validator.
        name: Short guard name. Becomes ``E_<NAME_UPPER>`` in error code.
        include_deletions: When ``True``, the diff filter is ``ACMRD`` so
            deletion-only pushes still surface to the validator. Default
            ``False`` excludes deletions to protect validators that read
            the listed paths.

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
        #
        # The Copilot shim normalizes ``\s+`` to single space before matching
        # ``Bash(git push*)``, so a real command like ``git    push origin``
        # fires the wrapper. Match that normalization here: accept any
        # whitespace between ``git`` and ``push``, with optional leading
        # whitespace. Otherwise the wrapper fires but this short-circuits
        # to 0 and bypasses every guard.
        if not _GIT_PUSH_RE.match(command):
            return 0

        project_dir = get_project_directory()
        all_changed = _changed_files(
            project_dir, name=name, include_deletions=include_deletions
        )
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
        _emit_fail_open(name, "exception", f"{type(exc).__name__}: {exc}")
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
