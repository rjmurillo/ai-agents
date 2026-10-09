"""A hostile durations file cannot make the split drop a test (issue #6239, AC2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci import run_pytest_partition as runner
from tests.ci.pytest_split_collect_helpers import collect, collect_with_code

# A small real slice keeps four extra collections cheap. The property under test
# belongs to pytest-split, not to the pool, so any multi-file slice shows it.
_HOSTILE_SLICE = "tests/workflows"


def _hostile_durations(slice_ids: list[str], shape: str) -> dict[str, float]:
    """A durations file a pull request head could commit to skew the split."""
    if shape == "one_test_dominates":
        return {node_id: (1e9 if i == 0 else 0.0) for i, node_id in enumerate(slice_ids)}
    if shape == "only_unknown_ids":
        return {f"tests/does_not_exist.py::test_{i}": 5.0 for i in range(50)}
    return {node_id: -1.0 for node_id in slice_ids}


def _run_groups(durations: Path) -> tuple[list[str], list[int]]:
    """Collect every group of the hostile slice; keep node IDs only from exit 0 groups."""
    split_flags = ["--splits", str(runner.SPLIT_COUNT), "--splitting-algorithm"]
    split_flags += [runner.SPLITTING_ALGORITHM, "--durations-path", str(durations)]
    union: list[str] = []
    codes: list[int] = []
    for group in range(1, runner.SPLIT_COUNT + 1):
        node_ids, returncode, output = collect_with_code(
            [*split_flags, "--group", str(group), _HOSTILE_SLICE]
        )
        assert returncode != 0 or node_ids, output
        codes.append(returncode)
        if returncode == 0:
            # A crashed group runs nothing, and its traceback can echo node IDs.
            union.extend(node_ids)
    return union, codes


@pytest.mark.timeout(300)
@pytest.mark.parametrize("shape", ["one_test_dominates", "only_unknown_ids", "negative_durations"])
def test_a_hostile_durations_file_cannot_drop_a_test(shape: str, tmp_path: Path) -> None:
    """AC2: a committed durations edit can skew group sizes but never drop a test.

    ADR-101 rates `tests/.test_durations` Medium on that basis. The worst a head
    edit can do is overload one leg past its job timeout, empty a group, or crash
    the plugin. An empty group exits 5 ("no tests collected") and a crash exits 3
    (INTERNALERROR); run_pytest_non_tmp passes either code through, so the leg
    fails red. The property: no test goes missing while every group exits 0.
    """
    slice_ids = collect([_HOSTILE_SLICE])
    hostile = tmp_path / "durations.json"
    hostile.write_text(json.dumps(_hostile_durations(slice_ids, shape)), encoding="utf-8")
    union, codes = _run_groups(hostile)
    assert len(union) == len(set(union)), "a test was collected by two groups"
    if all(code == 0 for code in codes):
        assert set(union) == set(slice_ids)


@pytest.mark.timeout(300)
def test_a_malformed_durations_file_fails_every_group(tmp_path: Path) -> None:
    """AC2: unparseable JSON fails each leg red; it never passes silently."""
    malformed = tmp_path / "durations.json"
    malformed.write_text("{", encoding="utf-8")
    union, codes = _run_groups(malformed)
    assert all(code != 0 for code in codes), codes
    assert union == []


@pytest.mark.timeout(300)
@pytest.mark.parametrize("fallback", ["missing_file", "empty_object"])
def test_an_absent_or_empty_durations_file_still_covers_the_slice(
    fallback: str, tmp_path: Path
) -> None:
    """AC2: with no usable timings pytest-split splits evenly; no test drops or doubles."""
    path = tmp_path / "durations.json"
    if fallback == "empty_object":
        path.write_text("{}", encoding="utf-8")
    slice_ids = collect([_HOSTILE_SLICE])
    union, codes = _run_groups(path)
    assert codes == [0] * runner.SPLIT_COUNT, codes
    assert len(union) == len(set(union)), "a test was collected by two groups"
    assert set(union) == set(slice_ids)
