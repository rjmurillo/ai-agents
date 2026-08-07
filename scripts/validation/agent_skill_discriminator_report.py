"""Human-readable reporting for check_agent_skill_discriminator.py."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class ScoreLike(Protocol):
    """Fields the report needs from an agent score."""

    name: str
    c1: bool
    c2: bool
    c3: bool
    score: int
    is_candidate: bool
    pipeline_count: int
    isolation_required: bool


class ResultLike(Protocol):
    """Fields the report needs from a check result."""

    scores: Sequence[ScoreLike]
    override_rationale: str | None

    @property
    def failing(self) -> Sequence[ScoreLike]: ...


def criteria_str(score: ScoreLike) -> str:
    """Return the compact criteria string for one score."""
    parts = [
        f"c1={'Y' if score.c1 else 'n'}",
        f"c2={'Y' if score.c2 else 'n'}",
        f"c3={'Y' if score.c3 else 'n'}",
    ]
    return " ".join(parts)


def print_report(
    result: ResultLike,
    audit_path: str,
    adr_path: str,
    *,
    enforce_candidates: bool = True,
) -> None:
    """Print a human-readable summary of the scoring."""
    print("Agent-skill discriminator check (Issue #2008)")
    print("=" * 60)

    if not result.scores:
        print("No changed agent definitions to score.")
        return

    for score in result.scores:
        status = "CANDIDATE" if score.is_candidate else "ok"
        print(
            f"  [{status}] {score.name} "
            f"(score {score.score}/3: {criteria_str(score)}, "
            f"pipelines={score.pipeline_count}, "
            f"isolation_required={'yes' if score.isolation_required else 'no'})"
        )

    if result.override_rationale:
        print()
        print(f"PR override present: {result.override_rationale}")

    failing = result.failing
    print()
    if not enforce_candidates:
        print("Full-corpus mode: candidates are checked against the baseline below.")
        return
    if not failing:
        print("PASS: no agent fails the discriminator.")
        return

    print("FAIL: the following agents are skill-shape candidates (score 2+):")
    for score in failing:
        print(f"  - {score.name} ({criteria_str(score)})")
    print()
    print("Each candidate must either:")
    print("  1. Be refactored into a skill before merge, or")
    print("  2. Add 'isolation_required: true' (with a one-line rationale) to")
    print("     the agent frontmatter, or")
    print("  3. Carry the PR-description token")
    print("     '[skill-discriminator: <rationale>]' for a one-off override.")
    print()
    print(f"See {audit_path}")
    print(f"and {adr_path}")
