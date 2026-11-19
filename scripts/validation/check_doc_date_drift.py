#!/usr/bin/env python3
"""Warn when a changed Markdown doc leaves a date or version out of step.

PRs #7428 and #6925 exposed stale source years and review dates.
The scanner reads committed added lines, canonical skill trees, and ADRs.
Rules: header-pair, subject-drift, version-drift, stale-as-of, and adr-date.
Every finding names both locations and suggests a replacement value.

``doc_date_claims.py`` owns prose matching; ``doc_date_adr.py`` owns ADR-073
last-updated checks. The lifecycle validator uses a frozen tree baseline.
It has no added-line path, so this gate owns changed ADR date checks.

``--tree`` measures the backlog. Generated mirrors, fixtures, historical
records, and fenced code are excluded. A reasoned line exception uses
``doc-date-drift: ignore -- <reason>`` on the flagged line or its predecessor.

The pre-PR gate is advisory. The CLI exits 1 for findings and 2 for git errors.
Promote by returning bool from the validator, removing its advisory licence
in evidence.py, and renaming its gate after measuring the backlog.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
# checks_common transitively imports ``scripts.cli_exec`` (absolute), so the
# repo root must be importable even when this runs as a plain script.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import doc_date_claims as dc  # noqa: E402
from checks_common import _resolve_default_base_ref  # noqa: E402
from citation_head_state import (  # noqa: E402
    HeadReadError,
    _added_lines_since_base,
    _git,
    _head_tracked_paths,
    _HeadFileCache,
)
from doc_date_adr import RULE_ADR, adr_problem  # noqa: E402
from measurement_claims import fenced_line_numbers  # noqa: E402
from stale_script_refs import HISTORICAL_ROOTS  # noqa: E402

from scripts.validation.evidence import (  # noqa: E402
    REASON_ADVISORY_FINDINGS,
    REASON_BASE_REF_UNRESOLVED,
    REASON_LISTING_FAILED,
    CheckOutcome,
)

_VALIDATOR = "validate_doc_date_drift"
_TAG = "[doc-date-drift]"
_SCANNED_SUFFIXES = (".md", ".md.tmpl")

# Dated records beyond stale_script_refs's tuple: each describes a moment.
_EXTRA_HISTORICAL_ROOTS = (
    ".project-toolkit/memory/",
    ".project-toolkit/pr-comments/",
    ".project-toolkit/handoffs/",
    ".project-toolkit/incidents/",
)

# Rendered from templates/ by build/scripts/build_all.py; the template source
# is the author of the claim, so the mirror is read once, at the source.
_GENERATED_ROOTS = (
    "src/claude/rules/",
    "src/claude/agents/",
    "src/codex/",
    "src/cursor/",
    "src/copilot-cli/",
    "src/muse/",
    "src/hermes/",
    ".github/instructions/",
    ".claude/rules/",
    ".claude/agents/",
)
_GENERATED_SKILL_ROOTS = ("src/claude/skills/", ".claude/skills/")
_GENERATED_SKILL_FILE = "SKILL.md"
_FIXTURE_FRAGMENT = "/fixtures/"

_Located = tuple[str, int, str]


@dataclass(frozen=True)
class Finding:
    """One drifted date or version: where it is, where the evidence is, what to write."""

    path: str
    line: int
    other_path: str
    other_line: int
    rule: str
    suggested: str
    detail: str

    def format(self) -> str:
        """Return the finding in file:line: [rule] reason form."""
        return (
            f"{self.path}:{self.line}: [{self.rule}] {self.detail} "
            f"Other location: {self.other_path}:{self.other_line}. "
            f"Suggested value: {self.suggested}"
        )


def is_out_of_scope(path: str) -> bool:
    """Return whether the gate must not read this tracked path."""
    if not path.endswith(_SCANNED_SUFFIXES):
        return True
    if path.startswith((*HISTORICAL_ROOTS, *_EXTRA_HISTORICAL_ROOTS, *_GENERATED_ROOTS)):
        return True
    generated_skill = path.startswith(_GENERATED_SKILL_ROOTS)
    if generated_skill and path.rsplit("/", 1)[-1] == _GENERATED_SKILL_FILE:
        return True
    return _FIXTURE_FRAGMENT in f"/{path}"


def head_commit_date(repo_root: Path) -> date | None:
    """Return the HEAD commit date, or None when git cannot say."""
    code, stdout, _stderr = _git(repo_root, ["log", "-1", "--format=%cs", "HEAD"])
    if code != 0:
        return None
    try:
        return date.fromisoformat(stdout.strip())
    except ValueError:
        return None


def _number_key(value: str) -> tuple[int, ...]:
    """Return a comparable form of a year or version; ``1.0`` equals ``1.0.0``."""
    parts = [int(part) for part in value.replace("-", ".").split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


@dataclass
class _Context:
    """Everything one scan reads, built once."""

    repo_root: Path
    head_files: _HeadFileCache
    tracked: set[str]
    merge_base: str | None
    head_date: date
    added_by_path: dict[str, set[int]]
    index: dict[str, dict[tuple[str, str], list[_Located]]]


def _fenced_lines(lines: list[str]) -> set[int]:
    """Return the 1-based numbers of lines inside or delimiting code fences."""
    fenced: set[int] = set(fenced_line_numbers(lines))
    return fenced


def _base_lines(ctx: _Context, path: str) -> list[str]:
    """Return the merge-base version of a file, or [] when it did not exist."""
    if ctx.merge_base is None:
        return []
    code, stdout, _stderr = _git(ctx.repo_root, ["show", f"{ctx.merge_base}:{path}"])
    return stdout.split("\n") if code == 0 else []


def _header_findings(ctx: _Context, path: str, lines: list[str], fenced: set[int]) -> list[Finding]:
    dates = dc.file_header_dates(lines, fenced)
    if not dates:
        return []
    base = _base_lines(ctx, path)
    base_dates = dc.file_header_dates(base, _fenced_lines(base)) if base else []
    problems = dc.header_problems(dates, base_dates, ctx.added_by_path[path], ctx.head_date)
    return [
        Finding(
            path,
            p.next_line,
            path,
            p.last_line,
            dc.RULE_HEADER,
            p.suggested.isoformat(),
            f"{p.reason}.",
        )
        for p in problems
        if not dc.has_reasoned_ignore(lines, p.next_line, lines[p.next_line - 1])
    ]


def _as_of_findings(ctx: _Context, path: str, lines: list[str], fenced: set[int]) -> list[Finding]:
    added = ctx.added_by_path[path]
    found = []
    for number, text in enumerate(lines, 1):
        stated = None if number in fenced else dc.as_of_claim(text)
        if stated is None or dc.has_reasoned_ignore(lines, number, text):
            continue
        window = range(max(1, number - dc.AS_OF_WINDOW_LINES), number + dc.AS_OF_WINDOW_LINES + 1)
        newer = [
            (other, d)
            for other in window
            if other != number and other in added and other not in fenced and other <= len(lines)
            for d in dc.dates_on_line(lines[other - 1])
            if stated.is_older_than(d)
        ]
        if newer:
            other, best = max(newer, key=lambda pair: pair[1].value)
            detail = f"As-of date {stated.text} is older than {best.text} added nearby."
            found.append(Finding(path, number, path, other, dc.RULE_AS_OF, best.text, detail))
    return found


def _build_index(ctx: _Context, skill: str) -> dict[tuple[str, str], list[_Located]]:
    """Index every claim in a skill's canonical tree by (rule, subject key)."""
    index: dict[tuple[str, str], list[_Located]] = {}
    for tree_path in dc.skill_tree_paths(skill, ctx.tracked):
        lines = ctx.head_files.lines(tree_path)
        fenced = _fenced_lines(lines)
        for number, text in enumerate(lines, 1):
            if number in fenced:
                continue
            for claim in dc.claims_for_line(text):
                index.setdefault((claim.rule, claim.key), []).append(
                    (tree_path, number, claim.value)
                )
    return index


def _skill_index(ctx: _Context, skill: str) -> dict[tuple[str, str], list[_Located]]:
    if skill not in ctx.index:
        ctx.index[skill] = _build_index(ctx, skill)
    return ctx.index[skill]


def _drift_finding(
    ctx: _Context, path: str, number: int, claim: dc.Claim, other: _Located
) -> Finding | None:
    """Return the finding for one (added line, other line) pair, or None."""
    other_path, other_line, other_value = other
    if (other_path, other_line) == (path, number):
        return None
    mine, theirs = _number_key(claim.value), _number_key(other_value)
    if claim.rule == dc.RULE_SUBJECT:
        width = min(len(mine), len(theirs))
        mine, theirs = mine[:width], theirs[:width]
    if mine == theirs:
        return None
    other_added = other_line in ctx.added_by_path.get(other_path, ())
    if other_added and mine < theirs:
        return None  # the symmetric pair reports the older line
    other_lines = ctx.head_files.lines(other_path)
    if dc.has_reasoned_ignore(other_lines, other_line, other_lines[other_line - 1]):
        return None
    subject = "URL or title" if claim.rule == dc.RULE_SUBJECT else "tool"
    detail = f"The same {subject} reads {other_value} here and {claim.value} elsewhere."
    return Finding(other_path, other_line, path, number, claim.rule, claim.value, detail)


def _drift_findings(
    ctx: _Context, path: str, numbered: list[tuple[int, str]], lines: list[str], fenced: set[int]
) -> list[Finding]:
    skill = dc.skill_name_for(path)
    if skill is None:
        return []
    index = _skill_index(ctx, skill)
    found = []
    for number, text in numbered:
        if number in fenced or dc.has_reasoned_ignore(lines, number, text):
            continue
        for claim in dc.claims_for_line(text):
            for other in index.get((claim.rule, claim.key), ()):
                finding = _drift_finding(ctx, path, number, claim, other)
                if finding is not None:
                    found.append(finding)
    return found


def _file_findings(ctx: _Context, path: str, numbered: list[tuple[int, str]]) -> list[Finding]:
    lines = ctx.head_files.lines(path)
    fenced = _fenced_lines(lines)
    problem = adr_problem(path, lines, ctx.added_by_path[path], fenced, ctx.head_date)
    adr = (
        []
        if problem is None
        else [
            Finding(
                path,
                problem.date_line,
                path,
                problem.other_line,
                RULE_ADR,
                problem.suggested.isoformat(),
                "ADR frontmatter date predates the changed decision.",
            )
        ]
    )
    return [
        *adr,
        *_header_findings(ctx, path, lines, fenced),
        *_as_of_findings(ctx, path, lines, fenced),
        *_drift_findings(ctx, path, numbered, lines, fenced),
    ]


def _dedupe(findings: list[Finding]) -> list[Finding]:
    """Keep one finding per flagged line, rule, and suggested value.

    A line that disagrees with ten others needs one fix, not ten reports; the
    kept finding cites the first other location in path and line order.
    """
    ordered = sorted(findings, key=lambda f: (f.path, f.line, f.rule, f.other_path, f.other_line))
    unique: dict[tuple[str, int, str, str], Finding] = {}
    for finding in ordered:
        unique.setdefault((finding.path, finding.line, finding.rule, finding.suggested), finding)
    return list(unique.values())


def _scan(
    ctx: _Context, candidates: dict[str, list[tuple[int, str]]]
) -> tuple[list[Finding], int, int]:
    """Scan in-scope candidates; return (findings, lines examined, files examined)."""
    findings: list[Finding] = []
    lines_examined = 0
    paths = [path for path in sorted(candidates) if not is_out_of_scope(path)]
    ctx.added_by_path = {path: {n for n, _ in candidates[path]} for path in paths}
    for path in paths:
        lines_examined += len(candidates[path])
        findings.extend(_file_findings(ctx, path, candidates[path]))
    return _dedupe(findings), lines_examined, len(paths)


def _whole_tree_candidates(
    tracked: set[str], head_files: _HeadFileCache
) -> dict[str, list[tuple[int, str]]]:
    """Treat every line of every in-scope tracked file at HEAD as added."""
    return {
        path: list(enumerate(head_files.lines(path), 1))
        for path in sorted(tracked)
        if not is_out_of_scope(path)
    }


def _merge_base(repo_root: Path, base_ref: str) -> str | None:
    code, stdout, _stderr = _git(repo_root, ["merge-base", base_ref, "HEAD"])
    return stdout.strip() or None if code == 0 else None


def find_doc_date_drift(
    repo_root: Path, base_ref: str | None, head_date: date | None = None
) -> tuple[list[Finding], str, int, int] | None:
    """Return (findings, scope label, lines examined, files examined), or None on git failure.

    ``base_ref`` None scans the whole tree at HEAD instead of the added lines.
    ``head_date`` defaults to the HEAD commit date.
    """
    tracked = _head_tracked_paths(repo_root)
    if tracked is None:
        return None
    head_files = _HeadFileCache(repo_root)
    try:
        if base_ref is None:
            candidates = _whole_tree_candidates(tracked, head_files)
            label, merge_base = "every line at HEAD", None
        else:
            added = _added_lines_since_base(repo_root, base_ref)
            if added is None:
                return None
            candidates, label = added, f"added lines vs {base_ref}"
            merge_base = _merge_base(repo_root, base_ref)
        resolved = head_date or head_commit_date(repo_root) or date.min
        ctx = _Context(repo_root, head_files, tracked, merge_base, resolved, {}, {})
        findings, lines, files = _scan(ctx, candidates)
    except HeadReadError as error:
        print(f"{_TAG} git could not read {error} at HEAD", file=sys.stderr)
        return None
    print(f"{_TAG} examined {lines} line(s) across {files} file(s): {label}")
    return findings, label, lines, files


def _report(findings: list[Finding]) -> None:
    """Print each finding plus the one-line remediation footer."""
    for finding in findings:
        print(finding.format())
    if findings:
        print(
            f"{_TAG} {len(findings)} finding(s). Update the flagged line to the suggested "
            f"value, or mark a deliberate exception with '{dc.IGNORE_MARKER} -- <reason>' "
            f"on the line or the line above."
        )


def validate_doc_date_drift(repo_root: Path) -> CheckOutcome:
    """Advisory gate entry point: print findings, return a typed result.

    Findings are ``FAIL`` with ``advisory.findings``; a git failure is
    ``BLOCKED``; no base ref is ``SKIP``. ``evidence._ADVISORY_LICENCES`` names
    the first two, so the push is not blocked.
    """
    scope = "Markdown lines added since the base ref"
    base_ref = _resolve_default_base_ref(repo_root)
    if base_ref is None:
        print("[SKIP] doc-date-drift: no base ref resolved; nothing to diff against")
        return CheckOutcome.skipped(
            _VALIDATOR, reason=REASON_BASE_REF_UNRESOLVED, scope=scope, detail="no base ref"
        )
    outcome = find_doc_date_drift(repo_root, base_ref)
    if outcome is None:
        print(f"{_TAG} git failed while reading repository state", file=sys.stderr)
        return CheckOutcome.blocked(
            _VALIDATOR,
            reason=REASON_LISTING_FAILED,
            scope=scope,
            detail="git could not list or read the changed files",
        )
    findings, _label, lines, _files = outcome
    _report(findings)
    if findings:
        return CheckOutcome.failed(
            _VALIDATOR,
            reason=REASON_ADVISORY_FINDINGS,
            revision="HEAD",
            scope=scope,
            examined=lines,
            findings=len(findings),
        )
    return CheckOutcome.passed(_VALIDATOR, revision="HEAD", scope=scope, examined=lines)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Flag date and version drift in changed Markdown docs."
    )
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument(
        "--base",
        default=None,
        help="Base ref to diff against (default: resolved like pre_pr's other gates).",
    )
    parser.add_argument(
        "--tree",
        action="store_true",
        help="Scan every in-scope line at HEAD instead of the added lines (backlog report).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the doc-date-drift check as a CLI."""
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / ".git").exists():
        print(f"{_TAG} not a git repository: {repo_root}", file=sys.stderr)
        return 2

    base_ref = None
    if not args.tree:
        base_ref = args.base or _resolve_default_base_ref(repo_root)
        if base_ref is None:
            print("[SKIP] doc-date-drift: no base ref resolved; nothing to diff against")
            return 0

    outcome = find_doc_date_drift(repo_root, base_ref)
    if outcome is None:
        print(f"{_TAG} git failed while reading repository state", file=sys.stderr)
        return 2
    _report(outcome[0])
    return 1 if outcome[0] else 0


if __name__ == "__main__":
    raise SystemExit(main())
