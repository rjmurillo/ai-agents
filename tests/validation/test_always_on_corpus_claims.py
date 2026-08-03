"""Guards the always-on corpus claims that ship inside the plugin.

Two documents state, in prose, which rules load on every turn:

* `.claude/skills/context-optimizer/references/model-context-doctrine.md`
  enumerates always-on rules in a three-row table, one row per declaration
  convention.
* `.claude/skills/software-engineering-library/SKILL.md` names which of the
  three book-derived rules load on every turn and which load on code files.

Both are hand-maintained and both have drifted. PR #4424 narrowed
`pragmatic-programmer` out of the always-on set and updated neither, which is
the drift these tests exist to catch.

Membership is measured from the generated `.github/instructions/` mirrors, not
from `.claude/rules/`. `generate_rules.py` drops `alwaysApply:`, renames
`paths:` to `applyTo:`, and synthesizes `applyTo: "**"` for a rule that
declares no scope or whose globs are all filtered out as internal-only. Those
last two paths reach the always-on corpus with no source line to grep, so the
mirror is authoritative for membership.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MIRROR_DIR = REPO_ROOT / ".github" / "instructions"
DOCTRINE = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "context-optimizer"
    / "references"
    / "model-context-doctrine.md"
)
LIBRARY_SKILL = (
    REPO_ROOT / ".claude" / "skills" / "software-engineering-library" / "SKILL.md"
)

BOOK_RULES = frozenset(
    {"code-quality", "pragmatic-programmer", "unified-software-engineering"}
)

_TABLE_HEADER = "| Form | Rules |"
_ROW_NAME = re.compile(r"`([a-z0-9-]+)`")
_LIBRARY_SENTENCE = re.compile(
    r"everyday default,\s*(?P<always>.+?)\s+loads? on every turn"
    r"\s+and\s+(?P<code>.+?)\s+loads? on code files",
    re.IGNORECASE,
)


def _frontmatter(text: str) -> dict:
    """Return the YAML frontmatter mapping bounded by the leading `---` pair."""
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


def measured_always_on() -> set[str]:
    """Return rule ids whose generated mirror declares universal scope."""
    found = set()
    for path in sorted(MIRROR_DIR.glob("*.instructions.md")):
        applyto = _frontmatter(path.read_text(encoding="utf-8")).get("applyTo")
        if isinstance(applyto, str) and applyto.strip() == "**":
            found.add(path.name.removesuffix(".instructions.md"))
    return found


def parse_doctrine_table(text: str) -> set[str]:
    """Return rule ids listed in the doctrine document's always-on table.

    Raises `ValueError` when the table cannot be located so that a rewrite of
    the surrounding prose fails loudly instead of asserting against an empty
    set.
    """
    start = text.find(_TABLE_HEADER)
    if start == -1:
        raise ValueError(f"always-on table header {_TABLE_HEADER!r} not found")
    names: set[str] = set()
    rows = 0
    for line in text[start:].splitlines()[2:]:
        if not line.startswith("|"):
            break
        rows += 1
        names.update(_ROW_NAME.findall(line))
    if rows == 0 or not names:
        raise ValueError("always-on table matched no rule rows")
    return names


def parse_library_sentence(text: str) -> tuple[set[str], set[str]]:
    """Return (always-on, code-files) rule ids named by the library skill."""
    match = _LIBRARY_SENTENCE.search(text)
    if not match:
        raise ValueError(
            "library skill loading sentence did not match the expected shape; "
            "update the sentence and this guard together"
        )
    split = re.compile(r"\s*,\s*|\s+and\s+")
    return (
        {p for p in split.split(match.group("always")) if p},
        {p for p in split.split(match.group("code")) if p},
    )


def test_measured_always_on_set_is_not_empty() -> None:
    """A silent glob or parse failure would make every other assertion vacuous."""
    measured = measured_always_on()
    assert len(measured) >= 5, f"suspiciously small always-on set: {measured}"
    assert "universal" in measured


def test_doctrine_table_matches_measured_always_on_set() -> None:
    listed = parse_doctrine_table(DOCTRINE.read_text(encoding="utf-8"))
    measured = measured_always_on()
    assert listed == measured, (
        f"doctrine table drift. only in doc: {sorted(listed - measured)}; "
        f"only in .github/instructions: {sorted(measured - listed)}"
    )


def test_doctrine_table_parser_rejects_a_missing_table() -> None:
    with pytest.raises(ValueError, match="not found"):
        parse_doctrine_table("# doc with no table\n\nprose only.\n")


def test_doctrine_table_parser_rejects_a_header_with_no_rows() -> None:
    with pytest.raises(ValueError, match="no rule rows"):
        parse_doctrine_table(f"{_TABLE_HEADER}\n|---|---|\n\nprose.\n")


def test_doctrine_table_parser_reads_every_row() -> None:
    """A parser that stopped at the first row would still pass a one-row doc."""
    doc = (
        f"{_TABLE_HEADER}\n|---|---|\n"
        "| `applyTo: '**'` | `alpha`, `beta` |\n"
        "| `alwaysApply: true` | `gamma` |\n"
        "| `paths: [\"**\"]` | `delta` |\n"
    )
    assert parse_doctrine_table(doc) == {"alpha", "beta", "gamma", "delta"}


def test_library_skill_loading_sentence_matches_reality() -> None:
    always, code = parse_library_sentence(LIBRARY_SKILL.read_text(encoding="utf-8"))
    measured = measured_always_on()
    assert always | code == BOOK_RULES, (
        f"library sentence names {sorted(always | code)}, expected {sorted(BOOK_RULES)}"
    )
    assert always == BOOK_RULES & measured, (
        f"sentence claims {sorted(always)} load every turn; "
        f"measured always-on book rules are {sorted(BOOK_RULES & measured)}"
    )
    assert not code & measured, (
        f"sentence claims {sorted(code & measured)} load on code files only, "
        "but they are always-on"
    )


def test_library_sentence_parser_rejects_an_unexpected_shape() -> None:
    with pytest.raises(ValueError, match="expected shape"):
        parse_library_sentence("For the everyday default, read whatever you like.")


def test_library_sentence_parser_splits_both_groups() -> None:
    parsed = parse_library_sentence(
        "For the everyday default, alpha loads on every turn and beta and "
        "gamma load on code files; open a reference here only when needed."
    )
    assert parsed == ({"alpha"}, {"beta", "gamma"})
