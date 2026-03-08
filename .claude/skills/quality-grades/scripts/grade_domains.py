#!/usr/bin/env python3
"""
Quality Grades - Domain grading with gap tracking.

Scans the repository for product domains and architectural layers,
computes quality grades (A-F), and tracks gaps over time.

Exit codes:
  0: Grading complete, report generated
  1: Script error
  2: Configuration error (invalid domain config)
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

GRADE_THRESHOLDS = {
    "A": 90,
    "B": 75,
    "C": 60,
    "D": 40,
    "F": 0,
}

LAYERS = ["agents", "skills", "scripts", "tests", "docs", "workflows"]


@dataclass
class Gap:
    """A tracked quality gap within a domain layer."""

    layer: str
    description: str
    severity: str  # critical, significant, minor


@dataclass
class LayerGrade:
    """Grade for a single architectural layer within a domain."""

    layer: str
    grade: str
    score: int
    gaps: list[Gap] = field(default_factory=list)
    file_count: int = 0


@dataclass
class DomainGrade:
    """Aggregate grade for a product domain."""

    domain: str
    layers: list[LayerGrade] = field(default_factory=list)

    @property
    def overall_grade(self) -> str:
        """Compute the aggregate letter grade across all layers."""
        if not self.layers:
            return "F"
        avg = sum(lg.score for lg in self.layers) / len(self.layers)
        return score_to_grade(avg)

    @property
    def overall_score(self) -> float:
        """Compute the average numeric score across all layers."""
        if not self.layers:
            return 0
        return sum(lg.score for lg in self.layers) / len(self.layers)


def score_to_grade(score: float) -> str:
    """Convert numeric score (0-100) to letter grade."""
    for grade, threshold in GRADE_THRESHOLDS.items():
        if score >= threshold:
            return grade
    return "F"


def detect_domains(repo_root: Path) -> list[str]:
    """Auto-detect product domains from repo structure."""
    domains: set[str] = set()

    # Detect from agent files
    agents_dir = repo_root / ".claude" / "agents"
    if agents_dir.is_dir():
        for f in agents_dir.glob("*.md"):
            if f.name not in ("AGENTS.md", "CLAUDE.md", "README.md"):
                domains.add(f.stem)

    # Detect from skill directories
    skills_dir = repo_root / ".claude" / "skills"
    if skills_dir.is_dir():
        for d in skills_dir.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                domains.add(d.name)

    return sorted(domains)


def _grade_agents_layer(
    repo_root: Path, domain: str,
) -> tuple[int, int, list[Gap]]:
    """Grade the agents layer for a domain.

    Returns:
        Tuple of (score, file_count, gaps).
    """
    gaps: list[Gap] = []
    agent_file = repo_root / ".claude" / "agents" / f"{domain}.md"
    if not agent_file.exists():
        gaps.append(
            Gap(
                layer="agents",
                description=f"No agent definition found for domain '{domain}'",
                severity="significant",
            )
        )
        return 0, 0, gaps

    content = agent_file.read_text(encoding="utf-8")
    score = 60  # Base score for existence
    if "## Core" in content or "## Core Identity" in content:
        score += 10
    if "## Style Guide" in content or "## Style" in content:
        score += 10
    if "## Tools" in content or "## Claude Code Tools" in content:
        score += 10
    if "## Activation" in content:
        score += 10
    if score < 90:
        gaps.append(
            Gap(
                layer="agents",
                description=f"Agent definition missing sections (score: {score}/100)",
                severity="minor",
            )
        )
    return score, 1, gaps


def _grade_skills_layer(
    repo_root: Path, domain: str,
) -> tuple[int, int, list[Gap]]:
    """Grade the skills layer for a domain.

    Returns:
        Tuple of (score, file_count, gaps).
    """
    gaps: list[Gap] = []
    skill_dir = repo_root / ".claude" / "skills" / domain
    if not skill_dir.is_dir():
        gaps.append(
            Gap(
                layer="skills",
                description=f"No skill directory for domain '{domain}'",
                severity="minor",
            )
        )
        return 50, 0, gaps

    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        gaps.append(
            Gap(
                layer="skills",
                description="Skill directory exists but SKILL.md missing",
                severity="critical",
            )
        )
        return 20, 0, gaps

    content = skill_file.read_text(encoding="utf-8")
    score = 60
    if content.startswith("---"):
        score += 15  # Has frontmatter
    if "## Triggers" in content or "## When to Use" in content:
        score += 10
    if "## Verification" in content:
        score += 10
    if score < 90:
        gaps.append(
            Gap(
                layer="skills",
                description=f"Skill definition incomplete (score: {score}/100)",
                severity="minor",
            )
        )
    return score, 1, gaps


def _grade_scripts_layer(
    repo_root: Path, domain: str,
) -> tuple[int, int, list[Gap]]:
    """Grade the scripts layer for a domain.

    Returns:
        Tuple of (score, file_count, gaps).
    """
    gaps: list[Gap] = []
    skill_scripts = repo_root / ".claude" / "skills" / domain / "scripts"
    repo_scripts = repo_root / "scripts"
    found_scripts: list[Path] = []
    if skill_scripts.is_dir():
        found_scripts.extend(skill_scripts.glob("*.py"))
    if repo_scripts.is_dir():
        found_scripts.extend(f for f in repo_scripts.glob("*.py") if domain in f.stem)
    file_count = len(found_scripts)
    if file_count == 0:
        gaps.append(
            Gap(layer="scripts", description="No automation scripts found", severity="minor")
        )
        return 50, 0, gaps

    score = 70
    has_docs = sum(
        1
        for script in found_scripts
        if '"""' in script.read_text(encoding="utf-8")[:500]
        or "'''" in script.read_text(encoding="utf-8")[:500]
    )
    doc_ratio = has_docs / file_count
    score += int(doc_ratio * 30)
    if doc_ratio < 1.0:
        gaps.append(
            Gap(
                layer="scripts",
                description=f"{file_count - has_docs}/{file_count} scripts lack docstrings",
                severity="minor",
            )
        )
    return score, file_count, gaps


def _grade_tests_layer(
    repo_root: Path, domain: str,
) -> tuple[int, int, list[Gap]]:
    """Grade the tests layer for a domain.

    Returns:
        Tuple of (score, file_count, gaps).
    """
    gaps: list[Gap] = []
    test_dirs = [
        repo_root / ".claude" / "skills" / domain / "tests",
        repo_root / "tests",
    ]
    test_files: list[Path] = []
    for td in test_dirs:
        if td.is_dir():
            test_files.extend(
                f for f in td.rglob("*test*") if f.is_file() and f.suffix in (".py", ".ps1")
            )
            test_files.extend(
                f
                for f in td.rglob("*Test*")
                if f.is_file() and f.suffix in (".py", ".ps1") and f not in test_files
            )
    domain_tests = [
        f
        for f in test_files
        if domain.replace("-", "_") in f.stem.lower()
        or domain.replace("-", "") in f.stem.lower()
    ]
    file_count = len(domain_tests)
    if file_count > 0:
        score = 80 + min(file_count * 5, 20)
        return score, file_count, gaps

    gaps.append(
        Gap(
            layer="tests",
            description=f"No test files found for domain '{domain}'",
            severity="significant",
        )
    )
    return 30, 0, gaps


def _grade_docs_layer(
    repo_root: Path, domain: str,
) -> tuple[int, int, list[Gap]]:
    """Grade the docs layer for a domain.

    Returns:
        Tuple of (score, file_count, gaps).
    """
    gaps: list[Gap] = []
    doc_locations = [repo_root / "docs", repo_root / ".agents"]
    doc_files: list[Path] = []
    for dl in doc_locations:
        if dl.is_dir():
            doc_files.extend(
                f
                for f in dl.rglob("*.md")
                if domain in f.stem.lower() or domain.replace("-", "") in f.stem.lower()
            )
    file_count = len(doc_files)
    if file_count > 0:
        score = 75 + min(file_count * 5, 25)
        return score, file_count, gaps

    gaps.append(
        Gap(
            layer="docs",
            description=f"No documentation found for domain '{domain}'",
            severity="significant",
        )
    )
    return 40, 0, gaps


def _grade_workflows_layer(
    repo_root: Path, domain: str,
) -> tuple[int, int, list[Gap]]:
    """Grade the workflows layer for a domain.

    Returns:
        Tuple of (score, file_count, gaps).
    """
    wf_dir = repo_root / ".github" / "workflows"
    if not wf_dir.is_dir():
        return 50, 0, []

    wf_files = [
        f
        for f in wf_dir.glob("*.yml")
        if domain in f.stem.lower() or domain.replace("-", "") in f.stem.lower()
    ]
    file_count = len(wf_files)
    if file_count > 0:
        score = 80 + min(file_count * 10, 20)
        return score, file_count, []

    return 50, 0, []


_LAYER_GRADERS: dict[str, object] = {
    "agents": _grade_agents_layer,
    "skills": _grade_skills_layer,
    "scripts": _grade_scripts_layer,
    "tests": _grade_tests_layer,
    "docs": _grade_docs_layer,
    "workflows": _grade_workflows_layer,
}


def grade_layer(
    repo_root: Path,
    domain: str,
    layer: str,
) -> LayerGrade:
    """Grade a single architectural layer for a domain."""
    grader = _LAYER_GRADERS.get(layer)
    if grader is None:
        return LayerGrade(layer=layer, grade="F", score=0, gaps=[], file_count=0)

    score, file_count, gaps = grader(repo_root, domain)
    score = min(score, 100)

    return LayerGrade(
        layer=layer,
        grade=score_to_grade(score),
        score=score,
        gaps=gaps,
        file_count=file_count,
    )


def grade_domain(repo_root: Path, domain: str) -> DomainGrade:
    """Grade all layers for a single domain."""
    layers = [grade_layer(repo_root, domain, layer) for layer in LAYERS]
    return DomainGrade(domain=domain, layers=layers)


def compute_trend(current: float, previous: float | None) -> str:
    """Compute trend indicator from score delta."""
    if previous is None:
        return "new"
    delta = current - previous
    if delta > 5:
        return "improving"
    if delta < -5:
        return "degrading"
    return "stable"


def load_previous_grades(output_path: Path) -> dict[str, float] | None:
    """Load previous grades from existing report for trend tracking."""
    if not output_path.exists():
        return None
    try:
        data = json.loads(output_path.read_text(encoding="utf-8"))
        return {d["domain"]: d["overall_score"] for d in data.get("domains", [])}
    except (json.JSONDecodeError, KeyError):
        return None


def format_markdown(grades: list[DomainGrade], trends: dict[str, str]) -> str:
    """Format grades as markdown report."""
    trend_icons = {
        "improving": "(improving)",
        "stable": "(stable)",
        "degrading": "(degrading)",
        "new": "(new)",
    }

    lines = [
        "# Quality Grades",
        "",
        f"Last updated: {datetime.now(UTC).strftime('%Y-%m-%d')}",
        "Grading agent: quality-auditor",
        "",
    ]

    for dg in sorted(grades, key=lambda g: g.domain):
        trend = trends.get(dg.domain, "new")
        trend_label = trend_icons.get(trend, "")
        lines.append(f"## Domain: {dg.domain}")
        lines.append("")
        lines.append(f"Overall: **{dg.overall_grade}** ({dg.overall_score:.0f}/100) {trend_label}")
        lines.append("")
        lines.append("| Layer | Grade | Score | Files | Gaps |")
        lines.append("|-------|-------|-------|-------|------|")
        for lg in dg.layers:
            gap_text = "; ".join(g.description for g in lg.gaps) if lg.gaps else "-"
            lines.append(f"| {lg.layer} | {lg.grade} | {lg.score} | {lg.file_count} | {gap_text} |")
        lines.append("")

    # Summary
    total_gaps = sum(len(lg.gaps) for dg in grades for lg in dg.layers)
    critical_gaps = sum(
        1 for dg in grades for lg in dg.layers for g in lg.gaps if g.severity == "critical"
    )
    lines.extend(
        [
            "## Summary",
            "",
            f"- Domains graded: {len(grades)}",
            f"- Total gaps: {total_gaps}",
            f"- Critical gaps: {critical_gaps}",
            "",
        ]
    )

    return "\n".join(lines)


def format_json(grades: list[DomainGrade], trends: dict[str, str]) -> str:
    """Format grades as JSON report."""
    data = {
        "generated_at": datetime.now(UTC).isoformat(),
        "grading_agent": "quality-auditor",
        "domains": [
            {
                "domain": dg.domain,
                "overall_grade": dg.overall_grade,
                "overall_score": round(dg.overall_score, 1),
                "trend": trends.get(dg.domain, "new"),
                "layers": [
                    {
                        "layer": lg.layer,
                        "grade": lg.grade,
                        "score": lg.score,
                        "file_count": lg.file_count,
                        "gaps": [asdict(g) for g in lg.gaps],
                    }
                    for lg in dg.layers
                ],
            }
            for dg in sorted(grades, key=lambda g: g.domain)
        ],
    }
    return json.dumps(data, indent=2)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Grade quality per product domain with gap tracking"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root directory (default: cwd)",
    )
    parser.add_argument(
        "--domains",
        nargs="*",
        help="Specific domains to grade (default: auto-detect)",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        help="Only show top N domains by gap count",
    )
    return parser.parse_args()


def main() -> int:
    """Run the quality grading process."""
    args = parse_args()
    repo_root = args.repo_root.resolve()

    if not (repo_root / ".claude").is_dir():
        print("Error: not a valid repo root (no .claude directory)", file=sys.stderr)
        return 2

    # Detect or use specified domains
    if args.domains:
        domains = args.domains
    else:
        domains = detect_domains(repo_root)

    if not domains:
        print("No domains detected.", file=sys.stderr)
        return 2

    # Load previous grades for trend tracking
    previous = None
    if args.output:
        json_path = args.output.with_suffix(".json")
        previous = load_previous_grades(json_path)

    # Grade each domain
    grades = [grade_domain(repo_root, d) for d in domains]

    # Compute trends
    trends: dict[str, str] = {}
    for dg in grades:
        prev_score = previous.get(dg.domain) if previous else None
        trends[dg.domain] = compute_trend(dg.overall_score, prev_score)

    # Filter to top N if requested
    if args.top_n:
        grades.sort(
            key=lambda g: sum(len(lg.gaps) for lg in g.layers),
            reverse=True,
        )
        grades = grades[: args.top_n]

    # Format output
    if args.format == "json":
        output = format_json(grades, trends)
    else:
        output = format_markdown(grades, trends)

    # Write or print
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
