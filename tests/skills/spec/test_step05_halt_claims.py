"""Step 0.5 halt claims must match the halt criteria table (issue #7440).

The spec skill and its docs page once said Step 0.5 halts when the question
is already answered. The halt criteria table has no such trigger: H6 to H10
fire on a risky change with no prior record, and H11 fires on blast radius.
These tests keep the prose and the table in agreement.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = REPO_ROOT / "templates" / "skills" / "spec.SKILL.md.tmpl"
RENDERED = REPO_ROOT / "src" / "claude" / "skills" / "spec" / "SKILL.md"
DOCS_PAGE = REPO_ROOT / "docs" / "skills" / "spec.md"
HALT_CRITERIA = (
    REPO_ROOT
    / "src"
    / "claude"
    / "skills"
    / "spec-generator"
    / "references"
    / "spec-prior-art-schema.md"
)

CLAIM_FILES = [TEMPLATE, RENDERED, DOCS_PAGE]
ALREADY_ANSWERED = re.compile(r"halts?\b[^.|]*already answered", re.IGNORECASE)


def _halt_table() -> dict[str, str]:
    """Return the trigger ID to trigger text map from the halt criteria table."""
    text = HALT_CRITERIA.read_text(encoding="utf-8")
    start = text.index("#### Step 0.5 halt criteria")
    end = text.index("#### Step 0.5 halt block format", start)
    rows = re.findall(r"^\| (H\d+) \| (.+?) \|$", text[start:end], re.MULTILINE)
    return dict(rows)


def test_halt_table_parses_expected_triggers() -> None:
    assert sorted(_halt_table(), key=lambda t: int(t[1:])) == [f"H{n}" for n in range(6, 12)]


def test_halt_table_has_no_already_answered_trigger() -> None:
    # If an "already answered" trigger is ever added, the prose claim becomes
    # true and test_no_already_answered_halt_claim should be revisited.
    for trigger_id, trigger in _halt_table().items():
        assert "already answered" not in trigger.lower(), trigger_id


@pytest.mark.parametrize("path", CLAIM_FILES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_no_already_answered_halt_claim(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert not ALREADY_ANSWERED.search(text), (
        f"{path.name} claims Step 0.5 halts when the question is already answered; "
        "no trigger in spec-prior-art-schema.md does that"
    )


@pytest.mark.parametrize("path", CLAIM_FILES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_step05_prose_names_real_triggers(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "blast-radius" in text, f"{path.name} does not name the H11 blast-radius trigger"
    assert "no prior record" in text, (
        f"{path.name} does not name the H6 to H9 prior-record triggers"
    )
    assert "no prior record or citation" in text, (
        f"{path.name} does not name the H10 missing-citation trigger"
    )


def test_regex_catches_the_original_wording() -> None:
    original = "work, halts when the search shows the question is already answered, and runs the"
    table_row = (
        "| Its job is to halt when the question is already answered, and a skim cannot halt |"
    )
    assert ALREADY_ANSWERED.search(original)
    assert ALREADY_ANSWERED.search(table_row)
    assert not ALREADY_ANSWERED.search(
        "It stops the agent from asking questions you already answered."
    )
