"""Plan and run the pre-push pytest partitions at the same time (issue #6198).

`git_hook_policy.run_pytest` used to run its partition commands one after
another, so the step cost the sum of the partitions. This module groups them
into lanes that overlap. Two rules shape the grouping:

* The xdist partitions (bulk, mutation) each get their own lane and split one
  worker budget, so the workers across lanes never exceed what the sequential
  run would have used.
* The commands that carry no ``-n`` flag (safe-push and pr-autofix) share one
  lane and run in order inside it. They are the process-sensitive modules, and
  they never share a pool with another partition.

The planner and the runner here take their process boundary as arguments, so the
unit tests need no subprocess. `git_hook_policy` supplies `_run_command`.
"""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

_WORKERS_FLAG = "-n"
_WORKERS_AUTO = "auto"
# Flags that consume the next argv token, so the token is not a test target.
_VALUE_FLAGS = frozenset({"-m", "-n", "--dist", "--ignore"})


@dataclass(frozen=True)
class Lane:
    """Commands that run in order, beside the other lanes."""

    commands: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class PartitionReport:
    """What one partition did: its result, or ``None`` when it never started."""

    label: str
    result: subprocess.CompletedProcess[str] | None
    seconds: float


def _is_xdist(command: Sequence[str]) -> bool:
    return _WORKERS_FLAG in command


def _workers_total(command: Sequence[str], visible_cpus: int) -> int | None:
    """Return the ``-n`` value as an integer, or ``None`` when it is not one.

    ``auto`` means one worker per visible CPU, the same meaning xdist gives it.
    """
    value_index = command.index(_WORKERS_FLAG) + 1
    if value_index >= len(command):
        return None
    raw = command[value_index]
    if raw == _WORKERS_AUTO:
        return visible_cpus
    return int(raw) if raw.isdecimal() and int(raw) > 0 else None


def _with_workers(command: Sequence[str], workers: int) -> tuple[str, ...]:
    """Return ``command`` with the ``-n`` value replaced by ``workers``."""
    index = command.index(_WORKERS_FLAG) + 1
    return (*command[:index], str(workers), *command[index + 1 :])


def split_workers(total: int, lane_count: int) -> list[int]:
    """Split ``total`` workers across ``lane_count`` lanes, earlier lanes first.

    The shares sum to ``total``. Callers check ``total >= lane_count`` first;
    a share of zero would be an invalid ``-n`` value.
    """
    base, extra = divmod(total, lane_count)
    return [base + (1 if index < extra else 0) for index in range(lane_count)]


def plan_lanes(commands: Sequence[Sequence[str]], visible_cpus: int) -> list[Lane] | None:
    """Group ``commands`` into lanes that can overlap, or ``None`` to stay serial.

    ``None`` means overlap gains nothing or would break the worker budget:
    fewer than two lanes, an unreadable ``-n`` value, or fewer workers than
    xdist lanes (a one-worker budget cannot feed two pools).
    """
    xdist = [tuple(command) for command in commands if _is_xdist(command)]
    serial = tuple(tuple(command) for command in commands if not _is_xdist(command))
    lane_count = len(xdist) + (1 if serial else 0)
    if lane_count < 2 or not xdist:
        return None
    total = _workers_total(xdist[0], visible_cpus)
    if total is None or total < len(xdist):
        return None
    shares = split_workers(total, len(xdist))
    lanes = [
        Lane(commands=(_with_workers(command, share),))
        for command, share in zip(xdist, shares, strict=True)
    ]
    if serial:
        lanes.append(Lane(commands=serial))
    return lanes


def partition_label(command: Sequence[str], repo_root: Path) -> str:
    """Name a partition by its first test target, so a failure points at it."""
    targets: list[str] = []
    skip = False
    tokens = list(command)
    start = tokens.index("pytest") + 1 if "pytest" in tokens else 1
    for token in tokens[start:]:
        if skip:
            skip = False
        elif token in _VALUE_FLAGS:
            skip = True
        elif not token.startswith("-"):
            targets.append(token)
    if not targets:
        return "pytest"
    first = Path(targets[0])
    try:
        name = first.relative_to(repo_root).as_posix()
    except ValueError:
        name = first.as_posix()
    return name if len(targets) == 1 else f"{name} (+{len(targets) - 1} more)"


def run_lane(
    lane: Lane,
    repo_root: Path,
    deadline: float,
    run_command: Callable[[Sequence[str], float], subprocess.CompletedProcess[str]],
    cancel: threading.Event,
) -> list[PartitionReport]:
    """Run one lane's commands in order against the shared ``deadline``.

    A command that would start with no time left, or after ``cancel`` is set,
    is reported as not started, so the report names every partition the budget
    or the interrupt cost the step.
    """
    reports: list[PartitionReport] = []
    for command in lane.commands:
        label = partition_label(command, repo_root)
        remaining = deadline - time.monotonic()
        if remaining <= 0 or cancel.is_set():
            reports.append(PartitionReport(label, None, 0.0))
            continue
        started = time.monotonic()
        result = run_command(command, remaining)
        reports.append(PartitionReport(label, result, time.monotonic() - started))
    return reports


def run_lanes(
    lanes: Sequence[Lane],
    run_one: Callable[[Lane, threading.Event], list[PartitionReport]],
    on_done: Callable[[list[PartitionReport]], None],
    stop_all: Callable[[], None],
) -> list[PartitionReport]:
    """Run every lane at once and return the reports in lane order.

    ``on_done`` runs on the calling thread as each lane finishes, so partition
    output prints whole instead of interleaved. If the calling thread is
    interrupted, the shared ``cancel`` event is set first, so a lane that has
    more commands queued starts none of them, and then ``stop_all`` ends every
    running child before the interrupt propagates. The children run in their
    own sessions and would otherwise outlive the hook until the deadline.
    """
    cancel = threading.Event()
    with ThreadPoolExecutor(max_workers=len(lanes)) as pool:
        futures: list[Future[list[PartitionReport]]] = []
        try:
            futures.extend(pool.submit(run_one, lane, cancel) for lane in lanes)
            for future in as_completed(futures):
                on_done(future.result())
        except BaseException:
            cancel.set()
            stop_all()
            raise
    return [report for future in futures for report in future.result()]
