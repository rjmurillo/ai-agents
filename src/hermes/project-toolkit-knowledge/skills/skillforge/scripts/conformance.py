#!/usr/bin/env python3
"""Check skills against the agentskills.io specification and guides.

Every rule in the catalog has an id, a level (MUST, SHOULD, MAY) taken from the
source page's wording, and the URL of the section it comes from. Rules a
script can check run as static checks; the rest are listed for human review.
No code from the checked skill runs.

Usage:
    conformance.py SKILL_DIR [SKILL_DIR ...] [--root DIR] [--profile spec|project]
                   [--waive RULE_ID ...] [--strict] [--format text|json]
                   [--verbose] [--manual]
    conformance.py --list [--profile spec|project] [--format text|json]

Statuses:
    PASS            the check found nothing
    FAIL            a MUST rule failed
    WARN            a SHOULD or MAY rule failed
    DEVIATION       the rule failed, and the project profile declares why
    WAIVED          the rule failed, and --waive named it
    NOT_APPLICABLE  the skill has nothing this rule checks
    NOT_EVALUATED   the check could not decide, such as unparsable frontmatter
    MANUAL          a guideline no script can judge; review it by hand

Exit codes:
    0  no FAIL, and no NOT_EVALUATED on a MUST rule
    1  a FAIL, or a MUST rule NOT_EVALUATED; with --strict, also any WARN or
       NOT_EVALUATED
    2  usage error: bad flag, unknown --waive id, or a path that is missing,
       not a directory, or outside --root
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _conformance_checks import NotApplicableError, NotEvaluatedError
from _conformance_guides import GUIDE_RULES
from _conformance_parse import load_skill
from _conformance_rules import SPEC_RULES, Rule
from _path_guard import contained_realpath, resolve_root

RULES: tuple[Rule, ...] = SPEC_RULES + GUIDE_RULES
RULES_BY_ID = {rule.id: rule for rule in RULES}

STATUS_ORDER = (
    "FAIL",
    "NOT_EVALUATED",
    "WARN",
    "DEVIATION",
    "WAIVED",
    "PASS",
    "NOT_APPLICABLE",
    "MANUAL",
)


@dataclass
class Result:
    rule: Rule
    status: str
    problems: list[str] = field(default_factory=list)
    reason: str = ""

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.rule.id,
            "level": self.rule.level,
            "status": self.status,
            "source": self.rule.source,
            "summary": self.rule.summary,
            "problems": self.problems,
            "reason": self.reason,
        }


@dataclass
class Report:
    path: str
    results: list[Result]
    notes: list[str]

    def to_json(self) -> dict[str, object]:
        return {
            "path": self.path,
            "notes": self.notes,
            "counts": counts(self.results),
            "results": [result.to_json() for result in self.results],
        }


def evaluate(directory: Path, profile: str, waived: set[str]) -> tuple[list[Result], list[str]]:
    """Run every rule against one skill directory."""
    doc = load_skill(directory)
    results: list[Result] = []
    for rule in RULES:
        if rule.check is None:
            reason = rule.deviation if profile == "project" and rule.deviation else ""
            results.append(Result(rule, "MANUAL", reason=reason))
            continue
        try:
            problems = rule.check(doc)
        except NotApplicableError as exc:
            results.append(Result(rule, "NOT_APPLICABLE", reason=str(exc)))
            continue
        except NotEvaluatedError as exc:
            results.append(Result(rule, "NOT_EVALUATED", reason=str(exc)))
            continue
        if not problems:
            results.append(Result(rule, "PASS"))
        elif rule.id in waived:
            results.append(Result(rule, "WAIVED", problems, "waived with --waive"))
        elif profile == "project" and rule.deviation:
            results.append(Result(rule, "DEVIATION", problems, rule.deviation))
        else:
            results.append(Result(rule, "FAIL" if rule.level == "MUST" else "WARN", problems))
    return results, doc.notes


def failed(results: list[Result], strict: bool) -> bool:
    for result in results:
        if result.status == "FAIL":
            return True
        if result.status == "NOT_EVALUATED" and (strict or result.rule.level == "MUST"):
            return True
        if strict and result.status == "WARN":
            return True
    return False


def counts(results: list[Result]) -> dict[str, int]:
    tally = dict.fromkeys(STATUS_ORDER, 0)
    for result in results:
        tally[result.status] += 1
    return tally


def _display(path: Path) -> str:
    try:
        return os.path.relpath(path)
    except ValueError:
        return str(path)


def render_text(reports: list[Report], profile: str, verbose: bool, manual: bool) -> str:
    lines: list[str] = []
    width = max(len(rule.id) for rule in RULES)
    for report in reports:
        results = report.results
        lines.append(f"agentskills.io conformance: {report.path} (profile: {profile})")
        for note in report.notes:
            lines.append(f"  note: {note}")
        hidden = {"PASS", "NOT_APPLICABLE", "MANUAL"} if not verbose else {"MANUAL"}
        if manual:
            hidden.discard("MANUAL")
        for result in sorted(results, key=lambda r: STATUS_ORDER.index(r.status)):
            if result.status in hidden:
                continue
            text = result.rule.summary if result.status in ("PASS", "MANUAL") else ""
            lines.append(
                f"  {result.status:<14} {result.rule.level:<6} {result.rule.id:<{width}} {text}".rstrip()
            )
            for problem in result.problems:
                lines.append(f"      {problem}")
            if result.reason:
                lines.append(f"      reason: {result.reason}")
            if result.status in ("FAIL", "WARN", "MANUAL"):
                lines.append(f"      source: {result.rule.source}")
        tally = counts(results)
        summary = ", ".join(
            f"{tally[s]} {s.lower().replace('_', ' ')}" for s in STATUS_ORDER if tally[s]
        )
        lines.append(f"  {summary}")
        if tally["MANUAL"] and not manual:
            lines.append(
                f"  {tally['MANUAL']} guideline items need human review; rerun with --manual to list them."
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_catalog(profile: str, fmt: str) -> str:
    if fmt == "json":
        rows = [
            {
                "id": rule.id,
                "level": rule.level,
                "kind": "manual" if rule.manual else "automated",
                "source": rule.source,
                "summary": rule.summary,
                "deviation": rule.deviation if profile == "project" else None,
            }
            for rule in RULES
        ]
        return json.dumps({"profile": profile, "rules": rows}, indent=2) + "\n"
    width = max(len(rule.id) for rule in RULES)
    lines = [f"agentskills.io conformance catalog ({len(RULES)} rules, profile: {profile})"]
    for rule in RULES:
        kind = "manual" if rule.manual else "auto"
        lines.append(f"{rule.level:<6} {kind:<6} {rule.id:<{width}} {rule.summary}")
        lines.append(f"{'':<14}{rule.source}")
        if profile == "project" and rule.deviation:
            lines.append(f"{'':<14}deviation: {rule.deviation}")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="conformance.py",
        description=__doc__.split("\n\n", 1)[0],
        epilog="Statuses and exit codes: see the module docstring, or SKILL.md's reference.",
    )
    parser.add_argument("skills", nargs="*", metavar="SKILL_DIR", help="skill directory to check")
    parser.add_argument("--root", help="every SKILL_DIR must resolve inside DIR (default: cwd)")
    parser.add_argument(
        "--profile",
        choices=("spec", "project"),
        default="spec",
        help="spec: pure agentskills.io; project: report declared deviations as DEVIATION",
    )
    parser.add_argument(
        "--waive", action="append", default=[], metavar="RULE_ID", help="report this rule as WAIVED"
    )
    parser.add_argument("--strict", action="store_true", help="also fail on WARN and NOT_EVALUATED")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--verbose", action="store_true", help="also print PASS and NOT_APPLICABLE rows"
    )
    parser.add_argument(
        "--manual", action="store_true", help="also print the guidelines that need human review"
    )
    parser.add_argument("--list", action="store_true", help="print the rule catalog and exit")
    return parser


def resolve_skills(
    parser: argparse.ArgumentParser, raw_paths: list[str], root_arg: str | None
) -> list[Path]:
    """Return the real path of each SKILL_DIR, or exit 2 through parser.error."""
    if not raw_paths:
        parser.error("give at least one SKILL_DIR, or --list")
    if root_arg is not None and not Path(root_arg).is_dir():
        parser.error(f"--root is not a directory: {root_arg}")
    root = resolve_root(root_arg)
    directories: list[Path] = []
    for raw in raw_paths:
        if not Path(raw).is_dir():
            parser.error(f"not a directory: {raw}")
        real = contained_realpath(Path(raw), root)
        if real is None:
            parser.error(f"{raw} resolves outside the root {root}; pass --root")
        directories.append(Path(real))
    return directories


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    unknown = sorted(set(args.waive) - set(RULES_BY_ID))
    if unknown:
        parser.error(f"unknown rule id for --waive: {', '.join(unknown)} (see --list)")
    if args.list:
        sys.stdout.write(render_catalog(args.profile, args.format))
        return 0
    directories = resolve_skills(parser, args.skills, args.root)
    reports = []
    for raw, directory in zip(args.skills, directories, strict=True):
        results, notes = evaluate(directory, args.profile, set(args.waive))
        reports.append(Report(_display(Path(raw)), results, notes))
    exit_code = 1 if any(failed(report.results, args.strict) for report in reports) else 0
    if args.format == "json":
        payload = {
            "profile": args.profile,
            "strict": args.strict,
            "exit_code": exit_code,
            "skills": [report.to_json() for report in reports],
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        sys.stdout.write(render_text(reports, args.profile, args.verbose, args.manual))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
