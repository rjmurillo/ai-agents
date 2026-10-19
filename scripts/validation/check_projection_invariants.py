#!/usr/bin/env python3
"""Assert ADR-107 projection invariants 6 and 8 for the two pilot skills.

ADR-107 section 5 lists eight invariants a projection must preserve. Byte
equality after regeneration proves the generator is deterministic. It does not
prove the transform kept the meaning, so this check compares the committed
Claude skill with its committed Copilot CLI projection and fails on a
difference in the two invariants that have a machine-readable representation.

Asserted here (issue #5687, ADR-107 migration step M2):

* Invariant 6, authorization requirements and the abstract capability set.
  The ``allowed-tools`` frontmatter entries of the source and the projection
  must be the same set. A dropped entry loses an authorization requirement. An
  added entry widens the grant. Both fail.
* Invariant 8, the documented exit-code contract. The ``## Exit Codes`` table
  of the source and the projection must carry the same codes with the same
  cells after the code (meaning and CI behavior).
* A repeated ``allowed-tools`` key, a repeated ``## Exit Codes`` heading, or a
  repeated exit-code row fails on either side. A loader keeps the last
  ``allowed-tools`` key while ``parse_allowed_tools`` reads the first, and
  ``parse_exit_codes`` keeps the last row for a code, so one copy would
  otherwise go unchecked.

Pilot inputs, because one skill cannot exercise both invariants:

* ``push-pr`` for invariant 6. Whether Copilot CLI honors argument-scoped
  ``allowed-tools`` entries is the subject of #5691 and is not decided here.
  This check only proves the projection did not change the entries.
* ``security-scan`` for invariant 8, with exit codes 0, 1, and 10.

Out of scope, by design: invariants 1 (ordered steps), 2 (completion criteria),
3 (evidence requirements), 4 (failure states), 5 (approval gates), and 7
(idempotence and rollback). They live in prose with no extractor, and the
body transform in ``build/scripts/copilot_body_translation.py`` cannot reorder
steps or delete a criterion, so a green result for them would measure nothing.
Their absence here is not coverage. They stay advisory until ADR-107 names a
machine-readable representation.

Both sides are read from disk as committed artifacts. The check never calls
the generator, so it cannot agree with the generator by construction. It fails
closed: a missing file, a symlinked or special file, a projection that is the
same file as its source, a missing ``allowed-tools`` line, an empty set, or a
missing or empty exit-code table is a finding.

Exit codes:
    0 - every pilot projection preserves its asserted invariant
    1 - at least one invariant violated or an input is missing or malformed
    2 - usage error
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SOURCE_ROOT = ".claude/skills"
PROJECTION_ROOT = "src/copilot-cli/skills"
SKILL_FILE = "SKILL.md"

INVARIANT_TOOLS = 6
INVARIANT_EXIT_CODES = 8


@dataclass(frozen=True)
class Pilot:
    """One skill and the single invariant it exercises."""

    skill: str
    invariant: int


PILOTS: tuple[Pilot, ...] = (
    Pilot("push-pr", INVARIANT_TOOLS),
    Pilot("security-scan", INVARIANT_EXIT_CODES),
)

# A YAML loader reads ``allowed-tools:``, ``"allowed-tools":``, ``'allowed-tools':``
# and ``allowed-tools :`` as the same key. The quote must match on both sides.
_ALLOWED_TOOLS_KEY = re.compile(r"""^(["']?)allowed-tools\1[ \t]*:\s*(.*)$""")
_LIST_ITEM = re.compile(r"^\s+-\s+(.+?)\s*$")
_EXIT_HEADING = re.compile(r"^##\s+Exit Codes\s*$", re.IGNORECASE)
_ANY_HEADING = re.compile(r"^#{1,6}\s")
_DIGITS = re.compile(r"^\d+$")


def _frontmatter_lines(text: str) -> list[str]:
    """Return the lines between the opening and closing ``---`` markers."""
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return []
    collected: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return collected
        collected.append(line)
    return []


def _split_top_level(value: str) -> list[str]:
    """Split on commas that sit outside any parenthesis."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def _block_list(lines: list[str]) -> list[str]:
    """Read ``- item`` lines until the next top-level key."""
    items: list[str] = []
    for line in lines:
        item = _LIST_ITEM.match(line)
        if item:
            items.append(item.group(1))
        elif line.strip() and not line.lstrip().startswith("#"):
            break
    return items


def count_allowed_tools_keys(text: str) -> int:
    """Return how many top-level ``allowed-tools`` keys the frontmatter declares."""
    return sum(1 for line in _frontmatter_lines(text) if _ALLOWED_TOOLS_KEY.match(line))


def parse_allowed_tools(text: str) -> frozenset[str]:
    """Return the ``allowed-tools`` entries, or an empty set when absent.

    Reads the first key. A repeated key is reported by
    :func:`count_allowed_tools_keys`, because a YAML loader keeps the last one.
    """
    lines = _frontmatter_lines(text)
    for index, line in enumerate(lines):
        match = _ALLOWED_TOOLS_KEY.match(line)
        if match is None:
            continue
        inline = match.group(2).strip()
        if inline:
            return frozenset(_split_top_level(inline))
        return frozenset(_block_list(lines[index + 1 :]))
    return frozenset()


def _exit_sections(text: str) -> list[list[str]]:
    """Return the lines under every ``## Exit Codes`` heading, each up to the next heading."""
    lines = text.replace("\r\n", "\n").split("\n")
    sections: list[list[str]] = []
    index = 0
    while index < len(lines):
        if not _EXIT_HEADING.match(lines[index].strip()):
            index += 1
            continue
        section: list[str] = []
        index += 1
        while index < len(lines) and not _ANY_HEADING.match(lines[index]):
            section.append(lines[index])
            index += 1
        sections.append(section)
    return sections


def _table_row(line: str) -> tuple[str, str] | None:
    """Return (code, remaining cells joined) for a row whose first cell is a number."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if len(cells) < 2 or not _DIGITS.match(cells[0]):
        return None
    return cells[0], " | ".join(" ".join(cell.split()) for cell in cells[1:])


def _exit_rows(text: str) -> list[tuple[str, str]]:
    """Return every (code, cells) row from every ``## Exit Codes`` section, in order."""
    parsed = (_table_row(line) for section in _exit_sections(text) for line in section)
    return [row for row in parsed if row is not None]


def parse_exit_codes(text: str) -> dict[str, str]:
    """Return {code: every later cell} from the ``## Exit Codes`` tables.

    A later row for a code replaces an earlier one. :func:`exit_code_duplicates`
    reports that case, so it never passes silently.
    """
    return dict(_exit_rows(text))


def exit_code_duplicates(text: str) -> list[str]:
    """Return one finding per repeated ``## Exit Codes`` heading or repeated code row."""
    problems: list[str] = []
    headings = len(_exit_sections(text))
    if headings > 1:
        problems.append(f"declares {headings} Exit Codes sections; the comparison needs one")
    counts: dict[str, int] = {}
    for code, _ in _exit_rows(text):
        counts[code] = counts.get(code, 0) + 1
    problems.extend(
        f"lists exit code {code} {count} times" for code, count in counts.items() if count > 1
    )
    return problems


def check_tools(source: str, projection: str) -> list[str]:
    """Invariant 6: the two allowed-tools sets must be equal and non-empty."""
    expected = parse_allowed_tools(source)
    if not expected:
        return ["source has no allowed-tools entries; invariant 6 is unmeasurable"]
    actual = parse_allowed_tools(projection)
    problems = [
        f"{label} declares allowed-tools {count} times; a loader keeps the last one"
        for label, text in (("source", source), ("projection", projection))
        if (count := count_allowed_tools_keys(text)) > 1
    ]
    problems += [f"projection dropped allowed-tools entry: {e}" for e in sorted(expected - actual)]
    problems += [f"projection added allowed-tools entry: {e}" for e in sorted(actual - expected)]
    return problems


def check_exit_codes(source: str, projection: str) -> list[str]:
    """Invariant 8: the two exit-code tables must carry identical rows."""
    expected = parse_exit_codes(source)
    if not expected:
        return ["source has no Exit Codes table rows; invariant 8 is unmeasurable"]
    actual = parse_exit_codes(projection)
    problems = [
        f"{label} {problem}"
        for label, text in (("source", source), ("projection", projection))
        for problem in exit_code_duplicates(text)
    ]
    problems += [
        f"projection dropped exit code {c}" for c in sorted(expected.keys() - actual.keys())
    ]
    problems += [f"projection added exit code {c}" for c in sorted(actual.keys() - expected.keys())]
    for code in sorted(expected.keys() & actual.keys()):
        if expected[code] != actual[code]:
            problems.append(
                f"exit code {code} row changed: {expected[code]!r} became {actual[code]!r}"
            )
    return problems


_CHECKS = {
    INVARIANT_TOOLS: check_tools,
    INVARIANT_EXIT_CODES: check_exit_codes,
}


def check_pilot(pilot: Pilot, source: str, projection: str) -> list[str]:
    """Run the one invariant a pilot exercises against its two texts."""
    return _CHECKS[pilot.invariant](source, projection)


def _read(path: Path) -> tuple[str, str | None]:
    """Return (text, error). A missing, unreadable, or non-regular file is an error.

    A symlink or special file is refused before the read. A symlinked
    projection that points at its own source would pass both invariants
    without the transform ever running (issue #6506).
    """
    try:
        if path.is_symlink() or (path.exists() and not path.is_file()):
            return "", f"{path} is not a regular file (symlink or special file)"
        return path.read_text(encoding="utf-8"), None
    except OSError as exc:
        return "", f"cannot read {path}: {exc.strerror or exc}"


def _distinct(source_path: Path, projection_path: Path) -> str | None:
    """Return why the two paths name the same file, or ``None``.

    Compares file identity. ``_read`` already refuses symlinks, so this catches
    a hard link between the trees.
    """
    try:
        if source_path.samefile(projection_path):
            return f"projection {projection_path} is the same file as its source {source_path}"
    except OSError as exc:
        return f"cannot compare {projection_path} with its source: {exc.strerror or exc}"
    return None


def run(repo_root: Path) -> list[str]:
    """Check every pilot and return one line per finding."""
    findings: list[str] = []
    for pilot in PILOTS:
        source_path = repo_root / SOURCE_ROOT / pilot.skill / SKILL_FILE
        projection_path = repo_root / PROJECTION_ROOT / pilot.skill / SKILL_FILE
        source, source_error = _read(source_path)
        projection, projection_error = _read(projection_path)
        errors = [e for e in (source_error, projection_error) if e]
        if not errors:
            same = _distinct(source_path, projection_path)
            errors = [same] if same else []
        problems = errors or check_pilot(pilot, source, projection)
        label = f"{pilot.skill} (invariant {pilot.invariant})"
        findings.extend(f"{label}: {problem}" for problem in problems)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo-root", default=".", help="repository root")
    args = parser.parse_args(argv)

    findings = run(Path(args.repo_root).resolve())
    if findings:
        print("ADR-107 projection invariant violations:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1
    print(f"ADR-107 invariants 6 and 8 hold for {len(PILOTS)} pilot skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
