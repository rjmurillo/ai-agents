#!/usr/bin/env python3
# taste-lint: ignore file-size -- pre-existing debt, unlinted before the ADR-119 source classification
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
  0: Policy satisfied, including an explicitly admitted regression
  10: Regression mode: a comparable quality regressed, or scored evidence was lost
  11: A file is below configured thresholds (absolute mode, or a new file in
      regression mode, which has no base to compare against)
  1: Script error
"""

import argparse
import ast
import json
import math
import re
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from functools import cache, lru_cache, partial
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
    ".ps1": "powershell",
    ".psm1": "powershell",
    ".psd1": "powershell",
}

# Every score here is size-derived, so adding one small function to a healthy
# module moves a quality by a few tenths with nothing wrong. Measured: adding one
# 2-line function to a 5-function module drops cohesion 8.7 -> 8.3. A zero
# tolerance fails that change, which is the inherited-debt complaint of issue
# #4364 in a new form. Real degradations move whole points (10.0 -> 3.3 in the
# same harness), so half a point separates noise from signal.
_DEFAULT_REGRESSION_TOLERANCE = 0.5

# These repository-specific admissions (ADR-122) are inert without the
# matching config. Each admits exactly one scanner coupling transition.
_CSHARP_PARSER_DEPENDENCY_ADMISSION = {
    "issue": 7406,
    "file": "src/claude/skills/code-qualities-assessment/scripts/assess.py",
    "imports": ["tree_sitter", "tree_sitter_c_sharp"],
    "baseScore": 10.0,
    "headScore": 8.0,
    "authorizedBy": "rjmurillo",
    "authorizedOn": "2026-11-16",
    "authorization": "Maintainer instruction: waiver, full send.",
}

_TYPESCRIPT_PARSER_DEPENDENCY_ADMISSION = {
    "issue": 7435,
    "file": "src/claude/skills/code-qualities-assessment/scripts/assess.py",
    "imports": ["tree_sitter", "tree_sitter_c_sharp", "tree_sitter_typescript"],
    "baseScore": 8.0,
    "headScore": 7.0,
    "authorizedBy": "rjmurillo",
    "authorizedOn": "2026-11-18",
    "authorization": (
        "Maintainer instruction: LGTM. Ship. agent- environment is optional. Package add approved"
    ),
}

_PYTHON_PARSER_DEPENDENCY_ADMISSION = {
    "issue": 7436,
    "file": "src/claude/skills/code-qualities-assessment/scripts/assess.py",
    "imports": [
        "tree_sitter",
        "tree_sitter_c_sharp",
        "tree_sitter_python",
        "tree_sitter_typescript",
    ],
    "baseScore": 7.0,
    "headScore": 6.0,
    "authorizedBy": "rjmurillo",
    "authorizedOn": "2026-11-18",
    "authorization": (
        "Maintainer instruction: LGTM. Ship. agent- environment is optional. Package add approved"
    ),
}

# Config key -> (fixed record, FileComparison field that carries it to JSON).
_PARSER_DEPENDENCY_ADMISSIONS = {
    "csharpParserDependencyAdmission": (
        _CSHARP_PARSER_DEPENDENCY_ADMISSION,
        "csharp_parser_dependency_admission",
    ),
    "typescriptParserDependencyAdmission": (
        _TYPESCRIPT_PARSER_DEPENDENCY_ADMISSION,
        "typescript_parser_dependency_admission",
    ),
    "pythonParserDependencyAdmission": (
        _PYTHON_PARSER_DEPENDENCY_ADMISSION,
        "python_parser_dependency_admission",
    ),
}

# ADR-122 item 10: eight change-scoped transitions from issue #7493. Each record
# pins the file, the quality, both scores, and both git blob ids.
_RENEWED_SEARCH_HEAD = "9128445e248852cd578927c6753b237f68ac510a"
_RENEWED_SHIM_HEAD = "9738fc16fc731f74d61d21ef7bf95240a241a046"
# The decisions that renewed each head pin, keyed by the renewed head blob.
_RENEWAL_NOTES: dict[str, str] = {
    _RENEWED_SEARCH_HEAD: (
        " Maintainer decisions D5 (2026-11-22, issue #7493 comment 7086682234),"
        " D9 (2026-11-23, issue #7493 comment 7120119475), and D12"
        " (2026-11-23, issue #7493 comment 7121288491) renewed this head pin."
        " Maintainer decision D13 (2026-11-23, issue #7493 comment 7121992178)"
        " set the cohesion head score to 2.0."
    ),
    _RENEWED_SHIM_HEAD: (
        " Maintainer decision D12 (2026-11-23, issue #7493 comment 7121288491)"
        " renewed this head pin."
    ),
}

_CHANGE_ADMISSIONS = tuple(
    {
        "issue": 7493,
        "file": file,
        "quality": quality,
        "baseScore": base,
        "headScore": head,
        "baseBlob": base_blob,
        "headBlob": head_blob,
        "authorizedBy": "rjmurillo",
        "authorizedOn": "2026-11-20",
        "authorization": (
            "Maintainer decisions D1 and D2, choice A: "
            "admit all 8 transitions as fixed records in one ADR-122 item."
            + _RENEWAL_NOTES.get(str(head_blob), "")
        ),
    }
    for file, quality, base, head, base_blob, head_blob in (
        (
            "build/scripts/lib_mirror.py",
            "coupling",
            8.0,
            7.0,
            "7477415f3dd715ef624f6cb14f5233d3afda9c48",
            "83f7c976ca63a7af312b05294281f084c5dea7a2",
        ),
        (
            "scripts/memory_enhancement/hooks/user_prompt_submit_memory.py",
            "cohesion",
            6.3,
            4.2,
            "32c45daf664cb0ace70a540d2fbd7088bc03cca8",
            "3d8a383a59c4b6b0ad5a5a6e7cd8cf33fc3d4a88",
        ),
        (
            "scripts/memory_enhancement/hooks/user_prompt_submit_memory.py",
            "coupling",
            6.0,
            3.0,
            "32c45daf664cb0ace70a540d2fbd7088bc03cca8",
            "3d8a383a59c4b6b0ad5a5a6e7cd8cf33fc3d4a88",
        ),
        (
            "scripts/memory_enhancement/search.py",
            "cohesion",
            4.2,
            2.0,
            "1dcb875cc1a14544bf3ff6294a45894fe2ae1106",
            _RENEWED_SEARCH_HEAD,
        ),
        (
            "scripts/memory_enhancement/search.py",
            "coupling",
            5.0,
            3.0,
            "1dcb875cc1a14544bf3ff6294a45894fe2ae1106",
            _RENEWED_SEARCH_HEAD,
        ),
        (
            "templates/hooks/UserPromptSubmit/invoke_memory_recall.py",
            "cohesion",
            9.2,
            7.7,
            "a828ad1f7182aa81effb649de69f5a8b81ff2f1e",
            _RENEWED_SHIM_HEAD,
        ),
        (
            "templates/hooks/invoke_dispatch_claude.py",
            "cohesion",
            5.7,
            4.6,
            "0672c74a1924030150352d7c96a04c0a60024d52",
            "6c83d8f9257a717d614173604abb4a7f4cb83d1c",
        ),
        (
            "tests/build_scripts/test_lib_mirror.py",
            "coupling",
            7.0,
            6.0,
            "e4259bb802bf1c14290e0fca6c425e9611caf532",
            "c8214f85fb74aa7b18ad5f611e88e3a1220cd8b2",
        ),
    )
)

# Coupling for these languages is counted from a syntax tree over raw source.
# Filtering comment lines first would drop PowerShell's `#Requires` statements,
# which are comments to a line filter.
_PARSED_COUPLING_LANGUAGES = frozenset(
    {"csharp", "javascript", "python", "typescript", "powershell"}
)

# Single-line comment prefixes. ``assess_content`` drops these lines once, and
# both the lines-of-code count and the non-redundancy ratio read the result.
# Block comments are intentionally not stripped: this is an approximation, not
# a parser.
_LINE_COMMENT_PREFIXES = {
    "python": ("#",),
    "typescript": ("//",),
    "javascript": ("//",),
    "csharp": ("//",),
    "java": ("//",),
    "go": ("//",),
    "powershell": ("#",),
}

# Lines that repeat by syntax, not by copy-paste, so non-redundancy skips them
# (issue #7454). One is made only of brackets and separators, such as `}`,
# `});`, or `{ }`. The other is a bare attribute or annotation with no
# arguments, such as `[Fact]` or `@Override`; with arguments it still counts.
_STRUCTURAL_ONLY_LINE = re.compile(r"[{}()\[\];,]+(?:\s+[{}()\[\];,]+)*")
_BARE_ATTRIBUTE_LINE = re.compile(r"\[[A-Za-z_][\w.]*\]|@[A-Za-z_][\w.]*")

# Repo-root-anchored prefixes of build outputs (ADR-109, ADR-119). Under
# ADR-119, src/claude/skills/<name>/ scripts and the top-level src/claude/lib
# modules are hand-maintained source, so only the rendered parts of src/claude
# are listed. build/scripts/lib_mirror.py renders the three lib packages,
# bootstrap.py, and the review skill's validator sidecar from scripts/.
# Every outputDir in templates/platforms/*.yaml and every lib_mirror.py
# destination falls under one of these prefixes; test_assess.py pins that.
_GENERATED_PATH_SEGMENTS = (
    ("src", "claude", "agents"),
    ("src", "claude", "hooks"),
    ("src", "claude", "lib", "ai_review_common"),
    ("src", "claude", "lib", "bootstrap.py"),
    ("src", "claude", "lib", "failure_classifier"),
    ("src", "claude", "lib", "github_core"),
    ("src", "claude", "lib", "hook_utilities"),
    ("src", "claude", "lib", "memory_enhancement"),
    ("src", "claude", "rules"),
    ("src", "claude", "skills", "review", "scripts", "validate_review_marker.py"),
    ("src", "codex"),
    ("src", "copilot-cli"),
    ("src", "cursor"),
    ("src", "hermes"),
    ("src", "muse"),
    ("src", "vs-code-agents"),
    (".claude", "hooks"),
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
    "java": re.compile(r"^\s*import\s+[A-Za-z_]"),
    "go": re.compile(
        r'^\s*import\s+(?:(?:[A-Za-z_]\w*|\.)\s+)?"[^"]+"\s*(?://.*)?$'
        r'|^\s+(?:(?:[A-Za-z_]\w*|\.)\s+)?"[^"]+"\s*(?://.*)?$'
    ),
}

# Extracts the quoted import path from a line the Go import pattern matched.
_GO_IMPORT_PATH = re.compile(r'"([^"]+)"')

# Python dependency statements in the pinned tree-sitter-python grammar. A
# ``from __future__`` statement has its own node type.
_PY_DEPENDENCY_QUERY = (
    "[(import_statement) (import_from_statement) (future_import_statement)] @dependency"
)

# Top-level standard-library module names. ``sys.stdlib_module_names`` exists
# from Python 3.10, the plugin's syntax floor. An older interpreter gets an
# empty set, so every import stays scored and nothing is wrongly exempted.
_PY_STDLIB_MODULES = frozenset(getattr(sys, "stdlib_module_names", ()))

# Reads the module path from a go.mod ``module`` directive.
_GO_MODULE_DIRECTIVE = re.compile(r'^\s*module\s+"?([^"\s]+)"?', re.MULTILINE)

# Score at or above which an import count reads as reasonable. Matches the
# default ``coupling.min`` so the explanation agrees with the default verdict.
_COUPLING_REASONABLE_MIN = 7.0

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
    # True only when the scanner tried to score the file and could not (read,
    # decode, or assessment failure). A file in a language the scanner does
    # not support is also unscored, but it is not a failure, so it stays
    # False. Consumers use this to tell a hole in the evidence from a file
    # that was never in scope for scoring.
    scoring_failed: bool = False

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


_HELP_EPILOG = """\
examples:
  %(prog)s --target src/app.py --format json
  %(prog)s --target src --changed-only --base origin/main --gate-mode regression

exit codes:
  0  gate passed (or nothing changed in regression mode)
  1  invalid target, config error, or no files to assess
  10  regression: a quality regressed or scored evidence was lost
  11  a file is below the configured thresholds
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Assess code quality across 5 foundational qualities",
        allow_abbrev=False,
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--target", required=True, help="File, directory, or glob pattern to assess"
    )
    parser.add_argument(
        "--context",
        choices=["production", "test", "generated"],
        default=None,
        help=(
            "Force one threshold context for every file. When omitted, each "
            "file uses the context of its own category (authored=production, "
            "test, generated)."
        ),
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
        if glob_matches is None and not target_path.is_file() and not target_path.is_dir():
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

    statuses = (
        {c.head_path: c.status for c in changes if c.head_path is not None} if changed_only else {}
    )
    existing_files: list[Path] = []
    for file_path in files:
        if not file_path.exists():
            continue
        if file_path.is_dir() and _skip_directory(file_path, changed_only, statuses):
            continue
        _resolve_in_workspace(file_path, "assessment candidate")
        existing_files.append(file_path)
    return existing_files


def _skip_directory(path: Path, changed_only: bool, statuses: dict[Path, str]) -> bool:
    """Return True when a directory path is not a source file to score.

    git diff can list a symlink to a directory as one changed path. In
    changed-only mode that is reported on stderr, except for a
    type change (status ``T``), which still reaches scoring so the review
    adapter sees the failed score. Outside changed-only mode a glob can match
    directories as a matter of course, so they are skipped silently.
    """
    if not changed_only:
        return True
    if statuses.get(path, "").startswith("T"):
        return False
    print(f"SKIPPED (directory): {path}", file=sys.stderr)
    return True


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
                path_index < len(path_parts) and matches(path_index + 1, pattern_index)
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
    context: str | None,
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
        assessments[str(file_path)] = _assess_base_bytes(file_path, raw, revision, relative_path)
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
    csharp_parser_dependency_admission: dict[str, Any] | None = None
    typescript_parser_dependency_admission: dict[str, Any] | None = None
    python_parser_dependency_admission: dict[str, Any] | None = None
    rule_admissions: dict[str, dict[str, Any]] | None = None
    change_admissions: list[dict[str, Any]] | None = None
    base_blob: str | None = None
    head_blob: str | None = None

    def parser_dependency_admission(self) -> dict[str, Any] | None:
        """Return the admission record attached to this comparison, if any."""
        return (
            self.csharp_parser_dependency_admission
            or self.typescript_parser_dependency_admission
            or self.python_parser_dependency_admission
        )


def _python_external_imports(path: Path) -> set[str]:
    """Read import roots through Python's parser, including nested imports."""
    roots: set[str] = set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise ValueError(f"Cannot verify parser dependency admission for {path}: {exc}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            roots.add(
                node.module.split(".", 1)[0] if node.module and node.level == 0 else ".relative"
            )
    return roots - _PY_STDLIB_MODULES


def _admission_mismatch_reason(comparison: FileComparison, admission: dict[str, Any]) -> str | None:
    """Return why *comparison* is outside the admitted transition, or None if it matches."""
    if comparison.is_new_file or comparison.change_status != "M":
        return f"change status is {comparison.change_status}, not a modified file"
    if comparison.absolute_gate_reason is not None:
        return f"absolute gate applies: {comparison.absolute_gate_reason}"
    coupling = next((d for d in comparison.deltas if d.quality == "coupling"), None)
    if coupling is None:
        return "no coupling delta recorded"
    base, head = admission["baseScore"], admission["headScore"]
    observed = (coupling.base, coupling.head, coupling.delta, coupling.status)
    if observed != (base, head, round(head - base, 4), "compared"):
        return f"coupling transition {observed} differs from {base} -> {head}"
    imports = _python_external_imports(Path(comparison.file_path))
    if imports != set(admission["imports"]):
        return f"external imports {sorted(imports)} differ from the admitted set"
    return None


def _configured_parser_admissions(config: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    """Return each configured admission, refusing any that differs from its fixed record."""
    configured = []
    for key, (record, field) in _PARSER_DEPENDENCY_ADMISSIONS.items():
        if key not in config:
            continue
        if config[key] != record:
            raise ValueError(f"Invalid {key}: scope or authorization differs")
        configured.append((record, field))
    return configured


def _apply_parser_dependency_admissions(
    comparisons: list[FileComparison], config: dict[str, Any]
) -> None:
    """Admit only an authorized ADR-122 transition, without changing its evidence."""
    admissions = _configured_parser_admissions(config)
    for comparison in comparisons:
        candidates = [
            (record, field)
            for record, field in admissions
            if Path(comparison.file_path).as_posix() == record["file"]
        ]
        if not candidates or "coupling" not in comparison.regressions:
            continue
        reasons: list[str] = []
        for record, field in candidates:
            reason = _admission_mismatch_reason(comparison, record)
            if reason is None:
                setattr(comparison, field, dict(record))
                break
            reasons.append(f"issue #{record['issue']}: {reason}")
        else:
            for reason in reasons:
                print(f"NOT ADMITTED: {comparison.file_path}: {reason}", file=sys.stderr)


# Issue #7525 rule admissions: a change that replaces local logic with one shared import drops
# coupling a point per file, and a file that loses unique lines drops
# non-redundancy with no duplicate added. These admissions keep the raw score
# and row, and admit the drop only when the change added no new dependency or
# duplicate. The coupling admission is inert unless the config opts in.
_ISSUE_RULE_ADMISSIONS = 7525
_FIRST_PARTY_COUPLING_KEY = "firstPartyCouplingAdmission"
_COUPLING_RULE = "no_new_third_party_import"
_NON_REDUNDANCY_RULE = "no_new_duplicate_lines"
_GIT_LS_TREE_TIMEOUT_SECONDS = 60
# The test runner is not a dependency of the code under test: a test module
# that gains ``import pytest`` for ``mark.parametrize`` couples nothing new.
_TEST_RUNNER_ROOTS = frozenset({"pytest"})


def _is_test_module(path: Path) -> bool:
    """Return True for a ``test_*`` or ``conftest.py`` file under a ``tests`` folder.

    The caller passes a repo-relative path, and only Python files reach it.
    """
    name = path.name
    return "tests" in path.parts[:-1] and (name.startswith("test_") or name == "conftest.py")


def _first_party_import_roots(config: dict[str, Any]) -> list[Path] | None:
    """Return the configured import roots, or None when the admission is off."""
    record = config.get(_FIRST_PARTY_COUPLING_KEY)
    if record is None:
        return None
    roots = record.get("importRoots") if isinstance(record, dict) else None
    if (
        not isinstance(record, dict)
        or set(record) != {"importRoots"}
        or not isinstance(roots, list)
        or not all(isinstance(root, str) and root.strip() for root in roots)
    ):
        raise ValueError(f"Invalid {_FIRST_PARTY_COUPLING_KEY}: expected {{'importRoots': [str]}}")
    return [_resolve_in_workspace(Path(root), "importRoots entry") for root in roots]


@lru_cache(maxsize=1)
def _tracked_python_paths(workspace: Path) -> frozenset[str]:
    """Return ``.py`` paths in the HEAD commit under *workspace*, relative to it.

    The reviewed commit decides, not the disk or the index: an untracked,
    ignored, or staged-but-uncommitted file must not change a verdict on the
    committed diff (ci-scripts MUST 9).
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "ls-tree", "-r", "-z", "--name-only", "HEAD"],
            cwd=workspace,
            capture_output=True,
            check=False,
            timeout=_GIT_LS_TREE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"git ls-tree timed out after {_GIT_LS_TREE_TIMEOUT_SECONDS} seconds"
        ) from exc
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git ls-tree failed: {error}")
    paths = result.stdout.decode("utf-8").split("\0")
    return frozenset(path for path in paths if path.endswith(".py"))


@cache
def _is_installed_package(root: str) -> bool:
    """Return True when *root* is importable from the interpreter's site-packages.

    Only the site directories are searched, never ``sys.path``, so neither the
    checkout nor the scanner's own folder can supply a same-named decoy. An
    installed package therefore stays third-party.
    """
    import importlib.machinery
    import site
    import sysconfig

    site_dirs = {sysconfig.get_paths()[key] for key in ("purelib", "platlib")}
    site_dirs.update(site.getsitepackages())
    site_dirs.add(site.getusersitepackages())
    search = sorted(d for d in site_dirs if d and Path(d).is_dir())
    try:
        return importlib.machinery.PathFinder.find_spec(root, search) is not None
    except (ImportError, ValueError):
        return False


def _is_first_party_root(root: str, file_path: Path, import_roots: list[Path]) -> bool:
    """Return True when *root* names a tracked module or package in the checkout.

    Searched: the importing file's directory and each ancestor up to the
    workspace (``scripts.x`` from anywhere, a sibling module from a build
    script), then each configured import root (a plugin ``lib`` directory that
    callers put on ``sys.path``). A match is a tracked ``<root>.py`` or
    ``<root>/__init__.py``; a bare directory such as ``build/`` is not.
    """
    if _is_installed_package(root):
        return False
    workspace = Path.cwd().resolve()
    tracked = _tracked_python_paths(workspace)
    directory = (workspace / file_path).parent.resolve()
    candidates = [directory, *directory.parents]
    searched = [d for d in candidates if d.is_relative_to(workspace)]
    for base in [*searched, *import_roots]:
        relative = base.relative_to(workspace)
        for module in (relative / f"{root}.py", relative / root / "__init__.py"):
            if module.as_posix() in tracked:
                return True
    return False


def _python_third_party_roots(
    source: str, file_path: Path, import_roots: list[Path]
) -> set[str] | None:
    """Return the import roots *source* takes from outside the checkout.

    Standard library, relative, and first-party roots are excluded. None means
    the source does not parse, so no admission can be shown.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    roots = {name.split(".", 1)[0] for name in names}
    return {
        root
        for root in roots - _PY_STDLIB_MODULES
        if not _is_first_party_root(root, file_path, import_roots)
    }


def _coupling_admission(
    base_text: str,
    head_text: str,
    comparison: FileComparison,
    import_roots: list[Path],
) -> dict[str, Any] | None:
    """Admit a Python coupling drop whose third-party roots did not grow.

    In a test module, ``pytest`` is left out of both root sets before the
    comparison, so the record lists the roots that were compared.
    """
    head_path = Path(comparison.file_path)
    if detect_language(head_path) != "python":
        print(f"NOT ADMITTED: {head_path}: coupling: language is not Python", file=sys.stderr)
        return None
    base = _python_third_party_roots(base_text, head_path, import_roots)
    head = _python_third_party_roots(head_text, head_path, import_roots)
    if base is None or head is None:
        print(f"NOT ADMITTED: {head_path}: coupling: source does not parse", file=sys.stderr)
        return None
    if _is_test_module(head_path):
        base, head = base - _TEST_RUNNER_ROOTS, head - _TEST_RUNNER_ROOTS
    if not head <= base:
        added = ", ".join(sorted(head - base))
        print(f"NOT ADMITTED: {head_path}: coupling: new third-party {added}", file=sys.stderr)
        return None
    return {
        "issue": _ISSUE_RULE_ADMISSIONS,
        "rule": _COUPLING_RULE,
        "baseThirdParty": sorted(base),
        "headThirdParty": sorted(head),
    }


def _non_redundancy_admission(
    base_text: str, head_text: str, comparison: FileComparison
) -> dict[str, Any] | None:
    """Admit a non-redundancy drop that added no copy of any line.

    Each line's repeat count at head must not exceed its count at base, so
    removing one duplicate cannot pay for a new one elsewhere.
    """
    head_path = Path(comparison.file_path)
    base_path = Path(comparison.base_file_path or comparison.file_path)
    base = _duplicate_lines(_code_lines(base_text, detect_language(base_path)))
    head = _duplicate_lines(_code_lines(head_text, detect_language(head_path)))
    if head - base:
        print(f"NOT ADMITTED: {head_path}: non_redundancy: a line gained a copy", file=sys.stderr)
        return None
    return {
        "issue": _ISSUE_RULE_ADMISSIONS,
        "rule": _NON_REDUNDANCY_RULE,
        "baseDuplicateLines": base.total(),
        "headDuplicateLines": head.total(),
    }


def _comparison_texts(comparison: FileComparison, revision: str) -> tuple[str, str] | None:
    """Return the base and head text of a modified file, or None if unreadable."""
    if comparison.base_file_path is None:
        return None
    raw = get_file_at_revision(Path(comparison.base_file_path), revision)
    if raw is None:
        return None
    try:
        return raw.decode("utf-8"), Path(comparison.file_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _apply_rule_admissions(
    comparisons: list[FileComparison], config: dict[str, Any], base: str | None
) -> None:
    """Admit coupling and non-redundancy drops that add no dependency or duplicate."""
    import_roots = _first_party_import_roots(config)
    # HEAD can move between runs in one process (tests commit); read it fresh per run.
    _tracked_python_paths.cache_clear()
    revision: str | None = None
    for comparison in comparisons:
        wanted = [
            quality
            for quality in comparison.regressions
            if quality == "non_redundancy" or (quality == "coupling" and import_roots is not None)
        ]
        if (
            not wanted
            or base is None
            or comparison.is_new_file
            or comparison.absolute_gate_reason is not None
            or comparison.parser_dependency_admission() is not None
            or comparison.change_admissions is not None
        ):
            continue
        revision = revision or resolve_comparison_base(base)
        texts = _comparison_texts(comparison, revision)
        if texts is None:
            for quality in wanted:
                print(
                    f"NOT ADMITTED: {comparison.file_path}: {quality}: base or head text is unreadable",
                    file=sys.stderr,
                )
            continue
        records: dict[str, dict[str, Any]] = {}
        for quality in wanted:
            record = (
                _coupling_admission(*texts, comparison, import_roots or [])
                if quality == "coupling"
                else _non_redundancy_admission(*texts, comparison)
            )
            if record is not None:
                records[quality] = record
        comparison.rule_admissions = records or None


def _git_blob(*args: str) -> str | None:
    """Run a git blob-id command and return its first output line, or None on failure."""
    import subprocess

    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    lines = result.stdout.split()
    return lines[0] if result.returncode == 0 and lines else None


def _blob_ids(path: str, base_revision: str | None) -> tuple[str | None, str | None]:
    """Return the git blob ids of *path* at *base_revision* and in the working tree."""
    base = None
    if base_revision is not None:
        # Without --verify, rev-parse echoes --end-of-options as an output line.
        base = _git_blob(
            "rev-parse", "--verify", "--quiet", "--end-of-options", f"{base_revision}:{path}"
        )
    return base, _git_blob("hash-object", "--", path)


def _change_admission_mismatch(
    comparison: FileComparison, record: dict[str, Any], blobs: tuple[str | None, str | None]
) -> str | None:
    """Return why *comparison* is outside the record's transition, or None if it matches."""
    if comparison.is_new_file or comparison.change_status != "M":
        return f"change status is {comparison.change_status}, not a modified file"
    if comparison.absolute_gate_reason is not None:
        return f"absolute gate applies: {comparison.absolute_gate_reason}"
    if comparison.evidence_loss:
        return f"evidence loss in {comparison.evidence_loss}"
    quality, base, head = record["quality"], record["baseScore"], record["headScore"]
    delta = next((d for d in comparison.deltas if d.quality == quality), None)
    if delta is None:
        return f"no {quality} delta recorded"
    observed = (delta.base, delta.head, delta.delta, delta.status)
    if observed != (base, head, round(head - base, 4), "compared"):
        return f"{quality} transition {observed} differs from {base} -> {head}"
    if blobs != (record["baseBlob"], record["headBlob"]):
        return f"file content differs from the pinned blobs {blobs}"
    return None


def _apply_change_admissions(
    comparisons: list[FileComparison],
    config: dict[str, Any],
    base_revision: str | None = None,
) -> None:
    """Admit a comparison only when every regressed quality has a matching record."""
    if "changeAdmissions" not in config:
        return
    if config["changeAdmissions"] != list(_CHANGE_ADMISSIONS):
        raise ValueError("Invalid changeAdmissions: scope or authorization differs")
    for comparison in comparisons:
        path = Path(comparison.file_path).as_posix()
        records = [r for r in _CHANGE_ADMISSIONS if r["file"] == path]
        if not records or not comparison.regressions:
            continue
        blobs = _blob_ids(path, base_revision)
        matched: list[dict[str, Any]] = []
        for quality in comparison.regressions:
            reasons = ["no record for this file and quality"]
            for record in (r for r in records if r["quality"] == quality):
                reason = _change_admission_mismatch(comparison, record, blobs)
                if reason is None:
                    matched.append(dict(record))
                    break
                reasons = [reason]
            else:
                print(f"NOT ADMITTED: {path}: {quality}: {reasons[0]}", file=sys.stderr)
        if len(matched) == len(comparison.regressions):
            comparison.change_admissions = matched
            comparison.base_blob, comparison.head_blob = blobs


def _admission_notice(comparison: FileComparison, quality: str) -> str | None:
    """Return the ADMITTED line for one regressed quality, or None when it is not admitted."""
    approval = comparison.parser_dependency_admission()
    if not (quality == "coupling" and approval):
        approval = next(
            (r for r in comparison.change_admissions or [] if r["quality"] == quality), None
        )
    if approval is None:
        rule = (comparison.rule_admissions or {}).get(quality)
        if rule is None:
            return None
        added = "third-party import" if quality == "coupling" else "duplicate line"
        return (
            f"ADMITTED: issue #{rule['issue']}, rule {rule['rule']}: the change added "
            f"no new {added}. Raw {quality} regression remains reported."
        )
    return (
        f"ADMITTED: issue #{approval['issue']}, authorized by "
        f"{approval['authorizedBy']} on {approval['authorizedOn']}: "
        f"{approval['authorization']} Raw {quality} regression remains reported."
    )


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


def _unscored_by_category(field: str, head: FileAssessment) -> bool:
    """Return True when *head*'s category leaves *field* unscored by design.

    A file that moves into a category the scanner does not score for that
    quality (an authored module renamed under ``tests/``) lost no evidence.
    """
    return head.category == "generated" or (field == "cohesion" and head.category == "test")


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
        elif delta.status == "evidence_lost" and not _unscored_by_category(field, head):
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
    return any(getattr(assessment, field).confidence > 0.0 for field in _QUALITY_FIELDS)


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
        change.head_path: change for change in (changed_files or []) if change.head_path is not None
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
        base_assessment = _assess_base_bytes(base_path, raw, revision)
        absolute_reason = None if _has_scored_quality(base_assessment) else "base_unscored"
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


def _assess_base_bytes(
    path: Path,
    raw: bytes,
    revision: str | None = None,
    revision_path: Path | None = None,
) -> FileAssessment:
    """Score the base revision's bytes, or record it as unmeasurable.

    An undecodable base scores nothing, so every quality reads as newly scored
    and no delta is fabricated from a file the assessor could not read. With
    *revision*, Go module context comes from that revision's go.mod, found
    from *revision_path* (the path ``git show`` accepts, default *path*).
    """
    resolver: Callable[[], str | None] | None = None
    if revision is not None:
        resolver = partial(_go_module_path_at_revision, revision_path or path, revision)

    try:
        return assess_content(path, raw.decode("utf-8"), resolver)
    except UnicodeDecodeError as exc:
        return _unreadable_assessment(path, f"decode failed at base: {exc}")
    except ParserError as exc:
        where = f"{path} at {revision}" if revision is not None else str(path)
        raise type(exc)(f"{where}: {exc}") from exc


def check_regression(
    comparisons: list[FileComparison],
    new_file_assessments: list[FileAssessment],
    config: dict[str, Any],
    context: str | None,
) -> int:
    """Gate on change, not on inherited debt.

    Returns:
        0:  no unadmitted regression and no new file failed absolutely
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
            notice = _admission_notice(comparison, quality)
            if notice is None:
                degraded = True
            else:
                print(notice, file=sys.stderr)
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


# A test module defines one function per case, so the size+definition proxy
# reads a focused suite as many unrelated responsibilities. Measured on issue
# #7410: a 273-line module of 30 related tests scored 1.0 and failed the gate.
_TEST_COHESION_REASON = (
    "Not scored for test modules: each test case counts as a definition, so the "
    "size+definition proxy penalizes cohesive suites (issue #7410)"
)


def _unscored_test_cohesion() -> QualityScore:
    return QualityScore(value=10.0, confidence=0.0, reasons=[_TEST_COHESION_REASON])


def _parse_go_module(raw: bytes) -> str | None:
    """Return the ``module`` directive of go.mod bytes, or None if unreadable."""
    try:
        match = _GO_MODULE_DIRECTIVE.search(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return None
    return match.group(1) if match else None


def _go_module_path(file_path: Path | None) -> str | None:
    """Return the module path from the nearest working-tree go.mod.

    The module's own packages are application coupling even when the module
    path has no dot (``module myapp``), so they must not read as standard
    library. Returns None when no readable go.mod declares a module.
    """
    if file_path is None:
        return None
    for directory in Path(file_path).resolve().parents:
        go_mod = directory / "go.mod"
        if not go_mod.is_file():
            continue
        try:
            return _parse_go_module(go_mod.read_bytes())
        except OSError:
            return None
    return None


def _go_module_path_at_revision(file_path: Path, revision: str) -> str | None:
    """Return the module path from the nearest go.mod at *revision*.

    Base scoring must read the base go.mod, not the working tree's. A renamed
    dotless module would otherwise classify the base's own imports as
    standard library and report a false coupling regression.
    """
    for directory in file_path.parents:
        raw = get_file_at_revision(directory / "go.mod", revision)
        if raw is not None:
            return _parse_go_module(raw)
    return None


def _is_go_standard_import(import_path: str, module_path: str | None) -> bool:
    """Classify a Go import path as standard library.

    Uses the Go toolchain rule: a standard path's first element has no dot.
    ``C`` (cgo) is a foreign-code dependency, and the enclosing module's own
    packages are application code, so neither counts as standard.
    """
    if import_path == "C":
        return False
    if module_path and (import_path == module_path or import_path.startswith(module_path + "/")):
        return False
    return "." not in import_path.split("/", 1)[0]


def _python_module_name(node: Any) -> str:
    """Return the module a ``dotted_name`` or ``relative_import`` node names.

    The name is built from identifier children, because node text keeps any
    spaces, comments, or line continuations around the dots (``os .path``).
    A relative module keeps one leading dot per level, so it reads as
    first-party.
    """
    if node.type == "relative_import":
        prefix = next(child for child in node.children if child.type == "import_prefix")
        dots = "." * prefix.text.decode("utf-8").count(".")
        names = [_python_module_name(c) for c in node.children if c.type == "dotted_name"]
        return str(dots + "".join(names))
    return ".".join(
        child.text.decode("utf-8") for child in node.children if child.type == "identifier"
    )


def _python_statement_modules(node: Any) -> list[str]:
    """Return the module names one Python dependency statement binds."""
    if node.type == "future_import_statement":
        return ["__future__"]
    if node.type == "import_from_statement":
        module = node.child_by_field_name("module_name")
        if module is None:
            raise PythonParserError(
                f"Cannot count Python dependencies: a from-import at line "
                f"{node.start_point[0] + 1} has no module name in the parse tree"
            )
        return [_python_module_name(module)]
    modules = []
    for name in node.children_by_field_name("name"):
        if name.type == "aliased_import":
            name = name.child_by_field_name("name")
        modules.append(_python_module_name(name))
    return modules


def _is_python_standard_statement(modules: list[str]) -> bool:
    """Classify one statement as standard library only.

    A statement that binds several modules (``import os, requests``) is
    standard only when every module is, so one third-party name keeps the whole
    statement scored. Relative imports are first-party.
    """
    return bool(modules) and all(
        not module.startswith(".") and module.split(".", 1)[0] in _PY_STDLIB_MODULES
        for module in modules
    )


class ParserError(RuntimeError):
    """Dependencies of a parsed language cannot be measured reliably.

    Every subclass is fatal (exit 1): no score is guessed for such a file.
    """


class CSharpParserError(ParserError):
    """C# dependencies cannot be measured reliably."""


class PowerShellParserError(ParserError):
    """PowerShell dependencies cannot be measured reliably."""


_PWSH_TIMEOUT_SECONDS = 60

# PowerShell resolves `using module` and `using assembly` targets while it
# parses: it reads local files, searches PSModulePath, and on Windows opens an
# SMB connection for a UNC target, which can send credentials (CWE-829). A
# `configuration` block loads DSC resources for `Import-DscResource` at parse
# time too. Every public parse and tokenize API does this. So the scanner
# rewrites each keyword to an inert command name before pwsh sees the source.
# PowerShell matches keywords by ASCII case (tested on pwsh 7.6.10); the
# Unicode-aware match below also rewrites lookalikes such as U+017F, which is
# harmless. The rewrite keeps line numbers and keeps valid syntax valid. The
# parser then sees each `using` statement as a command named the sentinel.
_PWSH_USING_SENTINEL = "__ptk_using__"
_PWSH_NEUTRALIZED_KEYWORDS = (
    (re.compile("using", re.IGNORECASE), _PWSH_USING_SENTINEL),
    (re.compile("configuration", re.IGNORECASE), "__ptk_configuration__"),
)

# With `using namespace` and `using module` rewritten, a class that names a
# type those statements would have brought in reports TypeNotFound. That is a
# lookup on the scanning machine, not a syntax error, so it never fails a scan.
_PWSH_TYPE_LOOKUP_ERROR_IDS = ("TypeNotFound",)

# Runs inside pwsh. Reads base64 UTF-8 source from stdin so no console code
# page can alter it, parses it without executing it, and prints one JSON line.
# Counted forms: Import-Module and ipmo calls (module-qualified or not),
# neutralized using module/namespace/assembly statements, and #Requires lines
# that PowerShell reads as naming modules (any -Modules abbreviation).
# The first parse finds the neutralized using statements. They are then blanked,
# keeping newlines, and the source is parsed again, because a using statement
# rewritten as a command would end the header where `[CmdletBinding()] param()`
# is legal. The second parse supplies the syntax errors and other counts.
# Runs first. An older pwsh exits 3, which the scanner reports as a failure.
_PWSH_VERSION_GUARD = r"""
if ($PSVersionTable.PSVersion.Major -lt 7) {
    [Console]::Error.WriteLine("PowerShell 7 or later is required; found $($PSVersionTable.PSVersion)")
    exit 3
}
"""

_PWSH_COUNT_SCRIPT = (
    _PWSH_VERSION_GUARD
    + r"""
$ErrorActionPreference = 'Stop'
function Read-Script([string]$text) {
    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseInput($text, [ref]$tokens, [ref]$errors)
    return ,@($ast, $tokens, $errors)
}
$encoded = [Console]::In.ReadToEnd().Trim()
$source = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded))
$usingKinds = @('module', 'namespace', 'assembly')
$bareWord = [System.Management.Automation.Language.StringConstantType]::BareWord
function Test-BareWord($element, [string]$value) {
    return ($element -is [System.Management.Automation.Language.StringConstantExpressionAst] -and
        $element.StringConstantType -eq $bareWord -and ($value -eq '' -or $element.Value -ceq $value))
}
$first = Read-Script $source
$sentinelCommands = @($first[0].FindAll({
    param($node)
    return ($node -is [System.Management.Automation.Language.CommandAst] -and
        $node.InvocationOperator -eq 'Unknown' -and (Test-BareWord $node.CommandElements[0] '__SENTINEL__'))
}, $true))
# Every rewritten `using` must be a statement PowerShell would accept, because
# the rewrite hides the errors PowerShell reports for it. Check kind, operand,
# arity, and placement (top level, before any other statement) here.
$root = $first[0]
$topBlocks = @($root.BeginBlock, $root.ProcessBlock, $root.EndBlock, $root.DynamicParamBlock) |
    Where-Object { $_ }
$headerEnd = [int]::MaxValue
if ($root.ParamBlock) { $headerEnd = $root.ParamBlock.Extent.StartOffset }
foreach ($block in $topBlocks) {
    # A top-level trap lives in Traps, not Statements, and still ends the header.
    foreach ($trap in $block.Traps) {
        if ($trap.Extent.StartOffset -lt $headerEnd) { $headerEnd = $trap.Extent.StartOffset }
    }
    foreach ($statement in $block.Statements) {
        $isUsing = $statement -is [System.Management.Automation.Language.PipelineAst] -and
            $statement.PipelineElements.Count -eq 1 -and $sentinelCommands -contains $statement.PipelineElements[0]
        if (-not $isUsing -and $statement.Extent.StartOffset -lt $headerEnd) {
            $headerEnd = $statement.Extent.StartOffset
        }
    }
}
$usingStatements = @()
$usingErrors = @()
foreach ($command in $sentinelCommands) {
    $elements = $command.CommandElements
    $kind = if ($elements.Count -ge 2 -and (Test-BareWord $elements[1] '')) { $elements[1].Value.ToLowerInvariant() } else { '' }
    $operand = if ($elements.Count -ge 3) { $elements[2] } else { $null }
    $errorId = $null
    if ($elements.Count -eq 1 -or $usingKinds -notcontains $kind) {
        $errorId = 'MissingUsingStatementDirective'
    } elseif ($elements.Count -eq 2) {
        $errorId = 'MissingUsingItemName'
    } elseif ($elements.Count -gt 3 -or $command.Redirections.Count -gt 0) {
        $errorId = 'MissingStatementTerminator'
    } elseif (-not ($operand -is [System.Management.Automation.Language.StringConstantExpressionAst] -or
            ($kind -eq 'module' -and $operand -is [System.Management.Automation.Language.HashtableAst]))) {
        $errorId = 'InvalidValueForUsingItemName'
    } elseif (-not ($command.Parent -is [System.Management.Automation.Language.PipelineAst] -and
            $topBlocks -contains $command.Parent.Parent -and $command.Parent.Parent.Unnamed -and
            $command.Extent.StartOffset -lt $headerEnd)) {
        $errorId = 'UsingMustBeAtStartOfScript'
    }
    if ($errorId) {
        $usingErrors += [pscustomobject]@{
            id = $errorId; line = $command.Extent.StartLineNumber; message = "Invalid using statement ($errorId)."
        }
    } else {
        $usingStatements += $command
        # Blanking removes the operand, so keep any error PowerShell found inside it,
        # such as a duplicate key in a `using module` hashtable.
        foreach ($inner in $first[2]) {
            $offset = $inner.Extent.StartOffset
            if ($offset -ge $command.Extent.StartOffset -and $offset -lt $command.Extent.EndOffset) {
                $usingErrors += [pscustomobject]@{
                    id = $inner.ErrorId; line = $inner.Extent.StartLineNumber
                    message = "$($inner.Message) ($($inner.ErrorId))"
                }
            }
        }
    }
}
# Blank each statement, plus trailing blanks and a `;` terminator, keeping newlines.
$chars = $source.ToCharArray()
foreach ($statement in $usingStatements) {
    $end = $statement.Extent.EndOffset
    $next = $end
    while ($next -lt $chars.Length -and ($chars[$next] -eq ' ' -or $chars[$next] -eq "`t")) { $next++ }
    if ($next -lt $chars.Length -and $chars[$next] -eq ';') { $end = $next + 1 }
    for ($i = $statement.Extent.StartOffset; $i -lt $end; $i++) {
        if ($chars[$i] -ne "`n" -and $chars[$i] -ne "`r") { $chars[$i] = ' ' }
    }
}
$second = Read-Script (-join $chars)
$ast = $second[0]
$tokens = $second[1]
$errors = $second[2]
$importNames = @('import-module', 'ipmo')
$imports = @($ast.FindAll({
    param($node)
    if ($node -isnot [System.Management.Automation.Language.CommandAst]) { return $false }
    $name = "$($node.GetCommandName())".Split('\')[-1].ToLowerInvariant()
    return $importNames -contains $name
}, $true)).Count
$requires = @($tokens | Where-Object {
    $_.Kind -eq 'Comment' -and $_.Text -match '^#requires\b' -and
        @((Read-Script $_.Text)[0].ScriptRequirements.RequiredModules).Count -gt 0
}).Count
$parseErrors = @($usingErrors) + @($errors | ForEach-Object {
    [pscustomobject]@{ id = $_.ErrorId; line = $_.Extent.StartLineNumber; message = $_.Message }
})
[pscustomobject]@{ count = $imports + $usingStatements.Count + $requires; errors = $parseErrors } |
    ConvertTo-Json -Compress -Depth 3 -EscapeHandling EscapeNonAscii
""".replace("__SENTINEL__", _PWSH_USING_SENTINEL)
)


class TypeScriptParserError(ParserError):
    """TypeScript dependencies cannot be measured reliably."""


class JavaScriptParserError(ParserError):
    """JavaScript dependencies cannot be measured reliably."""


class PythonParserError(ParserError):
    """Python dependencies cannot be measured reliably."""


@dataclass(frozen=True)
class _DependencyGrammar:
    """One pinned Tree-sitter grammar and the messages its failures print."""

    language_name: str
    packages: str
    reference: str
    unsupported_syntax: str
    error: type[ParserError]
    load: Callable[[], object]
    query: str


def _csharp_grammar() -> object:
    import tree_sitter_c_sharp

    return tree_sitter_c_sharp.language()


def _python_grammar() -> object:
    import tree_sitter_python

    return tree_sitter_python.language()


def _typescript_grammar(function_name: str) -> object:
    import tree_sitter_typescript

    return getattr(tree_sitter_typescript, function_name)()


_CSHARP_GRAMMAR = _DependencyGrammar(
    language_name="C#",
    packages="tree-sitter==0.26.1 and tree-sitter-c-sharp==0.23.5",
    reference="references/csharp-parser.md",
    unsupported_syntax=(
        "Cannot count C# dependencies: the pinned C# grammar "
        "(tree-sitter-c-sharp==0.23.5) could not parse this file. "
        "The file has a syntax error, or it is valid C# that the grammar "
        "does not support (for example a signature split across #if/#else, "
        "or C# 14 extension blocks)"
    ),
    error=CSharpParserError,
    load=_csharp_grammar,
    query="(using_directive) @dependency",
)

_PYTHON_GRAMMAR = _DependencyGrammar(
    language_name="Python",
    packages="tree-sitter==0.26.1 and tree-sitter-python==0.25.0",
    reference="references/python-parser.md",
    unsupported_syntax=(
        "Cannot count Python dependencies: the pinned Python grammar "
        "(tree-sitter-python==0.25.0) could not parse this file. "
        "The file has a syntax error, or it uses syntax the grammar "
        "does not support (for example Python 3.15 lazy imports)"
    ),
    error=PythonParserError,
    load=_python_grammar,
    query=_PY_DEPENDENCY_QUERY,
)

# Import and re-export statements with a source, require("...") calls, and
# dynamic import() calls. `import x = require("y")` is one import_statement.
# `export { a }` with no source names no module, so it is not a dependency.
_TYPESCRIPT_DEPENDENCY_QUERY = """
(import_statement) @dependency
(export_statement source: (_)) @dependency
(call_expression
  function: (identifier) @_callee
  arguments: (arguments)
  (#eq? @_callee "require")) @dependency
(call_expression function: (import)) @dependency
"""

_TYPESCRIPT_UNSUPPORTED_SYNTAX = (
    "Cannot count TypeScript dependencies: the pinned TypeScript grammar "
    "(tree-sitter-typescript==0.23.2) could not parse this file. "
    "The file has a syntax error, or it is valid TypeScript that the grammar "
    "does not support (for example `export type * from`, or `in`/`out` "
    "variance annotations)"
)

_TYPESCRIPT_PACKAGES = "tree-sitter==0.26.1 and tree-sitter-typescript==0.23.2"

# .tsx needs its own grammar: `<T>value` is a type cast in .ts and JSX in .tsx.
_TYPESCRIPT_GRAMMARS = {
    suffix: _DependencyGrammar(
        language_name="TypeScript",
        packages=_TYPESCRIPT_PACKAGES,
        reference="references/typescript-parser.md",
        unsupported_syntax=_TYPESCRIPT_UNSUPPORTED_SYNTAX,
        error=TypeScriptParserError,
        load=partial(_typescript_grammar, function_name),
        query=_TYPESCRIPT_DEPENDENCY_QUERY,
    )
    for suffix, function_name in ((".ts", "language_typescript"), (".tsx", "language_tsx"))
}

# JavaScript reuses the TSX grammar and query (issue #7434), so it adds no
# parser import and no scanner coupling. TSX parses JavaScript, JSX, and Flow
# annotations. It rejects TypeScript keywords used as identifiers.
_JAVASCRIPT_GRAMMAR = _DependencyGrammar(
    language_name="JavaScript",
    packages=_TYPESCRIPT_PACKAGES,
    reference="references/typescript-parser.md",
    unsupported_syntax=(
        "Cannot count JavaScript dependencies: the pinned TSX grammar "
        "(tree-sitter-typescript==0.23.2) could not parse this file. "
        "The file has a syntax error, or it is valid JavaScript that the grammar "
        "does not support (for example a TypeScript keyword such as `interface` "
        "used as an identifier)"
    ),
    error=JavaScriptParserError,
    load=partial(_typescript_grammar, "language_tsx"),
    query=_TYPESCRIPT_DEPENDENCY_QUERY,
)


def _count_dependency_nodes(source: str, grammar: _DependencyGrammar) -> int:
    """Count dependency syntax nodes, never comments, strings, or lookalike text."""
    return len(_dependency_nodes(source, grammar))


def _dependency_nodes(source: str, grammar: _DependencyGrammar) -> list[Any]:
    """Return the dependency syntax nodes, never comments, strings, or lookalike text."""
    try:
        from tree_sitter import Language, Parser, Query, QueryCursor

        language = Language(grammar.load())
        tree = Parser(language).parse(source.encode("utf-8"))
        if tree.root_node.has_error:
            raise grammar.error(grammar.unsupported_syntax)
        query = Query(language, grammar.query)
        nodes: list[Any] = QueryCursor(query).captures(tree.root_node).get("dependency", [])
        return nodes
    except ParserError:
        raise
    except ImportError as exc:
        raise grammar.error(
            f"{grammar.language_name} parser packages are missing: {exc}. Install "
            f"{grammar.packages} into a virtual environment that runs the scanner, "
            f"not the system Python (see {grammar.reference})"
        ) from exc
    except Exception as exc:
        raise grammar.error(
            f"{grammar.language_name} parser failed to start or run: "
            f"{type(exc).__name__}: {exc}. Check the pinned versions ({grammar.packages})"
        ) from exc


def _csharp_root_namespace(node: Any) -> str | None:
    """Return the first namespace segment a C# name node refers to.

    ``global::`` is the root namespace, so ``global::System.IO`` starts with
    ``System``. An extern alias (``Lib::System``) names another assembly, so it
    returns None. A tuple, array, nullable, pointer, or keyword alias target is
    not a name node, so it returns None and stays scored, even when its element
    type is a ``System`` type such as ``System.Int32[]``.
    """
    while node.type in ("qualified_name", "generic_name"):
        node = (
            node.child_by_field_name("qualifier")
            if node.type == "qualified_name"
            else next(c for c in node.named_children if c.type == "identifier")
        )
    if node.type == "alias_qualified_name":
        if node.child_by_field_name("alias").text != b"global":
            return None
        node = node.child_by_field_name("name")
    if node.type != "identifier":
        return None
    name: str = node.text.decode("utf-8")
    return name.removeprefix("@")


def _is_csharp_standard_directive(directive: Any) -> bool:
    """Classify one ``using`` directive as importing the ``System`` namespace tree.

    The target is the directive's last non-comment named child; for an alias
    directive the ``name`` field holds the alias, so the target follows it.
    """
    alias = directive.child_by_field_name("name")
    targets = [
        child
        for child in directive.named_children
        if child.type != "comment" and (alias is None or child.id != alias.id)
    ]
    if not targets:
        # Defensive: the pinned grammar rejects `using ;` as a parse error
        # first. A grammar change must still fail closed, not guess a score.
        raise CSharpParserError(
            f"Cannot count C# dependencies: the using directive on line "
            f"{directive.start_point[0] + 1} has no target. "
            f"Check the pinned versions ({_CSHARP_GRAMMAR.packages})"
        )
    return _csharp_root_namespace(targets[-1]) == "System"


def _count_csharp_imports(source: str) -> tuple[int, int]:
    """Count directive syntax nodes, not resource declarations or literal text.

    Returns the directive count and how many of those have a target rooted at
    the ``System`` namespace, whatever assembly provides it (issue #7459).
    """
    directives = _dependency_nodes(source, _CSHARP_GRAMMAR)
    try:
        # A list, not a generator: PEP 479 would turn StopIteration into RuntimeError.
        standard = len([node for node in directives if _is_csharp_standard_directive(node)])
    except (AttributeError, StopIteration) as exc:
        # A node shape the pinned grammar should never produce: fail closed.
        raise CSharpParserError(
            f"Cannot count C# dependencies: unexpected parse-tree shape "
            f"({type(exc).__name__}). Check the pinned versions ({_CSHARP_GRAMMAR.packages})"
        ) from exc
    return len(directives), standard


def _count_python_imports(source: str) -> tuple[int, int]:
    """Count Python dependency statements from a syntax tree.

    Returns the statement count and how many of those are standard library
    only. Imports nested in functions, classes, and ``try`` blocks count;
    text in strings and comments does not.
    """
    statements = _dependency_nodes(source, _PYTHON_GRAMMAR)
    try:
        # A list, not a generator: PEP 479 would turn StopIteration into RuntimeError.
        modules = [_python_statement_modules(node) for node in statements]
    except (AttributeError, StopIteration) as exc:
        # A node shape the pinned grammar should never produce: fail closed
        # rather than let the generic handler mark the file unscored.
        raise PythonParserError(
            f"Cannot count Python dependencies: unexpected parse-tree shape "
            f"({type(exc).__name__}). Check the pinned grammar (tree-sitter-python==0.25.0)"
        ) from exc
    standard = sum(1 for names in modules if _is_python_standard_statement(names))
    return len(statements), standard


def _count_javascript_imports(source: str) -> int:
    """Count JavaScript dependency nodes with the TSX grammar."""
    return _count_dependency_nodes(source, _JAVASCRIPT_GRAMMAR)


def _count_typescript_imports(source: str, suffix: str) -> int:
    """Count TypeScript dependency nodes with the grammar for *suffix*."""
    return _count_dependency_nodes(source, _TYPESCRIPT_GRAMMARS[suffix])


def _pwsh_rejection(pwsh: Path) -> str | None:
    """Return why *pwsh* must not run, or None when it is an installed pwsh."""
    if sys.platform == "win32" and pwsh.suffix.lower() != ".exe":
        return f"Refusing to run {pwsh}: pwsh on Windows must be pwsh.exe"
    scanned = Path.cwd().resolve()
    if pwsh.is_relative_to(scanned) or pwsh.resolve().is_relative_to(scanned):
        return f"Refusing to run {pwsh}: it is inside the scanned directory, not an installed pwsh"
    return None


def _find_pwsh() -> str:
    """Return the first eligible pwsh on an absolute PATH entry (CWE-427).

    Relative PATH entries resolve against the scanned checkout, where a planted
    `pwsh` could run in place of PowerShell. Each entry is searched in order,
    so an ineligible match (a `pwsh.cmd` shim, or a copy inside the checkout)
    does not hide a real pwsh in a later entry.
    """
    import os
    import shutil

    name = "pwsh.exe" if sys.platform == "win32" else "pwsh"
    rejection = None
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or not os.path.isabs(entry):
            continue
        found = shutil.which(name, path=entry)
        if found is None:
            continue
        # Run the PATH entry itself, not its symlink target: a Snap install
        # links /snap/bin/pwsh to /usr/bin/snap, which dispatches on its name.
        pwsh = Path(found).absolute()
        rejection = _pwsh_rejection(pwsh)
        if rejection is None:
            return str(pwsh)
    raise PowerShellParserError(
        rejection
        or "PowerShell 7 (pwsh) is not on PATH. It is required to count "
        "PowerShell dependencies (see references/powershell-parser.md)"
    )


def _neutralize_using(source: str) -> str:
    """Rewrite each resolving keyword so pwsh loads no module, assembly, or resource."""
    for keyword, sentinel in _PWSH_NEUTRALIZED_KEYWORDS:
        source = keyword.sub(sentinel, source)
    return source


def _run_pwsh_counter(source: str) -> dict[str, Any]:
    """Run PowerShell's own parser over *source* and return its JSON result.

    The source is neutralized first (see _PWSH_USING_SENTINEL), so parsing
    reads no other file and opens no connection. pwsh also runs from an empty
    temporary directory. The source travels as stdin data, never as a command
    argument (CWE-78).
    """
    import base64
    import subprocess
    import tempfile

    pwsh = _find_pwsh()
    command = base64.b64encode(_PWSH_COUNT_SCRIPT.encode("utf-16-le")).decode("ascii")
    payload = base64.b64encode(_neutralize_using(source).encode("utf-8")).decode("ascii")
    argv = [pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", command]
    try:
        # A cleanup failure (Windows can hold the directory briefly) must not
        # discard a finished parse, so cleanup errors are ignored.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as empty_dir:
            result = subprocess.run(
                argv,
                input=payload,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_PWSH_TIMEOUT_SECONDS,
                cwd=empty_dir,
                check=False,
            )
    except subprocess.TimeoutExpired as exc:
        raise PowerShellParserError(
            f"PowerShell parser timed out after {_PWSH_TIMEOUT_SECONDS} seconds"
        ) from exc
    except OSError as exc:
        raise PowerShellParserError(f"PowerShell parser failed to start: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-500:]
        raise PowerShellParserError(
            f"PowerShell parser exited {result.returncode}: {detail or 'no output'}"
        )
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PowerShellParserError(
            f"PowerShell parser returned unreadable output: {result.stdout[:200]!r}"
        ) from exc
    if not isinstance(parsed, dict):
        raise PowerShellParserError(f"PowerShell parser returned {type(parsed).__name__}")
    return parsed


def _count_powershell_imports(source: str) -> int:
    """Count dependency statements from PowerShell's syntax tree, not regex.

    Strings and comments do not count, except `#Requires -Modules`, which
    PowerShell itself treats as a statement. A syntax error is fatal: no count
    is guessed. No module or assembly is resolved, so a missing one is not an
    error, and neither is a type only that resolution would have supplied.
    """
    parsed = _run_pwsh_counter(source)
    errors = parsed.get("errors")
    errors = [errors] if isinstance(errors, dict) else errors
    if not isinstance(errors, list):
        raise PowerShellParserError(f"PowerShell parser returned errors as {errors!r}")
    errors = [
        error
        for error in errors
        if not (isinstance(error, dict) and error.get("id") in _PWSH_TYPE_LOOKUP_ERROR_IDS)
    ]
    if errors:
        first = errors[0]
        where = f"line {first.get('line')}: " if isinstance(first, dict) else ""
        message = first.get("message") if isinstance(first, dict) else first
        raise PowerShellParserError(
            f"Cannot count PowerShell dependencies: PowerShell reports "
            f"{len(errors)} syntax error(s), first at {where}{message}"
        )
    count = parsed.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise PowerShellParserError(f"PowerShell parser returned count {count!r}")
    return count


def _score_coupling(
    language: str | None,
    code_lines: list[str],
    go_module_resolver: Callable[[], str | None] | None = None,
    suffix: str = "",
) -> QualityScore:
    """Approximate coupling from the number of import/dependency statements.

    A high score means loose coupling (few imports), which is good, matching
    the rubric where 10 is best. Languages without a tuned import pattern are
    counted with a generic fallback for the report but returned at confidence
    0.0 so the threshold gate does not fail a file scored only by that
    untuned heuristic (matches the file-header contract).

    C#, TypeScript, JavaScript, Python, and PowerShell receive original source
    lines for syntax-tree parsing; *suffix* picks the TypeScript or TSX grammar.
    Other languages receive filtered code lines. Go and Python standard-library
    imports and C# ``System`` namespace directives are reported but not scored:
    they are stable utilities, not application or third-party coupling
    (issues #7047, #7354, and #7459).
    """
    pattern = _IMPORT_PATTERNS.get(language) if language else None
    standard_count = 0
    if language in ("python", "csharp"):
        standard_counter = _count_python_imports if language == "python" else _count_csharp_imports
        import_count, standard_count = standard_counter("\n".join(code_lines))
        confidence = 0.6
        tuned = True
    elif language in _PARSED_COUPLING_LANGUAGES:
        counters: dict[str, Callable[[str], int]] = {
            "javascript": _count_javascript_imports,
            "typescript": partial(_count_typescript_imports, suffix=suffix),
            "powershell": _count_powershell_imports,
        }
        import_count = counters[language]("\n".join(code_lines))
        confidence = 0.6
        tuned = True
    elif pattern is not None:
        import_lines = [line for line in code_lines if pattern.search(line)]
        import_count = len(import_lines)
        if language == "go":
            module_path = go_module_resolver() if go_module_resolver else None
            for line in import_lines:
                match = _GO_IMPORT_PATH.search(line)
                if match and _is_go_standard_import(match.group(1), module_path):
                    standard_count += 1
        confidence = 0.6
        tuned = True
    else:
        import_count = sum(1 for line in code_lines if _GENERIC_IMPORT_PATTERN.search(line))
        confidence = 0.0
        tuned = False
    scored_count = import_count - standard_count
    score = max(1.0, min(10.0, 10.0 - scored_count))
    detail = (
        "Import count is reasonable"
        if score >= _COUPLING_REASONABLE_MIN
        else "High import count suggests high coupling"
    )
    if not tuned:
        detail = "Generic import approximation (untuned language); not gated"
    reasons = [f"{import_count} import/dependency statements"]
    if language == "go":
        reasons.append(
            f"{standard_count} Go standard library (not scored), "
            f"{scored_count} application or third-party (scored)"
        )
    elif language == "python" and standard_count:
        reasons.append(
            f"{standard_count} Python standard library (not scored), "
            f"{scored_count} application or third-party (scored)"
        )
    elif language == "csharp" and standard_count:
        reasons.append(
            f"{standard_count} C# System namespace (not scored), "
            f"{scored_count} application or third-party (scored)"
        )
    reasons.append(detail)
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


def _is_syntax_only_line(line: str) -> bool:
    """Return True when a stripped line repeats by syntax, not by copy-paste."""
    return bool(_STRUCTURAL_ONLY_LINE.fullmatch(line) or _BARE_ATTRIBUTE_LINE.fullmatch(line))


def _code_lines(content: str, language: str | None) -> list[str]:
    """Return non-blank lines, minus line comments for a tuned language."""
    prefixes = _LINE_COMMENT_PREFIXES.get(language, ()) if language else ()
    return [
        line
        for line in content.split("\n")
        if line.strip() and not (prefixes and line.strip().startswith(prefixes))
    ]


def _compared_lines(code_lines: list[str]) -> list[str]:
    """Return the stripped lines non-redundancy compares, syntax-only lines dropped."""
    stripped = [line.strip() for line in code_lines if line.strip()]
    return [line for line in stripped if not _is_syntax_only_line(line)]


def _duplicate_lines(code_lines: list[str]) -> Counter[str]:
    """Return each compared line's count of copies beyond its first."""
    counts = Counter(_compared_lines(code_lines))
    return Counter({line: count - 1 for line, count in counts.items() if count > 1})


def _score_non_redundancy(code_lines: list[str], scored: bool) -> QualityScore:
    """Approximate non-redundancy from the ratio of unique to compared lines.

    *code_lines* are non-blank and, for a tuned language, free of line
    comments. Syntax-only lines are dropped too, so a brace or a `[Fact]`
    that every member repeats does not read as duplication.
    """
    confidence = 0.5 if scored else 0.0
    stripped = [line.strip() for line in code_lines if line.strip()]
    compared = _compared_lines(code_lines)
    if not compared:
        return QualityScore(
            value=10.0, confidence=confidence, reasons=["No lines left to compare, no duplication"]
        )
    skipped = f"{len(stripped) - len(compared)} syntax-only lines skipped"
    if scored:
        skipped = f"line comments and {skipped}"
    unique_lines = len(set(compared))
    score = (unique_lines / len(compared)) * 10.0
    reasons = [
        f"{unique_lines}/{len(compared)} unique lines ({skipped})",
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
    ``scoring_failed`` is set so a consumer can tell this failure from a file
    whose language the scanner does not support.
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
        scoring_failed=True,
    )


def assess_content(
    file_path: Path,
    content: str,
    go_module_resolver: Callable[[], str | None] | None = None,
) -> FileAssessment:
    """Score already-loaded *content* attributed to *file_path*.

    Split out of ``assess_file`` so the same scoring runs over a base revision
    fetched with ``git show``, which never touches the working tree. Keeping
    one scoring body is what makes a base-to-head delta meaningful: two bodies
    would drift and the delta would measure the drift instead of the code.

    *go_module_resolver* supplies the enclosing Go module path. It defaults to
    the working-tree go.mod; base scoring passes one that reads the revision.
    """
    resolve_go_module = go_module_resolver or (lambda: _go_module_path(file_path))

    language = detect_language(file_path)

    category = classify_file_category(file_path, content)
    if category == "generated":
        return _unscored_generated_assessment(file_path)

    lines = content.split("\n")
    code_lines = _code_lines(content, language)
    loc = len(code_lines)

    return FileAssessment(
        file_path=str(file_path),
        category=category,
        cohesion=(
            _unscored_test_cohesion()
            if category == "test"
            else _score_cohesion(language, code_lines, loc)
        ),
        coupling=_score_coupling(
            language,
            lines if language in _PARSED_COUPLING_LANGUAGES else code_lines,
            resolve_go_module,
            file_path.suffix.lower(),
        ),
        encapsulation=_score_encapsulation(language, code_lines),
        testability=_score_testability(language, code_lines),
        non_redundancy=_score_non_redundancy(code_lines, language is not None),
    )


def assess_file_content(
    file_path: Path,
    content: str,
    context: str | None,
) -> FileAssessment:
    """Preserve the earlier content-assessment helper."""
    del context
    return assess_content(file_path, content)


def assess_file(file_path: Path, context: str | None, use_serena: bool) -> FileAssessment:
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


def _confidence_floor(config: dict[str, Any]) -> float:
    """Return the confidence below which a score is advisory, never gating.

    ``minConfidence`` is a top-level config key. A config without it gates every
    scored quality, as before. A score under the floor is still reported but
    cannot fail the absolute gate, because the metric says it is a weak proxy.
    """
    return float(config.get("minConfidence", 0.0))


def _is_advisory(score: QualityScore, floor: float) -> bool:
    return 0.0 < score.confidence < floor


def generate_markdown_report(
    assessments: list[FileAssessment],
    config: dict[str, Any],
    context: str | None = None,
) -> str:
    """Generate markdown report.

    Issues are listed against each file's own thresholds, the same ones
    ``check_thresholds`` gates on, so a file that passes the gate is not
    reported with issues.
    """
    report = ["# Code Quality Assessment Report\n"]

    # Summary statistics
    if not assessments:
        return "No files assessed."

    avg_cohesion = _average_scored([a.cohesion for a in assessments])
    avg_coupling = _average_scored([a.coupling for a in assessments])
    avg_encap = _average_scored([a.encapsulation for a in assessments])
    avg_test = _average_scored([a.testability for a in assessments])
    avg_nonred = _average_scored([a.non_redundancy for a in assessments])

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
        file_thresholds = _thresholds_for(config, context, assessment)
        floor = _confidence_floor(config)
        for label, threshold_key, score in quality_rows:
            if _score_below_threshold(score, _threshold_min(file_thresholds, threshold_key)):
                advisory = (
                    " (advisory for absolute thresholds, low confidence)"
                    if _is_advisory(score, floor)
                    else ""
                )
                report.append(f"**{label} Issues{advisory}**:")
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
                f"Renamed from `{comparison.base_file_path}` ({comparison.change_status}).\n"
            )
        if comparison.absolute_gate_reason == "base_unscored":
            lines.append("Base file had no scored qualities; head is gated absolutely.\n")
        lines.append("| Quality | Base | Head | Delta | Status |")
        lines.append("| --- | --- | --- | --- | --- |")
        for delta in comparison.deltas:
            base = "n/a" if delta.base is None else f"{delta.base:.1f}"
            head = "n/a" if delta.head is None else f"{delta.head:.1f}"
            change = "n/a" if delta.delta is None else f"{delta.delta:+.1f}"
            lines.append(f"| {delta.quality} | {base} | {head} | {change} | {delta.status} |")
        lines.append("")
    return "\n".join(lines)


def generate_json_report(
    assessments: list[FileAssessment],
    comparisons: list[FileComparison] | None = None,
    gate_mode: str = "absolute",
    threshold_gates: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Generate JSON report.

    Each file carries ``threshold_gate``: its absolute threshold verdict, or
    null when the absolute gate did not examine it (a regression-mode file
    with a comparable base).
    """
    gates = threshold_gates or {}
    return json.dumps(
        {
            "files": [{**asdict(a), "threshold_gate": gates.get(a.file_path)} for a in assessments],
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


_CATEGORY_CONTEXT = {"authored": "production", "test": "test", "generated": "generated"}


def _thresholds_for(
    config: dict[str, Any],
    context: str | None,
    assessment: FileAssessment,
) -> dict[str, Any]:
    """Merge the config thresholds with the context that applies to one file."""
    if context is None:
        context = _CATEGORY_CONTEXT.get(assessment.category, "production")
    thresholds = config["thresholds"]
    return {**thresholds, **config.get("context", {}).get(context, {})}


def check_thresholds(
    assessments: list[FileAssessment],
    config: dict[str, Any],
    context: str | None,
    *,
    fail_unscored_supported: bool = False,
) -> int:
    """
    Check if quality scores meet configured thresholds.

    ``context`` is an explicit override applied to every file. When it is
    None, each file uses the context named by its own category.

    Every file and every quality is checked before the verdict, so one run
    reports every failure (issue #7481).

    Returns:
        0: All thresholds met
        11: Below thresholds
    """
    floor = _confidence_floor(config)
    failed = False
    for assessment in assessments:
        gate = evaluate_threshold_gate(
            assessment,
            config,
            context,
            fail_unscored_supported=fail_unscored_supported,
        )
        if gate["unscored_supported_source"]:
            print(
                f"❌ {assessment.file_path}: supported authored source could not be scored",
                file=sys.stderr,
            )
        for miss in gate["below_threshold"]:
            label = _QUALITY_LABELS[miss["quality"]]
            message = f"{assessment.file_path}: {label} {miss['score']} < {miss['minimum']}"
            if miss["advisory"]:
                print(
                    f"⚠️ {message} (advisory: confidence {miss['confidence']} "
                    f"< minConfidence {floor})",
                    file=sys.stderr,
                )
                continue
            print(f"❌ {message}", file=sys.stderr)
        failed = failed or gate["failed"]

    return 11 if failed else 0


# Gate order, JSON key (the FileAssessment field name), config key, and the
# label the stderr lines print. Coupling uses "min" semantics: higher score =
# looser coupling = better. Legacy configs that only specify "max" are skipped
# rather than gated incorrectly.
_GATED_QUALITIES = (
    ("cohesion", "cohesion", "Cohesion"),
    ("coupling", "coupling", "Coupling"),
    ("encapsulation", "encapsulation", "Encapsulation"),
    ("testability", "testability", "Testability"),
    ("non_redundancy", "nonRedundancy", "Non-Redundancy"),
)
_QUALITY_LABELS = {field: label for field, _, label in _GATED_QUALITIES}


def evaluate_threshold_gate(
    assessment: FileAssessment,
    config: dict[str, Any],
    context: str | None,
    *,
    fail_unscored_supported: bool = False,
) -> dict[str, Any]:
    """Return the absolute threshold verdict for one file.

    This is the single source for both the stderr lines ``check_thresholds``
    prints and the ``threshold_gate`` object the JSON report carries, so a
    caller reading the JSON gets the same verdict the exit code reflects.
    ``failed`` is true when the file is unscored supported source, or when any
    ``below_threshold`` entry is not advisory.
    """
    if (
        fail_unscored_supported
        and assessment.category != "generated"
        and detect_language(Path(assessment.file_path)) is not None
        and not _has_scored_quality(assessment)
    ):
        return {"failed": True, "unscored_supported_source": True, "below_threshold": []}

    thresholds = _thresholds_for(config, context, assessment)
    floor = _confidence_floor(config)
    misses: list[dict[str, Any]] = []
    for field_name, config_key, _ in _GATED_QUALITIES:
        score: QualityScore = getattr(assessment, field_name)
        minimum = thresholds[config_key].get("min")
        if not _score_below_threshold(score, minimum):
            continue
        misses.append(
            {
                "quality": field_name,
                "score": score.value,
                "minimum": minimum,
                "confidence": score.confidence,
                "advisory": _is_advisory(score, floor),
            }
        )
    return {
        "failed": any(not miss["advisory"] for miss in misses),
        "unscored_supported_source": False,
        "below_threshold": misses,
    }


def _resolve_target_path(target: str) -> str:
    """Return an absolute target path inside the current working directory."""
    return str(_resolve_in_workspace(Path(target), "--target"))


def _assess_files(
    files: list[Path],
    context: str | None,
    use_serena: bool,
) -> list[FileAssessment]:
    """Assess every readable file and report per-file failures.

    A file that raises is recorded as an all-unscored assessment rather than
    dropped. Dropping it made the failure invisible downstream: `summary`
    reports `file_count` as the length of this list, so a run that lost four of
    five files still looked internally consistent, and a consumer could read
    the survivor as evidence the whole change was assessed. This is the same
    treatment an unreadable file already gets at the decode site.

    A C#, TypeScript, JavaScript, Python, or PowerShell parser failure is the
    exception: it is deliberately fatal (exit 1), so no parsed-language score is guessed.
    """
    assessments: list[FileAssessment] = []
    for file_path in files:
        try:
            assessments.append(assess_file(file_path, context, use_serena))
        except ParserError as exc:
            raise type(exc)(f"{file_path}: {exc}") from exc
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


def _absolute_gate_inputs(
    gate_mode: str,
    assessments: list[FileAssessment],
    new_file_assessments: list[FileAssessment],
) -> tuple[list[FileAssessment], bool]:
    """Return the files the absolute threshold gate examines, and whether an
    unscored supported file fails it. Regression mode gates only files with
    no comparable base; absolute mode gates every file."""
    if gate_mode == "regression":
        return new_file_assessments, True
    return assessments, False


def _render_report(
    output_format: str,
    assessments: list[FileAssessment],
    comparisons: list[FileComparison],
    config: dict[str, Any],
    gate_mode: str,
    context: str | None = None,
    new_file_assessments: list[FileAssessment] | None = None,
) -> str:
    """Render the selected report format."""
    if output_format == "markdown":
        report = generate_markdown_report(assessments, config, context)
        section = generate_regression_section(comparisons)
        return f"{report}\n\n{section}" if section else report
    if output_format == "json":
        gated, fail_unscored = _absolute_gate_inputs(
            gate_mode, assessments, new_file_assessments or []
        )
        gates = {
            a.file_path: evaluate_threshold_gate(
                a, config, context, fail_unscored_supported=fail_unscored
            )
            for a in gated
        }
        return generate_json_report(assessments, comparisons, gate_mode, gates)
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
    context: str | None,
) -> int:
    """Apply the gate policy selected for this run."""
    if gate_mode == "regression":
        return check_regression(comparisons, new_file_assessments, config, context)
    gated, fail_unscored = _absolute_gate_inputs(gate_mode, assessments, new_file_assessments)
    return check_thresholds(gated, config, context, fail_unscored_supported=fail_unscored)


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
        if args.changed_only and not resolved_target.is_file() and not resolved_target.is_dir():
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
                print(
                    f"ERROR: --target does not match HEAD or base: {args.target}", file=sys.stderr
                )
                return 1
            report = _render_report(args.format, [], [], config, gate_mode)
            _write_report(report, args.output)
            return 0
        print("No files to assess", file=sys.stderr)
        return 1

    try:
        assessments = _assess_files(files, args.context, args.use_serena == "yes")
        comparisons, new_file_assessments = _build_regression_inputs(
            assessments,
            gate_mode,
            comparison_base,
            args.regression_tolerance,
            changed_files,
        )
        _apply_parser_dependency_admissions(comparisons, config)
        _apply_change_admissions(comparisons, config, comparison_base)
        _apply_rule_admissions(comparisons, config, comparison_base)
    except (RuntimeError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    report = _render_report(
        args.format,
        assessments,
        comparisons,
        config,
        gate_mode,
        args.context,
        new_file_assessments,
    )
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
