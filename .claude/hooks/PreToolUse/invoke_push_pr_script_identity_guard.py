#!/usr/bin/env python3
# Standalone hook must carry its parser and policy into one generated shim.
# taste-lint: ignore file-size, splitting would break cross-harness parity.
# Parser branches preserve distinct lexical states and fail-closed reasons.
# taste-lint: ignore complexity, flattening would merge security decisions.
"""Deny noncanonical push-pr Python entrypoints (issue #4764).

Exit codes:
    0 = allow
    2 = block

Scope (relevance gate, issue #4825 review 4894113215)
-----------------------------------------------------
The host registers this guard on the plugin-wide ``Bash`` matcher, so it runs
on every Bash command. It therefore decides relevance BEFORE it decides policy.
``_command_is_in_scope`` runs first and returns 0 (allow, non-blocking) for any
command that cannot reach ``new_pr.py``. A command is in scope only when:

A. Its text names ``new_pr.py`` after line-continuation removal, quote,
   whitespace, ``+`` and backslash compaction, path-separator normalization,
   and bounded brace expansion; or
B. it is a Python invocation whose script operand carries shell expansion, so
   the guard cannot statically prove the operand is not ``new_pr.py``; or
C. one of its operands resolves to a regular file whose bytes match the trusted
   ``new_pr.py`` (a renamed copy).

Everything else, including ``git status && git diff``, ``bash -c``, Node, Perl,
unrelated Python scripts, ``python3 -m pytest`` and Git commands in a
repository with active hooks, is out of scope and passes untouched.

Residual risk (accepted, not a defect)
--------------------------------------
A command that reconstructs the path at runtime without naming it, for example
``python3 -c`` with a hex-decoded path or ``git clone ext::sh -c <payload>``
that never spells ``new_pr.py``, is outside the detection surface. This guard
bounds the identity of *named* push-pr invocations. It is not a Python or shell
sandbox: an actor able to run arbitrary code does not need ``new_pr.py`` to
open a pull request. Widening the scope to cover that case is what wedged every
unrelated Bash command, which is a larger, certain harm than the residual.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO, NamedTuple

_MAX_STDIN_BYTES = 128 * 1024
_SCRIPT_RELATIVE_PATH = Path("skills/github/scripts/pr/new_pr.py")
_PLUGIN_SCRIPT_REFERENCE = (
    "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/pr/new_pr.py"
)
_SHELL_EXPANSION_MARKERS = ("$", "`", "\\\n", "{", "[", "*", "?")
_INNERMOST_BRACE_GROUP = re.compile(r"\{([^{}]*)\}")
# Bash extglob group: one of ? * + @ ! immediately followed by a
# parenthesized alternation. Innermost only, so nesting is handled by repeated
# application rather than by a recursive pattern.
_EXTGLOB_GROUP = re.compile(r"([?*+@!])\(([^()]*)\)")
_COMMAND_SUBSTITUTION = re.compile(r"\$\([^()]*\)|`[^`]*`")
_NEW_PR_TARGET = "new_pr.py"
_ANSI_C_QUOTED = re.compile(r"\$'((?:[^'\\]|\\.)*)'")
_MAX_BRACE_EXPANSIONS = 4096
# Total bytes one relevance decision may materialize across all brace
# expansions. The count budget above cannot bound this: every expansion carries
# a copy of the surrounding literal text, so cost is count times length. Issue
# #4764 measured 204,832,768 bytes and a 195.6 MiB peak from a 100,060-byte
# command that never exceeded the count budget. 256 KiB leaves ordinary
# multi-alternative commands untouched while keeping a hostile 128 KiB command
# far from both the host's 10s PreToolUse timeout (where a Copilot timeout
# fails OPEN) and any meaningful RSS growth.
_MAX_BRACE_EXPANDED_BYTES = 256 * 1024
# Bound on innermost-first extglob rewrites, so a pathological nesting cannot
# loop. Far above any real command; the canonical invocation has none.
_MAX_EXTGLOB_REWRITES = 64
_MAX_POLICY_TOKENS = 256
_MAX_INTERPRETER_SEARCH = 64
_DIGEST_CHUNK_BYTES = 1 << 20
_SHELL_EVALUATORS = frozenset(
    {
        "ash",
        "bash",
        "cmd",
        "cmd.exe",
        "csh",
        "dash",
        "elvish",
        "es",
        "eval",
        "fish",
        "ksh",
        "mksh",
        "nu",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "rc",
        "rbash",
        "rksh",
        "rzsh",
        "sh",
        "tcsh",
        "xonsh",
        "yash",
        "zsh",
    }
)
_DYNAMIC_EVALUATORS = frozenset(
    {
        "awk",
        "bpftrace",
        "bb",
        "bun",
        "clisp",
        "clojure",
        "dc",
        "deno",
        "dotnet-script",
        "ed",
        "elixir",
        "emacs",
        "escript",
        "ex",
        "expect",
        "gawk",
        "ghci",
        "gmake",
        "groovy",
        "guile",
        "js",
        "jsc",
        "jshell",
        "julia",
        "kotlin",
        "less",
        "lua",
        "luajit",
        "make",
        "mawk",
        "man",
        "mariadb",
        "mysql",
        "nawk",
        "nim",
        "node",
        "nodejs",
        "nvim",
        "ocaml",
        "perl",
        "php",
        "psql",
        "qjs",
        "r",
        "racket",
        "raku",
        "ruby",
        "rscript",
        "sbcl",
        "scala",
        "sed",
        "sqlite3",
        "swift",
        "tclsh",
        "ts-node",
        "tsx",
        "vi",
        "view",
        "vim",
        "wish",
    }
)
_ENV_COMMANDS = frozenset({"env", "env.exe"})
_BUSYBOX_COMMANDS = frozenset({"busybox", "busybox.exe"})
_EXPANSION_SAFE_COMMANDS = frozenset({"printf"})
_COMMAND_DELEGATORS = frozenset(
    {
        "chrt",
        "chroot",
        "catchsegv",
        "doas",
        "flock",
        "i386",
        "i486",
        "i586",
        "i686",
        "ionice",
        "linux32",
        "linux64",
        "ltrace",
        "nsenter",
        "ncat",
        "nc",
        "numactl",
        "parallel",
        "perf",
        "prlimit",
        "proot",
        "rsync",
        "runuser",
        "scp",
        "script",
        "setarch",
        "setpriv",
        "sftp",
        "slogin",
        "socat",
        "ssh",
        "sshpass",
        "strace",
        "su",
        "sudo",
        "taskset",
        "torify",
        "uname26",
        "unshare",
        "valgrind",
        "watch",
        "x86_64",
        "xargs",
    }
)
_DEBUG_EVALUATORS = frozenset({"gdb", "lldb"})
_COMMAND_DELEGATION_ENVIRONMENT = {
    "tar": frozenset({"PATH", "TAR_OPTIONS"}),
}
_COMMAND_DELEGATION_OPTIONS = {
    "find": frozenset({"-exec", "-execdir", "-ok", "-okdir"}),
    "tar": frozenset(
        {
            "-F",
            "-I",
            "--checkpoint-action",
            "--info-script",
            "--new-volume-script",
            "--rsh-command",
            "--to-command",
            "--use-compress-program",
        }
    ),
}
_PROCESS_WRAPPER_OPERAND_OPTIONS = {
    "nice": frozenset({"-n", "--adjustment"}),
    "stdbuf": frozenset({"-e", "-i", "-o", "--error", "--input", "--output"}),
    "time": frozenset({"-f", "-o", "--format", "--output"}),
    "timeout": frozenset({"-k", "-s", "--kill-after", "--signal"}),
}
_PROCESS_WRAPPER_FLAG_OPTIONS = {
    "nice": frozenset(),
    "nohup": frozenset(),
    "setsid": frozenset({"-c", "-f", "-w", "--ctty", "--fork", "--keep-groups", "--wait"}),
    "stdbuf": frozenset(),
    "time": frozenset(
        {"-a", "-p", "-q", "-v", "--append", "--portability", "--quiet", "--verbose"}
    ),
    "timeout": frozenset({"-v", "--foreground", "--preserve-status", "--verbose"}),
}
_GIT_COMMAND_ENVIRONMENT = frozenset(
    {
        "EDITOR",
        "GIT_ASKPASS",
        "GIT_ALLOW_PROTOCOL",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_EDITOR",
        "GIT_EXEC_PATH",
        "GIT_EXTERNAL_DIFF",
        "GIT_PAGER",
        "GIT_PROTOCOL_FROM_USER",
        "GIT_PROXY_COMMAND",
        "GIT_SEQUENCE_EDITOR",
        "GIT_SSH",
        "GIT_SSH_COMMAND",
        "GIT_TEMPLATE_DIR",
        "GIT_WORK_TREE",
        "HOME",
        "PAGER",
        "PATH",
        "SSH_ASKPASS",
        "VISUAL",
        "XDG_CONFIG_HOME",
    }
)
_GIT_BUILTIN_COMMANDS = frozenset(
    {
        "add",
        "am",
        "annotate",
        "apply",
        "archive",
        "bisect",
        "blame",
        "branch",
        "bundle",
        "checkout",
        "cherry",
        "cherry-pick",
        "clean",
        "clone",
        "commit",
        "config",
        "count-objects",
        "describe",
        "diagnose",
        "diff",
        "fetch",
        "format-patch",
        "fsck",
        "gc",
        "grep",
        "hash-object",
        "init",
        "log",
        "ls-files",
        "ls-remote",
        "ls-tree",
        "maintenance",
        "merge",
        "merge-base",
        "merge-tree",
        "mv",
        "name-rev",
        "notes",
        "pack-objects",
        "pack-refs",
        "patch-id",
        "prune",
        "pull",
        "push",
        "range-diff",
        "read-tree",
        "reflog",
        "repack",
        "replace",
        "request-pull",
        "rerere",
        "reset",
        "restore",
        "rev-list",
        "rev-parse",
        "revert",
        "rm",
        "shortlog",
        "show",
        "show-branch",
        "show-ref",
        "sparse-checkout",
        "stage",
        "stash",
        "status",
        "switch",
        "symbol-ref",
        "tag",
        "update-index",
        "update-ref",
        "var",
        "verify-commit",
        "verify-tag",
        "version",
        "whatchanged",
        "worktree",
        "write-tree",
    }
)
_GIT_GLOBAL_EXECUTION_OPTIONS = frozenset(
    {
        "-C",
        "-p",
        "--attr-source",
        "--bare",
        "--config-env",
        "--git-dir",
        "--namespace",
        "--paginate",
        "--work-tree",
    }
)
_GIT_GLOBAL_EXECUTION_PREFIXES = (
    "--attr-source=",
    "--config-env=",
    "--exec-path=",
    "--git-dir=",
    "--namespace=",
    "--work-tree=",
)
_GIT_EXECUTION_OPTIONS_BY_SUBCOMMAND = {
    "archive": frozenset({"--exec"}),
    "clone": frozenset({"-c", "-u", "--config", "--template", "--upload-pack"}),
    "diff": frozenset({"--ext-diff"}),
    "fetch": frozenset({"--upload-pack"}),
    "grep": frozenset({"-O", "--open-files-in-pager"}),
    "ls-remote": frozenset({"--upload-pack"}),
    "merge": frozenset({"-s", "--strategy"}),
    "pull": frozenset({"-s", "--strategy", "--upload-pack"}),
    "push": frozenset({"--exec", "--receive-pack"}),
}
_GIT_OPTION_OPERANDS_BY_SUBCOMMAND = {
    "clone": frozenset(
        {
            "-b",
            "-c",
            "-o",
            "-u",
            "--branch",
            "--config",
            "--origin",
            "--template",
            "--upload-pack",
        }
    ),
    "fetch": frozenset({"-j", "--jobs", "--server-option", "--upload-pack"}),
    "ls-remote": frozenset({"--server-option", "--upload-pack"}),
    "pull": frozenset({"-j", "--jobs", "--server-option", "--upload-pack"}),
    "push": frozenset({"-o", "--push-option", "--receive-pack", "--repo"}),
}
_GIT_EXECUTION_OPERANDS_BY_SUBCOMMAND = {
    "bisect": frozenset({"run"}),
}
_GIT_SHORT_CLUSTER_OPERANDS_BY_SUBCOMMAND = {
    "grep": frozenset({"A", "B", "C", "e", "f", "m"}),
}
_GIT_SAFE_REMOTE_SCHEMES = frozenset({"git", "http", "https", "ssh"})
_GIT_REMOTE_SUBCOMMANDS = frozenset({"clone", "fetch", "ls-remote", "pull", "push"})
_GIT_CONFIG_READ_ACTIONS = frozenset(
    {
        "--get",
        "--get-all",
        "--get-regexp",
        "--list",
        "-l",
        "get",
        "get-all",
        "get-regexp",
        "list",
    }
)
_GIT_HOOK_FREE_SUBCOMMANDS = frozenset(
    {
        "annotate",
        "blame",
        "config",
        "count-objects",
        "describe",
        "diff",
        "fsck",
        "grep",
        "log",
        "ls-files",
        "ls-remote",
        "ls-tree",
        "merge-base",
        "merge-tree",
        "name-rev",
        "patch-id",
        "range-diff",
        "rev-list",
        "rev-parse",
        "shortlog",
        "show",
        "show-branch",
        "status",
        "verify-commit",
        "verify-tag",
        "whatchanged",
    }
)
_DANGEROUS_LOADER_ENVIRONMENT = frozenset(
    {
        "CORECLR_ENABLE_PROFILING",
        "CORECLR_PROFILER",
        "COR_ENABLE_PROFILING",
        "COR_PROFILER",
        "DOTNET_STARTUP_HOOKS",
        "LD_AUDIT",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "NODE_OPTIONS",
        "PERL5OPT",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "RUBYOPT",
    }
)
# Assignments whose VALUE names a program the shell or interpreter executes,
# beyond the loader set above. Relevance inspects these because such a variable
# runs its value without the path ever appearing as a command operand
# (issue #4764).
# Commands that exist to RUN another program named in their arguments. Their
# operands are never data, so relevance keeps a new_pr.py reference in scope
# (issue #4764). Interpreters, shells, and evaluators are covered by the
# existing evaluator sets; this list is the remaining launchers.
#
# Omission fails closed only when the launcher is also unresolvable, so keep it
# current: a resolvable launcher missing from this list would let
# `<launcher> new_pr.py` read as data. `uv` is here because `uv run
# tools/copy.py` executes a renamed copy of new_pr.py, which is a measured
# vector in tests/hooks/test_push_pr_script_identity_guard.py.
_LAUNCHER_COMMANDS = frozenset(
    {
        "conda",
        "doas",
        "hatch",
        "micromamba",
        "nix-shell",
        "parallel",
        "pdm",
        "pipenv",
        "pipx",
        "pixi",
        "poetry",
        "rye",
        "sudo",
        "tox",
        "uv",
        "uvx",
        "xargs",
    }
)
_EXECUTION_INFLUENCING_VARIABLES = frozenset(
    {
        "BASH_ENV",
        "ENV",
        "PAGER",
        "PUSH_PR_SCRIPT",
        "SHELL",
        "VISUAL",
    }
)
_GIT_CONFIG_READ_MODIFIERS = frozenset(
    {
        "--fixed-value",
        "--includes",
        "--local",
        "--name-only",
        "--no-includes",
        "--show-names",
        "--show-origin",
        "--show-scope",
        "--system",
        "--type",
        "--worktree",
        "--global",
    }
)
_TRUSTED_NEW_PR_SHA256 = "f9df25527cb27ec10c2eb70100d664165d81666a825eab848cd90609251dae26"
_TRUSTED_VALIDATE_PR_DESCRIPTION_SHA256 = (
    "00f32287461be4a0d0b15b0b7fb8a870d3824fbe4a6427373376fb4c38bda9eb"
)
_TRUSTED_PR_VALIDATIONS_SHA256 = (
    "a58457c51dfc7f1dc95ba95870e0311cde158be6b35114acb1e36c300f968570"
)


class GuardViolationError(ValueError):
    """A command shape the push-pr identity policy rejects."""


class ShellToken(NamedTuple):
    """One shell word with both source spelling and interpreted value."""

    raw: str
    value: str


def _read_request() -> tuple[str, Path]:
    raw = sys.stdin.read(_MAX_STDIN_BYTES + 1)
    if len(raw) > _MAX_STDIN_BYTES:
        raise GuardViolationError("hook input exceeds 128 KiB")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise GuardViolationError("hook input is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise GuardViolationError("hook input is not a JSON object")

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        raise GuardViolationError("tool_input is missing or invalid")
    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        raise GuardViolationError("Bash command is missing or invalid")

    cwd_value = payload.get("cwd")
    if cwd_value is None:
        return command, Path.cwd().resolve()
    if not isinstance(cwd_value, str) or not cwd_value.strip():
        raise GuardViolationError("hook cwd is invalid")
    cwd = Path(cwd_value)
    if not cwd.is_absolute():
        cwd = Path.cwd() / cwd
    return command, cwd.resolve()


def _split_command(command: str) -> list[ShellToken]:
    tokens: list[ShellToken] = []
    raw: list[str] = []
    value: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if char in "\r\n\0":
            raise GuardViolationError("command contains a line break or null byte")
        if quote == "'":
            raw.append(char)
            if char == "'":
                quote = None
            else:
                value.append(char)
            index += 1
            continue
        if quote == '"':
            raw.append(char)
            if char == '"':
                quote = None
            elif char == "`":
                raise GuardViolationError("command substitution is not allowed")
            elif char == "$" and command[index + 1 : index + 2] == "(":
                raise GuardViolationError("command substitution is not allowed")
            elif char == "\\":
                index += 1
                if index >= len(command):
                    raise GuardViolationError("command has incomplete shell quoting")
                raw.append(command[index])
                if command[index] in {"$", "`", '"', "\\"}:
                    value.append(command[index])
                else:
                    value.extend(("\\", command[index]))
            else:
                value.append(char)
            index += 1
            continue
        if char.isspace():
            if raw:
                tokens.append(ShellToken("".join(raw), "".join(value)))
                raw.clear()
                value.clear()
            index += 1
            continue
        if char == "\\":
            raw.append(char)
            index += 1
            if index >= len(command):
                raise GuardViolationError("command has incomplete shell quoting")
            raw.append(command[index])
            value.append(command[index])
            index += 1
            continue
        if char in ("'", '"'):
            raw.append(char)
            quote = char
        elif char in ";&|<>()":
            raise GuardViolationError("shell operators are not allowed")
        elif char == "`":
            raise GuardViolationError("command substitution is not allowed")
        elif char == "#" and not raw:
            raise GuardViolationError("shell comments are not allowed")
        else:
            raw.append(char)
            value.append(char)
        index += 1

    if quote is not None:
        raise GuardViolationError("command has incomplete shell quoting")
    if raw:
        tokens.append(ShellToken("".join(raw), "".join(value)))
    return tokens


def _could_target_new_pr(value: str) -> bool:
    literal = value.replace("\\\r\n", "").replace("\\\n", "").casefold()
    variants = {literal, literal.replace("\\", "/"), literal.replace("\\", "")}
    for normalized in variants:
        compacted = normalized.translate(str.maketrans("", "", "'\"+ \t"))
        if "new_pr.py" in compacted:
            return True
    return False


def _contains_shell_expansion(value: str) -> bool:
    return any(marker in value for marker in _SHELL_EXPANSION_MARKERS)


def _brace_alternatives(body: str) -> list[str]:
    """Return the alternatives a single innermost brace group can produce.

    A range is not materialized. Only values that can contribute a character
    of the target matter for the relevance decision, so a range collapses to
    at most the target's own alphabet plus one representative:

    * Digits appear nowhere in "new_pr.py", so a numeric range can never supply
      a character the target needs. It can only shift later text by its own
      width, and the narrowest and widest values bound that.
    * A character range can supply a needed character, so keep exactly the
      characters the target contains, plus the low value to represent every
      choice that lands outside a match.

    Bash's optional step (``{start..end..step}``) is parsed and then ignored.
    A step only removes values from the range, so collapsing against the full
    range stays a superset of what the shell produces, which is the safe
    direction: relevance may over-include, never under-include. Missing the
    step let ``./attacker/pr/n{e..e..1}w_pr.py`` read as literal text and skip
    the guard entirely (issue #4825).

    Materializing instead would make ``touch log{0..99}.txt`` and
    ``cp file{1..1000}.txt dir/`` exceed the expansion budget and fail closed,
    which denied legitimate commands (measured 4 of 7 in a probe).
    """
    bounds = body.split("..")
    if len(bounds) in {2, 3}:
        start, end = bounds[0], bounds[1]
        if start and end:
            if start.isdigit() and end.isdigit():
                low, high = sorted((int(start), int(end)))
                return sorted({str(low), str(high)})
            if len(start) == 1 and len(end) == 1:
                low, high = sorted((ord(start), ord(end)))
                candidates = {
                    chr(point)
                    for point in range(low, high + 1)
                    if chr(point) in _NEW_PR_TARGET
                }
                candidates.add(chr(low))
                return sorted(candidates)
    return body.split(",")


class _ExpansionBudgetError(Exception):
    """Enumeration hit a bound before finishing, so the caller must fail closed.

    A distinct type rather than a ``None`` return, so a caller cannot mistake
    "produced no match" for "gave up before looking". The two demand opposite
    verdicts: the first means the command is irrelevant, the second means the
    guard cannot prove it is, and an attacker who can force the second reading
    into an allow buys a bypass by making the command expensive.
    """


def _iter_brace_expansions(command: str) -> Iterator[str]:
    """Yield brace expansions of ``command``, innermost group first.

    Streams instead of materializing, and charges every projected byte against
    a budget BEFORE allocating it. Issue #4764 measured the previous
    list-building form on the merged tree:

        input 10,921 bytes -> 256 expansions, 2,562,194 bytes materialized
        input 100,060 bytes -> 2,048 expansions, 204,832,768 bytes,
                               195.6 MiB peak allocation

    Both stayed inside the 4,096-expansion budget, because a count budget
    cannot bound size: each expansion carries a full copy of the surrounding
    literal text, so cost is count times length, not count. The byte budget is
    the one that binds, and it is checked against the projected total before
    the strings exist, since checking after allocation measures a spike that
    has already happened.

    Raises ``_ExpansionBudgetError`` when either budget is exhausted. The
    enumeration is deliberately a superset of what a shell produces: relevance
    may over-include, never under-include.
    """
    frontier = [command]
    produced_bytes = len(command)
    remaining = _MAX_BRACE_EXPANSIONS
    while frontier:
        candidate = frontier.pop()
        group = _INNERMOST_BRACE_GROUP.search(candidate)
        if group is None:
            yield candidate
            continue
        alternatives = _brace_alternatives(group.group(1))
        remaining -= len(alternatives)
        if remaining < 0:
            raise _ExpansionBudgetError("brace expansion count budget exhausted")
        base_length = len(candidate) - (group.end() - group.start())
        produced_bytes += sum(base_length + len(alternative) for alternative in alternatives)
        if produced_bytes > _MAX_BRACE_EXPANDED_BYTES:
            raise _ExpansionBudgetError("brace expansion byte budget exhausted")
        frontier.extend(
            candidate[: group.start()] + alternative + candidate[group.end() :]
            for alternative in alternatives
        )


def _extglob_to_brace(text: str) -> str:
    """Rewrite Bash extglob groups into brace groups the expander already handles.

    Issue #4764: ``bash -O extglob`` expands
    ``.../pr/@(new)_pr.py`` to ``.../pr/new_pr.py``, and both dispatchers
    returned 0 (allow) for that command on the merged tree. ``@(`` and ``!(``
    carry none of the ``? * [`` characters the guard treated as glob markers,
    so the pattern read as ordinary literal text that did not contain
    ``new_pr.py``, and ``(`` made the segment fail to tokenize, which routed it
    to a backstop that only inspects the head word.

    Rewriting rather than adding a second expander keeps one enumeration engine
    and one budget. The mapping is a superset of what the shell produces, which
    is the safe direction for a relevance decision:

    ==========  =============  =================================
    Pattern     Rewrite        Reason
    ==========  =============  =================================
    ``@(a|b)``  ``{a,b}``      exactly one alternative
    ``+(a|b)``  ``{a,b}``      one or more; one alternative is in the set
    ``?(a|b)``  ``{,a,b}``     zero or one
    ``*(a|b)``  ``{,a,b}``     zero or more; both endpoints are in the set
    ``!(a|b)``  ``*``          anything else, so a wildcard covers it
    ==========  =============  =================================

    ``*(a|b)`` can also produce ``aa`` and ``abab``, which this does not
    enumerate. It does not need to: relevance asks whether the pattern CAN name
    new_pr.py, and if it can, one of the listed alternatives already spells it.

    Innermost-first, bounded by ``_MAX_EXTGLOB_REWRITES``, so a nested pattern
    cannot loop. Text with no extglob group is returned unchanged.
    """
    for _ in range(_MAX_EXTGLOB_REWRITES):
        match = _EXTGLOB_GROUP.search(text)
        if match is None:
            return text
        operator, body = match.group(1), match.group(2)
        alternatives = body.split("|")
        if operator == "!":
            replacement = "*"
        elif operator in {"?", "*"}:
            replacement = "{," + ",".join(alternatives) + "}"
        else:
            replacement = "{" + ",".join(alternatives) + "}"
        text = text[: match.start()] + replacement + text[match.end() :]
    return text


def _spellings(text: str) -> set[str]:
    """Return the ways a shell could spell ``text`` before it reaches the OS.

    Collects the obfuscations the guard already knew about individually:
    single-character glob classes (``n[e]w_pr.py``), ANSI-C quoting
    (``$'new\\x5fpr.py'``), and extglob groups (``@(new)_pr.py``). Brace
    expansion is applied by the caller, because it is the only one that can
    exceed a budget.
    """
    unclassed = text.replace("[", "").replace("]", "")
    variants = {text, unclassed}
    variants |= {_ansi_c_decoded(variant) for variant in tuple(variants)}
    variants |= {_extglob_to_brace(variant) for variant in tuple(variants)}
    return variants


def _names_new_pr(command: str) -> bool:
    """True when ``command`` text can spell new_pr.py anywhere in it.

    Substring-based and position-blind. Used for CODE positions, where the text
    is a program rather than a path, and by the fail-closed backstop for a
    segment that will not tokenize. Path positions use
    ``_path_names_new_pr`` instead, because a substring test reports
    ``tests/test_new_pr.py`` as new_pr.py (issue #4764).
    """
    for text in _spellings(command):
        if _could_target_new_pr(text):
            return True
        try:
            if any(_could_target_new_pr(candidate) for candidate in _iter_brace_expansions(text)):
                return True
        except _ExpansionBudgetError:
            return True
    return False


def _path_names_new_pr(value: str) -> bool:
    """True when ``value`` is a path whose final component is new_pr.py.

    Basename equality, not substring containment. Issue #4764 measured the
    substring form denying ``python3 -m pytest tests/test_new_pr.py``, because
    ``test_new_pr.py`` contains ``new_pr.py``. A path names the script only
    when its LAST component is the script; ``foo_new_pr.py`` and
    ``new_pr.py.bak`` are different files.

    Narrowing here does not lose the renamed-copy case: a file whose name
    differs but whose bytes match is caught by ``_operand_is_new_pr_copy``,
    which compares content at execution positions.
    """
    for text in _spellings(value):
        try:
            candidates = list(_iter_brace_expansions(text))
        except _ExpansionBudgetError:
            return True
        for candidate in candidates:
            literal = candidate.replace("\\\r\n", "").replace("\\\n", "").casefold()
            for normalized in (literal, literal.replace("\\", "/"), literal.replace("\\", "")):
                compacted = normalized.translate(str.maketrans("", "", "'\"+ \t"))
                basename = compacted.rsplit("/", 1)[-1]
                if basename == _NEW_PR_TARGET:
                    return True
                if any(marker in basename for marker in "?*[") and fnmatch.fnmatch(
                    _NEW_PR_TARGET, basename
                ):
                    return True
    return False


def _ansi_c_decoded(text: str) -> str:
    """Decode Bash ANSI-C ``$'...'`` segments so naming sees what runs.

    Bash executes ``./attacker/pr/$'new\\x5fpr.py'`` as
    ``./attacker/pr/new_pr.py``. The compaction below strips the backslash
    without decoding the escape, producing ``newx5fpr.py``, so a direct launch
    missed every relevance rule (issue #4825). Octal (``\\137``) has the same
    shape.
    """

    def decode(match: re.Match[str]) -> str:
        body = match.group(1)
        try:
            return body.encode("latin-1", "backslashreplace").decode("unicode_escape")
        except (UnicodeDecodeError, UnicodeEncodeError, ValueError):
            return body

    # Annotated because the generated shim inlines this module into a
    # function, which loses the pattern's inferred type and makes the
    # substitution read as Any to mypy.
    decoded: str = _ANSI_C_QUOTED.sub(decode, text)
    return decoded


def _execution_position_names_new_pr(tokens: list[ShellToken], cwd: Path) -> bool:
    """Scope rule D: an executed path is a glob or escape naming new_pr.py.

    Position, not a literal prefix, separates a targeted glob from a data glob.
    ``./attacker/pr/?ew_pr.py`` and ``./attacker/pr/[!x]ew_pr.py`` both expand
    to the lookalike and both have an empty literal prefix, so a
    prefix-threshold heuristic let them through while a direct launch missed
    scope rules B and C (issue #4825). ``echo *.py`` stays out of scope because
    an argument to ``echo`` is not an execution position.

    ANSI-C quoting in an execution position fails closed. Decoding covers the
    escapes ``unicode_escape`` knows; a path that runs and still needs
    ``$'...'`` to spell itself is not a shape this guard can clear.
    """
    for token in _execution_position_tokens(tokens, cwd):
        if "$'" in token.raw:
            return True
        basename = token.value.rsplit("/", 1)[-1]
        if not basename or not any(marker in basename for marker in "?*["):
            continue
        if fnmatch.fnmatch(_NEW_PR_TARGET, basename):
            return True
    return False


def _strip_unquoted_redirections(command: str) -> str:
    """Remove redirections that sit outside quotes.

    ``_split_command`` rejects ``<`` and ``>`` as policy, and a rejected
    segment used to be skipped, so ``./attacker/pr/?ew_pr.py >out`` reached no
    relevance rule (issue #4825). A redirection never changes which file runs,
    so dropping it preserves execution position while letting the segment
    parse. Quoted text is copied through untouched, because a redirection
    operator inside quotes is data.
    """
    out: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if quote is None and char == "\\":
            out.append(char)
            if index + 1 < len(command):
                out.append(command[index + 1])
                index += 2
                continue
            index += 1
            continue
        if quote is not None:
            out.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "'\"":
            quote = char
            out.append(char)
            index += 1
            continue
        if char in "<>":
            while out and out[-1].isdigit():
                out.pop()
            while index < len(command) and command[index] in "<>&":
                index += 1
            while index < len(command) and command[index] in " \t":
                index += 1
            while index < len(command) and command[index] not in " \t;&|<>\n":
                index += 1
            out.append(" ")
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _split_shell_segments(command: str) -> list[str]:
    """Split on shell operators that sit outside quotes.

    A regex split matched operators inside quoted arguments, so
    ``./attacker/pr/?ew_pr.py "x && y"`` was torn into fragments that no longer
    parsed and the execution was never classified (issue #4825).
    """
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if quote is None and char == "\\":
            current.append(char)
            if index + 1 < len(command):
                current.append(command[index + 1])
                index += 2
                continue
            index += 1
            continue
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "'\"":
            quote = char
            current.append(char)
            index += 1
            continue
        if char in ";&|\n":
            segments.append("".join(current))
            current = []
            if index + 1 < len(command) and command[index + 1] == char:
                index += 1
            index += 1
            continue
        current.append(char)
        index += 1
    segments.append("".join(current))
    return segments


def _segment_head_names_new_pr(segment: str) -> bool:
    """Fail-closed backstop for a segment that still will not tokenize.

    Keeps an unparseable but target-shaped execution in scope rather than
    letting a quoting artifact decide relevance.

    Position-blind on purpose. Everywhere else relevance asks WHERE the name
    appears, but a segment that will not tokenize has no positions to ask
    about: the guard cannot tell an operand from a command word in text it
    could not parse. So the whole segment is tested, which is the merged
    tree's original rule confined to the one case that needs it. Testing only
    the head word let ``python3 .../new_pr.py # comment`` out of scope, because
    ``#`` makes ``_split_command`` raise and the head is ``python3``
    (issue #4764).
    """
    stripped = segment.strip()
    if not stripped:
        return False
    if _names_new_pr(stripped):
        return True
    head = stripped.split(None, 1)
    word = head[0].strip("'\"")
    basename = word.rsplit("/", 1)[-1]
    if not basename:
        return False
    return any(marker in basename for marker in "?*[") and fnmatch.fnmatch(
        _NEW_PR_TARGET, basename
    )


def _scope_segments(command: str) -> list[list[ShellToken]]:
    """Tokenize each shell segment for the relevance decision only.

    ``_split_command`` rejects command substitution, shell operators and
    redirections as policy. Those rejections must not decide relevance:
    returning nothing on a parse failure failed open, so appending ``&& true``
    or ``>out`` defeated every execution-position rule (issue #4825).

    Substitutions are neutralized, redirections dropped, and the command split
    on unquoted operators, because execution position is a per-segment
    property. A segment that still will not parse is reported through the
    fail-closed backstop rather than silently skipped.
    """
    neutralized = _COMMAND_SUBSTITUTION.sub("$X", command)
    segments: list[list[ShellToken]] = []
    for piece in _split_shell_segments(_strip_unquoted_redirections(neutralized)):
        stripped = piece.strip()
        if not stripped:
            continue
        # Extglob groups become brace groups BEFORE tokenizing. `(` and `)` are
        # shell operators that _split_command rejects, so an extglob segment
        # used to fail to parse and fall through to the head-word backstop,
        # which allowed `python3 .../@(new)_pr.py` outright (issue #4764).
        # Rewriting keeps one expansion engine and one budget; see
        # _extglob_to_brace for the mapping and why it is a safe superset.
        rewritten = _extglob_to_brace(stripped)
        try:
            tokens = _split_command(rewritten)
        except GuardViolationError:
            if _segment_head_names_new_pr(rewritten):
                return [[ShellToken(_NEW_PR_TARGET, _NEW_PR_TARGET)]]
            continue
        if tokens:
            segments.append(tokens)
    return segments


def _shell_evaluator_argument_is_in_scope(
    tokens: list[ShellToken],
    cwd: Path,
    depth: int,
) -> bool:
    index = _effective_command_index(tokens)
    if index is None:
        return False
    command_name = _command_name(tokens[index].value)
    unversioned_name = _unversioned_command_name(tokens[index].value)
    if command_name not in _SHELL_EVALUATORS and unversioned_name not in _SHELL_EVALUATORS:
        return False
    for offset, token in enumerate(tokens[index + 1 :], start=index + 1):
        value = token.value
        if value == "-c":
            return offset + 1 < len(tokens) and _command_text_is_in_scope(
                tokens[offset + 1].value,
                cwd,
                depth + 1,
            )
        if value.startswith("-") and not value.startswith("--") and "c" in value[1:]:
            return offset + 1 < len(tokens) and _command_text_is_in_scope(
                tokens[offset + 1].value,
                cwd,
                depth + 1,
            )
    return command_name == "eval" and any(
        _command_text_is_in_scope(token.value, cwd, depth + 1)
        for token in tokens[index + 1 :]
    )


def _unresolvable_python_target(tokens: list[ShellToken], cwd: Path) -> bool:
    """Scope rule B: a Python script operand the guard cannot resolve."""
    arguments = _python_arguments(tokens, cwd)
    if arguments is None:
        return False
    target, dynamic = _execution_target(arguments)
    if target is None or dynamic:
        return False
    return _contains_shell_expansion(target.raw) or _contains_shell_expansion(target.value)


def _execution_position_tokens(tokens: list[ShellToken], cwd: Path) -> list[ShellToken]:
    """Return the tokens a file could actually execute from.

    Only three positions run a file: the effective command, a Python
    interpreter reached through wrappers, and that interpreter's script
    operand. An operand sitting elsewhere is a filename argument, not an
    execution, so it is not this guard's business.

    Consults ``_operands_are_data`` first, so every scope rule shares one
    definition of an execution position. Without that, the interpreter search
    reads shebangs and reports the real new_pr.py as an "interpreter" whenever
    it appears as an operand, which put ``git diff -- .../new_pr.py`` and
    ``ruff check .../new_pr.py`` back in scope through the renamed-copy rule
    even after the path rule had correctly classified them as data
    (issue #4764).
    """
    index = _effective_command_index(tokens)
    if index is None:
        return []
    if _operands_are_data(tokens, index, cwd):
        return [tokens[index]]
    positions = [tokens[index]]
    arguments = _python_arguments(tokens, cwd)
    if arguments is not None:
        interpreter_index = len(tokens) - len(arguments) - 1
        if 0 <= interpreter_index < len(tokens):
            positions.append(tokens[interpreter_index])
        target, dynamic = _execution_target(arguments)
        if target is not None and not dynamic:
            positions.append(target)
    return positions


def _matches_trusted_file(
    candidate: Path,
    runtime_script: Path,
    trusted: os.stat_result,
) -> bool:
    """Compare one operand against the trusted script with a single stat."""
    try:
        info = candidate.stat()
    except OSError:
        return False
    if not stat.S_ISREG(info.st_mode):
        return False
    if (info.st_dev, info.st_ino) == (trusted.st_dev, trusted.st_ino):
        return True
    if info.st_size != trusted.st_size:
        return False
    return _same_executable_content(candidate, runtime_script)


def _operand_is_new_pr_copy(tokens: list[ShellToken], cwd: Path) -> bool:
    """Scope rule C: an executed file is a byte-identical copy of new_pr.py.

    This inspects execution positions, not every token. A fixed 64-token window
    let a command pad itself past the cap with `env` assignments and hide a
    byte-identical copy behind them (issue #4825). Raising or fail-closing the
    cap traded that leak for denying large ordinary commands. Position is the
    property that actually matters: a copy in argument slot 500 never runs.
    """
    runtime_script = _runtime_script()
    if runtime_script is None:
        return False
    try:
        trusted = runtime_script.stat()
    except OSError:
        return False
    for token in _execution_position_tokens(tokens, cwd):
        value = token.value
        if not value or value.startswith("-"):
            continue
        candidate = Path(os.path.expanduser(value))
        if not candidate.is_absolute():
            candidate = cwd / candidate
        if _matches_trusted_file(candidate, runtime_script, trusted):
            return True
    return False


def _operands_are_data(tokens: list[ShellToken], index: int, cwd: Path) -> bool:
    """True when the effective command READS its operands instead of running them.

    This is the discriminator that fixes the issue #4764 false denials without
    weakening execution detection. ``git diff -- .../new_pr.py``, ``cat
    .../new_pr.py`` and ``ruff check .../new_pr.py`` all name the script in an
    operand, and none of them execute an operand, so the reference is data.

    Stated as four disqualifications rather than an allowlist of readers. An
    allowlist would have to name every tool anyone runs against a Python file,
    and every omission is a false denial of a routine command. The
    disqualifications below are closed sets the guard already maintains, so an
    unlisted READER is handled correctly by default and only an unlisted
    EXECUTOR needs adding.

    Operands are NOT data when:

    1. A leading assignment is present. ``/usr/bin/env PATH=. cat
       attacker/new_pr.py`` reads like a plain read, but ``PATH=.`` decides
       which ``cat`` runs, so the command is no longer the one it names.
    2. The command word carries active shell expansion. ``/usr/bin/pytho[n]3``,
       ``pytho{n,xx}3`` and ``$PY`` all resolve at runtime to something the
       guard cannot name, so it must assume the worst.
    3. The command is an interpreter, evaluator, or launcher. These exist to
       run their operands.
    4. The command does not resolve to a program on disk. An unresolvable
       command word is an unknown program, and this fails closed.

    Anything that survives all four is a resolvable, non-executing program, and
    a path in its argument vector is data.
    """
    if any(_is_assignment(token.value) for token in tokens[:index]):
        return False
    token = tokens[index]
    if _contains_active_shell_expansion(token.raw):
        return False
    name = _command_name(token.value)
    unversioned = _unversioned_command_name(token.value)
    executors = _SHELL_EVALUATORS | _DYNAMIC_EVALUATORS | _DEBUG_EVALUATORS | _LAUNCHER_COMMANDS
    if name in executors or unversioned in executors:
        return False
    if _is_python_interpreter(token.value) or _is_dynamic_evaluator_name(token.value):
        return False
    # `script -q -c '<command>'` and `nsenter --target 1 --mount <command>` run
    # a program named in their arguments without being interpreters. The policy
    # layer already classifies them through `_is_command_delegator`; relevance
    # reuses it so a shape the policy would deny cannot fall out of scope first.
    #
    # `_contains_dynamic_evaluator` is deliberately NOT reused here even though
    # it is the fuller predicate: it calls `_repository_has_active_git_hooks`,
    # which returns True for an ordinary repository, so every `git` command
    # would be classified as an executor and `git diff -- .../new_pr.py` would
    # be denied again.
    if _is_command_delegator(tokens, index):
        return False
    if _resolves_to_known_command(tokens, index, cwd, executors):
        return False
    if _resolved_command(tokens, index, cwd) is None:
        return False
    return not _token_is_python_interpreter(tokens, index, cwd)


def _execution_capable_paths(tokens: list[ShellToken], cwd: Path) -> list[ShellToken]:
    """Return the tokens whose VALUE is a path something could execute.

    Issue #4764 narrowed relevance to these positions. The previous rule placed
    a command in scope whenever its text mentioned new_pr.py anywhere, which
    denied ``git diff -- .../new_pr.py`` and ``python3 -m pytest
    tests/test_new_pr.py``: routine commands that read the file or merely share
    a name suffix with it. Both were measured returning 2 on both dispatchers.

    A path reaches execution through exactly these doors:

    1. the effective command, after assignments and wrappers are skipped;
    2. a Python interpreter reached through those wrappers, and its script
       operand when the launcher is static;
    3. every remaining word, whenever the effective command is not provably a
       reader (see ``_operands_are_data``). This is the fail-closed default:
       an interpreter, a launcher, an obfuscated command word, or one the guard
       cannot resolve gives it no way to tell an operand from a target;
    4. an assignment the loader or interpreter acts on (``PYTHONSTARTUP``,
       ``LD_PRELOAD``, ``BASH_ENV``, ``GIT_*``), which executes its value
       without it ever appearing as an operand;
    5. an operand Git delegates execution to (``-c core.pager=``,
       ``--upload-pack=``, ``--open-files-in-pager=``, an ``ext::`` remote).

    Doors 4 and 5 are additive and apply even to a reader, because they are how
    a command that otherwise only reads can still run a program.

    What this removes is door 0 of the merged tree: "the command text mentions
    new_pr.py anywhere". That rule is what denied ``git diff`` and ``pytest``.
    """
    index = _effective_command_index(tokens)
    if index is None:
        return []

    positions: list[ShellToken] = [tokens[index]]
    positions.extend(
        ShellToken(token.raw, token.value.partition("=")[2])
        for token in tokens[:index]
        if _is_execution_influencing_assignment(token.value)
    )
    positions.extend(_git_delegated_operands(tokens, index, cwd))

    if _operands_are_data(tokens, index, cwd):
        return positions

    # Not provably a reader, so every remaining word is a candidate path. This
    # is the fail-closed branch: an obfuscated command word
    # (`/usr/bin/pytho[n]3`), an unresolvable one (`./p`), or one preceded by an
    # assignment that redirects resolution (`PATH=. cat`) gives the guard no way
    # to know which operand the program will run, so it treats them all as
    # execution-capable. Narrowing this to _execution_position_tokens alone
    # allowed six such shapes that the merged tree denied.
    positions.extend(tokens[index:])
    return positions


def _is_execution_influencing_assignment(value: str) -> bool:
    """True when a leading ``NAME=value`` assignment can execute its value."""
    name, separator, _ = value.partition("=")
    if not separator:
        return False
    return (
        name in _EXECUTION_INFLUENCING_VARIABLES
        or name in _DANGEROUS_LOADER_ENVIRONMENT
        or name.startswith(("DYLD_", "GIT_CONFIG_"))
        or name in _GIT_COMMAND_ENVIRONMENT
    )


def _git_delegated_operands(
    tokens: list[ShellToken],
    command_index: int,
    cwd: Path,
) -> list[ShellToken]:
    """Return operands a Git invocation would hand to a program to execute.

    Keeps the Git pager and external-transport vectors in scope after relevance
    narrowed to execution positions. ``git -c core.pager=<path> log`` and
    ``git clone ext::<payload>`` never place the executed path in a command
    position, so ``_execution_position_tokens`` cannot see it.

    Narrower than ``_contains_git_execution_delegation``, deliberately. That
    predicate answers "could this Git command run a hook or helper at all",
    which is true for almost every subcommand in a repository with hooks
    installed, and using it for relevance is what denied ``git diff``. This
    returns only the operands whose VALUE names a program.
    """
    git_invocation = _normalized_git_invocation(tokens, command_index, cwd)
    if git_invocation is None:
        return []
    normalized, index = git_invocation

    operands: list[ShellToken] = []
    position = index + 1
    while position < len(normalized):
        token = normalized[position]
        value = token.value
        if value == "-c" and position + 1 < len(normalized):
            configured = normalized[position + 1]
            operands.append(
                ShellToken(configured.raw, configured.value.partition("=")[2])
            )
            position += 2
            continue
        if value.startswith("-c") and len(value) > 2:
            operands.append(ShellToken(token.raw, value[2:].partition("=")[2]))
        elif value in _GIT_GLOBAL_EXECUTION_OPTIONS and position + 1 < len(normalized):
            operands.append(normalized[position + 1])
        elif value.startswith(_GIT_GLOBAL_EXECUTION_PREFIXES):
            operands.append(ShellToken(token.raw, value.partition("=")[2] or value))
        elif _has_unsafe_git_remote(value):
            operands.append(token)
        position += 1

    # Per-subcommand execution options, e.g. `git grep
    # --open-files-in-pager=<program>`. These are not global options, so the
    # loop above cannot see them, and omitting them let a pager-delegated
    # execution out of scope.
    subcommand_index = _git_subcommand_index_or_none(normalized, index)
    if subcommand_index is not None:
        subcommand = normalized[subcommand_index].value.casefold()
        execution_options = _GIT_EXECUTION_OPTIONS_BY_SUBCOMMAND.get(subcommand, frozenset())
        for offset, token in enumerate(
            normalized[subcommand_index + 1 :], start=subcommand_index + 1
        ):
            if not _matches_git_option(subcommand, token.value, execution_options):
                continue
            _key, separator, configured = token.value.partition("=")
            if separator:
                operands.append(ShellToken(token.raw, configured))
            elif offset + 1 < len(normalized):
                operands.append(normalized[offset + 1])
    return operands


def _git_subcommand_index_or_none(tokens: list[ShellToken], command_index: int) -> int | None:
    """``_git_subcommand_index`` without its policy exception.

    The policy version raises on unsupported global options, which is correct
    when deciding whether to DENY. Relevance must not raise: a command it
    cannot classify is simply one with no extractable delegation operand, and
    the other scope rules still apply to it.
    """
    try:
        return _git_subcommand_index(tokens, command_index)
    except GuardViolationError:
        return None


def _execution_capable_code(tokens: list[ShellToken], cwd: Path) -> list[str]:
    """Return argument text that is CODE rather than a path.

    Code is tested by substring, because a program that reaches new_pr.py spells
    the name inside a larger expression: ``runpy.run_path('new_pr.py')`` is not
    a path and has no basename to compare. Applying the substring test only here
    is what lets ``python3 -m pytest tests/test_new_pr.py`` out of scope while
    keeping ``python3 -c "...new_pr.py..."`` in it.
    """
    index = _effective_command_index(tokens)
    if index is None:
        return []

    code: list[str] = []
    arguments = _python_arguments(tokens, cwd)
    if arguments is not None:
        target, dynamic = _execution_target(arguments)
        if dynamic and target is not None:
            code.append(target.value)
            code.append(target.raw)

    # An evaluator's arguments are a program in its own language, and this
    # guard has no parser for awk, perl, or node. Substring over the whole
    # argument list is what the merged tree already applied to every command;
    # confining it to evaluators is strictly narrower, so it cannot deny
    # anything the merged tree allowed.
    if _command_is_evaluator(tokens, index, cwd):
        code.extend(token.value for token in tokens[index + 1 :])
        code.extend(token.raw for token in tokens[index + 1 :])
    return code


def _command_is_evaluator(tokens: list[ShellToken], index: int, cwd: Path) -> bool:
    """True when the effective command interprets its arguments as a program."""
    command_name = _command_name(tokens[index].value)
    unversioned = _unversioned_command_name(tokens[index].value)
    if command_name in _SHELL_EVALUATORS or unversioned in _SHELL_EVALUATORS:
        return True
    if any(_is_dynamic_evaluator_name(token.value) for token in tokens[index : index + 2]):
        return True
    return _resolves_to_known_command(
        tokens,
        index,
        cwd,
        _DYNAMIC_EVALUATORS | _DEBUG_EVALUATORS,
    )


def _command_is_in_scope(command: str, cwd: Path) -> bool:
    """Non-blocking relevance gate. See the module docstring for the contract."""
    return _command_text_is_in_scope(command, cwd, 0)


def _segments_are_in_scope(tokens: list[ShellToken], cwd: Path, depth: int) -> bool:
    """Decide relevance for one shell segment."""
    if any(_path_names_new_pr(token.value) for token in _execution_capable_paths(tokens, cwd)):
        return True
    if any(_names_new_pr(text) for text in _execution_capable_code(tokens, cwd)):
        return True
    return (
        _unresolvable_python_target(tokens, cwd)
        or _execution_position_names_new_pr(tokens, cwd)
        or _operand_is_new_pr_copy(tokens, cwd)
        or _shell_evaluator_argument_is_in_scope(tokens, cwd, depth)
    )


def _command_text_is_in_scope(command: str, cwd: Path, depth: int) -> bool:
    if depth > 4:
        return True
    return any(
        _segments_are_in_scope(tokens, cwd, depth) for tokens in _scope_segments(command)
    )


def _contains_active_parameter_expansion(raw: str) -> bool:
    quote: str | None = None
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if char == "'":
            quote = None if quote == "'" else "'" if quote is None else quote
        elif char == '"':
            quote = None if quote == '"' else '"' if quote is None else quote
        elif char in {"$", "`"} and quote != "'":
            return True
        index += 1
    return False


def _contains_active_shell_expansion(raw: str) -> bool:
    quote: str | None = None
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if char == "'":
            quote = None if quote == "'" else "'" if quote is None else quote
        elif char == '"':
            quote = None if quote == '"' else '"' if quote is None else quote
        elif char in {"$", "`"} and quote != "'":
            return True
        elif quote is None and char in {"{", "[", "*", "?", "~"}:
            return True
        index += 1
    return False


def _requires_identity_check(command: str, cwd: Path) -> bool:
    joined = command.replace("\\\r\n", "").replace("\\\n", "")
    compacted = joined.casefold().translate(str.maketrans("", "", "'\"+ \t\\"))
    if "new_pr.py" in compacted:
        return True
    if ".py" in compacted:
        return True
    tokens = _split_command(command)
    arguments = _python_arguments(tokens, cwd)
    if arguments is not None:
        return True
    if any(
        _command_name(token.value) in _SHELL_EVALUATORS
        and (
            _command_name(token.value) == "eval"
            or any(option.value == "-c" for option in tokens[index + 1 :])
        )
        for index, token in enumerate(tokens)
    ):
        return True
    if not _contains_shell_expansion(command):
        return False
    command_index = _effective_command_index(tokens)
    if command_index is None:
        return True
    effective_command = tokens[command_index]
    if _contains_shell_expansion(effective_command.raw):
        return True
    if not _resolves_to_installed_command(
        tokens,
        command_index,
        cwd,
        _EXPANSION_SAFE_COMMANDS,
    ):
        return True
    return any(_contains_active_parameter_expansion(token.raw) for token in tokens)


def _is_assignment(token: str) -> bool:
    name, separator, _ = token.partition("=")
    return bool(separator and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name))


def _contains_dangerous_loader_environment(tokens: list[ShellToken]) -> bool:
    command_index = _effective_command_index(tokens)
    if command_index is None:
        return False
    for token in tokens[:command_index]:
        name, separator, _ = token.value.partition("=")
        if separator and (name in _DANGEROUS_LOADER_ENVIRONMENT or name.startswith("DYLD_")):
            return True
    return False


def _command_name(value: str) -> str:
    return Path(value).name.casefold().removesuffix(".exe")


def _unversioned_command_name(value: str) -> str:
    return re.sub(
        r"[._-]?\d+(?:\.\d+)*(?:[a-z][a-z0-9.-]*)?$",
        "",
        _command_name(value),
    ).rstrip("._-")


def _is_python_interpreter(value: str) -> bool:
    name = Path(value).name.casefold()
    return bool(
        re.fullmatch(
            r"(?:python(?:[23](?:\.\d+)*)?|pypy(?:[23](?:\.\d+)*)?|py)(?:\.exe)?",
            name,
        )
    )


def _sha256_digest(stream: BinaryIO) -> hashlib._Hash:
    """Hash a binary stream without ``hashlib.file_digest``.

    ``hashlib.file_digest`` landed in Python 3.11, but the generated hook
    launchers accept any interpreter at 3.10 or newer:

        "$_c" -I -c "import sys;print(int(sys.version_info>=(3,10)))"

    Calling it on 3.10 raised ``AttributeError`` and the guard exited 1, which
    a PreToolUse host treats as a hook error rather than a block, so the
    identity gate silently stopped enforcing on that interpreter. Reproduced on
    cpython 3.10.20 against the canonical push-pr command (issue #4825).
    """
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(_DIGEST_CHUNK_BYTES), b""):
        digest.update(chunk)
    return digest


def _same_executable_content(left: Path, right: Path) -> bool:
    try:
        if left.samefile(right):
            return True
        if left.stat().st_size != right.stat().st_size:
            return False
        with left.open("rb") as left_stream, right.open("rb") as right_stream:
            return _sha256_digest(left_stream).digest() == _sha256_digest(right_stream).digest()
    except OSError:
        return False


def _command_search_path(tokens: list[ShellToken], index: int) -> str:
    search_path = os.environ.get("PATH", os.defpath)
    for token in tokens[:index]:
        value = token.value
        if value in {"-i", "--ignore-environment"}:
            search_path = os.defpath
            continue
        name, separator, configured_value = value.partition("=")
        if separator and name == "PATH":
            search_path = configured_value
    return search_path


def _resolved_command(
    tokens: list[ShellToken],
    index: int,
    cwd: Path,
) -> Path | None:
    value = os.path.expanduser(tokens[index].value)
    candidate = Path(value)
    if candidate.is_absolute() or candidate.parent != Path("."):
        if not candidate.is_absolute():
            candidate = cwd / candidate
        try:
            return candidate.resolve(strict=True)
        except OSError:
            return None
    resolved = shutil.which(value, path=_command_search_path(tokens, index))
    return Path(resolved).resolve() if resolved is not None else None


def _resolves_to_known_command(
    tokens: list[ShellToken],
    index: int,
    cwd: Path,
    names: frozenset[str],
) -> bool:
    resolved = _resolved_command(tokens, index, cwd)
    if resolved is None:
        return False
    if _command_name(resolved.name) in names or _unversioned_command_name(resolved.name) in names:
        return True
    try:
        with resolved.open("rb") as stream:
            shebang = stream.readline(4096).decode("utf-8", errors="ignore")
    except OSError:
        shebang = ""
    if shebang.startswith("#!") and any(
        _command_name(part) in names or _unversioned_command_name(part) in names
        for part in shebang[2:].split()
    ):
        return True
    for name in names:
        known = shutil.which(name)
        if known is not None and _same_executable_content(
            resolved,
            Path(known).resolve(),
        ):
            return True
    return False


def _resolves_to_installed_command(
    tokens: list[ShellToken],
    index: int,
    cwd: Path,
    names: frozenset[str],
) -> bool:
    resolved = _resolved_command(tokens, index, cwd)
    if resolved is None:
        return False
    for name in names:
        known = shutil.which(name)
        if known is not None and _same_executable_content(
            resolved,
            Path(known).resolve(),
        ):
            return True
    return False


def _env_command_index(tokens: list[ShellToken], index: int) -> int | None:
    operand_options = {
        "-a",
        "-u",
        "--unset",
        "-C",
        "--chdir",
        "--argv0",
    }
    flag_options = {
        "-0",
        "--null",
        "-i",
        "--ignore-environment",
        "-v",
        "--debug",
    }
    while index < len(tokens):
        value = tokens[index].value
        if _is_env_split_string_option(value):
            raise GuardViolationError("env split-string launchers are not allowed")
        if value == "--":
            index += 1
            while index < len(tokens) and "=" in tokens[index].value:
                index += 1
            return index if index < len(tokens) else None
        if _is_env_assignment(value):
            index += 1
            continue
        if value in flag_options:
            index += 1
            continue
        if value in operand_options:
            index += 2
            continue
        if value.startswith(("--unset=", "--chdir=", "--argv0=")):
            index += 1
            continue
        if value.startswith(("-a", "-u", "-C")) and len(value) > 2:
            index += 1
            continue
        if value.startswith("-"):
            raise GuardViolationError("unsupported env options are not allowed")
        return index
    return None


def _is_env_split_string_option(value: str) -> bool:
    long_option = value.partition("=")[0]
    if len(long_option) > 2 and "--split-string".startswith(long_option):
        return True
    if not value.startswith("-") or value.startswith("--"):
        return False
    for option in value[1:]:
        if option == "S":
            return True
        if option in {"a", "C", "u"}:
            return False
        if option not in {"0", "i", "v"}:
            return False
    return False


def _is_env_assignment(value: str) -> bool:
    return "=" in value and not value.startswith("-")


def _token_is_python_interpreter(
    tokens: list[ShellToken],
    index: int,
    cwd: Path,
) -> bool:
    token = tokens[index]
    if _is_python_interpreter(token.value):
        return True
    resolved_interpreter = _resolved_command(tokens, index, cwd)
    if resolved_interpreter is None:
        return False
    try:
        with resolved_interpreter.open("rb") as stream:
            shebang = stream.readline(4096)
    except OSError:
        shebang = b""
    if shebang.startswith(b"#!") and re.search(
        rb"(?:^|[/\s])(?:python(?:[23](?:\.\d+)*)?|pypy(?:[23](?:\.\d+)*)?)(?:\s|$)",
        shebang,
        re.IGNORECASE,
    ):
        return True
    runtime_interpreter = Path(sys.executable).resolve()
    return _is_python_interpreter(resolved_interpreter.name) or _same_executable_content(
        resolved_interpreter,
        runtime_interpreter,
    )


def _python_arguments(tokens: list[ShellToken], cwd: Path) -> list[ShellToken] | None:
    index = _effective_command_index(tokens)
    if index is None:
        return None
    # Bounded search. _effective_command_index has already skipped assignments,
    # `env`, and process wrappers, so an interpreter that is actually being
    # invoked sits within a few tokens of here. Probing every token instead
    # cost a shebang read each, and an 87 KiB command took 10.2s against the
    # host's 10s timeout, where a Copilot timeout fails open (issue #4825).
    #
    # The scan reads shebangs, so it also classifies a Python SCRIPT as an
    # interpreter. That is deliberate and load-bearing: `uv run tools/copy.py`
    # is a real execution whose interpreter this guard cannot name. Relevance
    # therefore filters on the effective COMMAND (see `_operands_are_data`)
    # rather than on the operand, because the operand cannot tell the two
    # apart, and filtering here denied `git diff -- .../new_pr.py`
    # (issue #4764).
    limit = min(len(tokens), index + _MAX_INTERPRETER_SEARCH)
    for candidate_index in range(index, limit):
        if _token_is_python_interpreter(tokens, candidate_index, cwd):
            return tokens[candidate_index + 1 :]
    return None


def _skip_command_wrappers(tokens: list[ShellToken], index: int) -> int:
    while index < len(tokens) and tokens[index].value in {"command", "exec"}:
        wrapper = tokens[index].value
        index += 1
        while index < len(tokens) and tokens[index].value.startswith("-"):
            option = tokens[index].value
            if option == "--":
                index += 1
                break
            if wrapper == "exec" and option == "-a":
                index += 2
                continue
            index += 1
    return index


def _resolve_wrapper_long_option(wrapper: str, value: str) -> tuple[str, bool]:
    option_name, separator, _ = value.partition("=")
    options = _PROCESS_WRAPPER_OPERAND_OPTIONS.get(
        wrapper, frozenset()
    ) | _PROCESS_WRAPPER_FLAG_OPTIONS.get(wrapper, frozenset())
    candidates = {
        option for option in options if option.startswith("--") and option.startswith(option_name)
    }
    if len(option_name) <= 2 or len(candidates) != 1:
        raise GuardViolationError("unsupported process wrapper options are not allowed")
    return candidates.pop(), bool(separator)


def _skip_wrapper_short_options(
    tokens: list[ShellToken],
    index: int,
    wrapper: str,
) -> int:
    value = tokens[index].value
    operand_options = _PROCESS_WRAPPER_OPERAND_OPTIONS.get(wrapper, frozenset())
    flag_options = _PROCESS_WRAPPER_FLAG_OPTIONS.get(wrapper, frozenset())
    for option_index, option_name in enumerate(value[1:]):
        option = f"-{option_name}"
        if option in flag_options:
            continue
        if option not in operand_options:
            raise GuardViolationError("unsupported process wrapper options are not allowed")
        if option_index + 1 < len(value[1:]):
            return index + 1
        if index + 1 >= len(tokens):
            raise GuardViolationError("process wrapper option requires an operand")
        return index + 2
    return index + 1


def _skip_wrapper_options(
    tokens: list[ShellToken],
    index: int,
    wrapper: str,
) -> int:
    operand_options = _PROCESS_WRAPPER_OPERAND_OPTIONS.get(wrapper, frozenset())
    flag_options = _PROCESS_WRAPPER_FLAG_OPTIONS.get(wrapper, frozenset())
    while index < len(tokens) and tokens[index].value.startswith("-"):
        value = tokens[index].value
        if value == "--":
            return index + 1
        if value.startswith("--"):
            option, attached_operand = _resolve_wrapper_long_option(wrapper, value)
            if option in flag_options:
                index += 1
                continue
            if attached_operand:
                index += 1
                continue
            if option in operand_options and index + 1 < len(tokens):
                index += 2
                continue
            raise GuardViolationError("process wrapper option requires an operand")
        index = _skip_wrapper_short_options(tokens, index, wrapper)
    return index


def _skip_process_wrappers(tokens: list[ShellToken], index: int) -> int:
    wrappers = set(_PROCESS_WRAPPER_FLAG_OPTIONS)
    while index < len(tokens):
        wrapper = _command_name(tokens[index].value)
        if wrapper not in wrappers:
            break
        index += 1
        index = _skip_wrapper_options(tokens, index, wrapper)
        if wrapper == "timeout" and index < len(tokens):
            index += 1
    return index


def _contains_shell_evaluator(tokens: list[ShellToken], cwd: Path) -> bool:
    for index, token in enumerate(tokens):
        command_name = _command_name(token.value)
        unversioned_name = _unversioned_command_name(token.value)
        if command_name in _SHELL_EVALUATORS or unversioned_name in _SHELL_EVALUATORS:
            return True
        if (
            command_name in _BUSYBOX_COMMANDS
            and index + 1 < len(tokens)
            and _command_name(tokens[index + 1].value) in _SHELL_EVALUATORS
        ):
            return True
    command_index = _effective_command_index(tokens)
    return command_index is not None and _resolves_to_known_command(
        tokens,
        command_index,
        cwd,
        _SHELL_EVALUATORS,
    )


def _is_dynamic_evaluator_name(value: str) -> bool:
    command_name = _command_name(value)
    unversioned_name = _unversioned_command_name(value)
    return (
        command_name in _DYNAMIC_EVALUATORS
        or command_name in _DEBUG_EVALUATORS
        or unversioned_name in _DYNAMIC_EVALUATORS
        or unversioned_name in _DEBUG_EVALUATORS
    )


def _is_command_delegator(tokens: list[ShellToken], index: int) -> bool:
    command_name = _command_name(tokens[index].value)
    argument_index = index + 1
    if command_name in _BUSYBOX_COMMANDS and argument_index < len(tokens):
        command_name = _command_name(tokens[argument_index].value)
        argument_index += 1
    if command_name in _COMMAND_DELEGATORS:
        return True
    dangerous_environment = _COMMAND_DELEGATION_ENVIRONMENT.get(
        command_name,
        frozenset(),
    )
    for token in tokens[:index]:
        name, separator, _ = token.value.partition("=")
        if separator and name in dangerous_environment:
            return True
    delegation_options = _COMMAND_DELEGATION_OPTIONS.get(command_name, frozenset())
    arguments = tokens[argument_index:]
    for token in arguments:
        value = token.value
        option_name = value.partition("=")[0]
        for option in delegation_options:
            if value == option or value.startswith(f"{option}="):
                return True
            if (
                option.startswith("--")
                and option_name.startswith("--")
                and len(option_name) > 2
                and option.startswith(option_name)
            ):
                return True
            if (
                len(option) == 2
                and option.startswith("-")
                and not option.startswith("--")
                and not value.startswith("--")
                and value.startswith(option)
            ):
                return True
    if command_name == "tar" and arguments:
        first = arguments[0].value
        if not first.startswith("-") and any(option in first for option in {"F", "I"}):
            return True
        if any(
            token.value.startswith("-")
            and not token.value.startswith("--")
            and any(option in token.value[1:] for option in {"F", "I"})
            for token in arguments
        ):
            return True
    return False


def _is_safe_git_config(value: str) -> bool:
    key, separator, configured_value = value.partition("=")
    return bool(
        separator
        and key.casefold().startswith("color.")
        and configured_value.casefold() in {"always", "auto", "false", "never", "true"}
    )


def _has_unsafe_git_remote(value: str) -> bool:
    remote = value.partition("=")[2] or value
    if re.match(r"[A-Za-z][A-Za-z0-9+.-]*::", remote):
        return True
    scheme_match = re.match(r"([A-Za-z][A-Za-z0-9+.-]*)://", remote)
    return bool(
        scheme_match is not None
        and scheme_match.group(1).casefold() not in _GIT_SAFE_REMOTE_SCHEMES
    )


def _is_literal_safe_git_remote(value: str) -> bool:
    if _has_unsafe_git_remote(value):
        return False
    if re.match(r"^[A-Za-z]:", value) or value.startswith(("\\", "//")):
        return False
    scheme_match = re.match(r"([A-Za-z][A-Za-z0-9+.-]*)://", value)
    if scheme_match is not None:
        return scheme_match.group(1).casefold() in _GIT_SAFE_REMOTE_SCHEMES
    if re.match(r"(?:[^/@:]+@)?[^/:]+:.+", value):
        return True
    return False


def _git_remote_operand(
    tokens: list[ShellToken],
    subcommand_index: int,
) -> str | None:
    subcommand = tokens[subcommand_index].value.casefold()
    operand_options = _GIT_OPTION_OPERANDS_BY_SUBCOMMAND.get(
        subcommand,
        frozenset(),
    )
    arguments = tokens[subcommand_index + 1 :]
    index = 0
    while index < len(arguments):
        token = arguments[index]
        value = token.value
        if value in {"--remote", "--repo"}:
            return arguments[index + 1].value if index + 1 < len(arguments) else None
        if value.startswith(("--remote=", "--repo=")):
            return value.partition("=")[2]
        if value == "--":
            return arguments[index + 1].value if index + 1 < len(arguments) else None
        if value.startswith("--"):
            option_name, separator, _ = value.partition("=")
            matches = [
                option
                for option in operand_options
                if option.startswith("--")
                and (
                    option_name == option
                    or (len(option_name) > 2 and option.startswith(option_name))
                )
            ]
            if len(matches) == 1:
                index += 1 if separator else 2
                continue
            index += 1
            continue
        if value.startswith("-"):
            consumed_next = False
            for option_index, option in enumerate(value[1:]):
                if f"-{option}" not in operand_options:
                    continue
                consumed_next = not value[option_index + 2 :]
                break
            index += 2 if consumed_next else 1
            continue
        if not value.startswith("-"):
            return value
        index += 1
    return None


def _git_subcommand_index(tokens: list[ShellToken], command_index: int) -> int | None:
    index = command_index + 1
    safe_flags = {
        "-P",
        "--glob-pathspecs",
        "--icase-pathspecs",
        "--literal-pathspecs",
        "--no-lazy-fetch",
        "--no-advice",
        "--no-optional-locks",
        "--no-pager",
        "--no-replace-objects",
        "--noglob-pathspecs",
    }
    while index < len(tokens):
        value = tokens[index].value
        if value == "-c":
            index += 2
            continue
        if value.startswith("-c") and len(value) > 2:
            index += 1
            continue
        if value in safe_flags:
            index += 1
            continue
        if value.startswith("-"):
            raise GuardViolationError("unsupported Git global options are not allowed")
        return index
    return None


def _is_read_only_git_config(tokens: list[ShellToken], subcommand_index: int) -> bool:
    for token in tokens[subcommand_index + 1 :]:
        value = token.value
        if value in _GIT_CONFIG_READ_MODIFIERS:
            continue
        return value in _GIT_CONFIG_READ_ACTIONS
    return False


def _matches_git_option(
    subcommand: str,
    value: str,
    options: frozenset[str],
) -> bool:
    option_name = value.partition("=")[0]
    for option in options:
        if value == option or value.startswith(f"{option}="):
            return True
        if (
            option.startswith("--")
            and option_name.startswith("--")
            and len(option_name) > 2
            and option.startswith(option_name)
        ):
            return True
        if option.startswith("-") and not option.startswith("--"):
            if len(option) == 2 and not value.startswith("--") and value.startswith(option):
                return True
    if not value.startswith("-") or value.startswith("--"):
        return False
    dangerous_options = {
        option[1]
        for option in options
        if len(option) == 2 and option.startswith("-") and not option.startswith("--")
    }
    operand_options = _GIT_SHORT_CLUSTER_OPERANDS_BY_SUBCOMMAND.get(
        subcommand,
        frozenset(),
    )
    for option in value[1:]:
        if option in dangerous_options:
            return True
        if option in operand_options:
            return False
    return False


def _repository_has_active_git_hooks(cwd: Path) -> bool:
    git = shutil.which("git")
    if git is None:
        return False
    try:
        result = subprocess.run(
            [git, "-C", str(cwd), "rev-parse", "--git-path", "hooks"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    hooks_path = Path(result.stdout.strip())
    if not hooks_path.is_absolute():
        hooks_path = cwd / hooks_path
    try:
        hooks = hooks_path.resolve(strict=True).iterdir()
    except OSError:
        return False
    for hook in hooks:
        try:
            mode = hook.stat().st_mode
        except OSError:
            continue
        if (
            hook.is_file()
            and not hook.name.endswith(".sample")
            and (os.name == "nt" or mode & stat.S_IXUSR)
        ):
            return True
    return False


def _contains_git_execution_delegation(
    tokens: list[ShellToken],
    command_index: int,
    cwd: Path,
) -> bool:
    for token in tokens[:command_index]:
        name, separator, _ = token.value.partition("=")
        if not separator:
            continue
        if name.startswith("GIT_CONFIG_") or name in _GIT_COMMAND_ENVIRONMENT:
            return True

    index = command_index + 1
    while index < len(tokens):
        value = tokens[index].value
        if value == "-c":
            index += 1
            if index >= len(tokens) or not _is_safe_git_config(tokens[index].value):
                return True
        elif value.startswith("-c") and len(value) > 2:
            if not _is_safe_git_config(value[2:]):
                return True
        elif value in _GIT_GLOBAL_EXECUTION_OPTIONS:
            return True
        elif value.startswith(_GIT_GLOBAL_EXECUTION_PREFIXES):
            return True
        if _has_unsafe_git_remote(value):
            return True
        index += 1

    subcommand_index = _git_subcommand_index(tokens, command_index)
    if subcommand_index is None:
        return False
    subcommand = tokens[subcommand_index].value.casefold()
    if subcommand not in _GIT_BUILTIN_COMMANDS:
        return True
    if subcommand == "config" and not _is_read_only_git_config(
        tokens,
        subcommand_index,
    ):
        return True
    if (
        subcommand not in _GIT_HOOK_FREE_SUBCOMMANDS
        and _repository_has_active_git_hooks(cwd)
    ):
        return True
    if subcommand in _GIT_REMOTE_SUBCOMMANDS:
        remote = _git_remote_operand(tokens, subcommand_index)
        if remote is None or not _is_literal_safe_git_remote(remote):
            return True
    execution_options = _GIT_EXECUTION_OPTIONS_BY_SUBCOMMAND.get(
        subcommand,
        frozenset(),
    )
    execution_operands = _GIT_EXECUTION_OPERANDS_BY_SUBCOMMAND.get(
        subcommand,
        frozenset(),
    )
    for token in tokens[subcommand_index + 1 :]:
        if _matches_git_option(subcommand, token.value, execution_options):
            return True
        if token.value.casefold() in execution_operands:
            return True
    return False


def _normalized_git_invocation(
    tokens: list[ShellToken],
    command_index: int,
    cwd: Path,
) -> tuple[list[ShellToken], int] | None:
    command_name = _command_name(tokens[command_index].value)
    if command_name == "git":
        return tokens, command_index
    if command_name.startswith("git-") and len(command_name) > 4:
        subcommand = command_name.removeprefix("git-")
        normalized = list(tokens)
        normalized[command_index] = ShellToken("git", "git")
        normalized.insert(command_index + 1, ShellToken(subcommand, subcommand))
        return normalized, command_index
    if _resolves_to_known_command(
        tokens,
        command_index,
        cwd,
        frozenset({"git"}),
    ):
        return tokens, command_index
    return None


def _contains_dynamic_evaluator(tokens: list[ShellToken], cwd: Path) -> bool:
    index = _effective_command_index(tokens)
    if index is None:
        return False
    command_name = _command_name(tokens[index].value)
    if _resolves_to_known_command(
        tokens,
        index,
        cwd,
        _DYNAMIC_EVALUATORS | _DEBUG_EVALUATORS,
    ):
        return True
    if _is_command_delegator(tokens, index):
        return True
    git_invocation = _normalized_git_invocation(tokens, index, cwd)
    if git_invocation is not None and _contains_git_execution_delegation(
        *git_invocation,
        cwd,
    ):
        return True
    if command_name in _EXPANSION_SAFE_COMMANDS:
        return not _resolves_to_installed_command(
            tokens,
            index,
            cwd,
            _EXPANSION_SAFE_COMMANDS,
        )
    if any(_is_dynamic_evaluator_name(token.value) for token in tokens[index:]):
        return True
    return (
        _command_name(tokens[index].value) in _BUSYBOX_COMMANDS
        and index + 1 < len(tokens)
        and _is_dynamic_evaluator_name(tokens[index + 1].value)
    )


def _effective_command(tokens: list[ShellToken]) -> ShellToken | None:
    index = _effective_command_index(tokens)
    return tokens[index] if index is not None else None


def _effective_command_index(tokens: list[ShellToken]) -> int | None:
    index = 0
    while index < len(tokens) and _is_assignment(tokens[index].value):
        index += 1
    while index < len(tokens):
        index = _skip_command_wrappers(tokens, index)
        index = _skip_process_wrappers(tokens, index)
        if index >= len(tokens):
            return None
        if _command_name(tokens[index].value) in _BUSYBOX_COMMANDS:
            index += 1
            continue
        if _command_name(tokens[index].value) not in _ENV_COMMANDS:
            return index
        command_index = _env_command_index(tokens, index + 1)
        if command_index is None:
            return None
        index = command_index
    return None


def _execution_target(
    arguments: list[ShellToken],
) -> tuple[ShellToken | None, bool]:
    if not arguments:
        return None, False
    value_options = {"-W", "-X", "--check-hash-based-pycs"}
    no_value_short_options = frozenset("bBdEhiIOPqRsSuvVx")
    index = 0
    while index < len(arguments):
        token = arguments[index]
        value = token.value
        if value in {"-c", "-m"}:
            target = arguments[index + 1] if index + 1 < len(arguments) else token
            return target, True
        if value.startswith(("-c", "-m")) and len(value) > 2:
            return ShellToken(token.raw[2:], value[2:]), True
        if value.startswith("-") and not value.startswith("--"):
            cluster = value[1:]
            consumed_value = False
            for option_index, option in enumerate(cluster):
                if option in {"c", "m"}:
                    attached = cluster[option_index + 1 :]
                    if attached:
                        return ShellToken(attached, attached), True
                    target = arguments[index + 1] if index + 1 < len(arguments) else token
                    return target, True
                if option in {"W", "X"}:
                    index += 1 if cluster[option_index + 1 :] else 2
                    consumed_value = True
                    break
                if option not in no_value_short_options:
                    break
            if consumed_value:
                continue
        if value == "--":
            target = arguments[index + 1] if index + 1 < len(arguments) else token
            return target, False
        if value in value_options:
            index += 2
            continue
        if value.startswith(("-W", "-X")) and len(value) > 2:
            index += 1
            continue
        if not value.startswith("-"):
            return token, False
        index += 1
    return None, False


def _targets_new_pr(tokens: list[ShellToken], cwd: Path) -> bool:
    arguments = _python_arguments(tokens, cwd)
    if arguments is not None:
        target, dynamic = _execution_target(arguments)
        if target is not None and (
            _could_target_new_pr(target.value) or _could_target_new_pr(target.raw)
        ):
            return True
        if dynamic and any(
            _could_target_new_pr(argument.value) or _could_target_new_pr(argument.raw)
            for argument in arguments
        ):
            return True
        return any(
            token.value.startswith("PYTHONSTARTUP=")
            and _could_target_new_pr(token.value.partition("=")[2])
            for token in tokens
        )

    target_mentioned = any(
        _could_target_new_pr(token.value) or _could_target_new_pr(token.raw) for token in tokens
    )
    python_mentioned = any(
        _is_python_interpreter(token.value)
        or "python" in token.value.casefold()
        or "pypy" in token.value.casefold()
        for token in tokens
    )
    dynamic_command = any(
        any(marker in token.raw for marker in ("$", "*", "?", "[", "{", "\\\n")) for token in tokens
    )
    command = _effective_command(tokens)
    direct_command = command is not None and (
        _could_target_new_pr(command.value) or _could_target_new_pr(command.raw)
    )
    return target_mentioned and (python_mentioned or dynamic_command or direct_command)


def _script_reference(tokens: list[ShellToken]) -> ShellToken:
    values = [token.value for token in tokens]
    if len(tokens) < 3 or values[:2] != ["python3", "-I"]:
        raise GuardViolationError("new_pr.py must run with python3 -I")
    script_reference = tokens[2]
    if script_reference.value.startswith("-"):
        raise GuardViolationError("new_pr.py script path is missing")
    if script_reference.value != _PLUGIN_SCRIPT_REFERENCE and any(
        marker in script_reference.raw for marker in ("$", "`", "\\\n", "{", "[", "*", "?")
    ):
        raise GuardViolationError("new_pr.py script path cannot use shell expansion")
    if any(("$" in token.raw or "`" in token.raw) for token in tokens[3:]):
        raise GuardViolationError("argument substitution is not allowed")
    if any(_contains_active_shell_expansion(token.raw) for token in tokens[3:]):
        raise GuardViolationError("argument shell expansion is not allowed")
    return script_reference


def _validate_new_pr_arguments(tokens: list[ShellToken], cwd: Path) -> None:
    values: dict[str, str] = {}
    index = 3
    while index < len(tokens):
        option = tokens[index].value
        if option not in {"--title", "--body-file"}:
            raise GuardViolationError("new_pr.py accepts only --title and --body-file here")
        if option in values or index + 1 >= len(tokens):
            raise GuardViolationError(
                f"new_pr.py option {option} is duplicate or missing its value"
            )
        values[option] = tokens[index + 1].value
        index += 2
    if set(values) != {"--title", "--body-file"}:
        raise GuardViolationError("new_pr.py requires exactly --title and --body-file")
    if not values["--title"].strip():
        raise GuardViolationError("new_pr.py title cannot be empty")

    body_reference = Path(values["--body-file"])
    if (
        body_reference.is_absolute()
        or len(body_reference.parts) != 3
        or body_reference.parts[:2] != (".agents", "scratch")
        or body_reference.suffix.casefold() != ".md"
    ):
        raise GuardViolationError(
            "new_pr.py body file must be one .md file directly under .agents/scratch"
        )
    if ".." in body_reference.parts:
        raise GuardViolationError("new_pr.py body file cannot traverse parent directories")
    body_path = cwd / body_reference
    for parent in (cwd / ".agents", cwd / ".agents" / "scratch"):
        if parent.is_symlink():
            raise GuardViolationError("new_pr.py body file parent cannot be a symlink")
    try:
        body_stat = body_path.lstat()
    except OSError as exc:
        raise GuardViolationError("new_pr.py body file must be an existing regular file") from exc
    if body_path.is_symlink() or not stat.S_ISREG(body_stat.st_mode) or body_stat.st_nlink != 1:
        raise GuardViolationError("new_pr.py body file must be a single-link regular file")


def _regular_resolved_file(path: Path) -> Path | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return path.resolve(strict=True)
    except OSError:
        return None


def _require_trusted_digest(path: Path, expected: str, label: str) -> None:
    try:
        with path.open("rb") as stream:
            actual = _sha256_digest(stream).hexdigest()
    except OSError as exc:
        raise GuardViolationError(f"{label} is unreadable") from exc
    if actual != expected:
        raise GuardViolationError(f"{label} does not match the trusted plugin copy")


def _validate_runtime_bundle(script: Path) -> None:
    """Verify every file new_pr.py executes or imports, as one unit.

    ``pr_validations.py`` joined the bundle in issue #4764 when new_pr.py was
    split for cohesion. It MUST be pinned here: new_pr.py loads it by absolute
    path at import time, so an unpinned sibling would be an unverified code
    path inside a script whose whole purpose here is to be verified. Pinning it
    keeps the split from widening the trusted surface.
    """
    _require_trusted_digest(script, _TRUSTED_NEW_PR_SHA256, "new_pr.py")
    for name, expected in (
        ("validate_pr_description.py", _TRUSTED_VALIDATE_PR_DESCRIPTION_SHA256),
        ("pr_validations.py", _TRUSTED_PR_VALIDATIONS_SHA256),
    ):
        helper = _regular_resolved_file(script.parent / name)
        if helper is None:
            raise GuardViolationError(f"{name} is missing, unreadable, or a symlink")
        _require_trusted_digest(helper, expected, name)


def _runtime_script() -> Path | None:
    runtime_root = Path(__file__).resolve().parents[2]
    return _regular_resolved_file(runtime_root / _SCRIPT_RELATIVE_PATH)


def _script_path(script_reference: ShellToken, cwd: Path) -> Path:
    if script_reference.value == _PLUGIN_SCRIPT_REFERENCE:
        if script_reference.raw != f'"{_PLUGIN_SCRIPT_REFERENCE}"':
            raise GuardViolationError(
                "plugin script reference must use the exact double-quoted form"
            )
        configured_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get(
            "CLAUDE_PLUGIN_ROOT"
        )
        root = Path(configured_root) if configured_root is not None else cwd / ".claude"
        if not root.is_absolute():
            root = cwd / root
        path = root / _SCRIPT_RELATIVE_PATH
    else:
        if "$" in script_reference.raw or "`" in script_reference.raw:
            raise GuardViolationError("script path substitution is not allowed")
        path = Path(script_reference.value)
        runtime_script = _runtime_script()
        if runtime_script is None or not path.is_absolute() or path != runtime_script:
            raise GuardViolationError(
                "literal script path must be the exact runtime new_pr.py path"
            )

    resolved = _regular_resolved_file(path)
    if resolved is None:
        raise GuardViolationError("script path is missing, unreadable, or a symlink")
    return resolved


def _deny(reason: str) -> int:
    print(
        "push-pr script identity denied: "
        f"{reason}. Run only the repository or installed-plugin new_pr.py.",
        file=sys.stderr,
    )
    return 2


def main() -> int:
    try:
        command, cwd = _read_request()
        if not _command_is_in_scope(command, cwd):
            return 0
        tokens = _split_command(command)
        if len(tokens) > _MAX_POLICY_TOKENS:
            # In scope and too large to verify. The canonical invocation is
            # seven tokens; nothing legitimate reaches this. Denying here keeps
            # the policy off inputs that cost more than the host's 10s timeout,
            # where a Copilot timeout fails open (issue #4825).
            raise GuardViolationError("command has too many arguments to verify")
        if _contains_dangerous_loader_environment(tokens):
            raise GuardViolationError("dynamic loader environment variables are not allowed")
        if _contains_shell_evaluator(tokens, cwd):
            raise GuardViolationError("shell evaluator wrappers are not allowed")
        if _contains_dynamic_evaluator(tokens, cwd):
            raise GuardViolationError("dynamic evaluator wrappers are not allowed")
        if not _requires_identity_check(command, cwd):
            return 0
        if _contains_shell_expansion(command) and _python_arguments(tokens, cwd) is None:
            raise GuardViolationError(
                "shell-expanded commands outside the exact allowlist are not allowed"
            )
        arguments = _python_arguments(tokens, cwd)
        if arguments is not None:
            target, dynamic = _execution_target(arguments)
            if dynamic:
                raise GuardViolationError("dynamic Python -c and -m launchers are not allowed")
            if (
                target is not None
                and not dynamic
                and _contains_shell_expansion(target.raw)
                and target.raw != f'"{_PLUGIN_SCRIPT_REFERENCE}"'
            ):
                raise GuardViolationError("Python script paths cannot use shell expansion")
        if not _targets_new_pr(tokens, cwd):
            if arguments is not None:
                raise GuardViolationError("Python execution is limited to the approved new_pr.py")
            raise GuardViolationError(
                "command references new_pr.py through an unsupported launcher"
            )
        script_reference = _script_reference(tokens)
        script = _script_path(script_reference, cwd)
        if script != _runtime_script():
            raise GuardViolationError("resolved script is not an approved new_pr.py")
        _validate_runtime_bundle(script)
        _validate_new_pr_arguments(tokens, cwd)
        return 0
    except GuardViolationError as exc:
        return _deny(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
