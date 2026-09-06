"""The counts in evals/skill-triage.md must match the rows they count.

Third instance of one defect class in the forgetful decommission: a count left
behind when the list it counts got shorter. The first two were caught by Devin
Review on PR #5617, where `memory-documentary` still read "Memory Systems
(4 MCP servers)" five lines above its own three-item list, and its verification
checklist still required all four to have been queried.

This file is the same shape one level up, and the document carries the numbers
on two surfaces that a partial fix would leave disagreeing: the `## Name (N)`
section headings, and the `## Classification` table whose Total is their sum.
Retiring a skill removes its classification row, and nothing recomputes either.

Measured across the file's history. `2c85d2547` (#5156) retired `guard-maturity`
and left `Utility-skip` declaring 20 against 19 rows, so the drift predates
PR #5625, which then removed one row from each section.

Deliberately NOT asserted: any claim about how many skills exist under
`.claude/skills/` today. The document is a dated snapshot whose rows are pruned
as skills retire, so the tree count and the classified count are different
facts. The intro paragraph used to duplicate the Total, which is how the two
first diverged; it no longer carries a number.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TRIAGE_DOC = REPO_ROOT / "evals" / "skill-triage.md"

# "## Eval-worthy (38, scaffold)" and "## Already covered (12)" both count.
_COUNTED_HEADING = re.compile(r"^## (?P<name>.+?) \((?P<count>\d+)(?:,[^)]*)?\)\s*$")

# The "|---|---|" separator. Everything after it, up to the first non-table
# line, is a data row.
_ALIGNMENT_ROW = re.compile(r"^\|[\s|:-]*-[\s|:-]*\|?\s*$")

# "| Already covered | 12 | ... |", and the bold "| **Total** | **68** | |".
_CLASSIFICATION_ROW = re.compile(
    r"^\|\s*(?P<name>[^|]+?)\s*\|\s*\*{0,2}(?P<count>\d+)\*{0,2}\s*\|"
)

CLASSIFICATION_HEADING = "Classification"
TOTAL_LABEL = "Total"


def _normalize(label: str) -> str:
    """Reduce a table label to the section name it refers to.

    "Eval-worthy (deferred)" is the same category as the "## Eval-worthy"
    heading, and "**Total**" is the sum row.
    """
    label = label.strip().strip("*").strip()
    return re.sub(r"\s*\([^)]*\)$", "", label).strip()


def _tables_by_heading(text: str) -> dict[str, list[str]]:
    """Map each `## ` heading to the data rows of the tables beneath it.

    A data row is a table line following an alignment row. Keying on the
    alignment row rather than on the shape of the row's first cell is what
    makes this blind to cell contents. The first version of this parser matched
    ``^\\|\\s*[a-z0-9-]+\\s*\\|`` and therefore skipped every capitalised skill
    name (`SkillForge`), undercounting the section it was written to check and
    counting each table's header row in its place.
    """
    found: dict[str, list[str]] = {}
    current: str | None = None
    in_table = False
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[len("## ") :].strip()
            found.setdefault(current, [])
            in_table = False
            continue
        if _ALIGNMENT_ROW.match(line):
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("|"):
            if current is not None:
                found[current].append(line)
        else:
            in_table = False
    return found


def _counted_sections(text: str) -> dict[str, tuple[int, int]]:
    """Map section name to (count declared in its heading, rows found beneath)."""
    tables = _tables_by_heading(text)
    parsed: dict[str, tuple[int, int]] = {}
    for heading, rows in tables.items():
        match = _COUNTED_HEADING.match(f"## {heading}")
        if match:
            parsed[match.group("name")] = (int(match.group("count")), len(rows))
    return parsed


def _classification(text: str) -> dict[str, int]:
    """Map each Classification-table category to the count it declares."""
    rows = _tables_by_heading(text).get(CLASSIFICATION_HEADING, [])
    counts: dict[str, int] = {}
    for row in rows:
        match = _CLASSIFICATION_ROW.match(row)
        if match:
            counts[_normalize(match.group("name"))] = int(match.group("count"))
    return counts


@pytest.fixture(scope="module")
def doc_text() -> str:
    assert TRIAGE_DOC.is_file(), f"triage doc not found at {TRIAGE_DOC}"
    return TRIAGE_DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sections(doc_text: str) -> dict[str, tuple[int, int]]:
    parsed = _counted_sections(doc_text)
    assert parsed, "no counted sections parsed; the heading format changed"
    return parsed


@pytest.fixture(scope="module")
def classification(doc_text: str) -> dict[str, int]:
    parsed = _classification(doc_text)
    assert parsed, (
        "no Classification rows parsed; the table moved or changed shape. "
        "Update this parser rather than deleting the guard."
    )
    return parsed


def test_every_section_count_matches_its_rows(
    sections: dict[str, tuple[int, int]],
) -> None:
    """A heading that counts its own list must agree with the list."""
    wrong = {
        name: f"heading says {declared}, {rows} rows present"
        for name, (declared, rows) in sections.items()
        if declared != rows
    }
    assert not wrong, (
        f"skill-triage.md section counts disagree with their tables: {wrong}. "
        "Removing a classification row means editing the count in its heading."
    )


def test_classification_table_matches_the_section_headings(
    sections: dict[str, tuple[int, int]], classification: dict[str, int]
) -> None:
    """The summary table and the sections it summarizes carry the same numbers.

    Fixing only the headings leaves the identical defect one screen up, where
    it is read first.
    """
    categories = {name: n for name, n in classification.items() if name != TOTAL_LABEL}
    assert set(categories) == set(sections), (
        f"Classification table lists {sorted(categories)} but the counted "
        f"sections are {sorted(sections)}; one of them gained or lost a category."
    )
    wrong = {
        name: f"table says {n}, heading says {sections[name][0]}"
        for name, n in categories.items()
        if n != sections[name][0]
    }
    assert not wrong, f"Classification table disagrees with the headings: {wrong}"


def test_classification_total_is_the_sum_of_its_categories(
    classification: dict[str, int],
) -> None:
    """The Total row is arithmetic, so it can be checked rather than trusted."""
    assert TOTAL_LABEL in classification, (
        f"no Total row parsed from the Classification table: {classification}"
    )
    categories = {name: n for name, n in classification.items() if name != TOTAL_LABEL}
    assert classification[TOTAL_LABEL] == sum(categories.values()), (
        f"Total is {classification[TOTAL_LABEL]} but the categories sum to "
        f"{sum(categories.values())}: {categories}"
    )


def test_the_document_still_has_counted_sections(
    sections: dict[str, tuple[int, int]],
) -> None:
    """Non-vacuity: the guards above pass because counts agree, not because the
    parser stopped finding sections."""
    assert len(sections) >= 3, (
        f"expected at least 3 counted sections, parsed {len(sections)}: "
        f"{sorted(sections)}. If the document was restructured, update the "
        "pattern rather than deleting this guard."
    )
    assert all(rows > 0 for _, rows in sections.values()), (
        f"a counted section parsed zero rows, so the comparison is vacuous: {sections}"
    )


def test_parser_detects_a_short_table() -> None:
    """Negative control: a heading claiming more rows than it has must fail.

    This is the exact defect the guard exists for, so the parser has to see it.
    """
    parsed = _counted_sections(
        "## Example (3)\n\n| Skill | Why |\n|---|---|\n| beta | y |\n| gamma | z |\n"
    )
    assert parsed["Example"] == (3, 2)


def test_parser_counts_a_capitalised_skill_name() -> None:
    """Regression control for this parser's own first version.

    `^\\|\\s*[a-z0-9-]+\\s*\\|` skipped `SkillForge` and counted the header row
    instead, so the two errors cancelled and the section total looked plausible.
    Both rows below must be counted and the header row must not.
    """
    parsed = _counted_sections(
        "## Example (2)\n\n| Skill | Why |\n|---|---|\n"
        "| SkillForge | meta-skill |\n| adr-review | debate |\n"
    )
    assert parsed["Example"] == (2, 2)


def test_parser_ignores_rows_under_an_uncounted_heading() -> None:
    """Edge: rows beneath a heading with no count belong to no counted section.

    Without the reset, a later uncounted table would inflate the previous
    section and hide a real mismatch.
    """
    parsed = _counted_sections(
        "## Counted (1)\n\n| Skill | Why |\n|---|---|\n| alpha | y |\n\n"
        "## Cross-references\n\n| Ref | Note |\n|---|---|\n| b | y |\n| c | z |\n"
    )
    assert parsed == {"Counted": (1, 1)}


def test_classification_parser_reads_a_bold_total_and_a_parenthetical_label() -> None:
    """Edge: the Total row bolds its digits and one label carries a qualifier.

    A parser that missed either would compare an incomplete table and pass.
    """
    parsed = _classification(
        "## Classification\n\n| Category | Count | Action |\n|---|---|---|\n"
        "| Already covered | 12 | none |\n"
        "| Eval-worthy (deferred) | 38 | scaffold |\n"
        "| **Total** | **50** | |\n"
    )
    assert parsed == {"Already covered": 12, "Eval-worthy": 38, "Total": 50}
