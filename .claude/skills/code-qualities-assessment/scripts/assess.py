#!/usr/bin/env python3
"""
Code Qualities Assessment - Main Orchestrator

Assesses code maintainability using 5 foundational qualities:
- Cohesion
- Coupling
- Encapsulation
- Testability
- Non-Redundancy

Exit codes:
  0: Assessment complete, all thresholds met
  10: Quality degraded vs previous run
  11: Quality below configured thresholds
  1: Script error
"""

import argparse
import json
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


def classify_file_category(file_path: Path, content: str | None = None) -> str:
    """Classify a changed file as authored, test, or generated.

    Generated outputs are reviewed through their generator and drift checks,
    not as independent authored modules.
    """
    parts = file_path.parts
    if any(
        any(parts[i : i + len(segment)] == segment for i in range(len(parts)))
        for segment in _GENERATED_PATH_SEGMENTS
    ):
        return "generated"
    if file_path.name.startswith("pr-quality-gate-") and ".github" in parts:
        return "generated"
    if content is None:
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
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


def parse_args() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Assess code quality across 5 foundational qualities"
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
    return parser.parse_args()


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


def get_files_to_assess(target: str, changed_only: bool, base: str | None = None) -> list[Path]:
    """Get files to assess, using the PR base when one is supplied."""
    import subprocess
    from glob import glob

    if changed_only:
        revision_range = f"{base}...HEAD" if base else "HEAD"
        result = subprocess.run(
            ["git", "diff", "--name-only", revision_range],
            capture_output=True,
            text=True,
            check=True,
        )
        files = [Path(f) for f in result.stdout.splitlines() if f]
    else:
        target_path = Path(target)
        if target_path.is_file():
            files = [target_path]
        elif target_path.is_dir():
            files = [f for suffix in _LANGUAGE_BY_SUFFIX for f in target_path.rglob(f"*{suffix}")]
        else:
            # Glob pattern
            files = [Path(f) for f in glob(target, recursive=True)]

    return [f for f in files if f.exists()]


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
    language = detect_language(file_path)
    comment_prefixes = _LINE_COMMENT_PREFIXES.get(language, ()) if language else ()

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        return _unreadable_assessment(file_path, f"read failed: {exc}")
    except UnicodeDecodeError as exc:
        return _unreadable_assessment(file_path, f"decode failed: {exc}")

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


def generate_json_report(assessments: list[FileAssessment]) -> str:
    """Generate JSON report"""
    return json.dumps(
        {
            "files": [asdict(a) for a in assessments],
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
    assessments: list[FileAssessment], config: dict[str, Any], context: str
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


def main() -> int:
    """Main entry point"""
    args = parse_args()

    # Load configuration
    config = load_config(args.config)

    # Validate target path to prevent path traversal (CWE-22)
    import os

    try:
        allowed_base = os.path.abspath(".")
        target_path = os.path.abspath(args.target)
        if not target_path.startswith(allowed_base):
            raise ValueError(f"Path traversal attempt detected in --target: {args.target}")
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Get files to assess
    try:
        files = get_files_to_assess(target_path, args.changed_only, args.base)
    except Exception as e:
        print(f"Error getting files: {e}", file=sys.stderr)
        return 1

    if not files:
        print("No files to assess", file=sys.stderr)
        return 1

    # Determine Serena availability
    use_serena = args.use_serena == "yes"
    if args.use_serena == "auto":
        # Try to detect Serena (simplified - real version would check MCP)
        use_serena = False

    # Assess each file
    assessments = []
    for file_path in files:
        try:
            assessment = assess_file(file_path, args.context, use_serena)
            assessments.append(assessment)
        except Exception as e:
            print(f"Error assessing {file_path}: {e}", file=sys.stderr)
            continue

    # Generate report
    if args.format == "markdown":
        report = generate_markdown_report(assessments, config)
    elif args.format == "json":
        report = generate_json_report(assessments)
    else:  # HTML
        report = "HTML format not yet implemented"

    # Output report
    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to {args.output}")
    else:
        print(report)

    # Check thresholds
    exit_code = check_thresholds(assessments, config, args.context)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
