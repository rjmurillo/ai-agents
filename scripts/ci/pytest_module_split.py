"""Split the CI pytest pool into legs that keep each test module whole (issue #6846).

`scripts/ci/run_pytest_partition.py` loads this as a pytest plugin on every
split leg. Each leg collects the whole pool, and this plugin keeps only the
modules that belong to the leg's group.

pytest-split's `least_duration` places single tests, so it spread the tests of
1835 of 1984 modules across the five legs (run 39886538175, 2026-10-23). Tests
that share a cached whole-repository scan then paid for that scan on every leg
they landed on: `tests/test_guard_diff.py` ran its 14s scan three times and
breached its slow-test budget.

This plugin balances whole modules instead. It takes the longest module first
and gives it to the least loaded leg, so the slowest modules still land on
different legs, the property issue #6828 needed. A module's cost is the sum of
its tests' recorded durations. A test with no recorded duration costs the mean
of the recorded ones, or one second when none are recorded.

pytest-split still records the durations: the legs keep `--store-durations`
and `--durations-path`, and this plugin reads the same `--durations-path`.
"""

from __future__ import annotations

import heapq
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar

import pytest

if TYPE_CHECKING:
    from _pytest.config import Config
    from _pytest.config.argparsing import Parser

SPLITS_OPTION = "--module-splits"
GROUP_OPTION = "--module-group"

_UNRECORDED_DEFAULT_SECONDS = 1.0


class HasNodeId(Protocol):
    """All the split reads from a collected item."""

    @property
    def nodeid(self) -> str: ...


ItemT = TypeVar("ItemT", bound=HasNodeId)


@dataclass(frozen=True)
class Leg(Generic[ItemT]):
    """One leg's share: the items it runs and deselects, and its estimated seconds."""

    selected: list[ItemT]
    deselected: list[ItemT]
    duration: float


def module_of(nodeid: str) -> str:
    """The test file a node ID belongs to: ``tests/a.py::T::t[x]`` is ``tests/a.py``."""
    return nodeid.split("::", 1)[0]


def module_costs(nodeids: Sequence[str], durations: Mapping[str, float]) -> dict[str, float]:
    """Estimated seconds per module, keyed in first-collected order."""
    recorded = [durations[nodeid] for nodeid in nodeids if nodeid in durations]
    default = sum(recorded) / len(recorded) if recorded else _UNRECORDED_DEFAULT_SECONDS
    costs: dict[str, float] = {}
    for nodeid in nodeids:
        module = module_of(nodeid)
        costs[module] = costs.get(module, 0.0) + durations.get(nodeid, default)
    return costs


def assign_modules(costs: Mapping[str, float], splits: int) -> dict[str, int]:
    """Each module's zero-based leg: longest first, onto the least loaded leg.

    Ties on cost keep collection order. Ties on load go to the leg holding
    fewer modules, then to the lower leg, so modules recorded at zero seconds
    still spread out, and every leg computes the same assignment.
    """
    if splits < 1:
        raise ValueError(f"splits must be at least 1, got {splits}")
    order = sorted(costs, key=lambda module: -costs[module])
    loads = [(0.0, 0, leg) for leg in range(splits)]
    homes: dict[str, int] = {}
    for module in order:
        load, count, leg = heapq.heappop(loads)
        homes[module] = leg
        heapq.heappush(loads, (load + costs[module], count + 1, leg))
    return homes


def split_by_module(
    splits: int, items: Sequence[ItemT], durations: Mapping[str, float]
) -> list[Leg[ItemT]]:
    """Every leg's share of ``items``, each module whole, each leg in collection order."""
    nodeids = [item.nodeid for item in items]
    costs = module_costs(nodeids, durations)
    homes = assign_modules(costs, splits)
    legs: list[Leg[ItemT]] = []
    for leg in range(splits):
        selected = [item for item in items if homes[module_of(item.nodeid)] == leg]
        deselected = [item for item in items if homes[module_of(item.nodeid)] != leg]
        cost = sum(costs[module] for module, home in homes.items() if home == leg)
        legs.append(Leg(selected, deselected, cost))
    return legs


def load_durations(path: Path) -> dict[str, float]:
    """The recorded durations at ``path``, or an empty map when the file is absent.

    Raises:
        pytest.UsageError: the file is not JSON, not a map of node IDs, or holds
            a duration that is not a number.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise pytest.UsageError(f"{path}: durations file is not JSON: {exc}") from exc
    # pytest-split wrote a list of pairs before it switched to a map; read both.
    if isinstance(data, list):
        try:
            data = dict(data)
        except (TypeError, ValueError) as exc:
            raise pytest.UsageError(f"{path}: durations list is not node ID pairs") from exc
    if not isinstance(data, dict):
        raise pytest.UsageError(f"{path}: durations file is not a map of node IDs")
    for nodeid, seconds in data.items():
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise pytest.UsageError(f"{path}: duration of {nodeid!r} is not a number")
    return data


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("module split", "Split the pool into legs of whole modules.")
    group.addoption(
        SPLITS_OPTION,
        dest="module_splits",
        type=int,
        help="How many legs to split the pool into, keeping each module whole.",
    )
    group.addoption(
        GROUP_OPTION,
        dest="module_group",
        type=int,
        help="Which leg this run collects, from 1.",
    )


def pytest_configure(config: Config) -> None:
    splits = config.getoption("module_splits")
    group = config.getoption("module_group")
    if splits is None and group is None:
        return
    if splits is None or group is None:
        raise pytest.UsageError(f"{SPLITS_OPTION} and {GROUP_OPTION} go together")
    if splits < 1:
        raise pytest.UsageError(f"{SPLITS_OPTION} must be at least 1, got {splits}")
    if not 1 <= group <= splits:
        raise pytest.UsageError(f"{GROUP_OPTION} must be from 1 to {splits}, got {group}")


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: Config, items: list[pytest.Item]) -> None:
    splits = config.getoption("module_splits")
    group = config.getoption("module_group")
    if splits is None or group is None:
        return
    durations = load_durations(Path(config.getoption("durations_path")))
    leg = split_by_module(splits, items, durations)[group - 1]
    items[:] = leg.selected
    config.hook.pytest_deselected(items=leg.deselected)
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(
            f"[module-split] leg {group}/{splits}: {len(leg.selected)} tests, "
            f"estimated {leg.duration:.1f}s"
        )
