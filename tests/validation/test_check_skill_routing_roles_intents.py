"""Tests for the `intents` gate (REQ-039 criterion 11, DESIGN-037).

Split out of `test_check_skill_routing_roles.py` (taste-lint file-size
ceiling) once these cases pushed that file past 500 lines. Shares its
fixtures from `_skill_routing_fixtures.py`, the same way
`test_skill_routing_report.py` already splits report-layer tests out of the
core gate tests.
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
    _routing,
    _skill,
    tree_fixture,  # noqa: F401 (registers the `tree` pytest fixture)
)


def test_intents_on_front_door_passes(tree: Path) -> None:
    _skill(
        tree,
        "specialist",
        _routing(
            role="front-door",
            invoker="harness",
            trigger="t",
            user_facing=True,
            intents=["developer experience", "developer friction"],
        ),
    )

    assert gate.validate_skill_routing_roles(tree) is True


def test_intents_on_a_non_front_door_role_fails(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _skill(
        tree,
        "helper",
        _routing(
            role="nested-helper",
            invoker="build",
            trigger="t",
            user_facing=False,
            intents=["some intent"],
        ),
    )

    assert gate.validate_skill_routing_roles(tree) is False
    err = capsys.readouterr().err
    assert "`intents` is only valid on role `front-door`, not `nested-helper`" in err


def test_intents_non_list_fails(tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _skill(
        tree,
        "specialist",
        _routing(
            role="front-door", invoker="autoplan", trigger="t", user_facing=True, intents="oops"
        ),
    )

    assert gate.validate_skill_routing_roles(tree) is False
    assert "`intents` must be a non-empty list of non-empty strings" in capsys.readouterr().err


def test_intents_empty_list_fails(tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _skill(
        tree,
        "specialist",
        _routing(role="front-door", invoker="autoplan", trigger="t", user_facing=True, intents=[]),
    )

    assert gate.validate_skill_routing_roles(tree) is False
    assert "`intents` must be a non-empty list of non-empty strings" in capsys.readouterr().err


def test_intents_empty_string_item_fails(tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _skill(
        tree,
        "specialist",
        _routing(
            role="front-door",
            invoker="autoplan",
            trigger="t",
            user_facing=True,
            intents=["developer experience", "   "],
        ),
    )

    assert gate.validate_skill_routing_roles(tree) is False
    err = capsys.readouterr().err
    assert "`intents` item" in err
    assert "must be a non-empty string" in err
