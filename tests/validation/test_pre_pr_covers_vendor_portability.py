"""Bind pre_pr's gate list to the Validate Vendor Portability job (issue #5670).

Two canonical lists of the same validators exist and nothing joined them. The
CI job ``.github/workflows/validate-vendor-portability.yml`` runs six, and the
``_SEQUENCE`` in ``scripts/validation/pre_pr_sequence.py`` ran two. A branch
could clear every local gate and still turn that job red, which is what
happened on ``fix/4462-squash-merge-audit``: 65 of 65 gates green while
``check_skill_portability`` exited 1 for a skill script with no baseline entry.

The workflow is the source of truth here, not a constant copied out of it. Each
test below reads the YAML, so adding a seventh validator to the job fails these
tests until a pre_pr gate runs it too.

Why the tests assert on the argv reaching ``_run_subprocess`` rather than on a
name appearing in a module: ``check_skill_portability`` was already named in
``checks_spec.py`` before this fix, inside the docstring of
``validate_skill_md_portability``. Any grep-shaped check would have called the
gap covered. A gate proves it runs a validator only by executing it.

Negative controls, each verified to fail before shipping:

- Delete a row from ``_EXPECTED`` while the workflow still runs the command:
  ``test_every_workflow_validator_is_mapped`` fails.
- Delete a ``_Gate`` from ``_SEQUENCE``: ``test_mapped_gate_exists`` fails.
- Point a gate at a different validator: ``test_gate_runs_its_validator`` fails.
- Change the script or module a validator runs:
  ``test_gate_invokes_the_same_target_as_ci`` fails.
- Mark a gate ``skip_when_quick=True``: ``test_mapped_gate_is_never_skipped``
  fails.
- Add a seventh validator step to the workflow carrying ``if: always()``:
  ``test_workflow_still_defines_six_validators``,
  ``test_no_validator_step_is_conditional``, and
  ``test_every_workflow_validator_is_mapped`` all fail. Filtering steps on
  ``if`` rather than on shape would have made that step invisible, which is the
  silent direction to fail.

The job is not one of the ruleset's nine required status checks. It still
blocks: ``test_pr_merge_ready.py`` refuses to merge on a failed non-required
check with no entry in ``.agents/pr-checks/dispositions.json``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "validate-vendor-portability.yml"

# Import the pre-PR runner modules the way they are designed to be imported:
# add ``scripts/validation`` to ``sys.path`` and import by bare name. These
# modules self-insert their own directory and use bare intra-package imports
# (issue #2223). Insert once and leave it, matching production; see the longer
# note in test_pre_pr_model_pin_wiring.py for why restoring sys.path breaks the
# function-local imports in checks_tooling.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import checks_portability
import checks_spec
import pre_pr_sequence

# The six wrappers live in two modules: two predate this change in
# ``checks_spec``, four are new in ``checks_portability`` (see that module's
# docstring for why they did not join the first two). Resolution walks both so
# a later move between them does not need a test edit.
_VALIDATOR_MODULES = (checks_portability, checks_spec)

# Workflow command -> (pre_pr gate name, validator function name).
#
# Keyed on the command exactly as the workflow spells it, so a change to the
# invocation form (script to module, or a new flag) shows up here as an
# unmapped command rather than passing silently against a stale key.
_EXPECTED: dict[str, tuple[str, str]] = {
    "python3 scripts/validation/check_vendor_portability.py": (
        "Vendor Portability",
        "validate_vendor_portability",
    ),
    "python3 -m scripts.validation.check_skill_portability": (
        "Skill Script Portability",
        "validate_skill_script_portability",
    ),
    "uv run --frozen python scripts/validation/check_skill_md_exec_portability.py": (
        "Skill Markdown Exec Portability",
        "validate_skill_md_exec_portability",
    ),
    "uv run --frozen python scripts/validation/check_skill_md_portability.py": (
        "Skill Markdown Portability",
        "validate_skill_md_portability",
    ),
    "python3 scripts/validation/check_skill_resolver_anchoring.py": (
        "Skill Resolver Anchoring",
        "validate_skill_resolver_anchoring",
    ),
    "python3 scripts/validation/check_skill_contract_tests.py": (
        "Skill Contract Tests",
        "validate_skill_contract_tests",
    ),
}


def _run_steps() -> list[dict[str, Any]]:
    """Job steps that execute a command. Setup steps use ``uses:`` and have none."""
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["validate-portability"]["steps"]
    return [step for step in steps if "run" in step]


def _workflow_validator_commands() -> list[str]:
    """Every single-command ``run:`` step in the validate-portability job.

    Split on shape, not on ``if:``. The remediation step is the job's only
    multi-line ``run``, a block of ``echo`` lines that quotes several validator
    commands in its help text, so anything matching on the text would collect it
    as a seventh validator. Filtering on ``if`` instead would drop a real
    validator the day someone adds one with a condition, which is the silent
    direction to fail.

    ``test_only_the_remediation_step_is_multi_line`` holds the other half: a
    validator added as a multi-line step fails there rather than disappearing.
    """
    return [step["run"].strip() for step in _run_steps() if "\n" not in step["run"].strip()]


def _defining_module(name: str) -> Any:
    """Return the module that defines a wrapper.

    Stubbing ``_run_subprocess`` has to target the module the wrapper resolves
    it from. Patching the wrong one leaves the real subprocess running and turns
    an assertion about argv into an assertion about nothing.
    """
    for module in _VALIDATOR_MODULES:
        if getattr(module, name, None) is not None:
            return module
    raise AssertionError(f"no module defines {name!r}")


def _validator(name: str) -> Any:
    """Resolve a wrapper by name across the modules that define the six."""
    return getattr(_defining_module(name), name)


def _target_of(command: str) -> str:
    """Return the script path or module the command executes.

    Normalizes away the interpreter prefix, which differs across the workflow's
    own steps (``python3`` vs ``uv run --frozen python``) without changing which
    checker runs.
    """
    tokens = command.split()
    if "-m" in tokens:
        return tokens[tokens.index("-m") + 1]
    return next(token for token in tokens if token.endswith(".py"))


def _gate(name: str) -> Any:
    matches = [gate for gate in pre_pr_sequence._SEQUENCE if gate.name == name]
    assert len(matches) == 1, f"expected exactly one gate named {name!r}, got {len(matches)}"
    return matches[0]


def test_workflow_still_defines_six_validators() -> None:
    """Anchor the count so a silently dropped CI step is visible here too."""
    assert len(_workflow_validator_commands()) == 6


def test_only_the_remediation_step_is_multi_line() -> None:
    """The shape filter must exclude exactly one step, the help printer.

    A validator added as a multi-line ``run`` would slip past
    ``_workflow_validator_commands`` and never be checked for a pre_pr gate.
    """
    multi = [step for step in _run_steps() if "\n" in step["run"].strip()]
    assert len(multi) == 1, f"expected one multi-line run step, got {len(multi)}"
    assert multi[0].get("if") == "failure()"
    assert multi[0]["run"].strip().startswith("echo")


def test_no_validator_step_is_conditional() -> None:
    """A conditional validator would run in CI sometimes and pre_pr always.

    The mapping tests would still cover it, so this is about the CI side staying
    unconditional, the same property tests/ci/test_validate_vendor_portability_wiring.py
    asserts per known command.
    """
    conditional = [
        step["run"].strip()
        for step in _run_steps()
        if "\n" not in step["run"].strip() and "if" in step
    ]
    assert conditional == []


@pytest.mark.parametrize("command", _workflow_validator_commands())
def test_every_workflow_validator_is_mapped(command: str) -> None:
    """A validator CI runs must have a pre_pr gate, or this test names it."""
    assert command in _EXPECTED, (
        f"CI runs {command!r} but no pre_pr gate is mapped to it. Add a gate to "
        "scripts/validation/pre_pr_sequence.py and a row to _EXPECTED, or pre_pr "
        "will pass on branches this job rejects (issue #5670)."
    )


@pytest.mark.parametrize(("gate_name", "validator_name"), sorted(_EXPECTED.values()))
def test_mapped_gate_exists(gate_name: str, validator_name: str) -> None:
    """Every mapped gate is present in the sequence and names a real validator."""
    assert _gate(gate_name) is not None
    assert callable(_validator(validator_name))


@pytest.mark.parametrize(("gate_name", "validator_name"), sorted(_EXPECTED.values()))
def test_mapped_gate_is_never_skipped(gate_name: str, validator_name: str) -> None:
    """None of the six may be skippable, or the coverage claim is conditional.

    ``skip_when_quick`` drops a gate under ``--quick``, and ``already_run_by``
    drops it when the named pre-push fast-stage job set the environment marker.
    Either one would let a caller clear pre_pr without running a validator the
    CI job runs, which is the defect this file exists to prevent.
    """
    gate = _gate(gate_name)
    assert gate.skip_when_quick is False, f"{gate_name!r} is dropped by --quick"
    assert gate.already_run_by == "", f"{gate_name!r} defers to {gate.already_run_by!r}"


@pytest.mark.parametrize(("gate_name", "validator_name"), sorted(_EXPECTED.values()))
def test_gate_runs_its_validator(
    gate_name: str, validator_name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The gate calls the validator, proven by rebinding it to a spy.

    ``_root_only`` resolves the validator from ``pre_pr_sequence`` globals at
    call time precisely so a test can observe the call. A gate wired to some
    other validator, or to nothing, leaves ``calls`` empty.
    """
    calls: list[Path] = []

    def _spy(repo_root: Path) -> bool:
        calls.append(repo_root)
        return True

    monkeypatch.setattr(pre_pr_sequence, validator_name, _spy, raising=True)
    assert _gate(gate_name).run(tmp_path, SimpleNamespace()) is True
    assert calls == [tmp_path], f"gate {gate_name!r} did not call {validator_name}"


@pytest.mark.parametrize("command", sorted(_EXPECTED))
def test_gate_invokes_the_same_target_as_ci(
    command: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The validator shells out to the same script or module the CI job runs.

    Without this, a gate could carry the right name, call the right wrapper, and
    still run a different checker than the required job.
    """
    _gate_name, validator_name = _EXPECTED[command]
    seen: list[list[str]] = []

    def _fake_run(args: list[str], *_a: object, **_kw: object) -> tuple[int, str, str]:
        seen.append(args)
        return 0, "", ""

    monkeypatch.setattr(
        _defining_module(validator_name), "_run_subprocess", _fake_run, raising=True
    )
    assert _validator(validator_name)(REPO_ROOT) is True
    assert len(seen) == 1, f"{validator_name} ran {len(seen)} subprocesses, expected 1"
    argv = seen[0]
    target = _target_of(command)
    if target.endswith(".py"):
        assert argv[1] == str(REPO_ROOT / target), f"{validator_name} ran {argv[1]!r}"
    else:
        assert argv[1:3] == ["-m", target], f"{validator_name} ran {argv[1:3]!r}"


@pytest.mark.parametrize(("gate_name", "validator_name"), sorted(_EXPECTED.values()))
def test_validator_failure_fails_the_gate(
    gate_name: str, validator_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-zero exit from the wrapped checker fails, and is not swallowed.

    Covers exit 1 (drift) and exit 2 (configuration error); the CI job treats
    both as failures, so pre_pr must too.
    """
    for exit_code in (1, 2):
        monkeypatch.setattr(
            _defining_module(validator_name),
            "_run_subprocess",
            lambda *_a, _rc=exit_code, **_kw: (_rc, "drift", ""),
            raising=True,
        )
        assert _validator(validator_name)(REPO_ROOT) is False


@pytest.mark.parametrize(("gate_name", "validator_name"), sorted(_EXPECTED.values()))
def test_missing_checker_script_raises_missing_script_skip(
    gate_name: str, validator_name: str, tmp_path: Path
) -> None:
    """An absent checker is a deliberate skip, not a silent pass.

    ``tmp_path`` has no ``scripts/validation`` tree, so every wrapper must reach
    its existence check. Returning True here would let a pruned checker read as
    a passing gate.
    """
    with pytest.raises(checks_spec.MissingScriptSkip):
        _validator(validator_name)(tmp_path)


@pytest.mark.parametrize(("gate_name", "validator_name"), sorted(_EXPECTED.values()))
def test_validator_argv_is_accepted_by_the_real_checker(
    gate_name: str, validator_name: str
) -> None:
    """Run the real checker, because every other test here stubs the subprocess.

    Without this, a wrapper could pass a flag the script rejects and the stubbed
    assertions would still be green: argparse would exit 2 only in production.
    Slow by design: measured at 41.5s across the six, dominated by
    check_skill_md_portability at 26.3s. That is the price of the only
    assertions here that touch the actual checkers.
    """
    assert _validator(validator_name)(REPO_ROOT) is True
