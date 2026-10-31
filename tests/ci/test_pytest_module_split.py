"""Unit tests for the whole-module split plugin (issue #6846).

The end-to-end checks live beside the pool: test_pytest_split_pool.py proves the
real groups cover the pool once with no module on two legs, and
test_pytest_split_hostile_durations.py feeds the plugin hostile timings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from _pytest.config import Config

from scripts.ci import pytest_module_split as split


class _Item:
    """The one attribute the split reads from a collected item."""

    def __init__(self, nodeid: str) -> None:
        self.nodeid = nodeid

    def __repr__(self) -> str:
        return self.nodeid


class _Config:
    """The option lookups ``pytest_configure`` makes."""

    def __init__(self, splits: int | None, group: int | None) -> None:
        self._options = {"module_splits": splits, "module_group": group}

    def getoption(self, name: str) -> int | None:
        return self._options[name]


def _configure(splits: int | None, group: int | None) -> None:
    split.pytest_configure(cast("Config", _Config(splits, group)))


def _items(*nodeids: str) -> list[_Item]:
    return [_Item(nodeid) for nodeid in nodeids]


@pytest.mark.parametrize(
    ("nodeid", "module"),
    [
        ("tests/a.py::test_x", "tests/a.py"),
        ("tests/a.py::TestA::test_x[p::q]", "tests/a.py"),
        ("tests/a.py", "tests/a.py"),
    ],
)
def test_module_of_takes_the_file_part_of_a_node_id(nodeid: str, module: str) -> None:
    assert split.module_of(nodeid) == module


def test_module_costs_sum_each_modules_recorded_durations() -> None:
    nodeids = ["tests/a.py::x", "tests/a.py::y", "tests/b.py::z"]
    durations = {"tests/a.py::x": 3.0, "tests/a.py::y": 4.0, "tests/b.py::z": 2.0}

    assert split.module_costs(nodeids, durations) == {"tests/a.py": 7.0, "tests/b.py": 2.0}


def test_module_costs_charge_an_unrecorded_test_the_recorded_mean() -> None:
    nodeids = ["tests/a.py::x", "tests/b.py::y", "tests/b.py::new"]
    durations = {"tests/a.py::x": 2.0, "tests/b.py::y": 4.0, "tests/gone.py::z": 100.0}

    costs = split.module_costs(nodeids, durations)

    assert costs == {"tests/a.py": 2.0, "tests/b.py": 7.0}, "the mean ignores tests not collected"


def test_module_costs_count_tests_when_nothing_is_recorded() -> None:
    nodeids = ["tests/a.py::x", "tests/a.py::y", "tests/b.py::z"]

    assert split.module_costs(nodeids, {}) == {"tests/a.py": 2.0, "tests/b.py": 1.0}


def test_module_costs_keep_first_collected_order() -> None:
    nodeids = ["tests/z.py::a", "tests/a.py::b", "tests/z.py::c"]

    assert list(split.module_costs(nodeids, {})) == ["tests/z.py", "tests/a.py"]


def test_assign_modules_puts_the_longest_modules_on_different_legs() -> None:
    costs = {"tests/a.py": 180.0, "tests/b.py": 116.0, "tests/c.py": 71.0, "tests/d.py": 5.0}

    homes = split.assign_modules(costs, 3)

    assert len({homes["tests/a.py"], homes["tests/b.py"], homes["tests/c.py"]}) == 3
    assert homes["tests/d.py"] == homes["tests/c.py"], "the small module joins the lightest leg"


def test_assign_modules_breaks_ties_by_collection_order_and_lower_leg() -> None:
    costs = {"tests/a.py": 1.0, "tests/b.py": 1.0, "tests/c.py": 1.0}

    assert split.assign_modules(costs, 2) == {"tests/a.py": 0, "tests/b.py": 1, "tests/c.py": 0}


def test_assign_modules_with_more_legs_than_modules_leaves_legs_empty() -> None:
    homes = split.assign_modules({"tests/a.py": 1.0}, 3)

    assert homes == {"tests/a.py": 0}


def test_assign_modules_spreads_modules_recorded_at_zero_seconds() -> None:
    costs = {"tests/big.py": 1e9, **{f"tests/z{i}.py": 0.0 for i in range(8)}}

    homes = split.assign_modules(costs, 5)

    assert set(homes.values()) == {0, 1, 2, 3, 4}, "no leg may be left empty"


def test_assign_modules_rejects_fewer_than_one_leg() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        split.assign_modules({"tests/a.py": 1.0}, 0)


def test_split_by_module_covers_every_item_once_and_keeps_modules_whole() -> None:
    items = _items(
        "tests/a.py::1",
        "tests/b.py::1",
        "tests/a.py::2",
        "tests/c.py::1",
        "tests/b.py::2",
        "tests/d.py::1",
    )
    durations = {"tests/a.py::1": 10.0, "tests/a.py::2": 10.0, "tests/b.py::1": 6.0}

    legs = split.split_by_module(3, items, durations)

    selected = [item for leg in legs for item in leg.selected]
    assert sorted(map(repr, selected)) == sorted(map(repr, items))
    assert len(selected) == len(items)
    for leg in legs:
        modules = {split.module_of(item.nodeid) for item in leg.selected}
        for other in legs:
            if other is not leg:
                assert not modules & {split.module_of(i.nodeid) for i in other.selected}
        assert sorted(map(repr, leg.selected + leg.deselected)) == sorted(map(repr, items))


def test_split_by_module_keeps_collection_order_between_equal_modules() -> None:
    items = _items("tests/a.py::1", "tests/b.py::1", "tests/a.py::2", "tests/b.py::2")

    (only,) = split.split_by_module(1, items, {})

    assert only.selected == items
    assert only.deselected == []


def test_split_by_module_runs_the_longest_module_first() -> None:
    """Issue #6846: a 209s test collected late started 270s in and set the leg's tail."""
    items = _items(
        "tests/a.py::1", "tests/a.py::2", "tests/b.py::1", "tests/long.py::1", "tests/long.py::2"
    )
    durations = {"tests/long.py::1": 200.0, "tests/long.py::2": 9.0, "tests/b.py::1": 5.0}
    durations |= {"tests/a.py::1": 1.0, "tests/a.py::2": 1.0}

    (only,) = split.split_by_module(1, items, durations)

    assert [item.nodeid for item in only.selected] == [
        "tests/long.py::1",
        "tests/long.py::2",
        "tests/b.py::1",
        "tests/a.py::1",
        "tests/a.py::2",
    ]


def test_split_by_module_reports_each_legs_estimated_seconds() -> None:
    items = _items("tests/a.py::1", "tests/b.py::1")
    durations = {"tests/a.py::1": 5.0, "tests/b.py::1": 3.0}

    legs = split.split_by_module(2, items, durations)

    assert [leg.duration for leg in legs] == [5.0, 3.0]


def test_split_by_module_of_no_items_gives_empty_legs() -> None:
    legs = split.split_by_module(2, list[_Item](), {})

    assert [(leg.selected, leg.deselected, leg.duration) for leg in legs] == [
        ([], [], 0.0),
        ([], [], 0.0),
    ]


def test_load_durations_reads_a_map(tmp_path: Path) -> None:
    path = tmp_path / "durations.json"
    path.write_text(json.dumps({"tests/a.py::x": 1.5}), encoding="utf-8")

    assert split.load_durations(path) == {"tests/a.py::x": 1.5}


def test_load_durations_of_a_missing_file_is_empty(tmp_path: Path) -> None:
    assert split.load_durations(tmp_path / "absent.json") == {}


def test_load_durations_reads_the_old_list_of_pairs(tmp_path: Path) -> None:
    path = tmp_path / "durations.json"
    path.write_text(json.dumps([["tests/a.py::x", 2.0]]), encoding="utf-8")

    assert split.load_durations(path) == {"tests/a.py::x": 2.0}


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{", "not JSON"),
        ("42", "not a map"),
        ('"text"', "not a map"),
        ("[1, 2]", "not node ID pairs"),
        ('{"tests/a.py::x": null}', "not a number"),
        ('{"tests/a.py::x": "1.5"}', "not a number"),
        ('{"tests/a.py::x": true}', "not a number"),
    ],
)
def test_load_durations_refuses_a_malformed_file(
    tmp_path: Path, content: str, message: str
) -> None:
    path = tmp_path / "durations.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(pytest.UsageError, match=message):
        split.load_durations(path)


def test_load_durations_refuses_a_file_that_is_not_utf8(tmp_path: Path) -> None:
    path = tmp_path / "durations.json"
    path.write_bytes(b'{"tests/a.py::x": 1.0, "\xff": 2.0}')

    with pytest.raises(pytest.UsageError, match="cannot read"):
        split.load_durations(path)


def test_load_durations_refuses_a_path_it_cannot_read(tmp_path: Path) -> None:
    with pytest.raises(pytest.UsageError, match="cannot read"):
        split.load_durations(tmp_path)


def test_configure_accepts_no_split_options() -> None:
    _configure(None, None)


def test_configure_accepts_a_group_within_the_splits() -> None:
    _configure(5, 5)


@pytest.mark.parametrize(
    ("splits", "group", "message"),
    [
        (5, None, "go together"),
        (None, 1, "go together"),
        (0, 1, "at least 1"),
        (5, 0, "from 1 to 5"),
        (5, 6, "from 1 to 5"),
    ],
)
def test_configure_refuses_a_bad_split_request(
    splits: int | None, group: int | None, message: str
) -> None:
    with pytest.raises(pytest.UsageError, match=message):
        _configure(splits, group)
