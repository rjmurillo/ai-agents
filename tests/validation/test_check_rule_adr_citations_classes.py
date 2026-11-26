"""Negation, pointer labels, headings and the summary line of check_rule_adr_citations.py.

pos: a verb that nothing negates, a non-history pointer label, a heading naming a
number with no record, a combined failing count. neg: negated or historical verbs,
every history and bibliography label as a line start or a pipe cell, a heading in a
code span, a heading naming a non-accepted record. edge: the negation window ends
three words back, one pointer match per sentence, a stale baseline entry is not
counted as known, fragment fences print only under --verbose.
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
    MISSING,
    UNCLASSIFIED,
    citations_in,
)

from tests.validation.test_check_rule_adr_citations import (
    GOOD,
    STATUSES,
    _baseline,
    _kinds,
    _make_repo,
    _run,
)

RECORDS = frozenset(STATUSES)


def _kind_set(text: str) -> set[str]:
    return {kind for _, kind, _ in _kinds(text)}


# --------------------------------------------------------------------------
# Item 1: a compliance verb that is negated or historical is not compliance
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "ADR-111 follows ADR-080 and owns pins.\n",
        "Pin changes no longer pass ADR-080.\n",
        "On the first pass ADR-080 was drafted.\n",
        "Nobody needs ADR-080 now.\n",
        "Authors don't satisfy ADR-080.\n",
        "Authors don’t satisfy ADR-080.\n",
        "Pin changes do not meet ADR-080.\n",
        "Pin changes never obey ADR-080.\n",
        "Pin changes once pass ADR-080.\n",
    ],
)
def test_a_negated_or_historical_verb_is_not_binding(text: str) -> None:
    assert _kind_set(text) == {UNCLASSIFIED}


@pytest.mark.parametrize(
    "text",
    [
        "Pin changes pass ADR-080; this policy never justifies a pin.\n",
        "- `model:` needs an ADR-080 `KEEP_PIN` sidecar entry, or a bare alias.\n",
        "Pin changes pass ADR-080 first.\n",
        "We never skip it, so changes pass ADR-080.\n",
    ],
)
def test_a_verb_nothing_negates_stays_binding(text: str) -> None:
    assert _kind_set(text) == {BINDING}


def test_follows_alone_is_no_longer_a_compliance_verb() -> None:
    assert _kind_set("Pin changes follows ADR-080 first.\n") == {UNCLASSIFIED}


def test_a_modal_in_the_sentence_still_outranks_a_negated_verb() -> None:
    """Another binding signal fires, so the negation rule does not demote it."""
    assert _kind_set("Pin changes no longer pass, but they MUST cite ADR-080.\n") == {BINDING}


# --------------------------------------------------------------------------
# Item 2: the history denylist covers every bibliography word and more
# --------------------------------------------------------------------------

HISTORY_LABELS = [
    "Background",
    "Context",
    "Prior art",
    "Prior",
    "Compare",
    "Predecessor",
    "Predecessors",
    "Old",
    "Origin",
    "Origins",
    "Rationale",
    "Note",
    "Notes",
    "Source",
    "Sources",
    "Reference",
    "References",
    "Ref",
    "Refs",
    "See also",
]


@pytest.mark.parametrize("label", HISTORY_LABELS)
def test_a_history_label_at_line_start_is_not_a_binding_pointer(label: str) -> None:
    assert BINDING not in _kind_set(f"{label}: ADR-080\n")


@pytest.mark.parametrize("label", HISTORY_LABELS)
def test_a_history_label_in_a_pipe_cell_is_not_a_binding_pointer(label: str) -> None:
    """At line start a bibliography word is META before the pointer rule runs, so
    only the pipe-cell form reaches the denylist."""
    assert BINDING not in _kind_set(f"x|{label.lower()}: ADR-080|y\n")


def test_every_word_the_bibliography_label_accepts_is_also_a_history_word() -> None:
    for word in ("reference", "references", "ref", "refs", "see also", "source", "sources"):
        assert gate._POINTER_HISTORY_RE.search(word), word
        assert gate._BIB_LABEL_RE.match(f"{word}:"), word


@pytest.mark.parametrize(
    "text",
    [
        "pins: ADR-080\n",
        "Effort|by task shape|bounded: lowest|pins: ADR-080\n",
        "x|owner: ADR-080|y\n",
    ],
)
def test_an_arbitrary_label_stays_a_binding_pointer(text: str) -> None:
    assert _kind_set(text) == {BINDING}


# --------------------------------------------------------------------------
# Item 3: the pointer match runs once per sentence
# --------------------------------------------------------------------------


def test_the_pointer_is_matched_once_per_sentence_not_once_per_mention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    real = gate.is_binding_pointer

    def counting(sentence: str) -> bool:
        calls.append(sentence)
        return real(sentence)

    monkeypatch.setattr(gate, "is_binding_pointer", counting)
    found = citations_in("f.md", "Owners: ADR-078, ADR-079, ADR-080\n", STATUSES, set())
    assert [c.kind for c in found] == [BINDING, BINDING, BINDING]
    assert len(calls) == 1


def test_a_sentence_without_a_mention_does_no_pointer_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def record(sentence: str) -> bool:
        calls.append(sentence)
        return False

    monkeypatch.setattr(gate, "is_binding_pointer", record)
    assert citations_in("f.md", "No citation here. Or here.\n", STATUSES, set()) == []
    assert calls == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("pins: ADR-080.\n", {BINDING}),
        ("pins: ADR-080 .\n", {BINDING}),
        ("pins: ADR-080   \n", {BINDING}),
        ("pins: ADR-080..\n", {UNCLASSIFIED}),
        ("pins: ADR-080 x\n", {UNCLASSIFIED}),
    ],
)
def test_the_pointer_tail_accepts_one_period_and_whitespace_only(
    text: str, expected: set[str]
) -> None:
    assert _kind_set(text) == expected


def test_classify_still_computes_the_pointer_when_the_caller_passes_none() -> None:
    sentence = "pins: ADR-080"
    match = gate._MENTION_RE.search(sentence)
    assert match is not None
    assert gate.classify(sentence, match, len(sentence), False) == BINDING
    assert gate.classify(sentence, match, len(sentence), False, pointer=False) == UNCLASSIFIED


# --------------------------------------------------------------------------
# Item 4: a heading gets the existence check and nothing more
# --------------------------------------------------------------------------


def _found(text: str, records: frozenset[int] | None = RECORDS) -> list[tuple[int, str, int]]:
    found = citations_in("f.md", text, STATUSES, set(), records)
    return [(c.adr, c.kind, c.line) for c in found]


def test_a_heading_naming_a_number_with_no_record_is_missing() -> None:
    assert _found("intro\n\n## Pin policy (ADR-999)\n") == [(999, MISSING, 3)]
    assert _found("# ADR-999 index\n") == [(999, MISSING, 1)]


def test_a_heading_in_a_code_span_or_fence_is_exempt() -> None:
    assert _found("## Pin policy (`ADR-999`)\n") == []
    assert _found("```text\n## Pin policy (ADR-999)\n```\n") == []


def test_a_heading_naming_a_non_accepted_record_is_not_classified() -> None:
    assert _found("## Pin policy (ADR-080)\n") == []
    assert _found("## Authors MUST comply with ADR-080\n") == []


def test_a_heading_naming_a_tracked_record_is_clean() -> None:
    assert _found("## Pin policy (ADR-042)\n") == []


def test_a_heading_is_not_checked_when_no_record_set_is_given() -> None:
    assert _found("## Pin policy (ADR-999)\n", None) == []


def test_a_heading_with_no_space_after_the_hashes_is_prose_and_still_missing() -> None:
    assert _found("#ADR-999 is a hashtag\n") == [(999, MISSING, 1)]


def test_a_missing_heading_fails_the_run_and_a_baseline_key_accepts_it(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": "## Pin policy (ADR-999)\n"})
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_REGRESSION
    assert _run(repo, _baseline(tmp_path, ["CLAUDE.md::ADR-999"])) == EXIT_OK


# --------------------------------------------------------------------------
# Item 6: the known count is against the combined failing total
# --------------------------------------------------------------------------

BINDING_LINE = "Authors MUST comply with ADR-078.\n"
MISSING_LINE = "Background: ADR-999 came first.\n"


def test_known_is_reported_against_binding_plus_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": BINDING_LINE, "AGENTS.md": MISSING_LINE})
    known = ["CLAUDE.md::ADR-078", "AGENTS.md::ADR-999"]
    assert _run(repo, _baseline(tmp_path, known)) == EXIT_OK
    out = capsys.readouterr().out
    assert "1 binding violation(s) and 1 missing record(s), 2 failing (2 known)" in out
    assert "(1 known)" not in out


def test_a_new_failure_is_counted_failing_but_not_known(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": BINDING_LINE, "AGENTS.md": MISSING_LINE})
    assert _run(repo, _baseline(tmp_path, ["CLAUDE.md::ADR-078"])) == EXIT_REGRESSION
    assert "2 failing (1 known)" in capsys.readouterr().err


def test_a_stale_baseline_entry_is_not_counted_as_known(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": BINDING_LINE})
    stale = ["CLAUDE.md::ADR-078", "AGENTS.md::ADR-078"]
    assert _run(repo, _baseline(tmp_path, stale)) == EXIT_REGRESSION
    assert "1 failing (1 known)" in capsys.readouterr().err


def test_a_clean_tree_reports_zero_failing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": GOOD})
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_OK
    out = capsys.readouterr().out
    assert "0 binding violation(s) and 0 missing record(s), 0 failing (0 known)" in out
    assert "tracked rule file" not in out


# --------------------------------------------------------------------------
# Item 7: --verbose prints each fragment fence location
# --------------------------------------------------------------------------

FRAGMENT = "templates/agents/partials/a.mustache"


def test_verbose_prints_each_fragment_fence_location(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, {FRAGMENT: GOOD + "```text\nopen\n"})
    assert _run(repo, _baseline(tmp_path, []), "--verbose") == EXIT_OK
    err = capsys.readouterr().err
    assert (
        f"{FRAGMENT}:2: [rule-adr-citation] code fence is never closed in a template fragment"
        in err
    )


def test_a_fragment_fence_is_silent_without_verbose(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, {FRAGMENT: GOOD + "```text\nopen\n"})
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_OK
    captured = capsys.readouterr()
    assert "template fragment" not in captured.err + captured.out
    assert "1 fragment fence(s) not failed" in captured.out


def test_verbose_with_no_fragment_fence_prints_none(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": GOOD})
    assert _run(repo, _baseline(tmp_path, []), "--verbose") == EXIT_OK
    assert "template fragment" not in capsys.readouterr().err
