"""Contract tests for the needs-split label steps in pr-validation.yml (Issue #2557).

The `needs-split` label is *advisory*: it cosmetically marks PRs with 10+
commits ("consider squashing or splitting"). It is NOT a gate: no commit-count
tier can block a PR (the former 20/40-commit BLOCK tier was removed by
ADR-099; `Enforce Blocking Issues` no longer reads commit count at all).

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
_LABEL_SCRIPT = _REPO_ROOT / "scripts" / "ci" / "update_needs_split_label.py"
_ENFORCE_SCRIPT = _REPO_ROOT / "scripts" / "ci" / "enforce_pr_validation.py"

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


def _script_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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
        script = _script_text(_LABEL_SCRIPT)
        assert "python3 scripts/ci/update_needs_split_label.py --mode add" in run
        # The mutation path must use Write-Warning (or ::warning), NOT throw.
        # The READ-labels `gh pr view` call may keep its throw — the issue
        # explicitly notes REST reads succeed where GraphQL mutations 401.
        # We catch any `throw` after the mutation marker.
        mutation_marker = '"POST"'
        api_marker = "/labels"
        assert mutation_marker in script and api_marker in script
        # Split on whichever marker is present and check the trailing block.
        marker = mutation_marker if mutation_marker in script else api_marker
        tail = script.split(marker, 1)[1]
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
        script = _script_text(_LABEL_SCRIPT)
        assert "python3 scripts/ci/update_needs_split_label.py --mode add" in run
        assert "gh pr edit" not in run or "--add-label" not in run, (
            f"{_APPLY_STEP_NAME!r} must not invoke `gh pr edit --add-label` "
            "(GraphQL — fails with HTTP 401 on installation tokens). "
            "Use `gh api -X POST .../issues/{N}/labels` (REST) instead."
        )
        assert '"gh"' in script and '"api"' in script and "/labels" in script

    def test_step_reads_labels_via_rest_not_graphql(self) -> None:
        step = _find_step(_APPLY_STEP_NAME)
        assert step is not None
        run = _executable_lines(step.get("run") or "")
        script = _script_text(_LABEL_SCRIPT)
        assert "python3 scripts/ci/update_needs_split_label.py --mode add" in run
        assert "gh pr view" not in run, (
            f"{_APPLY_STEP_NAME!r} must not read labels with `gh pr view`, "
            "which can use GraphQL under this token shape"
        )
        assert "issues/{pr_number}/labels" in script


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
        script = _script_text(_LABEL_SCRIPT)
        assert "python3 scripts/ci/update_needs_split_label.py --mode remove" in run
        mutation_marker = '"DELETE"'
        api_marker = "}/{LABEL}"  # REST DELETE form: .../labels/needs-split
        assert mutation_marker in script and api_marker in script
        marker = mutation_marker if mutation_marker in script else api_marker
        tail = script.split(marker, 1)[1]
        assert "throw" not in tail.lower(), (
            f"{_REMOVE_STEP_NAME!r} must not `throw` after the label-mutation "
            "call — log `::warning` instead"
        )

    def test_step_uses_rest_api_not_graphql_for_mutation(self) -> None:
        step = _find_step(_REMOVE_STEP_NAME)
        assert step is not None
        run = _executable_lines(step.get("run") or "")
        script = _script_text(_LABEL_SCRIPT)
        assert "python3 scripts/ci/update_needs_split_label.py --mode remove" in run
        assert "gh pr edit" not in run or "--remove-label" not in run, (
            f"{_REMOVE_STEP_NAME!r} must not invoke `gh pr edit --remove-label` "
            "(GraphQL — fails with HTTP 401 on installation tokens). Use "
            "`gh api -X DELETE .../issues/{N}/labels/{name}` (REST) instead."
        )
        assert '"gh"' in script and '"api"' in script and "}/{LABEL}" in script

    def test_step_reads_labels_via_rest_not_graphql(self) -> None:
        step = _find_step(_REMOVE_STEP_NAME)
        assert step is not None
        run = _executable_lines(step.get("run") or "")
        script = _script_text(_LABEL_SCRIPT)
        assert "python3 scripts/ci/update_needs_split_label.py --mode remove" in run
        assert "gh pr view" not in run, (
            f"{_REMOVE_STEP_NAME!r} must not read labels with `gh pr view`, "
            "which can use GraphQL under this token shape"
        )
        assert "issues/{pr_number}/labels" in script


class TestEnforceStepStillReportsOverallStatus:
    """Sanity: `Enforce Blocking Issues` still fails the job on OVERALL_STATUS.

    ADR-099 removed the 20-commit BLOCK tier and its `commit-limit-bypass`
    label check entirely: the commit count is advisory only now. What remains
    a real, unconditional gate is the description/standards OVERALL_STATUS
    check (FAIL or ERROR), which this class still pins.
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

    def test_enforce_step_exits_on_overall_status_failure(self) -> None:
        step = _find_step(_ENFORCE_STEP_NAME)
        assert step is not None
        run = step.get("run") or ""
        script = _script_text(_ENFORCE_SCRIPT)
        assert "python3 scripts/ci/enforce_pr_validation.py" in run
        assert 'overall_status in {"FAIL", "ERROR"}' in script, (
            f"{_ENFORCE_STEP_NAME!r} must still branch on OVERALL_STATUS"
        )
        assert "return LOGIC_ERROR" in script, (
            f"{_ENFORCE_STEP_NAME!r} must still exit 1 on a failed OVERALL_STATUS"
        )

    def test_enforce_step_no_longer_reads_a_bypass_label(self) -> None:
        """ADR-099: there is no more label to fetch for this gate.

        The script's module docstring names `commit-limit-bypass` historically
        (why the label check was removed), so this checks operative code, not
        a blanket substring: no label-fetch endpoint, and no BYPASS_LABEL
        attribute left to reintroduce the check against.
        """
        step = _find_step(_ENFORCE_STEP_NAME)
        assert step is not None
        run = _executable_lines(step.get("run") or "")
        script = _script_text(_ENFORCE_SCRIPT)
        assert "python3 scripts/ci/enforce_pr_validation.py" in run
        assert "gh pr view" not in run
        assert "issues/{pr_number}/labels" not in script
        import importlib

        enforce_module = importlib.import_module(
            "scripts.ci.enforce_pr_validation"
        )
        assert not hasattr(enforce_module, "BYPASS_LABEL")
        assert not hasattr(enforce_module, "_fetch_labels")
