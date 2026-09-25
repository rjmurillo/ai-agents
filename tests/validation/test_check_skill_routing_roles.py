"""Tests for the skill routing-role classification gate (REQ-038, DESIGN-036).

Every fixture is built in `tmp_path`. Each negative shape asserts the exit
code and the message, so a test cannot pass for the wrong reason (per
`.claude/rules/testing.md` SHOULD 10). Modeled on
`tests/validation/test_check_capability_graph.py`, the style model TASK-047
names for this gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_skill_routing_roles as gate

from tests.validation._skill_routing_fixtures import (
    _agent,
    _reference,
    _routing,
    _skill,
    tree_fixture,  # noqa: F401 (registers the `tree` pytest fixture)
)

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


def test_explicit_only_that_is_not_user_facing_fails(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(
        tree,
        "hidden",
        _routing(
            role="explicit-only", invoker="user", trigger="t", user_facing=False, rationale="r"
        ),
    )

    assert gate.validate_skill_routing_roles(tree) is False
    assert "explicit-only role requires `user-facing: true`" in capsys.readouterr().err


def test_bad_removal_issue_fails_even_with_a_valid_replaced_by(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    heir = _routing(role="front-door", invoker="harness", trigger="t", user_facing=True)
    _skill(tree, "heir", heir)
    _skill(tree, "dying", _routing(role="deprecated", replaced_by="heir", removal_issue=-1))

    assert gate.validate_skill_routing_roles(tree) is False
    assert "`removal-issue` value -1 is not a positive integer" in capsys.readouterr().err


def test_unknown_keys_of_mixed_types_fail_without_a_crash(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    block = _routing(role="front-door", invoker="harness", trigger="t", user_facing=True)
    _skill(tree, "mixed", block + "\n    1: x\n    foo: y")

    assert gate.main(["--repo-root", str(tree)]) == 1
    assert "unknown routing key(s) `1`, `foo`" in capsys.readouterr().err
