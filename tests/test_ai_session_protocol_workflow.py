"""Regression tests for .github/workflows/ai-session-protocol.yml.

Issue #2384: The legacy-markdown branch invoked ./scripts/Convert-SessionToJson.ps1,
a script removed during the PowerShell-to-Python migration (PR #1063/#1064) and
whose wrapper was sunset in PR #2359. Any markdown session log routed through that
branch failed with "Migration failed". These tests pin the fix in place.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = (
    Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ai-session-protocol.yml"
)


def _validate_step_run() -> str:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = doc["jobs"]
    validate_job = jobs["validate"]
    for step in validate_job["steps"]:
        if step.get("id") == "validate":
            return step["run"]
    raise AssertionError("validate step not found in ai-session-protocol.yml")


def test_workflow_does_not_call_phantom_convert_script() -> None:
    """Issue #2384: phantom Convert-SessionToJson.ps1 must not be invoked."""
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "Convert-SessionToJson.ps1" not in body, (
        "ai-session-protocol.yml still references the removed "
        "Convert-SessionToJson.ps1 script (issue #2384)."
    )


def test_workflow_does_not_claim_legacy_markdown_migration() -> None:
    """The dead 'migrate to JSON first' branch must be gone."""
    run = _validate_step_run()
    assert "Migration failed - could not convert markdown to JSON" not in run
    assert "Legacy markdown detected - migrating to JSON" not in run


def test_markdown_branch_fails_fast_with_actionable_message() -> None:
    """Markdown session logs should now fail fast with guidance, not silently retry."""
    run = _validate_step_run()
    assert "Markdown session logs are no longer supported." in run
    assert "session-init now emits JSON" in run
    # Branch must still set a non-zero exit so CI surfaces the failure.
    assert "$exitCode = 1" in run


def test_json_branch_still_calls_python_validator() -> None:
    """JSON path is the supported branch; keep its validator wired up."""
    run = _validate_step_run()
    assert "python3 ./scripts/validate_session_json.py $sessionFile" in run


def _counter_block() -> str:
    """Extract the MUST-counting PowerShell from the validate step.

    Slicing the real workflow text keeps the test honest: it exercises the
    shipped code rather than a copy that can drift.
    """
    run = _validate_step_run()
    start = run.index("$mustFailCount = 0")
    end = run.index("$mustFailCount | Out-File")
    return run[start:end]


def _run_counter(tmp_path: Path, summary: str | None, exit_code: int) -> int:
    """Run the extracted counter block under pwsh and return its verdict."""
    if summary is not None:
        (tmp_path / "validation-summary.json").write_text(summary, encoding="utf-8")
    script = tmp_path / "counter.ps1"
    script.write_text(
        f"$exitCode = {exit_code}\n{_counter_block()}\nWrite-Output $mustFailCount\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return int(proc.stdout.strip().splitlines()[-1])


pwsh_required = pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not installed")


class TestMustFailureCounter:
    """Issue #3365: the counter must be able to reach a nonzero value.

    The previous implementation regexed for markdown table rows
    (`| Check | MUST | FAIL |`) that scripts/validate_session_json.py has never
    emitted, so the count was structurally pinned at 0 and the downstream
    "Enforce MUST Requirements" step was decorative.
    """

    def test_the_phantom_markdown_table_regex_is_gone(self) -> None:
        """The old pattern matched output no validator produces."""
        run = _validate_step_run()
        assert "MUST\\s*\\|\\s*FAIL" not in run, (
            "ai-session-protocol.yml still counts MUST failures with a regex "
            "for a markdown table validate_session_json.py never emits (#3365)."
        )

    def test_the_counter_reads_the_validator_summary(self) -> None:
        run = _validate_step_run()
        assert "--json-output validation-summary.json" in run
        assert "$summary.must_failures" in run

    @pwsh_required
    def test_a_summary_with_must_failures_counts_them(self, tmp_path: Path) -> None:
        """The regression the phantom regex could never catch."""
        summary = json.dumps({"verdict": "NON_COMPLIANT", "must_failures": 4})
        assert _run_counter(tmp_path, summary, exit_code=1) == 4

    @pwsh_required
    def test_a_clean_summary_counts_zero(self, tmp_path: Path) -> None:
        summary = json.dumps({"verdict": "COMPLIANT", "must_failures": 0})
        assert _run_counter(tmp_path, summary, exit_code=0) == 0

    @pwsh_required
    def test_a_missing_summary_on_failure_fails_closed(self, tmp_path: Path) -> None:
        """No summary means the validator died; do not report a confident zero.

        The enforcement step tests `-gt 0`, so 0 or a negative sentinel would
        read as "nothing to enforce" and let the failure through that path.
        """
        assert _run_counter(tmp_path, None, exit_code=1) == 1

    @pwsh_required
    def test_a_missing_summary_on_success_counts_zero(self, tmp_path: Path) -> None:
        """A skipped or deleted file exits 0 and legitimately has no summary."""
        assert _run_counter(tmp_path, None, exit_code=0) == 0


class TestValidationFindingsReachTheJobLog:
    """Issue #3364: a blocking gate must say why it failed in the job log.

    The findings were computed, written to an artifact, and never echoed, so a
    red required check showed only "Exit code: 1".
    """

    def test_the_failure_path_echoes_the_findings(self) -> None:
        run = _validate_step_run()
        failure_echo = run[run.index("if ($exitCode -ne 0) {") :]
        assert "$result | ForEach-Object { Write-Host $_ }" in failure_echo, (
            "The validate step no longer echoes validator findings to the job "
            "log; contributors would have to download an artifact (#3364)."
        )

    def test_the_artifact_upload_is_preserved(self) -> None:
        """The echo is additive: tooling still gets the artifact."""
        run = _validate_step_run()
        assert '$result | Out-File -FilePath "validation-result.md"' in run
        assert "validation-results/${fileName}-findings.txt" in run

    def test_the_dead_double_write_is_gone(self) -> None:
        """validation-result.md was written twice on the post-validation path.

        The first write wrapped the findings in markdown, the second
        immediately overwrote it with the raw findings, so the wrapper was
        dead. The early-exit branch for a deleted file has its own legitimate
        write and is deliberately outside this slice.
        """
        run = _validate_step_run()
        post_validation = run[run.index("$fileName = Split-Path") :]
        assert post_validation.count('Out-File -FilePath "validation-result.md"') == 1, (
            "validation-result.md is written more than once after validation; "
            "the earlier write is immediately overwritten."
        )
