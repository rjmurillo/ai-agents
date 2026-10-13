"""Tests for the domain-design behavior-first checker.

Covers the six fixtures the issue requires (source-shaped anti-pattern, explicit
progress state, behavioral API operation, CRUD is adequate, temporal behavior,
YAGNI control), input validation, the CLI, and a mutation control that proves
each behavior-driven axis is load-bearing.
"""

import copy
import json
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import evaluate_design as ed
import pytest

SCRIPT = Path(ed.__file__).resolve()


def adopt_all() -> dict[str, Any]:
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
        "use_cases": [{"question": "show the status", "needs_reconstruction": False}],
    }


def verdicts(proposal: dict[str, Any]) -> dict[str, str]:
    return {f.axis: f.verdict for f in ed.evaluate(proposal)}


def revised_axes(proposal: dict[str, Any]) -> set[str]:
    return {axis for axis, verdict in verdicts(proposal).items() if verdict == "revise"}


# Fixture 1: source-shaped anti-pattern


def test_source_shaped_model_is_revised() -> None:
    p = adopt_all()
    p["mirrors_source_payload"] = True
    p["behavior_diverges_from_source"] = True
    assert revised_axes(p) == {"source-shape"}


def test_source_shape_that_matches_behavior_is_adopted() -> None:
    p = adopt_all()
    p["mirrors_source_payload"] = True
    p["behavior_diverges_from_source"] = False
    assert revised_axes(p) == set()


# Fixture 2: explicit progress state


def test_progress_reconstructed_from_fact_rows_is_revised() -> None:
    p = adopt_all()
    p["business_question"] = "what work has completed?"
    p["state_representation"] = "reconstructed"
    p["use_cases"] = [{"question": "what work has completed?", "needs_reconstruction": True}]
    assert revised_axes(p) == {"state", "use-cases"}


def test_reconstruction_of_a_non_first_class_value_is_a_safe_derivation() -> None:
    p = adopt_all()
    p["fact_is_first_class"] = False
    p["state_representation"] = "reconstructed"
    assert revised_axes(p) == set()


# Fixture 3: behavioral API operation


def test_crud_over_a_behavior_with_invariants_is_revised() -> None:
    p = adopt_all()
    p["behavior_has_invariant"] = True
    p["api_style"] = "crud"
    assert revised_axes(p) == {"operation"}


def test_domain_operation_over_a_behavior_with_invariants_is_adopted() -> None:
    p = adopt_all()
    p["behavior_has_invariant"] = True
    p["api_style"] = "domain"
    assert revised_axes(p) == set()


# Fixture 4: CRUD is adequate


def test_plain_crud_without_invariant_is_adopted() -> None:
    finding = next(f for f in ed.evaluate(adopt_all()) if f.axis == "operation")
    assert finding.verdict == "adopt"
    assert "CRUD is correct" in finding.message


def test_domain_verb_without_invariant_is_ceremony() -> None:
    p = adopt_all()
    p["api_style"] = "domain"
    assert revised_axes(p) == {"operation"}


# Fixture 5: temporal behavior


def test_time_dependent_question_without_history_is_revised() -> None:
    p = adopt_all()
    p["temporal_question"] = True
    p["history_modeled"] = False
    assert revised_axes(p) == {"temporal"}


def test_time_dependent_question_with_history_is_adopted() -> None:
    p = adopt_all()
    p["temporal_question"] = True
    p["history_modeled"] = True
    assert revised_axes(p) == set()


def test_history_without_a_temporal_question_is_not_penalized() -> None:
    p = adopt_all()
    p["history_modeled"] = True
    assert revised_axes(p) == set()


# Fixture 6: YAGNI control


def test_speculative_mechanism_without_need_is_rejected() -> None:
    p = adopt_all()
    p["speculative_mechanism"] = "event sourcing"
    p["mechanism_has_behavioral_need"] = False
    finding = next(f for f in ed.evaluate(p) if f.axis == "speculation")
    assert finding.verdict == "revise"
    assert "event sourcing" in finding.message


def test_mechanism_with_behavioral_need_is_kept() -> None:
    p = adopt_all()
    p["speculative_mechanism"] = "audit log"
    p["mechanism_has_behavioral_need"] = True
    assert revised_axes(p) == set()


def test_empty_mechanism_string_is_not_a_mechanism() -> None:
    p = adopt_all()
    p["speculative_mechanism"] = ""
    assert revised_axes(p) == set()


# Use-case walk


def test_one_failing_use_case_among_many_is_named() -> None:
    p = adopt_all()
    p["use_cases"] = [
        {"question": "show the status", "needs_reconstruction": False},
        {"question": "what was true last quarter?", "needs_reconstruction": True},
    ]
    finding = next(f for f in ed.evaluate(p) if f.axis == "use-cases")
    assert finding.verdict == "revise"
    assert "what was true last quarter?" in finding.message
    assert "show the status" not in finding.message


# Combined


def test_every_axis_can_revise_at_once() -> None:
    p = adopt_all()
    p.update(
        state_representation="reconstructed",
        behavior_has_invariant=True,
        temporal_question=True,
        mirrors_source_payload=True,
        behavior_diverges_from_source=True,
        speculative_mechanism="CQRS",
    )
    p["use_cases"][0]["needs_reconstruction"] = True
    assert revised_axes(p) == {
        "state",
        "operation",
        "temporal",
        "source-shape",
        "speculation",
        "use-cases",
    }


def test_evaluate_does_not_mutate_the_proposal() -> None:
    p = adopt_all()
    before = copy.deepcopy(p)
    ed.evaluate(p)
    assert p == before


# Mutation control: each axis is load-bearing


MUTATIONS = [
    ("check_reconstruction", {"state_representation": "reconstructed"}, "state"),
    ("check_operation", {"behavior_has_invariant": True}, "operation"),
    ("check_temporal", {"temporal_question": True}, "temporal"),
    (
        "check_source_shape",
        {"mirrors_source_payload": True, "behavior_diverges_from_source": True},
        "source-shape",
    ),
    ("check_speculation", {"speculative_mechanism": "event sourcing"}, "speculation"),
    (
        "check_use_cases",
        {"use_cases": [{"question": "q", "needs_reconstruction": True}]},
        "use-cases",
    ),
]


@pytest.mark.parametrize(("check_name", "override", "axis"), MUTATIONS)
def test_neutralizing_an_axis_hides_its_defect(
    monkeypatch: pytest.MonkeyPatch, check_name: str, override: dict[str, Any], axis: str
) -> None:
    p = adopt_all()
    p.update(override)
    assert axis in revised_axes(p)

    def always_adopt(_proposal: dict[str, Any]) -> ed.Finding:
        return ed.Finding(axis, "adopt", "neutralized")

    mutated = tuple(always_adopt if c.__name__ == check_name else c for c in ed.CHECKS)
    monkeypatch.setattr(ed, "CHECKS", mutated)
    assert axis not in revised_axes(p)


# Input validation


def test_non_object_proposal_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be an object"):
        ed.evaluate([])


def test_missing_keys_are_listed() -> None:
    with pytest.raises(ValueError, match="missing required keys: api_style, use_cases"):
        ed.evaluate({k: v for k, v in adopt_all().items() if k not in ("api_style", "use_cases")})


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("business_question", "   ", "non-empty string"),
        ("business_question", 3, "non-empty string"),
        ("state_representation", "guessed", "one of"),
        ("api_style", "rpc", "one of"),
        ("fact_is_first_class", "yes", "must be a boolean"),
        ("speculative_mechanism", 5, "string or null"),
        ("use_cases", [], "non-empty list"),
        ("use_cases", "q", "non-empty list"),
        ("use_cases", ["q"], "must be an object"),
        ("use_cases", [{"question": "", "needs_reconstruction": False}], "non-empty string"),
        ("use_cases", [{"question": "q", "needs_reconstruction": "no"}], "must be a boolean"),
    ],
)
def test_invalid_field_is_rejected(key: str, value: Any, message: str) -> None:
    p = adopt_all()
    p[key] = value
    with pytest.raises(ValueError, match=message):
        ed.evaluate(p)


# CLI


def run_cli(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True, check=False
    )


def test_cli_exits_zero_on_adopt(tmp_path: Path) -> None:
    f = tmp_path / "p.json"
    f.write_text(json.dumps(adopt_all()), encoding="utf-8")
    result = run_cli(f)
    assert result.returncode == ed.EXIT_ADOPT
    assert "Overall: adopt" in result.stdout


def test_cli_exits_one_on_revise(tmp_path: Path) -> None:
    p = adopt_all()
    p["temporal_question"] = True
    f = tmp_path / "p.json"
    f.write_text(json.dumps(p), encoding="utf-8")
    result = run_cli(f)
    assert result.returncode == ed.EXIT_REVISE
    assert "[REVISE] temporal" in result.stdout
    assert "Overall: revise" in result.stdout


def test_cli_exits_two_on_missing_file(tmp_path: Path) -> None:
    result = run_cli(tmp_path / "absent.json")
    assert result.returncode == ed.EXIT_BAD_INPUT
    assert "cannot read" in result.stderr


def test_cli_exits_two_on_invalid_json(tmp_path: Path) -> None:
    f = tmp_path / "p.json"
    f.write_text("{not json", encoding="utf-8")
    result = run_cli(f)
    assert result.returncode == ed.EXIT_BAD_INPUT
    assert "invalid JSON" in result.stderr


def test_cli_exits_two_on_invalid_proposal(tmp_path: Path) -> None:
    f = tmp_path / "p.json"
    f.write_text("[]", encoding="utf-8")
    result = run_cli(f)
    assert result.returncode == ed.EXIT_BAD_INPUT
    assert "must be an object" in result.stderr


def test_main_returns_codes_in_process(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "p.json"
    f.write_text(json.dumps(adopt_all()), encoding="utf-8")
    assert ed.main([str(f)]) == ed.EXIT_ADOPT
    assert "Overall: adopt" in capsys.readouterr().out


def test_main_reports_bad_input_in_process(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "absent.json"
    assert ed.main([str(missing)]) == ed.EXIT_BAD_INPUT
    assert "cannot read" in capsys.readouterr().err

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert ed.main([str(broken)]) == ed.EXIT_BAD_INPUT
    assert "invalid JSON" in capsys.readouterr().err

    wrong = tmp_path / "wrong.json"
    wrong.write_text("[]", encoding="utf-8")
    assert ed.main([str(wrong)]) == ed.EXIT_BAD_INPUT
    assert "must be an object" in capsys.readouterr().err


def test_main_returns_revise_in_process(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = adopt_all()
    p["temporal_question"] = True
    f = tmp_path / "p.json"
    f.write_text(json.dumps(p), encoding="utf-8")
    assert ed.main([str(f)]) == ed.EXIT_REVISE
    assert "[REVISE] temporal" in capsys.readouterr().out


def test_script_entry_point_exits_with_main_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "p.json"
    f.write_text(json.dumps(adopt_all()), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), str(f)])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert excinfo.value.code == ed.EXIT_ADOPT
