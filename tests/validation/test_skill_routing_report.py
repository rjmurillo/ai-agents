"""Tests for the skill routing-role gate: key shapes, scenario paths, the
report, and the CLI (REQ-038 criteria 10 to 12, DESIGN-036 evidence layers).

Split from `test_check_skill_routing_roles.py` to keep each file under the
500-line taste limit. Fixtures live in `_skill_routing_fixtures.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_skill_routing_roles as gate

from tests.validation._skill_routing_fixtures import (
    _routing,
    _scenario_file,
    _skill,
    tree_fixture,  # noqa: F401 (registers the `tree` pytest fixture)
)

# ---------------------------------------------------------------------------
# Missing required keys / wrong types / empty trigger
# ---------------------------------------------------------------------------


def test_missing_required_keys_fails_and_lists_them(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(tree, "incomplete", "metadata:\n  routing:\n    role: front-door")

    assert gate.validate_skill_routing_roles(tree) is False
    err = capsys.readouterr().err
    assert "missing required routing key(s):" in err
    assert "invoker" in err
    assert "trigger" in err
    assert "user-facing" in err


def test_user_facing_wrong_type_fails(tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _skill(
        tree,
        "odd-type",
        "metadata:\n  routing:\n    role: front-door\n    invoker: harness\n"
        '    trigger: t\n    user-facing: "yes"',
    )

    assert gate.validate_skill_routing_roles(tree) is False
    assert "user-facing is str, not a boolean" in capsys.readouterr().err


def test_invoker_wrong_type_fails(tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _skill(
        tree,
        "odd-invoker",
        "metadata:\n  routing:\n    role: front-door\n    invoker: 7\n"
        "    trigger: t\n    user-facing: true",
    )

    assert gate.validate_skill_routing_roles(tree) is False
    assert "invoker is int, not a string" in capsys.readouterr().err


def test_empty_trigger_fails(tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _skill(
        tree,
        "no-trigger",
        "metadata:\n  routing:\n    role: front-door\n    invoker: harness\n"
        '    trigger: ""\n    user-facing: true',
    )

    assert gate.validate_skill_routing_roles(tree) is False
    assert "trigger must be a non-empty string" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Scenario override path
# ---------------------------------------------------------------------------


def test_scenario_override_under_tests_evals_passes(tree: Path) -> None:
    _skill(
        tree,
        "renamed",
        _routing(
            role="explicit-only",
            invoker="user",
            trigger="t",
            user_facing=True,
            rationale="Explicit only; scenario file lives under a different name.",
            scenario="tests/evals/skill-scenarios/renamed-alt.json",
        ),
    )

    assert gate.validate_skill_routing_roles(tree) is True


@pytest.mark.parametrize(
    "bad_scenario",
    [
        "../outside.json",
        "/etc/passwd",
        "docs/skill-scenarios/renamed.json",
    ],
)
def test_scenario_override_outside_tests_evals_fails(
    tree: Path, capsys: pytest.CaptureFixture[str], bad_scenario: str
) -> None:
    _skill(
        tree,
        "renamed",
        _routing(
            role="explicit-only",
            invoker="user",
            trigger="t",
            user_facing=True,
            rationale="Explicit only; scenario path under test is illegal.",
            scenario=bad_scenario,
        ),
    )

    assert gate.validate_skill_routing_roles(tree) is False
    assert "must be a relative path under tests/evals/" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Report: totals, unresolved, inbound-zero, reachability, scenario coverage,
# scored-accuracy line, JSON, determinism, sorted order.
# ---------------------------------------------------------------------------


def _report_catalog(tree: Path) -> None:
    _skill(
        tree,
        "autoplan",
        _routing(role="front-door", invoker="harness", trigger="t", user_facing=True),
        body="Routes to build.",
    )
    _skill(
        tree,
        "build",
        _routing(role="front-door", invoker="autoplan", trigger="t", user_facing=True),
        body="One of the six lifecycle skills; autoplan routes here.",
    )
    # No skill or agent text mentions "solo-thing", so it is inbound-zero AND
    # unresolved (its invoker's text never names it either).
    _skill(
        tree,
        "solo-thing",
        _routing(
            role="nested-helper", invoker="build", trigger="build calls this", user_facing=False
        ),
        body="A helper nobody's prose mentions by name.",
    )
    _skill(
        tree,
        "explicit-thing",
        _routing(
            role="explicit-only",
            invoker="user",
            trigger="t",
            user_facing=True,
            rationale="Reachable only by direct user request.",
        ),
    )


def test_report_totals_by_role(tree: Path) -> None:
    _report_catalog(tree)

    skills, _findings, evidence = gate.survey(tree)
    text = gate.render(skills, evidence, "text")

    assert "skills: 4" in text
    assert "role front-door: 2" in text
    assert "role lifecycle: 0" in text
    assert "role nested-helper: 1" in text
    assert "role explicit-only: 1" in text
    assert "role conditional-adjunct: 0" in text
    assert "role deprecated: 0" in text


def test_report_lists_unresolved_skills(tree: Path) -> None:
    _report_catalog(tree)

    _skills, _findings, evidence = gate.survey(tree)

    assert "solo-thing" in evidence.unresolved


def test_report_lists_inbound_zero_skills(tree: Path) -> None:
    _report_catalog(tree)

    _skills, _findings, evidence = gate.survey(tree)

    assert "solo-thing" in evidence.inbound_zero


def test_routing_block_naming_a_skill_is_not_an_inbound_reference(tree: Path) -> None:
    # A rationale or trigger that names another skill must not count, or the
    # manifest would certify its own reachability.
    _report_catalog(tree)
    _skill(
        tree,
        "namer",
        _routing(
            role="explicit-only",
            invoker="user",
            trigger="after solo-thing runs",
            user_facing=True,
            rationale="Composes solo-thing later.",
        ),
    )

    _skills, _findings, evidence = gate.survey(tree)

    assert "solo-thing" in evidence.inbound_zero
    assert "solo-thing" in evidence.unresolved


def test_body_text_naming_a_skill_is_an_inbound_reference(tree: Path) -> None:
    _report_catalog(tree)
    _skill(
        tree,
        "namer",
        _routing(
            role="explicit-only", invoker="user", trigger="t", user_facing=True, rationale="r"
        ),
        body="Step 2: invoke solo-thing.",
    )

    _skills, _findings, evidence = gate.survey(tree)

    assert "solo-thing" not in evidence.inbound_zero


def test_report_prints_unresolved_and_inbound_zero_counts(tree: Path) -> None:
    _report_catalog(tree)

    skills, _findings, evidence = gate.survey(tree)
    text = gate.render(skills, evidence, "text")

    assert "unresolved: 1" in text
    assert "inbound-zero: " in text


def test_reachability_counted_by_declaration_for_user_and_harness(tree: Path) -> None:
    _report_catalog(tree)

    _skills, _findings, evidence = gate.survey(tree)

    # autoplan (role=front-door, invoker=harness) is counted checked and
    # reachable without a text search (DESIGN-036: "user and harness routes
    # count as reachable by declaration").
    assert "autoplan" in evidence.checked
    assert "autoplan" not in evidence.unresolved
    # explicit-only is not one of the four reachable roles (front-door,
    # lifecycle, conditional-adjunct, nested-helper), so it is never checked
    # at all: nothing routes to it by prose, the user names it directly.
    assert "explicit-thing" not in evidence.checked


def test_scenario_coverage_counts_only_present_files(tree: Path) -> None:
    _report_catalog(tree)
    _scenario_file(tree, "tests/evals/skill-scenarios/build.json")

    _skills, _findings, evidence = gate.survey(tree)

    assert evidence.scenario_covered == ("build",)


def test_scored_accuracy_line_says_not_measured_in_text_and_json(tree: Path) -> None:
    _report_catalog(tree)

    skills, _findings, evidence = gate.survey(tree)
    text = gate.render(skills, evidence, "text")
    payload = json.loads(gate.render(skills, evidence, "json"))

    assert "scored accuracy: not measured" in text
    assert payload["scored_accuracy"] == "not measured"


def test_json_report_is_valid_json_with_expected_shape(tree: Path) -> None:
    _report_catalog(tree)

    skills, _findings, evidence = gate.survey(tree)
    payload = json.loads(gate.render(skills, evidence, "json"))

    assert set(payload) == {"skills", "counts", "unresolved", "inbound_zero", "scored_accuracy"}
    assert payload["counts"]["total"] == 4


def test_report_is_byte_identical_across_runs(tree: Path) -> None:
    _report_catalog(tree)

    first_skills, _f1, first_evidence = gate.survey(tree)
    second_skills, _f2, second_evidence = gate.survey(tree)

    for fmt in ("text", "json"):
        assert gate.render(first_skills, first_evidence, fmt) == gate.render(
            second_skills, second_evidence, fmt
        )


def test_evidence_lists_are_sorted(tree: Path) -> None:
    _report_catalog(tree)

    _skills, _findings, evidence = gate.survey(tree)

    assert list(evidence.unresolved) == sorted(evidence.unresolved)
    assert list(evidence.inbound_zero) == sorted(evidence.inbound_zero)
    assert list(evidence.scenario_covered) == sorted(evidence.scenario_covered)
    assert list(evidence.checked) == sorted(evidence.checked)


# ---------------------------------------------------------------------------
# CLI / config errors
# ---------------------------------------------------------------------------


def test_missing_templates_skills_tree_is_a_config_error(tmp_path: Path) -> None:
    assert gate.main(["--repo-root", str(tmp_path)]) == 2


def test_empty_templates_skills_tree_is_a_config_error(tmp_path: Path) -> None:
    (tmp_path / "templates" / "skills").mkdir(parents=True)

    assert gate.main(["--repo-root", str(tmp_path)]) == 2


def test_invalid_repo_root_is_a_config_error(tmp_path: Path) -> None:
    assert gate.main(["--repo-root", str(tmp_path / "does-not-exist")]) == 2


def test_cli_returns_one_on_a_violation(tree: Path) -> None:
    _skill(tree, "bare", "version: 1.0.0")

    assert gate.main(["--repo-root", str(tree)]) == 1


def test_cli_returns_zero_on_a_clean_tree(tree: Path) -> None:
    _skill(
        tree,
        "solo",
        _routing(
            role="explicit-only",
            invoker="user",
            trigger="t",
            user_facing=True,
            rationale="Only invoked directly by the user.",
        ),
    )

    assert gate.main(["--repo-root", str(tree)]) == 0


def test_cli_report_json_flag_prints_and_returns_zero(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(
        tree,
        "solo",
        _routing(
            role="explicit-only",
            invoker="user",
            trigger="t",
            user_facing=True,
            rationale="Only invoked directly by the user.",
        ),
    )

    assert gate.main(["--repo-root", str(tree), "--report", "--format", "json"]) == 0
    out = capsys.readouterr().out
    assert '"scored_accuracy"' in out
    json.loads(out)  # must be valid JSON


def test_cli_report_text_flag_prints_and_returns_zero(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(
        tree,
        "solo",
        _routing(
            role="explicit-only",
            invoker="user",
            trigger="t",
            user_facing=True,
            rationale="Only invoked directly by the user.",
        ),
    )

    assert gate.main(["--repo-root", str(tree), "--report"]) == 0
    assert "scored accuracy: not measured" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Real repository
# ---------------------------------------------------------------------------


def test_the_real_repository_passes_the_gate() -> None:
    """A gate must eventually be green against the corpus it ships with
    (ci-scripts MUST 13).

    This currently fails: TASK-047 step 4 (adding a `metadata.routing` block
    to every `templates/skills/*.SKILL.md.tmpl`) is being done in a parallel
    change and has not landed on this branch yet. That is expected here, not
    a defect in this test; issue #5384 tracks the classification work. This
    test is written as a plain assertion, not skipped or marked xfail, so CI
    shows the true state of the catalog once both changes land together.
    """
    assert gate.validate_skill_routing_roles(_REPO_ROOT) is True


@pytest.mark.parametrize(
    "rationale_block",
    [
        # Four-space indentation under metadata.
        "metadata:\n    routing:\n        role: explicit-only\n        invoker: user\n"
        "        trigger: t\n        user-facing: true\n        rationale: after solo-thing",
        # Inline flow mapping.
        "metadata:\n  routing: {role: explicit-only, invoker: user, trigger: t, "
        "user-facing: true, rationale: after solo-thing}",
    ],
)
def test_routing_block_in_any_yaml_form_is_not_an_inbound_reference(
    tree: Path, rationale_block: str
) -> None:
    _report_catalog(tree)
    _skill(tree, "namer", rationale_block)

    _skills, findings, evidence = gate.survey(tree)

    assert findings == []
    assert "solo-thing" in evidence.inbound_zero
