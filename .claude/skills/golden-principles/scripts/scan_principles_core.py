#!/usr/bin/env python3
# taste-lint: ignore file-size -- git diff-line helpers added for #4007 pushed
# this file from 440 to 513 lines. They cannot be extracted without circular
# imports: they depend on _git_root, _GIT_TIMEOUT_SECONDS, is_safe_path, and
# subprocess, all defined here. A further split is tracked separately.
"""Core types, utilities, and git helpers for the golden-principles scanner.

Split from ``scan_principles.py`` (issue #4028). Rule checkers and the CLI
entry point remain in ``scan_principles.py``; this module holds the shared
foundations that do not change when rules are added or modified.

Exit codes from ``scan_principles.py``:
    0 = clean, 1 = script error, 10 = violations detected.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "EXIT_SUCCESS",
    "EXIT_ERROR",
    "EXIT_VIOLATIONS",
    "SUPPRESSION_PATTERN",
    "ALL_RULES",
    "REQUIRED_SKILL_FIELDS",
    "AGENT_REQUIRED_SECTIONS",
    "SHA_PIN_PATTERN",
    "TAG_PIN_PATTERN",
    "FIRST_PARTY_ACTIONS",
    "Violation",
    "ScanResult",
    "is_safe_path",
    "read_file_lines",
    "has_suppression",
    "get_repo_files",
    "get_diff_files",
    "_ALLOWED_MODEL_ALIASES",
    "_COST_EXCEPTION_ALIASES",
    "_MODEL_FIELD_RE",
    "_check_skill_model_adr080",
    "check_script_language",
    "check_agent_definition",
]

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_VIOLATIONS = 10

SUPPRESSION_PATTERN = re.compile(
    r"#\s*golden-principle:\s*ignore\s+([\w-]+)",
    re.IGNORECASE,
)

ALL_RULES = (
    "script-language",
    "skill-frontmatter",
    "agent-definition",
    "yaml-logic",
    "actions-pinned",
)

REQUIRED_SKILL_FIELDS = ("name", "version", "description", "license")

AGENT_REQUIRED_SECTIONS = ("description", "model")
# ADR-080: skills inherit the harness model by default; model: is optional.
# When present it must be a bare rolling alias (no versioned id) with a
# model-rationale: field. Versioned ids like claude-opus-4-6 are forbidden.
# Per ADR-080 rule 3, model-rationale is a cost exception: only an alias
# priced below the harness default qualifies; in practice that is haiku.
_ALLOWED_MODEL_ALIASES: frozenset[str] = frozenset({"sonnet", "opus", "haiku"})
_COST_EXCEPTION_ALIASES: frozenset[str] = frozenset({"haiku"})
_MODEL_FIELD_RE = re.compile(r"^model:\s*(.*?)\s*$", re.MULTILINE)


# Path markers used to scope rules to their file-type domain. Defined once and
# reused by every checker so the marker appears a single time, keeping the
# upstream-path portability ratchet (issue #2050) at its existing baseline
# instead of growing one ref per checker.
_SKILLS_PATH_MARKER = ".claude/skills/"
_AGENTS_PATH_MARKER = ".claude/agents/"
_WORKFLOWS_PATH_MARKER = ".github/workflows/"

# SHA pattern for pinned actions
SHA_PIN_PATTERN = re.compile(r"uses:\s+[\w-]+/[\w.-]+@([a-f0-9]{40})")
TAG_PIN_PATTERN = re.compile(r"uses:\s+([\w-]+/[\w.-]+)@(v[\d.]+|[\w.-]+)")
FIRST_PARTY_ACTIONS = {"actions/checkout", "actions/setup-python", "actions/setup-node"}

# Bound git subprocess calls so a hung or wedged git process cannot stall the
# diff-scope pre-flight indefinitely.
_GIT_TIMEOUT_SECONDS = 30


@dataclass
class Violation:
    """A detected principle violation with remediation."""

    rule: str
    principle: str
    severity: str
    file: str
    line: int
    message: str
    remediation: str


@dataclass
class ScanResult:
    """Scan result container."""

    files_scanned: int = 0
    applicable_files: int = 0
    violations: list[Violation] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


def is_safe_path(filepath: str) -> bool:
    """Check if a path is safe from path traversal attacks (CWE-22)."""
    if os.path.isabs(filepath):
        return True
    parts = Path(filepath).parts
    return ".." not in parts


def _path_parts(filepath: str) -> tuple[str, ...]:
    """Return path components with Windows separators normalized."""
    return Path(filepath.replace("\\", "/")).parts


def _marker_parts(marker: str) -> tuple[str, ...]:
    """Return path marker components without adding duplicate path literals."""
    return tuple(marker.strip("/").split("/"))


def _has_path_parts(filepath: str, marker: tuple[str, ...]) -> bool:
    """Return True when marker appears as contiguous path components."""
    parts = _path_parts(filepath)
    width = len(marker)
    return any(parts[index : index + width] == marker for index in range(len(parts) - width + 1))


def read_file_lines(filepath: str) -> list[str]:
    """Read file lines, returning empty list on error."""
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except OSError:
        return []


def has_suppression(lines: list[str], rule: str) -> bool:
    """Check if file has a suppression comment for the given rule."""
    for line in lines[:10]:
        match = SUPPRESSION_PATTERN.search(line)
        if match and match.group(1) == rule:
            return True
    return False


def get_repo_files(directory: str) -> list[str]:
    """Recursively collect files, skipping hidden dirs except .claude, .agents, .github."""
    files = []
    for root, dirs, filenames in os.walk(directory):
        dirs[:] = [
            d for d in dirs if not d.startswith(".") or d in (".claude", ".agents", ".github")
        ]
        for filename in filenames:
            filepath = os.path.join(root, filename)
            if is_safe_path(filepath):
                files.append(filepath)
    return sorted(files)


def _git_root() -> str:
    """Return the absolute path of the git working tree root.

    Raises:
        RuntimeError: git is unavailable, times out, or the command fails (for
            example when run outside a repository). Surfacing the failure stops
            the gate from silently anchoring diff paths to the wrong place and
            scanning zero files.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=True,
            encoding="utf-8",
            errors="ignore",
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git is not available to compute --diff-scope") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("git rev-parse --show-toplevel timed out") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"git rev-parse --show-toplevel failed (exit {exc.returncode})") from exc
    return result.stdout.strip()


def get_diff_files(base: str) -> list[str]:
    """Collect files changed in the diff against a base branch.

    Derives the list from `git diff --name-only <base>...HEAD`. Path traversal
    candidates (CWE-22) are dropped, paths are anchored to the git root so they
    resolve regardless of the process working directory, and the result is
    sorted.

    Raises:
        ValueError: ``base`` is empty or starts with ``-`` (CWE-88 argument
            injection: a leading dash would be parsed by git as an option).
        RuntimeError: git is unavailable or the diff command fails (for example
            an unknown base). A git failure must not be mistaken for an empty
            diff, which would let a standards pre-flight pass without scanning.
    """
    if not base or base.startswith("-"):
        raise ValueError(f"invalid --diff-scope base: {base!r}")
    root = _git_root()
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            capture_output=True,
            check=True,
            encoding="utf-8",
            errors="ignore",
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git is not available to compute --diff-scope") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"git diff timed out for base {base!r}") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"git diff failed for base {base!r} (exit {exc.returncode})") from exc
    files = [f for f in result.stdout.splitlines() if f]
    return sorted(os.path.join(root, f) for f in files if is_safe_path(f))


def _parse_hunk_header(header: str) -> tuple[int, int]:
    """Parse a unified-diff hunk header and return (start_line, line_count).

    The header format is ``@@ -a,b +c,d @@`` where ``c`` is the starting line
    in the new file and ``d`` is the number of lines in the hunk.  A missing
    comma means the hunk is exactly one line (implicit count of 1).
    """
    match = re.search(r"\+(\d+)(?:,(\d+))?", header)
    if not match:
        return 0, 0
    start = int(match.group(1))
    count = int(match.group(2)) if match.group(2) is not None else 1
    return start, count


def _run_git_diff(base: str) -> str:
    """Return the unified-diff output for *base*...HEAD.

    Raises ``RuntimeError`` on git failure so callers can treat an error as
    non-empty (fail safe: report violations rather than silently skip them).
    """
    if not base or base.startswith("-"):
        raise ValueError(f"invalid --diff-scope base: {base!r}")
    root = _git_root()
    try:
        result = subprocess.run(
            ["git", "diff", "-U0", f"{base}...HEAD"],
            capture_output=True,
            check=True,
            cwd=root,
            encoding="utf-8",
            errors="ignore",
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git is not available to compute diff lines") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"git diff timed out for base {base!r}") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"git diff failed for base {base!r} (exit {exc.returncode})") from exc
    return result.stdout


def get_diff_line_numbers(base: str) -> dict[str, set[int]]:
    """Return a mapping of absolute file path to changed line numbers.

    Each value is the set of *new-file* line numbers that appear in a unified
    diff hunk for that file against ``base...HEAD``.  Only added or context
    lines are counted; removed lines (prefixed with ``-``) are not in the new
    file and are excluded.

    When ``base`` is empty or ``None`` the function returns an empty dict so
    callers treat every line as changed (no filtering).
    """
    if not base:
        return {}
    raw = _run_git_diff(base)
    result: dict[str, set[int]] = {}
    current_file: str | None = None
    current_line = 0
    root = _git_root()
    for line in raw.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            abs_path = os.path.join(root, path)
            current_file = abs_path if is_safe_path(path) else None
            current_line = 0
        elif line.startswith("@@ "):
            start, _ = _parse_hunk_header(line)
            current_line = start
        elif current_file is not None and line.startswith("-"):
            pass  # removed line; no position in new file
        elif current_file is not None:
            if current_line > 0:
                result.setdefault(current_file, set()).add(current_line)
            current_line += 1
    return result


# Re-export path-marker helpers for use by checkers in scan_principles.py.
# These are module-private in spirit but must be visible to the sibling module.


def check_script_language(filepath: str, lines: list[str]) -> list[Violation]:
    """GP-001: No new .sh or .bash files."""
    suffix = Path(filepath).suffix
    if suffix not in (".sh", ".bash"):
        return []
    if has_suppression(lines, "script-language"):
        return []
    return [
        Violation(
            rule="script-language",
            principle="GP-001",
            severity="error",
            file=filepath,
            line=0,
            message=f"Shell script detected: {Path(filepath).name}",
            remediation=(
                "AGENT_REMEDIATION: Convert this shell script to Python per ADR-042.\n"
                "  1. Create a new Python file with the same base name\n"
                "  2. Use subprocess.run() for shell commands that have no Python equivalent\n"
                "  3. Use pathlib.Path for file operations\n"
                "  4. Add argparse for CLI arguments\n"
                "  5. Delete the original shell script"
            ),
        )
    ]


def _check_skill_model_adr080(filepath: str, frontmatter: str) -> list[Violation]:
    """ADR-080: validate model field in skill frontmatter when present.

    Blank values, versioned ids, non-cost-exception aliases, and aliases
    missing a rationale are all errors. Returns [] when model is absent or valid.
    """
    model_match = _MODEL_FIELD_RE.search(frontmatter)
    if not model_match:
        return []
    model_value = model_match.group(1).strip()
    if model_value == "":
        return [
            Violation(
                rule="skill-frontmatter",
                principle="GP-003",
                severity="error",
                file=filepath,
                line=1,
                message=(
                    "SKILL.md model field violates ADR-080: blank value;"
                    " omit the model: field to inherit the harness default"
                ),
                remediation=(
                    "AGENT_REMEDIATION: Per ADR-080, omitting model: inherits the harness"
                    " default, which is the correct default for skills.\n"
                    "  Remove the empty model: line."
                ),
            )
        ]
    if model_value not in _ALLOWED_MODEL_ALIASES:
        return [
            Violation(
                rule="skill-frontmatter",
                principle="GP-003",
                severity="error",
                file=filepath,
                line=1,
                message=(
                    f"SKILL.md model field violates ADR-080: '{model_value}' is a versioned"
                    " id; use a rolling alias (sonnet / opus / haiku) or omit the field"
                ),
                remediation=(
                    "AGENT_REMEDIATION: Per ADR-080, skills must not carry a versioned"
                    " model id.\n"
                    "  Remove the model: field to inherit the harness default, or use a"
                    " rolling alias with a cost rationale:\n"
                    "    model: haiku\n"
                    "    model-rationale: Cost-sensitive; haiku suffices for this task."
                ),
            )
        ]
    if model_value not in _COST_EXCEPTION_ALIASES:
        return [
            Violation(
                rule="skill-frontmatter",
                principle="GP-003",
                severity="error",
                file=filepath,
                line=1,
                message=(
                    f"SKILL.md model field violates ADR-080: '{model_value}' is not a"
                    " cost-exception alias; per ADR-080 rule 3, only 'haiku' resolves"
                    " to a version priced below the harness default"
                ),
                remediation=(
                    "AGENT_REMEDIATION: Per ADR-080 rule 3, model-rationale is a cost"
                    " exception only for haiku.\n"
                    "  Omit the model: field to inherit the harness default, or replace"
                    " with haiku if this skill needs cost-tier pricing:\n"
                    "    model: haiku\n"
                    "    model-rationale: Cost-sensitive; haiku suffices for this task."
                ),
            )
        ]
    if "model-rationale:" not in frontmatter:
        return [
            Violation(
                rule="skill-frontmatter",
                principle="GP-003",
                severity="error",
                file=filepath,
                line=1,
                message=(
                    f"SKILL.md model field violates ADR-080: alias '{model_value}'"
                    " requires a model-rationale: field"
                ),
                remediation=(
                    "AGENT_REMEDIATION: Per ADR-080, a rolling alias requires a cost"
                    " rationale.\n"
                    "  Add model-rationale: explaining why this skill uses a cheaper"
                    " model:\n"
                    "    model-rationale: Cost-sensitive; haiku suffices for this task."
                ),
            )
        ]
    return []


def check_agent_definition(filepath: str, lines: list[str]) -> list[Violation]:
    """GP-004: Agent definitions must have required frontmatter."""
    if not filepath.endswith(".md"):
        return []
    if not _has_path_parts(filepath, _marker_parts(_AGENTS_PATH_MARKER)):
        return []
    if Path(filepath).name in ("CLAUDE.md",):
        return []
    if has_suppression(lines, "agent-definition"):
        return []

    content = "".join(lines)
    if not content.startswith("---"):
        return [
            Violation(
                rule="agent-definition",
                principle="GP-004",
                severity="error",
                file=filepath,
                line=1,
                message="Agent definition missing YAML frontmatter",
                remediation=(
                    "AGENT_REMEDIATION: Add YAML frontmatter with required fields.\n"
                    "  ---\n"
                    "  name: agent-name\n"
                    "  description: What the agent does\n"
                    "  model: sonnet\n"
                    "  ---"
                ),
            )
        ]

    parts = content.split("---", 2)
    if len(parts) < 3:
        return []

    frontmatter = parts[1]
    missing = [f for f in AGENT_REQUIRED_SECTIONS if f"{f}:" not in frontmatter]
    if missing:
        return [
            Violation(
                rule="agent-definition",
                principle="GP-004",
                severity="warning",
                file=filepath,
                line=1,
                message=f"Agent definition missing fields: {', '.join(missing)}",
                remediation=(
                    "AGENT_REMEDIATION: Add the missing frontmatter fields:\n"
                    + "\n".join(f"  {f}: <value>" for f in missing)
                ),
            )
        ]
    return []


_SKILLS_PATH_PARTS = _marker_parts(_SKILLS_PATH_MARKER)
_AGENTS_PATH_PARTS = _marker_parts(_AGENTS_PATH_MARKER)
_WORKFLOWS_PATH_PARTS = _marker_parts(_WORKFLOWS_PATH_MARKER)
