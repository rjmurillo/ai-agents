#!/usr/bin/env python3
"""Taste invariant linter with agent-readable remediation instructions.

Exit codes: 0 = clean, 1 = script error, 10 = violations detected.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_VIOLATIONS = 10

# Frontmatter is metadata. A block that has not closed by here is not
# frontmatter, and bounding the scan keeps _suppression_window cheap on every
# file in the repository.
_MAX_FRONTMATTER_LINES = 50

SUPPRESSION_PATTERN = re.compile(
    r"#\s*taste-lint:\s*ignore\s+([\w-]+)",
    re.IGNORECASE,
)

ALL_RULES = ("file-size", "naming", "complexity", "skill-size")

# File extensions to scan
SCANNABLE_EXTENSIONS = {
    ".py",
    ".ps1",
    ".psm1",
    ".sh",
    ".bash",
    ".yml",
    ".yaml",
    ".md",
    ".json",
}

# Path segments holding captured or generated JSON that is exempt from the
# file-size rule. A line ceiling is the wrong gate for these: the content has no
# boundaries to split on, and JSON cannot carry a `# taste-lint: ignore`
# suppression comment, so a path exemption is the only mechanism available.
#
# The exemption requires the `.json` suffix as well as the path. The rationale
# above is about JSON specifically, and without the suffix condition the
# exemption reached every authored file that happened to sit in one of these
# directories: a 913-line markdown catalog and a 542-line XML spec under
# `sessions/` were silently excused, and both have ordinary section boundaries
# to split on.
#
#   memory/: the episode-extraction hook appends an episode record on every
#   session-log commit (issue #2785).
#
#   analysis/eval-artifacts/: raw eval result files, archived so the numbers
#   published in an analysis can be re-derived instead of taken on faith.
#   Splitting one would break the provenance it exists to provide, and the
#   file-size remediation text proposes extracting "helper functions" from a
#   JSON dump, which is advice no author can act on (issue #3970).
#
#   sessions/: session logs carry one workLog entry per step by convention, so
#   length tracks how much work a session did and nothing else.
#   validate_session_json.py validates one file per session, so splitting one
#   is not available either.
_AGENT_STATE_DIR = ".agents"

FILE_SIZE_EXEMPT_SUFFIX = ".json"

FILE_SIZE_EXEMPT_SEGMENTS: tuple[tuple[str, ...], ...] = (
    (_AGENT_STATE_DIR, "memory"),
    (_AGENT_STATE_DIR, "analysis", "eval-artifacts"),
    (_AGENT_STATE_DIR, "sessions"),
)

_GENERATED_PATH_SEGMENTS: tuple[tuple[str, ...], ...] = (
    ("src", "copilot-cli"),
    ("src", "vs-code-agents"),
    (".github", "instructions"),
)
_GENERATED_MARKERS = (
    "AUTO-GENERATED MATCHER SHIM",
    "GENERATED -- DO NOT EDIT",
    "DO NOT EDIT BY HAND - regenerated",
)
# Match markers within the leading header window only. Authored files that
# mention a marker string deeper in the body (generator scripts, this
# classifier's own marker tuple) must not be misread as generated. 20 lines
# clears every real generated header while excluding those in-body literals.
_GENERATED_MARKER_HEADER_LINES = 20


@functools.lru_cache(maxsize=8)
def _git_root_for_cwd(cwd: str) -> str | None:
    """Return the git working-tree root for ``cwd``, or None outside a repo.

    Cached per working directory so classifying many files does not spawn one
    ``git rev-parse`` per file. ``cwd`` is an explicit cache key because the
    root depends on the process working directory, which tests change.
    """
    try:
        return _git_root()
    except RuntimeError:
        return None


def _repo_relative_parts(path: Path) -> tuple[str, ...]:
    """Return path parts for segment matching, relative to the repo root.

    ``_GENERATED_PATH_SEGMENTS`` are repo-root-anchored, and ``get_diff_files``
    anchors diff paths to the git root so they resolve regardless of the process
    working directory. Relativizing here against the git root (not CWD) keeps the
    anchored match correct from any subdirectory: the git root is tried first,
    CWD second (non-repo callers and tests), and an unrelativizable path falls
    back to its own parts unchanged.
    """
    if path.is_absolute():
        for anchor in (_git_root_for_cwd(os.getcwd()), os.getcwd()):
            if anchor is None:
                continue
            try:
                return path.relative_to(anchor).parts
            except ValueError:
                continue
    return path.parts


def _generated_by_path(path: Path) -> bool:
    """True when the path alone marks a file generated (no body read needed)."""
    parts = _repo_relative_parts(path)
    if any(parts[: len(segment)] == segment for segment in _GENERATED_PATH_SEGMENTS):
        return True
    return path.name.startswith("pr-quality-gate-") and ".github" in parts


def classify_file_category(filepath: str, lines: list[str]) -> str:
    """Classify a file as authored, test, or generated."""
    path = Path(filepath)
    if _generated_by_path(path):
        return "generated"
    header = "".join(lines[:_GENERATED_MARKER_HEADER_LINES])
    if any(marker in header for marker in _GENERATED_MARKERS):
        return "generated"
    if "tests" in _repo_relative_parts(path) or path.name.startswith("test_"):
        return "test"
    return "authored"


@dataclass
class Violation:
    """A detected taste violation with remediation."""

    rule: str
    severity: str
    file: str
    line: int
    message: str
    remediation: str
    category: str = "authored"


@dataclass
class LintResult:
    """Lint result container."""

    files_scanned: int = 0
    files_by_category: dict[str, int] = field(default_factory=dict)
    violations: list[Violation] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


def is_safe_path(filepath: str) -> bool:
    """Check if a path is safe from path traversal attacks (CWE-22).

    For relative paths: rejects any path containing '..' in components.
    For absolute paths: allows them (relies on OS permissions for access control).
    """
    # Allow absolute paths (rely on OS permissions)
    if os.path.isabs(filepath):
        return True
    # Reject relative paths with '..' traversal
    parts = Path(filepath).parts
    return ".." not in parts


def get_staged_files() -> list[str]:
    """Get the sorted list of staged files from git.

    Output is sorted so ordering is deterministic and consistent with the
    diff-scope and directory modes.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            check=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SECONDS,
        )
        files = [f for f in result.stdout.splitlines() if f]
        # Filter out any paths with traversal attempts (CWE-22)
        return sorted(f for f in files if is_safe_path(f))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return []


# Bound git subprocess calls so a hung or wedged git process cannot stall the
# diff-scope pre-flight indefinitely.
_GIT_TIMEOUT_SECONDS = 30


def _git_root() -> str:
    """Return the absolute path of the git working tree root.

    Raises:
        RuntimeError: git is unavailable, times out, or the command fails (for
            example when run outside a repository). Surfacing the failure stops
            the gate from silently anchoring diff paths to the wrong place and
            linting zero files.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=True,
            encoding="utf-8",
            errors="replace",
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
    """Get list of files changed in the diff against a base branch.

    Derives the list from `git diff --name-only <base>...HEAD`. Path traversal
    candidates (CWE-22) are dropped, paths are anchored to the git root so they
    resolve regardless of the process working directory, and the result is
    sorted so output ordering is deterministic and consistent with the directory
    and staged modes.

    Raises:
        ValueError: ``base`` is empty or starts with ``-`` (CWE-88 argument
            injection: a leading dash would be parsed by git as an option).
        RuntimeError: git is unavailable or the diff command fails (for example
            an unknown base). A git failure must not be mistaken for an empty
            diff, which would let a standards pre-flight pass without linting.
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
            errors="replace",
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

    Raises ``RuntimeError`` on git failure so callers treat an error as
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
            errors="replace",
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


def get_base_file_line_count(filepath: str) -> int:
    """Return the number of lines in *filepath*, or 0 if unreadable."""
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def get_files_from_directory(directory: str) -> list[str]:
    """Recursively get scannable files from a directory."""
    files = []
    for root, _dirs, filenames in os.walk(directory):
        for filename in filenames:
            filepath = os.path.join(root, filename)
            if Path(filepath).suffix in SCANNABLE_EXTENSIONS:
                files.append(filepath)
    return sorted(files)


def read_file_lines(filepath: str) -> list[str]:
    """Read file lines, returning empty list on error."""
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except OSError:
        return []


# A YAML mapping key: a token with no whitespace or colon in it, then a colon
# that is followed by whitespace or ends the line. The trailing requirement is
# what separates `explainer: https://example.com` (a key whose value is a URL)
# from `See https://example.com for details` (prose whose only colon belongs to
# a URL scheme). Matching a bare colon anywhere in the line classified the
# second as a mapping and widened the suppression window past an unrelated
# `---` later in the file, which is the regression this whole check prevents.
_YAML_KEY_LINE = re.compile(r"[^\s:]+\s*:(\s|$)")

def _looks_like_yaml_mapping(block: list[str]) -> bool:
    """True when ``block`` has the shape of a YAML mapping.

    Deliberately a stdlib shape check rather than ``yaml.safe_load``. This
    linter is invoked with a bare ``python3`` in seven places in its own
    SKILL.md, and a job whose only preceding step is a checkout has installed
    nothing, so a third-party import here fails at module load and takes the
    gate red on every PR (`.claude/rules/ci-scripts.md` MUST-18). The question
    is only "is this frontmatter or a horizontal rule", which does not need a
    parser.

    A mapping needs at least one top-level ``key:`` line, and every non-blank,
    non-comment line must be either such a key or an indented continuation of
    one. Prose under a horizontal rule fails on its first unindented line.
    """
    saw_key = False
    for raw in block:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line[:1] in {" ", "\t"} or stripped.startswith("- "):
            continue  # continuation: nested mapping, list item, folded scalar
        if not _YAML_KEY_LINE.match(stripped):
            return False
        saw_key = True
    return saw_key


def _suppression_window(lines: list[str]) -> list[str]:
    """Lines a suppression may appear in: any frontmatter block, plus 10 more.

    The window means "near the top of the file", not "the first 10 bytes of
    metadata". Both placements are in use in this repository and both must keep
    working:

    - Inside the frontmatter, as a YAML comment on line 2. ADR-068 and ADR-085
      do this ("accepted append-only record; splitting breaks audit
      continuity").
    - After the frontmatter, as an HTML comment under the title. ADR-035 does
      this.

    A plain first-10-lines window only sees the first. ADR-073 lifecycle
    frontmatter is exactly 10 lines (``---``, eight keys, ``---``), so on a
    record carrying it the window closes before any content is read: ADR-035's
    suppression sat at line 3, moved to line 14 when the issue #5190 backfill
    added frontmatter, and silently stopped counting.

    Widening rather than shifting is deliberate. This window is a strict
    superset of the old one, so it cannot retire a suppression that works today.
    An earlier attempt skipped the frontmatter instead and broke ADR-068 and
    ADR-085, which is the failure this docstring exists to prevent recurring.

    A closing delimiter is not sufficient on its own. A document that opens with
    a horizontal rule and carries an unrelated ``---`` separator far below would
    otherwise have its window widened to that separator, silently disabling a
    lint hundreds of lines from any real suppression. So the block must also
    parse as a YAML mapping, which is what frontmatter is. A horizontal rule
    followed by prose does not.

    The scan for the closing delimiter is bounded. Frontmatter is metadata, so a
    block that has not closed within ``_MAX_FRONTMATTER_LINES`` is not
    frontmatter, and stopping there keeps this cheap on every file in the repo.
    """
    if not lines or lines[0].strip() != "---":
        return lines[:10]

    for index in range(1, min(len(lines), _MAX_FRONTMATTER_LINES)):
        if lines[index].strip() not in {"---", "..."}:
            continue
        if _looks_like_yaml_mapping(lines[1:index]):
            return lines[: index + 11]
        return lines[:10]
    return lines[:10]


def has_suppression(lines: list[str], rule: str) -> bool:
    """Check if file has a suppression comment for the given rule."""
    for line in _suppression_window(lines):
        match = SUPPRESSION_PATTERN.search(line)
        if match and match.group(1) == rule:
            return True
    return False


def _is_file_size_exempt(filepath: str) -> bool:
    """True when filepath is captured JSON under a dir exempt from file-size.

    Both conditions are required. The exempt segment must anchor at the START of
    the repository-relative path, not match anywhere in it. Otherwise a checkout
    whose parent directories happen to contain ``.agents/memory`` (for example a
    clone under ``/home/me/.agents/memory/repo``) would leak the exemption to
    unrelated files. The suffix must be ``.json``, because the reason these
    directories are exempt at all is that JSON cannot carry a suppression
    comment; an authored markdown or XML file sitting in one of them has
    ordinary boundaries to split on and is not excused.

    Absolute paths are first made relative to the current working directory (the
    linter runs from the repo root); a path outside the repo is never exempt.
    """
    path = Path(filepath).expanduser()
    if path.suffix.lower() != FILE_SIZE_EXEMPT_SUFFIX:
        return False
    if path.is_absolute():
        try:
            parts = path.resolve().relative_to(Path.cwd().resolve()).parts
        except ValueError:
            return False
    else:
        parts = path.parts
    return any(parts[: len(segment)] == segment for segment in FILE_SIZE_EXEMPT_SEGMENTS)


# Extensions that hold structured data rather than authored source code. The
# file-size rule still fires (oversized data files do affect context cost and
# ratchet counts), but the remediation text for these files must not suggest
# extracting helper functions or type definitions. Issue #3970.
_DATA_EXTENSIONS: frozenset[str] = frozenset({".json", ".yaml", ".yml"})


def check_file_size(filepath: str, lines: list[str]) -> list[Violation]:
    """Check file line count against thresholds."""
    if _is_file_size_exempt(filepath):
        return []
    if has_suppression(lines, "file-size"):
        return []
    line_count = len(lines)
    is_data_file = Path(filepath).suffix.lower() in _DATA_EXTENSIONS
    if line_count > 500:
        if is_data_file:
            remediation = (
                "AGENT_REMEDIATION: Data file exceeds 500 lines. Options:\n"
                "  1. Shard by a natural key (e.g. date, id range, category)\n"
                "  2. Exempt the path in FILE_SIZE_EXEMPT_SEGMENTS if the file\n"
                "     is append-only generated data with no module boundary.\n"
                "  Target: each shard under 500 lines or path-exempt the directory."
            )
        else:
            bn = Path(filepath).stem
            sx = Path(filepath).suffix
            remediation = (
                f"AGENT_REMEDIATION: Split this file into smaller modules. "
                f"Consider extracting:\n"
                f"  1. Helper functions -> {bn}_helpers{sx}\n"
                f"  2. Type definitions -> {bn}_types{sx}\n"
                f"  3. Constants -> {bn}_constants{sx}\n"
                f"  Target: each module under 300 lines for good cohesion."
            )
        return [
            Violation(
                rule="file-size",
                severity="error",
                file=filepath,
                line=line_count,
                message=f"File exceeds 500 lines ({line_count} lines)",
                remediation=remediation,
            )
        ]
    if line_count > 300:
        if is_data_file:
            remediation = (
                "AGENT_REMEDIATION: Data file is growing large. If it is "
                "append-only generated data, consider exempting the path in "
                "FILE_SIZE_EXEMPT_SEGMENTS or sharding by a natural key before "
                "it exceeds 500 lines."
            )
        else:
            remediation = (
                "AGENT_REMEDIATION: File is growing large. Plan extraction "
                "before it exceeds 500 lines. Look for:\n"
                "  1. Groups of related functions that form a cohesive module\n"
                "  2. Data classes or constants that can be separated\n"
                "  3. Test helpers that belong in a conftest or fixture file"
            )
        return [
            Violation(
                rule="file-size",
                severity="warning",
                file=filepath,
                line=line_count,
                message=f"File approaching size limit ({line_count}/500 lines)",
                remediation=remediation,
            )
        ]
    return []


def _check_python_naming(filepath: str, name: str, suffix: str) -> Violation | None:
    # An optional single leading underscore marks a private module (PEP 8,
    # "internal use"); the rest is snake_case. Without the `_?` the rule
    # flags every `_private_module.py` in the repo (e.g. scripts/eval/_*).
    # See issue #2795.
    if name == "__init__" or re.match(r"^_?[a-z][a-z0-9_]*$", name):
        return None
    path = Path(filepath)
    return Violation(
        rule="naming",
        severity="error",
        file=filepath,
        line=0,
        message=f"Python file '{name}{suffix}' is not snake_case",
        remediation=(
            f"AGENT_REMEDIATION: Rename to snake_case. "
            f"Suggested: {_to_snake_case(name)}{suffix}\n"
            f"  Update all imports that reference this module.\n"
            f"  Run: git mv {filepath} "
            f"{path.parent / (_to_snake_case(name) + suffix)}"
        ),
    )


def _check_yaml_naming(filepath: str, name: str, suffix: str) -> Violation | None:
    if re.match(r"^[a-z][a-z0-9-]*$", name) or name in ("CLAUDE", "project", "settings"):
        return None
    return Violation(
        rule="naming",
        severity="warning",
        file=filepath,
        line=0,
        message=f"YAML file '{name}{suffix}' is not kebab-case",
        remediation=(
            f"AGENT_REMEDIATION: Rename to kebab-case. "
            f"Suggested: {_to_kebab_case(name)}{suffix}\n"
            f"  Update any references in workflows or configs."
        ),
    )


def _check_hook_naming(filepath: str, name: str, suffix: str) -> Violation | None:
    # Entrypoint hooks require the invoke_ prefix so settings.json and the
    # dispatcher can resolve them. Non-entrypoint modules that legitimately live
    # in the hooks tree are exempt: private/dunder helpers (leading underscore,
    # e.g. _bootstrap.py, __init__.py) and shared framework base classes
    # (*_base.py, e.g. push_guard_base.py). See issue #3239.
    if name.startswith("invoke_") or name.startswith("_") or name.endswith("_base"):
        return None
    return Violation(
        rule="naming",
        severity="error",
        file=filepath,
        line=0,
        message=f"Hook script '{name}{suffix}' missing 'invoke_' prefix",
        remediation=(
            f"AGENT_REMEDIATION: Hook scripts must use invoke_ prefix "
            f"for consistency.\n"
            f"  Rename to: invoke_{name}{suffix}\n"
            f"  Update .claude/settings.json hook command references."
        ),
    )


def _check_skill_dir_naming(filepath: str) -> Violation | None:
    parts = Path(filepath).parts
    try:
        skills_idx = parts.index("skills")
    except ValueError:
        return None
    if skills_idx + 1 >= len(parts):
        return None
    skill_dir = parts[skills_idx + 1]
    if re.match(r"^[a-z][a-z0-9-]*$", skill_dir) or skill_dir == "CLAUDE.md":
        return None
    return Violation(
        rule="naming",
        severity="warning",
        file=filepath,
        line=0,
        message=f"Skill directory '{skill_dir}' is not kebab-case",
        remediation=(
            f"AGENT_REMEDIATION: Skill directories use kebab-case.\n"
            f"  Rename: {skill_dir} -> {_to_kebab_case(skill_dir)}\n"
            f"  Update SKILL.md name field to match."
        ),
    )


def check_naming(filepath: str, _lines: list[str]) -> list[Violation]:
    """Check file naming conventions."""
    if has_suppression(_lines, "naming"):
        return []

    violations: list[Violation] = []
    name = Path(filepath).stem
    suffix = Path(filepath).suffix

    checkers: list[tuple[bool, Callable[[], Violation | None]]] = [
        (suffix == ".py", lambda: _check_python_naming(filepath, name, suffix)),
        (suffix in (".yml", ".yaml"), lambda: _check_yaml_naming(filepath, name, suffix)),
        (
            ".claude/hooks/" in filepath and suffix == ".py",
            lambda: _check_hook_naming(filepath, name, suffix),
        ),
        (".claude/skills/" in filepath, lambda: _check_skill_dir_naming(filepath)),
    ]
    for condition, checker in checkers:
        if condition:
            v = checker()
            if v:
                violations.append(v)

    return violations


def _emit_if_complex(
    violations: list[Violation],
    filepath: str,
    func_name: str | None,
    func_line: int,
    branch_count: int,
) -> None:
    """Append a complexity violation if the function exceeds the threshold."""
    if func_name and branch_count > 10:
        violations.append(_complexity_violation(filepath, func_name, func_line, branch_count))


def _is_func_body_end(line: str, indent: int, func_indent: int) -> bool:
    """Check if a line signals the end of a function body."""
    if indent > func_indent:
        return False
    if line.strip().startswith("#"):
        return False
    return not re.match(r"^\s*def\s+", line)


def check_complexity(filepath: str, lines: list[str]) -> list[Violation]:
    """Check function complexity (Python only, simple branch counting)."""
    if Path(filepath).suffix != ".py" or has_suppression(lines, "complexity"):
        return []

    violations: list[Violation] = []
    branch_keywords = re.compile(r"^\s*(if |elif |for |while |except |with )")
    current_func: str | None = None
    current_func_line = 0
    func_indent = 0
    branch_count = 0

    for i, line in enumerate(lines, 1):
        if not line.rstrip():
            continue

        indent = len(line) - len(line.lstrip())
        func_match = re.match(r"^(\s*)def\s+(\w+)", line)

        if func_match:
            _emit_if_complex(violations, filepath, current_func, current_func_line, branch_count)
            func_indent = len(func_match.group(1))
            current_func = func_match.group(2)
            current_func_line = i
            branch_count = 1
            continue

        if current_func and indent > func_indent and branch_keywords.match(line):
            branch_count += 1

        if current_func and _is_func_body_end(line, indent, func_indent):
            _emit_if_complex(violations, filepath, current_func, current_func_line, branch_count)
            current_func = None

    _emit_if_complex(violations, filepath, current_func, current_func_line, branch_count)
    return violations


def _complexity_violation(
    filepath: str,
    func_name: str,
    line: int,
    complexity: int,
) -> Violation:
    return Violation(
        rule="complexity",
        severity="error",
        file=filepath,
        line=line,
        message=f"Function '{func_name}' has complexity {complexity} (max 10)",
        remediation=(
            f"AGENT_REMEDIATION: Decompose '{func_name}' to reduce complexity.\n"
            f"  1. Extract conditional branches into named helper methods\n"
            f"  2. Use early returns to flatten nested conditions\n"
            f"  3. Replace complex conditionals with strategy pattern or lookup tables\n"
            f"  Target: cyclomatic complexity <= 10 per function."
        ),
    )


def check_skill_size(filepath: str, lines: list[str]) -> list[Violation]:
    """Check skill SKILL.md files for size limits."""
    if not filepath.endswith("SKILL.md") or ".claude/skills/" not in filepath:
        return []
    if has_suppression(lines, "skill-size"):
        return []
    if "size-exception: true" in "".join(lines[:20]):
        return []
    line_count = len(lines)
    if line_count > 500:
        sd = Path(filepath).parent.name
        return [
            Violation(
                rule="skill-size",
                severity="error",
                file=filepath,
                line=line_count,
                message=f"Skill prompt exceeds 500 lines ({line_count} lines)",
                remediation=(
                    f"AGENT_REMEDIATION: Refactor using progressive disclosure:\n"
                    f"  1. Move reference docs -> {sd}/references/\n"
                    f"  2. Extract reusable logic -> {sd}/scripts/\n"
                    f"  3. Use templates -> {sd}/templates/\n"
                    f"  Or add 'size-exception: true' to frontmatter if justified."
                ),
            )
        ]
    if line_count > 300:
        return [
            Violation(
                rule="skill-size",
                severity="warning",
                file=filepath,
                line=line_count,
                message=f"Skill prompt approaching limit ({line_count}/500 lines)",
                remediation=(
                    "AGENT_REMEDIATION: Plan progressive disclosure refactoring "
                    "before exceeding 500 lines.\n"
                    "  Move reference material to references/ subdirectory."
                ),
            )
        ]
    return []


def _to_snake_case(name: str) -> str:
    """Convert a name to snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.replace("-", "_").lower()


def _to_kebab_case(name: str) -> str:
    """Convert a name to kebab-case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1-\2", s)
    return s.replace("_", "-").lower()


RULE_CHECKERS = {
    "file-size": check_file_size,
    "naming": check_naming,
    "complexity": check_complexity,
    "skill-size": check_skill_size,
}


def _filter_violations_for_diff(
    violations: list[Violation],
    filepath: str,
    diff_lines: dict[str, set[int]],
    diff_base: str,
) -> list[Violation]:
    """Keep only violations whose line numbers fall within the diff.

    A violation with ``line == 0`` is file-level (e.g. file-size).  File-level
    violations are kept only when the file grew in this diff, i.e. the new
    line count exceeds the line count at ``diff_base``.  A file already over
    the threshold that did not grow further is suppressed: its size violation
    was pre-existing, not introduced by this PR.  Any other violation is kept
    only if its line number appears in the changed-line set for that file.

    When ``filepath`` is not in ``diff_lines`` (no changed lines recorded for
    the file), all violations are suppressed so pre-existing issues in
    unchanged files are not reported.
    """
    if filepath not in diff_lines:
        return []
    changed = diff_lines[filepath]
    result = []
    for v in violations:
        if v.line == 0:
            try:
                root = _git_root()
                rel = os.path.relpath(filepath, root)
                proc = subprocess.run(
                    ["git", "show", f"{diff_base}:{rel}"],
                    capture_output=True,
                    check=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=_GIT_TIMEOUT_SECONDS,
                )
                old_count = proc.stdout.count("\n")
            except Exception:
                old_count = 0
            new_count = get_base_file_line_count(filepath)
            if new_count > old_count:
                result.append(v)
        elif v.line in changed:
            result.append(v)
    return result


def _lint_file_rules(
    filepath: str,
    lines: list[str],
    rules: tuple[str, ...],
    category: str,
) -> list[Violation]:
    """Run all rule checkers for a single file and return violations."""
    violations: list[Violation] = []
    for rule in rules:
        checker = RULE_CHECKERS.get(rule)
        if checker:
            rule_violations = checker(filepath, lines)
            for v in rule_violations:
                v.category = category
            violations.extend(rule_violations)
    return violations


def run_lint(
    files: list[str],
    rules: tuple[str, ...],
    diff_lines: dict[str, set[int]] | None = None,
    diff_base: str = "",
) -> LintResult:
    """Run taste lints on the given files."""
    result = LintResult()

    for filepath in files:
        # CWE-22: Validate path before processing
        if not is_safe_path(filepath):
            continue
        if not os.path.isfile(filepath):
            continue
        if Path(filepath).suffix not in SCANNABLE_EXTENSIONS:
            continue

        # Skip files classifiable as generated by path before reading them.
        # Marker-based detection still needs the body, but mirror and
        # instruction copies are known from the path alone, so avoid the I/O.
        if _generated_by_path(Path(filepath)):
            result.files_scanned += 1
            result.files_by_category["generated"] = result.files_by_category.get("generated", 0) + 1
            continue

        lines = read_file_lines(filepath)
        category = classify_file_category(filepath, lines)
        result.files_scanned += 1
        result.files_by_category[category] = result.files_by_category.get(category, 0) + 1
        if category == "generated":
            continue

        violations = _lint_file_rules(filepath, lines, rules, category)
        if diff_lines is not None:
            violations = _filter_violations_for_diff(violations, filepath, diff_lines, diff_base)
        result.violations.extend(violations)

    return result


def format_text(result: LintResult) -> str:
    """Format results as human/agent-readable text."""
    if not result.violations:
        return f"taste-lints: {result.files_scanned} files scanned, no violations found."

    output = []
    for v in result.violations:
        severity_marker = "ERROR" if v.severity == "error" else "WARNING"
        output.append(
            f"\n[{severity_marker}] {v.category} {v.rule}: {v.file}:{v.line}\n"
            f"  {v.message}\n"
            f"  {v.remediation}"
        )

    summary = (
        f"\ntaste-lints: {result.files_scanned} files scanned, "
        f"{result.error_count} error(s), {result.warning_count} warning(s)"
    )
    output.append(summary)
    return "\n".join(output)


def format_json(result: LintResult) -> str:
    """Format results as JSON."""
    data = {
        "files_scanned": result.files_scanned,
        "files_by_category": result.files_by_category,
        "error_count": result.error_count,
        "warning_count": result.warning_count,
        "violations": [
            {
                "rule": v.rule,
                "severity": v.severity,
                "category": v.category,
                "file": v.file,
                "line": v.line,
                "message": v.message,
                "remediation": v.remediation,
            }
            for v in result.violations
        ],
    }
    return json.dumps(data, indent=2)


def parse_rules(rules_str: str) -> tuple[str, ...]:
    """Parse comma-separated rule names."""
    if not rules_str:
        return ALL_RULES
    rules = tuple(r.strip() for r in rules_str.split(","))
    invalid = [r for r in rules if r not in ALL_RULES]
    if invalid:
        print(f"error: unknown rules: {', '.join(invalid)}", file=sys.stderr)
        print(f"valid rules: {', '.join(ALL_RULES)}", file=sys.stderr)
        sys.exit(EXIT_ERROR)
    return rules


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Taste invariant linter with agent-readable remediation",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Files to lint",
    )
    parser.add_argument(
        "--git-staged",
        action="store_true",
        help="Lint git staged files",
    )
    parser.add_argument(
        "--diff-scope",
        metavar="BASE_BRANCH",
        help="Lint only files changed in 'git diff --name-only BASE_BRANCH...HEAD'",
    )
    parser.add_argument(
        "--directory",
        "-d",
        help="Lint all scannable files in directory",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--rules",
        help=f"Comma-separated rules to run (default: all). Options: {','.join(ALL_RULES)}",
    )

    args = parser.parse_args()
    rules = parse_rules(args.rules)

    files: list[str] = []
    diff_lines: dict[str, set[int]] | None = None
    diff_base: str = ""
    if args.git_staged:
        files = get_staged_files()
    elif args.diff_scope is not None:
        try:
            files = get_diff_files(args.diff_scope)
            diff_lines = get_diff_line_numbers(args.diff_scope)
            diff_base = args.diff_scope
        except (ValueError, RuntimeError) as exc:
            print(f"taste-lints: {exc}", file=sys.stderr)
            return EXIT_ERROR
    elif args.directory:
        files = get_files_from_directory(args.directory)
    elif args.files:
        files = args.files
    else:
        parser.print_help()
        return EXIT_ERROR

    if not files:
        print("taste-lints: no files to scan.")
        return EXIT_SUCCESS

    result = run_lint(files, rules, diff_lines, diff_base)

    if args.format == "json":
        print(format_json(result))
    else:
        print(format_text(result))

    if result.error_count > 0:
        return EXIT_VIOLATIONS
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
