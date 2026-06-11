"""Contract tests for the needs-split label steps in pr-validation.yml (Issue #2557).

The `needs-split` label is *advisory* — it cosmetically marks PRs with 10+
commits ("consider squashing or splitting"). It is NOT a gate: the 20-commit
BLOCK tier is enforced separately in the `Enforce Blocking Issues` step.

Two stacked bugs in the original implementation hard-failed `Validate PR` on
every PR that crossed the WARNING tier:

1. **Token/API mismatch.** `gh pr edit --add-label` and
   `gh pr edit --remove-label` route through the GraphQL API, which rejects
   installation/fine-grained tokens with HTTP 401. The REST endpoint
   (`POST /repos/{owner}/{repo}/issues/{number}/labels`,
   `DELETE .../labels/{name}`) accepts the same token that the workflow's
   REST reads already use. Run 27280632030 / job 80573824518 was the first
   reproduction.

2. **Severity inversion.** Both label steps `throw`-ed on any failure,
   making a cosmetic label outage a job-failing red check. The advisory
   `::notice` tier must never block.

These tests pin both fixes so neither can silently regress.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "pr-validation.yml"

_APPLY_STEP_NAME = "Apply needs-split label"
_REMOVE_STEP_NAME = "Remove needs-split label when below threshold"
_ENFORCE_STEP_NAME = "Enforce Blocking Issues"


@lru_cache(maxsize=1)
def _load_workflow() -> dict[str, Any]:
    """Parse pr-validation.yml into a dict."""
    with _WORKFLOW_PATH.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    assert isinstance(loaded, dict), (
        f"expected {_WORKFLOW_PATH} to parse as a mapping, got {type(loaded).__name__}"
    )
    return loaded


def _validate_pr_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the steps of the `validate-pr` job, defensively."""
    jobs = workflow.get("jobs") or {}
    if not isinstance(jobs, dict):
        return []
    job = jobs.get("validate-pr") or {}
    if not isinstance(job, dict):
        return []
    steps = job.get("steps") or []
    if not isinstance(steps, list):
        return []
    return [s for s in steps if isinstance(s, dict)]


def _find_step(name: str) -> dict[str, Any] | None:
    for step in _validate_pr_steps(_load_workflow()):
        if step.get("name") == name:
            return step
    return None


def _executable_lines(run_block: str) -> str:
    """Return only the executable PowerShell lines (no comments).

    Strips:
      * pure-comment lines (`#...`)

    This keeps the tests focused on actual command invocations and avoids
    false positives from docstring-style comments that reference the old
    (broken) `gh pr edit --add-label` / `--remove-label` calls for context.

    Stricter/looser/different than canonical:
      This helper is intentionally looser than a PowerShell parser. It only
      strips pure-comment lines and leaves inline comments intact because the
      workflow assertions need command-level signal, not shell syntax fidelity.
    """
    kept: list[str] = []
    for line in run_block.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        kept.append(line)
    return "\n".join(kept)


class TestWorkflowFile:
    """Positive: the workflow file is present and parseable."""

    def test_workflow_file_exists(self) -> None:
        assert _WORKFLOW_PATH.is_file(), f"missing workflow: {_WORKFLOW_PATH}"

    def test_validate_pr_job_has_steps(self) -> None:
        assert _validate_pr_steps(_load_workflow()), "validate-pr job should have at least one step"


class TestApplyNeedsSplitStep:
    """Apply-label step is advisory: must never fail the job."""

    def test_step_exists(self) -> None:
        assert _find_step(_APPLY_STEP_NAME) is not None, (
            f"expected step named {_APPLY_STEP_NAME!r} in validate-pr job"
        )

    def test_step_is_continue_on_error(self) -> None:
        """The advisory label step MUST be failure-isolated at the step level.

        Without this, any transient label-API failure (401, 403, rate-limit,
        network blip) reddens `Validate PR` even when every real check passed.
        Pinning this prevents future edits from removing the guard.
        """
        step = _find_step(_APPLY_STEP_NAME)
        assert step is not None
        assert step.get("continue-on-error") is True, (
            f"{_APPLY_STEP_NAME!r} must set `continue-on-error: true` — the "
            "needs-split label is advisory and cannot fail a green PR"
        )

    def test_step_does_not_throw_on_mutation_failure(self) -> None:
        """Belt-and-suspenders: no `throw` on the label-mutation path.

        continue-on-error catches any step failure, but the script body MUST
        ALSO degrade to a warning instead of raising, so the GitHub Actions
        UI shows a clean step annotation rather than a red ❌ outline.

        We inspect only executable lines so prose comments that mention
        `throw` for context do not trip the check.
        """
        step = _find_step(_APPLY_STEP_NAME)
        assert step is not None
        run = _executable_lines(step.get("run") or "")
        # The mutation path must use Write-Warning (or ::warning), NOT throw.
        # The READ-labels `gh pr view` call may keep its throw — the issue
        # explicitly notes REST reads succeed where GraphQL mutations 401.
        # We catch any `throw` after the mutation marker.
        mutation_marker = "--add-label"
        api_marker = "/labels"
        assert mutation_marker in run or api_marker in run, (
            "step body should still attempt to add the label somehow"
        )
        # Split on whichever marker is present and check the trailing block.
        marker = mutation_marker if mutation_marker in run else api_marker
        tail = run.split(marker, 1)[1]
        assert "throw" not in tail.lower(), (
            f"{_APPLY_STEP_NAME!r} must not `throw` after the label-mutation "
            "call — log `::warning` (Write-Warning) instead so an advisory "
            "label outage does not redden the check"
        )

    def test_step_uses_rest_api_not_graphql_for_mutation(self) -> None:
        """Root-cause fix: route label add through REST, not GraphQL.

        `gh pr edit --add-label` calls GraphQL, which returns HTTP 401 for
        installation/fine-grained tokens this job runs under.
        `gh api POST /repos/{owner}/{repo}/issues/{number}/labels` uses REST
        and accepts the same token that the read-labels step already uses.

        We inspect only executable lines (comments stripped) so prose that
        documents the old bad pattern for context does not trip the check.
        """
        step = _find_step(_APPLY_STEP_NAME)
        assert step is not None
        run = _executable_lines(step.get("run") or "")
        assert "gh pr edit" not in run or "--add-label" not in run, (
            f"{_APPLY_STEP_NAME!r} must not invoke `gh pr edit --add-label` "
            "(GraphQL — fails with HTTP 401 on installation tokens). "
            "Use `gh api -X POST .../issues/{N}/labels` (REST) instead."
        )
        assert "gh api" in run and "/labels" in run, (
            f"{_APPLY_STEP_NAME!r} must call the REST labels endpoint via "
            "`gh api`. Expected `gh api ... /labels` in the step body."
        )

    def test_step_reads_labels_via_rest_not_graphql(self) -> None:
        step = _find_step(_APPLY_STEP_NAME)
        assert step is not None
        run = _executable_lines(step.get("run") or "")
        assert "gh pr view" not in run, (
            f"{_APPLY_STEP_NAME!r} must not read labels with `gh pr view`, "
            "which can use GraphQL under this token shape"
        )
        assert "issues/$env:PR_NUMBER/labels" in run


class TestRemoveNeedsSplitStep:
    """Remove-label step has the same severity / API contract as the add step."""

    def test_step_exists(self) -> None:
        assert _find_step(_REMOVE_STEP_NAME) is not None

    def test_step_is_continue_on_error(self) -> None:
        step = _find_step(_REMOVE_STEP_NAME)
        assert step is not None
        assert step.get("continue-on-error") is True, (
            f"{_REMOVE_STEP_NAME!r} must set `continue-on-error: true`"
        )

    def test_step_does_not_throw_on_mutation_failure(self) -> None:
        step = _find_step(_REMOVE_STEP_NAME)
        assert step is not None
        run = _executable_lines(step.get("run") or "")
        mutation_marker = "--remove-label"
        api_marker = "/labels/"  # REST DELETE form: .../labels/needs-split
        assert mutation_marker in run or api_marker in run, (
            "step body should still attempt to remove the label somehow"
        )
        marker = mutation_marker if mutation_marker in run else api_marker
        tail = run.split(marker, 1)[1]
        assert "throw" not in tail.lower(), (
            f"{_REMOVE_STEP_NAME!r} must not `throw` after the label-mutation "
            "call — log `::warning` instead"
        )

    def test_step_uses_rest_api_not_graphql_for_mutation(self) -> None:
        step = _find_step(_REMOVE_STEP_NAME)
        assert step is not None
        run = _executable_lines(step.get("run") or "")
        assert "gh pr edit" not in run or "--remove-label" not in run, (
            f"{_REMOVE_STEP_NAME!r} must not invoke `gh pr edit --remove-label` "
            "(GraphQL — fails with HTTP 401 on installation tokens). Use "
            "`gh api -X DELETE .../issues/{N}/labels/{name}` (REST) instead."
        )
        assert "gh api" in run and "/labels/" in run, (
            f"{_REMOVE_STEP_NAME!r} must call the REST labels DELETE endpoint "
            "via `gh api`. Expected `gh api -X DELETE .../labels/<name>`."
        )

    def test_step_reads_labels_via_rest_not_graphql(self) -> None:
        step = _find_step(_REMOVE_STEP_NAME)
        assert step is not None
        run = _executable_lines(step.get("run") or "")
        assert "gh pr view" not in run, (
            f"{_REMOVE_STEP_NAME!r} must not read labels with `gh pr view`, "
            "which can use GraphQL under this token shape"
        )
        assert "issues/$env:PR_NUMBER/labels" in run


class TestBlockTierStillFails:
    """Sanity: the BLOCK tier (20+ commits) MUST still fail the job.

    The fix relaxes the advisory tier only. The hard limit at 20 commits is
    enforced in `Enforce Blocking Issues` and must remain a blocking gate
    (exit 1 unless `commit-limit-bypass` label is set).
    """

    def test_enforce_step_exists(self) -> None:
        assert _find_step(_ENFORCE_STEP_NAME) is not None

    def test_enforce_step_is_not_continue_on_error(self) -> None:
        step = _find_step(_ENFORCE_STEP_NAME)
        assert step is not None
        # `continue-on-error` must be absent or False on the gate step.
        assert step.get("continue-on-error") in (None, False), (
            f"{_ENFORCE_STEP_NAME!r} is the real gate — it must NOT set `continue-on-error: true`"
        )

    def test_enforce_step_exits_on_block_status(self) -> None:
        step = _find_step(_ENFORCE_STEP_NAME)
        assert step is not None
        run = step.get("run") or ""
        assert 'COMMIT_STATUS -eq "BLOCKED"' in run, (
            f"{_ENFORCE_STEP_NAME!r} must still branch on COMMIT_STATUS == "
            "BLOCKED to enforce the 20-commit cap"
        )
        assert "exit 1" in run, f"{_ENFORCE_STEP_NAME!r} must still `exit 1` on the BLOCK tier"

    def test_enforce_step_reads_bypass_label_via_rest_and_fails_closed(self) -> None:
        step = _find_step(_ENFORCE_STEP_NAME)
        assert step is not None
        run = _executable_lines(step.get("run") or "")
        assert "gh pr view" not in run, (
            f"{_ENFORCE_STEP_NAME!r} must not use GraphQL-backed `gh pr view` "
            "for bypass-label reads"
        )
        assert "issues/$env:PR_NUMBER/labels" in run
        assert "throw \"Failed to fetch PR labels" in run, (
            f"{_ENFORCE_STEP_NAME!r} must fail closed when the bypass-label "
            "REST read fails"
        )
