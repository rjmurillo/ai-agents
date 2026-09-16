"""Unit tests for check_memory_placement.classify(), the issue #5391 placement validator.

Pure, no I/O: each signal in isolation, each classification branch (evidence,
suspect via one signal, normative via a heading, a role contract, or a
term-density-plus-ordered-procedure combination), both route branches, valid
and invalid suppression, fenced-code and inline-code exclusion, and the edge
cases that keep the signals from over-firing (lowercase "must", a list broken
by prose or by two blank lines, empty text).

The CLI half (real git, exit codes, skip list, symlinks) lives in
``test_check_memory_placement_cli.py``; both import the shared content
fixtures from ``_placement_fixtures.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from tests.validation._placement_fixtures import (
    EVIDENCE_INCIDENT,
    INVALID_SUPPRESSION,
    NORMATIVE_HEADING,
    NORMATIVE_TERM_AND_ORDER,
    ROLE_CONTRACT,
    SUSPECT_ORDERED_ONLY,
    SUSPECT_TERM_DENSITY,
    VALID_SUPPRESSION,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_memory_placement as checker

# --- classify(): unit tests --------------------------------------------------


def test_classify_evidence_plain_prose_has_no_signals():
    result = checker.classify("# Notes\n\nJust some observations about the build.\n")
    assert result.label == "evidence"
    assert result.signals == ()


def test_classify_evidence_incident_record_with_lowercase_must_and_never_again():
    result = checker.classify(EVIDENCE_INCIDENT)
    assert result.label == "evidence"
    assert result.raw_label == "evidence"


def test_classify_lowercase_must_is_not_counted_as_a_normative_term():
    # Two lowercase "must" occurrences: signal (a) counts only exact-case
    # MUST/MUST NOT/SHALL or case-insensitive "must not"/never/always/required.
    result = checker.classify("must go here. must also go there.")
    assert result.signals == ()


def test_classify_normative_via_heading_signal():
    result = checker.classify(NORMATIVE_HEADING)
    assert result.label == "normative"
    assert any(s.startswith("heading:") for s in result.signals)
    assert result.route == "rule"


def test_classify_ignores_headings_and_lists_inside_fenced_code():
    # A memory that quotes a rule's shape inside a code fence is evidence
    # about that rule, not a rule. Headings and numbered steps inside the
    # fence must not fire signals (b), (c), or (d).
    text = (
        "# Observation about the review skill\n\n"
        "The skill file looked like this when it broke:\n\n"
        "```markdown\n"
        "## Constraints\n"
        "## Role\n"
        "## Handoff\n"
        "1. step\n2. step\n3. step\n4. step\n5. step\n6. step\n"
        "```\n\n"
        "It failed because the fence was unterminated in the original.\n"
    )
    result = checker.classify(text)
    assert result.label == "evidence", result.signals


def test_classify_marker_inside_fenced_code_does_not_suppress():
    text = (
        "# Notes\n\n## Constraints\n\nMUST do X. MUST NOT do Y.\n\n"
        "```markdown\n<!-- placement: evidence; reason: quoted example -->\n```\n"
    )
    result = checker.classify(text)
    assert result.label == "normative"
    assert result.suppressed is False


def test_classify_marker_in_inline_code_span_does_not_suppress():
    text = (
        "# Notes\n\n## Constraints\n\nMUST do X.\n\n"
        "Use `<!-- placement: evidence; reason: quoted example -->` to suppress.\n"
    )
    result = checker.classify(text)
    assert result.label == "normative"
    assert result.suppressed is False


def test_classify_marker_nested_in_html_element_does_not_suppress():
    text = (
        "# Notes\n\n## Constraints\n\nMUST do X.\n\n"
        "<div><!-- placement: evidence; reason: nested --></div>\n"
    )
    result = checker.classify(text)
    assert result.label == "normative"
    assert result.suppressed is False


def test_classify_standalone_marker_with_leading_indent_suppresses():
    text = "# Notes\n\n## Constraints\n\n  <!-- placement: evidence; reason: incident record -->\n"
    result = checker.classify(text)
    assert result.label == "evidence"
    assert result.suppressed is True


def test_classify_two_weak_signals_stay_suspect_not_evidence():
    # a in [3, 5) together with an ordered procedure is two weak signals: it
    # must not fall through to evidence, and it is not normative either.
    text = "# Two weak\n\nnever always required\n\n1. a\n2. b\n3. c\n4. d\n5. e\n"
    result = checker.classify(text)
    assert result.label == "suspect"
    assert result.route == "skill"


def test_classify_whitespace_only_reason_is_invalid_suppression():
    result = checker.classify(NORMATIVE_HEADING + "\n<!-- placement: evidence; reason:    -->\n")
    assert result.label == "normative"
    assert result.invalid_suppression is True


def test_classify_normative_via_role_contract_signal():
    result = checker.classify(ROLE_CONTRACT)
    assert result.label == "normative"
    assert any(s.startswith("role-contract:") for s in result.signals)
    assert result.route == "agent"


def test_classify_normative_via_term_density_and_ordered_procedure_combo():
    result = checker.classify(NORMATIVE_TERM_AND_ORDER)
    assert result.label == "normative"
    assert any(s.startswith("normative-terms=") for s in result.signals)
    assert any(s.startswith("ordered-procedure=") for s in result.signals)
    # No heading or role signal fired; this file is normative purely on the
    # (a >= 5 AND c) combination, not on b or d.
    assert not any(s.startswith("heading:") for s in result.signals)
    assert not any(s.startswith("role-contract:") for s in result.signals)


def test_classify_suspect_via_term_density_alone():
    result = checker.classify(SUSPECT_TERM_DENSITY)
    assert result.label == "suspect"
    assert result.route == "rule"


def test_classify_suspect_via_ordered_procedure_alone():
    result = checker.classify(SUSPECT_ORDERED_ONLY)
    assert result.label == "suspect"
    # Signal (c) fired with normative-term count below the density threshold,
    # so this routes to a skill rather than a rule.
    assert result.route == "skill"


def test_classify_route_rule_is_the_default_for_a_plain_normative_heading():
    result = checker.classify(NORMATIVE_HEADING)
    assert result.route == "rule"


def test_classify_valid_suppression_downgrades_to_evidence():
    result = checker.classify(VALID_SUPPRESSION)
    assert result.raw_label == "normative"
    assert result.label == "evidence"
    assert result.suppressed is True
    assert result.invalid_suppression is False


def test_classify_invalid_suppression_does_not_downgrade():
    result = checker.classify(INVALID_SUPPRESSION)
    assert result.raw_label == "normative"
    assert result.label == "normative"
    assert result.suppressed is False
    assert result.invalid_suppression is True
    assert "invalid-suppression" in result.signals


def test_classify_empty_text_is_evidence():
    result = checker.classify("")
    assert result.label == "evidence"
    assert result.signals == ()


def test_classify_ordered_list_tolerates_one_blank_line_between_items():
    text = "1. one\n\n2. two\n3. three\n\n4. four\n5. five\n"
    fires, longest = checker._has_ordered_procedure(text)
    assert fires is True
    assert longest == 5


def test_classify_ordered_list_breaks_on_two_blank_lines():
    text = "1. one\n2. two\n3. three\n\n\n4. four\n5. five\n"
    fires, longest = checker._has_ordered_procedure(text)
    assert fires is False
    assert longest < 5


def test_classify_ordered_list_breaks_on_an_interrupting_prose_line():
    text = "1. one\n2. two\nsome prose here\n3. three\n4. four\n5. five\n"
    fires, _ = checker._has_ordered_procedure(text)
    assert fires is False
