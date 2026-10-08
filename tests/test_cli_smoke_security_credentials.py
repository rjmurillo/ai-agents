"""Credential-scope tests for the PR-gated CLI smoke workflow (REQ-047 AC3, AC9).

Each leg's CLI step receives only its own credential; install and non-CLI steps
receive none.
"""

from __future__ import annotations

import shlex
from typing import Any

import pytest

from tests.lib.cli_smoke_workflow import (
    CLI_SECRET,
    CLIS,
    CREDENTIAL_STEPS,
    HOOK_STEP,
    INSTALL_STEP,
    PLUGIN_STEP,
    SECRET_NAMES,
    _step_by_name,
)

pytest_plugins = ["tests.lib.cli_smoke_fixtures"]


@pytest.mark.parametrize("cli", CLIS)
def test_install_step_has_no_secret_environment(smoke_job: dict[str, Any], cli: str) -> None:
    """Edge: a later workflow edit cannot reintroduce install-step secrets."""
    install = _step_by_name(smoke_job, INSTALL_STEP[cli])
    install_env = install.get("env") or {}

    assert SECRET_NAMES.isdisjoint(install_env)
    assert "secrets." not in install["run"]


@pytest.mark.parametrize("cli", CLIS)
@pytest.mark.parametrize("steps", [HOOK_STEP, PLUGIN_STEP], ids=["hook", "plugin"])
def test_cli_step_receives_only_its_own_credential(
    smoke_job: dict[str, Any], steps: dict[str, str], cli: str
) -> None:
    """Positive: a leg's CLI step gets exactly its provider secret and no other."""
    step = _step_by_name(smoke_job, steps[cli])

    assert set(step["env"]) == {CLI_SECRET[cli]}
    assert step["env"][CLI_SECRET[cli]] == f"${{{{ secrets.{CLI_SECRET[cli]} }}}}"
    assert f"matrix.cli == '{cli}'" in step["if"]


@pytest.mark.parametrize("cli", CLIS)
@pytest.mark.parametrize("steps", [HOOK_STEP, PLUGIN_STEP], ids=["hook", "plugin"])
def test_cli_step_selects_only_its_own_marker(
    smoke_job: dict[str, Any], steps: dict[str, str], cli: str
) -> None:
    """Negative: a leg cannot run the other provider's tests, which would skip."""
    arguments = shlex.split(_step_by_name(smoke_job, steps[cli])["run"])
    other = next(c for c in CLIS if c != cli)

    marker_expression = arguments[arguments.index("-m") + 1]
    assert marker_expression == f"smoke and {cli}"
    assert other not in marker_expression


def test_non_cli_steps_receive_no_credentials(smoke_job: dict[str, Any]) -> None:
    """Negative: credentials do not leak to checkout, setup, install, or checks."""
    for step in smoke_job["steps"]:
        if step.get("name") in CREDENTIAL_STEPS:
            continue
        step_env = step.get("env") or {}
        assert SECRET_NAMES.isdisjoint(step_env)


def test_credential_steps_exist_for_every_cli_and_smoke(smoke_job: dict[str, Any]) -> None:
    """Guard: the exemption list above cannot drift from the real step names."""
    names = {step.get("name") for step in smoke_job["steps"]}
    assert CREDENTIAL_STEPS <= names
    with_secrets = {s["name"] for s in smoke_job["steps"] if "secrets." in str(s.get("env"))}
    assert with_secrets == CREDENTIAL_STEPS
