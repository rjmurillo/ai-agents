"""Tests for scripts/validation/adr_prose.py, the ADR gate's prose preparation.

Covers the two places it differs from the rule gate on purpose (PR #7489 review):
frontmatter fences the lifecycle parser accepts, and sentences soft-wrapped
before a mention. Each has a positive and a negative case, and the frontmatter
mask is pinned to ``frontmatter_contract.parse_frontmatter`` on the same input.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from adr_prose import mask_frontmatter, paragraph_blocks
from check_adr_supersession_citations import AUTHORITY, HISTORY, citations_in
from frontmatter_contract import FrontmatterStatus, parse_frontmatter

from tests.validation.test_check_adr_supersession_citations import CORPUS

_META = "id: ADR-107\ntitle: ADR-080 governs pins\n"


@pytest.mark.parametrize(
    ("opening", "closing"),
    [("---", "---"), ("---", "--- "), ("----", "----"), ("---\t", "---"), ("---", "-----")],
)
def test_metadata_under_any_accepted_fence_is_never_a_citation(opening: str, closing: str) -> None:
    text = f"{opening}\n{_META}{closing}\n\nBody with no citation.\n"
    assert parse_frontmatter(text).status is FrontmatterStatus.VALID
    assert citations_in("f.md", 107, text, CORPUS) == []
    assert "ADR-080" not in mask_frontmatter(text)


def test_frontmatter_mask_preserves_offsets_and_the_body() -> None:
    text = f"--- \n{_META}----\n\nADR-080 governs pins.\n"
    masked = mask_frontmatter(text)
    assert len(masked) == len(text)
    assert masked.count("\n") == text.count("\n")
    assert masked.endswith("ADR-080 governs pins.\n")


def test_an_unclosed_frontmatter_block_is_left_for_the_lifecycle_gate() -> None:
    text = f"---\n{_META}\nADR-080 governs pins.\n"
    assert mask_frontmatter(text) == text


@pytest.mark.parametrize(
    "text",
    [
        "Historically,\nADR-080 was the authority for model pins.\n",
        "Historically, ADR-080 was the authority for model pins.\n",
        "- Historically,\n  ADR-080 was the authority for model pins.\n",
    ],
)
def test_a_soft_wrap_keeps_the_history_word_in_the_sentence(text: str) -> None:
    assert [c.kind for c in citations_in("f.md", 107, text, CORPUS)] == [HISTORY]


def test_separate_list_items_stay_separate_blocks() -> None:
    text = "- Historically, pins moved.\n- ADR-080 governs pins.\n"
    assert [c.kind for c in citations_in("f.md", 107, text, CORPUS)] == [AUTHORITY]
    assert [[n for n, _ in block] for block in paragraph_blocks(text)] == [[1], [2]]


def test_headings_blank_lines_and_table_rows_end_a_block() -> None:
    text = "intro line\nwrapped line\n\n## Head\nnext\n| a | b |\n| c | d |\n"
    assert [[n for n, _ in block] for block in paragraph_blocks(text)] == [[1, 2], [5], [6], [7]]
