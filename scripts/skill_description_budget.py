#!/usr/bin/env python3
"""Corpus-wide skill-description budget instrument (issue #2794).

`validate-skill.py` gates each skill's `description` individually (<=1024 chars,
ADR-040), but nothing measures the aggregate. Every skill `description` is
resident in context on every invocation, before any task work begins, so the sum
is a standing token cost the per-skill validator cannot see by construction.

This script sums the `description` frontmatter across `.claude/skills/*/SKILL.md`,
reports the total chars and an estimated token count, lists the top offenders,
and (optionally) fails when the corpus exceeds a budget so the standing cost gets
a signal when it grows. It is the skill-description sibling of
`memory/scripts/count_memory_tokens.py`.

Token estimate: chars / 4, the heuristic the issue itself used to report
"17,109 chars (~4,277 est. tokens)". No tiktoken dependency: the instrument must
run in bare CI with no extra install, and a 4-chars-per-token estimate is good
enough to trend the aggregate and gate growth.

Exit codes (AGENTS.md): 0 ok (and within budget if one is set), 1 over budget,
2 config (bad root / no skills found).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

EXIT_OK = 0
EXIT_OVER_BUDGET = 1
EXIT_CONFIG = 2

_CHARS_PER_TOKEN = 4
_FRONTMATTER_DELIM = "---"


def estimate_tokens(chars: int) -> int:
    """Estimate tokens from a character count (4 chars/token, rounded up)."""
    return math.ceil(chars / _CHARS_PER_TOKEN)


def extract_frontmatter(text: str) -> dict[str, object] | None:
    """Parse the leading `---`-fenced YAML frontmatter block of a SKILL.md.

    Returns the parsed mapping, or None when the file has no frontmatter or the
    block does not parse to a mapping. A malformed block is a skip, not a crash:
    the instrument degrades gracefully over a corpus it does not control.
    """
    if not text.startswith(_FRONTMATTER_DELIM):
        return None
    lines = text.splitlines()
    # Find the closing delimiter after the opening one on line 0.
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == _FRONTMATTER_DELIM:
            end = index
            break
    if end is None:
        return None
    block = "\n".join(lines[1:end])
    try:
        parsed = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    return parsed if isinstance(parsed, dict) else None


@dataclass(frozen=True)
class SkillDescription:
    """One skill's description footprint."""

    name: str
    chars: int

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.chars)


def measure_skill(skill_md: Path) -> SkillDescription | None:
    """Measure one SKILL.md. None when it has no usable `description`.

    The skill name comes from the frontmatter `name` when present, else the
    skill directory name, so a skill with a malformed `name` still reports under
    a stable key.
    """
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return None
    frontmatter = extract_frontmatter(text)
    if frontmatter is None:
        return None
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description:
        return None
    name = frontmatter.get("name")
    name_str = name if isinstance(name, str) and name else skill_md.parent.name
    return SkillDescription(name=name_str, chars=len(description))


@dataclass
class BudgetReport:
    """Aggregate footprint across the skill corpus."""

    skills: list[SkillDescription]
    skills_without_description: int

    @property
    def count(self) -> int:
        return len(self.skills)

    @property
    def total_chars(self) -> int:
        return sum(s.chars for s in self.skills)

    @property
    def total_tokens(self) -> int:
        return estimate_tokens(self.total_chars)

    def top(self, n: int) -> list[SkillDescription]:
        return sorted(self.skills, key=lambda s: (-s.chars, s.name))[:n]


def measure_corpus(root: Path) -> BudgetReport:
    """Measure every `<root>/*/SKILL.md`. Sorted, deterministic output."""
    skills: list[SkillDescription] = []
    without = 0
    for skill_md in sorted(root.glob("*/SKILL.md")):
        measured = measure_skill(skill_md)
        if measured is None:
            without += 1
        else:
            skills.append(measured)
    return BudgetReport(skills=skills, skills_without_description=without)


def to_json(report: BudgetReport, *, top: int) -> dict[str, object]:
    return {
        "skills": report.count,
        "skills_without_description": report.skills_without_description,
        "total_chars": report.total_chars,
        "total_tokens_est": report.total_tokens,
        "chars_per_token": _CHARS_PER_TOKEN,
        "top": [
            {"name": s.name, "chars": s.chars, "tokens_est": s.tokens}
            for s in report.top(top)
        ],
    }


def to_human(report: BudgetReport, *, top: int) -> str:
    lines = [
        f"Skill description budget: {report.count} skill(s), "
        f"{report.total_chars} chars (~{report.total_tokens} est. tokens "
        f"at {_CHARS_PER_TOKEN} chars/token)",
    ]
    if report.skills_without_description:
        lines.append(
            f"  {report.skills_without_description} skill(s) had no parseable "
            f"description (skipped)"
        )
    if report.skills:
        lines.append(f"Top {min(top, report.count)} by description length:")
        for s in report.top(top):
            lines.append(f"  {s.chars:>5} chars (~{s.tokens:>4} tok)  {s.name}")
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure the aggregate skill-description footprint and optionally "
            "gate it against a budget (issue #2794)."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(".claude/skills"),
        help="Directory of skill subdirs each holding SKILL.md (default: .claude/skills).",
    )
    parser.add_argument(
        "--top", type=int, default=10, help="How many offenders to list (default: 10)."
    )
    parser.add_argument(
        "--max-total-chars",
        type=int,
        default=None,
        help="Fail (exit 1) when the corpus exceeds this many description chars.",
    )
    parser.add_argument(
        "--max-total-tokens",
        type=int,
        default=None,
        help="Fail (exit 1) when the estimated corpus tokens exceed this.",
    )
    parser.add_argument(
        "--output-format",
        choices=("human", "json"),
        default="human",
        help="Render as a table (human) or JSON (default: human).",
    )
    return parser.parse_args(argv)


def _over_budget(report: BudgetReport, args: argparse.Namespace) -> str | None:
    """Return a human reason when a budget is set and exceeded, else None."""
    if args.max_total_chars is not None and report.total_chars > args.max_total_chars:
        return (
            f"corpus is {report.total_chars} chars, over the "
            f"{args.max_total_chars}-char budget"
        )
    if args.max_total_tokens is not None and report.total_tokens > args.max_total_tokens:
        return (
            f"corpus is ~{report.total_tokens} est. tokens, over the "
            f"{args.max_total_tokens}-token budget"
        )
    return None


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if not args.root.is_dir():
        print(f"error: --root {args.root} is not a directory", file=sys.stderr)
        return EXIT_CONFIG
    if args.top < 0:
        print(f"error: --top must be non-negative, got {args.top}", file=sys.stderr)
        return EXIT_CONFIG

    report = measure_corpus(args.root)
    if report.count == 0:
        print(f"error: no skills with a description under {args.root}", file=sys.stderr)
        return EXIT_CONFIG

    if args.output_format == "json":
        print(json.dumps(to_json(report, top=args.top), indent=2, sort_keys=True))
    else:
        print(to_human(report, top=args.top))

    reason = _over_budget(report, args)
    if reason is not None:
        print(f"OVER BUDGET: {reason}", file=sys.stderr)
        return EXIT_OVER_BUDGET
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
