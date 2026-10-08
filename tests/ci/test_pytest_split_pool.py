"""The split groups cover the pool exactly once, and the durations file is fresh.

Issue #6239 acceptance criteria covered here:

- AC2: every pytest CI leg runs its full share. The union of the four split
  groups' collected node IDs equals the whole pool's, with no duplicate.
- AC4: pytest-split balances by recorded duration, so the committed durations
  file must name most of the pool, and no group collects a file that belongs to
  a dedicated leg or a pin step.

Collection runs `pytest --collect-only` in a child process against the real
tree, so a group that drops or doubles a test fails here and not on a CI leg.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from scripts.ci import run_pytest_partition as runner

_REPO = Path(__file__).resolve().parents[2]
_DURATIONS = _REPO / runner.DURATIONS_PATH

# The share of the pool allowed to be missing from the durations file before a
# split group stops being balanced. pytest-split assigns an unknown test the
# average known duration, so a small gap is harmless; a large one skews groups.
MAX_MISSING_FRACTION = 0.20

_COLLECT_TIMEOUT_SECONDS = 280


def _collect(args: list[str]) -> list[str]:
    """Node IDs pytest collects for ``args``, in collection order."""
    node_ids, returncode, output = _collect_with_code(args)
    assert returncode == 0, output
    return node_ids


def _collect_with_code(args: list[str]) -> tuple[list[str], int, str]:
    """Node IDs, pytest's exit code, and the output tail for ``args``."""
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=--import-mode=importlib",
        "--collect-only",
        "-q",
        *args,
    ]
    result = subprocess.run(
        command,
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=_COLLECT_TIMEOUT_SECONDS,
    )
    node_ids = [line for line in result.stdout.splitlines() if "::" in line]
    return node_ids, result.returncode, result.stdout[-2000:] + result.stderr[-2000:]


def _without_parallel_flags(args: list[str]) -> list[str]:
    """Drop xdist flags: collection needs no workers."""
    assert args[:4] == runner._PARALLEL
    return args[4:]


def _pool_args() -> list[str]:
    """The pool with no split flags: what the four groups must add up to."""
    return [*runner._POOL_IGNORES, "tests/"]


def missing_fraction(pool_ids: list[str], durations: dict[str, float]) -> float:
    """The share of ``pool_ids`` that ``durations`` has no entry for."""
    if not pool_ids:
        raise ValueError("the pool collected no tests")
    missing = [node_id for node_id in pool_ids if node_id not in durations]
    return len(missing) / len(pool_ids)


def _load_durations(path: Path) -> dict[str, float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object of node ID to seconds")
    return {str(key): float(value) for key, value in data.items()}


@pytest.fixture(scope="module")
def collected() -> dict[str, list[str]]:
    """Collect the pool and each split group once, concurrently."""
    jobs = {"pool": _pool_args()}
    for name in runner.split_names():
        jobs[name] = _without_parallel_flags(runner._PARTITION_FULL_ARGS[name])
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = {name: executor.submit(_collect, args) for name, args in jobs.items()}
        return {name: future.result() for name, future in futures.items()}


@pytest.mark.timeout(300)
class TestSplitGroupsCoverThePool:
    def test_the_pool_is_not_empty(self, collected: dict[str, list[str]]) -> None:
        assert len(collected["pool"]) > 1000

    def test_the_union_of_the_groups_equals_the_pool(self, collected: dict[str, list[str]]) -> None:
        union = [node_id for name in runner.split_names() for node_id in collected[name]]
        assert set(union) == set(collected["pool"])

    def test_no_node_id_is_collected_twice(self, collected: dict[str, list[str]]) -> None:
        union = [node_id for name in runner.split_names() for node_id in collected[name]]
        duplicates = [node_id for node_id, count in Counter(union).items() if count > 1]
        assert not duplicates, duplicates[:5]
        assert len(union) == len(collected["pool"])

    def test_every_group_collects_something(self, collected: dict[str, list[str]]) -> None:
        for name in runner.split_names():
            assert collected[name], name

    def test_no_group_collects_a_dedicated_or_pinned_file(
        self, collected: dict[str, list[str]]
    ) -> None:
        excluded = runner._SAFE_PUSH_TESTS | runner._PR_AUTOFIX_TESTS | runner._UNPARTITIONED_TESTS
        for name in runner.split_names():
            files = {node_id.split("::", 1)[0] for node_id in collected[name]}
            assert not files & excluded, (name, sorted(files & excluded))

    def test_the_dedicated_legs_still_collect_their_files(self) -> None:
        safe_push = _collect(runner._PARTITION_FULL_ARGS["safe-push"])
        pr_autofix = _collect(runner._PARTITION_FULL_ARGS["pr-autofix"])
        assert {i.split("::", 1)[0] for i in safe_push} == runner._SAFE_PUSH_TESTS
        assert {i.split("::", 1)[0] for i in pr_autofix} == runner._PR_AUTOFIX_TESTS


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
    slice_ids = _collect([_HOSTILE_SLICE])
    hostile = tmp_path / "durations.json"
    hostile.write_text(json.dumps(_hostile_durations(slice_ids, shape)), encoding="utf-8")
    split_flags = ["--splits", str(runner.SPLIT_COUNT), "--splitting-algorithm"]
    split_flags += [runner.SPLITTING_ALGORITHM, "--durations-path", str(hostile)]
    union: list[str] = []
    codes: list[int] = []
    for group in range(1, runner.SPLIT_COUNT + 1):
        node_ids, returncode, output = _collect_with_code(
            [*split_flags, "--group", str(group), _HOSTILE_SLICE]
        )
        assert returncode != 0 or node_ids, output
        codes.append(returncode)
        if returncode == 0:
            # A crashed group runs nothing, and its traceback can echo node IDs.
            union.extend(node_ids)
    assert len(union) == len(set(union)), "a test was collected by two groups"
    if all(code == 0 for code in codes):
        assert set(union) == set(slice_ids)


class TestMissingFraction:
    def test_all_known_is_zero(self) -> None:
        assert missing_fraction(["a::t", "b::t"], {"a::t": 1.0, "b::t": 2.0}) == 0.0

    def test_counts_only_ids_absent_from_the_file(self) -> None:
        assert missing_fraction(["a::t", "b::t", "c::t", "d::t"], {"a::t": 1.0}) == 0.75

    def test_extra_entries_for_deleted_tests_do_not_count(self) -> None:
        assert missing_fraction(["a::t"], {"a::t": 1.0, "gone::t": 5.0}) == 0.0

    def test_an_empty_pool_is_an_error_not_a_pass(self) -> None:
        with pytest.raises(ValueError, match="collected no tests"):
            missing_fraction([], {"a::t": 1.0})

    def test_whitespace_in_an_id_is_not_trimmed(self) -> None:
        assert missing_fraction(["a::t "], {"a::t": 1.0}) == 1.0


class TestLoadDurations:
    def test_reads_node_ids_and_seconds(self, tmp_path: Path) -> None:
        path = tmp_path / "d"
        path.write_text('{"a::t": 1.5}', encoding="utf-8")
        assert _load_durations(path) == {"a::t": 1.5}

    def test_a_non_object_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "d"
        path.write_text("[1, 2]", encoding="utf-8")
        with pytest.raises(ValueError, match="not a JSON object"):
            _load_durations(path)

    def test_malformed_json_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "d"
        path.write_text("{", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            _load_durations(path)

    def test_a_non_numeric_duration_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "d"
        path.write_text('{"a::t": "soon"}', encoding="utf-8")
        with pytest.raises(ValueError):
            _load_durations(path)


@pytest.mark.timeout(300)
def test_the_durations_file_names_most_of_the_pool(request: pytest.FixtureRequest) -> None:
    """Refresh it with the command in tests/AGENTS.md when this fails.

    Skips while the file is absent: pytest-split then warns and splits by test
    count, which still runs every test.
    """
    if not _DURATIONS.is_file():
        pytest.skip(f"{runner.DURATIONS_PATH} is not committed yet; pytest-split splits evenly")
    pool_ids = request.getfixturevalue("collected")["pool"]
    fraction = missing_fraction(pool_ids, _load_durations(_DURATIONS))
    assert fraction <= MAX_MISSING_FRACTION, (
        f"{fraction:.1%} of the pool is missing from {runner.DURATIONS_PATH} "
        f"(limit {MAX_MISSING_FRACTION:.0%}); refresh it, see tests/AGENTS.md"
    )
