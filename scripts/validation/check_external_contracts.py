#!/usr/bin/env python3
"""Gate: a load-bearing external contract carries a short, checkable provenance record.

Issue #5415. Some correctness depends on an outside source the repository
cannot import: a vendor limit, a version-specific API contract, a wire-level
standard, or a runtime behavior the vendor documentation omits. A record next
to the consumer says which source and version were used and how to re-verify
it. There is no global ledger: the record lives in the file whose behavior
depends on the contract, so unrelated changes never write to one shared file.

Two carriers, chosen by file type. Markdown and template files (.md, .tmpl)
use a fenced block whose info string is `external-contract`:

    ```external-contract
    source: https://example.org/spec
    version: v2.1
    evidence: specification
    verified: 2026-10-11
    purpose: One line naming what the code relies on
    reverify: tests/path/to/test_conformance.py
    ```

Every other scanned file type (.py, .sh, .yml, .yaml, .toml) uses a comment
block: a line holding only the comment marker and `external-contract:`,
followed by comment lines indented two or more spaces further.

Fields, a closed list:

    source     required. A URI, such as a documentation URL or a repository URL.
    version    required. Release, API version, commit, or date the source had.
    evidence   required. documentation, specification, or empirical.
    verified   required. ISO date of the last check against the source.
    purpose    required. One line. Never a copy of the source text.
    reverify   a repo path (optionally `path::selector`) to a test, probe, or
               script that re-checks the contract. Required for empirical
               evidence, because a runtime observation has no URL to re-read.
    capability a capability name that a canonical artifact owns under
               `metadata.capability` (ADR-110). Reuses issue #5396 ownership
               rather than creating a second dependency system.

A file with no record is not a defect. Ordinary documentation lookups stay
ephemeral, and a contract already encoded by an import, a schema, or a pinned
dependency needs no record. The gate only checks records that exist.

Query modes answer "who depends on this source" without grep folklore:

    check_external_contracts.py --source docs.github.com
    check_external_contracts.py --stale-before 2026-01-01

Exit codes (ADR-035):
    0 - Every record is well formed, or a query ran
    1 - A record is malformed
    2 - Config error (invalid repository root or date argument)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))  # pragma: no cover

# Canonical author surfaces only. src/, .github/instructions/, .github/agents/,
# and the rendered rules and agents under .claude/ are projections of these, so
# scanning them would report every record two or three times.
SCAN_ROOTS: tuple[str, ...] = (
    "templates",
    "scripts",
    "build",
    "tests",
    ".claude/skills",
    ".agents",
    ".project-toolkit",
    "docs",
)
MARKDOWN_SUFFIXES = frozenset({".md", ".tmpl"})
COMMENT_SUFFIXES = frozenset({".py", ".sh", ".yml", ".yaml", ".toml"})
SKIPPED_PARTS = frozenset({"__pycache__", ".venv", "node_modules"})
# .claude/skills/<name>/SKILL.md renders from templates/skills; the rest of the
# skill tree (scripts, references) is canonical there.
PROJECTED_NAME = "SKILL.md"

REQUIRED_FIELDS = ("source", "version", "evidence", "verified", "purpose")
OPTIONAL_FIELDS = ("reverify", "capability")
ALLOWED_FIELDS = frozenset(REQUIRED_FIELDS + OPTIONAL_FIELDS)
EVIDENCE_KINDS = ("documentation", "specification", "empirical")
# A purpose line is a label, not an excerpt. 200 characters holds a sentence
# and refuses a pasted paragraph of source text.
MAX_VALUE_LENGTH = 200

_SOURCE_URI = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:\S+$")
_FENCE_OPEN = re.compile(r"^(?P<ticks>`{3,}|~{3,})external-contract\s*$")
_COMMENT_MARKER = re.compile(r"^(?P<prefix>\s*#)\s*external-contract:\s*$")
_FIELD_LINE = re.compile(r"^(?P<key>[A-Za-z][\w-]*):\s*(?P<value>.*?)\s*$")


@dataclass
class Record:
    """One parsed external-contract block and the problems found while parsing it."""

    path: str
    line: int
    fields: dict[str, str] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def describe(self) -> dict[str, object]:
        """Return the JSON shape the query modes print."""
        return {"file": self.path, "line": self.line, **self.fields}


def _unquote(value: str) -> str:
    """Drop one pair of matching surrounding quotes."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _parse_body(body: list[str], record: Record) -> None:
    """Fill record.fields from `key: value` lines, noting what cannot parse."""
    for text in body:
        if not text.strip():
            continue
        match = _FIELD_LINE.match(text.strip())
        if match is None:
            record.problems.append(f"line is not `key: value`: {text.strip()[:60]!r}")
            continue
        key = match["key"]
        if key in record.fields:
            record.problems.append(f"duplicate field `{key}`")
            continue
        record.fields[key] = _unquote(match["value"])


def _fenced_records(rel: str, lines: list[str]) -> list[Record]:
    """Return every ```external-contract fenced block in a Markdown-like file."""
    records: list[Record] = []
    index = 0
    while index < len(lines):
        match = _FENCE_OPEN.match(lines[index])
        index += 1
        if match is None:
            continue
        record = Record(rel, index)
        body: list[str] = []
        while index < len(lines) and not lines[index].startswith(match["ticks"]):
            body.append(lines[index])
            index += 1
        if index >= len(lines):
            record.problems.append("fence is never closed")
        index += 1
        _parse_body(body, record)
        records.append(record)
    return records


def _comment_body(lines: list[str], start: int, prefix: str) -> tuple[list[str], int]:
    """Collect the comment lines under a marker, indented deeper than the marker."""
    body: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        rest = line[len(prefix) :]
        if not line.startswith(prefix) or not rest.startswith("  "):
            break
        body.append(rest)
        index += 1
    return body, index


def _comment_records(rel: str, lines: list[str]) -> list[Record]:
    """Return every `# external-contract:` comment block in a code or config file."""
    records: list[Record] = []
    index = 0
    while index < len(lines):
        match = _COMMENT_MARKER.match(lines[index])
        index += 1
        if match is None:
            continue
        record = Record(rel, index)
        body, index = _comment_body(lines, index, match["prefix"])
        _parse_body(body, record)
        records.append(record)
    return records


def parse_file(rel: str, text: str) -> list[Record]:
    """Parse the records one file carries, by the carrier its suffix selects."""
    suffix = Path(rel).suffix
    lines = text.splitlines()
    if suffix in MARKDOWN_SUFFIXES:
        return _fenced_records(rel, lines)
    return _comment_records(rel, lines)


def _scannable(path: Path) -> bool:
    """Return True for a canonical, non-projected file of a carrier type."""
    if SKIPPED_PARTS.intersection(path.parts):
        return False
    if path.suffix not in MARKDOWN_SUFFIXES | COMMENT_SUFFIXES:
        return False
    return path.name != PROJECTED_NAME or ".claude" not in path.parts


def collect_records(repo_root: Path) -> list[Record]:
    """Return every record under the canonical scan roots, in path order."""
    records: list[Record] = []
    for root in SCAN_ROOTS:
        base = repo_root / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or not _scannable(path.relative_to(repo_root)):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            records.extend(parse_file(path.relative_to(repo_root).as_posix(), text))
    return records


def _check_presence(fields: dict[str, str]) -> list[str]:
    """Refuse an unknown key, a missing required key, or an empty value."""
    problems = [f"unknown field `{key}`" for key in sorted(set(fields) - ALLOWED_FIELDS)]
    for key in REQUIRED_FIELDS:
        if key not in fields:
            problems.append(f"missing required field `{key}`")
    problems.extend(f"field `{key}` is empty" for key, value in sorted(fields.items()) if not value)
    return problems


def _check_value_shapes(fields: dict[str, str], today: dt.date) -> list[str]:
    """Check the evidence enum, the source URI, the date, and the length cap."""
    problems: list[str] = []
    for key, value in sorted(fields.items()):
        if len(value) > MAX_VALUE_LENGTH:
            problems.append(
                f"field `{key}` is {len(value)} characters; keep a label, not a copy of the source"
            )
    evidence = fields.get("evidence")
    if evidence and evidence not in EVIDENCE_KINDS:
        problems.append(f"evidence `{evidence}` is not one of {', '.join(EVIDENCE_KINDS)}")
    source = fields.get("source")
    if source and not _SOURCE_URI.match(source):
        problems.append(f"source `{source[:60]}` is not a URI")
    verified = fields.get("verified")
    if verified:
        problems.extend(_check_date(verified, today))
    return problems


def _check_date(value: str, today: dt.date) -> list[str]:
    """Refuse a verified date that is not ISO or lies in the future."""
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        return [f"verified `{value}` is not an ISO date (YYYY-MM-DD)"]
    if parsed > today:
        return [f"verified `{value}` is in the future"]
    return []


def _check_reverify(fields: dict[str, str], repo_root: Path) -> list[str]:
    """Require a re-check path for empirical evidence, and a real path when given."""
    target = fields.get("reverify")
    if not target:
        if fields.get("evidence") == "empirical":
            return [
                "empirical evidence needs `reverify`: a runtime observation has no URL to re-read"
            ]
        return []
    path_part = target.split("::", 1)[0]
    if not (repo_root / path_part).is_file():
        return [f"reverify path `{path_part}` does not exist"]
    return []


def _check_capability(fields: dict[str, str], owners: set[str] | None) -> list[str]:
    """Require a named capability to be owned by a canonical artifact."""
    name = fields.get("capability")
    if not name or owners is None or name in owners:
        return []
    return [f"capability `{name}` is not owned by any canonical artifact (ADR-110)"]


def check_record(
    record: Record, repo_root: Path, today: dt.date, owners: set[str] | None
) -> list[str]:
    """Return every finding for one record, each prefixed with its location."""
    problems = list(record.problems)
    problems += _check_presence(record.fields)
    problems += _check_value_shapes(record.fields, today)
    problems += _check_reverify(record.fields, repo_root)
    problems += _check_capability(record.fields, owners)
    return [f"{record.path}:{record.line}: {problem}" for problem in problems]


def _capability_owners(repo_root: Path) -> set[str] | None:
    """Return the owned capability names, or None when the graph cannot be read."""
    from check_capability_graph import TreeError, survey

    try:
        _nodes, owners, _findings = survey(repo_root)
    except TreeError:
        return None
    return set(owners)


def find_findings(repo_root: Path, today: dt.date | None = None) -> list[str]:
    """Return every finding across the repository, sorted for stable output."""
    records = collect_records(repo_root)
    owners = _capability_owners(repo_root) if records else None
    day = today or dt.date.today()
    findings: list[str] = []
    for record in records:
        findings.extend(check_record(record, repo_root, day, owners))
    return sorted(findings)


def query_records(
    records: list[Record], source: str | None, stale_before: dt.date | None
) -> list[Record]:
    """Filter records by a source substring and by a verification-age cutoff."""
    matched: list[Record] = []
    for record in records:
        if source and source.lower() not in record.fields.get("source", "").lower():
            continue
        if stale_before and not _is_stale(record, stale_before):
            continue
        matched.append(record)
    return matched


def _is_stale(record: Record, cutoff: dt.date) -> bool:
    """Return True when the record was verified before the cutoff."""
    try:
        return dt.date.fromisoformat(record.fields.get("verified", "")) < cutoff
    except ValueError:
        return True


def validate_external_contracts(repo_root: Path) -> bool:
    """Return True when every record is well formed.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract that
    ``pre_pr_sequence.py`` expects.
    """
    findings = find_findings(repo_root)
    if not findings:
        return True
    print(f"[FAIL] {len(findings)} external contract record defect(s):", file=sys.stderr)
    for finding in findings:
        print(f"  {finding}", file=sys.stderr)
    print(
        "\nFix: keep the record to the listed fields, point `reverify` at a real "
        "test or probe, and reference the source instead of copying it. "
        "Contract: .claude/skills/ai-agents-external-claims/SKILL.md",
        file=sys.stderr,
    )
    return False


def _build_parser() -> argparse.ArgumentParser:
    """Return the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo_root", nargs="?", default=None)
    parser.add_argument("--source", help="list records whose source contains this text")
    parser.add_argument(
        "--stale-before", metavar="YYYY-MM-DD", help="list records verified before this date"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    repo_root = (
        Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[2]
    )
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    if not (args.source or args.stale_before):
        return 0 if validate_external_contracts(repo_root) else 1
    try:
        cutoff = dt.date.fromisoformat(args.stale_before) if args.stale_before else None
    except ValueError:
        print(f"[FAIL] --stale-before is not an ISO date: {args.stale_before}", file=sys.stderr)
        return 2
    matched = query_records(collect_records(repo_root), args.source, cutoff)
    print(json.dumps([record.describe() for record in matched], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
