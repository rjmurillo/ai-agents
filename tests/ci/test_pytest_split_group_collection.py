"""collect_groups collects the pool once and derives the split groups (issue #6892).

The pool test timed out at 300s on a loaded CI runner because it ran one full
`pytest --collect-only` per group. These tests replace the child process with a
counting fake, so they pin the number of collections without paying for one.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from scripts.ci import run_pytest_partition as runner
from tests.ci import pytest_split_group_collection as group_collection


def _pool(modules: int, tests_per_module: int) -> list[str]:
    return [
        f"tests/mod_{module:02d}.py::test_{test}"
        for module in range(modules)
        for test in range(tests_per_module)
    ]


class _FakeCollect:
    """Stands in for the child-process collection and records each call."""

    def __init__(self, pool: list[str]) -> None:
        self.pool = pool
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> list[str]:
        self.calls.append(args)
        return list(self.pool)


@pytest.fixture
def fake_collect(monkeypatch: pytest.MonkeyPatch) -> _FakeCollect:
    fake = _FakeCollect(_pool(modules=23, tests_per_module=4))
    monkeypatch.setattr(group_collection, "collect", fake)
    return fake


def test_collects_the_pool_once_whatever_the_group_count(
    fake_collect: _FakeCollect, tmp_path: Path
) -> None:
    group_collection.collect_groups(tmp_path / "durations.json")
    assert fake_collect.calls == [group_collection.pool_args()]


def test_every_split_group_is_returned_beside_the_pool(
    fake_collect: _FakeCollect, tmp_path: Path
) -> None:
    collected = group_collection.collect_groups(tmp_path / "durations.json")
    assert list(collected) == ["pool", *runner.split_names()]
    assert collected["pool"] == fake_collect.pool


def test_the_groups_cover_the_pool_exactly_once(fake_collect: _FakeCollect, tmp_path: Path) -> None:
    collected = group_collection.collect_groups(tmp_path / "durations.json")
    union = [node_id for name in runner.split_names() for node_id in collected[name]]
    assert Counter(union) == Counter(fake_collect.pool)


def test_no_module_spans_two_groups(fake_collect: _FakeCollect, tmp_path: Path) -> None:
    collected = group_collection.collect_groups(tmp_path / "durations.json")
    homes: dict[str, set[str]] = {}
    for name in runner.split_names():
        for node_id in collected[name]:
            homes.setdefault(node_id.split("::", 1)[0], set()).add(name)
    assert {module for module, groups in homes.items() if len(groups) > 1} == set()


def test_the_fixture_map_times_two_thirds_of_the_pool(
    fake_collect: _FakeCollect, tmp_path: Path
) -> None:
    path = tmp_path / "durations.json"
    group_collection.collect_groups(path)
    recorded = json.loads(path.read_text(encoding="utf-8"))
    assert set(recorded) < set(fake_collect.pool)
    assert len(recorded) == sum(1 for index in range(len(fake_collect.pool)) if index % 3)


def test_a_single_module_pool_fills_one_group_and_leaves_the_rest_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeCollect(_pool(modules=1, tests_per_module=6))
    monkeypatch.setattr(group_collection, "collect", fake)
    collected = group_collection.collect_groups(tmp_path / "durations.json")
    sizes = sorted(len(collected[name]) for name in runner.split_names())
    assert sizes == [0, 0, 0, 0, 6]


def test_an_empty_pool_gives_empty_groups(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(group_collection, "collect", _FakeCollect([]))
    collected = group_collection.collect_groups(tmp_path / "durations.json")
    assert collected == {"pool": [], **{name: [] for name in runner.split_names()}}


def test_a_collection_failure_propagates_instead_of_yielding_empty_groups(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def failing(args: list[str]) -> list[str]:
        raise AssertionError("collection failed")

    monkeypatch.setattr(group_collection, "collect", failing)
    with pytest.raises(AssertionError, match="collection failed"):
        group_collection.collect_groups(tmp_path / "durations.json")
