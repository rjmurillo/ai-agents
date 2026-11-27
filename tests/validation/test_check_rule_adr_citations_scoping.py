"""Scope of masks, cells, compliance lists and the baseline in check_rule_adr_citations.py.

Regressions for four verified PR #7770 review findings.

pos: an indented fence hides its example numbers, a compliance verb reaches every
item of an ADR list, a `Refs:` cell leaves the next cell a binding pointer, a
baselined binding key still passes. neg: text before the backticks is not a fence,
a verb ended by another word or a negator is not compliance, a missing record is
never covered by a baseline key. edge: `~~~` fences, nested indent, an unterminated
indented fence, a bibliography heading scoping every cell, a leading pipe.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_rule_adr_citations as gate
from check_rule_adr_citations import (
    BINDING,
    EXIT_OK,
    EXIT_REGRESSION,
    META,
    MISSING,
    UNCLASSIFIED,
    citations_in,
)

from tests.validation.test_check_rule_adr_citations import (
    BAD,
    STATUSES,
    _baseline,
    _git,
    _kinds,
    _make_repo,
    _run,
)

RECORDS = frozenset(STATUSES)


def _found(text: str) -> list[tuple[int, str, int]]:
    found = citations_in("f.md", text, STATUSES, set(), RECORDS)
    return [(c.adr, c.kind, c.line) for c in found]


# --------------------------------------------------------------------------
# Indented fences are code
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "1. Example citation format:\n\n   ```text\n   Example ADR-999\n   ```\n",
        "- item\n  ~~~text\n  Authors MUST comply with ADR-080\n  ~~~\n",
        "1. outer\n   - inner\n\n      ```\n      ADR-999 and ADR-080 MUST\n      ```\n",
        " ```\nADR-999\n ```\n",
    ],
)
def test_an_indented_fenced_example_is_not_a_citation(text: str) -> None:
    assert _found(text) == []


def test_an_indented_fence_does_not_mask_prose_after_its_close() -> None:
    text = "1. Example:\n\n   ```text\n   ADR-999\n   ```\n\nAuthors MUST comply with ADR-080.\n"
    assert _found(text) == [(80, BINDING, 7)]


def test_text_before_the_backticks_is_not_a_fence() -> None:
    """Negative control: only leading blanks may precede the fence marker."""
    assert _found("see ``` ADR-999\n") == [(999, MISSING, 1)]


def test_an_unterminated_indented_fence_is_reported() -> None:
    assert gate.unterminated_fence_line("intro\n\n   ```text\n   open\n") == 3


def test_a_terminated_indented_fence_is_not_reported() -> None:
    assert gate.unterminated_fence_line("1. x\n\n   ```text\n   body\n   ```\n") is None


def test_an_indented_fence_in_a_tracked_file_does_not_fail_the_run(tmp_path: Path) -> None:
    text = "1. Example citation format:\n\n   ```text\n   ADR-999\n   ```\n"
    repo = _make_repo(tmp_path, {"CLAUDE.md": text})
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_OK


# --------------------------------------------------------------------------
# A compliance verb covers a coordinated list
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Pin changes pass ADR-042 and ADR-080.\n",
        "Pin changes pass ADR-042, ADR-092, and ADR-080.\n",
        "Pin changes pass ADR-042 or ADR-080.\n",
        "Pin changes pass ADR-042 / ADR-080.\n",
        "Pin changes pass the ADR-042 and the ADR-080.\n",
        "Pin changes pass ADR-042 + ADR-080.\n",
    ],
)
def test_a_later_item_of_a_compliance_list_is_binding(text: str) -> None:
    assert _kinds(text) == [(80, BINDING, 1)]


def test_every_non_accepted_item_of_a_compliance_list_is_binding() -> None:
    assert _kinds("Pin changes pass ADR-078, ADR-079 and ADR-080.\n") == [
        (78, BINDING, 1),
        (79, BINDING, 1),
        (80, BINDING, 1),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Nobody needs ADR-042 or ADR-080.\n",
        "Pin changes no longer pass ADR-042 and ADR-080.\n",
        "Pin changes once pass ADR-042, ADR-092 and ADR-080.\n",
        "Authors don't satisfy ADR-042 and ADR-080.\n",
    ],
)
def test_a_negated_verb_does_not_reach_later_list_items(text: str) -> None:
    """The negation window is read off the verb, never widened for the list."""
    assert _kinds(text) == [(80, UNCLASSIFIED, 1)]


def test_another_word_between_the_verb_and_the_item_ends_the_list() -> None:
    assert _kinds("Authors who pass ADR-042 and cite ADR-080.\n") == [(80, UNCLASSIFIED, 1)]
    assert _kinds("Pin changes pass ADR-042 and then ADR-080.\n") == [(80, UNCLASSIFIED, 1)]


def test_a_list_item_keeps_its_own_lineage_exception() -> None:
    text = "Pin changes pass ADR-042 and ADR-080, which supersedes ADR-079.\n"
    assert _kinds(text) == [(80, BINDING, 1), (79, META, 1)]


def test_a_verb_with_no_list_before_it_is_unchanged() -> None:
    assert _kinds("Pin changes pass ADR-080.\n") == [(80, BINDING, 1)]
    assert _kinds("ADR-111 follows ADR-042 and ADR-080.\n") == [(80, UNCLASSIFIED, 1)]


# --------------------------------------------------------------------------
# A bibliography label opens its own cell
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Refs: ADR-078 | pins: ADR-080\n",
        "Refs: ADR-078|pins: ADR-080\n",
        "| Refs: ADR-078 | pins: ADR-080 |\n",
        "- Refs: ADR-078 | pins: ADR-080\n",
    ],
)
def test_a_refs_cell_does_not_hide_the_next_cells_pointer(text: str) -> None:
    assert _kinds(text) == [(78, META, 1), (80, BINDING, 1)]


def test_a_refs_cell_later_in_the_row_is_bibliography_for_that_cell_only() -> None:
    assert _kinds("| pins: ADR-080 | Refs: ADR-078 |\n") == [(80, BINDING, 1), (78, META, 1)]


def test_a_label_still_covers_every_sentence_of_a_block_with_no_pipe() -> None:
    assert _kinds("**References**: ADR-078, ADR-079.\n") == [(78, META, 1), (79, META, 1)]
    assert _kinds("Refs: ADR-078. ADR-079 too.\n") == [(78, META, 1), (79, META, 1)]


def test_a_bibliography_heading_still_scopes_every_cell() -> None:
    text = "## References\n\n| a: ADR-080 | b: ADR-078 |\n"
    assert _kinds(text) == [(80, META, 3), (78, META, 3)]


# --------------------------------------------------------------------------
# The baseline holds binding keys only
# --------------------------------------------------------------------------


def test_a_baseline_key_does_not_accept_a_missing_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": "## Pin policy (ADR-999)\n"})
    assert _run(repo, _baseline(tmp_path, ["CLAUDE.md::ADR-999"])) == EXIT_REGRESSION
    captured = capsys.readouterr()
    assert "CLAUDE.md:1: [rule-adr-citation] ADR-999 has no tracked record" in captured.out
    assert "CLAUDE.md::ADR-999: [rule-adr-citation] baseline entry no longer produced" in (
        captured.out
    )
    assert "1 new, 1 stale" in captured.err


def test_deleting_a_baselined_record_turns_the_known_entry_into_a_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": BAD})
    baseline = _baseline(tmp_path, ["CLAUDE.md::ADR-078"])
    assert _run(repo, baseline) == EXIT_OK
    capsys.readouterr()
    _git(repo, "rm", "--quiet", "--force", "--", ".project-toolkit/architecture/ADR-078-x.md")
    assert _run(repo, baseline) == EXIT_REGRESSION
    captured = capsys.readouterr()
    assert "ADR-078 has no tracked record" in captured.out
    assert "0 binding violation(s) and 1 missing record(s), 1 failing (0 known)" in captured.err


def test_a_binding_key_in_the_baseline_still_passes(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": BAD})
    assert _run(repo, _baseline(tmp_path, ["CLAUDE.md::ADR-078"])) == EXIT_OK
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_REGRESSION


# --------------------------------------------------------------------------
# The repository-wide Copilot guide is scanned
# --------------------------------------------------------------------------


def test_the_repository_wide_copilot_guide_is_in_the_scan_set() -> None:
    assert ".github/copilot-instructions.md" in gate.SCAN_GLOBS


def test_the_copilot_guide_is_checked_and_a_sibling_file_is_not(tmp_path: Path) -> None:
    repo = _make_repo(
        tmp_path,
        {".github/copilot-instructions.md": BAD, ".github/pull_request_template.md": BAD},
    )
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_REGRESSION
    known = [".github/copilot-instructions.md::ADR-078"]
    assert _run(repo, _baseline(tmp_path, known)) == EXIT_OK
