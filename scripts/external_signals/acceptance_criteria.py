#!/usr/bin/env python3
"""Mechanically extract acceptance-criteria checkboxes from a PR/issue body.

This is the externally-grounded signal that ``ai-spec-validation.yml`` should
gate on (issue #1855). The LLM critic may still annotate *why* a criterion is
unmet, but the pass/fail decision is determined here:

* Parse Markdown task-list items under an "Acceptance" / "Acceptance Criteria"
  heading.
* Optionally grep the PR diff for keyword evidence of each criterion.
* Emit a JSON report plus a non-zero exit code when required criteria are
  missing or unchecked.

Exit codes follow ADR-035:

* 0 - success (all required criteria satisfied, or none declared)
* 1 - logic error: declared criteria are missing/unchecked
* 2 - config error: bad arguments / unreadable input

The tool is intentionally dumb: no model calls, no network, deterministic on
its inputs. That is the point.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

_ACCEPTANCE_HEADING = re.compile(
    r"^#{1,6}\s*acceptance(?:\s+criteria)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_NEXT_HEADING = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)
_CHECKBOX = re.compile(r"^\s*[-*]\s*\[(?P<mark>[ xX])\]\s+(?P<text>.+?)\s*$")


@dataclass(frozen=True)
class Criterion:
    """A single acceptance-criterion checkbox parsed from prose."""

    text: str
    checked: bool


@dataclass
class Report:
    """Deterministic acceptance-criteria evaluation result."""

    criteria: list[Criterion] = field(default_factory=list)
    unchecked: list[str] = field(default_factory=list)
    diff_misses: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.unchecked and not self.diff_misses

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "criteria_count": len(self.criteria),
            "unchecked": list(self.unchecked),
            "diff_misses": list(self.diff_misses),
            "criteria": [
                {"text": c.text, "checked": c.checked} for c in self.criteria
            ],
        }


def extract_acceptance_section(body: str) -> str:
    """Return the text between an ``## Acceptance`` heading and the next heading."""

    match = _ACCEPTANCE_HEADING.search(body)
    if not match:
        return ""
    start = match.end()
    tail = body[start:]
    next_heading = _NEXT_HEADING.search(tail)
    return tail[: next_heading.start()] if next_heading else tail


def parse_criteria(body: str) -> list[Criterion]:
    """Parse acceptance-criteria checkboxes from a Markdown body."""

    section = extract_acceptance_section(body)
    out: list[Criterion] = []
    for line in section.splitlines():
        m = _CHECKBOX.match(line)
        if not m:
            continue
        out.append(
            Criterion(
                text=m.group("text").strip(),
                checked=m.group("mark").lower() == "x",
            )
        )
    return out


def _keywords(text: str) -> list[str]:
    """Cheap keyword extraction: alphanumeric tokens >=4 chars, lowercased."""

    return [t.lower() for t in re.findall(r"[A-Za-z0-9_]{4,}", text)]


def diff_misses(criteria: Iterable[Criterion], diff: str) -> list[str]:
    """Return criterion texts whose keywords do not appear anywhere in diff.

    A criterion "hits" the diff if ANY of its >=4-char tokens shows up.
    Coarse on purpose: this is a smoke-grep that flags criteria with zero
    apparent evidence in the change. False positives are acceptable; false
    negatives (criteria that look implemented but aren't) are the LLM
    reviewer's job to surface.
    """

    if not diff:
        return []
    hay = diff.lower()
    misses: list[str] = []
    for c in criteria:
        tokens = _keywords(c.text)
        if not tokens:
            continue
        if not any(tok in hay for tok in tokens):
            misses.append(c.text)
    return misses


def evaluate(body: str, diff: str = "") -> Report:
    """Build a Report from a Markdown body and optional unified diff."""

    criteria = parse_criteria(body)
    report = Report(criteria=criteria)
    report.unchecked = [c.text for c in criteria if not c.checked]
    if diff:
        report.diff_misses = diff_misses(criteria, diff)
    return report


def _read(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").splitlines()[0] if __doc__ else ""
    )
    parser.add_argument(
        "--body", type=Path, required=True, help="Path to Markdown body (PR/issue)."
    )
    parser.add_argument("--diff", type=Path, help="Optional path to unified diff.")
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON report."
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Treat 'no acceptance criteria found' as success (default: failure).",
    )
    args = parser.parse_args(argv)

    body = _read(args.body)
    diff = _read(args.diff) if args.diff else ""
    report = evaluate(body, diff)

    if not report.criteria and not args.allow_empty:
        print(
            "FAIL: no acceptance criteria found in body; "
            "add an '## Acceptance' section or pass --allow-empty.",
            file=sys.stderr,
        )
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        return 1

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"criteria: {len(report.criteria)}")
        print(f"unchecked: {len(report.unchecked)}")
        print(f"diff_misses: {len(report.diff_misses)}")
        for text in report.unchecked:
            print(f"  unchecked: {text}")
        for text in report.diff_misses:
            print(f"  diff_miss: {text}")

    return 0 if report.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
