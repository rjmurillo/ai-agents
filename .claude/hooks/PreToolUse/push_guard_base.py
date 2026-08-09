#!/usr/bin/env python3
"""Shared framework for pre-push guard hooks.

Provides one public entry point: :func:`run_guard`. Hooks call it with a
validator function, the path globs that activate them, and a short name
used in log lines and error codes. The framework owns:

- bootstrap of ``hook_utilities``
- consumer-repo skip
- stdin parsing (with size cap)
- ``git diff --name-only @{push}..HEAD`` with a fallback chain that
  prefers the per-branch upstream (``@{u}``) and only falls through to
  ``refs/remotes/origin/HEAD`` (typically ``origin/main``) when no
  upstream is set; ``origin/main`` is the literal last resort. See
  ``_detect_default_base_ref`` for the rationale.
- glob filtering (single-segment via fnmatch, multi-segment via prefix
  plus suffix string check; see issue 1884 pre-mortem R-E)
- structured stdout block on violation
- a machine-parseable ``EVENT=<json>`` line on stderr for every block
- configurable infrastructure error handling

Hook Type: PreToolUse

Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Allow (no matching files or validator clean)
    2 = Block (validator returned violations, strict infrastructure failure,
        or bootstrap failure)

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

Customer-facing verifiers pass ``project_only=False`` and
``fail_closed=True``. Internal advisory guards can retain the defaults.

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
import shlex
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
_lib_dir: str | None = None
if _plugin_root:
    _lib_dir = str(Path(_plugin_root).resolve() / "lib")
else:
    _cur = Path(__file__).resolve().parent
    while True:
        if (_cur / ".claude-plugin" / "plugin.json").is_file():
            _lib_dir = str(_cur / "lib")
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
if _lib_dir is None or not os.path.isdir(_lib_dir):
    print(
        f"Plugin lib directory not found: {_lib_dir} "
        f"(CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities import get_project_directory  # noqa: E402
from hook_utilities.guards import skip_if_consumer_repo  # noqa: E402

# Re-export for sibling guards that delegate plugin path resolution to
# _bootstrap. They import via this module so the static path-resolution
# tests (ADR-047) recognize the canonical pattern.
#
# ``emit_fail_open`` (the public alias of ``_emit_fail_open``) lets
# guard-level fail-open paths emit the same structured EVENT line that
# the framework emits on its own fail-open paths. Without it, the
# telemetry pipeline cannot distinguish "guard ran clean" from "guard
# silently bypassed because gh/markdownlint/etc. was missing".
__all__ = ["run_guard", "get_project_directory", "emit_fail_open"]

GIT_DIFF_TIMEOUT = 10

# ---------------------------------------------------------------------------
# Trusted git resolution (defect #2 mitigation)
# ---------------------------------------------------------------------------
# Well-known system directories where git is installed by the OS or
# package manager.  Inherited PATH is never consulted -- a consumer can
# place a hostile ``git`` anywhere on PATH and the denylist cannot
# enumerate every possible wrapper location.
_SYSTEM_GIT_DIRS: tuple[str, ...] = (
    # Linux / generic Unix
    "/usr/bin",
    "/usr/local/bin",
    # macOS Homebrew (Apple Silicon + Intel)
    "/opt/homebrew/bin",
    "/usr/local/Cellar",
    # macOS Xcode / CLT
    "/Library/Developer/CommandLineTools/usr/bin",
    "/Applications/Xcode.app/Contents/Developer/usr/bin",
)
_WINDOWS_GIT_DIRS: tuple[str, ...] = (
    r"C:\Program Files\Git\cmd",
    r"C:\Program Files (x86)\Git\cmd",
    r"C:\Program Files\Git\bin",
)

# Environment variables that can redirect git behavior to attacker code.
_GIT_DANGEROUS_ENV = frozenset({
    "GIT_EXEC_PATH", "GIT_EXTERNAL_DIFF", "GIT_DIFF_OPTS",
    "GIT_SSH_COMMAND", "GIT_ASKPASS", "GIT_EDITOR",
    "GIT_PAGER", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
    "GIT_CONFIG_NOSYSTEM", "GIT_ATTR_NOSYSTEM",
})


def _resolve_trusted_git() -> str:
    """Return absolute path to a system-installed git binary.

    Searches only well-known OS/package-manager directories.  Never
    consults inherited PATH.  Validates that the resolved real path
    also lives under a trusted prefix (guards against symlink attacks).
    On POSIX, additionally checks root ownership (uid 0).
    """
    name = "git.exe" if sys.platform == "win32" else "git"
    dirs = _WINDOWS_GIT_DIRS if sys.platform == "win32" else _SYSTEM_GIT_DIRS
    trusted_prefixes = tuple(dirs)

    for d in dirs:
        candidate = os.path.join(d, name)
        if not os.path.isfile(candidate):
            continue
        if not os.access(candidate, os.X_OK):
            continue
        # Resolve symlinks and verify the target is also under a
        # trusted prefix (prevents /usr/bin/git -> /tmp/evil/git).
        resolved = os.path.realpath(candidate)
        if not any(resolved.startswith(tp) for tp in trusted_prefixes):
            continue
        # POSIX: require root ownership.
        if sys.platform != "win32":
            try:
                st = os.stat(resolved)
            except OSError:
                continue
            if st.st_uid != 0:
                continue
        return resolved

    raise FileNotFoundError(
        "no system git found in trusted directories: "
        + ", ".join(dirs)
    )


def _scrubbed_git_env() -> dict[str, str]:
    """Return os.environ minus dangerous GIT_* and PYTHON* variables."""
    return {
        k: v
        for k, v in os.environ.items()
        if k not in _GIT_DANGEROUS_ENV
        and not k.startswith("PYTHON")
    }


# Resolved once at import time; guards fail closed if untrusted.
try:
    _TRUSTED_GIT: str | None = _resolve_trusted_git()
except FileNotFoundError:
    _TRUSTED_GIT = None


# Cap stdin read so a malicious or buggy upstream cannot OOM the hook
# (CWE-400). Real Claude Code tool_input commands are well below 1 MiB.
MAX_STDIN_BYTES = 1_048_576

# Match git push at the start of the command, with any whitespace
# between ``git`` and ``push``. The Copilot shim collapses runs of
# whitespace before matching ``Bash(git push*)``, so the literal prefix
# ``git push`` is too strict. ``re.match`` anchors at the start, but
# accept optional leading whitespace too for robustness.
_GIT_PUSH_RE = re.compile(r"\s*git\s+push(\s|$)")
_SAFE_PUSH_OPTIONS = {
    "--atomic",
    "--dry-run",
    "--force-with-lease",
    "--force-if-includes",
    "--no-signed",
    "--porcelain",
    "--quiet",
    "--signed",
    "--signed=false",
    "--signed=if-asked",
    "--signed=true",
    "--verbose",
    "-q",
    "-v",
}
_SHELL_EXPANSION_RE = re.compile(r"[\n\r`$;&|<>()*?\[\]{}\\!]")


class _HookInputError(ValueError):
    """Raised when a strict guard receives an invalid hook payload."""


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


def _validate_strict_push_command(command: str, cwd: str) -> None:
    """Reject push forms whose outgoing commit set cannot be determined safely."""
    if _SHELL_EXPANSION_RE.search(command):
        raise _HookInputError(
            "strict push guards do not allow shell expansion or control syntax"
        )
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise _HookInputError(f"unparseable git push command: {exc}") from exc

    if len(tokens) < 2 or tokens[:2] != ["git", "push"]:
        raise _HookInputError("command is not a direct git push")

    arguments = [
        token
        for token in tokens[2:]
        if token not in _SAFE_PUSH_OPTIONS
    ]
    if not arguments:
        return

    remote, branch = _strict_push_target(cwd)
    allowed_targets = ([remote, branch], [remote, f"HEAD:{branch}"])
    if arguments in allowed_targets:
        return

    rendered = " ".join(arguments)
    raise _HookInputError(
        "strict push guards require the configured push target; "
        f"unsupported arguments: {rendered}. Use git push."
    )


def _git_config_values(cwd: str, key: str) -> list[str]:
    rc, out = _run_git_diff(["git", "config", "--get-all", key], cwd=cwd)
    if rc == 1:
        return []
    if rc != 0:
        raise _HookInputError(f"could not read git config {key}: {out}")
    return [line for line in out.splitlines() if line.strip()]


def _git_config_bool(cwd: str, key: str) -> bool:
    rc, out = _run_git_diff(["git", "config", "--bool", "--get", key], cwd=cwd)
    if rc == 1:
        return False
    if rc != 0:
        raise _HookInputError(f"could not read git config {key}: {out}")
    value = out.strip()
    if value not in {"false", "true"}:
        raise _HookInputError(f"git config {key} is not boolean: {value}")
    return value == "true"


def _strict_push_remote(cwd: str, branch: str) -> str:
    for key in (
        f"branch.{branch}.pushRemote",
        "remote.pushDefault",
        f"branch.{branch}.remote",
    ):
        values = _git_config_values(cwd, key)
        if values:
            return values[-1]

    rc, out = _run_git_diff(["git", "remote"], cwd=cwd)
    if rc != 0:
        raise _HookInputError(f"could not list git remotes: {out}")
    remotes = [line for line in out.splitlines() if line.strip()]
    if "origin" in remotes:
        return "origin"
    if len(remotes) == 1:
        return remotes[0]
    raise _HookInputError("bare git push has no unambiguous push remote")


def _strict_push_target(cwd: str) -> tuple[str, str]:
    """Return the configured push remote and current branch."""
    rc, branch = _run_git_diff(["git", "branch", "--show-current"], cwd=cwd)
    branch = branch.strip()
    if rc != 0 or not branch:
        raise _HookInputError("bare git push requires an attached branch")

    push_defaults = _git_config_values(cwd, "push.default")
    push_default = push_defaults[-1] if push_defaults else "simple"
    if push_default not in {"current", "simple", "upstream"}:
        raise _HookInputError(
            "strict push guards require push.default=current, simple, or upstream; "
            f"found {push_default}"
        )

    return _strict_push_remote(cwd, branch), branch


def _validate_strict_push_configuration(cwd: str) -> None:
    """Require a current-branch-only bare push configuration."""
    remote, _branch = _strict_push_target(cwd)
    if remote == ".":
        raise _HookInputError("strict push guards do not support remote '.'")
    refspecs = _git_config_values(cwd, f"remote.{remote}.push")
    if refspecs:
        raise _HookInputError(
            f"strict push guards do not support remote.{remote}.push refspecs"
        )
    for key in (f"remote.{remote}.mirror", "push.followTags"):
        if _git_config_bool(cwd, key):
            raise _HookInputError(f"strict push guards require {key}=false")

    recurse_values = _git_config_values(cwd, "push.recurseSubmodules")
    if recurse_values:
        recurse = recurse_values[-1]
        if recurse not in {"check", "false", "no"}:
            raise _HookInputError(
                "strict push guards require "
                f"push.recurseSubmodules=no or check; found {recurse}"
            )
    elif _git_config_bool(cwd, "submodule.recurse"):
        raise _HookInputError(
            "strict push guards require submodule.recurse=false "
            "when push.recurseSubmodules is unset"
        )


def _run_git_diff(args: list[str], cwd: str) -> tuple[int, str]:
    if _TRUSTED_GIT is None:
        return 1, "git not found or resolved to untrusted location"
    # Replace bare 'git' with absolute trusted path.
    resolved_args = [_TRUSTED_GIT if a == "git" else a for a in args]
    try:
        proc = subprocess.run(
            resolved_args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GIT_DIFF_TIMEOUT,
            shell=False,
            check=False,
            env=_scrubbed_git_env(),
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
    fail_closed: bool = False,
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
    outcome = "blocking push" if fail_closed else "allowing push (fail-open)"
    print(
        f"[{name}] git diff failed on both refs; {outcome}. "
        f"primary=@{{push}}..HEAD: {primary_reason}; "
        f"fallback={fallback_ref}...HEAD: {fallback_reason}",
        file=sys.stderr,
    )
    if not fail_closed:
        _emit_fail_open(
            name,
            "diff_failed",
            f"primary: {primary_reason}; fallback: {fallback_reason}",
        )
    return None


_GH_TIMEOUT = 5


def _gh_base_ref(cwd: str) -> str | None:
    """Return ``origin/<baseRefName>`` for the open PR, or None.

    When a PR exists for the current branch, ``baseRefName`` is the
    ground truth. This handles the derivative-PR case where the user
    has not run ``git push -u`` yet but the PR is already opened
    against a non-default base. Fail-open semantics: any gh failure
    (missing CLI, no PR, auth, network) returns None and the caller
    falls through to the next signal in the chain.
    """
    import shutil  # local import to keep top-level imports minimal

    if shutil.which("gh") is None:
        return None
    try:
        proc = subprocess.run(
            ["gh", "pr", "view", "--json", "baseRefName", "-q", ".baseRefName"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT,
            shell=False,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if proc.returncode != 0:
        return None
    base = proc.stdout.strip()
    if not base:
        return None
    return f"origin/{base}"


def _detect_default_base_ref(cwd: str) -> str:
    """Resolve the right base ref to diff against when ``@{push}`` is unset.

    The fallback hierarchy mirrors what a careful engineer would inspect by
    hand:

    1. The PR's actual ``baseRefName`` via ``gh pr view``. This is the
       ground truth once a PR exists and handles the derivative-PR case
       where the user has not run ``git push -u`` yet but the PR is
       already opened against a non-default base. Fail-open: any gh
       failure (missing CLI, no PR, auth, network) falls to step 2.
    2. The current branch's configured upstream (``@{u}``). When the user
       has set tracking explicitly (``git push -u``,
       ``git branch --set-upstream-to=...``), this is the right answer
       for both mainline branches and derivative branches before the PR
       exists. Hardcoding ``origin/main`` here would pull in the parent
       branch's history.
    3. The remote's default branch via ``refs/remotes/origin/HEAD``. The
       documented "what does the remote consider default" answer for a
       brand-new feature branch with no upstream and no PR yet.
    4. ``origin/main`` as a last-resort literal so a misconfigured clone
       still produces a sensible (if imperfect) reference.
    """
    pr_base = _gh_base_ref(cwd)
    if pr_base:
        return pr_base
    rc, out = _run_git_diff(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        cwd=cwd,
    )
    if rc == 0:
        ref = out.strip()
        # rev-parse prints "@{upstream}" or "HEAD@{upstream}" verbatim when
        # no upstream is set; filter that out so we do not feed an
        # unresolvable ref to git diff. The filter targets the literal
        # ``@{`` token that only appears in the unresolved form, NOT a bare
        # ``@`` (git refnames legitimately permit ``@`` in branch names like
        # ``origin/release@v2``). Defense in depth: while modern git returns
        # rc != 0 on unresolved upstream, some older versions and edge
        # configurations have been observed to return rc=0 with the literal
        # token; the regression test
        # ``test_fallback_ignores_unresolved_upstream_token`` locks this in.
        if ref and "@{" not in ref:
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


def _read_stdin_command(name: str, fail_closed: bool = False) -> str | None:
    """Parse the tool command from hook stdin, or return None.

    Fail-open with telemetry: every anomalous stdin shape (oversize, unparseable
    JSON, non-object payload, missing/mistyped tool_input, missing/mistyped
    command) emits a structured ``EVENT=...`` fail-open line via _emit_fail_open
    and still returns None, preserving the framework's documented allow-but-observe
    contract (see the module docstring, "Operations and telemetry"). Interactive
    stdin is always a no-op. Empty non-interactive stdin is a no-op for advisory
    guards and invalid input for strict guards.
    """
    if sys.stdin.isatty():
        return None
    def invalid(detail: str) -> None:
        if fail_closed:
            raise _HookInputError(detail)
        _emit_fail_open(name, "bad_stdin", detail)

    raw = sys.stdin.read(MAX_STDIN_BYTES + 1)
    if len(raw) > MAX_STDIN_BYTES:
        invalid(f"stdin exceeds {MAX_STDIN_BYTES} bytes")
        return None
    if not raw.strip():
        if fail_closed:
            invalid("stdin empty")
        return None
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        invalid(f"unparseable JSON: {type(exc).__name__}")
        return None
    if not isinstance(payload, dict):
        invalid("payload not a JSON object")
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        invalid("tool_input missing/not object")
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        invalid("command missing/not non-empty string")
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


# Public alias so guard-level fail-open paths (markdownlint binary
# missing, gh CLI missing, gh timeout, ...) can emit the same EVENT
# shape the framework uses for its own fail-open paths. Without a
# stable public name, callers would have to reach into the leading-
# underscore symbol, which the linter and reviewers flag as a private
# import.
emit_fail_open = _emit_fail_open


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
    *,
    project_only: bool = True,
    fail_closed: bool = False,
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
        project_only: Skip outside the ai-agents repository when ``True``.
        fail_closed: Block when hook input, Git state, or validation fails.

    Returns:
        Exit code: 0 to allow, 2 to block.
    """
    if project_only and skip_if_consumer_repo(name):
        return 0
    try:
        command = _read_stdin_command(name, fail_closed=fail_closed)
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
        if fail_closed:
            _validate_strict_push_command(command, project_dir)
            _validate_strict_push_configuration(project_dir)
        all_changed = _changed_files(
            project_dir,
            name=name,
            include_deletions=include_deletions,
            fail_closed=fail_closed,
        )
        if all_changed is None:
            if fail_closed:
                _emit_violations(
                    name,
                    ["Guard could not determine changed files."],
                    0,
                    0,
                )
                return 2
            return 0

        matching = _filter_by_globs(all_changed, globs)
        if not matching:
            return 0

        violations = validator_fn(matching, all_changed)
        if not violations:
            return 0

        _emit_violations(name, violations, len(matching), len(all_changed))
        return 2

    except _HookInputError as exc:
        _emit_violations(name, [f"Guard received invalid hook input: {exc}"], 0, 0)
        return 2
    except Exception as exc:
        if fail_closed:
            _emit_violations(
                name,
                [f"Guard infrastructure failure: {type(exc).__name__}: {exc}"],
                0,
                0,
            )
            return 2
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
