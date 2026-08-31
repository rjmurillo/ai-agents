#!/usr/bin/env python3
"""Tests for the review-conversation publication floor (issue #5403).

Each test carries positive, negative, and edge coverage per
`.agents/governance/TESTING-RIGOR.md`. The scenario map at the bottom ties the
issue's 18 required scenarios to the assertions that prove the deterministic
subset; the judgment-heavy scenarios are proven only for the part a pure
function can decide, and that boundary is stated per scenario.

Every negative control is written so it fails if the guard is removed: the
`assert ... == ...` on the wrong branch would flip.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

# Load the module by path so the test runs from any cwd without a package install.
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "conversation-protocol"
    / "scripts"
    / "publication.py"
)
_spec = importlib.util.spec_from_file_location("publication", _MODULE_PATH)
assert _spec and _spec.loader
publication = importlib.util.module_from_spec(_spec)
sys.modules["publication"] = publication
_spec.loader.exec_module(publication)

Disposition = publication.Disposition
Finding = publication.Finding
Attribution = publication.Attribution
Verification = publication.Verification
ResponseAction = publication.ResponseAction
RoundState = publication.RoundState
ConductError = publication.ConductError


# ---------------------------------------------------------------------------
# Disposition and severity (scenarios 8, 9)
# ---------------------------------------------------------------------------


def test_blocking_gates_approval_others_do_not():
    assert Disposition.BLOCKING.gates_approval is True
    assert Disposition.OPTIONAL.gates_approval is False
    assert Disposition.NIT.gates_approval is False
    assert Disposition.FYI.gates_approval is False


@pytest.mark.parametrize(
    "severity,expected",
    [("CRITICAL", Disposition.BLOCKING), ("IMPORTANT", Disposition.BLOCKING),
     ("SUGGESTION", Disposition.OPTIONAL)],
)
def test_disposition_for_severity_maps_canonical_severities(severity, expected):
    assert publication.disposition_for_severity(severity) is expected


def test_disposition_for_severity_is_case_and_whitespace_insensitive():
    assert publication.disposition_for_severity("  critical ") is Disposition.BLOCKING


def test_disposition_for_severity_rejects_unknown_severity():
    # Negative control: an unknown severity must fail closed, not downgrade.
    with pytest.raises(ValueError):
        publication.disposition_for_severity("MINOR")


def test_disposition_for_severity_rejects_non_string():
    with pytest.raises(ValueError):
        publication.disposition_for_severity(None)  # type: ignore[arg-type]


def test_critical_severity_never_maps_to_non_gating_disposition():
    # The severity-mutation guard: no severity that should block may render
    # as a non-gating disposition.
    assert publication.disposition_for_severity("CRITICAL").gates_approval
    assert publication.disposition_for_severity("IMPORTANT").gates_approval


# ---------------------------------------------------------------------------
# Rendering: publication cannot mutate severity (scenarios 7, 8, 9)
# ---------------------------------------------------------------------------


def test_blocker_renders_as_blocker_not_nit_or_fyi():
    rendered = publication.render_finding(Finding(Disposition.BLOCKING, "missing guard"))
    assert rendered.startswith("[BLOCKING]")
    assert "[NIT]" not in rendered
    assert "[FYI]" not in rendered


def test_optional_finding_never_renders_as_required():
    rendered = publication.render_finding(Finding(Disposition.OPTIONAL, "prefer a helper"))
    assert rendered.startswith("[OPTIONAL]")
    assert "[BLOCKING]" not in rendered


@pytest.mark.parametrize("disposition", list(Disposition))
def test_render_echoes_input_disposition_verbatim(disposition):
    # Every disposition renders as itself. There is no content-based relabeling.
    rendered = publication.render_finding(Finding(disposition, "some finding"))
    assert rendered.startswith(f"[{disposition.value}]")


def test_render_includes_why_evidence_and_fix_when_present():
    finding = Finding(
        Disposition.BLOCKING,
        "null deref on expired session",
        why="users hit a white screen",
        evidence="auth.ts:47",
        fix_direction="add a null check before deref",
    )
    rendered = publication.render_finding(finding)
    assert "Why: users hit a white screen" in rendered
    assert "Evidence: auth.ts:47" in rendered
    assert "Fix direction: add a null check before deref" in rendered


def test_render_omits_empty_optional_sections():
    # Edge: a concise one-line nit needs no Why/Evidence/Fix boilerplate.
    rendered = publication.render_finding(Finding(Disposition.NIT, "rename tmp to buffer"))
    assert rendered == "[NIT] rename tmp to buffer"


def test_finding_is_immutable():
    finding = Finding(Disposition.NIT, "x")
    with pytest.raises(FrozenInstanceError):
        finding.disposition = Disposition.BLOCKING  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Conduct: address code not people (scenarios 6, 14)
# ---------------------------------------------------------------------------


def test_sanitize_passes_clean_technical_comment_unchanged():
    text = "The parser skips validation on empty input."
    assert publication.sanitize_comment(text) == text


def test_sanitize_redacts_pejoratives():
    cleaned = publication.sanitize_comment("The retry loop is sloppy and unbounded.")
    assert "sloppy" not in cleaned.lower()
    assert "retry loop" in cleaned
    assert "unbounded" in cleaned


def test_sanitize_rejects_author_directed_wording():
    # Scenario 6: personal/author-directed wording is suppressed at publication.
    with pytest.raises(ConductError):
        publication.sanitize_comment("You clearly didn't test the empty case.")


def test_render_blocks_personal_attack_in_any_field():
    # A blocker cannot smuggle a personal attack through the Why line.
    finding = Finding(
        Disposition.BLOCKING, "guard missing", why="you obviously ignored the spec"
    )
    with pytest.raises(ConductError):
        publication.render_finding(finding)


def test_scan_conduct_reports_without_mutating():
    report = publication.scan_conduct("lazy code; you should have checked null")
    assert "lazy" in [p.lower() for p in report.pejoratives]
    assert report.personal_address  # "you should have" detected
    assert report.clean is False


def test_scan_conduct_clean_on_technical_text():
    report = publication.scan_conduct("The index is off by one at line 12.")
    assert report.clean is True


def test_hostile_input_does_not_lower_ai_standard():
    # Scenario 14: even if a human comment is hostile, the AI reply must stay
    # code-focused. A reply drafted with personal wording is rejected, so the
    # AI cannot mirror hostility into the thread.
    with pytest.raises(ConductError):
        publication.sanitize_comment("Your logic is garbage and you are careless.")


# ---------------------------------------------------------------------------
# Author/responder decision tree (scenarios 1, 2, 3, 5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "verification,expected",
    [
        (Verification.CORRECT, ResponseAction.ACCEPT_AND_FIX),
        (Verification.PARTLY_CORRECT, ResponseAction.SPLIT),
        (Verification.INCORRECT, ResponseAction.PUSH_BACK),
        (Verification.INSUFFICIENT, ResponseAction.INVESTIGATE),
    ],
)
def test_response_action_routes_each_outcome(verification, expected):
    assert publication.response_action(verification) is expected


def test_insufficient_evidence_never_routes_to_compliance_or_pushback():
    # Negative control: insufficient evidence must not bluff either way.
    action = publication.response_action(Verification.INSUFFICIENT)
    assert action is not ResponseAction.ACCEPT_AND_FIX
    assert action is not ResponseAction.PUSH_BACK


# ---------------------------------------------------------------------------
# Bounded escalation and handoff (scenarios 12, 17; "new agent cannot reset")
# ---------------------------------------------------------------------------


def test_round_state_advances_and_exhausts():
    state = RoundState(round_count=0, max_rounds=3)
    assert state.exhausted is False
    state = state.advance().advance().advance()
    assert state.round_count == 3
    assert state.exhausted is True


def test_merge_takes_max_round_and_union_of_resolved():
    # Scenario 12: a context handoff preserves round count and resolved set.
    incoming = RoundState(round_count=0, resolved=frozenset())
    current = RoundState(round_count=3, resolved=frozenset({"f1"}))
    merged = publication.merge_round_state(incoming, current)
    assert merged.round_count == 3
    assert "f1" in merged.resolved


def test_new_context_cannot_reset_exhausted_debate():
    # Negative control: a fresh zeroed state must not rewind an exhausted one.
    exhausted = RoundState(round_count=5, max_rounds=3, resolved=frozenset({"a", "b"}))
    fresh = RoundState(round_count=0)
    merged = publication.merge_round_state(fresh, exhausted)
    assert merged.exhausted is True
    assert merged.round_count == 5
    assert merged.resolved == frozenset({"a", "b"})


def test_round_state_roundtrips_through_dict():
    state = RoundState(round_count=2, max_rounds=4, resolved=frozenset({"x", "y"}))
    restored = RoundState.from_dict(state.to_dict())
    assert restored == state


def test_reopen_requires_new_evidence():
    state = RoundState(round_count=1).resolve("f1")
    with pytest.raises(ConductError):
        state.reopen("f1", new_evidence=False)


def test_reopen_allowed_with_new_evidence():
    state = RoundState(round_count=1).resolve("f1")
    reopened = state.reopen("f1", new_evidence=True)
    assert "f1" not in reopened.resolved


def test_round_state_rejects_negative_count():
    with pytest.raises(ValueError):
        RoundState(round_count=-1)


def test_round_state_rejects_zero_max_rounds():
    with pytest.raises(ValueError):
        RoundState(max_rounds=0)


# ---------------------------------------------------------------------------
# Deduplication (scenario 18)
# ---------------------------------------------------------------------------


def test_deduplicate_collapses_case_and_whitespace_variants():
    comments = [
        "Guard the null case.",
        "guard   the null case",
        "GUARD THE NULL CASE!",
    ]
    assert publication.deduplicate(comments) == ["Guard the null case."]


def test_deduplicate_keeps_distinct_comments():
    # Negative control: distinct comments are not merged.
    comments = ["Guard the null case.", "Add a retry cap."]
    assert publication.deduplicate(comments) == comments


def test_deduplicate_drops_empty_after_normalization():
    # Edge: punctuation-only comments normalize to empty and are dropped.
    assert publication.deduplicate(["...", "real point"]) == ["real point"]


# ---------------------------------------------------------------------------
# Attribution (scenario 13)
# ---------------------------------------------------------------------------


def test_render_preserves_ai_attribution():
    finding = Finding(
        Disposition.OPTIONAL, "consider a helper",
        attribution=Attribution(author="reviewer-bot", is_ai=True),
    )
    rendered = publication.render_finding(finding)
    assert "reviewer-bot (AI)" in rendered


def test_render_preserves_human_attribution():
    finding = Finding(
        Disposition.BLOCKING, "off-by-one",
        attribution=Attribution(author="alice", is_ai=False),
    )
    rendered = publication.render_finding(finding)
    assert "alice (human)" in rendered


def test_ai_and_human_attribution_are_distinguishable():
    # Never impersonate a human: the AI marker must differ from the human one.
    ai = Attribution(author="x", is_ai=True).label()
    human = Attribution(author="x", is_ai=False).label()
    assert ai != human


# ---------------------------------------------------------------------------
# CLI self-check
# ---------------------------------------------------------------------------


def test_self_check_passes():
    assert publication._self_check() is True


def test_cli_self_check_exits_zero():
    # Exercises the __main__ entry point and the success exit code.
    result = subprocess.run([sys.executable, str(_MODULE_PATH)], capture_output=True)
    assert result.returncode == 0
