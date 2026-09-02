"""Child-pytest proof that discovery runs once per worker (issue #5379).

``tests/test_conftest_local_env_vars_cache.py`` proves the cache with repeated
in-process calls. That is one pytest item calling a function three times, so it
cannot observe what issue #5379 actually asks for: that *multiple collected
items*, spread over *real xdist worker processes*, still trigger exactly one
``git rev-parse --local-env-vars`` per worker.

This module spawns a real child pytest over a generated project whose conftest
re-exports the repository's autouse git-isolation fixture and counts the
discovery subprocesses that fixture causes. It runs that child twice, serial
and under ``-n 2``, and asserts the per-worker count from each run.

The counter lives in the child's conftest rather than in the code under test,
so nothing here changes how ``_local_env_vars()`` behaves. Counts are handed
back through one JSON file per worker, written in ``pytest_sessionfinish``,
because an xdist worker is a separate process with no shared memory.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_CONFTEST = REPO_ROOT / "tests" / "conftest.py"

# Six is enough to make "once per item" and "once per worker" different numbers
# under both run modes, and small enough that two child pytest runs stay cheap.
_ITEM_COUNT = 6

_CHILD_CONFTEST = '''
"""Generated conftest: count git discovery calls the real fixture triggers."""

import importlib.util
import json
import os
import subprocess
from pathlib import Path

_REAL = Path(os.environ["LOCAL_ENV_VARS_REAL_CONFTEST"])
_COUNT_DIR = Path(os.environ["LOCAL_ENV_VARS_COUNT_DIR"])

_spec = importlib.util.spec_from_file_location("real_tests_conftest", _REAL)
real = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(real)

_counts = {"discovery": 0, "items": 0}


class _CountingSubprocess:
    """Stand-in for the ``subprocess`` module in the real conftest's globals.

    ``_local_env_vars()`` resolves ``subprocess.run`` and ``subprocess`` error
    types through its own module namespace, so rebinding that one name counts
    the spawns without touching the function under test.
    """

    CalledProcessError = subprocess.CalledProcessError
    SubprocessError = subprocess.SubprocessError
    TimeoutExpired = subprocess.TimeoutExpired

    @staticmethod
    def run(args, **kwargs):
        if "--local-env-vars" in args:
            _counts["discovery"] += 1
        return subprocess.run(args, **kwargs)


real.subprocess = _CountingSubprocess

# Re-exporting the fixture object registers it for this session, so the items
# below go through the repository's real autouse isolation path.
_isolate_tmp_path_from_parent_git_repo = real._isolate_tmp_path_from_parent_git_repo


def pytest_runtest_call(item):
    _counts["items"] += 1


def pytest_sessionfinish(session, exitstatus):
    worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    _COUNT_DIR.mkdir(parents=True, exist_ok=True)
    (_COUNT_DIR / (worker + ".json")).write_text(json.dumps(_counts), encoding="utf-8")
'''


def _write_child_project(root: Path) -> None:
    """Generate a minimal pytest project with ``_ITEM_COUNT`` items."""
    root.mkdir(parents=True, exist_ok=True)
    # Its own ini file, so the repository's addopts and plugins do not apply.
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (root / "conftest.py").write_text(_CHILD_CONFTEST, encoding="utf-8")
    bodies = "\n".join(f"def test_item_{index}():\n    pass\n" for index in range(_ITEM_COUNT))
    (root / "test_items.py").write_text(bodies, encoding="utf-8")


def _run_child_pytest(root: Path, count_dir: Path, extra_args: list[str]) -> None:
    """Run the generated project in a child process and require a green run."""
    env = {
        key: value
        for key, value in os.environ.items()
        # The parent session's own xdist and pytest coordinates would otherwise
        # leak in and make the child believe it is already a worker.
        if not key.startswith("PYTEST_") and key != "_PYTEST_BASETEMP"
    }
    env["LOCAL_ENV_VARS_REAL_CONFTEST"] = str(REAL_CONFTEST)
    env["LOCAL_ENV_VARS_COUNT_DIR"] = str(count_dir)
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *extra_args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, (
        f"child pytest exited {completed.returncode}\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )


def _read_counts(count_dir: Path) -> dict[str, dict[str, int]]:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(count_dir.glob("*.json"))
    }


def _assert_one_discovery_per_working_process(counts: dict[str, dict[str, int]]) -> None:
    """Every process that ran items discovered exactly once; idle ones, zero."""
    assert counts, "child pytest wrote no per-worker count files"
    total_items = sum(entry["items"] for entry in counts.values())
    assert total_items == _ITEM_COUNT, (
        f"child ran {total_items} items, expected {_ITEM_COUNT}: {counts}"
    )
    for worker, entry in counts.items():
        expected = 1 if entry["items"] else 0
        assert entry["discovery"] == expected, (
            f"worker {worker} ran {entry['discovery']} git discovery subprocesses "
            f"for {entry['items']} items; caching should make that "
            f"{expected}. Full counts: {counts}"
        )


def test_serial_run_discovers_once_for_many_items(tmp_path: Path) -> None:
    """Six collected items in one process trigger one discovery subprocess."""
    root = tmp_path / "serial"
    count_dir = tmp_path / "counts-serial"
    _write_child_project(root)

    _run_child_pytest(root, count_dir, [])

    counts = _read_counts(count_dir)
    assert list(counts) == ["master"], f"expected a single serial process: {counts}"
    _assert_one_discovery_per_working_process(counts)


def test_xdist_run_discovers_once_per_worker(tmp_path: Path) -> None:
    """Under ``-n 2`` each worker discovers once, not once per item it owns.

    xdist distributes the six items across the workers rather than repeating
    them, so the assertion is per worker: a worker that ran any item ran
    exactly one discovery subprocess. The distribution itself is xdist's to
    choose, so this does not pin how many items each worker gets.
    """
    pytest.importorskip("xdist", reason="pytest-xdist is required for the parallel proof")
    root = tmp_path / "xdist"
    count_dir = tmp_path / "counts-xdist"
    _write_child_project(root)

    _run_child_pytest(root, count_dir, ["-n", "2"])

    counts = _read_counts(count_dir)
    workers = [name for name in counts if name.startswith("gw")]
    assert len(workers) == 2, f"expected two xdist workers, got {sorted(counts)}"
    _assert_one_discovery_per_working_process(counts)
