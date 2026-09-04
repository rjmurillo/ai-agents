"""Tests for the ai-review infrastructure gate (ADR-006 extraction, issue #2967).

Covers the behavior the workflow's inline skip block had: skip on context
infrastructure failure with a DID_NOT_RUN verdict file, run otherwise, the exact
verdict/message/warning strings, the output sinks, and the CLI exit contract.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.test_selection import path_policy

pytestmark = pytest.mark.windows_path

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "ci" / "check_ai_review_infra_gate.py"
)
_ACTION_PATH = (
    Path(__file__).resolve().parents[1] / ".github" / "actions" / "ai-review" / "action.yml"
)
_PYTEST_WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pytest.yml"
_spec = importlib.util.spec_from_file_location("check_ai_review_infra_gate", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
sys.modules["check_ai_review_infra_gate"] = mod
_spec.loader.exec_module(mod)


# ---------------------------------------------------------------------------
# evaluate_gate: the pure decision
# ---------------------------------------------------------------------------


def test_context_infra_failure_true_skips():
    decision = mod.evaluate_gate("true")
    assert decision.skip is True
    assert decision.verdict == "DID_NOT_RUN"
    assert decision.infrastructure_failure is True
    assert decision.retry_count == 0
    assert decision.message == (
        "AI review did not run because context build had an infrastructure failure."
    )


def test_empty_context_runs():
    decision = mod.evaluate_gate("")
    assert decision.skip is False
    assert decision.verdict == ""
    assert decision.message == ""
    assert decision.infrastructure_failure is False


def test_false_string_runs():
    # The inline shell compared with = "true"; "false" is not a skip.
    assert mod.evaluate_gate("false").skip is False


@pytest.mark.parametrize("value", ["True", "TRUE", "1", "yes", " true", "true "])
def test_non_exact_true_runs(value: str):
    # Only the exact lowercase "true" triggers a skip (shell string equality).
    assert mod.evaluate_gate(value).skip is False


# ---------------------------------------------------------------------------
# render_output_file: the verdict file body
# ---------------------------------------------------------------------------


def test_render_output_file_matches_inline_block():
    body = mod.render_output_file(mod.evaluate_gate("true"))
    assert body == (
        "VERDICT: DID_NOT_RUN\n"
        "MESSAGE: AI review did not run because context build had an infrastructure failure.\n"
    )


# ---------------------------------------------------------------------------
# resolve_output_file: one cross-platform path shared by every action step
# ---------------------------------------------------------------------------


def test_module_has_no_hard_coded_output_path():
    assert "/tmp/ai-review-output.txt" not in _MODULE_PATH.read_text(encoding="utf-8")


def test_resolve_output_file_prefers_explicit_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    explicit = tmp_path / "explicit.txt"
    monkeypatch.setenv("AI_REVIEW_OUTPUT_FILE", str(explicit))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))

    assert mod.resolve_output_file() == str(explicit)


def test_resolve_output_file_uses_runner_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    runner_temp = tmp_path / "runner"
    monkeypatch.delenv("AI_REVIEW_OUTPUT_FILE", raising=False)
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))

    assert mod.resolve_output_file() == str(runner_temp / "ai-review-output.txt")


def test_resolve_output_file_falls_back_to_system_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("AI_REVIEW_OUTPUT_FILE", raising=False)
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    monkeypatch.setattr(mod.tempfile, "gettempdir", lambda: str(tmp_path))

    assert mod.resolve_output_file() == str(tmp_path / "ai-review-output.txt")


# ---------------------------------------------------------------------------
# emit: the sinks (GITHUB_OUTPUT, verdict file, warning)
# ---------------------------------------------------------------------------


def test_emit_skip_writes_file_outputs_and_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    out = tmp_path / "out.txt"
    output_file = tmp_path / "ai-review-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    mod.emit(mod.evaluate_gate("true"), str(output_file))

    out_text = out.read_text(encoding="utf-8")
    assert out_text.splitlines() == [
        f"output_file={output_file}",
        "skip=true",
        "infrastructure_failure=true",
        "retry_count=0",
    ]
    file_text = output_file.read_text(encoding="utf-8")
    assert file_text.startswith("VERDICT: DID_NOT_RUN\n")
    assert "MESSAGE: AI review did not run" in file_text
    captured = capsys.readouterr()
    assert "::warning::Skipping Copilot CLI invocation" in captured.out


def test_emit_run_writes_only_skip_false_and_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    out = tmp_path / "out.txt"
    output_file = tmp_path / "ai-review-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    mod.emit(mod.evaluate_gate(""), str(output_file))

    out_text = out.read_text(encoding="utf-8")
    assert out_text.splitlines() == [
        f"output_file={output_file}",
        "skip=false",
    ]
    assert not output_file.exists()  # no verdict file on the run path
    assert capsys.readouterr().out == ""  # no warning on the run path


def test_emit_without_github_output_is_silent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    output_file = tmp_path / "ai-review-output.txt"
    # Must not raise even though GITHUB_OUTPUT is unset; verdict file still written on skip.
    mod.emit(mod.evaluate_gate("true"), str(output_file))
    assert output_file.exists()


# ---------------------------------------------------------------------------
# main: the CLI exit contract and env plumbing
# ---------------------------------------------------------------------------


def test_main_skip_returns_zero_and_writes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    out = tmp_path / "out.txt"
    output_file = tmp_path / "ai-review-output.txt"
    monkeypatch.setenv("CONTEXT_INFRA_FAILURE", "true")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("AI_REVIEW_OUTPUT_FILE", str(output_file))

    assert mod.main() == 0
    assert "skip=true" in out.read_text(encoding="utf-8")
    assert output_file.read_text(encoding="utf-8").startswith("VERDICT: DID_NOT_RUN")


def test_main_skip_uses_runner_temp_without_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    out = tmp_path / "out.txt"
    monkeypatch.setenv("CONTEXT_INFRA_FAILURE", "true")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.delenv("AI_REVIEW_OUTPUT_FILE", raising=False)

    assert mod.main() == 0
    output_file = tmp_path / "ai-review-output.txt"
    assert output_file.read_text(encoding="utf-8").startswith("VERDICT: DID_NOT_RUN")
    assert f"output_file={output_file}" in out.read_text(encoding="utf-8")


def test_resolved_output_path_is_shared_with_bash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bash = shutil.which("bash")
    assert bash is not None

    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.delenv("AI_REVIEW_OUTPUT_FILE", raising=False)

    output_file = mod.resolve_output_file()
    env = os.environ.copy()
    env["AI_REVIEW_OUTPUT_FILE"] = output_file
    subprocess.run(
        [bash, "-c", 'printf "VERDICT: PASS\n" > "$AI_REVIEW_OUTPUT_FILE"'],
        env=env,
        check=True,
        timeout=10,
    )

    assert Path(output_file).read_text(encoding="utf-8") == "VERDICT: PASS\n"


def test_main_run_returns_zero_and_skips_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    out = tmp_path / "out.txt"
    output_file = tmp_path / "ai-review-output.txt"
    monkeypatch.setenv("CONTEXT_INFRA_FAILURE", "")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("AI_REVIEW_OUTPUT_FILE", str(output_file))

    assert mod.main() == 0
    assert "skip=false" in out.read_text(encoding="utf-8")
    assert not output_file.exists()


def test_main_missing_context_env_defaults_to_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    out = tmp_path / "out.txt"
    monkeypatch.delenv("CONTEXT_INFRA_FAILURE", raising=False)
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("AI_REVIEW_OUTPUT_FILE", str(tmp_path / "ai-review-output.txt"))

    assert mod.main() == 0
    assert "skip=false" in out.read_text(encoding="utf-8")


def test_main_unwritable_output_file_returns_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # A directory as the output-file path makes write_text raise OSError -> exit 2.
    unwritable = tmp_path / "as-dir"
    unwritable.mkdir()
    monkeypatch.setenv("CONTEXT_INFRA_FAILURE", "true")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setenv("AI_REVIEW_OUTPUT_FILE", str(unwritable))

    assert mod.main() == 2


def test_action_routes_gate_invoke_and_parse_through_one_output_path():
    action = _ACTION_PATH.read_text(encoding="utf-8")

    shared_env = "AI_REVIEW_OUTPUT_FILE: ${{ steps.infra_gate.outputs.output_file }}"
    assert action.count(shared_env) == 2
    assert "steps.infra_gate.outputs.infrastructure_failure" in action
    assert 'python3 "$GITHUB_WORKSPACE/scripts/ci/invoke_copilot_cli.py"' in action
    assert 'python3 "$GITHUB_WORKSPACE/scripts/ci/parse_ai_review_output.py"' in action
    assert "/tmp/ai-review-output.txt" not in action


def test_windows_contract_jobs_run_for_action_changes():
    workflow = _PYTEST_WORKFLOW_PATH.read_text(encoding="utf-8")

    # The ai-review action change still triggers the Windows path-contract job.
    #
    # Read from the shared policy rather than the workflow text. Issue #5318
    # moved the path list out of this workflow's inline filter and into
    # `scripts/test_selection/path_policy.yml`, so that the CI filter and the
    # local test selector cannot drift apart. Asserting against the workflow
    # text here would pass only while the list was duplicated, which is the
    # state that move exists to end. The property under test is unchanged: a
    # change to the ai-review action must still reach this filter.
    assert ".github/actions/ai-review/action.yml" in path_policy.load_patterns()
    # The single marker-based step replaces the old hardcoded per-file steps
    # (issue #4299). Both test_pytest_head_guard.py and this file carry
    # pytestmark = pytest.mark.windows_path, so they still run on Windows.
    assert workflow.count("- name: Run Windows path-contract tests") == 1
    timeout = yaml.safe_load(workflow)["jobs"]["test-windows-pwsh"]["timeout-minutes"]
    assert 1 <= timeout <= 15
