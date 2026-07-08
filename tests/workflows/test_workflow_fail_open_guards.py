"""Contract tests for the fail-open fixes in four CI workflows (Issue #2808).

Each of these workflows had a step meant to DETECT a problem that converted its
own crash (or findings) into a green run via `|| true`, `2>/dev/null`, or a
default-to-pass parse branch. These tests pin the hardened contract so a later
edit cannot silently reintroduce the suppression without a test failing first.

Covered:
  - audit-hook-bypass.yml: detection step classifies exit code, fails on >=2,
    and treats missing JSON as a failure (not indicator_count=0).
  - pytest.yml (security job): bandit gates on high severity/confidence with no
    `|| true`, the job has actions: read plus security-events: write, and a
    codeql upload-sarif step publishes findings with if: always().
  - memory-validation.yml: verify step captures the exit code before pipefail
    aborts, and the parse step fails on a missing/empty results file instead of
    posting a green Pass.
  - drift-detection.yml: the JSON re-run stops swallowing stderr and the exit
    code, failing only on exit >=2 (config/crash) since exit 1 is the expected
    drift path for this step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

_WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _load_workflow(name: str) -> dict[str, Any]:
    with (_WORKFLOWS / name).open(encoding="utf-8") as handle:
        loaded: dict[str, Any] = yaml.safe_load(handle)
        return loaded


def _job_steps(workflow: Any, job: str) -> list[dict[str, Any]]:
    """Return the step mappings for a job, tolerating malformed shapes."""
    if not isinstance(workflow, dict):
        return []
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return []
    job_def = jobs.get(job)
    if not isinstance(job_def, dict):
        return []
    steps = job_def.get("steps")
    if not isinstance(steps, list):
        return []
    return [step for step in steps if isinstance(step, dict)]


def _command_text(run: str) -> str:
    """Drop comment-only lines so token checks target the actual commands.

    The hardened steps document `|| true` and `2>/dev/null` in explanatory
    comments; the suppression assertions must inspect the executable lines only.
    """
    lines = [line for line in run.splitlines() if not line.lstrip().startswith("#")]
    return "\n".join(lines)


def _find_step_by_run(steps: list[dict[str, Any]], needle: str) -> dict[str, Any] | None:
    for step in steps:
        run = step.get("run")
        if isinstance(run, str) and needle in run:
            return step
    return None


def _find_step_by_uses(steps: list[dict[str, Any]], needle: str) -> dict[str, Any] | None:
    for step in steps:
        uses = step.get("uses")
        if isinstance(uses, str) and needle in uses:
            return step
    return None


def _job_permissions(workflow: dict[str, Any], job: str) -> dict[str, Any]:
    jobs = workflow.get("jobs") or {}
    job_def = jobs.get(job) or {}
    perms = job_def.get("permissions")
    return perms if isinstance(perms, dict) else {}


class TestStepExtractionEdges:
    """Edge: malformed workflow shapes yield empty steps, not exceptions."""

    def test_non_mapping_inputs_return_empty(self) -> None:
        assert _job_steps(None, "test") == []
        assert _job_steps({"jobs": None}, "test") == []
        assert _job_steps({"jobs": {"test": None}}, "test") == []
        assert _job_steps({"jobs": {"test": {"steps": None}}}, "test") == []

    def test_missing_job_returns_empty(self) -> None:
        wf = {"jobs": {"other": {"steps": [{"run": "echo hi"}]}}}
        assert _job_steps(wf, "test") == []

    def test_non_mapping_steps_are_filtered(self) -> None:
        wf = {"jobs": {"test": {"steps": ["scalar", {"run": "echo hi"}]}}}
        assert _job_steps(wf, "test") == [{"run": "echo hi"}]

    def test_find_helpers_return_none_when_absent(self) -> None:
        assert _find_step_by_run([{"run": "echo hi"}], "missing") is None
        assert _find_step_by_uses([{"uses": "actions/checkout"}], "missing") is None
        # Steps without the queried key must not raise.
        assert _find_step_by_run([{"uses": "x"}], "echo") is None
        assert _find_step_by_uses([{"run": "x"}], "actions") is None


class TestAuditHookBypass:
    """audit-hook-bypass.yml detection step must not mask the crash path."""

    def _detect_step(self) -> dict[str, Any]:
        steps = _job_steps(_load_workflow("audit-hook-bypass.yml"), "detect-bypass")
        step = _find_step_by_run(steps, "detect_hook_bypass.py")
        assert step is not None
        return step

    def test_no_blanket_true_suppression(self) -> None:
        assert "|| true" not in _command_text(self._detect_step()["run"])

    def test_captures_and_hard_fails_on_crash(self) -> None:
        run = self._detect_step()["run"]
        assert "set +e" in run
        assert "rc=$?" in run
        assert "set -e" in run
        assert 'if [ "$rc" -ge 2 ]' in run
        assert 'exit "$rc"' in run

    def test_missing_json_is_a_failure_not_zero_indicators(self) -> None:
        run = self._detect_step()["run"]
        # The else branch must fail instead of reporting a clean audit.
        assert "indicator_count=0" not in run
        assert "test -s artifacts/hook-bypass-audit.json" in run


class TestPytestBanditSecurity:
    """pytest.yml security job must fail on real findings and upload SARIF."""

    def _workflow(self) -> dict[str, Any]:
        return _load_workflow("pytest.yml")

    def _bandit_step(self) -> dict[str, Any]:
        steps = _job_steps(self._workflow(), "security")
        step = _find_step_by_run(steps, "bandit -r")
        assert step is not None
        return step

    def test_bandit_has_no_true_suppression(self) -> None:
        assert "|| true" not in _command_text(self._bandit_step()["run"])

    def test_bandit_gates_on_high_severity_and_confidence(self) -> None:
        run = self._bandit_step()["run"]
        assert "--severity-level high" in run
        assert "--confidence-level high" in run

    def test_bandit_writes_sarif_artifact(self) -> None:
        run = self._bandit_step()["run"]
        assert "-f sarif" in run
        assert "-o bandit.sarif" in run

    def test_bandit_excludes_test_paths(self) -> None:
        # Test-only B324 SHA1-for-module-name false positives must not gate CI.
        assert "-x" in self._bandit_step()["run"]

    def test_security_job_can_write_code_scanning_events(self) -> None:
        permissions = _job_permissions(self._workflow(), "security")
        assert permissions.get("actions") == "read"
        assert permissions.get("security-events") == "write"

    def test_bandit_sarif_upload_runs_after_bandit_on_trusted_prs(self) -> None:
        steps = _job_steps(self._workflow(), "security")
        step = _find_step_by_uses(steps, "github/codeql-action/upload-sarif@")
        assert step is not None
        condition = step.get("if")
        assert condition is not None
        assert condition.startswith("always()")
        assert "github.event_name != 'pull_request'" in condition
        assert "github.event.pull_request.head.repo.full_name == github.repository" in condition
        assert step["with"]["sarif_file"] == "bandit.sarif"
        assert step["with"]["category"] == "bandit"


class TestMemoryValidation:
    """memory-validation.yml must not post a green Pass on a crashed run."""

    def _workflow(self) -> dict[str, Any]:
        return _load_workflow("memory-validation.yml")

    def _verify_step(self) -> dict[str, Any]:
        steps = _job_steps(self._workflow(), "validate-memories")
        step = _find_step_by_run(steps, "verify-all --json")
        assert step is not None
        return step

    def _parse_step(self) -> dict[str, Any]:
        # The verify step also references the results file; pick the parser.
        for candidate in _job_steps(self._workflow(), "validate-memories"):
            run = candidate.get("run")
            if isinstance(run, str) and "jq 'length'" in run:
                return candidate
        raise AssertionError("parse step not found")

    def test_verify_captures_exit_code_before_pipefail(self) -> None:
        run = self._verify_step()["run"]
        assert "set +e" in run
        assert "rc=$?" in run
        assert "set -e" in run
        assert "exit_code=$rc" in run
        # The buggy form captured $? on a separate line after the redirect.
        assert 'echo "exit_code=$?"' not in run

    def test_parse_treats_empty_results_as_failure(self) -> None:
        run = self._parse_step()["run"]
        assert "-s memory-validation-results.json" in run
        assert "exit 1" in run

    def test_parse_does_not_default_missing_file_to_pass(self) -> None:
        run = self._parse_step()["run"]
        # The else branch previously set has_stale=false on a missing file.
        # has_stale=false legitimately remains in the zero-stale branch, so key
        # on the error signal that must now precede any exit in the else path.
        assert "::error::memory-validation-results.json missing or empty" in run


class TestDriftDetection:
    """drift-detection.yml JSON re-run must surface crashes, not swallow them."""

    def _collect_step(self) -> dict[str, Any]:
        steps = _job_steps(_load_workflow("drift-detection.yml"), "detect-drift")
        step = _find_step_by_run(steps, "--output-format json")
        assert step is not None
        return step

    def test_stderr_not_discarded(self) -> None:
        assert "2>/dev/null" not in _command_text(self._collect_step()["run"])

    def test_no_blanket_true_suppression(self) -> None:
        assert "|| true" not in _command_text(self._collect_step()["run"])

    def test_fails_only_on_config_or_crash(self) -> None:
        run = self._collect_step()["run"]
        # exit 1 is the expected drift path for this step; only >=2 fails.
        assert "set +e" in run
        assert "rc=$?" in run
        assert "set -e" in run
        assert 'if [ "$rc" -ge 2 ]' in run
        assert 'exit "$rc"' in run


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-x", "-q"]))
