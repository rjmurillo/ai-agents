#!/usr/bin/env python3
"""Compute aggregate health status from collected metrics.

Synthesizes metrics from session logs and memory health into actionable
status indicators (healthy, warning, error) with threshold-based alerting.

EXIT CODES:
  0  - Success: Health status computed, all components healthy or warning
  1  - Error: At least one component in error state
  2  - Error: Configuration or path error
  3  - Error: Unexpected error

See: ADR-035 Exit Code Standardization
See: Issue #178 - Add Health Status Computation from Metrics
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path


class HealthLevel(Enum):
    """Overall health status level."""

    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Threshold:
    """Warning and error thresholds for a metric."""

    warning: float
    error: float
    higher_is_worse: bool = True


# Default thresholds per issue #178 spec
DEFAULT_THRESHOLDS: dict[str, Threshold] = {
    "memory_stale_rate": Threshold(warning=0.10, error=0.25),
    "memory_error_rate": Threshold(warning=0.05, error=0.15),
    "session_failure_rate": Threshold(warning=0.10, error=0.25),
    "context_retrieval_skip_rate": Threshold(warning=0.40, error=0.60),
}


@dataclass
class ComponentHealth:
    """Health status for a single component."""

    name: str
    level: HealthLevel
    value: float
    threshold_warning: float
    threshold_error: float
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        """Convert to JSON-serializable dict."""
        return {
            "name": self.name,
            "level": self.level.value,
            "value": round(self.value, 4),
            "threshold_warning": self.threshold_warning,
            "threshold_error": self.threshold_error,
            "detail": self.detail,
        }


@dataclass
class HealthStatusReport:
    """Aggregate health status across all components."""

    components: list[ComponentHealth] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def overall_level(self) -> HealthLevel:
        """Worst status across all components."""
        if any(c.level == HealthLevel.ERROR for c in self.components):
            return HealthLevel.ERROR
        if any(c.level == HealthLevel.WARNING for c in self.components):
            return HealthLevel.WARNING
        return HealthLevel.HEALTHY

    @property
    def error_count(self) -> int:
        """Number of components in error state."""
        return sum(1 for c in self.components if c.level == HealthLevel.ERROR)

    @property
    def warning_count(self) -> int:
        """Number of components in warning state."""
        return sum(1 for c in self.components if c.level == HealthLevel.WARNING)

    @property
    def healthy_count(self) -> int:
        """Number of components in healthy state."""
        return sum(1 for c in self.components if c.level == HealthLevel.HEALTHY)

    def to_dict(self) -> dict[str, object]:
        """Convert to JSON-serializable dict."""
        return {
            "checked_at": self.checked_at.isoformat(),
            "overall": self.overall_level.value,
            "summary": {
                "total": len(self.components),
                "healthy": self.healthy_count,
                "warning": self.warning_count,
                "error": self.error_count,
            },
            "components": [c.to_dict() for c in self.components],
        }

    def to_markdown(self) -> str:
        """Generate a markdown health report."""
        lines: list[str] = []
        lines.append("# Health Status Report")
        lines.append("")

        if not self.components:
            lines.append("No components checked.")
            return "\n".join(lines)

        icon = _level_icon(self.overall_level)
        lines.append(f"**{icon} Overall: {self.overall_level.value.upper()}**")
        lines.append("")
        lines.append(f"Checked: {self.checked_at.strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append("")
        lines.append("| Component | Status | Value | Warning | Error | Detail |")
        lines.append("|-----------|--------|-------|---------|-------|--------|")

        for comp in self.components:
            icon = _level_icon(comp.level)
            lines.append(
                f"| {comp.name} | {icon} {comp.level.value} "
                f"| {comp.value:.2%} "
                f"| {comp.threshold_warning:.0%} "
                f"| {comp.threshold_error:.0%} "
                f"| {comp.detail} |"
            )

        lines.append("")
        lines.append(
            f"**Summary**: {self.healthy_count} healthy, "
            f"{self.warning_count} warning, "
            f"{self.error_count} error"
        )
        lines.append("")

        recommendations = _get_recommendations(self)
        if recommendations:
            lines.append("## Recommendations")
            lines.append("")
            for rec in recommendations:
                lines.append(f"- {rec}")
            lines.append("")

        return "\n".join(lines)


def _level_icon(level: HealthLevel) -> str:
    """Return a text indicator for a health level."""
    icons = {
        HealthLevel.HEALTHY: "[PASS]",
        HealthLevel.WARNING: "[WARN]",
        HealthLevel.ERROR: "[FAIL]",
    }
    return icons.get(level, "[?]")


def _get_recommendations(report: HealthStatusReport) -> list[str]:
    """Generate actionable recommendations for non-healthy components."""
    recs: list[str] = []
    for comp in report.components:
        if comp.level == HealthLevel.HEALTHY:
            continue
        if comp.name == "memory_stale_rate":
            recs.append(
                f"Memory stale rate is {comp.value:.0%}. "
                "Run memory health checks and update stale citations."
            )
        elif comp.name == "memory_error_rate":
            recs.append(
                f"Memory error rate is {comp.value:.0%}. "
                "Fix malformed memory files in .serena/memories/."
            )
        elif comp.name == "session_failure_rate":
            recs.append(
                f"Session failure rate is {comp.value:.0%}. "
                "Review recent session logs for recurring failures."
            )
        elif comp.name == "context_retrieval_skip_rate":
            recs.append(
                f"Context retrieval skip rate is {comp.value:.0%}. "
                "Check orchestrator classification for context-retrieval invocation."
            )
    return recs


def classify_level(value: float, threshold: Threshold) -> HealthLevel:
    """Classify a metric value against thresholds.

    For higher_is_worse metrics (default), values above thresholds trigger
    warning or error. For lower_is_worse, values below thresholds trigger.
    """
    if threshold.higher_is_worse:
        if value >= threshold.error:
            return HealthLevel.ERROR
        if value >= threshold.warning:
            return HealthLevel.WARNING
        return HealthLevel.HEALTHY

    if value <= threshold.error:
        return HealthLevel.ERROR
    if value <= threshold.warning:
        return HealthLevel.WARNING
    return HealthLevel.HEALTHY


def compute_memory_health(memories_dir: Path) -> list[ComponentHealth]:
    """Compute health components from memory files.

    Scans .serena/memories/ for markdown files and computes stale rate
    and error rate based on file parse success and frontmatter validity.
    """
    components: list[ComponentHealth] = []

    if not memories_dir.is_dir():
        return components

    md_files = sorted(memories_dir.glob("*.md"))
    total = len(md_files)

    if total == 0:
        return components

    parse_errors = 0
    stale_count = 0

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            parse_errors += 1
            continue

        # Check for valid YAML frontmatter
        if not content.startswith("---"):
            parse_errors += 1
            continue

        parts = content.split("---", 2)
        if len(parts) < 3:
            parse_errors += 1
            continue

        # Check for staleness indicators in frontmatter
        frontmatter = parts[1]
        if re.search(r"^\s*(?:stale|deprecated):\s*true", frontmatter, re.MULTILINE):
            stale_count += 1

    stale_rate = stale_count / total
    error_rate = parse_errors / total

    stale_threshold = DEFAULT_THRESHOLDS["memory_stale_rate"]
    error_threshold = DEFAULT_THRESHOLDS["memory_error_rate"]

    components.append(
        ComponentHealth(
            name="memory_stale_rate",
            level=classify_level(stale_rate, stale_threshold),
            value=stale_rate,
            threshold_warning=stale_threshold.warning,
            threshold_error=stale_threshold.error,
            detail=f"{stale_count}/{total} memories stale",
        )
    )
    components.append(
        ComponentHealth(
            name="memory_error_rate",
            level=classify_level(error_rate, error_threshold),
            value=error_rate,
            threshold_warning=error_threshold.warning,
            threshold_error=error_threshold.error,
            detail=f"{parse_errors}/{total} memories with parse errors",
        )
    )

    return components


def compute_session_health(sessions_dir: Path, limit: int = 50) -> list[ComponentHealth]:
    """Compute health components from session logs.

    Analyzes recent session logs for failure rates and context-retrieval
    invocation patterns.
    """
    components: list[ComponentHealth] = []

    if not sessions_dir.is_dir():
        return components

    log_files = sorted(sessions_dir.glob("*.json"), key=lambda p: p.name, reverse=True)
    log_files = log_files[:limit]

    if not log_files:
        return components

    total_sessions = 0
    failed_sessions = 0
    eligible_orchestrations = 0
    skipped_context_retrieval = 0

    for log_path in log_files:
        try:
            content = log_path.read_text(encoding="utf-8")
            session = json.loads(content)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue

        if not isinstance(session, dict):
            continue

        total_sessions += 1

        # Check session outcome for failures
        status = session.get("status", "")
        if isinstance(status, str) and status.lower() in ("failed", "error", "aborted"):
            failed_sessions += 1

        # Check context-retrieval invocation
        classification = session.get("classification", {})
        if isinstance(classification, dict) and classification:
            eligible_orchestrations += 1
            cr_status = classification.get("context_retrieval", "")
            if isinstance(cr_status, str) and cr_status.upper() != "INVOKED":
                skipped_context_retrieval += 1

    # Session failure rate
    if total_sessions > 0:
        failure_rate = failed_sessions / total_sessions
        failure_threshold = DEFAULT_THRESHOLDS["session_failure_rate"]
        components.append(
            ComponentHealth(
                name="session_failure_rate",
                level=classify_level(failure_rate, failure_threshold),
                value=failure_rate,
                threshold_warning=failure_threshold.warning,
                threshold_error=failure_threshold.error,
                detail=f"{failed_sessions}/{total_sessions} sessions failed",
            )
        )

    # Context-retrieval skip rate
    if eligible_orchestrations > 0:
        skip_rate = skipped_context_retrieval / eligible_orchestrations
        skip_threshold = DEFAULT_THRESHOLDS["context_retrieval_skip_rate"]
        components.append(
            ComponentHealth(
                name="context_retrieval_skip_rate",
                level=classify_level(skip_rate, skip_threshold),
                value=skip_rate,
                threshold_warning=skip_threshold.warning,
                threshold_error=skip_threshold.error,
                detail=(
                    f"{skipped_context_retrieval}/{eligible_orchestrations} "
                    "orchestrations skipped context-retrieval"
                ),
            )
        )

    return components


def compute_health(
    project_root: Path,
    *,
    memories_dir: Path | None = None,
    sessions_dir: Path | None = None,
    session_limit: int = 50,
) -> HealthStatusReport:
    """Compute aggregate health status from all metric sources.

    Args:
        project_root: Repository root for path containment.
        memories_dir: Override for memories directory.
        sessions_dir: Override for sessions directory.
        session_limit: Max session logs to analyze.

    Returns:
        HealthStatusReport with all component health statuses.
    """
    report = HealthStatusReport()

    mem_dir = memories_dir or (project_root / ".serena" / "memories")
    sess_dir = sessions_dir or (project_root / ".agents" / "sessions")

    report.components.extend(compute_memory_health(mem_dir))
    report.components.extend(compute_session_health(sess_dir, limit=session_limit))

    return report


def main() -> int:
    """Entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Compute aggregate health status from metrics"
    )
    parser.add_argument(
        "--memories-dir",
        type=Path,
        default=None,
        help="Path to memories directory (default: .serena/memories/)",
    )
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=None,
        help="Path to sessions directory (default: .agents/sessions/)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum session logs to analyze (default: 50)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "table", "markdown"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root for path containment (default: auto-detect)",
    )
    args = parser.parse_args()

    # Determine project root with CWE-22 path containment
    if args.project_root:
        project_root = args.project_root.resolve()
    else:
        project_root = Path(__file__).resolve().parent.parent

    # Validate provided paths are within project root
    for dir_arg, name in [
        (args.memories_dir, "memories"),
        (args.sessions_dir, "sessions"),
    ]:
        if dir_arg is not None:
            resolved = dir_arg.resolve()
            if not resolved.is_relative_to(project_root):
                print(
                    f"[ERROR] {name} directory must be within project root"
                    f" ({project_root})",
                    file=sys.stderr,
                )
                return 2

    try:
        report = compute_health(
            project_root,
            memories_dir=args.memories_dir,
            sessions_dir=args.sessions_dir,
            session_limit=args.limit,
        )
    except Exception as exc:
        print(f"[ERROR] Unexpected error: {exc}", file=sys.stderr)
        return 3

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    elif args.format == "markdown":
        print(report.to_markdown())
    else:
        _print_table(report)

    # Exit code 1 if any component in error state
    if report.overall_level == HealthLevel.ERROR:
        return 1
    return 0


def _print_table(report: HealthStatusReport) -> None:
    """Print a human-readable table summary."""
    icon = _level_icon(report.overall_level)
    print(f"=== Health Status: {icon} {report.overall_level.value.upper()} ===")
    print()

    if not report.components:
        print("No components checked. Ensure .serena/memories/ and .agents/sessions/ exist.")
        return

    print(f"{'Component':<30} {'Status':<10} {'Value':>8}  {'Detail'}")
    print("-" * 80)
    for comp in report.components:
        icon = _level_icon(comp.level)
        print(
            f"{comp.name:<30} {icon:<10} {comp.value:>7.1%}  {comp.detail}"
        )
    print()
    print(
        f"Summary: {report.healthy_count} healthy, "
        f"{report.warning_count} warning, "
        f"{report.error_count} error"
    )

    recommendations = _get_recommendations(report)
    if recommendations:
        print()
        print("Recommendations:")
        for rec in recommendations:
            print(f"  - {rec}")


if __name__ == "__main__":
    sys.exit(main())
