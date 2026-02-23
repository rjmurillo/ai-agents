#!/usr/bin/env python3
"""Auto-consolidate recurring patterns from session logs into skill candidates.

Scans session logs for recurring action patterns that meet consolidation
criteria (minimum uses, success rate, lookback window). Outputs skill
candidates as JSON or writes them to .serena/memories/.

EXIT CODES:
  0  - Success: Consolidation completed
  1  - Error: Logic or validation error
  2  - Error: Configuration or path error

See: ADR-035 Exit Code Standardization
See: Issue #173 - Implement Skill Auto-Consolidation from Retrospectives
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class ConsolidationConfig:
    """Thresholds for pattern consolidation."""

    min_uses: int = 3
    min_success_rate: float = 0.70
    lookback_days: int = 7


@dataclass
class PatternOccurrence:
    """A single occurrence of a pattern in a session."""

    session_date: str
    session_file: str
    raw_action: str
    succeeded: bool


@dataclass
class PatternStats:
    """Aggregated statistics for a normalized pattern."""

    normalized: str
    category: str
    occurrences: list[PatternOccurrence] = field(default_factory=list)

    @property
    def use_count(self) -> int:
        return len(self.occurrences)

    @property
    def success_count(self) -> int:
        return sum(1 for o in self.occurrences if o.succeeded)

    @property
    def success_rate(self) -> float:
        if not self.occurrences:
            return 0.0
        return self.success_count / self.use_count

    def meets_criteria(self, config: ConsolidationConfig) -> bool:
        return self.use_count >= config.min_uses and self.success_rate >= config.min_success_rate

    def to_dict(self) -> dict[str, object]:
        return {
            "normalized_pattern": self.normalized,
            "category": self.category,
            "use_count": self.use_count,
            "success_count": self.success_count,
            "success_rate": round(self.success_rate, 4),
            "sessions": [o.session_file for o in self.occurrences],
        }


@dataclass
class SkillCandidate:
    """A pattern that qualifies for skill generation."""

    pattern: PatternStats
    skill_id: str
    title: str
    duplicate_of: str | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "skill_id": self.skill_id,
            "title": self.title,
            "category": self.pattern.category,
            "use_count": self.pattern.use_count,
            "success_rate": round(self.pattern.success_rate, 4),
            "sessions": [o.session_file for o in self.pattern.occurrences],
        }
        if self.duplicate_of:
            result["duplicate_of"] = self.duplicate_of
        return result


@dataclass
class ConsolidationReport:
    """Result of the consolidation process."""

    sessions_scanned: int = 0
    patterns_found: int = 0
    candidates: list[SkillCandidate] = field(default_factory=list)
    duplicates_skipped: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "sessions_scanned": self.sessions_scanned,
            "patterns_found": self.patterns_found,
            "candidates_total": len(self.candidates),
            "candidates_new": len([c for c in self.candidates if not c.duplicate_of]),
            "duplicates_skipped": self.duplicates_skipped,
            "candidates": [c.to_dict() for c in self.candidates],
        }


# Regex patterns for normalizing action strings
_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
_ISSUE_RE = re.compile(r"#\d+")
_FILE_PATH_RE = re.compile(r"[\w./\\-]+\.\w{1,6}")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SESSION_NUM_RE = re.compile(r"session[- ]?\d+", re.IGNORECASE)

# Category keywords for classifying patterns
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "security": ["security", "cwe", "vulnerability", "scan", "audit"],
    "testing": ["test", "pytest", "pester", "coverage", "assert"],
    "ci-infrastructure": ["workflow", "ci", "pipeline", "action", "deploy"],
    "documentation": ["doc", "readme", "adr", "markdown"],
    "git-operations": ["commit", "push", "merge", "branch", "rebase"],
    "memory": ["memory", "serena", "forgetful", "knowledge"],
    "pr-review": ["pr", "review", "comment", "thread"],
    "session": ["session", "log", "protocol", "validation"],
    "implementation": ["implement", "script", "code", "refactor", "fix"],
}


def normalize_action(action: str) -> str:
    """Normalize an action string by removing volatile identifiers."""
    result = action.strip().lower()
    result = _SHA_RE.sub("<sha>", result)
    result = _ISSUE_RE.sub("<issue>", result)
    result = _FILE_PATH_RE.sub("<path>", result)
    result = _DATE_RE.sub("<date>", result)
    result = _SESSION_NUM_RE.sub("<session>", result)
    # Collapse whitespace
    result = re.sub(r"\s+", " ", result).strip()
    return result


def classify_category(action: str) -> str:
    """Classify an action into a category based on keywords."""
    action_lower = action.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in action_lower for kw in keywords):
            return category
    return "general"


def infer_success(session: dict[str, object]) -> bool:
    """Infer whether a session was successful from its data.

    Checks protocol compliance, outcomes, and status fields.
    """
    # Check explicit status
    status = session.get("status", "")
    if isinstance(status, str) and status.lower() in ("failed", "error", "aborted"):
        return False

    # Check protocol compliance end state
    compliance = session.get("protocolCompliance", {})
    if isinstance(compliance, dict):
        end = compliance.get("sessionEnd", {})
        if isinstance(end, dict):
            for item in end.values():
                if isinstance(item, dict):
                    level = item.get("level", "")
                    complete = item.get("Complete", item.get("complete", True))
                    if level == "MUST" and not complete:
                        return False

    # Check outcomes for failure indicators
    outcomes = session.get("outcomes", [])
    if isinstance(outcomes, list):
        for outcome in outcomes:
            if isinstance(outcome, str):
                lower = outcome.lower()
                if any(word in lower for word in ("failed", "error", "blocked", "aborted")):
                    return False

    return True


def extract_actions(session: dict[str, object]) -> list[str]:
    """Extract action strings from a session log."""
    actions: list[str] = []

    # From workLog
    work_log = session.get("workLog", session.get("work", []))
    if isinstance(work_log, list):
        for entry in work_log:
            if isinstance(entry, dict):
                action = entry.get("action", "")
                if isinstance(action, str) and action.strip():
                    actions.append(action.strip())

    # From agentActivities
    activities = session.get("agentActivities", [])
    if isinstance(activities, list):
        for activity in activities:
            if isinstance(activity, dict):
                agent = activity.get("agent", "")
                action = activity.get("action", "")
                if isinstance(action, str) and action.strip():
                    prefix = f"{agent}: " if agent else ""
                    actions.append(f"{prefix}{action.strip()}")

    return actions


def load_sessions(
    sessions_dir: Path,
    cutoff: datetime,
) -> list[tuple[dict[str, object], str]]:
    """Load session logs newer than the cutoff date.

    Returns list of (session_data, filename) tuples.
    """
    if not sessions_dir.is_dir():
        return []

    results: list[tuple[dict[str, object], str]] = []

    for log_path in sorted(sessions_dir.glob("*.json")):
        try:
            content = log_path.read_text(encoding="utf-8")
            data = json.loads(content)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue

        if not isinstance(data, dict):
            continue

        # Extract date from session metadata or filename
        session_meta = data.get("session", {})
        date_str = ""
        if isinstance(session_meta, dict):
            date_str = session_meta.get("date", "")

        if not date_str:
            # Try filename: YYYY-MM-DD-session-NN.json
            match = re.match(r"(\d{4}-\d{2}-\d{2})", log_path.name)
            if match:
                date_str = match.group(1)

        if not date_str:
            continue

        try:
            session_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            continue

        if session_date >= cutoff:
            results.append((data, log_path.name))

    return results


def find_patterns(
    sessions: list[tuple[dict[str, object], str]],
) -> dict[str, PatternStats]:
    """Extract and aggregate patterns from session logs."""
    patterns: dict[str, PatternStats] = {}

    for session_data, filename in sessions:
        session_meta = session_data.get("session", {})
        date_str = ""
        if isinstance(session_meta, dict):
            date_str = session_meta.get("date", "")

        succeeded = infer_success(session_data)
        actions = extract_actions(session_data)

        for action in actions:
            normalized = normalize_action(action)
            if len(normalized) < 10:
                continue

            if normalized not in patterns:
                category = classify_category(action)
                patterns[normalized] = PatternStats(
                    normalized=normalized, category=category
                )

            patterns[normalized].occurrences.append(
                PatternOccurrence(
                    session_date=date_str,
                    session_file=filename,
                    raw_action=action,
                    succeeded=succeeded,
                )
            )

    return patterns


def load_existing_skill_titles(memories_dir: Path) -> set[str]:
    """Load titles of existing skills from memory files for dedup."""
    titles: set[str] = set()

    if not memories_dir.is_dir():
        return titles

    for md_file in memories_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # Extract title from markdown heading
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip().lower()
                titles.add(title)
                break

    return titles


def generate_skill_id(category: str, existing_ids: set[str]) -> str:
    """Generate a unique skill ID for a category."""
    for i in range(1, 1000):
        skill_id = f"Skill-{category.title().replace('-', '')}-{i:03d}"
        if skill_id not in existing_ids:
            existing_ids.add(skill_id)
            return skill_id
    return f"Skill-{category.title()}-999"


def build_skill_title(pattern: PatternStats) -> str:
    """Build a human-readable skill title from a pattern."""
    # Clean up the normalized pattern for use as a title
    title = pattern.normalized
    # Remove placeholder tokens
    title = title.replace("<sha>", "").replace("<issue>", "")
    title = title.replace("<path>", "").replace("<date>", "")
    title = title.replace("<session>", "")
    title = re.sub(r"\s+", " ", title).strip()
    # Capitalize first letter and truncate
    if title:
        title = title[0].upper() + title[1:]
    if len(title) > 80:
        title = title[:77] + "..."
    return title


def check_duplicates(
    candidate_title: str,
    existing_titles: set[str],
) -> str | None:
    """Check if a candidate title is a duplicate of an existing skill.

    Returns the matching existing title if found, None otherwise.
    """
    candidate_lower = candidate_title.lower()
    for existing in existing_titles:
        # Exact match
        if candidate_lower == existing:
            return existing
        # Substring containment (either direction)
        if len(candidate_lower) > 15 and len(existing) > 15:
            if candidate_lower in existing or existing in candidate_lower:
                return existing
    return None


def consolidate(
    sessions_dir: Path,
    memories_dir: Path,
    config: ConsolidationConfig,
) -> ConsolidationReport:
    """Run the full consolidation pipeline."""
    report = ConsolidationReport()

    cutoff = datetime.now(UTC) - timedelta(days=config.lookback_days)
    sessions = load_sessions(sessions_dir, cutoff)
    report.sessions_scanned = len(sessions)

    if not sessions:
        return report

    patterns = find_patterns(sessions)
    report.patterns_found = len(patterns)

    qualifying = {
        k: v for k, v in patterns.items() if v.meets_criteria(config)
    }

    if not qualifying:
        return report

    existing_titles = load_existing_skill_titles(memories_dir)
    used_ids: set[str] = set()

    for pattern in sorted(qualifying.values(), key=lambda p: p.use_count, reverse=True):
        title = build_skill_title(pattern)
        skill_id = generate_skill_id(pattern.category, used_ids)
        duplicate = check_duplicates(title, existing_titles)

        candidate = SkillCandidate(
            pattern=pattern,
            skill_id=skill_id,
            title=title,
            duplicate_of=duplicate,
        )

        if duplicate:
            report.duplicates_skipped += 1
        report.candidates.append(candidate)

    return report


def render_skill_markdown(candidate: SkillCandidate) -> str:
    """Render a skill candidate as a Serena memory markdown file."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    sessions_list = ", ".join(
        sorted(set(o.session_file for o in candidate.pattern.occurrences))
    )

    return f"""# Skill: {candidate.title}

## Statement

{candidate.title}

## Context

Auto-consolidated from {candidate.pattern.use_count} session occurrences with \
{candidate.pattern.success_rate:.0%} success rate.

## Pattern

Recurring action pattern detected across sessions:
- Category: {candidate.pattern.category}
- Uses: {candidate.pattern.use_count}
- Success rate: {candidate.pattern.success_rate:.0%}

## Evidence

Sessions: {sessions_list}

## Atomicity

**Score**: 70%

## Category

{candidate.pattern.category}

## Tag

helpful

## Impact

**Rating**: 5/10

## Validation Count

{candidate.pattern.use_count} (auto-consolidated)

## Created

{today}
"""


def write_skills(
    candidates: list[SkillCandidate],
    memories_dir: Path,
) -> list[Path]:
    """Write new skill candidates to memory files. Returns paths written."""
    written: list[Path] = []

    for candidate in candidates:
        if candidate.duplicate_of:
            continue

        filename = f"{candidate.pattern.category}-auto-{candidate.skill_id.lower()}.md"
        path = memories_dir / filename

        content = render_skill_markdown(candidate)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)

    return written


def main() -> int:
    """Entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Auto-consolidate recurring patterns from session logs into skills"
    )
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=None,
        help="Path to sessions directory (default: .agents/sessions/)",
    )
    parser.add_argument(
        "--memories-dir",
        type=Path,
        default=None,
        help="Path to memories directory (default: .serena/memories/)",
    )
    parser.add_argument(
        "--min-uses",
        type=int,
        default=3,
        help="Minimum uses for consolidation (default: 3)",
    )
    parser.add_argument(
        "--min-success-rate",
        type=float,
        default=0.70,
        help="Minimum success rate for consolidation (default: 0.70)",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="Lookback window in days (default: 7)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report candidates without writing files",
    )
    parser.add_argument(
        "--format",
        choices=["json", "table"],
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

    # Determine project root
    if args.project_root:
        project_root = args.project_root.resolve()
    else:
        project_root = Path(__file__).resolve().parent.parent

    sessions_dir = args.sessions_dir or (project_root / ".agents" / "sessions")
    memories_dir = args.memories_dir or (project_root / ".serena" / "memories")

    # CWE-22 path traversal prevention: reject ".." in raw path, then resolve
    for dir_path, name in [(sessions_dir, "sessions"), (memories_dir, "memories")]:
        if ".." in dir_path.parts:
            print(
                f"[ERROR] {name} directory contains path traversal component",
                file=sys.stderr,
            )
            return 2

    config = ConsolidationConfig(
        min_uses=args.min_uses,
        min_success_rate=args.min_success_rate,
        lookback_days=args.lookback_days,
    )

    try:
        report = consolidate(sessions_dir, memories_dir, config)
    except Exception as exc:
        print(f"[ERROR] Consolidation failed: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_table(report, args.dry_run)

    if not args.dry_run:
        new_candidates = [c for c in report.candidates if not c.duplicate_of]
        if new_candidates:
            written = write_skills(new_candidates, memories_dir)
            for path in written:
                print(f"  Written: {path}")

    return 0


def _print_table(report: ConsolidationReport, dry_run: bool) -> None:
    """Print a human-readable summary."""
    mode = "[DRY RUN] " if dry_run else ""
    print(f"{mode}=== Skill Auto-Consolidation Report ===")
    print()
    print(f"Sessions scanned: {report.sessions_scanned}")
    print(f"Patterns found:   {report.patterns_found}")

    new_count = len([c for c in report.candidates if not c.duplicate_of])
    print(f"Candidates (new): {new_count}")
    print(f"Duplicates:       {report.duplicates_skipped}")
    print()

    if not report.candidates:
        print("No patterns met consolidation criteria.")
        return

    print(f"{'Skill ID':<28} {'Uses':>5} {'Rate':>6}  {'Title'}")
    print("-" * 80)
    for candidate in report.candidates:
        dup = " [DUP]" if candidate.duplicate_of else ""
        print(
            f"{candidate.skill_id:<28} "
            f"{candidate.pattern.use_count:>5} "
            f"{candidate.pattern.success_rate:>5.0%}  "
            f"{candidate.title[:40]}{dup}"
        )


if __name__ == "__main__":
    sys.exit(main())
