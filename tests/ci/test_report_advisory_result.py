"""The advisory reporter prints one typed line and never changes the exit code.

Issue #5636, decision D17 item 2. Every advisory step keeps the semantics it had
(exit 0 whatever the observed state), and gains a machine-readable state and
reason. Each mapping has a test; the CLI's exit code is asserted through
``main(argv)`` and through a real subprocess.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci import report_advisory_result as reporter

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "report_advisory_result.py"
BASE = ["--validator", "demo-check", "--scope", "the demo scope"]


@pytest.fixture(autouse=True)
def _clean_github_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY", "GITHUB_SHA"):
        monkeypatch.delenv(name, raising=False)


def _step(*extra: str, outcome: str) -> list[str]:
    return ["step", *BASE, "--outcome", outcome, *extra]


def _run_cmd(*extra: str, command: list[str]) -> list[str]:
    return ["run", *BASE, *extra, "--", *command]


def _first_line(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().out.splitlines()[0]


# --- step mode -------------------------------------------------------------


def test_a_successful_step_prints_a_pass_and_no_annotation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = reporter.main(_step(outcome="success"))

    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("[PASS] demo-check scope=the demo scope rev=WORKING_TREE")
    assert "::warning" not in out


def test_a_pass_records_the_commit_sha_when_actions_provides_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)

    reporter.main(_step(outcome="success"))

    assert f"rev={'a' * 40}" in capsys.readouterr().out


def test_a_failed_step_defaults_to_blocked_script_failed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = reporter.main(_step(outcome="failure"))

    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("[BLOCKED] demo-check reason=script.failed")
    assert "::warning title=demo-check::[BLOCKED]" in out


def test_a_failed_step_uses_the_configured_state_and_reason(
    capsys: pytest.CaptureFixture[str],
) -> None:
    reporter.main(
        _step("--failure-state", "FAIL", "--failure-reason", "advisory.findings", outcome="failure")
    )

    assert _first_line(capsys).startswith("[FAIL] demo-check reason=advisory.findings")


def test_a_cancelled_step_is_reported_as_a_failure(capsys: pytest.CaptureFixture[str]) -> None:
    reporter.main(_step(outcome="cancelled"))

    out = capsys.readouterr().out
    assert out.startswith("[BLOCKED] demo-check")
    assert "the step outcome was cancelled" in out


def test_a_skipped_step_is_a_typed_skip(capsys: pytest.CaptureFixture[str]) -> None:
    reporter.main(_step(outcome="skipped"))

    assert _first_line(capsys).startswith("[SKIP] demo-check reason=policy.exempt")


@pytest.mark.parametrize("outcome", ["", "Success", "neutral", " "])
def test_an_unreadable_outcome_is_unknown_never_pass(
    outcome: str, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = reporter.main(_step(outcome=outcome))

    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("[UNKNOWN] demo-check reason=output.malformed")
    assert "[PASS]" not in out


# --- run mode --------------------------------------------------------------


def test_a_command_that_exits_zero_is_a_pass_and_keeps_its_output(
    capfd: pytest.CaptureFixture[str],
) -> None:
    rc = reporter.main(_run_cmd(command=[sys.executable, "-c", "print('child output')"]))

    out = capfd.readouterr().out
    assert rc == 0
    assert "child output" in out
    assert "[PASS] demo-check" in out


def test_a_findings_exit_is_a_fail_with_advisory_findings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = reporter.main(_run_cmd(command=[sys.executable, "-c", "raise SystemExit(1)"]))

    assert rc == 0
    assert _first_line(capsys).startswith("[FAIL] demo-check reason=advisory.findings")


def test_findings_exit_codes_are_configurable(capsys: pytest.CaptureFixture[str]) -> None:
    reporter.main(
        _run_cmd("--findings-exit", "3", "4", command=[sys.executable, "-c", "raise SystemExit(4)"])
    )

    assert _first_line(capsys).startswith("[FAIL] demo-check reason=advisory.findings")


def test_any_other_nonzero_exit_is_a_tool_error_not_a_finding(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = reporter.main(_run_cmd(command=[sys.executable, "-c", "raise SystemExit(2)"]))

    assert rc == 0
    assert _first_line(capsys).startswith("[BLOCKED] demo-check reason=script.failed")


def test_a_missing_executable_is_blocked_tool_absent(capsys: pytest.CaptureFixture[str]) -> None:
    rc = reporter.main(_run_cmd(command=["definitely-not-a-real-binary-5636"]))

    assert rc == 0
    assert _first_line(capsys).startswith("[BLOCKED] demo-check reason=tool.absent")


def test_a_non_executable_command_is_blocked_tool_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = tmp_path / "notexec"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o644)

    rc = reporter.main(_run_cmd(command=[str(script)]))

    assert rc == 0
    assert "reason=tool.absent" in _first_line(capsys)


def test_a_timeout_is_blocked_with_the_timeout_reason(capsys: pytest.CaptureFixture[str]) -> None:
    rc = reporter.main(
        _run_cmd("--timeout", "1", command=[sys.executable, "-c", "import time; time.sleep(30)"])
    )

    assert rc == 0
    assert _first_line(capsys).startswith("[BLOCKED] demo-check reason=timeout")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_a_signal_death_is_blocked_process_signaled(capsys: pytest.CaptureFixture[str]) -> None:
    code = "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"

    rc = reporter.main(_run_cmd(command=[sys.executable, "-c", code]))

    assert rc == 0
    assert _first_line(capsys).startswith("[BLOCKED] demo-check reason=process.signaled")


# --- --propagate-errors keeps a crash failing ------------------------------


def _propagating(*extra: str, command: list[str]) -> list[str]:
    return _run_cmd("--propagate-errors", *extra, command=command)


def test_propagate_errors_still_exits_zero_on_success_and_on_findings() -> None:
    assert reporter.main(_propagating(command=[sys.executable, "-c", "pass"])) == 0
    assert reporter.main(_propagating(command=[sys.executable, "-c", "raise SystemExit(1)"])) == 0


def test_propagate_errors_returns_the_childs_own_error_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = reporter.main(_propagating(command=[sys.executable, "-c", "raise SystemExit(2)"]))

    assert rc == 2
    assert _first_line(capsys).startswith("[BLOCKED] demo-check reason=script.failed")


def test_propagate_errors_fails_when_the_executable_is_missing() -> None:
    assert reporter.main(_propagating(command=["definitely-not-a-real-binary-5636"])) == 3


def test_propagate_errors_fails_on_a_timeout() -> None:
    code = "import time; time.sleep(30)"

    assert reporter.main(_propagating("--timeout", "1", command=[sys.executable, "-c", code])) == 3


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_propagate_errors_fails_on_a_signal_death() -> None:
    code = "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"

    assert reporter.main(_propagating(command=[sys.executable, "-c", code])) == 3


def test_without_the_flag_a_child_crash_still_exits_zero() -> None:
    """Inverse: the flag is opt-in, so every other caller keeps its swallow."""
    assert reporter.main(_run_cmd(command=[sys.executable, "-c", "raise SystemExit(2)"])) == 0


def test_the_process_exit_code_carries_the_childs_code_under_the_flag() -> None:
    result = _process(*_propagating(command=[sys.executable, "-c", "raise SystemExit(5)"]))

    assert result.returncode == 5
    assert "reason=script.failed" in result.stdout


# --- bad arguments exit 2 --------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["run", *BASE, "--"],
        ["run", *BASE],
        ["step", *BASE],
        ["step", *BASE, "--outcome", "success", "--failure-state", "PASS"],
        ["step", *BASE, "--outcome", "failure", "--failure-reason", "Not A Code"],
        ["step", *BASE, "--outcome", "failure", "--failure-reason", ""],
        ["step", "--validator", "bad name", "--scope", "s", "--outcome", "success"],
        ["step", "--validator", "x\n::error::y", "--scope", "s", "--outcome", "success"],
        ["step", "--validator", "ok\n", "--scope", "s", "--outcome", "success"],
        ["step", *BASE, "--outcome", "failure", "--failure-reason", "timeout\n"],
        [],
        ["unknown-mode"],
    ],
)
def test_bad_arguments_exit_two(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        reporter.main(argv)

    assert raised.value.code == 2


# --- annotation, summary, outputs ------------------------------------------


def test_a_newline_in_the_detail_cannot_start_a_second_workflow_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    reporter.main(_step("--detail", "line one\n::error::forged 100%", outcome="failure"))

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert lines[1].startswith("::warning title=demo-check::")
    assert "::error::" not in lines[1].split("::warning", 1)[1].split("::", 2)[2]
    assert "%0A" not in lines[0]


def test_the_result_is_appended_to_the_step_summary_and_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary, output = tmp_path / "summary.md", tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    reporter.main(_step("--failure-reason", "timeout", outcome="failure"))

    assert "`BLOCKED` demo-check `timeout`" in summary.read_text(encoding="utf-8")
    assert output.read_text(encoding="utf-8") == "state=BLOCKED\nreason=timeout\n"


def test_a_pass_writes_an_empty_reason_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    reporter.main(_step(outcome="success"))

    assert output.read_text(encoding="utf-8") == "state=PASS\nreason=\n"


def test_an_unwritable_output_path_is_a_warning_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "missing-dir" / "out.txt"))

    rc = reporter.main(_step(outcome="success"))

    assert rc == 0
    assert "::warning::could not write out.txt" in capsys.readouterr().out


# --- the process exit code, and the bare-python constraint ------------------


def _process(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-S", str(SCRIPT), *argv],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def test_the_process_exits_zero_on_a_failed_step_and_runs_without_site_packages() -> None:
    """``-S`` drops site-packages, proving a bare ``python3`` step can run it."""
    result = _process(*_step(outcome="failure"))

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("[BLOCKED] demo-check")


def test_the_process_exits_zero_when_the_wrapped_command_crashes() -> None:
    result = _process(*_run_cmd(command=[sys.executable, "-c", "raise SystemExit(7)"]))

    assert result.returncode == 0
    assert "reason=script.failed" in result.stdout


def test_the_process_exits_two_on_bad_arguments() -> None:
    assert _process("step", *BASE).returncode == 2
