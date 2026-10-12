"""Lane planning and running for the pre-push pytest partitions (issue #6198).

The planner turns the four partition commands into lanes that overlap while the
total xdist worker count stays inside the budget. The runner starts every lane
at once and stops the children when the caller is interrupted.
"""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.validation import pytest_lanes
from scripts.validation.pytest_lanes import Lane, PartitionReport

ROOT = Path("/repo")
PY = ["python", "-m", "pytest"]


def _bulk(workers: str) -> list[str]:
    return [*PY, "-m", "not integration", "-n", workers, "--dist", "loadfile", str(ROOT / "tests")]


def _mutation(workers: str) -> list[str]:
    return [*PY, "-m", "not integration", "-n", workers, "--dist", "loadfile", str(ROOT / "m")]


SAFE_PUSH = [*PY, "-m", "x", str(ROOT / "tests/test_safe_push_pr_branch.py"), str(ROOT / "s")]
PR_AUTOFIX = [*PY, "-m", "x", str(ROOT / "tests/test_pr_autofix_late_live_state_gate.py")]
FOUR = [_bulk("8"), _mutation("8"), SAFE_PUSH, PR_AUTOFIX]


def _workers(lane: Lane) -> int:
    command = lane.commands[0]
    return int(command[command.index("-n") + 1])


def test_four_partitions_become_two_pools_and_one_serial_lane() -> None:
    lanes = pytest_lanes.plan_lanes(FOUR, visible_cpus=48)

    assert lanes is not None
    assert len(lanes) == 3
    assert [_workers(lane) for lane in lanes[:2]] == [4, 4]
    assert lanes[2].commands == (tuple(SAFE_PUSH), tuple(PR_AUTOFIX))


def test_safe_push_and_pr_autofix_never_get_a_worker_pool() -> None:
    lanes = pytest_lanes.plan_lanes(FOUR, visible_cpus=48)

    assert lanes is not None
    for command in lanes[2].commands:
        assert "-n" not in command


def test_the_serial_lane_keeps_the_original_order() -> None:
    lanes = pytest_lanes.plan_lanes([PR_AUTOFIX, _bulk("4"), SAFE_PUSH, _mutation("4")], 48)

    assert lanes is not None
    assert lanes[-1].commands == (tuple(PR_AUTOFIX), tuple(SAFE_PUSH))


@pytest.mark.parametrize("total", range(2, 65))
def test_workers_across_pools_never_exceed_the_budget(total: int) -> None:
    lanes = pytest_lanes.plan_lanes([_bulk("auto"), _mutation("auto"), SAFE_PUSH], total)
    explicit = pytest_lanes.plan_lanes([_bulk(str(total)), _mutation(str(total))], visible_cpus=1)

    assert lanes is not None
    assert explicit is not None
    for planned in (lanes[:2], explicit):
        assert sum(_workers(lane) for lane in planned) == total
        assert all(_workers(lane) >= 1 for lane in planned)


def test_an_odd_budget_gives_the_extra_worker_to_the_earlier_pool() -> None:
    lanes = pytest_lanes.plan_lanes([_bulk("5"), _mutation("5")], visible_cpus=48)

    assert lanes is not None
    assert [_workers(lane) for lane in lanes] == [3, 2]


def test_auto_means_one_worker_per_visible_cpu() -> None:
    lanes = pytest_lanes.plan_lanes([_bulk("auto"), _mutation("auto")], visible_cpus=6)

    assert lanes is not None
    assert [_workers(lane) for lane in lanes] == [3, 3]


def test_planning_leaves_the_input_commands_unchanged() -> None:
    commands = [list(command) for command in FOUR]

    pytest_lanes.plan_lanes(commands, visible_cpus=48)

    assert commands == FOUR


@pytest.mark.parametrize(
    "commands",
    [
        pytest.param([_bulk("8")], id="single-command"),
        pytest.param([SAFE_PUSH, PR_AUTOFIX], id="only-serial"),
        pytest.param([], id="empty"),
        pytest.param([_bulk("1"), _mutation("1")], id="one-worker-cannot-feed-two-pools"),
        pytest.param([_bulk("0"), _mutation("0")], id="zero-workers"),
        pytest.param([_bulk("half"), _mutation("half")], id="unreadable-workers"),
        pytest.param([[*PY, "-n"], [*PY, "-n"]], id="trailing-n-flag"),
    ],
)
def test_commands_that_gain_nothing_from_overlap_stay_in_sequence(
    commands: list[list[str]],
) -> None:
    assert pytest_lanes.plan_lanes(commands, visible_cpus=48) is None


def test_one_pool_beside_a_serial_lane_still_overlaps() -> None:
    lanes = pytest_lanes.plan_lanes([_bulk("4"), SAFE_PUSH], visible_cpus=48)

    assert lanes is not None
    assert [_workers(lanes[0]), len(lanes)] == [4, 2]


def test_split_workers_shares_sum_to_the_total() -> None:
    assert pytest_lanes.split_workers(7, 3) == [3, 2, 2]
    assert pytest_lanes.split_workers(2, 2) == [1, 1]


@pytest.mark.parametrize(
    ("command", "label"),
    [
        (_bulk("4"), "tests"),
        (_mutation("4"), "m"),
        (SAFE_PUSH, "tests/test_safe_push_pr_branch.py (+1 more)"),
        (PR_AUTOFIX, "tests/test_pr_autofix_late_live_state_gate.py"),
        ([*PY, "--testmon", "--testmon-forceselect", "-m", "x", str(ROOT / "t")], "t"),
        ([*PY, "-m", "x", "/elsewhere/t"], "/elsewhere/t"),
        ([*PY, "-m", "x"], "pytest"),
        (["tool", "arg"], "arg"),
    ],
)
def test_a_partition_is_named_by_its_first_test_target(command: list[str], label: str) -> None:
    assert pytest_lanes.partition_label(command, ROOT) == label


def _done(command: Sequence[str], code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, code, "", "")


def test_run_lane_runs_commands_in_order_within_the_deadline() -> None:
    seen: list[tuple[str, ...]] = []

    def run(command: Sequence[str], remaining: float) -> subprocess.CompletedProcess[str]:
        seen.append(tuple(command))
        assert 0 < remaining <= 100
        return _done(command)

    lane = Lane(commands=(tuple(SAFE_PUSH), tuple(PR_AUTOFIX)))
    reports = pytest_lanes.run_lane(lane, ROOT, time.monotonic() + 100, run, threading.Event())

    assert seen == [tuple(SAFE_PUSH), tuple(PR_AUTOFIX)]
    assert [report.label for report in reports] == [
        "tests/test_safe_push_pr_branch.py (+1 more)",
        "tests/test_pr_autofix_late_live_state_gate.py",
    ]
    assert all(report.result is not None and report.seconds >= 0 for report in reports)


def test_run_lane_reports_a_command_it_had_no_time_to_start() -> None:
    def run(command: Sequence[str], remaining: float) -> subprocess.CompletedProcess[str]:
        pytest.fail("a spent deadline must not start a command")

    lane = Lane(commands=(tuple(SAFE_PUSH),))
    reports = pytest_lanes.run_lane(lane, ROOT, time.monotonic() - 1, run, threading.Event())

    assert [(report.label, report.result) for report in reports] == [
        ("tests/test_safe_push_pr_branch.py (+1 more)", None)
    ]


def _lane(name: str) -> Lane:
    return Lane(commands=((*PY, str(ROOT / name)),))


def test_run_lanes_starts_every_lane_before_any_finishes() -> None:
    barrier = threading.Barrier(3, timeout=10)

    def run_one(lane: Lane, _cancel: threading.Event) -> list[PartitionReport]:
        barrier.wait()  # raises BrokenBarrierError unless all three lanes run at once
        return [PartitionReport(lane.commands[0][-1], _done(lane.commands[0]), 0.0)]

    done: list[list[PartitionReport]] = []
    reports = pytest_lanes.run_lanes(
        [_lane("a"), _lane("b"), _lane("c")], run_one, done.append, lambda: None
    )

    assert [report.label for report in reports] == ["/repo/a", "/repo/b", "/repo/c"]
    assert len(done) == 3


def test_run_lanes_hands_each_finished_lane_to_the_calling_thread() -> None:
    threads: set[int] = set()

    def run_one(lane: Lane, _cancel: threading.Event) -> list[PartitionReport]:
        return [PartitionReport("x", None, 0.0)]

    pytest_lanes.run_lanes(
        [_lane("a"), _lane("b")],
        run_one,
        lambda _reports: threads.add(threading.get_ident()),
        lambda: None,
    )

    assert threads == {threading.get_ident()}


def test_run_lanes_stops_every_child_when_interrupted_then_reraises() -> None:
    release = threading.Event()
    stopped: list[bool] = []

    def run_one(lane: Lane, _cancel: threading.Event) -> list[PartitionReport]:
        if lane.commands[0][-1].endswith("slow"):
            release.wait(timeout=10)
            return [PartitionReport("slow", None, 0.0)]
        return [PartitionReport("fast", None, 0.0)]

    def on_done(_reports: list[PartitionReport]) -> None:
        raise KeyboardInterrupt

    def stop_all() -> None:
        stopped.append(True)
        release.set()

    with pytest.raises(KeyboardInterrupt):
        pytest_lanes.run_lanes([_lane("fast"), _lane("slow")], run_one, on_done, stop_all)

    assert stopped == [True]


def test_run_lane_starts_nothing_once_cancelled() -> None:
    cancel = threading.Event()
    seen: list[Sequence[str]] = []

    def run(command: Sequence[str], remaining: float) -> subprocess.CompletedProcess[str]:
        seen.append(command)
        cancel.set()  # an interrupt lands while the first command runs
        return _done(command)

    lane = Lane(commands=(tuple(SAFE_PUSH), tuple(PR_AUTOFIX)))
    reports = pytest_lanes.run_lane(lane, ROOT, time.monotonic() + 100, run, cancel)

    assert seen == [tuple(SAFE_PUSH)]
    assert [report.result is None for report in reports] == [False, True]


def test_run_lanes_sets_cancel_before_stopping_children() -> None:
    order: list[str] = []
    captured: list[threading.Event] = []

    def run_one(lane: Lane, cancel: threading.Event) -> list[PartitionReport]:
        captured.append(cancel)
        return [PartitionReport("x", None, 0.0)]

    def on_done(_reports: list[PartitionReport]) -> None:
        raise KeyboardInterrupt

    def stop_all() -> None:
        order.append("set" if captured[0].is_set() else "unset")

    with pytest.raises(KeyboardInterrupt):
        pytest_lanes.run_lanes([_lane("a")], run_one, on_done, stop_all)

    assert order == ["set"]
