"""Session reflection for memory reinforcement, skill candidate generation, and fact extraction.

Processes session logs to:
1. Reinforce memories that led to successful outcomes.
2. Generate skill candidates from repeated failures (governed, not auto-promoted).
3. Extract novel facts from session activity.
4. Apply confidence decay to accessed but unverified memories.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

# Confidence adjustment constants
REINFORCE_BOOST = 0.05
DECAY_PENALTY = 0.02
MAX_CONFIDENCE = 1.0
MIN_CONFIDENCE = 0.0
FAILURE_CLUSTER_THRESHOLD = 2


@dataclass
class SkillCandidate:
    """A proposed skill generated from repeated session failures."""

    name: str
    description: str
    source_failures: list[str]
    session_id: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    governance_gate: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return asdict(self)


@dataclass
class SessionFact:
    """A fact extracted from a session log."""

    key: str
    value: str
    session_id: str
    confidence: float = 0.7

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return asdict(self)


@dataclass
class ReflectionResult:
    """Summary of a reflection pass over a session."""

    reinforced_count: int = 0
    skill_candidates: list[SkillCandidate] = field(default_factory=list)
    facts_captured: list[SessionFact] = field(default_factory=list)
    decayed_count: int = 0


def reinforce_memories(
    accessed_memories: list[str],
    successes: list[str],
) -> list[tuple[str, float]]:
    """Bump confidence for memories accessed during successful outcomes.

    Args:
        accessed_memories: Memory IDs accessed during the session.
        successes: Descriptions of successful outcomes.

    Returns:
        List of (memory_id, boost_amount) tuples for memories that were reinforced.
    """
    if not successes:
        return []

    reinforced: list[tuple[str, float]] = []
    for memory_id in accessed_memories:
        if not memory_id:
            continue
        reinforced.append((memory_id, REINFORCE_BOOST))
    return reinforced


def generate_skill_candidates(
    failures: list[str],
    session_id: str = "",
) -> list[SkillCandidate]:
    """Cluster failures into skill candidate proposals.

    Groups similar failure descriptions and generates a skill candidate
    when the cluster size meets the threshold.

    Args:
        failures: Descriptions of failures from the session.
        session_id: Session identifier for traceability.

    Returns:
        List of SkillCandidate proposals (staged, not auto-promoted).
    """
    if not failures:
        return []

    # Group failures by their first significant word (simple clustering)
    clusters: dict[str, list[str]] = {}
    for failure in failures:
        normalized = failure.strip().lower()
        if not normalized:
            continue
        # Use first two words as cluster key for basic grouping
        words = normalized.split()
        cluster_key = " ".join(words[:2]) if len(words) >= 2 else normalized
        clusters.setdefault(cluster_key, []).append(failure)

    candidates: list[SkillCandidate] = []
    for cluster_key, cluster_failures in clusters.items():
        if len(cluster_failures) >= FAILURE_CLUSTER_THRESHOLD:
            safe_name = cluster_key.replace(" ", "-")[:50]
            candidates.append(
                SkillCandidate(
                    name=f"skill-candidate-{safe_name}",
                    description=(
                        f"Auto-generated from {len(cluster_failures)} similar failures: "
                        f"{cluster_failures[0][:100]}"
                    ),
                    source_failures=cluster_failures,
                    session_id=session_id,
                )
            )
    return candidates


def extract_session_facts(
    session_log: dict[str, Any],
    session_id: str = "",
) -> list[SessionFact]:
    """Parse a session log to extract novel facts.

    Looks for structured data in session log fields such as decisions,
    tools used, and outcomes.

    Args:
        session_log: Parsed session log dictionary.
        session_id: Session identifier for citation.

    Returns:
        List of SessionFact entries.
    """
    facts: list[SessionFact] = []

    # Extract decisions as facts
    decisions = session_log.get("decisions", [])
    for decision in decisions:
        if isinstance(decision, str) and decision.strip():
            facts.append(
                SessionFact(
                    key="decision",
                    value=decision.strip(),
                    session_id=session_id,
                )
            )
        elif isinstance(decision, dict):
            desc = decision.get("description", "")
            if desc:
                facts.append(
                    SessionFact(
                        key="decision",
                        value=str(desc).strip(),
                        session_id=session_id,
                    )
                )

    # Extract tools used
    tools = session_log.get("tools_used", [])
    if tools:
        facts.append(
            SessionFact(
                key="tools_used",
                value=", ".join(str(t) for t in tools),
                session_id=session_id,
                confidence=0.9,
            )
        )

    # Extract outcome
    outcome = session_log.get("outcome", "")
    if isinstance(outcome, str) and outcome.strip():
        facts.append(
            SessionFact(
                key="outcome",
                value=outcome.strip(),
                session_id=session_id,
                confidence=0.8,
            )
        )

    return facts


def decay_unverified_memories(
    accessed_memories: list[str],
    verified_memories: list[str] | None = None,
) -> list[tuple[str, float]]:
    """Reduce confidence for memories accessed but not verified this session.

    Args:
        accessed_memories: Memory IDs accessed during the session.
        verified_memories: Memory IDs that were verified during the session.

    Returns:
        List of (memory_id, penalty_amount) tuples for decayed memories.
    """
    verified_set = set(verified_memories or [])
    decayed: list[tuple[str, float]] = []

    for memory_id in accessed_memories:
        if not memory_id:
            continue
        if memory_id not in verified_set:
            decayed.append((memory_id, DECAY_PENALTY))
    return decayed


def run_reflection(
    session_log: dict[str, Any],
    session_id: str,
) -> ReflectionResult:
    """Execute a full reflection pass on a session log.

    Orchestrates all four reflection steps:
    1. Reinforce memories with successful outcomes.
    2. Generate skill candidates from failures.
    3. Extract novel facts.
    4. Decay unverified memories.

    Args:
        session_log: Parsed session log dictionary.
        session_id: Session identifier.

    Returns:
        ReflectionResult summarizing all actions taken.
    """
    accessed = session_log.get("accessed_memories", [])
    successes = session_log.get("successes", [])
    failures = session_log.get("failures", [])
    verified = session_log.get("verified_memories", [])

    reinforced = reinforce_memories(accessed, successes)
    candidates = generate_skill_candidates(failures, session_id)
    facts = extract_session_facts(session_log, session_id)
    decayed = decay_unverified_memories(accessed, verified)

    return ReflectionResult(
        reinforced_count=len(reinforced),
        skill_candidates=candidates,
        facts_captured=facts,
        decayed_count=len(decayed),
    )


def save_skill_candidates(
    candidates: list[SkillCandidate],
    output_dir: Path,
) -> list[Path]:
    """Save skill candidates to the governance staging directory.

    Each candidate is written as a JSON file. These are NOT auto-promoted
    to .claude/skills/. Human review is required.

    Args:
        candidates: Skill candidates to save.
        output_dir: Directory to write candidate files.

    Returns:
        List of paths to saved candidate files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    for candidate in candidates:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        filename = f"{timestamp}-{candidate.name}.json"
        filepath = output_dir / filename
        filepath.write_text(
            json.dumps(candidate.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
        saved.append(filepath)

    return saved


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for running reflection on a session log file.

    Args:
        argv: Command-line arguments. First argument is the session log path.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: reflection.py <session-log-path>", file=sys.stderr)
        return 1

    session_path = Path(args[0])
    if not session_path.is_file():
        print(f"Session log not found: {session_path}", file=sys.stderr)
        return 1

    try:
        session_log = json.loads(session_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Failed to read session log: {exc}", file=sys.stderr)
        return 1

    session_id = session_log.get("session_id", session_path.stem)
    result = run_reflection(session_log, session_id)

    # Save skill candidates if any
    if result.skill_candidates:
        project_root = _find_project_root(session_path)
        candidates_dir = project_root / ".agents" / "governance" / "skill-candidates"
        saved = save_skill_candidates(result.skill_candidates, candidates_dir)
        for path in saved:
            _logger.info("Saved skill candidate: %s", path)

    print(
        f"Reflection: {len(result.skill_candidates)} skill candidates, "
        f"{len(result.facts_captured)} facts captured, "
        f"{result.reinforced_count} reinforced, "
        f"{result.decayed_count} decayed",
        file=sys.stderr,
    )
    return 0


def _find_project_root(start: Path) -> Path:
    """Walk up from start to find the project root (directory containing .git)."""
    current = start.resolve()
    if current.is_file():
        current = current.parent
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return Path.cwd()


if __name__ == "__main__":
    sys.exit(main())
