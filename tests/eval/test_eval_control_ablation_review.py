"""Tests for the reviewer arm, recovery path, and dry-run signal checks of the ablation CLI.

Issue #5768. The Claude CLI is never invoked for real: `FakeClaudeRunner` plays its
part, including the reviewer launch. Git and `python3` grading run for real.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._control_ablation_test_support import (
    FakeClaudeRunner,
    ablation,
    cli,
    dry_run,
    durable_outcome,
    grade,
    live_reduced_args,
    load_tasks,
    outcome,
    review,
    write_tasks,
)

REVIEWER_MODEL = "claude-sonnet-5"


def _records(tmp_path: Path, control: str = "reduced") -> list[outcome.OutcomeRecord]:
    path = tmp_path / "out" / f"records-{control}.jsonl"
    return [outcome.parse_record(json.loads(x)) for x in path.read_text("utf-8").splitlines()]


def _report(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))


def test_without_a_reviewer_the_signals_are_null_and_the_record_is_unverified(
    tmp_path: Path,
) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path))

    code = cli.main(live_reduced_args(tmp_path), runner=runner)

    assert code == cli.EXIT_OK and runner.review_calls == []
    for record in _records(tmp_path):
        assert record.config.reviewer == "none"
        assert record.durable.review_findings is None
        assert record.economics.human_correction_minutes is None
        assert durable_outcome.classify(record) is durable_outcome.Verdict.UNVERIFIED


def test_a_reviewer_runs_once_per_accepted_change_and_records_zero_findings(
    tmp_path: Path,
) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path))

    code = cli.main(live_reduced_args(tmp_path, "--reviewer-model", REVIEWER_MODEL), runner=runner)

    assert code == cli.EXIT_OK and len(runner.review_calls) == 5
    for record in _records(tmp_path):
        assert record.config.reviewer == f"claude:{REVIEWER_MODEL}:default"
        assert record.durable.review_findings == 0
        assert record.durable.rollback_events == 0
        # Producer 0.01 plus reviewer 0.02: the review is part of the price.
        assert record.economics.model_cost_usd == pytest.approx(0.03)
        assert record.economics.human_correction_minutes is None


def test_reviewer_findings_are_counted_from_the_reply(tmp_path: Path) -> None:
    reply = f'{review.REVIEW_MARKER} {{"findings": ["off by one", "no test"]}}'
    runner = FakeClaudeRunner(load_tasks(tmp_path), review_reply=reply)

    cli.main(live_reduced_args(tmp_path, "--reviewer-model", REVIEWER_MODEL), runner=runner)

    assert {r.durable.review_findings for r in _records(tmp_path)} == {2}


def test_a_malformed_review_reply_is_null_not_zero(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path), review_reply="Looks good to me.")

    code = cli.main(live_reduced_args(tmp_path, "--reviewer-model", REVIEWER_MODEL), runner=runner)

    assert code == cli.EXIT_OK
    assert {r.durable.review_findings for r in _records(tmp_path)} == {None}


def test_a_failed_reviewer_keeps_the_record_flags_it_and_exits_external(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path), review_returncode=1)

    code = cli.main(live_reduced_args(tmp_path, "--reviewer-model", REVIEWER_MODEL), runner=runner)

    assert code == cli.EXIT_EXTERNAL
    records = _records(tmp_path)
    assert len(records) == 5 and {r.durable.review_findings for r in records} == {None}
    runs = _report(tmp_path)["runs"]
    assert all("claude exited 1" in run["reviewer_note"] for run in runs)


def test_the_reviewer_sees_the_change_but_no_control_hidden_file_or_edit_tool(
    tmp_path: Path,
) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path))
    args = live_reduced_args(tmp_path, "--only-tasks", "hidden-regression")
    args[args.index("reduced")] = "full"

    code = cli.main([*args, "--reviewer-model", REVIEWER_MODEL], runner=runner)

    assert code == cli.EXIT_OK and len(runner.review_calls) == 1
    seen = runner.review_calls[0]
    files = set(seen["files"])
    assert {"calc/core.py", "tests/test_core.py"} <= files
    assert "AGENTS.md" not in files and "CLAUDE.md" not in files
    assert not [f for f in files if f.startswith((".claude/", "followup/", ".git/"))]
    argv = seen["argv"]
    assert argv[argv.index("--tools") + 1] == "Read,Glob,Grep"
    assert "--allowedTools" not in argv
    assert "def subtract" in (
        tmp_path / "ws" / "hidden-regression-full-0" / "calc" / "core.py"
    ).read_text("utf-8")


def test_the_reviewer_prompt_carries_the_requirement_and_no_hidden_check(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path))

    cli.main(
        live_reduced_args(
            tmp_path, "--only-tasks", "hidden-regression", "--reviewer-model", REVIEWER_MODEL
        ),
        runner=runner,
    )

    prompt = str(runner.review_calls[0]["prompt"])
    assert prompt.startswith(review.REVIEWER_INSTRUCTIONS)
    assert "Add a subtract(a, b) function to calc/core.py." in prompt
    assert "test_hidden" not in prompt and "subtract(10, 4)" not in prompt


def test_an_unaccepted_change_gets_no_review_and_no_rollback(tmp_path: Path) -> None:
    broken = {"calc/core.py": "def add(a, b):\n    return 0\n"}
    runner = FakeClaudeRunner(load_tasks(tmp_path), extra_files=broken)

    code = cli.main(
        live_reduced_args(
            tmp_path, "--only-tasks", "hidden-regression", "--reviewer-model", REVIEWER_MODEL
        ),
        runner=runner,
    )

    assert code == cli.EXIT_OK and runner.review_calls == []
    (record,) = _records(tmp_path)
    assert record.execution.deterministic_acceptance.value == "FAIL"
    assert record.durable.review_findings is None
    assert record.durable.rollback_events == 0
    assert durable_outcome.classify(record) is durable_outcome.Verdict.REJECTED
    note = _report(tmp_path)["runs"][0]["reviewer_note"]
    assert note == cli.REVIEW_SKIPPED


def test_an_accepted_change_that_fails_follow_up_is_reverted_and_counted(
    tmp_path: Path,
) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path), kind="known_bad")

    code = cli.main(
        live_reduced_args(
            tmp_path, "--only-tasks", "hidden-regression", "--reviewer-model", REVIEWER_MODEL
        ),
        runner=runner,
    )

    assert code == cli.EXIT_OK
    (record,) = _records(tmp_path)
    assert record.execution.deterministic_acceptance.value == "PASS"
    assert record.durable.followup_validation.value == "FAIL"
    assert record.durable.rollback_events == 1
    # No human timed the pass, so the live record is UNVERIFIED until one does.
    assert durable_outcome.classify(record) is durable_outcome.Verdict.UNVERIFIED
    timed = dataclasses.replace(
        record, economics=dataclasses.replace(record.economics, human_correction_minutes=0.0)
    )
    assert durable_outcome.classify(timed) is durable_outcome.Verdict.ACCEPTED_NOT_DURABLE
    workspace = tmp_path / "ws" / "hidden-regression-reduced-0"
    assert grade.changed_paths(workspace) == ()
    assert "return 3" not in (workspace / "calc" / "core.py").read_text("utf-8")


def test_a_change_that_stays_correct_needs_no_rollback(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path), kind="known_good")

    cli.main(live_reduced_args(tmp_path, "--only-tasks", "hidden-regression"), runner=runner)

    (record,) = _records(tmp_path)
    assert record.durable.rollback_events == 0
    workspace = tmp_path / "ws" / "hidden-regression-reduced-0"
    assert "def subtract" in (workspace / "calc" / "core.py").read_text("utf-8")


def test_an_unverifiable_revert_is_null_not_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(grade, "rollback_to_seed", lambda _workspace: False)
    runner = FakeClaudeRunner(load_tasks(tmp_path), kind="known_bad")

    cli.main(live_reduced_args(tmp_path, "--only-tasks", "hidden-regression"), runner=runner)

    (record,) = _records(tmp_path)
    assert record.durable.rollback_events is None
    assert durable_outcome.classify(record) is durable_outcome.Verdict.UNVERIFIED


def test_the_run_cap_counts_the_reviewer_launches(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path))

    code = cli.main(
        live_reduced_args(tmp_path, "--max-runs", "9", "--reviewer-model", REVIEWER_MODEL),
        runner=runner,
    )

    assert code == cli.EXIT_CONFIG and runner.calls == []


def test_the_run_cap_allows_the_reviewer_when_it_fits(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path))

    code = cli.main(
        live_reduced_args(tmp_path, "--max-runs", "10", "--reviewer-model", REVIEWER_MODEL),
        runner=runner,
    )

    assert code == cli.EXIT_OK


def test_a_blank_reviewer_model_is_refused_before_any_call(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path))

    code = cli.main(live_reduced_args(tmp_path, "--reviewer-model", "  "), runner=runner)

    assert code == cli.EXIT_CONFIG and runner.calls == []


def test_a_reviewer_model_with_a_colon_is_refused_before_any_call(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path))

    code = cli.main(live_reduced_args(tmp_path, "--reviewer-model", "a:b"), runner=runner)

    assert code == cli.EXIT_CONFIG and runner.calls == []


def _dry_run(tmp_path: Path) -> tuple[int, dict[str, Any]]:
    code = cli.main(
        [
            "--tasks",
            str(write_tasks(tmp_path)),
            "--dry-run",
            "--workspace-root",
            str(tmp_path / "ws"),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    return code, _report(tmp_path)


def test_dry_run_proves_nonzero_review_and_a_real_rollback_discriminate(tmp_path: Path) -> None:
    code, report = _dry_run(tmp_path)

    assert code == cli.EXIT_OK and report["signal_problems"] == []
    by_key = {(r["task_id"], r["kind"]): r["record"] for r in report["runs"]}
    good = by_key[("hidden-regression", "known_good")]
    bad = by_key[("hidden-regression", "known_bad")]
    assert good["durable"]["review_findings"] == 0 and good["durable"]["rollback_events"] == 0
    assert bad["durable"]["review_findings"] == 1 and bad["durable"]["rollback_events"] == 1
    assert good["config"]["reviewer"] == review.DRY_RUN_REVIEWER
    assert "fixture" in report["dry_run_inputs"]


def test_dry_run_fails_when_the_driver_stops_measuring_review_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ablation, "review_findings", lambda _code, _reply: None)

    code, report = _dry_run(tmp_path)

    assert code == cli.EXIT_LOGIC and report["status"] == "FAIL"
    assert any("review_findings" in problem for problem in report["signal_problems"])


def test_dry_run_fails_when_the_rollback_cannot_be_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(grade, "rollback_to_seed", lambda _workspace: False)

    code, report = _dry_run(tmp_path)

    assert code == cli.EXIT_LOGIC
    assert any("rollback_events" in problem for problem in report["signal_problems"])


def test_dry_run_fails_when_a_known_good_reports_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    noisy = f'{review.REVIEW_MARKER} {{"findings": ["spurious"]}}'
    monkeypatch.setitem(dry_run.DRY_RUN_REVIEWS, "known_good", noisy)

    code, report = _dry_run(tmp_path)

    assert code == cli.EXIT_LOGIC
    assert any("known_good review_findings" in p for p in report["signal_problems"])
