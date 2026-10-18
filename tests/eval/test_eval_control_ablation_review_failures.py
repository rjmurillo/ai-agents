"""Reviewer-arm failure handling in the ablation runner (issue #5768).

A reviewer launch that fails still costs money and time, a review copy that cannot
be built is a missing review and not a lost run, and a stale or hostile workspace
never reaches the reviewer. The Claude CLI is never invoked for real.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.eval._control_ablation_test_support import (
    FakeClaudeRunner,
    ablation_tasks,
    claude_run,
    cli,
    grade,
    live_reduced_args,
    load_tasks,
    outcome,
)

REVIEWER_MODEL = "claude-sonnet-5"
PRODUCER_COST = 0.01
REVIEW_COST = 0.02


def _records(tmp_path: Path) -> list[outcome.OutcomeRecord]:
    path = tmp_path / "out" / "records-reduced.jsonl"
    return [outcome.parse_record(json.loads(x)) for x in path.read_text("utf-8").splitlines()]


def _report(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))


def _review_args(tmp_path: Path, *extra: str) -> list[str]:
    return live_reduced_args(tmp_path, "--reviewer-model", REVIEWER_MODEL, *extra)


def test_a_failed_reviewer_launch_still_adds_its_cost_to_the_run(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(
        load_tasks(tmp_path), review_returncode=1, cost=PRODUCER_COST, review_cost=REVIEW_COST
    )

    code = cli.main(_review_args(tmp_path), runner=runner)

    assert code == cli.EXIT_EXTERNAL
    records = _records(tmp_path)
    assert records
    for record in records:
        assert record.durable.review_findings is None
        assert record.economics.model_cost_usd == pytest.approx(PRODUCER_COST + REVIEW_COST)


def test_a_successful_reviewer_launch_adds_the_same_cost(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path), cost=PRODUCER_COST, review_cost=REVIEW_COST)

    assert cli.main(_review_args(tmp_path), runner=runner) == cli.EXIT_OK

    for record in _records(tmp_path):
        assert record.economics.model_cost_usd == pytest.approx(PRODUCER_COST + REVIEW_COST)


def _stream(model: str, cost: float | None, *, is_error: bool = False) -> str:
    result: dict[str, object] = {"type": "result", "subtype": "success", "result": "reply"}
    if cost is not None:
        result["total_cost_usd"] = cost
    if is_error:
        result["is_error"] = True
    events = [{"type": "system", "subtype": "init", "model": model}, result]
    return "\n".join(json.dumps(event) for event in events) + "\n"


def _runner(returncode: int, stdout: str) -> Any:
    def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")

    return run


@pytest.mark.parametrize(
    ("returncode", "stdout", "expected_cost"),
    [
        (1, _stream(REVIEWER_MODEL, 0.4), 0.4),
        (0, _stream(REVIEWER_MODEL, 0.3, is_error=True), 0.3),
        (0, _stream("claude-opus-9", 0.2), 0.2),
        (0, _stream(REVIEWER_MODEL, None), 0.0),
        (1, "not json at all", 0.0),
        (0, "not json at all", 0.0),
    ],
)
def test_a_failed_launch_carries_the_cost_its_stream_reported(
    tmp_path: Path, returncode: int, stdout: str, expected_cost: float
) -> None:
    with pytest.raises(claude_run.HarnessFailureError) as raised:
        claude_run.invoke_reviewer(
            tmp_path, "prompt", REVIEWER_MODEL, 30.0, _runner(returncode, stdout)
        )

    assert raised.value.cost_usd == pytest.approx(expected_cost)
    assert raised.value.wall_seconds >= 0.0


def test_a_timed_out_launch_carries_its_elapsed_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = iter([100.0, 107.5])
    monkeypatch.setattr(claude_run.time, "monotonic", lambda: next(clock))

    def hang(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, 30.0)

    with pytest.raises(claude_run.HarnessFailureError) as raised:
        claude_run.invoke_reviewer(tmp_path, "prompt", REVIEWER_MODEL, 30.0, hang)

    assert raised.value.wall_seconds == pytest.approx(7.5)
    assert raised.value.cost_usd == 0.0


def test_a_failure_that_ran_nothing_carries_zero() -> None:
    error = claude_run.HarnessFailureError("boom")

    assert (error.cost_usd, error.wall_seconds) == (0.0, 0.0)


class SymlinkingRunner(FakeClaudeRunner):
    """A producer that, besides its fix, plants a symlink to a file outside the workspace."""

    outside: Path

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        result = super().__call__(argv, **kwargs)
        if "--tools" in argv and "Bash" in argv[argv.index("--tools") + 1]:
            link = Path(str(kwargs["cwd"])) / "escape.txt"
            if not link.is_symlink():
                link.symlink_to(self.outside)
        return result


def test_an_escaping_symlink_in_the_change_does_not_abort_the_run(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n", encoding="utf-8")
    runner = SymlinkingRunner(load_tasks(tmp_path))
    runner.outside = outside

    code = cli.main(_review_args(tmp_path), runner=runner)

    assert code == cli.EXIT_OK
    assert len(_records(tmp_path)) == 5
    assert (tmp_path / "out" / "report.json").is_file()
    assert runner.review_calls
    assert all("escape.txt" not in call["files"] for call in runner.review_calls)


def test_a_review_copy_that_cannot_be_built_is_a_missing_review_not_a_lost_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise ablation_tasks.ControlAblationConfigError("path escapes the workspace")

    monkeypatch.setattr(grade, "review_copy", refuse)
    runner = FakeClaudeRunner(load_tasks(tmp_path))

    code = cli.main(_review_args(tmp_path), runner=runner)

    assert code == cli.EXIT_EXTERNAL
    assert runner.review_calls == []
    records = _records(tmp_path)
    assert len(records) == 5
    assert {r.durable.review_findings for r in records} == {None}
    assert all("review copy failed" in run["reviewer_note"] for run in _report(tmp_path)["runs"])


def test_an_oserror_building_the_review_copy_is_also_a_missing_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(grade, "review_copy", fail)
    runner = FakeClaudeRunner(load_tasks(tmp_path))

    code = cli.main(_review_args(tmp_path), runner=runner)

    assert code == cli.EXIT_EXTERNAL and len(_records(tmp_path)) == 5


def test_a_review_copy_from_an_earlier_run_is_not_shown_to_the_reviewer(tmp_path: Path) -> None:
    stale = tmp_path / "ws" / "hidden-regression-reduced-0.review"
    stale.mkdir(parents=True)
    (stale / "previous_agent_change.py").write_text("old agent\n", encoding="utf-8")
    runner = FakeClaudeRunner(load_tasks(tmp_path))

    code = cli.main(_review_args(tmp_path, "--only-tasks", "hidden-regression"), runner=runner)

    assert code == cli.EXIT_OK and len(runner.review_calls) == 1
    assert "previous_agent_change.py" not in runner.review_calls[0]["files"]
