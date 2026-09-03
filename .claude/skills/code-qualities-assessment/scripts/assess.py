#!/usr/bin/env python3
"""
Code Qualities Assessment - Main Orchestrator

Assesses code maintainability using 5 foundational qualities:
- Cohesion
- Coupling
- Encapsulation
- Testability
- Non-Redundancy

Two gate modes decide what an exit code means. Absolute mode gates every
assessed file against the configured thresholds. Regression mode scores each
changed file at its base revision too and gates on the change, so inherited
debt in a file you only touched does not fail the run.

Exit codes:
  0: Gate passed
  10: Regression mode: a comparable quality regressed, or scored evidence was lost
  11: A file is below configured thresholds (absolute mode, or a new file in
      regression mode, which has no base to compare against)
  1: Script error
"""

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Language detection by file suffix. Only languages with tuned heuristics are
# listed. Unsupported files are reported as unscored for gate purposes so the
# gate never fails a file it cannot actually score.
_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".cs": "csharp",
    ".java": "java",
    ".go": "go",
}

# Every score here is size-derived, so adding one small function to a healthy
# module moves a quality by a few tenths with nothing wrong. Measured: adding one
# 2-line function to a 5-function module drops cohesion 8.7 -> 8.3. A zero
# tolerance fails that change, which is the inherited-debt complaint of issue
# #4364 in a new form. Real degradations move whole points (10.0 -> 3.3 in the
# same harness), so half a point separates noise from signal.
_DEFAULT_REGRESSION_TOLERANCE = 0.5

# Single-line comment prefixes, used to exclude comment lines from the
# lines-of-code count. Block comments are intentionally not stripped: this is an
# approximation, not a parser.
_LINE_COMMENT_PREFIXES = {
    "python": ("#",),
    "typescript": ("//",),
    "javascript": ("//",),
    "csharp": ("//",),
    "java": ("//",),
    "go": ("//",),
}

_GENERATED_PATH_SEGMENTS = (
    ("src", "copilot-cli"),
    ("src", "vs-code-agents"),
    (".github", "instructions"),
)
_GENERATED_MARKERS = (
    "AUTO-GENERATED MATCHER SHIM",
    "GENERATED -- DO NOT EDIT",
    "DO NOT EDIT BY HAND - regenerated",
)
# Generated files carry their markers in the file header. Authored files that
# only mention a marker string deeper in the body (generator scripts, this
# classifier's own marker tuple) must not be misread as generated, so match
# markers within the leading window only. 20 lines clears every real generated
# header (hook shims sit at lines 3-6) while excluding the marker literals in
# generator scripts and this tuple.
_GENERATED_MARKER_HEADER_LINES = 20


def _repo_relative_parts(file_path: Path) -> tuple[str, ...]:
    """Return path parts for segment matching, relative to CWD when possible.

    ``_GENERATED_PATH_SEGMENTS`` are repo-root-anchored. An absolute path also
    carries the checkout directory, so a clone under a path that itself contains
    e.g. ``src/copilot-cli`` would false-match and misclassify authored files as
    generated. Relativizing to CWD strips that prefix; already-relative paths, or
    paths outside CWD, fall back to their own parts unchanged.
    """
    if file_path.is_absolute():
        try:
            return file_path.relative_to(Path.cwd()).parts
        except ValueError:
            return file_path.parts
    return file_path.parts


def classify_file_category(file_path: Path, content: str | None = None) -> str:
    """Classify a changed file as authored, test, or generated.

    Generated outputs are reviewed through their generator and drift checks,
    not as independent authored modules.
    """
    parts = _repo_relative_parts(file_path)
    if any(parts[: len(segment)] == segment for segment in _GENERATED_PATH_SEGMENTS):
        return "generated"
    if file_path.name.startswith("pr-quality-gate-") and ".github" in parts:
        return "generated"
    if content is None:
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            content = ""
    header = "\n".join(content.splitlines()[:_GENERATED_MARKER_HEADER_LINES])
    if any(marker in header for marker in _GENERATED_MARKERS):
        return "generated"
    if "tests" in parts or file_path.name.startswith("test_"):
        return "test"
    return "authored"


# Per-language import / dependency line patterns for the coupling heuristic.
_IMPORT_PATTERNS = {
    "python": re.compile(r"^\s*(?:import\s+\S|from\s+\S+\s+import\s+)"),
    "javascript": re.compile(r"^\s*import\s+|\brequire\s*\("),
    "typescript": re.compile(r"^\s*import\s+|\brequire\s*\("),
    "csharp": re.compile(r"^\s*using\s+[A-Za-z_]"),
    "java": re.compile(r"^\s*import\s+[A-Za-z_]"),
    "go": re.compile(
        r'^\s*import\s+(?:(?:[A-Za-z_]\w*|\.)\s+)?"[^"]+"\s*(?://.*)?$'
        r'|^\s+(?:(?:[A-Za-z_]\w*|\.)\s+)?"[^"]+"\s*(?://.*)?$'
    ),
}

# Generic import fallback for languages without a tuned pattern.
_GENERIC_IMPORT_PATTERN = re.compile(r"^\s*(?:import|from|using|require|#include)\b")

# Per-language definition patterns (types, functions, methods) for the cohesion
# heuristic. More definitions plus larger size means lower cohesion.
_DEFINITION_PATTERNS = {
    "python": re.compile(r"^\s*(?:async\s+)?def\s+\w|^\s*class\s+\w"),
    "javascript": re.compile(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+\w"
        r"|^\s*(?:export\s+)?class\s+\w"
        r"|=\s*(?:async\s*)?\([^)]*\)\s*=>"
    ),
    "typescript": re.compile(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+\w"
        r"|^\s*(?:export\s+)?(?:abstract\s+)?class\s+\w"
        r"|^\s*(?:export\s+)?interface\s+\w"
        r"|=\s*(?:async\s*)?\([^)]*\)\s*=>"
    ),
    "csharp": re.compile(
        r"^\s*(?:public|private|protected|internal)\b[^;={]*\([^)]*\)\s*(?:\{|=>|$)"
        r"|^\s*(?:public|private|protected|internal)\s+"
        r"(?:static\s+|abstract\s+|sealed\s+|partial\s+)*"
        r"(?:class|interface|struct|record|enum)\s+\w"
    ),
    "java": re.compile(
        r"^\s*(?:public|private|protected)\b[^;={]*\([^)]*\)\s*(?:\{|throws\b|$)"
        r"|^\s*(?:public|private|protected)\s+"
        r"(?:static\s+|abstract\s+|final\s+)*"
        r"(?:class|interface|enum|record)\s+\w"
    ),
    "go": re.compile(r"^\s*func\s+|^\s*type\s+\w+\s+(?:struct|interface)\b"),
}


def detect_language(file_path: Path) -> str | None:
    """Return the tuned-heuristic language for a path, or None if unsupported."""
    return _LANGUAGE_BY_SUFFIX.get(file_path.suffix.lower())


def _count_python_global_state(lines: list[str]) -> int:
    return sum(1 for line in lines if line.strip().startswith("global "))


def _count_web_global_state(lines: list[str]) -> int:
    patterns = (
        re.compile(r"\bglobalThis\b"),
        re.compile(r"\bwindow\.\w+\s*="),
        re.compile(r"^(?:var|let|const)\s+\w"),
    )
    return sum(1 for line in lines if any(p.search(line) for p in patterns))


def _count_go_global_state(lines: list[str]) -> int:
    # Package-level (unindented) var declarations are mutable global state.
    count = 0
    in_package_var_block = False
    for line in lines:
        stripped = line.strip()
        if in_package_var_block:
            if stripped == ")":
                in_package_var_block = False
                continue
            if not stripped or stripped.startswith("//"):
                continue
            if re.match(r"^[A-Za-z_]\w*(?:\s|,|=)", stripped):
                count += 1
            continue

        if re.match(r"^var\s+\(", line):
            in_package_var_block = True
            continue
        if re.match(r"^var\s+\w", line):
            count += 1
    return count


def _immutable_static(stripped: str, immutable_keywords: tuple[str, ...]) -> bool:
    type_decls = ("class ", "struct ", "interface ", "enum ", "record ")
    return any(kw in stripped for kw in immutable_keywords + type_decls)


def _count_csharp_static_state(lines: list[str]) -> int:
    count = 0
    for line in lines:
        stripped = line.strip()
        if "static" not in stripped or "(" in stripped:
            continue
        if stripped.startswith("using "):
            continue
        if _immutable_static(stripped, ("readonly", "const ")):
            continue
        if stripped.endswith(";") or "=" in stripped:
            count += 1
    return count


def _count_java_static_state(lines: list[str]) -> int:
    count = 0
    for line in lines:
        stripped = line.strip()
        if "static" not in stripped or "(" in stripped:
            continue
        if stripped.startswith("import "):
            continue
        if _immutable_static(stripped, ("final",)):
            continue
        if stripped.endswith(";") or "=" in stripped:
            count += 1
    return count


# Mutable-global-state counters keyed by language. A missing language means
# "cannot score testability here"; the caller marks it unscored.
_GLOBAL_STATE_COUNTERS = {
    "python": _count_python_global_state,
    "javascript": _count_web_global_state,
    "typescript": _count_web_global_state,
    "go": _count_go_global_state,
    "csharp": _count_csharp_static_state,
    "java": _count_java_static_state,
}


def _count_python_public_fields(lines: list[str]) -> int:
    pattern = re.compile(r"(?<!\w)self\.([A-Za-z]\w*)\s*=(?!=)")
    fields = {
        m.group(1)
        for line in lines
        for m in pattern.finditer(line)
        if not m.group(1).startswith("_")
    }
    return len(fields)


def _count_public_fields_by_modifier(lines: list[str]) -> int:
    """Count public field declarations in a C#/Java style source.

    Public methods are the API and are fine; public *fields* expose mutable
    state and break encapsulation. Properties (`{ get; set; }`) and type
    declarations are excluded.
    """
    count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("public "):
            continue
        if "(" in stripped:  # method or constructor
            continue
        brace_idx = stripped.find("{")
        if brace_idx != -1 and "=" not in stripped[:brace_idx]:
            # Property (`{ get; set; }`) or type body, not a brace initializer
            # such as `public int[] xs = {1, 2};`, which is still a public field.
            continue
        if any(kw in stripped for kw in ("class ", "interface ", "struct ", "enum ", "record ")):
            continue
        if any(kw in stripped.split() for kw in ("const", "readonly", "final")):
            continue
        if stripped.endswith(";") or "=" in stripped:
            count += 1
    return count


# Public-field counters keyed by language. A missing language means
# encapsulation cannot be scored reliably (for example JavaScript, where
# visibility is largely conventional); the caller marks it unscored.
_PUBLIC_FIELD_COUNTERS = {
    "python": _count_python_public_fields,
    "csharp": _count_public_fields_by_modifier,
    "java": _count_public_fields_by_modifier,
}


@dataclass
class QualityScore:
    """Individual quality score with confidence.

    A confidence of 0.0 means the metric could not be scored for this file
    (for example, an unsupported language). The threshold gate skips any
    quality whose confidence is 0.0 rather than failing a file it could not
    measure.
    """

    value: float  # 1-10
    confidence: float  # 0-1
    reasons: list[str]


@dataclass
class FileAssessment:
    """Assessment results for a single file."""

    file_path: str
    category: str
    cohesion: QualityScore
    coupling: QualityScore
    encapsulation: QualityScore
    testability: QualityScore
    non_redundancy: QualityScore

    @property
    def overall(self) -> float:
        """Average of scored qualities only."""
        scored_values = [
            score.value
            for score in (
                self.cohesion,
                self.coupling,
                self.encapsulation,
                self.testability,
                self.non_redundancy,
            )
            if score.confidence > 0.0
        ]
        if not scored_values:
            return 0.0
        return sum(scored_values) / len(scored_values)


def _non_negative_finite_float(value: str) -> float:
    """Parse a finite, non-negative floating-point option."""
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than or equal to 0")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Assess code quality across 5 foundational qualities",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--target", required=True, help="File, directory, or glob pattern to assess"
    )
    parser.add_argument(
        "--context",
        choices=["production", "test", "generated"],
        default="production",
        help="Code context (affects thresholds)",
    )
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Only assess files changed from --base, or uncommitted files without --base",
    )
    parser.add_argument("--base", help="Base revision for --changed-only, such as origin/main")
    parser.add_argument(
        "--gate-mode",
        choices=["auto", "regression", "absolute"],
        default="auto",
        help=(
            "regression: gate on base-to-head change (needs --changed-only --base). "
            "absolute: gate on configured thresholds. "
            "auto (default): regression when --changed-only and --base are both set, "
            "otherwise absolute."
        ),
    )
    parser.add_argument(
        "--regression-tolerance",
        type=_non_negative_finite_float,
        default=_DEFAULT_REGRESSION_TOLERANCE,
        help=(
            "Score drop tolerated before a quality counts as regressed "
            f"(default {_DEFAULT_REGRESSION_TOLERANCE})"
        ),
    )
    parser.add_argument(
        "--format", choices=["markdown", "json", "html"], default="markdown", help="Output format"
    )
    parser.add_argument("--config", default=".qualityrc.json", help="Path to configuration file")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    parser.add_argument(
        "--use-serena",
        choices=["auto", "yes", "no"],
        default="auto",
        help="Use Serena for symbol extraction",
    )
    return parser.parse_args(argv)


def resolve_gate_mode(gate_mode: str, changed_only: bool, base: str | None) -> str:
    """Resolve the requested gate mode, rejecting a regression run with no base.

    Regression mode without a base has nothing to compare against, and silently
    falling back to absolute thresholds is how a gate that claims to block only
    regressions ends up blocking inherited debt.
    """
    if gate_mode == "regression":
        if not base:
            raise ValueError("--gate-mode regression requires --base")
        if not changed_only:
            raise ValueError("--gate-mode regression requires --changed-only")
        return "regression"
    if gate_mode == "absolute":
        return "absolute"
    return "regression" if changed_only and base else "absolute"


def load_config(config_path: str) -> dict[str, Any]:
    """Load configuration or return defaults"""
    try:
        with open(config_path, encoding="utf-8") as f:
            config: dict[str, Any] = json.load(f)
            return config
    except FileNotFoundError:
        # Default configuration
        return {
            "thresholds": {
                "cohesion": {"min": 7},
                "coupling": {"min": 7},
                "encapsulation": {"min": 7},
                "testability": {"min": 6},
                "nonRedundancy": {"min": 8},
            },
            "context": {"test": {"testability": {"min": 3}}},
            "ignore": ["**/generated/**", "**/*.pb.py"],
        }


@dataclass(frozen=True)
class ChangedFile:
    """One path change between the comparison base and head."""

    status: str
    base_path: Path | None
    head_path: Path | None


def _parse_changed_files(raw: bytes) -> list[ChangedFile]:
    """Parse ``git diff --name-status -z`` output."""
    import os

    tokens = raw.split(b"\0")
    if tokens and not tokens[-1]:
        tokens.pop()
    changes: list[ChangedFile] = []
    index = 0
    while index < len(tokens):
        status = tokens[index].decode("ascii")
        index += 1
        base_path: Path | None
        head_path: Path | None
        if status.startswith(("R", "C")):
            if index + 1 >= len(tokens):
                raise ValueError("Malformed git rename record")
            base_path = Path(os.fsdecode(tokens[index]))
            head_path = Path(os.fsdecode(tokens[index + 1]))
            index += 2
        else:
            if index >= len(tokens):
                raise ValueError("Malformed git path record")
            path = Path(os.fsdecode(tokens[index]))
            index += 1
            base_path = None if status == "A" else path
            head_path = None if status == "D" else path
        changes.append(ChangedFile(status, base_path, head_path))
    return changes


def get_changed_files(
    base: str | None,
    head: str = "HEAD",
    *,
    base_is_comparison: bool = False,
) -> list[ChangedFile]:
    """Return rename-aware changed paths between *base* and *head*."""
    import subprocess

    if base is not None:
        _reject_option_like_revision(base)
    _reject_option_like_revision(head)
    separator = ".." if base_is_comparison else "..."
    revision_range = f"{base}{separator}{head}" if base else head
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-status",
            "-M",
            "-z",
            "--end-of-options",
            revision_range,
        ],
        capture_output=True,
        check=True,
    )
    return _parse_changed_files(result.stdout)


def get_files_to_assess(
    target: str,
    changed_only: bool,
    base: str | None = None,
    changed_files: list[ChangedFile] | None = None,
    target_glob_matches: set[Path] | None = None,
) -> list[Path]:
    """Get files to assess, using the PR base when one is supplied."""
    from glob import glob

    if changed_only:
        changes = changed_files if changed_files is not None else get_changed_files(base)
        target_path = Path(target)
        glob_matches = target_glob_matches
        if (
            glob_matches is None
            and not target_path.is_file()
            and not target_path.is_dir()
        ):
            glob_matches = _glob_target_matches(target)
        files = [
            change.head_path
            for change in changes
            if change.head_path is not None
            and _target_contains(change.head_path, target, glob_matches)
        ]
    else:
        target_path = Path(target)
        if target_path.is_file():
            files = [target_path]
        elif target_path.is_dir():
            files = [f for suffix in _LANGUAGE_BY_SUFFIX for f in target_path.rglob(f"*{suffix}")]
        else:
            # Glob pattern
            files = [Path(f) for f in glob(target, recursive=True)]

    existing_files: list[Path] = []
    for file_path in files:
        if not file_path.exists():
            continue
        _resolve_in_workspace(file_path, "assessment candidate")
        existing_files.append(file_path)
    return existing_files


def _resolve_in_workspace(path: Path, label: str) -> Path:
    """Resolve *path* and require it to remain inside the current workspace."""
    workspace = Path.cwd().resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the workspace: {path}") from exc
    return resolved


def _glob_target_matches(target: str) -> set[Path]:
    """Resolve one glob target into a reusable candidate set."""
    from glob import glob

    return {
        _resolve_in_workspace(Path(match), "assessment candidate")
        for match in glob(target, recursive=True)
    }


def _target_contains(
    file_path: Path,
    target: str,
    glob_matches: set[Path] | None = None,
) -> bool:
    """Return whether *file_path* belongs to the requested target scope."""
    resolved_file = _resolve_in_workspace(file_path, "assessment candidate")
    target_path = Path(target)
    if target_path.is_file():
        return resolved_file == _resolve_in_workspace(target_path, "--target")
    if target_path.is_dir():
        resolved_target = _resolve_in_workspace(target_path, "--target")
        try:
            resolved_file.relative_to(resolved_target)
            return True
        except ValueError:
            return False
    matches = glob_matches if glob_matches is not None else _glob_target_matches(target)
    return resolved_file in matches


def _target_exists_at_revision(target: str, revision: str) -> bool:
    """Return whether a missing target matched any path at *revision*."""
    import subprocess

    workspace = Path.cwd().resolve()
    resolved_target = Path(target)
    try:
        relative_target = resolved_target.relative_to(workspace).as_posix()
    except ValueError as exc:
        raise ValueError(f"--target escapes the workspace: {target}") from exc
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", revision],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-tree failed for target validation at {revision}")
    names = result.stdout.splitlines()
    if any(character in relative_target for character in "*?["):
        return any(_match_path_glob(name, relative_target) for name in names)
    prefix = relative_target.rstrip("/")
    return any(name == prefix or name.startswith(f"{prefix}/") for name in names)


def _match_path_glob(path: str, pattern: str) -> bool:
    """Match a root-anchored glob where ``**`` spans zero or more segments."""
    import fnmatch

    path_parts = tuple(part for part in path.split("/") if part)
    pattern_parts = tuple(part for part in pattern.split("/") if part)

    def matches(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)
        part = pattern_parts[pattern_index]
        if part == "**":
            return matches(path_index, pattern_index + 1) or (
                path_index < len(path_parts)
                and matches(path_index + 1, pattern_index)
            )
        return (
            path_index < len(path_parts)
            and fnmatch.fnmatchcase(path_parts[path_index], part)
            and matches(path_index + 1, pattern_index + 1)
        )

    return matches(0, 0)


def _target_is_known(
    target: str,
    revision: str,
    glob_matches: set[Path] | None = None,
) -> bool:
    """Return whether target exists in HEAD or matched the comparison base."""
    target_path = Path(target)
    if target_path.exists():
        return True
    if any(character in target for character in "*?["):
        matches = glob_matches if glob_matches is not None else _glob_target_matches(target)
        if matches:
            return True
    return _target_exists_at_revision(target, revision)


def _reject_option_like_revision(revision: str) -> None:
    """Refuse a revision git would read as an option (CWE-88)."""
    if revision.startswith("-"):
        raise ValueError(f"--base must be a git revision, not an option: {revision!r}")


def resolve_revision(revision: str) -> str:
    """Return the commit SHA for *revision*, raising when it does not resolve.

    Resolving once up front is what lets a later per-file ``git show`` failure
    mean "absent at base", and therefore "new file", rather than "your --base
    was a typo". Without it every file looks new and the gate passes silently.
    """
    import subprocess

    _reject_option_like_revision(revision)
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"--base does not resolve to a commit: {revision!r}")
    return result.stdout.strip()


def resolve_comparison_base(base: str) -> str:
    """Return the commit the head is compared against: the merge base with HEAD.

    ``get_changed_files`` selects with ``base...HEAD``, which git resolves from
    the merge base. Reading content at the tip of *base* instead charges the
    branch for every change that landed on the base branch after the fork, which
    is the inherited-debt failure this gate exists to prevent (issue #4364).
    Falls back to the resolved commit when the two histories share no merge base.
    """
    import subprocess

    revision = resolve_revision(base)
    result = subprocess.run(
        ["git", "merge-base", "--end-of-options", revision, "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    merge_base = result.stdout.strip()
    if result.returncode == 1:
        return revision
    if result.returncode != 0:
        error = result.stderr.strip()
        raise RuntimeError(f"git merge-base failed for {revision}: {error}")
    if not merge_base:
        raise RuntimeError(f"git merge-base returned no commit for {revision}")
    return merge_base


def get_file_at_revision(file_path: Path, revision: str) -> bytes | None:
    """Return the file's bytes at *revision*, or None when absent there.

    None means the path did not exist in that commit, which the regression gate
    reads as a new file. Callers MUST have run ``resolve_revision`` first so a
    bad revision cannot masquerade as every file being new.

    Bytes, not text: ``text=True`` would decode with the locale codec, so the
    same file scores from different characters on a UTF-8 runner and a cp1252
    one, and a file that is not decodable at all raises UnicodeDecodeError
    (a ValueError) that reads as a bad ``--base``.
    """
    import subprocess

    _reject_option_like_revision(revision)
    entry = subprocess.run(
        ["git", "ls-tree", "-z", revision, "--", file_path.as_posix()],
        capture_output=True,
        check=False,
    )
    if entry.returncode != 0:
        error = entry.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git ls-tree failed for {revision}:{file_path}: {error}")
    if not entry.stdout:
        return None

    result = subprocess.run(
        ["git", "show", "--end-of-options", f"{revision}:{file_path.as_posix()}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git show failed for {revision}:{file_path}: {error}")
    return result.stdout


def _get_base_assessments(
    files: list[Path],
    base: str,
    context: str,
) -> dict[str, FileAssessment]:
    """Return safe base assessments for callers of the earlier regression API."""
    import subprocess

    repo_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if repo_result.returncode != 0:
        raise RuntimeError("git rev-parse --show-toplevel failed")
    repo_root = Path(repo_result.stdout.strip()).resolve()
    revision = resolve_comparison_base(base)
    assessments: dict[str, FileAssessment] = {}
    for file_path in files:
        try:
            relative_path = file_path.resolve().relative_to(repo_root)
        except ValueError:
            continue
        raw = get_file_at_revision(relative_path, revision)
        if raw is None:
            continue
        assessments[str(file_path)] = _assess_base_bytes(file_path, raw)
    return assessments


# Quality attributes on FileAssessment, in report order.
_QUALITY_FIELDS = (
    "cohesion",
    "coupling",
    "encapsulation",
    "testability",
    "non_redundancy",
)


@dataclass
class QualityDelta:
    """One quality compared between a base and a head assessment.

    ``status`` is one of:
      compared      both revisions scored it; ``delta`` is head minus base
      newly_scored  only head scored it; no delta exists to report
      evidence_lost only base scored it; the head stopped being measurable
      not_scored    neither revision scored it
    """

    quality: str
    base: float | None
    head: float | None
    delta: float | None
    status: str


@dataclass
class FileComparison:
    """Base-to-head comparison for one changed file."""

    file_path: str
    is_new_file: bool
    deltas: list[QualityDelta]
    regressions: list[str]
    evidence_loss: list[str]
    base_file_path: str | None = None
    change_status: str = "M"
    absolute_gate_reason: str | None = None


def _delta_for(quality: str, base: QualityScore, head: QualityScore) -> QualityDelta:
    base_scored = base.confidence > 0.0
    head_scored = head.confidence > 0.0
    if base_scored and head_scored:
        return QualityDelta(
            quality=quality,
            base=base.value,
            head=head.value,
            delta=round(head.value - base.value, 4),
            status="compared",
        )
    if head_scored:
        # No fabricated delta: there is no base number to subtract from.
        return QualityDelta(quality, None, head.value, None, "newly_scored")
    if base_scored:
        return QualityDelta(quality, base.value, None, None, "evidence_lost")
    return QualityDelta(quality, None, None, None, "not_scored")


def compare_assessments(
    base: FileAssessment | None,
    head: FileAssessment,
    tolerance: float = 0.0,
    base_file_path: str | None = None,
    change_status: str = "M",
    absolute_gate_reason: str | None = None,
) -> FileComparison:
    """Compare *head* against *base* quality by quality.

    Qualities are compared independently and only where both revisions scored
    them, so a file whose scored-quality set changed never produces a delta
    against a different set. Aggregate averages are deliberately not compared
    for the same reason.
    """
    if base is None:
        return FileComparison(
            head.file_path,
            True,
            [],
            [],
            [],
            base_file_path,
            change_status,
            absolute_gate_reason,
        )

    deltas: list[QualityDelta] = []
    regressions: list[str] = []
    evidence_loss: list[str] = []
    for field in _QUALITY_FIELDS:
        delta = _delta_for(field, getattr(base, field), getattr(head, field))
        deltas.append(delta)
        if delta.status == "compared" and delta.delta is not None and delta.delta < -tolerance:
            regressions.append(field)
        elif delta.status == "evidence_lost" and head.category != "generated":
            evidence_loss.append(field)
    return FileComparison(
        head.file_path,
        False,
        deltas,
        regressions,
        evidence_loss,
        base_file_path,
        change_status,
        absolute_gate_reason,
    )


def check_regressions(
    assessments: list[FileAssessment],
    base_assessments: dict[str, FileAssessment],
) -> int:
    """Preserve the earlier regression helper on top of per-quality comparison."""
    comparisons = [
        compare_assessments(
            base_assessments.get(str(head.file_path)),
            head,
            tolerance=0.05,
        )
        for head in assessments
        if str(head.file_path) in base_assessments
    ]
    return 10 if any(c.regressions or c.evidence_loss for c in comparisons) else 0


def _has_scored_quality(assessment: FileAssessment) -> bool:
    return any(
        getattr(assessment, field).confidence > 0.0
        for field in _QUALITY_FIELDS
    )


def build_comparisons(
    assessments: list[FileAssessment],
    base: str,
    tolerance: float = 0.0,
    changed_files: list[ChangedFile] | None = None,
) -> tuple[list[FileComparison], list[FileAssessment]]:
    """Score each head assessment against its base revision.

    Returns the per-file comparisons and, separately, the head assessments of
    files that did not exist at base. New files carry no delta, so they are
    handed to the absolute gate instead.
    """
    revision = resolve_comparison_base(base)
    explicit_changes = changed_files is not None
    change_by_head = {
        change.head_path: change
        for change in (changed_files or [])
        if change.head_path is not None
    }
    comparisons: list[FileComparison] = []
    new_files: list[FileAssessment] = []
    for head in assessments:
        path = Path(head.file_path)
        change = change_by_head.get(path, ChangedFile("M", path, path))
        base_path = change.base_path
        if base_path is None:
            comparisons.append(
                compare_assessments(
                    None,
                    head,
                    tolerance,
                    None,
                    change.status,
                    "new_file",
                )
            )
            new_files.append(head)
            continue
        raw = get_file_at_revision(base_path, revision)
        if raw is None:
            if explicit_changes and change.status != "A":
                raise ValueError(f"Base blob is absent for {base_path} at {revision}")
            comparisons.append(
                compare_assessments(
                    None,
                    head,
                    tolerance,
                    None,
                    "A",
                    "new_file",
                )
            )
            new_files.append(head)
            continue
        base_assessment = _assess_base_bytes(base_path, raw)
        absolute_reason = (
            None if _has_scored_quality(base_assessment) else "base_unscored"
        )
        comparisons.append(
            compare_assessments(
                base_assessment,
                head,
                tolerance,
                base_path.as_posix(),
                change.status,
                absolute_reason,
            )
        )
        if absolute_reason is not None:
            new_files.append(head)
    return comparisons, new_files


def _assess_base_bytes(path: Path, raw: bytes) -> FileAssessment:
    """Score the base revision's bytes, or record it as unmeasurable.

    An undecodable base scores nothing, so every quality reads as newly scored
    and no delta is fabricated from a file the assessor could not read.
    """
    try:
        return assess_content(path, raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        return _unreadable_assessment(path, f"decode failed at base: {exc}")


def check_regression(
    comparisons: list[FileComparison],
    new_file_assessments: list[FileAssessment],
    config: dict[str, Any],
    context: str,
) -> int:
    """Gate on change, not on inherited debt.

    Returns:
        0:  no comparable quality regressed and no new file failed absolutely
        10: a comparable quality regressed, or scored evidence was lost
        11: no regression, but a new authored file is below absolute thresholds
    """
    degraded = False
    for comparison in comparisons:
        for quality in comparison.regressions:
            delta = next(d for d in comparison.deltas if d.quality == quality)
            print(
                f"❌ {comparison.file_path}: {quality} regressed "
                f"{delta.base} -> {delta.head} (delta {delta.delta})",
                file=sys.stderr,
            )
            degraded = True
        for quality in comparison.evidence_loss:
            print(
                f"❌ {comparison.file_path}: {quality} was scored at base and is "
                f"unscored at head (evidence loss)",
                file=sys.stderr,
            )
            degraded = True

    # New files and files whose base revision scored nothing have no comparable
    # base. Absolute thresholds are the only policy that can apply to them.
    new_file_code = check_thresholds(
        new_file_assessments,
        config,
        context,
        fail_unscored_supported=True,
    )

    if degraded:
        return 10
    return new_file_code


def _score_cohesion(language: str | None, code_lines: list[str], loc: int) -> QualityScore:
    """Approximate cohesion from size plus definition count.

    This is a size+definition approximation, not a true LCOM cohesion metric.
    More definitions packed into a larger file suggests the file is doing many
    things (lower cohesion). Confidence is deliberately low.
    """
    pattern = _DEFINITION_PATTERNS.get(language) if language else None
    def_count = sum(1 for line in code_lines if pattern.search(line)) if pattern else 0
    score = 10.0 - (loc / 120.0) - max(0, def_count - 1) * 0.3
    score = max(1.0, min(10.0, score))
    confidence = 0.4 if pattern else 0.0
    reasons = [
        f"{loc} LOC, {def_count} definitions (size+definition approximation, not LCOM)",
        (
            "Definition count not scored for this language"
            if pattern is None
            else "Large file with many definitions suggests low cohesion"
            if score < 7
            else "Size and definition count are reasonable"
        ),
    ]
    return QualityScore(value=round(score, 1), confidence=confidence, reasons=reasons)


def _score_coupling(language: str | None, code_lines: list[str]) -> QualityScore:
    """Approximate coupling from the number of import/dependency statements.

    A high score means loose coupling (few imports), which is good, matching
    the rubric where 10 is best. Languages without a tuned import pattern are
    counted with a generic fallback for the report but returned at confidence
    0.0 so the threshold gate does not fail a file scored only by that
    untuned heuristic (matches the file-header contract).
    """
    pattern = _IMPORT_PATTERNS.get(language) if language else None
    if pattern is not None:
        import_count = sum(1 for line in code_lines if pattern.search(line))
        confidence = 0.6
        tuned = True
    else:
        import_count = sum(1 for line in code_lines if _GENERIC_IMPORT_PATTERN.search(line))
        confidence = 0.0
        tuned = False
    score = max(1.0, min(10.0, 10.0 - import_count))
    detail = (
        "High import count suggests high coupling"
        if import_count > 10
        else "Import count is reasonable"
    )
    if not tuned:
        detail = "Generic import approximation (untuned language); not gated"
    reasons = [
        f"{import_count} import/dependency statements",
        detail,
    ]
    return QualityScore(value=round(score, 1), confidence=confidence, reasons=reasons)


def _score_encapsulation(language: str | None, code_lines: list[str]) -> QualityScore:
    """Approximate encapsulation from the number of exposed public fields.

    Public methods are the intended API and are not penalized; public mutable
    *fields* break encapsulation and lower the score. Languages without a
    reliable visibility signal (for example JavaScript, where privacy is
    conventional) are left unscored (confidence 0.0) so the gate does not fail
    a file it cannot measure.
    """
    counter = _PUBLIC_FIELD_COUNTERS.get(language) if language else None
    if counter is None:
        return QualityScore(
            value=10.0,
            confidence=0.0,
            reasons=["Encapsulation not scored for this language (no reliable visibility signal)"],
        )
    public_fields = counter(code_lines)
    score = 10.0 if public_fields == 0 else max(1.0, 10.0 - public_fields * 2.5)
    reasons = [
        f"{public_fields} exposed public field(s)",
        (
            "Exposed public state weakens encapsulation"
            if public_fields > 0
            else "No exposed public fields detected"
        ),
    ]
    return QualityScore(value=round(score, 1), confidence=0.5, reasons=reasons)


def _score_testability(language: str | None, code_lines: list[str]) -> QualityScore:
    """Approximate testability from the amount of global/static state.

    The per-language counters flag global and static references. Some of these
    (for example JS/TS ``const``) are not reassignable, so the label is
    "global/static", not "mutable".

    Languages without a global-state counter are left unscored (confidence
    0.0) rather than defaulting to a perfect constant, which previously made
    every non-Python file look maximally testable.
    """
    counter = _GLOBAL_STATE_COUNTERS.get(language) if language else None
    if counter is None:
        return QualityScore(
            value=10.0,
            confidence=0.0,
            reasons=["Testability not scored for this language (no global-state model)"],
        )
    global_count = counter(code_lines)
    score = max(1.0, 10.0 - global_count * 2)
    reasons = [
        f"{global_count} global/static references",
        ("Global state hinders testability" if global_count > 0 else "No global state detected"),
    ]
    return QualityScore(value=round(score, 1), confidence=0.5, reasons=reasons)


def _score_non_redundancy(lines: list[str], scored: bool) -> QualityScore:
    """Approximate non-redundancy from the ratio of unique to total lines.

    This is language-agnostic and unchanged in spirit from the original
    heuristic.
    """
    confidence = 0.5 if scored else 0.0
    non_blank = [line.strip() for line in lines if line.strip()]
    if not non_blank:
        return QualityScore(
            value=10.0, confidence=confidence, reasons=["Empty file, no duplication"]
        )
    unique_lines = len(set(non_blank))
    score = (unique_lines / len(non_blank)) * 10.0
    reasons = [
        f"{unique_lines}/{len(non_blank)} unique non-blank lines",
        "High duplication detected" if score < 7 else "Low duplication",
    ]
    if not scored:
        reasons.append("Non-redundancy not scored for this language")
    return QualityScore(value=round(score, 1), confidence=confidence, reasons=reasons)


def _unscored_generated_assessment(file_path: Path) -> FileAssessment:
    """Return a generated artifact assessment excluded from local quality gates."""

    def _unscored() -> QualityScore:
        return QualityScore(
            value=10.0,
            confidence=0.0,
            reasons=["Generated artifact, reviewed through its generator and drift checks"],
        )

    return FileAssessment(
        file_path=str(file_path),
        category="generated",
        cohesion=_unscored(),
        coupling=_unscored(),
        encapsulation=_unscored(),
        testability=_unscored(),
        non_redundancy=_unscored(),
    )


def _unreadable_assessment(file_path: Path, reason: str) -> FileAssessment:
    """Return an all-unscored assessment for a file that could not be read.

    Every quality is confidence 0.0 so ``check_thresholds`` skips the file
    rather than passing it on meaningless scores derived from empty content.
    The reason is carried so the report explains why the file was not scored.
    """

    def _unscored() -> QualityScore:
        # A fresh instance (and reasons list) per quality so a later mutation
        # of one metric cannot alias into the others.
        return QualityScore(
            value=10.0,
            confidence=0.0,
            reasons=[f"Not scored ({reason})"],
        )

    return FileAssessment(
        file_path=str(file_path),
        category=classify_file_category(file_path),
        cohesion=_unscored(),
        coupling=_unscored(),
        encapsulation=_unscored(),
        testability=_unscored(),
        non_redundancy=_unscored(),
    )


def assess_content(file_path: Path, content: str) -> FileAssessment:
    """Score already-loaded *content* attributed to *file_path*.

    Split out of ``assess_file`` so the same scoring runs over a base revision
    fetched with ``git show``, which never touches the working tree. Keeping
    one scoring body is what makes a base-to-head delta meaningful: two bodies
    would drift and the delta would measure the drift instead of the code.
    """
    language = detect_language(file_path)
    comment_prefixes = _LINE_COMMENT_PREFIXES.get(language, ()) if language else ()

    category = classify_file_category(file_path, content)
    if category == "generated":
        return _unscored_generated_assessment(file_path)

    lines = content.split("\n")
    code_lines = [
        line
        for line in lines
        if line.strip() and not (comment_prefixes and line.strip().startswith(comment_prefixes))
    ]
    loc = len(code_lines)

    return FileAssessment(
        file_path=str(file_path),
        category=category,
        cohesion=_score_cohesion(language, code_lines, loc),
        coupling=_score_coupling(language, code_lines),
        encapsulation=_score_encapsulation(language, code_lines),
        testability=_score_testability(language, code_lines),
        non_redundancy=_score_non_redundancy(lines, language is not None),
    )


def assess_file_content(
    file_path: Path,
    content: str,
    context: str,
) -> FileAssessment:
    """Preserve the earlier content-assessment helper."""
    del context
    return assess_content(file_path, content)


def assess_file(file_path: Path, context: str, use_serena: bool) -> FileAssessment:
    """
    Assess a single file for all 5 qualities.

    This is a heuristic implementation. It detects the language from the file
    suffix and applies language-aware approximations for each quality. Metrics
    that cannot be scored for a given language are returned with confidence
    0.0, and the threshold gate skips any quality with confidence 0.0 rather
    than failing a file it could not measure. A production implementation would
    parse symbols (using Serena if available) instead of scanning lines.
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        return _unreadable_assessment(file_path, f"read failed: {exc}")
    except UnicodeDecodeError as exc:
        return _unreadable_assessment(file_path, f"decode failed: {exc}")
    return assess_content(file_path, content)


def _average_scored(scores: list[QualityScore]) -> float | None:
    values = [score.value for score in scores if score.confidence > 0.0]
    if not values:
        return None
    return sum(values) / len(values)


def _format_average(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}/10"


def _format_quality_score(score: QualityScore) -> str:
    if score.confidence == 0.0:
        return "unscored (n/a)"
    return f"{score.value:.1f}/10"


def _threshold_min(thresholds: dict[str, Any], key: str) -> float | None:
    threshold = thresholds.get(key, {})
    value = threshold.get("min")
    return float(value) if value is not None else None


def _score_below_threshold(score: QualityScore, threshold: float | None) -> bool:
    return threshold is not None and score.confidence > 0.0 and score.value < threshold


def generate_markdown_report(assessments: list[FileAssessment], config: dict[str, Any]) -> str:
    """Generate markdown report"""
    report = ["# Code Quality Assessment Report\n"]

    # Summary statistics
    if not assessments:
        return "No files assessed."

    avg_cohesion = _average_scored([a.cohesion for a in assessments])
    avg_coupling = _average_scored([a.coupling for a in assessments])
    avg_encap = _average_scored([a.encapsulation for a in assessments])
    avg_test = _average_scored([a.testability for a in assessments])
    avg_nonred = _average_scored([a.non_redundancy for a in assessments])
    thresholds = config["thresholds"]

    report.append("## Summary\n")
    report.append(f"**Files Assessed**: {len(assessments)}\n")
    report.append(f"**Average Cohesion**: {_format_average(avg_cohesion)}")
    report.append(f"**Average Coupling**: {_format_average(avg_coupling)}")
    report.append(f"**Average Encapsulation**: {_format_average(avg_encap)}")
    report.append(f"**Average Testability**: {_format_average(avg_test)}")
    report.append(f"**Average Non-Redundancy**: {_format_average(avg_nonred)}\n")

    # Per-file breakdown
    report.append("## File Assessments\n")
    for assessment in sorted(assessments, key=lambda a: a.overall):
        report.append(f"### {assessment.file_path} ({assessment.category})\n")
        overall = _format_average(assessment.overall if assessment.overall > 0 else None)
        report.append(f"**Overall**: {overall}\n")
        quality_rows = (
            ("Cohesion", "cohesion", assessment.cohesion),
            ("Coupling", "coupling", assessment.coupling),
            ("Encapsulation", "encapsulation", assessment.encapsulation),
            ("Testability", "testability", assessment.testability),
            ("Non-Redundancy", "nonRedundancy", assessment.non_redundancy),
        )
        for label, _, score in quality_rows:
            report.append(f"- **{label}**: {_format_quality_score(score)}")
        report.append("")

        # Show reasons for low scores
        for label, threshold_key, score in quality_rows:
            if _score_below_threshold(score, _threshold_min(thresholds, threshold_key)):
                report.append(f"**{label} Issues**:")
                for reason in score.reasons:
                    report.append(f"  - {reason}")
                report.append("")

    return "\n".join(report)


def generate_regression_section(comparisons: list[FileComparison]) -> str:
    """Render the base/head/delta table for a regression-mode markdown report."""
    if not comparisons:
        return ""
    lines = ["## Regression Comparison\n"]
    for comparison in comparisons:
        lines.append(f"### {comparison.file_path}\n")
        if comparison.is_new_file:
            lines.append("New file at head; no base score exists. Gated absolutely.\n")
            continue
        if (
            comparison.base_file_path is not None
            and comparison.base_file_path != comparison.file_path
        ):
            lines.append(
                f"Renamed from `{comparison.base_file_path}` "
                f"({comparison.change_status}).\n"
            )
        if comparison.absolute_gate_reason == "base_unscored":
            lines.append(
                "Base file had no scored qualities; head is gated absolutely.\n"
            )
        lines.append("| Quality | Base | Head | Delta | Status |")
        lines.append("| --- | --- | --- | --- | --- |")
        for delta in comparison.deltas:
            base = "n/a" if delta.base is None else f"{delta.base:.1f}"
            head = "n/a" if delta.head is None else f"{delta.head:.1f}"
            change = "n/a" if delta.delta is None else f"{delta.delta:+.1f}"
            lines.append(
                f"| {delta.quality} | {base} | {head} | {change} | {delta.status} |"
            )
        lines.append("")
    return "\n".join(lines)


def generate_json_report(
    assessments: list[FileAssessment],
    comparisons: list[FileComparison] | None = None,
    gate_mode: str = "absolute",
) -> str:
    """Generate JSON report"""
    return json.dumps(
        {
            "files": [asdict(a) for a in assessments],
            "gate_mode": gate_mode,
            "comparisons": [asdict(c) for c in (comparisons or [])],
            "summary": {
                "file_count": len(assessments),
                "average_scores": {
                    "cohesion": _average_scored([a.cohesion for a in assessments]),
                    "coupling": _average_scored([a.coupling for a in assessments]),
                    "encapsulation": _average_scored([a.encapsulation for a in assessments]),
                    "testability": _average_scored([a.testability for a in assessments]),
                    "non_redundancy": _average_scored([a.non_redundancy for a in assessments]),
                },
            },
        },
        indent=2,
    )


def check_thresholds(
    assessments: list[FileAssessment],
    config: dict[str, Any],
    context: str,
    *,
    fail_unscored_supported: bool = False,
) -> int:
    """
    Check if quality scores meet configured thresholds.

    Returns:
        0: All thresholds met
        11: Below thresholds
    """
    thresholds = config["thresholds"]

    # Apply context-specific thresholds
    if context in config.get("context", {}):
        context_thresholds = config["context"][context]
        thresholds = {**thresholds, **context_thresholds}

    for assessment in assessments:
        if (
            fail_unscored_supported
            and assessment.category != "generated"
            and detect_language(Path(assessment.file_path)) is not None
            and not _has_scored_quality(assessment)
        ):
            print(
                f"❌ {assessment.file_path}: supported authored source could not be scored",
                file=sys.stderr,
            )
            return 11

        if (
            assessment.cohesion.confidence > 0.0
            and assessment.cohesion.value < thresholds["cohesion"]["min"]
        ):
            print(
                f"❌ {assessment.file_path}: Cohesion {assessment.cohesion.value} "
                f"< {thresholds['cohesion']['min']}",
                file=sys.stderr,
            )
            return 11

        # Coupling uses "min" semantics: higher score = looser coupling = better.
        # Legacy configs that only specify "max" are skipped rather than gated
        # incorrectly.
        coupling_min = thresholds["coupling"].get("min")
        if (
            coupling_min is not None
            and assessment.coupling.confidence > 0.0
            and assessment.coupling.value < coupling_min
        ):
            print(
                f"❌ {assessment.file_path}: Coupling {assessment.coupling.value} < {coupling_min}",
                file=sys.stderr,
            )
            return 11

        if (
            assessment.encapsulation.confidence > 0.0
            and assessment.encapsulation.value < thresholds["encapsulation"]["min"]
        ):
            print(
                f"❌ {assessment.file_path}: Encapsulation {assessment.encapsulation.value} "
                f"< {thresholds['encapsulation']['min']}",
                file=sys.stderr,
            )
            return 11

        if (
            assessment.testability.confidence > 0.0
            and assessment.testability.value < thresholds["testability"]["min"]
        ):
            print(
                f"❌ {assessment.file_path}: Testability {assessment.testability.value} "
                f"< {thresholds['testability']['min']}",
                file=sys.stderr,
            )
            return 11

        if (
            assessment.non_redundancy.confidence > 0.0
            and assessment.non_redundancy.value < thresholds["nonRedundancy"]["min"]
        ):
            print(
                f"❌ {assessment.file_path}: Non-Redundancy {assessment.non_redundancy.value} "
                f"< {thresholds['nonRedundancy']['min']}",
                file=sys.stderr,
            )
            return 11

    return 0


def _resolve_target_path(target: str) -> str:
    """Return an absolute target path inside the current working directory."""
    return str(_resolve_in_workspace(Path(target), "--target"))


def _assess_files(
    files: list[Path],
    context: str,
    use_serena: bool,
) -> list[FileAssessment]:
    """Assess every readable file and report per-file failures.

    A file that raises is recorded as an all-unscored assessment rather than
    dropped. Dropping it made the failure invisible downstream: `summary`
    reports `file_count` as the length of this list, so a run that lost four of
    five files still looked internally consistent, and a consumer could read
    the survivor as evidence the whole change was assessed. This is the same
    treatment an unreadable file already gets at the decode site.
    """
    assessments: list[FileAssessment] = []
    for file_path in files:
        try:
            assessments.append(assess_file(file_path, context, use_serena))
        except Exception as e:
            print(f"Error assessing {file_path}: {e}", file=sys.stderr)
            assessments.append(_unreadable_assessment(file_path, f"assessment failed: {e}"))
    return assessments


def _build_regression_inputs(
    assessments: list[FileAssessment],
    gate_mode: str,
    base: str | None,
    tolerance: float,
    changed_files: list[ChangedFile] | None,
) -> tuple[list[FileComparison], list[FileAssessment]]:
    """Build comparisons only when regression mode is active."""
    if gate_mode != "regression":
        return [], []
    if base is None:
        raise ValueError("--gate-mode regression requires --base")
    return build_comparisons(assessments, base, tolerance, changed_files)


def _render_report(
    output_format: str,
    assessments: list[FileAssessment],
    comparisons: list[FileComparison],
    config: dict[str, Any],
    gate_mode: str,
) -> str:
    """Render the selected report format."""
    if output_format == "markdown":
        report = generate_markdown_report(assessments, config)
        section = generate_regression_section(comparisons)
        return f"{report}\n\n{section}" if section else report
    if output_format == "json":
        return generate_json_report(assessments, comparisons, gate_mode)
    return "HTML format not yet implemented"


def _write_report(report: str, output: str | None) -> None:
    """Write the report to a file or stdout."""
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Report written to {output}")
        return
    print(report)


def _gate_result(
    gate_mode: str,
    comparisons: list[FileComparison],
    new_file_assessments: list[FileAssessment],
    assessments: list[FileAssessment],
    config: dict[str, Any],
    context: str,
) -> int:
    """Apply the gate policy selected for this run."""
    if gate_mode == "regression":
        return check_regression(comparisons, new_file_assessments, config, context)
    return check_thresholds(assessments, config, context)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(argv)
    config = load_config(args.config)
    try:
        gate_mode = resolve_gate_mode(args.gate_mode, args.changed_only, args.base)
        target_path = _resolve_target_path(args.target)
        comparison_base = args.base
        base_is_comparison = False
        if args.changed_only and gate_mode == "regression" and args.base is not None:
            comparison_base = resolve_comparison_base(args.base)
            base_is_comparison = True
        target_glob_matches = None
        resolved_target = Path(target_path)
        if (
            args.changed_only
            and not resolved_target.is_file()
            and not resolved_target.is_dir()
        ):
            target_glob_matches = _glob_target_matches(target_path)
        changed_files = (
            get_changed_files(
                comparison_base,
                base_is_comparison=base_is_comparison,
            )
            if args.changed_only
            else None
        )
        files = get_files_to_assess(
            target_path,
            args.changed_only,
            comparison_base,
            changed_files,
            target_glob_matches,
        )
    except (RuntimeError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error getting files: {e}", file=sys.stderr)
        return 1

    if not files:
        if gate_mode == "regression" and changed_files is not None:
            assert comparison_base is not None
            if not _target_is_known(
                target_path,
                comparison_base,
                target_glob_matches,
            ):
                print(f"ERROR: --target does not match HEAD or base: {args.target}", file=sys.stderr)
                return 1
            report = _render_report(args.format, [], [], config, gate_mode)
            _write_report(report, args.output)
            return 0
        print("No files to assess", file=sys.stderr)
        return 1

    assessments = _assess_files(files, args.context, args.use_serena == "yes")
    try:
        comparisons, new_file_assessments = _build_regression_inputs(
            assessments,
            gate_mode,
            comparison_base,
            args.regression_tolerance,
            changed_files,
        )
    except (RuntimeError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    report = _render_report(args.format, assessments, comparisons, config, gate_mode)
    _write_report(report, args.output)
    return _gate_result(
        gate_mode,
        comparisons,
        new_file_assessments,
        assessments,
        config,
        args.context,
    )


if __name__ == "__main__":
    sys.exit(main())
