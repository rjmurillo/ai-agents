"""`pre_pr.py --compact` prints only the gates that did not pass (issue #6734, item 5).

The pre-push hook ran `pre_pr.py` and a failed push scrolled 1007 lines
(231 PASS, 110 RUNNING, 17 SKIP lines) past the one gate that failed, with its
file and line near the top. Under `--compact` a gate that passes, or whose skip
means the fast stage already ran it, prints nothing. Every other skip and every
failing gate prints its own output, name, and verdict.

Coverage:

- positive: a failing gate keeps its path:line output, its name, and its verdict.
- negative: a passing gate and an already-run skip print nothing; default output is unchanged.
- edge: the summary lists only the rows that did not pass; the CLI flag parses.
- integration: the lefthook pre-push job passes `--compact`.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import pytest
import yaml

from scripts.validation import pre_pr
from scripts.validation.evidence import REASON_ALREADY_RUN, REASON_SCRIPT_ABSENT, CheckOutcome
from scripts.validation.pre_pr_state import ValidationState

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import pre_pr_sequence

LINT_FINDING = "docs/probe.md:3 error MD040/fenced-code-language"


def _passing() -> bool:
    print("[OK] scanned 686 files")
    return True


def _failing() -> CheckOutcome:
    print(LINT_FINDING)
    return CheckOutcome.failed("Markdown Linting", reason="legacy.boolean_contract", detail="bad")


def _already_run() -> CheckOutcome:
    print("nothing to scan")
    return CheckOutcome.skipped("Lint", reason=REASON_ALREADY_RUN, detail="ran in the fast stage")


def _script_absent() -> CheckOutcome:
    return CheckOutcome.skipped("Lint", reason=REASON_SCRIPT_ABSENT, detail="validator missing")


def test_compact_failing_gate_keeps_path_line_name_and_verdict(
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = ValidationState(compact=True)

    accepted = pre_pr.run_validation("Markdown Linting", state, _failing)

    out = capsys.readouterr().out
    assert accepted is False
    assert LINT_FINDING in out
    assert "=== Markdown Linting ===" in out
    assert "[FAIL] Markdown Linting completed" in out


def test_compact_passing_gate_prints_nothing_but_is_recorded(
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = ValidationState(compact=True)

    accepted = pre_pr.run_validation("Syntax", state, _passing)

    assert accepted is True
    assert capsys.readouterr().out == ""
    assert state.passed == 1
    assert state.total == 1


def test_compact_already_run_skip_prints_nothing_but_is_recorded(
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = ValidationState(compact=True)

    pre_pr.run_validation("Lint", state, _already_run)

    assert capsys.readouterr().out == ""
    assert state.skipped == 1


def test_compact_keeps_a_skip_that_means_the_validator_did_not_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = ValidationState(compact=True)

    pre_pr.run_validation("Lint", state, _script_absent)

    out = capsys.readouterr().out
    assert "[SKIP] Lint completed" in out
    assert REASON_SCRIPT_ABSENT in out


def test_compact_quick_mode_skip_is_still_printed(capsys: pytest.CaptureFixture[str]) -> None:
    state = ValidationState(compact=True)

    pre_pr.run_validation("Slow", state, _passing, skip=True)

    assert "[SKIP] Slow (skipped due to --quick flag)" in capsys.readouterr().out
    assert state.skipped == 1


def test_default_output_still_prints_every_gate(capsys: pytest.CaptureFixture[str]) -> None:
    state = ValidationState()

    pre_pr.run_validation("Syntax", state, _passing)

    out = capsys.readouterr().out
    assert "=== Syntax ===" in out
    assert "[RUNNING] Starting validation..." in out
    assert "[OK] scanned 686 files" in out
    assert "[PASS] Syntax completed" in out


def test_compact_failure_is_not_lost_when_a_gate_raises(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def boom() -> bool:
        print("partial output before the crash")
        raise RuntimeError("scanner exploded")

    state = ValidationState(compact=True)

    accepted = pre_pr.run_validation("Scanner", state, boom)

    out = capsys.readouterr().out
    assert accepted is False
    assert "partial output before the crash" in out
    assert "scanner exploded" in out


def test_compact_summary_lists_only_rows_that_did_not_pass(
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = ValidationState(compact=True)
    pre_pr.run_validation("Syntax", state, _passing)
    pre_pr.run_validation("Lint", state, _already_run)
    pre_pr.run_validation("Markdown Linting", state, _failing)
    capsys.readouterr()
    summary = pre_pr.aggregate("pre_pr", state.outcomes(), pre_pr._POLICY, 1.0)

    pre_pr._print_summary(summary, state)

    out = capsys.readouterr().out
    assert "Total Validations: 3" in out
    detailed = out.split("=== Detailed Results ===", 1)[1]
    assert "Markdown Linting" in detailed
    assert "Syntax" not in detailed
    assert "Lint\n" not in detailed


def test_sequence_skip_for_an_already_run_gate_is_silent_under_compact(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = next(g for g in pre_pr_sequence._SEQUENCE if g.already_run_by)
    monkeypatch.setenv(pre_pr_sequence.FAST_STAGE_RAN_ENV, "1")
    monkeypatch.setattr(pre_pr_sequence, "_SEQUENCE", (gate,))
    args = argparse.Namespace(quick=False, compact=True)
    state = ValidationState(compact=True)

    pre_pr_sequence.run_all_validations(Path("."), args, state, pre_pr.run_validation)

    assert capsys.readouterr().out == ""
    assert state.skipped == 1


def test_sequence_skip_for_an_already_run_gate_still_prints_by_default(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = next(g for g in pre_pr_sequence._SEQUENCE if g.already_run_by)
    monkeypatch.setenv(pre_pr_sequence.FAST_STAGE_RAN_ENV, "1")
    monkeypatch.setattr(pre_pr_sequence, "_SEQUENCE", (gate,))
    args = argparse.Namespace(quick=False)
    state = ValidationState()

    pre_pr_sequence.run_all_validations(Path("."), args, state, pre_pr.run_validation)

    assert f"[SKIP] {gate.name}" in capsys.readouterr().out


def test_compact_flag_parses_and_defaults_off() -> None:
    parser = pre_pr.build_parser()

    assert parser.parse_args(["--compact"]).compact is True
    assert parser.parse_args([]).compact is False


def test_pre_push_pre_pr_job_runs_compact() -> None:
    config = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "lefthook.yml").read_text(encoding="utf-8")
    )
    jobs = [
        job
        for entry in config["pre-push"]["jobs"]
        for job in (entry.get("group", {}).get("jobs") or [entry])
    ]
    command = next(job["run"] for job in jobs if job.get("name") == "pre-pr-validation")

    assert re.search(r"pre_pr\.py --compact(\s|$)", command)


def test_held_output_is_released_when_a_gate_exits_the_process(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def exits() -> bool:
        print("finding before sys.exit")
        raise SystemExit(2)

    state = ValidationState(compact=True)

    with pytest.raises(SystemExit):
        pre_pr.run_validation("Exiting gate", state, exits)

    out = capsys.readouterr().out
    assert "finding before sys.exit" in out
    assert "=== Exiting gate ===" in out


def test_a_slow_held_gate_is_named_before_it_finishes(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # pre_pr imports the flat module name, so patch the module that owns HeldOutput.
    console = sys.modules[pre_pr.HeldOutput.__module__]
    monkeypatch.setattr(console, "SLOW_AFTER_SECONDS", 0.05)
    seen_while_running: list[str] = []

    def slow() -> bool:
        time.sleep(0.4)
        seen_while_running.append(capsys.readouterr().out)
        return True

    state = ValidationState(compact=True)

    pre_pr.run_validation("Hanging Gate", state, slow)

    assert "[SLOW] Hanging Gate still running after 0.05s" in seen_while_running[0]
    assert capsys.readouterr().out == ""


def test_a_fast_held_gate_never_prints_the_slow_line(capsys: pytest.CaptureFixture[str]) -> None:
    state = ValidationState(compact=True)

    pre_pr.run_validation("Quick Gate", state, _passing)
    time.sleep(0.1)

    assert capsys.readouterr().out == ""
