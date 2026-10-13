#!/usr/bin/env python3
"""Fail when the equivalence predicate table is malformed, lapsed, or ratcheted up.

Issue #5686, ADR-107 migration step M1. ADR-107 section 4 says every artifact
class declares an equivalence predicate, and that the declaration lives in
``.agents/governance/GENERATOR-FILES.md``, one table row per class, under the
heading ``## Equivalence predicates``. This gate reads that table and fails on:

- a table that is missing, has the wrong columns, or has a short row (exit 2);
- a predicate outside the three legal values ``derived``, ``normalized``,
  ``none`` (there is no ``byte``: it is ``derived`` with an identity transform);
- a ``derived`` or ``normalized`` row whose Gate cell does not start with the
  path of a script that exists, so a predicate cannot cite a gate nobody wrote;
- a ``none`` row with no issue number or no ISO expiry date, or whose expiry is
  before today. An expired ``none`` is a finding, not a renewal;
- a class declared twice;
- an entry of ``GENERATORS`` in ``build/scripts/build_all.py`` with no row;
- the number of ``none`` rows differing from ``none_rows`` in the baseline;
- the number of rows falling below ``classes`` in the baseline, so a row cannot
  be deleted to dodge its expiry.

The baseline is ``scripts/validation/equivalence_predicates_baseline.json``. The
ceiling on ``none`` rows is exact, not a one-way ceiling: a count above it blocks
new debt, and a count below it blocks until the baseline is lowered in the same
change, so slack cannot be spent by a later row. Adding a class with ``derived``
or ``normalized`` needs no baseline edit. Adding one with ``none`` does, and
ADR-107 section 4 closes ``none`` to new classes, so a reviewer sees it.

Every failure path fails closed. A table that cannot be read is a failure, never
a pass over zero rows.

Exit codes (ADR-035): 0 ok, 1 a finding or a ratchet breach, 2 the table, the
baseline, or the generator list could not be read.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.evidence import WORKING_TREE, CheckOutcome, EvidenceState  # noqa: E402

VALIDATOR = "equivalence_predicates"
REASON_UNREADABLE = "table.unreadable"
REASON_FINDINGS = "table.findings"
REASON_RATCHET = "ratchet.breached"
EXIT_OK, EXIT_LOGIC, EXIT_CONFIG = 0, 1, 2

GOVERNANCE_PATH = Path(".agents/governance/GENERATOR-FILES.md")
BASELINE_PATH = Path("scripts/validation/equivalence_predicates_baseline.json")
BUILD_ALL_PATH = Path("build/scripts/build_all.py")
SECTION_HEADING = "## Equivalence predicates"
COLUMNS = ("Class", "Trees", "Predicate", "Gate", "Issue", "Expiry")
PREDICATES = frozenset({"derived", "normalized", "none"})
_SCOPE = f"{GOVERNANCE_PATH.as_posix()} {SECTION_HEADING}"

_ISSUE = re.compile(r"^#[0-9]+$")
_FIRST_CODE_SPAN = re.compile(r"`([^`]+)`")


class ConfigError(Exception):
    """An input the gate needs is missing or malformed."""


@dataclass(frozen=True)
class Row:
    """One table row, cells stripped of backticks and padding."""

    name: str
    predicate: str
    gate: str
    issue: str
    expiry: str
    line: int


def _cell(raw: str) -> str:
    return raw.strip().strip("`").strip()


def _section_lines(text: str) -> list[tuple[int, str]]:
    """Return ``(line number, line)`` for table lines under the heading."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == SECTION_HEADING]
    if not starts:
        raise ConfigError(f"heading {SECTION_HEADING!r} not found in {GOVERNANCE_PATH}")
    found: list[tuple[int, str]] = []
    for index in range(starts[0] + 1, len(lines)):
        if lines[index].startswith("## "):
            break
        if lines[index].lstrip().startswith("|"):
            found.append((index + 1, lines[index]))
    return found


def _split(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


def parse_table(text: str) -> list[Row]:
    """Parse the predicate table. Raises ``ConfigError`` on any shape fault."""
    table = _section_lines(text)
    if len(table) < 3:
        raise ConfigError(f"no table with data rows under {SECTION_HEADING!r}")
    header = tuple(_split(table[0][1]))
    if header != COLUMNS:
        raise ConfigError(f"table columns {header} do not match required {COLUMNS}")
    rows: list[Row] = []
    for number, line in table[2:]:
        cells = _split(line)
        if len(cells) != len(COLUMNS):
            raise ConfigError(f"line {number}: {len(cells)} cells, expected {len(COLUMNS)}")
        rows.append(
            Row(
                name=_cell(cells[0]),
                predicate=_cell(cells[2]),
                gate=cells[3],
                issue=_cell(cells[4]),
                expiry=_cell(cells[5]),
                line=number,
            )
        )
    return rows


def generator_names(source: str) -> list[str]:
    """Return the first element of every ``GENERATORS`` tuple, parsed not grepped."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ConfigError(f"{BUILD_ALL_PATH} does not parse: {exc}") from exc
    for node in ast.walk(tree):
        names = _generators_value(node)
        if names:
            return names
        if names is not None:
            raise ConfigError(f"GENERATORS in {BUILD_ALL_PATH} names no generator")
    raise ConfigError(f"GENERATORS not found in {BUILD_ALL_PATH}")


def _generators_value(node: ast.AST) -> list[str] | None:
    if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(node.value, ast.List):
        return None
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    if not any(isinstance(t, ast.Name) and t.id == "GENERATORS" for t in targets):
        return None
    return [
        element.elts[0].value
        for element in node.value.elts
        if isinstance(element, ast.Tuple)
        and element.elts
        and isinstance(element.elts[0], ast.Constant)
        and isinstance(element.elts[0].value, str)
    ]


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _none_findings(row: Row, today: date) -> list[str]:
    found: list[str] = []
    if not _ISSUE.match(row.issue):
        found.append(f"line {row.line}: none row {row.name!r} cites no owning issue (#N)")
    expiry = _parse_date(row.expiry)
    if expiry is None:
        found.append(f"line {row.line}: none row {row.name!r} has no ISO expiry date")
    elif expiry < today:
        found.append(
            f"line {row.line}: none row {row.name!r} expired {row.expiry}; "
            "declare a predicate, an expired none is not renewed"
        )
    return found


def _gate_findings(row: Row, repo_root: Path) -> list[str]:
    span = _FIRST_CODE_SPAN.search(row.gate)
    if span is None or not (repo_root / span.group(1)).is_file():
        return [
            f"line {row.line}: {row.predicate} row {row.name!r} must open its Gate cell "
            "with the repo-relative path of an existing script in backticks"
        ]
    return []


def row_findings(row: Row, repo_root: Path, today: date) -> list[str]:
    """Return the findings for one row."""
    if row.predicate not in PREDICATES:
        legal = ", ".join(sorted(PREDICATES))
        return [f"line {row.line}: {row.predicate!r} is not a legal predicate ({legal})"]
    if row.predicate == "none":
        return _none_findings(row, today)
    return _gate_findings(row, repo_root)


def table_findings(
    rows: list[Row], generators: list[str], repo_root: Path, today: date
) -> list[str]:
    """Return every row, duplicate, and coverage finding."""
    found: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if row.name in seen:
            found.append(f"line {row.line}: class {row.name!r} is declared twice")
        seen.add(row.name)
        found.extend(row_findings(row, repo_root, today))
    found.extend(
        f"GENERATORS entry {name!r} has no row in the predicate table"
        for name in generators
        if name not in seen
    )
    return found


def read_baseline(repo_root: Path) -> tuple[int, int]:
    """Return ``(none_rows, classes)`` from the baseline, or raise ``ConfigError``."""
    path = repo_root / BASELINE_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"baseline {BASELINE_PATH} unreadable: {exc}") from exc
    values = [data.get(key) if isinstance(data, dict) else None for key in ("none_rows", "classes")]
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in values):
        raise ConfigError(
            f"baseline {BASELINE_PATH} needs non-negative integers none_rows, classes"
        )
    return values[0], values[1]


def ratchet_findings(rows: list[Row], none_rows: int, classes: int) -> list[str]:
    """Compare the measured counts with the baseline."""
    measured = sum(1 for row in rows if row.predicate == "none")
    found: list[str] = []
    if measured > none_rows:
        found.append(
            f"none rows rose to {measured}, baseline allows {none_rows}; "
            "ADR-107 section 4 closes none to new classes"
        )
    if measured < none_rows:
        found.append(
            f"none rows fell to {measured}, baseline holds {none_rows}; "
            f"lower none_rows in {BASELINE_PATH} so the slack cannot be spent"
        )
    if len(rows) < classes:
        found.append(
            f"table holds {len(rows)} classes, baseline records {classes}; "
            "a class row cannot be deleted to dodge its expiry"
        )
    return found


def _read(repo_root: Path, relative: Path) -> str:
    try:
        return (repo_root / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{relative} unreadable: {exc}") from exc


def _unreadable(exc: ConfigError) -> CheckOutcome:
    return CheckOutcome.failed(
        VALIDATOR,
        reason=REASON_UNREADABLE,
        scope=_SCOPE,
        revision=WORKING_TREE,
        findings=1,
        detail=str(exc),
    )


def validate_equivalence_predicates(repo_root: Path, today: date | None = None) -> CheckOutcome:
    """Typed entry point for callers that hold a repository root."""
    try:
        rows = parse_table(_read(repo_root, GOVERNANCE_PATH))
        generators = generator_names(_read(repo_root, BUILD_ALL_PATH))
        none_rows, classes = read_baseline(repo_root)
    except ConfigError as exc:
        return _unreadable(exc)
    today = today or datetime.now(UTC).date()
    row_problems = table_findings(rows, generators, repo_root, today)
    ratchet_problems = ratchet_findings(rows, none_rows, classes)
    problems = row_problems + ratchet_problems
    if problems:
        reason = REASON_FINDINGS if row_problems else REASON_RATCHET
        return CheckOutcome.failed(
            VALIDATOR,
            reason=reason,
            scope=_SCOPE,
            revision=WORKING_TREE,
            examined=len(rows),
            findings=len(problems),
            detail="; ".join(problems),
        )
    return CheckOutcome.passed(
        VALIDATOR,
        revision=WORKING_TREE,
        scope=_SCOPE,
        examined=len(rows),
        detail=f"{len(rows)} classes, {none_rows} none",
    )


def _exit_code(outcome: CheckOutcome) -> int:
    if outcome.state is EvidenceState.PASS:
        return EXIT_OK
    return EXIT_CONFIG if outcome.reason == REASON_UNREADABLE else EXIT_LOGIC


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=_PROJECT_ROOT)
    parser.add_argument("--today", type=date.fromisoformat, default=None, help="test seam")
    args = parser.parse_args(argv)
    outcome = validate_equivalence_predicates(args.repo_root, args.today)
    print(outcome.report_line())
    return _exit_code(outcome)


if __name__ == "__main__":
    raise SystemExit(main())
