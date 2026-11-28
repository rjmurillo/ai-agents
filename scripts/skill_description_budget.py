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

Budget file mode (issue #5762): `--budget-file scripts/skill_description_budget.json`
measures every shipped skill root named in the file (`.claude/skills`,
`src/claude/skills`, `src/copilot-cli/skills`) against that root's
`max_total_chars`, so a description added only to one tree cannot bypass the
gate. The description budgets are a local engineering ratchet set just above the
measured corpus. They are not a measured limit of any model host. Raising one
needs a reviewed reason in the same PR; lowering one is always fine.

Listing chars (PR #7871): the budget file run also measures ListingChars per
root, the sum over skills with a parseable description of
`93 + len(name) + len(description)`. 93 is the Copilot CLI per-entry markup cost
for `<location>project</location>` entries (PR #7871 evidence note, receipt C).
It is the Copilot entry cost only. No Claude Code entry cost or budget is
measured, so none is listed. A root may set `max_listing_chars`, a ceiling that
fails the run (exit 1) when exceeded.

Host budgets (PR #7871): the optional top-level `host_budgets` list records
published or observed host listing budgets, each with `host`, `chars`, `state`,
`source`, and `date`. For each root and each host budget the run reports how many
skills keep a full entry under a name-order model: sort by name, add entries in
order, stop at the first entry that does not fit. That is a model. Copilot fill
order is not determined, so the count is INFERRED and does not gate.

Exit codes (AGENTS.md): 0 ok (and within budget if one is set), 1 over budget,
2 config (bad root / no skills found / bad budget file).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from scripts.hook_utilities.frontmatter_block import load_frontmatter  # noqa: E402
from scripts.skill_description_budget_config import (  # noqa: E402
    BudgetConfig,
    BudgetFileError,
    HostBudget,
    RootBudget,
    load_budget_config,
    load_root_budgets,
)

__all__ = ["BudgetFileError", "RootBudget", "load_root_budgets"]

EXIT_OK = 0
EXIT_OVER_BUDGET = 1
EXIT_CONFIG = 2

_CHARS_PER_TOKEN = 4

# Copilot CLI per-entry markup cost for `<location>project</location>` entries.
COPILOT_ENTRY_MARKUP_CHARS = 93

FIT_MODEL = "name-order, first-miss stop (INFERRED; Copilot fill order not determined)"


def estimate_tokens(chars: int) -> int:
    """Estimate tokens from a character count (4 chars/token, rounded up)."""
    return math.ceil(chars / _CHARS_PER_TOKEN)


def extract_frontmatter(text: str) -> dict[str, object] | None:
    """Parse the leading `---`-fenced YAML frontmatter block of a SKILL.md.

    Returns the parsed mapping, or None when the file has no frontmatter or the
    block does not parse to a mapping. A malformed block is a skip, not a crash:
    the instrument degrades gracefully over a corpus it does not control.

    Uses `scripts/hook_utilities/frontmatter_block.py`, the one shared parser.
    Duplicate keys are last-one-wins, as with `yaml.safe_load`.
    """
    return load_frontmatter(text, yaml, allow_duplicate_keys=True)


@dataclass(frozen=True)
class SkillDescription:
    """One skill's description footprint."""

    name: str
    chars: int

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.chars)

    @property
    def listing_chars(self) -> int:
        """Copilot CLI entry size: markup cost + name + description."""
        return COPILOT_ENTRY_MARKUP_CHARS + len(self.name) + self.chars


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

    @property
    def listing_chars(self) -> int:
        return sum(s.listing_chars for s in self.skills)

    def top(self, n: int) -> list[SkillDescription]:
        return sorted(self.skills, key=lambda s: (-s.chars, s.name))[:n]

    def fit_count(self, budget_chars: int) -> int:
        """Skills keeping a full entry under the name-order, first-miss-stop model.

        Entries are added in name order. The first entry that would push the
        running total past `budget_chars` stops the count, so a later, smaller
        entry is never counted. An entry that lands exactly on the budget fits.
        """
        used = 0
        fitted = 0
        for skill in sorted(self.skills, key=lambda s: s.name):
            used += skill.listing_chars
            if used > budget_chars:
                break
            fitted += 1
        return fitted


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
            {"name": s.name, "chars": s.chars, "tokens_est": s.tokens} for s in report.top(top)
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
            f"  {report.skills_without_description} skill(s) had no parseable description (skipped)"
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
        "--budget-file",
        type=Path,
        default=None,
        help=(
            "JSON file mapping each shipped skill root to its max_total_chars. "
            "Measures every root and fails when any exceeds its budget. "
            "Replaces --root and the --max-total-* flags."
        ),
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
        return f"corpus is {report.total_chars} chars, over the {args.max_total_chars}-char budget"
    if args.max_total_tokens is not None and report.total_tokens > args.max_total_tokens:
        return (
            f"corpus is ~{report.total_tokens} est. tokens, over the "
            f"{args.max_total_tokens}-token budget"
        )
    return None


@dataclass(frozen=True)
class RootResult:
    """One skill root measured against its budget."""

    label: str
    budget: int
    report: BudgetReport
    max_listing_chars: int | None = None
    host_budgets: tuple[HostBudget, ...] = ()

    @property
    def within(self) -> bool:
        return self.report.total_chars <= self.budget

    @property
    def within_listing_ceiling(self) -> bool:
        return self.max_listing_chars is None or self.report.listing_chars <= self.max_listing_chars

    @property
    def passed(self) -> bool:
        return self.within and self.within_listing_ceiling


def _root_to_human(result: RootResult, *, top: int) -> str:
    report = result.report
    status = "OK" if result.passed else "OVER BUDGET"
    lines = [
        f"[{status}] {result.label}: {report.count} skill(s), {report.total_chars} chars "
        f"(~{report.total_tokens} est. tokens), budget {result.budget} chars "
        f"(~{estimate_tokens(result.budget)} est. tokens)",
    ]
    ceiling = "none" if result.max_listing_chars is None else str(result.max_listing_chars)
    lines.append(f"  listing: {report.listing_chars} chars, ceiling {ceiling}")
    if result.max_listing_chars is not None and not result.within_listing_ceiling:
        lines.append(
            f"  listing over ceiling by {report.listing_chars - result.max_listing_chars} chars"
        )
    for host in result.host_budgets:
        lines.append(
            f"  fit [{host.state}] {host.host} {host.chars}: "
            f"{report.fit_count(host.chars)} of {report.count} skills keep a full entry "
            f"(model: {FIT_MODEL})"
        )
    if not result.within:
        lines.append(f"  over by {report.total_chars - result.budget} chars; largest contributors:")
        lines.extend(f"    {s.chars:>5} chars  {s.name}" for s in report.top(top))
    return "\n".join(lines)


def _root_to_json(result: RootResult, *, top: int) -> dict[str, object]:
    payload = to_json(result.report, top=top)
    payload.update(
        root=result.label,
        budget_chars=result.budget,
        budget_tokens_est=estimate_tokens(result.budget),
        within_budget=result.within,
        listing_chars=result.report.listing_chars,
        max_listing_chars=result.max_listing_chars,
        within_listing_ceiling=result.within_listing_ceiling,
        host_fit=[
            {
                "host": h.host,
                "chars": h.chars,
                "state": h.state,
                "source": h.source,
                "date": h.date,
                "fit_count": result.report.fit_count(h.chars),
                "skills": result.report.count,
                "fit_model": FIT_MODEL,
            }
            for h in result.host_budgets
        ],
    )
    return payload


def _measure_roots(config: BudgetConfig) -> list[RootResult]:
    """Measure every root, or raise BudgetFileError when a root has no described skills."""
    results: list[RootResult] = []
    for label, limits in config.roots.items():
        root = _REPO_ROOT / label
        if not root.is_dir():
            raise BudgetFileError(f"budget root {label} is not a directory at {root}")
        report = measure_corpus(root)
        if report.count == 0:
            raise BudgetFileError(f"budget root {label} has no skills with a description")
        results.append(
            RootResult(
                label=label,
                budget=limits.max_total_chars,
                report=report,
                max_listing_chars=limits.max_listing_chars,
                host_budgets=config.host_budgets,
            )
        )
    return results


def run_budget_file(path: Path, *, top: int, output_format: str = "human") -> int:
    """Gate every root in a budget file. Relative roots resolve against the repo root."""
    try:
        results = _measure_roots(load_budget_config(path))
    except BudgetFileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    failed = any(not r.passed for r in results)
    if output_format == "json":
        print(json.dumps([_root_to_json(r, top=top) for r in results], indent=2, sort_keys=True))
    else:
        for r in results:
            print(_root_to_human(r, top=top), file=sys.stdout if r.passed else sys.stderr)
    return EXIT_OVER_BUDGET if failed else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.top < 0:
        print(f"error: --top must be non-negative, got {args.top}", file=sys.stderr)
        return EXIT_CONFIG
    if args.budget_file is not None:
        return run_budget_file(args.budget_file, top=args.top, output_format=args.output_format)
    if not args.root.is_dir():
        print(f"error: --root {args.root} is not a directory", file=sys.stderr)
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
