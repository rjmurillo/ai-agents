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

The pre-push hook is the second source of gates. ``lefthook.yml`` runs jobs the
pull-request workflows do not, and a job pre_pr never runs costs a rejected
10-minute push after a green pre_pr (issue #6426).
``tests/validation/test_pre_pr_covers_pre_push_jobs.py`` reads every pre-push
job and fails when one has neither a gate nor a reasoned exemption.

The wrappers live in their own module because ``checks_spec.py`` is at the
500-line ceiling ``scripts/ci/taste_count_ratchet.py`` enforces.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_changed_paths import _changed_paths_since_base  # noqa: E402
from checks_common import (  # noqa: E402
    MissingScriptSkip,
    _refresh_remote_base,
    _resolve_default_base_ref,
    _run_subprocess,
)

_REPORT_LINES = 40


def _run_workflow_validator(repo_root: Path, relative: str, *args: str, module: str = "") -> bool:
    """Run one validator the way its workflow does and report a clean exit.

    ``module`` selects the ``-m`` form for a validator the workflow runs as a
    module. ``cwd`` is the repository root, as in CI.

    A missing script is a FAIL where this repository's workflows are present,
    because CI would still invoke it and fail: a branch that deletes a validator
    without editing the workflow must not read clean. Where no workflows exist
    (a downstream install), it raises :class:`MissingScriptSkip` instead.
    """
    script = repo_root / relative
    if not script.exists():
        if (repo_root / ".github" / "workflows").is_dir():
            print(f"[FAIL] {relative} is missing, but the workflows in this repository run it")
            return False
        raise MissingScriptSkip(f"{relative} not present")
    target = ["-m", module] if module else [str(script)]
    exit_code, stdout, stderr = _run_subprocess([sys.executable, *target, *args], cwd=repo_root)
    output = ((stdout or "") + (stderr or "")).strip()
    if output:
        for line in output.splitlines()[:_REPORT_LINES]:
            print(line)
    return bool(exit_code == 0)


class BaseRefUnavailable(Exception):  # noqa: N818 - names the missing input, not an error class
    """The base ref a diff gate needs could not be resolved or refreshed.

    ``pre_pr.run_validation`` records any exception a gate raises as a FAIL, so
    this fails the gate instead of skipping it (issue #6506).
    """


_REMOTE_HEAD = "refs/remotes/origin/HEAD"


def _is_ci() -> bool:
    """True under a CI runner, which fetches the base before the gates run."""
    return any(os.environ.get(var, "").lower() in ("true", "1") for var in ("CI", "GITHUB_ACTIONS"))


def _origin_branch(repo_root: Path, label: str) -> str:
    """Resolve ``refs/remotes/origin/HEAD`` to ``origin/<branch>`` so it can be fetched.

    ``_refresh_remote_base`` fetches only ``origin/<branch>`` refs. The remote
    HEAD symref is what ``_resolve_default_base_ref`` returns when no PR is
    open, the usual time to run ``pre_pr.py``, and it would otherwise pass
    through unfetched and judge a stale cache.
    """
    exit_code, stdout, stderr = _run_subprocess(
        ["git", "-C", str(repo_root), "symbolic-ref", "--short", _REMOTE_HEAD],
        timeout=10,
    )
    resolved = str(stdout).strip()
    if exit_code == 0 and resolved.startswith("origin/"):
        return resolved
    detail = str(stderr).strip() or f"git symbolic-ref exit {exit_code}"
    raise BaseRefUnavailable(f"{label} could not resolve {_REMOTE_HEAD} to a branch ({detail})")


def _stale_against_remote(base_ref: str, repo_root: Path) -> str:
    """Return why the cached ``base_ref`` is not the remote tip, or "" when it is.

    Asks the remote for the branch tip with ``git ls-remote`` and compares it
    with the local ref, so a base the refresh helper never fetches is still
    verified rather than trusted. Any git failure counts as stale: an
    unverified base is not a fresh base.
    """
    branch = base_ref.removeprefix("origin/")
    remote_code, remote_out, remote_err = _run_subprocess(
        ["git", "-C", str(repo_root), "ls-remote", "origin", f"refs/heads/{branch}"],
        timeout=15,
    )
    remote_sha = str(remote_out).split()[0] if str(remote_out).split() else ""
    if remote_code != 0 or not remote_sha:
        detail = str(remote_err).strip() or f"git ls-remote exit {remote_code}"
        return f"cannot read the remote tip: {detail}"
    local_code, local_out, _ = _run_subprocess(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", f"{base_ref}^{{commit}}"],
        timeout=10,
    )
    local_sha = str(local_out).strip()
    if local_code != 0 or local_sha != remote_sha:
        return f"local {local_sha[:12] or 'missing'} differs from remote {remote_sha[:12]}"
    return ""


def _require_base_ref(repo_root: Path, label: str) -> str:
    """Return the freshly fetched base ref, or raise :class:`BaseRefUnavailable`.

    A gate that diffs against a missing or stale base judges the wrong file set
    and can read clean while the required check fails. So an unresolved base ref
    and a failed refresh are both failures, not skips or warnings.

    The remote HEAD symref is normalized to ``origin/<branch>`` first, so the
    no-open-PR case is fetched like any other. A base that is not an
    ``origin/<branch>`` ref (the local ``main`` last resort) is never fetched,
    so outside CI it fails too.
    A slash-containing base such as ``origin/release/1.0`` is never fetched:
    ``_refresh_remote_base`` returns ``None``, which means no fetch was
    attempted. Outside CI the cached ref is compared with ``git ls-remote`` and
    fails unless it equals the remote tip.
    """
    base_ref = _resolve_default_base_ref(repo_root)
    if base_ref is None:
        raise BaseRefUnavailable(f"{label} needs a base ref and none resolved")
    if base_ref == _REMOTE_HEAD:
        base_ref = _origin_branch(repo_root, label)
    if not base_ref.startswith("origin/") and not _is_ci():
        raise BaseRefUnavailable(
            f"{label} resolved {base_ref}, a local ref that is never fetched; "
            "a stale base can hide new findings, so fetch origin and re-run"
        )
    # CI fetches the current base before it diffs. A stale local origin/<branch>
    # changes which files and suppressions count as new, so refresh it here.
    refresh_error = _refresh_remote_base(base_ref, repo_root)
    if refresh_error:
        raise BaseRefUnavailable(
            f"{label} could not refresh {base_ref} ({refresh_error}); "
            "a stale base can hide new findings, so fetch the base and re-run"
        )
    if refresh_error is None and not _is_ci():
        # None means no fetch was attempted. Under CI the runner already fetched.
        # Outside CI the helper also returns None for a slash-containing branch
        # such as origin/release/1.0, which it never fetches. Compare the cached
        # ref with the remote tip instead of trusting it.
        stale_detail = _stale_against_remote(base_ref, repo_root)
        if stale_detail:
            branch = base_ref.removeprefix("origin/")
            raise BaseRefUnavailable(
                f"{label} did not refresh {base_ref}: the refresh skips a branch name "
                f"that contains a slash, and the cached ref is stale ({stale_detail}). "
                f"Run `git fetch origin {branch}` and re-run."
            )
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
    """Fail when a changed agent lacks a discriminator against a skill.

    Scoped to the files changed since the base, as the pull-request job is. The
    changed set includes untracked and unstaged files, so a new agent is scored
    before its first commit; ``--all`` enumerates only what HEAD tracks and would
    miss it. Without a resolvable base it scores the whole corpus instead.
    """
    changed = _changed_paths_since_base(repo_root, "agent-skill discriminator")
    scope = ["--all"] if changed is None else ["--changed-files", *changed]
    return _run_workflow_validator(
        repo_root,
        "scripts/validation/check_agent_skill_discriminator.py",
        *scope,
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
    base_ref = _require_base_ref(repo_root, "placeholder identity check")
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
    base_ref = _require_base_ref(repo_root, "security suppression diff")
    return _run_workflow_validator(
        repo_root,
        "scripts/validation/git_hook_policy.py",
        "security-suppressions-diff",
        "--base-ref",
        base_ref,
    )


def validate_memory_placement(repo_root: Path) -> bool:
    """Fail when the branch adds a policy-shaped memory or raises one (``Validate PR``).

    Runs the command the ``Run memory-placement check`` step runs, over the
    commits since the base. It reads the committed range only, as CI does:
    commit first, because an uncommitted edit to a memory is not judged here.
    The pre-commit ``memory-placement`` job covers staged files. Issue #5828.
    """
    base_ref = _require_base_ref(repo_root, "memory placement check")
    return _run_workflow_validator(
        repo_root,
        "scripts/validation/check_memory_placement.py",
        "--ci",
        "--changed-since",
        base_ref,
    )


def validate_route_scenario_coverage(repo_root: Path) -> bool:
    """Fail when a new or changed autoplan route has no edited scenario.

    Runs the command the ``Require a scenario for each new or changed autoplan
    route`` step of ``Rule Activation Coverage`` runs, against the same base.
    It diffs the committed range from the merge base, as CI does. Issue #6291.
    """
    base_ref = _require_base_ref(repo_root, "route scenario coverage")
    return _run_workflow_validator(
        repo_root,
        "scripts/validation/check_route_scenario_coverage.py",
        "--base-ref",
        base_ref,
    )


def validate_closure_manifest(repo_root: Path) -> bool:
    """Advisory: compute the enforcement closure and report unresolved edges.

    Runs the command the scheduled `Enforcement Closure` job runs, with
    `--advisory` so it prints the summary and any unresolved edge without failing:
    the manifest is P0 code here, and the job that binds runs from the default
    branch. ADR-101 Phase 1, issue #5245.
    """
    return _run_workflow_validator(
        repo_root, "scripts/validation/closure_manifest.py", "--advisory"
    )


def validate_review_axis_drift(repo_root: Path) -> bool:
    """Fail when ``.github/prompts/pr-quality-gate-*.md`` drifts from the review skill.

    Runs the command the pre-push ``review-axis-drift`` job and the CI drift
    check run. ``--dry-run`` writes nothing and exits 1 with a diff on drift.
    """
    return _run_workflow_validator(
        repo_root, "build/scripts/generate_pr_quality_prompts.py", "--dry-run"
    )


def validate_skill_description_budget(repo_root: Path) -> bool:
    """Fail when the skill descriptions outgrow their per-root budget.

    Runs the command the ``Run skill description budget`` step of
    ``skill-passive-compliance.yml`` runs. The pytest suite asserts the same
    budget file, so a branch over it failed the pre-push test job first.
    """
    return _run_workflow_validator(
        repo_root,
        "scripts/skill_description_budget.py",
        "--budget-file",
        "scripts/skill_description_budget.json",
    )
