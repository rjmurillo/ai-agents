#!/usr/bin/env python3
"""Mechanically extract acceptance-criteria checkboxes from a PR/issue body.

This is the externally-grounded signal that ``ai-spec-validation.yml`` gates
on, through ``scripts/ci/spec_coverage_verdict.py`` (issues #1855 and #6182).
The LLM critic may still annotate *why* a criterion is unmet, but the pass/fail
decision is determined here:

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
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

# The repository root goes first on the path so the CLI form
# (python3 scripts/external_signals/acceptance_criteria.py) can import its sibling.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.external_signals.markdown_visibility import scan_hidden

_ACCEPTANCE_HEADING = re.compile(
    r"^(?P<hashes>#{1,6})\s*acceptance(?:\s+criteria)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_ACCEPTANCE_MENTION = re.compile(r"^#{1,6}\s+.*acceptance", re.IGNORECASE)
_ANY_HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+\S", re.MULTILINE)
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
            "criteria": [{"text": c.text, "checked": c.checked} for c in self.criteria],
        }


def _section_bounds(visible: str) -> tuple[int, int] | None:
    """Return the character span of the acceptance section in ``visible``, or None.

    The span starts after the heading and ends at the next heading of the same
    or higher level (equal or fewer ``#``), so ``###`` sub-headings stay inside.
    """

    match = _ACCEPTANCE_HEADING.search(visible)
    if not match:
        return None
    level = len(match.group("hashes"))
    for heading in _ANY_HEADING.finditer(visible, match.end()):
        if len(heading.group("hashes")) <= level:
            return match.end(), heading.start()
    return match.end(), len(visible)


def extract_acceptance_section(body: str) -> str:
    """Return the text under an ``Acceptance`` heading, up to its end.

    Fenced code and HTML comments are blanked first (``markdown_visibility.scan_hidden``), so a
    heading or a checkbox inside either is not part of the section.
    """

    visible = scan_hidden(body)[0]
    bounds = _section_bounds(visible)
    return "" if bounds is None else visible[bounds[0] : bounds[1]]


def acceptance_heading_count(body: str) -> int:
    """Count acceptance headings in the raw body, hidden or not.

    A scan that hides one heading can make a second one the graded section.
    Callers that gate on the boxes fail closed when this is above one.
    """

    return len(_ACCEPTANCE_HEADING.findall(body))


def has_acceptance_section(body: str) -> bool:
    """Return True when a visible heading the parser accepts exists in ``body``."""

    return _section_bounds(scan_hidden(body)[0]) is not None


def near_miss_headings(body: str) -> list[str]:
    """Return visible headings that mention acceptance but that the parser rejects.

    A suffix ("## Acceptance criteria (draft)") or a prefix ("## 3. Acceptance")
    fails the strict heading match. Naming the line tells the author what to rename.
    """

    visible = scan_hidden(body)[0]
    return [
        line.strip()
        for line in visible.splitlines()
        if _ACCEPTANCE_MENTION.match(line) and not _ACCEPTANCE_HEADING.match(line)
    ]


def hidden_unchecked(body: str) -> list[str]:
    """Return unchecked boxes in the acceptance section that the scan blanked.

    The scan is line based and cannot match every case GitHub renders, so a box
    it hides may still show on GitHub. Only an unchecked one could turn a FAIL
    into a PASS, so callers that gate on the boxes fail closed on this list. The
    scan keeps the line count, so raw and visible lines align by index.
    """

    visible = scan_hidden(body)[0]
    bounds = _section_bounds(visible)
    if bounds is None:
        return []
    first = visible.count("\n", 0, bounds[0])
    last = visible.count("\n", 0, bounds[1])
    raw_lines = body.split("\n")
    shown = visible.split("\n")
    hidden: list[str] = []
    for index in range(first, last + 1):
        match = _CHECKBOX.match(raw_lines[index])
        if match and match.group("mark") == " " and not _CHECKBOX.match(shown[index]):
            hidden.append(match.group("text"))
    return hidden


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


_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "are",
        "but",
        "not",
        "you",
        "all",
        "can",
        "her",
        "was",
        "one",
        "our",
        "out",
        "day",
        "get",
        "has",
        "him",
        "his",
        "how",
        "its",
        "let",
        "may",
        "new",
        "now",
        "old",
        "see",
        "two",
        "use",
        "way",
        "who",
        "why",
        "yet",
        "did",
        "per",
        "set",
        "via",
        "any",
        "had",
        "top",
        "try",
        "put",
        "too",
        "off",
        "own",
        "big",
        "far",
        "few",
        "got",
        "end",
        "due",
        "run",
        "nit",
        "nor",
        "isn",
    }
)


def _keywords(text: str) -> list[str]:
    """Cheap keyword extraction: alphanumeric tokens >=3 chars, lowercased.

    Tokens of exactly 3 chars that appear in the common-English stop-word set
    are excluded to avoid matching noise words like 'the', 'and', 'for'.
    Technical 3-char terms (api, cli, git, etc.) are kept because they are not
    in the stop-word set.
    """

    tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9_]{3,}", text)]
    return [t for t in tokens if len(t) > 3 or t not in _STOP_WORDS]


def diff_misses(criteria: Iterable[Criterion], diff: str) -> list[str]:
    """Return criterion texts whose keywords do not appear in added diff lines.

    Only added lines (those starting with '+' but not '+++') are searched.
    This avoids false positives from deleted lines or unmodified context where
    a keyword may appear in code that the PR removes, not adds.

    A criterion "hits" the diff if ANY of its keyword tokens shows up in any
    added line. Coarse on purpose: flags criteria with zero apparent evidence
    in the actual change. False positives are acceptable; false negatives
    (criteria that look implemented but aren't) are the LLM reviewer's job.
    """

    if not diff:
        return []
    added_lines = [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    hay = "\n".join(added_lines).lower()
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
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0] if __doc__ else "")
    parser.add_argument(
        "--body", type=Path, required=True, help="Path to Markdown body (PR/issue)."
    )
    parser.add_argument("--diff", type=Path, help="Optional path to unified diff.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON report.")
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
