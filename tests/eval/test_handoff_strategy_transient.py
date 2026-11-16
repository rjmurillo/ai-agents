"""Transient provider errors in the strategy comparison (issue #7350, protocol v2)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.eval._control_ablation_history_support import HistoryRepo, make_history_repo
from tests.eval.test_handoff_strategy import FakeRunner, corpus, v3_task

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _control_ablation as ablation  # noqa: E402
import _control_ablation_claude as claude_run  # noqa: E402
import _control_ablation_tasks as ablation_tasks  # noqa: E402
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
        assert caught.value.cost_usd == 0.0  # this launch reported none
        assert caught.value.prior_cost_usd == pytest.approx(0.01)

    def test_a_non_transient_failure_is_not_retried(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleeps: list[float] = []
        auth = RATE_LIMITED.replace("rate_limit_error", "authentication_error")
        with pytest.raises(claude_run.HarnessFailureError) as caught:
            run(repo, tmp_path, monkeypatch, {"fail_calls": {1}, "stdout": auth}, sleeps)
        assert caught.value.transient is False
        assert sleeps == []


def _entry(task: str, arm: str, repeat: int, accepted: bool = True) -> dict[str, Any]:
    return {
        "task_id": task,
        "arm": arm,
        "repeat": repeat,
        "valid": True,
        "accepted": accepted,
        "regression": False,
        "scope_violations": 0,
        "wall_seconds": 10.0,
    }


def _batch(path: Path, entries: list[dict[str, Any]], tasks_sha: str = "a" * 64) -> Path:
    path.mkdir(parents=True)
    report = {
        "entries": entries,
        "effort": "medium",
        "provenance": {"tasks_file_sha256": tasks_sha, "model_requested": "claude-sonnet-5-5"},
    }
    (path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return path


TASKS = {"tasks": [{"id": "s", "stall": True}, {"id": "n", "stall": False}]}


class TestCombine:
    def test_a_second_batch_fills_the_cells_the_first_lost(self, tmp_path: Path) -> None:
        cells = [(t, a, r) for t in ("s", "n") for r in range(3) for a in hs.ARMS]
        first = _batch(tmp_path / "a", [_entry(*c) for c in cells[:8]])
        second = _batch(tmp_path / "b", [_entry(*c) for c in cells[8:]])
        result = hs.combine([first, second], TASKS)
        assert result["cells"] == result["expected_cells"] == 12
        assert result["decision"]["outcome"] == "INCONCLUSIVE"
        assert "stalled task" in result["decision"]["reasons"][0]

    def test_a_cell_missing_from_every_batch_is_inconclusive(self, tmp_path: Path) -> None:
        cells = [(t, a, r) for t in ("s", "n") for r in range(3) for a in hs.ARMS]
        only = _batch(tmp_path / "a", [_entry(*c) for c in cells[:11]])
        result = hs.combine([only], TASKS)
        assert result["decision"]["reasons"][0] == "missing or invalid cells"

    def test_a_cell_in_two_batches_is_refused(self, tmp_path: Path) -> None:
        one = _batch(tmp_path / "a", [_entry("s", hs.ARM_CONTINUE, 0)])
        two = _batch(tmp_path / "b", [_entry("s", hs.ARM_CONTINUE, 0)])
        with pytest.raises(ablation_tasks.ControlAblationConfigError, match="more than one"):
            hs.combine([one, two], TASKS)

    def test_the_cli_writes_the_decision_and_exits_zero(self, tmp_path: Path) -> None:
        tasks = tmp_path / "tasks.json"
        tasks.write_text(json.dumps(TASKS), encoding="utf-8")
        sha = hashlib.sha256(tasks.read_bytes()).hexdigest()
        one = _batch(tmp_path / "a", [_entry("s", hs.ARM_CONTINUE, 0)], tasks_sha=sha)
        out = tmp_path / "out"
        code = cli.main(["--combine", str(one), "--tasks", str(tasks), "--output-dir", str(out)])
        assert code == cli.EXIT_OK
        assert json.loads((out / "decision.json").read_text("utf-8"))["cells"] == 1

    def test_the_cli_exits_2_when_a_report_is_missing(self, tmp_path: Path) -> None:
        tasks = tmp_path / "tasks.json"
        tasks.write_text(json.dumps(TASKS), encoding="utf-8")
        code = cli.main(["--combine", str(tmp_path / "nowhere"), "--tasks", str(tasks)])
        assert code == cli.EXIT_CONFIG


class TestStartRepeat:
    @pytest.mark.parametrize(("start", "repeats"), [(2, 2), (3, 1), (-1, 1)])
    def test_repeats_past_the_frozen_ceiling_are_refused_before_a_launch(
        self, repo: HistoryRepo, tmp_path: Path, start: int, repeats: int
    ) -> None:
        tasks = tmp_path / "tasks.json"
        tasks.write_text(
            json.dumps({"schema_version": 3, "tasks": [v3_task(repo)]}), encoding="utf-8"
        )
        code = cli.main(
            [
                "--tasks",
                str(tasks),
                "--repeats",
                str(repeats),
                "--start-repeat",
                str(start),
                "--real-home",
                "--workspace-root",
                str(tmp_path / "w"),
                "--output-dir",
                str(tmp_path / "out"),
            ],
            runner=lambda *a, **k: pytest.fail("a launch happened"),
        )
        assert code == cli.EXIT_CONFIG


class TestProvenanceOrder:
    def test_runner_state_is_taken_before_the_first_launch(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(REAL_HOME_ENV, "0")
        loaded = corpus(repo)
        task = loaded.tasks[0]
        runner = FakeRunner(task)
        seen: list[int] = []
        in_run: list[str | None] = []

        def version_aware(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if "--version" in argv:
                return subprocess.CompletedProcess(argv, 0, stdout="2.3.1\n", stderr="")
            return runner(argv, **kwargs)

        real_state = cli.batch.runner_state

        def spy(root: Path) -> dict[str, object]:
            seen.append(len(runner.calls))
            in_run.append(os.environ.get(REAL_HOME_ENV))
            return real_state(root)

        monkeypatch.setattr(cli.batch, "runner_state", spy)
        monkeypatch.setattr(cli, "REPO_ROOT", repo.root)
        monkeypatch.setattr(hs, "role_text", lambda root, arm: "ROLE")
        monkeypatch.setattr(
            cli.ablation,
            "resolve_control",
            lambda name, root: ablation.ControlFiles(name=name, files={}, context_bytes=0),
        )
        tasks = tmp_path / "tasks.json"
        tasks.write_text(json.dumps({"schema_version": 3, "tasks": [v3_task(repo)]}), "utf-8")
        args = cli._parser().parse_args(
            ["--tasks", str(tasks), "--repeats", "1", "--real-home", "--max-cells", "2"]
        )
        (tmp_path / "out").mkdir()
        report, _code = cli._run_live(args, loaded, tmp_path / "w", tmp_path / "out", version_aware)
        assert seen == [0]
        assert len(runner.calls) >= 2
        assert report["provenance"]["runner_commit"] == repo.fix_sha
        assert in_run == ["1"]
        assert report["real_home"] is True
        assert os.environ[REAL_HOME_ENV] == "0"
