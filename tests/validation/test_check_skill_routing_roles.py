"""Tests for the skill routing-role classification gate (REQ-038, DESIGN-036).

Every fixture is built in `tmp_path`. Each negative shape asserts the exit
code and the message, so a test cannot pass for the wrong reason (per
`.claude/rules/testing.md` SHOULD 10). Modeled on
`tests/validation/test_check_capability_graph.py`, the style model TASK-047
names for this gate.
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


def _routing(**fields: object) -> str:
    """Render one metadata.routing block as frontmatter lines."""
    lines = ["metadata:", "  routing:"]
    for key, value in fields.items():
        name = key.replace("_", "-")
        if isinstance(value, bool):
            lines.append(f"    {name}: {'true' if value else 'false'}")
        else:
            lines.append(f"    {name}: {value}")
    return "\n".join(lines)


def _skill(
    root: Path,
    name: str,
    block: str,
    body: str = "Body text.",
    *,
    user_invocable: bool | None = None,
) -> Path:
    path = root / "templates" / "skills" / f"{name}.SKILL.md.tmpl"
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = "" if user_invocable is None else f"user-invocable: {str(user_invocable).lower()}\n"
    path.write_text(f"---\nname: {name}\n{extra}{block}\n---\n\n{body}\n", encoding="utf-8")
    return path


def _agent(root: Path, name: str, body: str = "Agent body.") -> Path:
    path = root / "templates" / "agents" / f"{name}.shared.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nrole: support\n---\n\n{body}\n", encoding="utf-8")
    return path


def _reference(root: Path, skill_name: str, filename: str, body: str) -> Path:
    path = root / ".claude" / "skills" / skill_name / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _scenario_file(root: Path, rel: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    return path


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "templates" / "skills").mkdir(parents=True)
    (tmp_path / "templates" / "agents").mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Passing catalog
# ---------------------------------------------------------------------------


def test_valid_catalog_passes(tree: Path) -> None:
    # "build" is one of the six lifecycle skills: autoplan routes to it, so
    # its own role is front-door (DESIGN-036: "The six lifecycle skills are
    # front-door: autoplan routes to them.").
    _skill(
        tree,
        "autoplan",
        _routing(role="front-door", invoker="harness", trigger="user request", user_facing=True),
        body="Routes concrete requests to spec, plan, build, test, review, ship.",
    )
    _skill(
        tree,
        "build",
        _routing(role="front-door", invoker="autoplan", trigger="implement", user_facing=True),
        body="One of the six lifecycle skills. Uses build-helper and nested-thing.",
    )
    # A skill a lifecycle skill selects is itself `lifecycle`.
    _skill(
        tree,
        "build-helper",
        _routing(
            role="lifecycle", invoker="build", trigger="build delegates to this", user_facing=False
        ),
        body="Selected only by build.",
    )
    _skill(
        tree,
        "nested-thing",
        _routing(
            role="nested-helper",
            invoker="build",
            trigger="build calls this internally",
            user_facing=False,
        ),
        body="A helper invoked only by build.",
    )
    _skill(
        tree,
        "explicit-thing",
        _routing(
            role="explicit-only",
            invoker="user",
            trigger="user says do explicit-thing",
            user_facing=True,
            rationale="No other skill or agent routes to it; only a direct user request does.",
        ),
        body="Invoke this only by name.",
    )
    _skill(
        tree,
        "old-thing",
        _routing(role="deprecated", replaced_by="build"),
        body="Deprecated; build replaces it.",
    )

    assert gate.validate_skill_routing_roles(tree) is True


# ---------------------------------------------------------------------------
# REQ-038 criterion 2: missing block
# ---------------------------------------------------------------------------


def test_missing_routing_block_fails_and_names_the_skill(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(tree, "bare", "version: 1.0.0")

    assert gate.validate_skill_routing_roles(tree) is False
    err = capsys.readouterr().err
    assert "bare.SKILL.md.tmpl" in err
    assert "has no `metadata.routing` block" in err


def test_a_non_mapping_routing_block_fails(tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _skill(tree, "odd", "metadata:\n  routing: not-a-mapping")

    assert gate.validate_skill_routing_roles(tree) is False
    assert "`metadata.routing` is str, not a mapping" in capsys.readouterr().err


def test_an_empty_routing_block_fails_on_missing_role(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(tree, "hollow", "metadata:\n  routing: {}")

    assert gate.validate_skill_routing_roles(tree) is False
    assert "missing required routing key: role" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# REQ-038 criterion 3: bad role
# ---------------------------------------------------------------------------


def test_unknown_role_fails(tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _skill(
        tree,
        "odd-role",
        _routing(role="wizard", invoker="harness", trigger="t", user_facing=True),
    )

    assert gate.validate_skill_routing_roles(tree) is False
    assert "role `wizard` is not one of" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# REQ-038 criterion 4: unknown key
# ---------------------------------------------------------------------------


def test_unknown_routing_key_fails(tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _skill(
        tree,
        "typo",
        _routing(
            role="front-door", invoker="harness", trigger="t", user_facing=True, bogus="1"
        ),
    )

    assert gate.validate_skill_routing_roles(tree) is False
    assert "unknown routing key(s) `bogus`" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# REQ-038 criterion 5: unknown invoker
# ---------------------------------------------------------------------------


def test_unknown_invoker_fails(tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _skill(
        tree,
        "orphan",
        _routing(
            role="nested-helper",
            invoker="nonexistent-thing",
            trigger="t",
            user_facing=False,
        ),
    )

    assert gate.validate_skill_routing_roles(tree) is False
    err = capsys.readouterr().err
    assert "invoker `nonexistent-thing`" in err
    assert "is not a canonical skill, agent, `user`, or `harness`" in err


def test_a_canonical_agent_is_a_legal_invoker(tree: Path) -> None:
    _agent(tree, "analyst")
    _skill(
        tree,
        "helper-for-analyst",
        _routing(
            role="nested-helper",
            invoker="analyst",
            trigger="analyst calls helper-for-analyst",
            user_facing=False,
        ),
        body="Uses helper-for-analyst internally.",
    )
    _reference(
        tree, "analyst", "notes.md", "This uses helper-for-analyst for research."
    )

    assert gate.validate_skill_routing_roles(tree) is True


# ---------------------------------------------------------------------------
# REQ-038 criterion 6: role/invoker contradictions
# ---------------------------------------------------------------------------


def test_front_door_not_invoked_by_autoplan_or_harness_fails(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(
        tree, "build", _routing(role="lifecycle", invoker="autoplan", trigger="t", user_facing=True)
    )
    _skill(
        tree,
        "not-front-door",
        _routing(role="front-door", invoker="build", trigger="t", user_facing=True),
    )

    assert gate.validate_skill_routing_roles(tree) is False
    assert "role `front-door` must be invoked by `autoplan` or `harness`" in capsys.readouterr().err


def test_lifecycle_not_invoked_by_a_lifecycle_skill_fails(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(
        tree,
        "not-lifecycle",
        _routing(role="lifecycle", invoker="harness", trigger="t", user_facing=True),
    )

    assert gate.validate_skill_routing_roles(tree) is False
    assert "role `lifecycle` must be invoked by one of" in capsys.readouterr().err


@pytest.mark.parametrize("role", ["conditional-adjunct", "nested-helper"])
def test_adjunct_or_helper_invoked_by_user_fails(
    tree: Path, capsys: pytest.CaptureFixture[str], role: str
) -> None:
    _skill(tree, "victim", _routing(role=role, invoker="user", trigger="t", user_facing=False))

    assert gate.validate_skill_routing_roles(tree) is False
    err = capsys.readouterr().err
    assert f"role `{role}` must not be invoked by `user`, `harness`, or itself" in err


@pytest.mark.parametrize("role", ["conditional-adjunct", "nested-helper"])
def test_adjunct_or_helper_invoked_by_harness_fails(
    tree: Path, capsys: pytest.CaptureFixture[str], role: str
) -> None:
    _skill(tree, "victim", _routing(role=role, invoker="harness", trigger="t", user_facing=False))

    assert gate.validate_skill_routing_roles(tree) is False
    assert "must not be invoked by `user`, `harness`, or itself" in capsys.readouterr().err


@pytest.mark.parametrize("role", ["conditional-adjunct", "nested-helper"])
def test_adjunct_or_helper_invoked_by_itself_fails(
    tree: Path, capsys: pytest.CaptureFixture[str], role: str
) -> None:
    """Self-invoker edge case (REQ-038 criterion 12)."""
    _skill(
        tree,
        "narcissist",
        _routing(role=role, invoker="narcissist", trigger="t", user_facing=False),
    )

    assert gate.validate_skill_routing_roles(tree) is False
    err = capsys.readouterr().err
    assert "narcissist.SKILL.md.tmpl" in err
    assert "must not be invoked by `user`, `harness`, or itself" in err
    assert "got `narcissist`" in err


def test_explicit_only_not_invoked_by_user_fails(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(
        tree,
        "should-be-explicit",
        _routing(
            role="explicit-only",
            invoker="harness",
            trigger="t",
            user_facing=True,
            rationale="Only reachable by direct name, so no invoker names it.",
        ),
    )

    assert gate.validate_skill_routing_roles(tree) is False
    assert "role `explicit-only` must be invoked by `user`" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# REQ-038 criterion 7: missing explicit-only rationale
# ---------------------------------------------------------------------------


def test_explicit_only_with_no_rationale_fails(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(
        tree,
        "unexplained",
        _routing(role="explicit-only", invoker="user", trigger="t", user_facing=True),
    )

    assert gate.validate_skill_routing_roles(tree) is False
    assert "requires a non-empty `rationale`" in capsys.readouterr().err


def test_explicit_only_with_blank_rationale_fails(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(
        tree,
        "blank-rationale",
        _routing(
            role="explicit-only", invoker="user", trigger="t", user_facing=True, rationale="   "
        ),
    )

    assert gate.validate_skill_routing_roles(tree) is False
    assert "requires a non-empty `rationale`" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# REQ-038 criterion 8: deprecated retirement keys
# ---------------------------------------------------------------------------


def test_deprecated_without_replaced_by_or_removal_issue_fails(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(tree, "dying", "metadata:\n  routing:\n    role: deprecated")

    assert gate.validate_skill_routing_roles(tree) is False
    assert "declares neither a resolvable `replaced-by`" in capsys.readouterr().err


def test_deprecated_with_positive_removal_issue_passes(tree: Path) -> None:
    _skill(tree, "dying", _routing(role="deprecated", removal_issue=42))

    assert gate.validate_skill_routing_roles(tree) is True


def test_deprecated_removal_issue_non_positive_fails(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(tree, "dying", _routing(role="deprecated", removal_issue=-1))

    assert gate.validate_skill_routing_roles(tree) is False
    assert "is not a positive integer" in capsys.readouterr().err


def test_deprecated_removal_issue_non_int_fails(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(
        tree,
        "dying",
        "metadata:\n  routing:\n    role: deprecated\n    removal-issue: not-a-number",
    )

    assert gate.validate_skill_routing_roles(tree) is False
    assert "is not a positive integer" in capsys.readouterr().err


def test_deprecated_removal_issue_bool_true_is_not_a_valid_int(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Edge case: `bool` is an `int` subclass in Python; must not pass as positive."""
    _skill(tree, "dying", "metadata:\n  routing:\n    role: deprecated\n    removal-issue: true")

    assert gate.validate_skill_routing_roles(tree) is False
    assert "is not a positive integer" in capsys.readouterr().err


def test_deprecated_replaced_by_pointing_at_an_unknown_skill_fails(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(tree, "dying", _routing(role="deprecated", replaced_by="ghost"))

    assert gate.validate_skill_routing_roles(tree) is False
    assert "replaced-by `ghost` names no known skill" in capsys.readouterr().err


def test_deprecated_replaced_by_pointing_at_a_deprecated_skill_fails(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(tree, "also-dying", _routing(role="deprecated", removal_issue=1))
    _skill(tree, "dying", _routing(role="deprecated", replaced_by="also-dying"))

    assert gate.validate_skill_routing_roles(tree) is False
    assert "replaced-by `also-dying` names a deprecated skill" in capsys.readouterr().err


def test_deprecated_with_no_invoker_passes(tree: Path) -> None:
    """Edge case (REQ-038 criterion 12): deprecated skills need no invoker."""
    _skill(tree, "dying", "metadata:\n  routing:\n    role: deprecated\n    removal-issue: 7")

    assert gate.validate_skill_routing_roles(tree) is True


# ---------------------------------------------------------------------------
# REQ-038 criterion 9: user-facing vs user-invocable
# ---------------------------------------------------------------------------


def test_user_facing_true_on_a_non_user_invocable_skill_fails(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(
        tree, "build", _routing(role="front-door", invoker="harness", trigger="t", user_facing=True)
    )
    _skill(
        tree,
        "internal-only",
        _routing(
            role="nested-helper", invoker="build", trigger="build calls this", user_facing=True
        ),
        body="Uses internal-only.",
        user_invocable=False,
    )

    assert gate.validate_skill_routing_roles(tree) is False
    err = capsys.readouterr().err
    assert "internal-only.SKILL.md.tmpl" in err
    assert "user-facing is true but frontmatter sets user-invocable: false" in err


def test_user_facing_false_on_a_non_user_invocable_skill_passes(tree: Path) -> None:
    _skill(
        tree, "build", _routing(role="front-door", invoker="harness", trigger="t", user_facing=True)
    )
    _skill(
        tree,
        "internal-only",
        _routing(
            role="nested-helper", invoker="build", trigger="build calls this", user_facing=False
        ),
        body="Uses internal-only.",
        user_invocable=False,
    )

    assert gate.validate_skill_routing_roles(tree) is True


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
