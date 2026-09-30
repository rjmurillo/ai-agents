"""The fail-open inventory must classify every row, with an owner and an expiry.

Issue #5636 requires the inventory to be "tied to owners and a retirement/review
date; it is not an unbounded prose list", and requires expired exceptions to
fail closed. This test reads the classified tables and fails when a row is
unclassified, unowned, or past its review date.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import NamedTuple

INVENTORY = Path(__file__).resolve().parents[2] / ".agents/governance/FAIL-OPEN-INVENTORY.md"
SECTIONS = (
    "## Bypass markers and escape hatches",
    "## Local hook jobs that report success without proving their contract",
    "## Validators under `scripts/validation/` and `.github/scripts/`",
    "### Group 1",
    "### Group 2",
    "### Group 3",
    "### Group 4",
    "### Defects",
)
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
TRAILING_COMMENT = re.compile(r"\s*<!--.*-->\s*$")
DATE = re.compile(r"^(?:decision by )?(\d{4})-(\d{2})-(\d{2})$")
FIXED_IN = re.compile(r"^fixed in #\d+$")
CLASSIFIED = re.compile(r"^RESOLVED|(?:^|\s)[ABC]: ")
DEFAULT_OWNER = "rjmurillo"


class Row(NamedTuple):
    path: str
    target: str
    owner: str
    expiry: str


def parse_rows(text: str) -> list[Row]:
    """Return every data row of the classified tables, read from the right edge.

    The Path cell comes first and Target, Owner, Expiry are the last three
    cells, so a row whose middle cells hold an escaped pipe still parses.
    """
    rows: list[Row] = []
    section = ""
    for raw in text.splitlines():
        if raw.startswith(("## ", "### ")):
            section = raw
            continue
        in_table = any(section.startswith(s) for s in SECTIONS) and raw.startswith("|")
        if not in_table or raw.startswith(("|---", "| Path ")):
            continue
        cells = [c.strip() for c in UNESCAPED_PIPE.split(TRAILING_COMMENT.sub("", raw))[1:-1]]
        rows.append(Row(cells[0], cells[-3], cells[-2], cells[-1]))
    return rows


def _live() -> list[Row]:
    return parse_rows(INVENTORY.read_text(encoding="utf-8"))


def _expired(rows: list[Row], today: date) -> list[Row]:
    out = []
    for row in rows:
        match = DATE.match(row.expiry)
        if match and date(*(int(g) for g in match.groups())) < today:
            out.append(row)
    return out


def _table(*rows: str) -> str:
    title = "## Bypass markers and escape hatches"
    header = f"{title}\n| Path | Target | Owner | Expiry |\n|---|---|---|---|\n"
    return header + "\n".join(rows) + "\n"


def test_inventory_lists_rows() -> None:
    """Negative control: a parser that finds nothing would pass every test below."""
    assert len(_live()) >= 60


def test_no_row_is_undecided() -> None:
    assert [r.path for r in _live() if "UNDECIDED" in r.target] == []


def test_every_row_has_a_class() -> None:
    assert [r.path for r in _live() if not CLASSIFIED.search(r.target)] == []


def test_owner_is_the_default_or_n_a_for_resolved_rows() -> None:
    assert [r.path for r in _live() if r.owner not in (DEFAULT_OWNER, "n/a")] == []


def test_expiry_has_a_known_shape() -> None:
    bad = [
        r.path
        for r in _live()
        if not (DATE.match(r.expiry) or FIXED_IN.match(r.expiry) or r.expiry == "n/a")
    ]
    assert bad == []


def test_owned_rows_have_an_expiry() -> None:
    """A row that names an owner must also name when it is re-read."""
    assert [r.path for r in _live() if r.owner == DEFAULT_OWNER and r.expiry == "n/a"] == []


def test_no_row_is_past_its_review_date() -> None:
    """An expired exception fails closed (epic #5636)."""
    assert _expired(_live(), date.today()) == []


def test_parser_flags_an_undecided_row() -> None:
    rows = parse_rows(_table("| `x.py:1` | UNDECIDED | rjmurillo | 2026-12-31 |"))
    assert [r.path for r in rows if "UNDECIDED" in r.target] == ["`x.py:1`"]


def test_parser_flags_an_unclassified_row() -> None:
    rows = parse_rows(_table("| `x.py:1` | DELIBERATE | rjmurillo | 2026-12-31 |"))
    assert [r.path for r in rows if not CLASSIFIED.search(r.target)] == ["`x.py:1`"]


def test_parser_flags_an_expired_row_and_keeps_a_current_one() -> None:
    rows = parse_rows(_table(
        "| `old.py:1` | B: keep advisory. | rjmurillo | 2026-01-01 |",
        "| `new.py:1` | B: keep advisory. | rjmurillo | 2026-12-31 |",
    ))
    assert [r.path for r in _expired(rows, date(2026, 9, 29))] == ["`old.py:1`"]


def test_parser_reads_a_row_with_an_escaped_pipe_and_a_trailing_comment() -> None:
    line = r"| `a.yml:1` | uses `\|\| true` | B: keep advisory. | rjmurillo | 2026-12-31 |"
    rows = parse_rows(_table(line + " <!-- ignore -->"))
    assert rows == [Row("`a.yml:1`", "B: keep advisory.", "rjmurillo", "2026-12-31")]
