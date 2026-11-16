"""Regression tests for the review threads on PR 7385 (issue #7350).

Each class pins one thread. They fail on commit 29f04b444 and pass after the fix.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.eval._control_ablation_history_support import HistoryRepo, make_history_repo
from tests.eval.test_handoff_strategy import FakeRunner, corpus, v3_task
from tests.eval.test_handoff_strategy_transient import FlakyRunner

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _control_ablation as ablation  # noqa: E402
import _control_ablation_tasks as ablation_tasks  # noqa: E402
import _handoff_strategy as hs  # noqa: E402
import eval_handoff_strategy as cli  # noqa: E402
from _runtime_harness import REAL_HOME_ENV  # noqa: E402


@pytest.fixture
def repo(tmp_path: Path) -> HistoryRepo:
    return make_history_repo(tmp_path / "history")


def live(
    repo: HistoryRepo,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: Any,
    *extra: str,
) -> tuple[dict[str, Any], int]:
    """Drive `_run_live` against the fixture repository with a fake CLI."""
    loaded = corpus(repo)
    monkeypatch.setattr(cli, "REPO_ROOT", repo.root)
    monkeypatch.setattr(hs, "role_text", lambda root, arm: "ROLE")
    monkeypatch.setattr(
        cli.ablation,
        "resolve_control",
        lambda name, root: ablation.ControlFiles(name=name, files={}, context_bytes=0),
    )

    def with_version(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="2.3.1\n", stderr="")
        return runner(argv, **kwargs)

    tasks = tmp_path / "tasks.json"
    tasks.write_text(json.dumps({"schema_version": 3, "tasks": [v3_task(repo)]}), "utf-8")
    args = cli._parser().parse_args(
        ["--tasks", str(tasks), "--repeats", "1", "--real-home", "--max-cells", "2", *extra]
    )
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    return cli._run_live(args, loaded, tmp_path / "w", out, with_version)


class TestSpendCapFailsClosed:
    """Cursor: a failing launch's own unmeasured cost must not be hidden by earlier spend."""

    def test_a_failure_after_a_paid_launch_still_blocks_later_cells(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(REAL_HOME_ENV, "1")
        runner = FlakyRunner(corpus(repo).tasks[0], fail_calls={2}, stdout="")
        report, _code = live(repo, tmp_path, monkeypatch, runner, "--max-cost-usd", "10")
        # Call 1 (investigator) cost $0.01. Call 2 (producer) died with no reported cost.
        assert report["spend_unmeasured"] is True
        reasons = [f["reason"] for f in report["failures"]]
        assert len(reasons) == 2
        assert reasons[1].startswith("spend cap")
        assert len(runner.calls) == 2  # the second cell never launched

    def test_the_paid_launch_is_still_counted_as_spend(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(REAL_HOME_ENV, "1")
        runner = FlakyRunner(corpus(repo).tasks[0], fail_calls={2}, stdout="")
        report, _code = live(repo, tmp_path, monkeypatch, runner, "--max-cost-usd", "10")
        assert report["spent_usd"] == pytest.approx(0.01)

    def test_a_transient_failure_after_a_paid_launch_stays_measured(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tests.eval.test_handoff_strategy_transient import RATE_LIMITED

        monkeypatch.setenv(REAL_HOME_ENV, "1")
        monkeypatch.setattr(hs, "TRANSIENT_WAITS", (0.0, 0.0, 0.0))
        every_later_call = set(range(2, 40))
        runner = FlakyRunner(
            corpus(repo).tasks[0], fail_calls=every_later_call, stdout=RATE_LIMITED
        )
        report, _code = live(repo, tmp_path, monkeypatch, runner, "--max-cost-usd", "10")
        assert report["spend_unmeasured"] is False
        assert report["spent_usd"] == pytest.approx(0.01)  # only the first investigator ran


class TestResumeRefusesRecordedCells:
    """Devin: a rerun into an output directory must not relaunch a recorded cell."""

    def test_a_recorded_cell_blocks_the_batch_before_any_launch(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(REAL_HOME_ENV, "1")
        out = tmp_path / "out"
        out.mkdir()
        recorded = json.dumps({"task_id": "half-odd", "repeat": 0})
        (out / f"records-{hs.ARM_CONTINUE}.jsonl").write_text(recorded + "\n", encoding="utf-8")

        def no_launch(*args: object, **kwargs: object) -> None:
            pytest.fail("a launch happened")

        with pytest.raises(ablation_tasks.ControlAblationConfigError, match="already records"):
            live(repo, tmp_path, monkeypatch, no_launch)

    def test_a_different_repeat_is_not_blocked(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(REAL_HOME_ENV, "1")
        out = tmp_path / "out"
        out.mkdir()
        recorded = json.dumps({"task_id": "half-odd", "repeat": 2})
        (out / f"records-{hs.ARM_CONTINUE}.jsonl").write_text(recorded + "\n", encoding="utf-8")
        runner = FakeRunner(corpus(repo).tasks[0])
        report, _code = live(repo, tmp_path, monkeypatch, runner)
        assert len(report["entries"]) == 2


class TestRepairedCellsAreNotFirstPass:
    """Devin: a repaired cell's outcome record must carry its repairs and its first attempt."""

    def _record(
        self,
        repo: HistoryRepo,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fix_on_round: int | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        monkeypatch.setenv(REAL_HOME_ENV, "1")
        loaded = corpus(repo)
        task = loaded.tasks[0]
        entry, record, _patch, _cell = cli.run_cell(
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
            runner=FakeRunner(task, fix_on_round=fix_on_round),
            markers=(),
        )
        return entry, record

    def test_a_fix_on_the_second_round_is_one_retry_and_not_first_pass(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry, record = self._record(repo, tmp_path, monkeypatch, fix_on_round=1)
        assert record["execution"]["deterministic_acceptance"] == "PASS"
        assert record["execution"]["retries"] == 1
        assert record["execution"]["first_pass"] == "FAIL"
        assert record["config"]["retry_budget"] == hs.REPAIR_ROUNDS
        assert entry["first_attempt_exit"] != 0

    def test_a_first_attempt_fix_is_first_pass_with_no_retry(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry, record = self._record(repo, tmp_path, monkeypatch, fix_on_round=0)
        assert record["execution"]["retries"] == 0
        assert record["execution"]["first_pass"] == "PASS"
        assert record["config"]["retry_budget"] == hs.REPAIR_ROUNDS
        assert entry["first_attempt_exit"] == 0

    def test_a_cell_never_fixed_spends_its_budget_and_is_not_first_pass(
        self, repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _entry, record = self._record(repo, tmp_path, monkeypatch, fix_on_round=None)
        assert record["execution"]["retries"] == hs.REPAIR_ROUNDS
        assert record["execution"]["first_pass"] == "FAIL"
        assert record["execution"]["deterministic_acceptance"] == "FAIL"


def report_dir(
    path: Path,
    entries: list[dict[str, Any]],
    *,
    tasks_sha: str = "a" * 64,
    model: str = "claude-sonnet-5-5",
    effort: str = "medium",
) -> Path:
    path.mkdir(parents=True)
    report = {
        "entries": entries,
        "effort": effort,
        "provenance": {"tasks_file_sha256": tasks_sha, "model_requested": model},
    }
    (path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return path


def cell(task: str, arm: str, repeat: int, accepted: bool = True) -> dict[str, Any]:
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


TASKS = {
    "tasks": [
        {"id": "s1", "stall": True},
        {"id": "s2", "stall": True},
        {"id": "n", "stall": False},
    ]
}
GRID = [(t, a, r) for t in ("s1", "s2", "n") for r in range(3) for a in hs.ARMS]


class TestCombineChecksTheGrid:
    """Devin: a wrong cell in a full count must not stand in for a missing one."""

    def test_an_unexpected_cell_cannot_replace_a_missing_one(self, tmp_path: Path) -> None:
        # Devin's example: drop a control-arm cell, add a 4th repeat of the treatment arm.
        kept = [c for c in GRID if c != ("s2", hs.ARM_CONTINUE, 2)]
        entries = [cell(t, a, r, accepted=(a == hs.ARM_HANDOFF)) for t, a, r in kept]
        entries.append(cell("s2", hs.ARM_HANDOFF, 3))
        assert len(entries) == 18  # the count is complete, the grid is not
        batch = report_dir(tmp_path / "a", entries)
        with pytest.raises(ablation_tasks.ControlAblationConfigError, match="unexpected"):
            hs.combine([batch], TASKS)

    def test_an_unknown_task_or_arm_is_unexpected(self, tmp_path: Path) -> None:
        entries = [cell(*c) for c in GRID[:-1]] + [cell("ghost", hs.ARM_CONTINUE, 0)]
        batch = report_dir(tmp_path / "a", entries)
        with pytest.raises(ablation_tasks.ControlAblationConfigError, match="unexpected"):
            hs.combine([batch], TASKS)

    def test_decide_is_inconclusive_when_the_keys_differ_at_full_count(self) -> None:
        kept = [c for c in GRID if c != ("s2", hs.ARM_CONTINUE, 2)]
        entries = [cell(t, a, r, accepted=(a == hs.ARM_HANDOFF)) for t, a, r in kept]
        entries.append(cell("s2", hs.ARM_HANDOFF, 3))
        expected = set(GRID)
        out = hs.decide(entries, {"s1", "s2"}, {"n"}, 18, expected_keys=expected)
        assert out["outcome"] == "INCONCLUSIVE"
        assert out["routing"] == "retain incumbent"
        assert any("missing 1" in r and "unexpected 1" in r for r in out["reasons"])

    def test_the_old_count_only_check_would_have_supported_the_change(self) -> None:
        kept = [c for c in GRID if c != ("s2", hs.ARM_CONTINUE, 2)]
        entries = [cell(t, a, r, accepted=(a == hs.ARM_HANDOFF)) for t, a, r in kept]
        entries.append(cell("s2", hs.ARM_HANDOFF, 3))
        out = hs.decide(entries, {"s1", "s2"}, {"n"}, 18)
        assert out["outcome"] == "SUPPORTED_NARROW"  # why the key check is needed

    def test_a_complete_grid_across_two_batches_still_decides(self, tmp_path: Path) -> None:
        first = report_dir(tmp_path / "a", [cell(*c) for c in GRID[:10]])
        second = report_dir(tmp_path / "b", [cell(*c) for c in GRID[10:]])
        result = hs.combine([first, second], TASKS)
        assert result["cells"] == result["expected_cells"] == 18
        assert result["missing_cells"] == []
        assert result["decision"]["outcome"] == "INCONCLUSIVE"

    def test_missing_cells_are_listed_and_the_result_is_inconclusive(self, tmp_path: Path) -> None:
        only = report_dir(tmp_path / "a", [cell(*c) for c in GRID[:-2]])
        result = hs.combine([only], TASKS)
        assert result["missing_cells"] == [list(c) for c in sorted(GRID[-2:])]
        assert result["decision"]["outcome"] == "INCONCLUSIVE"


class TestCombineChecksProvenance:
    """Devin: batches compared as one experiment must share task file, model, and effort."""

    def _two(self, tmp_path: Path, **second: Any) -> list[Path]:
        first = report_dir(tmp_path / "a", [cell(*c) for c in GRID[:10]])
        rest = report_dir(tmp_path / "b", [cell(*c) for c in GRID[10:]], **second)
        return [first, rest]

    def test_a_different_task_file_hash_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ablation_tasks.ControlAblationConfigError, match="tasks_file_sha256"):
            hs.combine(self._two(tmp_path, tasks_sha="b" * 64), TASKS)

    def test_a_different_model_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ablation_tasks.ControlAblationConfigError, match="model_requested"):
            hs.combine(self._two(tmp_path, model="claude-opus-5-5"), TASKS)

    def test_a_different_effort_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ablation_tasks.ControlAblationConfigError, match="effort"):
            hs.combine(self._two(tmp_path, effort="high"), TASKS)

    def test_the_task_file_on_disk_must_match_the_reports(self, tmp_path: Path) -> None:
        batches = self._two(tmp_path)
        tasks = tmp_path / "tasks.json"
        tasks.write_text(json.dumps(TASKS), encoding="utf-8")
        with pytest.raises(ablation_tasks.ControlAblationConfigError, match="task file"):
            hs.combine_files(batches, tasks, None)
