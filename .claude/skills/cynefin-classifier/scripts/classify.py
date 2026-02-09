#!/usr/bin/env python3
"""Cynefin Framework Problem Classifier.

Classifies problems into Cynefin domains based on cause-effect characteristics
and recommends appropriate response strategies.

Exit Codes:
    0: Classification complete
    1: Invalid arguments
    2: Insufficient information (Confusion domain)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from enum import Enum


class Domain(Enum):
    """Cynefin framework domains."""

    CLEAR = "Clear"
    COMPLICATED = "Complicated"
    COMPLEX = "Complex"
    CHAOTIC = "Chaotic"
    CONFUSION = "Confusion"


class Confidence(Enum):
    """Classification confidence levels."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class DomainIndicators:
    """Indicators for each Cynefin domain."""

    clear_indicators: list[str] = field(default_factory=list)
    complicated_indicators: list[str] = field(default_factory=list)
    complex_indicators: list[str] = field(default_factory=list)
    chaotic_indicators: list[str] = field(default_factory=list)
    confusion_indicators: list[str] = field(default_factory=list)


@dataclass
class ClassificationResult:
    """Result of Cynefin classification."""

    problem: str
    domain: Domain
    confidence: Confidence
    rationale: str
    strategy: str
    actions: list[str]
    pitfall: str
    temporal_note: str | None = None
    boundary_note: str | None = None
    compound_note: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "problem": self.problem,
            "domain": self.domain.value,
            "confidence": self.confidence.value,
            "rationale": self.rationale,
            "strategy": self.strategy,
            "actions": self.actions,
            "pitfall": self.pitfall,
            "temporal_note": self.temporal_note,
            "boundary_note": self.boundary_note,
            "compound_note": self.compound_note,
        }

    def to_markdown(self) -> str:
        """Format as markdown output."""
        lines = [
            "## Cynefin Classification",
            "",
            f"**Problem**: {self.problem}",
            "",
            f"### Domain: {self.domain.value.upper()}",
            "",
            f"**Confidence**: {self.confidence.value}",
            "",
            "### Rationale",
            "",
            self.rationale,
            "",
            "### Response Strategy",
            "",
            f"**Approach**: {self.strategy}",
            "",
            "### Recommended Actions",
            "",
        ]
        for i, action in enumerate(self.actions, 1):
            lines.append(f"{i}. {action}")
        lines.extend(
            [
                "",
                "### Pitfall Warning",
                "",
                self.pitfall,
                "",
                "### Related Considerations",
                "",
            ]
        )
        if self.temporal_note:
            lines.append(f"- **Temporal**: {self.temporal_note}")
        if self.boundary_note:
            lines.append(f"- **Boundary**: {self.boundary_note}")
        if self.compound_note:
            lines.append(f"- **Compound**: {self.compound_note}")
        return "\n".join(lines)


# Domain-specific response strategies
STRATEGIES = {
    Domain.CLEAR: "Sense-Categorize-Respond",
    Domain.COMPLICATED: "Sense-Analyze-Respond",
    Domain.COMPLEX: "Probe-Sense-Respond",
    Domain.CHAOTIC: "Act-Sense-Respond",
    Domain.CONFUSION: "Gather Information",
}

# Domain-specific pitfalls
PITFALLS = {
    Domain.CLEAR: (
        "Over-complicating simple problems. "
        "Creating abstractions where none needed."
    ),
    Domain.COMPLICATED: (
        "Analysis paralysis OR acting without sufficient expertise. "
        "Balance thoroughness with timely action."
    ),
    Domain.COMPLEX: (
        "Trying to fully analyze before acting. "
        "Expecting predictable outcomes from experiments."
    ),
    Domain.CHAOTIC: (
        "Forming committees. Waiting for consensus. "
        "Deep analysis during active crisis."
    ),
    Domain.CONFUSION: (
        "Assuming a domain without evidence. "
        "Acting before gathering sufficient information."
    ),
}

# Keywords that suggest specific domains
DOMAIN_KEYWORDS = {
    Domain.CLEAR: [
        "typo",
        "simple fix",
        "known issue",
        "documented",
        "standard",
        "obvious",
        "trivial",
        "best practice",
        "procedure exists",
        "follow guideline",
    ],
    Domain.COMPLICATED: [
        "analyze",
        "expert",
        "root cause",
        "investigate",
        "debug",
        "profile",
        "evaluate options",
        "trade-off",
        "assessment",
        "audit",
        "memory leak",
        "performance",
    ],
    Domain.COMPLEX: [
        "unpredictable",
        "user behavior",
        "team dynamics",
        "experiment",
        "try and see",
        "emergent",
        "multiple factors",
        "new technology",
        "architecture decision",
        "adoption",
        "a/b test",
        "flaky",
        "intermittent",
        "randomly",
        "sometimes works",
        "race condition",
        "timing",
        "works locally",
        "fails in ci",
        "non-deterministic",
    ],
    Domain.CHAOTIC: [
        "outage",
        "down",
        "crisis",
        "breach",
        "urgent",
        "emergency",
        "critical",
        "immediate",
        "customers affected",
        "data loss",
        "unresponsive",
    ],
    Domain.CONFUSION: [
        "unclear",
        "vague",
        "sometimes",
        "intermittent",
        "not sure",
        "depends",
        "more information",
        "reproduce",
        "inconsistent",
    ],
}


def count_keyword_matches(text: str, domain: Domain) -> int:
    """Count keyword matches for a domain."""
    text_lower = text.lower()
    return sum(1 for kw in DOMAIN_KEYWORDS[domain] if kw in text_lower)


def classify_problem(
    problem: str, context: str | None = None
) -> ClassificationResult:
    """Classify a problem into a Cynefin domain.

    Args:
        problem: Description of the problem
        context: Additional context about constraints, environment

    Returns:
        ClassificationResult with domain, strategy, and recommendations
    """
    combined_text = problem
    if context:
        combined_text = f"{problem} {context}"

    # Count keyword matches for each domain
    scores = {
        domain: count_keyword_matches(combined_text, domain) for domain in Domain
    }

    # Find domain with highest score
    max_score = max(scores.values())
    if max_score == 0:
        # No strong indicators, default to Confusion
        domain = Domain.CONFUSION
        confidence = Confidence.LOW
        rationale = (
            "No clear indicators for any specific domain. "
            "Insufficient information to classify confidently."
        )
    else:
        # Get domains with max score (could be tie)
        top_domains = [d for d, s in scores.items() if s == max_score]

        if len(top_domains) > 1:
            # Tie between domains
            domain = Domain.CONFUSION
            confidence = Confidence.LOW
            rationale = (
                f"Mixed signals between {', '.join(d.value for d in top_domains)}. "
                "Need more information to disambiguate."
            )
        else:
            domain = top_domains[0]
            # Confidence based on match strength
            if max_score >= 3:
                confidence = Confidence.HIGH
            elif max_score >= 2:
                confidence = Confidence.MEDIUM
            else:
                confidence = Confidence.LOW

            rationale = _generate_rationale(domain, combined_text)

    # Generate domain-specific actions
    actions = _generate_actions(domain, problem)

    return ClassificationResult(
        problem=problem,
        domain=domain,
        confidence=confidence,
        rationale=rationale,
        strategy=STRATEGIES[domain],
        actions=actions,
        pitfall=PITFALLS[domain],
        temporal_note=_generate_temporal_note(domain),
        boundary_note=_generate_boundary_note(domain, scores),
        compound_note=None,  # Would require deeper analysis
    )


def _generate_rationale(domain: Domain, text: str) -> str:
    """Generate rationale for domain classification."""
    rationales = {
        Domain.CLEAR: (
            "Cause-effect relationships are clear. "
            "Standard procedures or best practices apply. "
            "Predictable outcome with established approach."
        ),
        Domain.COMPLICATED: (
            "Cause-effect relationships are discoverable through expert analysis. "
            "The problem has knowable solution but requires systematic investigation."
        ),
        Domain.COMPLEX: (
            "Multiple interacting factors make cause-effect unclear upfront. "
            "Outcomes are emergent and only visible in retrospect. "
            "Experimentation required to find patterns."
        ),
        Domain.CHAOTIC: (
            "Crisis situation with active harm occurring. "
            "No time for analysis. Immediate stabilization required. "
            "Act first, analyze later."
        ),
        Domain.CONFUSION: (
            "Insufficient information to determine domain. "
            "Need more data before choosing an approach."
        ),
    }
    return rationales[domain]


def _generate_actions(domain: Domain, problem: str) -> list[str]:
    """Generate recommended actions for domain."""
    actions = {
        Domain.CLEAR: [
            "Identify the established best practice or procedure",
            "Apply the standard solution",
            "Document if this is a recurring pattern",
        ],
        Domain.COMPLICATED: [
            "Gather relevant data and metrics",
            "Consult domain experts or documentation",
            "Analyze systematically using proven techniques",
            "Implement solution based on analysis findings",
        ],
        Domain.COMPLEX: [
            "Design safe-to-fail experiments with clear success criteria",
            "Run small probes to gather empirical data",
            "Observe patterns and amplify what works",
            "Iterate based on emerging insights",
        ],
        Domain.CHAOTIC: [
            "Execute immediate stabilization actions",
            "Restore basic functionality first",
            "Communicate status to stakeholders",
            "After stable: investigate root cause",
        ],
        Domain.CONFUSION: [
            "List specific unknowns that block classification",
            "Gather minimum viable information",
            "Decompose into smaller sub-problems if possible",
            "Re-classify once information is available",
        ],
    }
    return actions[domain]


def _generate_temporal_note(domain: Domain) -> str:
    """Generate note about temporal domain transitions."""
    notes = {
        Domain.CLEAR: "May shift to Complex/Chaotic if disrupted by unexpected change.",
        Domain.COMPLICATED: (
            "May simplify to Clear as expertise is codified, "
            "or shift to Complex if analysis reveals emergent factors."
        ),
        Domain.COMPLEX: (
            "May shift to Complicated once patterns emerge, "
            "or to Chaotic if situation destabilizes."
        ),
        Domain.CHAOTIC: (
            "Should transition to Complex after stabilization. "
            "Do not linger in Chaotic."
        ),
        Domain.CONFUSION: (
            "Temporary state. Should resolve to another domain "
            "once information is gathered."
        ),
    }
    return notes[domain]


def _generate_boundary_note(domain: Domain, scores: dict[Domain, int]) -> str | None:
    """Generate note if problem is near domain boundary."""
    max_score = max(scores.values())
    if max_score == 0:
        return None

    # Check for close scores
    close_domains = [
        d for d, s in scores.items() if s > 0 and s >= max_score - 1 and d != domain
    ]
    if close_domains:
        return (
            f"Near boundary with {', '.join(d.value for d in close_domains)}. "
            "Re-evaluate if initial approach does not yield progress."
        )
    return None


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Classify problems into Cynefin Framework domains"
    )
    parser.add_argument(
        "--problem",
        required=True,
        help="Description of the problem to classify",
    )
    parser.add_argument(
        "--context",
        help="Additional context about constraints, environment",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of markdown",
    )

    args = parser.parse_args()

    if not args.problem.strip():
        print("Error: Problem description cannot be empty", file=sys.stderr)
        return 1

    result = classify_problem(args.problem, args.context)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.to_markdown())

    # Exit code 2 for Confusion domain (insufficient info)
    if result.domain == Domain.CONFUSION:
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
