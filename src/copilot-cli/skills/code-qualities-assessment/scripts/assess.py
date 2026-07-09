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
# listed; anything else is analyzed with generic fallbacks and reduced
# confidence so the gate never fails a file it cannot actually score.
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

# Per-language import / dependency line patterns for the coupling heuristic.
_IMPORT_PATTERNS = {
    "python": re.compile(r"^\s*(?:import\s+\S|from\s+\S+\s+import\s+)"),
    "javascript": re.compile(r"^\s*import\s+|\brequire\s*\("),
    "typescript": re.compile(r"^\s*import\s+|\brequire\s*\("),
    "csharp": re.compile(r"^\s*using\s+[A-Za-z_]"),
    "java": re.compile(r"^\s*import\s+[A-Za-z_]"),
    "go": re.compile(r'^\s*import\s+"|^\s+_?\s*"[^"]+"\s*$'),
}

# Generic import fallback for languages without a tuned pattern.
_GENERIC_IMPORT_PATTERN = re.compile(r"^\s*(?:import|from|using|require|#include)\b")

# Per-language definition patterns (types, functions, methods) for the cohesion
# heuristic. More top-level definitions plus larger size means lower cohesion.
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
        re.compile(r"^var\s+\w"),
    )
    return sum(1 for line in lines if any(p.search(line) for p in patterns))


def _count_go_global_state(lines: list[str]) -> int:
    # Package-level (unindented) var declarations are mutable global state.
    return sum(1 for line in lines if re.match(r"^var\s+\w", line))


def _immutable_static(stripped: str, immutable_keywords: tuple[str, ...]) -> bool:
    type_decls = ("class ", "struct ", "interface ", "enum ", "record ")
    return any(kw in stripped for kw in immutable_keywords + type_decls)


def _count_csharp_static_state(lines: list[str]) -> int:
    count = 0
    for line in lines:
        stripped = line.strip()
        if "static" not in stripped or "(" in stripped:
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
    return sum(
        1 for line in lines for m in pattern.finditer(line) if not m.group(1).startswith("_")
    )


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
        if "(" in stripped or "{" in stripped:  # method, ctor, property, or type body
            continue
        if any(
            kw in stripped
            for kw in ("class ", "interface ", "struct ", "enum ", "record ")
        ):
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
    """Assessment results for a single file"""
    file_path: str
    cohesion: QualityScore
    coupling: QualityScore
    encapsulation: QualityScore
    testability: QualityScore
    non_redundancy: QualityScore

    @property
    def overall(self) -> float:
        """Weighted average of all qualities"""
        return (
            self.cohesion.value +
            self.coupling.value +
            self.encapsulation.value +
            self.testability.value +
            self.non_redundancy.value
        ) / 5


def parse_args() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Assess code quality across 5 foundational qualities"
    )
    parser.add_argument(
        "--target",
        required=True,
        help="File, directory, or glob pattern to assess"
    )
    parser.add_argument(
        "--context",
        choices=["production", "test", "generated"],
        default="production",
        help="Code context (affects thresholds)"
    )
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Only assess changed files (git diff)"
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "html"],
        default="markdown",
        help="Output format"
    )
    parser.add_argument(
        "--config",
        default=".qualityrc.json",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "--use-serena",
        choices=["auto", "yes", "no"],
        default="auto",
        help="Use Serena for symbol extraction"
    )
    return parser.parse_args()


def load_config(config_path: str) -> dict[str, Any]:
    """Load configuration or return defaults"""
    try:
        with open(config_path) as f:
            config: dict[str, Any] = json.load(f)
            return config
    except FileNotFoundError:
        # Default configuration
        return {
            "thresholds": {
                "cohesion": {"min": 7, "warn": 5},
                "coupling": {"min": 7, "warn": 5},
                "encapsulation": {"min": 7, "warn": 5},
                "testability": {"min": 6, "warn": 4},
                "nonRedundancy": {"min": 8, "warn": 6}
            },
            "context": {
                "test": {"testability": {"min": 3}}
            },
            "ignore": ["**/generated/**", "**/*.pb.py"]
        }


def get_files_to_assess(target: str, changed_only: bool) -> list[Path]:
    """Get list of files to assess"""
    import subprocess
    from glob import glob

    if changed_only:
        # Get changed files from git
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        files = [Path(f) for f in result.stdout.strip().split('\n') if f]
    else:
        target_path = Path(target)
        if target_path.is_file():
            files = [target_path]
        elif target_path.is_dir():
            files = [
                f
                for suffix in _LANGUAGE_BY_SUFFIX
                for f in target_path.rglob(f"*{suffix}")
            ]
        else:
            # Glob pattern
            files = [Path(f) for f in glob(target, recursive=True)]

    return [f for f in files if f.exists()]


def _score_cohesion(language: str | None, code_lines: list[str], loc: int) -> QualityScore:
    """Approximate cohesion from size plus top-level definition count.

    This is a size+definition approximation, not a true LCOM cohesion metric.
    More definitions packed into a larger file suggests the file is doing many
    things (lower cohesion). Confidence is deliberately low.
    """
    pattern = _DEFINITION_PATTERNS.get(language) if language else None
    def_count = (
        sum(1 for line in code_lines if pattern.search(line)) if pattern else 0
    )
    score = 10.0 - (loc / 120.0) - max(0, def_count - 1) * 0.3
    score = max(1.0, min(10.0, score))
    confidence = 0.4 if pattern else 0.3
    reasons = [
        f"{loc} LOC, {def_count} top-level definitions "
        "(size+definition approximation, not LCOM)",
        (
            "Large file with many definitions suggests low cohesion"
            if score < 7
            else "Size and definition count are reasonable"
        ),
    ]
    return QualityScore(value=round(score, 1), confidence=confidence, reasons=reasons)


def _score_coupling(language: str | None, code_lines: list[str]) -> QualityScore:
    """Approximate coupling from the number of import/dependency statements.

    A high score means loose coupling (few imports), which is good, matching
    the rubric where 10 is best.
    """
    pattern = _IMPORT_PATTERNS.get(language) if language else None
    if pattern is not None:
        import_count = sum(1 for line in code_lines if pattern.search(line))
        confidence = 0.6
    else:
        import_count = sum(
            1 for line in code_lines if _GENERIC_IMPORT_PATTERN.search(line)
        )
        confidence = 0.3
    score = max(1.0, min(10.0, 10.0 - import_count))
    reasons = [
        f"{import_count} import/dependency statements",
        (
            "High import count suggests high coupling"
            if import_count > 10
            else "Import count is reasonable"
        ),
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
            reasons=[
                "Encapsulation not scored for this language "
                "(no reliable visibility signal)"
            ],
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
    """Approximate testability from the amount of mutable global/static state.

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
        f"{global_count} mutable global/static references",
        (
            "Global state hinders testability"
            if global_count > 0
            else "No global state detected"
        ),
    ]
    return QualityScore(value=round(score, 1), confidence=0.5, reasons=reasons)


def _score_non_redundancy(lines: list[str]) -> QualityScore:
    """Approximate non-redundancy from the ratio of unique to total lines.

    This is language-agnostic and unchanged in spirit from the original
    heuristic.
    """
    non_blank = [line.strip() for line in lines if line.strip()]
    if not non_blank:
        return QualityScore(
            value=10.0, confidence=0.5, reasons=["Empty file, no duplication"]
        )
    unique_lines = len(set(non_blank))
    score = (unique_lines / len(non_blank)) * 10.0
    reasons = [
        f"{unique_lines}/{len(non_blank)} unique non-blank lines",
        "High duplication detected" if score < 7 else "Low duplication",
    ]
    return QualityScore(value=round(score, 1), confidence=0.5, reasons=reasons)


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
        with open(file_path, encoding='utf-8') as f:
            content = f.read()
    except Exception:
        content = ""

    lines = content.split('\n')
    code_lines = [
        line
        for line in lines
        if line.strip()
        and not (comment_prefixes and line.strip().startswith(comment_prefixes))
    ]
    loc = len(code_lines)

    return FileAssessment(
        file_path=str(file_path),
        cohesion=_score_cohesion(language, code_lines, loc),
        coupling=_score_coupling(language, code_lines),
        encapsulation=_score_encapsulation(language, code_lines),
        testability=_score_testability(language, code_lines),
        non_redundancy=_score_non_redundancy(lines),
    )


def generate_markdown_report(assessments: list[FileAssessment], config: dict[str, Any]) -> str:
    """Generate markdown report"""
    report = ["# Code Quality Assessment Report\n"]

    # Summary statistics
    if not assessments:
        return "No files assessed."

    avg_cohesion = sum(a.cohesion.value for a in assessments) / len(assessments)
    avg_coupling = sum(a.coupling.value for a in assessments) / len(assessments)
    avg_encap = sum(a.encapsulation.value for a in assessments) / len(assessments)
    avg_test = sum(a.testability.value for a in assessments) / len(assessments)
    avg_nonred = sum(a.non_redundancy.value for a in assessments) / len(assessments)

    report.append("## Summary\n")
    report.append(f"**Files Assessed**: {len(assessments)}\n")
    report.append(f"**Average Cohesion**: {avg_cohesion:.1f}/10")
    report.append(f"**Average Coupling**: {avg_coupling:.1f}/10")
    report.append(f"**Average Encapsulation**: {avg_encap:.1f}/10")
    report.append(f"**Average Testability**: {avg_test:.1f}/10")
    report.append(f"**Average Non-Redundancy**: {avg_nonred:.1f}/10\n")

    # Per-file breakdown
    report.append("## File Assessments\n")
    for assessment in sorted(assessments, key=lambda a: a.overall):
        report.append(f"### {assessment.file_path}\n")
        report.append(f"**Overall**: {assessment.overall:.1f}/10\n")
        report.append(f"- **Cohesion**: {assessment.cohesion.value}/10")
        report.append(f"- **Coupling**: {assessment.coupling.value}/10")
        report.append(f"- **Encapsulation**: {assessment.encapsulation.value}/10")
        report.append(f"- **Testability**: {assessment.testability.value}/10")
        report.append(f"- **Non-Redundancy**: {assessment.non_redundancy.value}/10\n")

        # Show reasons for low scores
        if assessment.cohesion.value < 7:
            report.append("**Cohesion Issues**:")
            for reason in assessment.cohesion.reasons:
                report.append(f"  - {reason}")
            report.append("")

        if assessment.coupling.value < 7:
            report.append("**Coupling Issues**:")
            for reason in assessment.coupling.reasons:
                report.append(f"  - {reason}")
            report.append("")

    return "\n".join(report)


def generate_json_report(assessments: list[FileAssessment]) -> str:
    """Generate JSON report"""
    count = len(assessments) if assessments else 1
    return json.dumps({
        "files": [asdict(a) for a in assessments],
        "summary": {
            "file_count": len(assessments),
            "average_scores": {
                "cohesion": (
                    sum(a.cohesion.value for a in assessments) / count if assessments else 0
                ),
                "coupling": (
                    sum(a.coupling.value for a in assessments) / count if assessments else 0
                ),
                "encapsulation": (
                    sum(a.encapsulation.value for a in assessments) / count if assessments else 0
                ),
                "testability": (
                    sum(a.testability.value for a in assessments) / count if assessments else 0
                ),
                "non_redundancy": (
                    sum(a.non_redundancy.value for a in assessments) / count if assessments else 0
                ),
            }
        }
    }, indent=2)


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
                file=sys.stderr
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
                f"❌ {assessment.file_path}: Coupling {assessment.coupling.value} "
                f"< {coupling_min}",
                file=sys.stderr
            )
            return 11

        if (
            assessment.encapsulation.confidence > 0.0
            and assessment.encapsulation.value < thresholds["encapsulation"]["min"]
        ):
            print(
                f"❌ {assessment.file_path}: Encapsulation {assessment.encapsulation.value} "
                f"< {thresholds['encapsulation']['min']}",
                file=sys.stderr
            )
            return 11

        if (
            assessment.testability.confidence > 0.0
            and assessment.testability.value < thresholds["testability"]["min"]
        ):
            print(
                f"❌ {assessment.file_path}: Testability {assessment.testability.value} "
                f"< {thresholds['testability']['min']}",
                file=sys.stderr
            )
            return 11

        if (
            assessment.non_redundancy.confidence > 0.0
            and assessment.non_redundancy.value < thresholds["nonRedundancy"]["min"]
        ):
            print(
                f"❌ {assessment.file_path}: Non-Redundancy {assessment.non_redundancy.value} "
                f"< {thresholds['nonRedundancy']['min']}",
                file=sys.stderr
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
            raise ValueError(
                f"Path traversal attempt detected in --target: {args.target}"
            )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Get files to assess
    try:
        files = get_files_to_assess(target_path, args.changed_only)
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
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"Report written to {args.output}")
    else:
        print(report)

    # Check thresholds
    exit_code = check_thresholds(assessments, config, args.context)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
