"""Transient provider errors in the strategy comparison (issue #7350, protocol v2)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.eval._control_ablation_history_support import HistoryRepo, make_history_repo
from tests.eval.test_handoff_strategy import FakeRunner, corpus

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _control_ablation as ablation  # noqa: E402
import _control_ablation_claude as claude_run  # noqa: E402
import _handoff_strategy as hs  # noqa: E402
import eval_handoff_strategy as cli  # noqa: E402
from _runtime_harness import REAL_HOME_ENV  # noqa: E402

RATE_LIMITED = (
    json.dumps({"type": "system", "subtype": "init", "model": "claude-sonnet-5-5"})
    + "\n"
    + json.dumps(
        {
            "type": "result",
            "subtype": "error",
            "is_error": True,
            "result": "rate_limit_error",
            "total_cost_usd": 0,
        }
    )
    + "\n"
)


class FlakyRunner(FakeRunner):
    """Fail the launches whose 1-based call number is in `fail_calls` with a rate limit."""

    def __init__(
        self, *args: Any, fail_calls: set[int], stdout: str = RATE_LIMITED, **kw: Any
    ) -> None:
        super().__init__(*args, **kw)
        self.fail_calls, self.fail_stdout = fail_calls, stdout

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if len(self.calls) + 1 in self.fail_calls:
            self.calls.append([str(a) for a in argv])
            return subprocess.CompletedProcess(argv, 1, stdout=self.fail_stdout, stderr="")
        return super().__call__(argv, **kwargs)


@pytest.fixture
def repo(tmp_path: Path) -> HistoryRepo:
    return make_history_repo(tmp_path / "history")


def run(
    repo: HistoryRepo,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner_kwargs: dict[str, Any],
    sleeps: list[float],
):
    monkeypatch.setenv(REAL_HOME_ENV, "1")
    loaded = corpus(repo)
    task = loaded.tasks[0]
    runner = FlakyRunner(task, **runner_kwargs)
    result = cli.run_cell(
        task,
        loaded.briefs[task.id],
        hs.ARM_HANDOFF,
        0,
        ablation.ControlFiles(name="full", files={}, context_bytes=0),
        role="R",
        model="claude-sonnet-5-5",
        effort=None,
        harness_version="t",
        timeout=30.0,
        workspace_root=tmp_path / "ws",
        runner=runner,
        markers=(),
        sleep=sleeps.append,
    )
    return result, runner


class TestDetector:
    def test_a_rate_limit_stream_with_a_reported_cost_is_transient(self) -> None:
        assert claude_run.is_transient_failure(RATE_LIMITED) is True

    def test_an_overload_is_transient_too(self) -> None:
        assert claude_run.is_transient_failure(RATE_LIMITED.replace("rate_limit", "overloaded"))

    def test_a_rate_limit_with_no_reported_cost_is_not_transient(self) -> None:
        no_cost = RATE_LIMITED.replace(', "total_cost_usd": 0', "")
        assert claude_run.is_transient_failure(no_cost) is False

    def test_other_errors_and_garbage_are_not_transient(self) -> None:
        assert claude_run.is_transient_failure("authentication_error") is False
        assert claude_run.is_transient_failure("rate_limit_error but not a stream") is False

    def test_the_flag_defaults_to_false(self) -> None:
        assert claude_run.HarnessFailureError("x").transient is False


class TestCellRetry:
    def test_a_transient_failure_is_retried_and_is_not_a_repair_turn(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleeps: list[float] = []
        (entry, *_), runner = run(repo, tmp_path, monkeypatch, {"fail_calls": {1, 2}}, sleeps)
        assert entry["accepted"] is True
        assert entry["repair_turns"] == 0
        assert entry["transient_retries"] == 2
        assert sleeps == list(hs.TRANSIENT_WAITS[:2])
        assert len(runner.calls) == 4  # two failed attempts, then investigator and producer

    def test_retries_are_bounded_and_the_failure_stays_transient(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleeps: list[float] = []
        everything = set(range(1, 20))
        with pytest.raises(claude_run.HarnessFailureError) as caught:
            run(repo, tmp_path, monkeypatch, {"fail_calls": everything}, sleeps)
        assert caught.value.transient is True
        assert sleeps == list(hs.TRANSIENT_WAITS)

    def test_a_failure_after_earlier_launches_carries_their_spend(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleeps: list[float] = []
        # Call 1 (investigator) succeeds at $0.01; every later call is rate limited.
        later = set(range(2, 20))
        with pytest.raises(claude_run.HarnessFailureError) as caught:
            run(repo, tmp_path, monkeypatch, {"fail_calls": later}, sleeps)
        assert caught.value.cost_usd == pytest.approx(0.01)

    def test_a_non_transient_failure_is_not_retried(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleeps: list[float] = []
        auth = RATE_LIMITED.replace("rate_limit_error", "authentication_error")
        with pytest.raises(claude_run.HarnessFailureError) as caught:
            run(repo, tmp_path, monkeypatch, {"fail_calls": {1}, "stdout": auth}, sleeps)
        assert caught.value.transient is False
        assert sleeps == []
