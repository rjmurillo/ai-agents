#!/usr/bin/env python3
"""Static check that ``.claude/commands/build.md`` wires the required exit gates.

The /build command is the implementer's exit path. Layer 2 of the PR #1887
retrospective (`.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`)
named the failure mode: existing skills (code-qualities-assessment,
taste-lints, doc-accuracy) were invoke-on-demand and not on the exit path,
so review-time bots flagged what they should have caught.

This validator pins the contract: any future edit that drops one of the
three exit gates from ``.claude/commands/build.md`` fails CI before merge,
not after. It is intentionally a small surface area; it does not validate
that the gates *run* (the implementer does that), only that they are
listed as required invocations.

EXIT CODES (`AGENTS.md`, ADR-035):
  0 - All required gates present.
  1 - One or more required gates missing.
  2 - Configuration error (build.md missing or unreadable).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# The three skill invocations the /build command must contain after PR
# `feat/wire-build-gates-1889` lands. Each entry is (skill_name,
# regex_pattern). The regex matches ``Skill(skill="<name>")`` allowing
# optional whitespace around the equals sign and either single or double
# quotes around the skill name. The regex is anchored to the literal
# ``Skill(skill=`` token so a stray mention of the skill name in prose
# does not satisfy the contract.
_REQUIRED_GATES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "code-qualities-assessment",
        re.compile(r"""Skill\(\s*skill\s*=\s*["']code-qualities-assessment["']\s*\)"""),
    ),
    (
        "taste-lints",
        re.compile(r"""Skill\(\s*skill\s*=\s*["']taste-lints["']\s*\)"""),
    ),
    (
        "doc-accuracy",
        re.compile(r"""Skill\(\s*skill\s*=\s*["']doc-accuracy["']\s*\)"""),
    ),
)

# The build.md file must contain a section heading that frames the gates
# as mandatory rather than advisory. Layer 2 of the retrospective is
# explicit: advisory output produced the iteration paradox.
_MANDATORY_SECTION: re.Pattern[str] = re.compile(
    r"^##\s+Mandatory Exit Gates\b", re.MULTILINE
)

_BUILD_MD_RELPATH = Path(".claude/commands/build.md")


@dataclass(frozen=True)
class GateViolation:
    """One missing required item in build.md."""

    kind: str  # "skill" or "section"
    name: str
    message: str


def collect_violations(repo_root: Path) -> list[GateViolation]:
    """Return the list of missing required gates in build.md.

    Empty list means the file passes the contract. This function reads
    ``.claude/commands/build.md`` from ``repo_root`` and applies the
    static checks above. It does not import anything; the caller decides
    how to surface the result.
    """
    build_md = repo_root / _BUILD_MD_RELPATH
    if not build_md.is_file():
        raise FileNotFoundError(f"missing build.md at {build_md}")

    text = build_md.read_text(encoding="utf-8")
    violations: list[GateViolation] = []

    section_match = _MANDATORY_SECTION.search(text)
    if not section_match:
        violations.append(
            GateViolation(
                kind="section",
                name="Mandatory Exit Gates",
                message=(
                    "build.md must contain a '## Mandatory Exit Gates' section. "
                    "The retrospective on PR #1887 documents that advisory framing "
                    "produced the iteration paradox; the heading wording matters."
                ),
            )
        )
        return violations

    mandatory_section_text = text[section_match.start() :]

    for skill_name, pattern in _REQUIRED_GATES:
        if not pattern.search(mandatory_section_text):
            violations.append(
                GateViolation(
                    kind="skill",
                    name=skill_name,
                    message=(
                        f"build.md must invoke Skill(skill=\"{skill_name}\") under the "
                        f"'## Mandatory Exit Gates' section. A mention elsewhere in the "
                        f"file does not satisfy the contract. See "
                        f".agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md "
                        f"Layer 2 for context."
                    ),
                )
            )

    return violations


def _format_violations(violations: list[GateViolation]) -> str:
    lines = ["BUILD GATE VIOLATIONS:"]
    for v in violations:
        lines.append(f"  [{v.kind}] {v.name}: {v.message}")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Static check that /build wires the required exit gates."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root. Defaults to two levels above this script.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    repo_root = args.repo_root or Path(__file__).resolve().parent.parent.parent
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repo root: {repo_root}", file=sys.stderr)
        return 2

    try:
        violations = collect_violations(repo_root)
    except FileNotFoundError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    if violations:
        print(_format_violations(violations))
        return 1

    print(f"[PASS] All required exit gates present in {_BUILD_MD_RELPATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
