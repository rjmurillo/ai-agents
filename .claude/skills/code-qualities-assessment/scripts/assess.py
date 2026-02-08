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
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class QualityScore:
    """Individual quality score with confidence"""
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


def load_config(config_path: str) -> dict:
    """Load configuration or return defaults"""
    try:
        with open(config_path) as f:
            return json.load(f)
    except FileNotFoundError:
        # Default configuration
        return {
            "thresholds": {
                "cohesion": {"min": 7, "warn": 5},
                "coupling": {"max": 3, "warn": 5},
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
            files = list(target_path.rglob("*.py")) + \
                    list(target_path.rglob("*.ts")) + \
                    list(target_path.rglob("*.js")) + \
                    list(target_path.rglob("*.cs")) + \
                    list(target_path.rglob("*.java"))
        else:
            # Glob pattern
            files = [Path(f) for f in glob(target, recursive=True)]

    return [f for f in files if f.exists()]


def assess_file(file_path: Path, context: str, use_serena: bool) -> FileAssessment:
    """
    Assess a single file for all 5 qualities.

    This is a simplified implementation. In production, this would:
    1. Parse the file to extract symbols (using Serena if available)
    2. Calculate metrics for each quality
    3. Apply scoring rubrics
    4. Return FileAssessment with scores and rationale
    """
    # Placeholder implementation - real version would analyze actual code
    # For demonstration, return sample scores

    # Read file to get basic metrics
    try:
        with open(file_path, encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
            loc = len([l for l in lines if l.strip() and not l.strip().startswith('#')])
    except Exception:
        loc = 0

    # Heuristic scoring based on file size (simplified)
    # Real implementation would use proper static analysis

    # Cohesion: penalize large files (likely low cohesion)
    cohesion_score = max(1, min(10, 10 - (loc / 100)))

    # Coupling: heuristic based on imports (simplified)
    import_count = len([l for l in lines if 'import ' in l])
    coupling_score = max(1, min(10, 10 - import_count))

    # Encapsulation: check for private vs public (simplified)
    public_methods = len([l for l in lines if 'def ' in l and 'def _' not in l])
    private_methods = len([l for l in lines if 'def _' in l])
    if public_methods + private_methods > 0:
        encap_score = (private_methods / (public_methods + private_methods)) * 10
    else:
        encap_score = 10

    # Testability: check for global state, hard-coded values
    global_vars = len([l for l in lines if l.strip().startswith('global ')])
    testability_score = max(1, 10 - global_vars * 2)

    # Non-redundancy: basic duplication check (simplified)
    # Real version would use token-based clone detection
    unique_lines = len(set([l.strip() for l in lines if l.strip()]))
    if len(lines) > 0:
        redundancy_score = (unique_lines / len(lines)) * 10
    else:
        redundancy_score = 10

    return FileAssessment(
        file_path=str(file_path),
        cohesion=QualityScore(
            value=round(cohesion_score, 1),
            confidence=0.7,
            reasons=[
                f"File has {loc} LOC",
                "Large files often indicate low cohesion" if loc > 200 else "File size is reasonable"
            ]
        ),
        coupling=QualityScore(
            value=round(coupling_score, 1),
            confidence=0.6,
            reasons=[
                f"File has {import_count} imports",
                "High import count suggests high coupling" if import_count > 10 else "Import count is reasonable"
            ]
        ),
        encapsulation=QualityScore(
            value=round(encap_score, 1),
            confidence=0.8,
            reasons=[
                f"{private_methods} private methods, {public_methods} public methods",
                "Good balance of private vs public" if encap_score > 7 else "Too many public methods"
            ]
        ),
        testability=QualityScore(
            value=round(testability_score, 1),
            confidence=0.7,
            reasons=[
                f"Found {global_vars} global variable references",
                "Global state hinders testability" if global_vars > 0 else "No global state detected"
            ]
        ),
        non_redundancy=QualityScore(
            value=round(redundancy_score, 1),
            confidence=0.5,
            reasons=[
                f"{unique_lines}/{len(lines)} unique lines",
                "High duplication detected" if redundancy_score < 7 else "Low duplication"
            ]
        )
    )


def generate_markdown_report(assessments: list[FileAssessment], config: dict) -> str:
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
    return json.dumps({
        "files": [asdict(a) for a in assessments],
        "summary": {
            "file_count": len(assessments),
            "average_scores": {
                "cohesion": sum(a.cohesion.value for a in assessments) / len(assessments) if assessments else 0,
                "coupling": sum(a.coupling.value for a in assessments) / len(assessments) if assessments else 0,
                "encapsulation": sum(a.encapsulation.value for a in assessments) / len(assessments) if assessments else 0,
                "testability": sum(a.testability.value for a in assessments) / len(assessments) if assessments else 0,
                "non_redundancy": sum(a.non_redundancy.value for a in assessments) / len(assessments) if assessments else 0,
            }
        }
    }, indent=2)


def check_thresholds(assessments: list[FileAssessment], config: dict, context: str) -> int:
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
        if assessment.cohesion.value < thresholds["cohesion"]["min"]:
            print(f"❌ {assessment.file_path}: Cohesion {assessment.cohesion.value} < {thresholds['cohesion']['min']}", file=sys.stderr)
            return 11

        if assessment.coupling.value > thresholds["coupling"]["max"]:
            print(f"❌ {assessment.file_path}: Coupling {assessment.coupling.value} > {thresholds['coupling']['max']}", file=sys.stderr)
            return 11

        if assessment.encapsulation.value < thresholds["encapsulation"]["min"]:
            print(f"❌ {assessment.file_path}: Encapsulation {assessment.encapsulation.value} < {thresholds['encapsulation']['min']}", file=sys.stderr)
            return 11

        if assessment.testability.value < thresholds["testability"]["min"]:
            print(f"❌ {assessment.file_path}: Testability {assessment.testability.value} < {thresholds['testability']['min']}", file=sys.stderr)
            return 11

        if assessment.non_redundancy.value < thresholds["nonRedundancy"]["min"]:
            print(f"❌ {assessment.file_path}: Non-Redundancy {assessment.non_redundancy.value} < {thresholds['nonRedundancy']['min']}", file=sys.stderr)
            return 11

    return 0


def main() -> int:
    """Main entry point"""
    args = parse_args()

    # Load configuration
    config = load_config(args.config)

    # Get files to assess
    try:
        files = get_files_to_assess(args.target, args.changed_only)
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
