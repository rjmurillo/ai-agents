"""ADR-107 names six conformance-check classes and the gate implementing each.

A prose table of script paths rots the first time a gate is renamed, and the rot
is invisible: the table still reads correctly. This test binds the table to the
filesystem so a rename, a deletion, or a dropped row fails here instead of being
discovered by the next reader.

The first revision of this test asserted only that at least five backticked
paths in the section resolved. The ADR-107 review round showed that floor was
vacuous: deleting the C1 and C2 rows left seven cited paths and the suite stayed
green, because unrelated citations elsewhere in the section padded the count. It
also dropped the two gates C1 actually invokes, because their backtick spans
carried a trailing flag.

So this version asserts coverage per class, not a count:

* the class-id set is exactly C1 through C6, so a deleted row fails;
* every row either cites a repository path that resolves, or carries an explicit
  missing marker, so a row cannot go dark by losing its gate.

Scope is deliberately narrow. It asserts citations, not behavior. A gate renamed
to a stub, unwired from ``pre_pr_sequence.py``, or hollowed to ``return 0`` still
passes here. ADR-107's Status section says so in as many words; wiring and
known-bad assertions are M2 (#5687).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = (
    REPO_ROOT
    / ".agents"
    / "architecture"
    / "ADR-107-canonical-skill-contracts-and-harness-projections.md"
)
SECTION_HEADING = "### Conformance checks"
EXPECTED_CLASS_IDS = ("C1", "C2", "C3", "C4", "C5", "C6")
MISSING_MARKER = "**Missing.**"

# A cited path carries a separator and a known suffix, or is a directory
# reference ending in `/`. Flags, prose, and bare identifiers do not match, so
# the extractor cannot invent an assertion out of `--check` or `VERIFIED`.
_PATH_RE = re.compile(r"`([A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+/?)`")
_SUFFIXES = (".py", ".md", ".json", ".yaml", ".yml")

# `| C1 label | gate cell | state cell |`
_ROW_RE = re.compile(r"^\|\s*(C\d+)\b([^|]*)\|([^|]*)\|([^|]*)\|\s*$")


class Row:
    """One conformance-table row: its class id, gate cell, and state cell."""

    def __init__(self, class_id: str, gate: str, state: str) -> None:
        self.class_id = class_id
        self.gate = gate
        self.state = state

    def __repr__(self) -> str:  # pragma: no cover - pytest id only
        return f"Row({self.class_id})"


def _section_text(body: str, heading: str) -> str:
    """Return the lines under `heading` up to the next heading of any level."""
    lines = body.splitlines()
    try:
        start = lines.index(heading) + 1
    except ValueError as exc:  # pragma: no cover - guarded by test_section_exists
        raise AssertionError(f"{ADR_PATH} has no section {heading!r}") from exc
    collected: list[str] = []
    for line in lines[start:]:
        if line.startswith("#"):
            break
        collected.append(line)
    return "\n".join(collected)


def table_rows(section: str) -> list[Row]:
    """Parse the conformance table's class rows out of `section`."""
    rows: list[Row] = []
    for line in section.splitlines():
        match = _ROW_RE.match(line)
        if match is None:
            continue
        rows.append(Row(match.group(1), match.group(3), match.group(4)))
    return rows


def cited_paths(cell: str) -> list[str]:
    """Extract repository paths cited in backticks within one table cell."""
    found: list[str] = []
    for candidate in _PATH_RE.findall(cell):
        if candidate.endswith("/") or candidate.endswith(_SUFFIXES):
            if candidate not in found:
                found.append(candidate)
    return found


def resolve_within(root: Path, cited: str) -> Path | None:
    """Resolve `cited` under `root`, or return None when it escapes.

    `_PATH_RE` accepts `.` and `-` inside a segment, so it also accepts `..`,
    and a bare `(root / cited).exists()` would then answer about a file outside
    the repository. Symlinks escape the same way, which is why this resolves
    both sides before comparing rather than checking the string.

    Containment is asserted where the check happens rather than by narrowing
    the extractor, so a traversal citation fails with a message that names it
    instead of vanishing from the candidate list.
    """
    root = root.resolve()
    try:
        candidate = (root / cited).resolve()
    except OSError:  # pragma: no cover - unreadable path component
        return None
    if candidate == root or root in candidate.parents:
        return candidate
    return None


def row_is_covered(row: Row) -> bool:
    """A row is covered when it names an existing gate or admits it has none."""
    if MISSING_MARKER in row.state:
        return True
    for path in cited_paths(row.gate):
        resolved = resolve_within(REPO_ROOT, path)
        if resolved is not None and resolved.exists():
            return True
    return False


def _rows() -> list[Row]:
    if not ADR_PATH.is_file():  # pragma: no cover - guarded by test_adr_exists
        return []
    return table_rows(_section_text(ADR_PATH.read_text(encoding="utf-8"), SECTION_HEADING))


def test_adr_exists() -> None:
    assert ADR_PATH.is_file(), f"ADR-107 missing at {ADR_PATH}"


def test_section_exists() -> None:
    body = ADR_PATH.read_text(encoding="utf-8")
    assert SECTION_HEADING in body, (
        f"{ADR_PATH} lost the {SECTION_HEADING!r} section; the conformance table "
        "is the contract this test guards"
    )


def test_every_conformance_class_has_a_row() -> None:
    """A deleted row must fail here, which a count floor cannot detect."""
    ids = tuple(row.class_id for row in _rows())
    assert ids == EXPECTED_CLASS_IDS, (
        f"ADR-107 conformance table declares {ids or '()'}; expected "
        f"{EXPECTED_CLASS_IDS}. Adding or removing a class changes the contract "
        "and must change this test in the same commit."
    )


@pytest.mark.parametrize("row", _rows(), ids=lambda row: row.class_id)
def test_row_names_an_existing_gate_or_admits_it_has_none(row: Row) -> None:
    paths = cited_paths(row.gate)
    assert row_is_covered(row), (
        f"ADR-107 class {row.class_id} cites {paths or 'no path'}, none of which "
        f"exists, and its state cell does not carry {MISSING_MARKER!r}. Update the "
        "ADR in the same change that moved or removed the gate."
    )


@pytest.mark.parametrize("row", _rows(), ids=lambda row: row.class_id)
def test_every_cited_path_resolves(row: Row) -> None:
    """A row may cite several gates; a stale one among them is still stale."""
    for path in cited_paths(row.gate):
        resolved = resolve_within(REPO_ROOT, path)
        assert resolved is not None, (
            f"ADR-107 class {row.class_id} cites {path!r}, which resolves outside "
            "the repository. A conformance gate lives in this tree."
        )
        assert resolved.exists(), (
            f"ADR-107 class {row.class_id} cites {path!r}, which does not exist."
        )


def test_the_extractor_still_yields_a_traversal_citation() -> None:
    """`_PATH_RE` accepts `..`, which is why containment is checked separately."""
    escape = "../../scripts/validation/pre_pr.py"
    assert cited_paths(f"`{escape}`") == [escape]
    assert resolve_within(REPO_ROOT, escape) is None


def test_a_traversal_to_an_existing_file_outside_the_root_is_rejected(
    tmp_path: Path,
) -> None:
    """The discriminating case: the target exists, so only containment can reject it."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "gate.py").write_text("", encoding="utf-8")
    escape = "../outside/gate.py"
    assert (root / escape).exists()
    assert resolve_within(root, escape) is None


def test_a_symlink_out_of_the_root_is_rejected(tmp_path: Path) -> None:
    """Resolving both sides catches an escape a string check would miss."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "gate.py"
    target.write_text("", encoding="utf-8")
    link = root / "gate.py"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):  # pragma: no cover - platform without symlinks
        pytest.skip("symlinks unavailable on this platform")
    assert link.exists()
    assert resolve_within(root, "gate.py") is None


def test_a_real_path_inside_the_root_still_resolves(tmp_path: Path) -> None:
    """Inverted control: containment must not reject a legitimate citation."""
    gate = tmp_path / "gate.py"
    gate.write_text("", encoding="utf-8")
    resolved = resolve_within(tmp_path, "gate.py")
    assert resolved is not None
    assert resolved == gate.resolve()


def test_negative_control_row_citing_only_a_missing_path_fails() -> None:
    """The predicate must reject a row whose only gate is fabricated."""
    fabricated = "scripts/validation/check_gate_that_does_not_exist.py"
    assert not (REPO_ROOT / fabricated).exists()
    row = Row("C9", f" `{fabricated}` ", " Exists ")
    assert cited_paths(row.gate) == [fabricated]
    assert not row_is_covered(row)


def test_negative_control_row_citing_nothing_fails() -> None:
    """A row that names no gate and admits no gap must not pass."""
    assert not row_is_covered(Row("C9", " asserts the thing ", " Exists "))


def test_missing_marker_is_the_only_way_to_pass_without_a_gate() -> None:
    """The admitted-gap path works, and only with the explicit marker."""
    assert row_is_covered(Row("C9", " asserts the thing ", f" {MISSING_MARKER} M2 "))
    assert not row_is_covered(Row("C9", " asserts the thing ", " Missing "))


def test_extractor_ignores_flags_and_bare_words() -> None:
    """Flags and identifiers must not become path assertions."""
    assert cited_paths("run `--check` then `build_all` with `VERIFIED`") == []


def test_row_parser_ignores_the_header_and_separator() -> None:
    """Only class rows are parsed, so the table header cannot become a row."""
    section = "\n".join(
        [
            "| Class | Gate | State |",
            "|---|---|---|",
            "| C1 thing | `scripts/validation/pre_pr.py` | Exists |",
        ]
    )
    rows = table_rows(section)
    assert [row.class_id for row in rows] == ["C1"]
