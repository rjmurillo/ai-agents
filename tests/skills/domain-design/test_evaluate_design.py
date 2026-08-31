"""Tests for the domain-design behavior-first checker.

Covers the six fixtures the issue requires (source-shaped anti-pattern, explicit
progress state, behavioral API operation, CRUD-is-adequate, temporal behavior,
YAGNI control), plus negative/edge input validation and a mutation control that
proves a behavior-driven check is load-bearing.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = str(
    Path(__file__).resolve().parents[3] / ".claude/skills/domain-design/scripts"
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import evaluate_design as ed

_SCRIPT = Path(_SCRIPTS_DIR) / "evaluate_design.py"


def _base() -> dict:
    """A proposal that adopts on every axis. Fixtures override single fields."""
    return {
        "business_question": "what is the current status?",
        "state_representation": "explicit",
        "fact_is_first_class": True,
        "api_style": "crud",
        "behavior_has_invariant": False,
        "temporal_question": False,
        "history_modeled": False,
        "mirrors_source_payload": False,
        "behavior_diverges_from_source": False,
        "speculative_mechanism": None,
        "mechanism_has_behavioral_need": False,
    }


def _axis(findings: list[ed.Finding], axis: str) -> ed.Finding:
    return next(f for f in findings if f.axis == axis)


# --- Fixture 1: source-shaped anti-pattern -----------------------------------


def test_source_shaped_payload_is_flagged() -> None:
    proposal = _base()
    proposal["business_question"] = "what have we fetched?"
    proposal["mirrors_source_payload"] = True
    proposal["behavior_diverges_from_source"] = True
    findings = ed.evaluate(proposal)
    assert _axis(findings, "source-shape").verdict == "revise"
    assert ed.needs_revision(findings)


# --- Fixture 2: explicit progress state --------------------------------------


def test_reconstructed_first_class_fact_is_flagged() -> None:
    proposal = _base()
    proposal["business_question"] = "what work has completed?"
    proposal["state_representation"] = "reconstructed"
    proposal["fact_is_first_class"] = True
    findings = ed.evaluate(proposal)
    finding = _axis(findings, "state")
    assert finding.verdict == "revise"
    assert "explicit business state" in finding.message


# --- Fixture 3: behavioral API operation -------------------------------------


def test_crud_with_invariant_prefers_domain_operation() -> None:
    proposal = _base()
    proposal["business_question"] = "replace this site's reporting window"
    proposal["api_style"] = "crud"
    proposal["behavior_has_invariant"] = True
    findings = ed.evaluate(proposal)
    finding = _axis(findings, "operation")
    assert finding.verdict == "revise"
    assert "domain operation" in finding.message


# --- Fixture 4: CRUD is adequate ---------------------------------------------


def test_crud_without_invariant_stays_crud() -> None:
    proposal = _base()
    proposal["business_question"] = "manage tags"
    proposal["api_style"] = "crud"
    proposal["behavior_has_invariant"] = False
    findings = ed.evaluate(proposal)
    finding = _axis(findings, "operation")
    assert finding.verdict == "adopt"
    assert "CRUD is correct" in finding.message
    assert not ed.needs_revision(findings)


def test_domain_verb_without_invariant_is_ceremony() -> None:
    proposal = _base()
    proposal["api_style"] = "domain"
    proposal["behavior_has_invariant"] = False
    finding = _axis(ed.evaluate(proposal), "operation")
    assert finding.verdict == "revise"
    assert "Prefer CRUD" in finding.message


# --- Fixture 5: temporal behavior --------------------------------------------


def test_temporal_question_without_history_is_flagged() -> None:
    proposal = _base()
    proposal["business_question"] = "what was the rate on the invoice date?"
    proposal["temporal_question"] = True
    proposal["history_modeled"] = False
    finding = _axis(ed.evaluate(proposal), "temporal")
    assert finding.verdict == "revise"
    assert "effective-time" in finding.message


def test_temporal_question_with_history_adopts() -> None:
    proposal = _base()
    proposal["temporal_question"] = True
    proposal["history_modeled"] = True
    assert _axis(ed.evaluate(proposal), "temporal").verdict == "adopt"


# --- Fixture 6: YAGNI control ------------------------------------------------


def test_speculative_mechanism_without_need_is_rejected() -> None:
    proposal = _base()
    proposal["speculative_mechanism"] = "event-sourcing"
    proposal["mechanism_has_behavioral_need"] = False
    finding = _axis(ed.evaluate(proposal), "speculation")
    assert finding.verdict == "revise"
    assert "#5397" in finding.message


def test_speculative_mechanism_with_need_adopts() -> None:
    proposal = _base()
    proposal["speculative_mechanism"] = "event-sourcing"
    proposal["mechanism_has_behavioral_need"] = True
    assert _axis(ed.evaluate(proposal), "speculation").verdict == "adopt"


# --- Mutation control: the invariant signal is load-bearing ------------------


def test_operation_check_responds_to_invariant_signal() -> None:
    """Flipping only behavior_has_invariant flips the operation verdict.

    If the check ignored the signal (always advising a domain verb, or never
    advising one), one of these assertions would fail. This proves the check is
    driven by the behavior, not hard-coded.
    """
    with_invariant = _base()
    with_invariant["api_style"] = "crud"
    with_invariant["behavior_has_invariant"] = True
    assert _axis(ed.evaluate(with_invariant), "operation").verdict == "revise"

    without_invariant = copy.deepcopy(with_invariant)
    without_invariant["behavior_has_invariant"] = False
    assert _axis(ed.evaluate(without_invariant), "operation").verdict == "adopt"


def test_state_check_responds_to_representation_signal() -> None:
    reconstructed = _base()
    reconstructed["state_representation"] = "reconstructed"
    reconstructed["fact_is_first_class"] = True
    assert _axis(ed.evaluate(reconstructed), "state").verdict == "revise"

    explicit = copy.deepcopy(reconstructed)
    explicit["state_representation"] = "explicit"
    assert _axis(ed.evaluate(explicit), "state").verdict == "adopt"


# --- Negative and edge input validation --------------------------------------


def test_non_dict_proposal_raises() -> None:
    with pytest.raises(ValueError, match="must be an object"):
        ed.evaluate(["not", "a", "dict"])


def test_missing_keys_raises() -> None:
    with pytest.raises(ValueError, match="missing required keys"):
        ed.evaluate({"business_question": "x"})


def test_empty_business_question_raises() -> None:
    proposal = _base()
    proposal["business_question"] = "   "
    with pytest.raises(ValueError, match="non-empty string"):
        ed.evaluate(proposal)


def test_invalid_state_enum_raises() -> None:
    proposal = _base()
    proposal["state_representation"] = "guessed"
    with pytest.raises(ValueError, match="state_representation"):
        ed.evaluate(proposal)


def test_invalid_api_enum_raises() -> None:
    proposal = _base()
    proposal["api_style"] = "graphql"
    with pytest.raises(ValueError, match="api_style"):
        ed.evaluate(proposal)


def test_non_bool_field_raises() -> None:
    proposal = _base()
    proposal["behavior_has_invariant"] = "yes"
    with pytest.raises(ValueError, match="must be a boolean"):
        ed.evaluate(proposal)


def test_non_string_mechanism_raises() -> None:
    proposal = _base()
    proposal["speculative_mechanism"] = 42
    with pytest.raises(ValueError, match="speculative_mechanism"):
        ed.evaluate(proposal)


# --- CLI exit codes ----------------------------------------------------------


def _run_cli(tmp_path: Path, payload: str) -> subprocess.CompletedProcess:
    proposal_file = tmp_path / "proposal.json"
    proposal_file.write_text(payload, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(_SCRIPT), str(proposal_file)],
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )


def test_cli_adopt_exit_zero(tmp_path: Path) -> None:
    result = _run_cli(tmp_path, json.dumps(_base()))
    assert result.returncode == ed.EXIT_ADOPT
    assert "Overall: adopt" in result.stdout


def test_cli_revise_exit_ten(tmp_path: Path) -> None:
    proposal = _base()
    proposal["temporal_question"] = True
    result = _run_cli(tmp_path, json.dumps(proposal))
    assert result.returncode == ed.EXIT_REVISE
    assert "revise" in result.stdout


def test_cli_bad_json_exit_one(tmp_path: Path) -> None:
    result = _run_cli(tmp_path, "{not json")
    assert result.returncode == ed.EXIT_ERROR
    assert "invalid JSON" in result.stderr


def test_cli_missing_file_exit_one() -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "does-not-exist.json"],
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == ed.EXIT_ERROR
    assert "cannot read" in result.stderr
