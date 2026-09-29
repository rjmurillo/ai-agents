#!/usr/bin/env python3
"""Pre-PR gates for validators that pull-request workflows run and pre_pr did not.

Issue #5676. Issue #5670 found four ``Validate Vendor Portability`` validators
with no ``pre_pr.py`` gate, and PR #5673 fixed that job alone. Every other
workflow still had the hole: a validator added to a workflow did not have to be
added here, and a branch could print "RESULT: All validations passed" and then
fail a required check, including ``Validate Generated Files`` and ``Validate PR``.

Each wrapper runs the same command the workflow runs, from the repository root,
so a local pass predicts the remote result.
``tests/validation/test_pre_pr_covers_workflow_validators.py`` reads every
pull-request workflow and fails when one runs a validator that neither a gate
here nor the exemption table in that test accounts for.

The wrappers live in their own module because ``checks_spec.py`` is at the
500-line ceiling ``scripts/ci/taste_count_ratchet.py`` enforces.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import (  # noqa: E402
    MissingScriptSkip,
    _resolve_default_base_ref,
    _run_subprocess,
)

_REPORT_LINES = 40


def _run_workflow_validator(repo_root: Path, relative: str, *args: str, module: str = "") -> bool:
    """Run one validator the way its workflow does and report a clean exit.

    ``module`` selects the ``-m`` form for a validator the workflow runs as a
    module. ``cwd`` is the repository root, as in CI. A missing script raises
    :class:`MissingScriptSkip`, so a downstream install without the validator
    reports SKIP rather than a misleading FAIL.
    """
    script = repo_root / relative
    if not script.exists():
        raise MissingScriptSkip(f"{relative} not present")
    target = ["-m", module] if module else [str(script)]
    exit_code, stdout, stderr = _run_subprocess([sys.executable, *target, *args], cwd=repo_root)
    output = ((stdout or "") + (stderr or "")).strip()
    if output:
        for line in output.splitlines()[:_REPORT_LINES]:
            print(line)
    return bool(exit_code == 0)


def _base_ref_or_skip(repo_root: Path, label: str) -> str:
    base_ref = _resolve_default_base_ref(repo_root)
    if base_ref is None:
        raise MissingScriptSkip(f"{label} needs a base ref and none resolved")
    return base_ref


def validate_agent_registry(repo_root: Path) -> bool:
    """Fail when the agent registry disagrees with the agent tree (``Validate Generated Files``)."""
    return _run_workflow_validator(repo_root, "scripts/validation/agent_registry.py")


def validate_plugin_frontmatter_self_containment(repo_root: Path) -> bool:
    """Fail when a shipped description names an upstream-only path (issue #3565)."""
    return _run_workflow_validator(
        repo_root, "scripts/validation/check_plugin_frontmatter_self_containment.py"
    )


def validate_python3_entrypoints(repo_root: Path) -> bool:
    """Fail when a plugin-shipped entry point is not bare ``python3`` (``Validate PR``)."""
    return _run_workflow_validator(repo_root, "scripts/validation/check_python3_entrypoints.py")


def validate_adr_uniqueness(repo_root: Path) -> bool:
    """Fail when two ADRs claim one number."""
    return _run_workflow_validator(repo_root, "scripts/validation/check_adr_uniqueness.py")


def validate_agent_skill_discriminator(repo_root: Path) -> bool:
    """Fail when an agent lacks a discriminator against a skill (whole corpus)."""
    return _run_workflow_validator(
        repo_root,
        "scripts/validation/check_agent_skill_discriminator.py",
        "--all",
        "--baseline",
        "scripts/validation/agent_skill_discriminator_baseline.json",
    )


def validate_hook_contracts(repo_root: Path) -> bool:
    """Fail when a hook breaks its declared contract."""
    return _run_workflow_validator(repo_root, "scripts/validation/hook_contracts.py", "--ci")


def validate_passive_context_budget(repo_root: Path) -> bool:
    """Fail when passive context grows past its budget."""
    return _run_workflow_validator(
        repo_root,
        "scripts/validation/passive_context_budget.py",
        "--ci",
        module="scripts.validation.passive_context_budget",
    )


def validate_skillbook(repo_root: Path) -> bool:
    """Fail when the skillbook is malformed."""
    return _run_workflow_validator(repo_root, "scripts/validation/validate_skillbook.py")


def validate_sha_pinning(repo_root: Path) -> bool:
    """Fail when a GitHub Actions reference is not pinned to a commit SHA."""
    return _run_workflow_validator(repo_root, "scripts/validation/sha_pinning.py", "--ci")


def validate_placeholder_identity(repo_root: Path) -> bool:
    """Fail when a commit on this branch carries a placeholder identity."""
    base_ref = _base_ref_or_skip(repo_root, "placeholder identity check")
    return _run_workflow_validator(
        repo_root,
        "scripts/validation/check_placeholder_identity.py",
        "--push-range",
        f"{base_ref}..HEAD",
        "--repo-root",
        ".",
    )


def validate_tracked_conflict_markers(repo_root: Path) -> bool:
    """Fail when a tracked file still holds a merge conflict marker (``Validate PR``)."""
    return _run_workflow_validator(
        repo_root, "scripts/validation/git_hook_policy.py", "tracked-conflict-markers"
    )


def validate_security_suppressions_diff(repo_root: Path) -> bool:
    """Fail when the branch adds a security-scanner suppression."""
    base_ref = _base_ref_or_skip(repo_root, "security suppression diff")
    return _run_workflow_validator(
        repo_root,
        "scripts/validation/git_hook_policy.py",
        "security-suppressions-diff",
        "--base-ref",
        base_ref,
    )
