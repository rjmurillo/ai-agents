"""Every xdist worker must deselect the same tests (issue #6747).

testmon 2.2.0 lets each xdist worker read ``.testmondata`` on its own and decide
which files and tests to skip, and in what order to run the rest. When another
pytest process saves records to that file while the workers start, an early and
a late worker disagree. xdist then stops the partition with "Different tests
were collected" before any test runs.

``scripts.validation.testmon_scoped_sync`` sends the controller's read to each
worker, so there is one decision. These tests cover the pure helpers, the two
hooks with fakes, and a replay with real xdist and testmon: the control without
the plugin fails with the xdist error, the run with it passes.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import pytest

from scripts.validation import testmon_scoped_sync as sync

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_FLAG = f"-p{sync.__name__}"
GATE_SECONDS = 60


class _Data:
    """Stands in for testmon's data object: one real attribute and one durations property."""

    marker = "kept"

    @property
    def avg_durations(self) -> dict[str, float]:
        return {"tests/test_a.py::test_one": 9.0}


class _Select:
    """Stands in for testmon's TestmonSelect plugin."""

    def __init__(self, files: list[str], tests: list[str]) -> None:
        self.deselected_files = files
        self.deselected_tests = tests
        self.testmon_data = _Data()


class _Manager:
    def __init__(self, select: _Select | None) -> None:
        self._plugins: dict[str, object] = {} if select is None else {"TestmonSelect": select}

    def get_plugin(self, name: str) -> object | None:
        return self._plugins.get(name)

    def has_plugin(self, name: str) -> bool:
        return name in self._plugins

    def register(self, plugin: object, name: str) -> None:
        self._plugins[name] = plugin


class _Config:
    def __init__(self, select: _Select | None, workerinput: dict | None = None) -> None:
        self.pluginmanager = _Manager(select)
        if workerinput is not None:
            self.workerinput = workerinput


class _Node:
    def __init__(self, workerinput: dict | None) -> None:
        if workerinput is not None:
            self.workerinput = workerinput


def _controller(select: _Select | None) -> sync._SelectionBroadcast:
    return sync._SelectionBroadcast(_Config(select))


def test_payload_is_sorted_plain_lists() -> None:
    payload = sync.selection_payload({"b.py", "a.py"}, {"c.py::t2", "c.py::t1"})
    assert payload == {"files": ["a.py", "b.py"], "tests": ["c.py::t1", "c.py::t2"]}


def test_payload_drops_tests_in_a_deselected_file() -> None:
    payload = sync.selection_payload(["a.py"], ["a.py::t1", "b.py::t1"])
    assert payload["tests"] == ["b.py::t1"]


def test_payload_of_nothing_is_empty_lists() -> None:
    assert sync.selection_payload([], []) == {"files": [], "tests": []}


def test_adopt_replaces_the_worker_own_choice() -> None:
    select = _Select(["local.py"], ["local.py::t"])
    assert sync.adopt_payload(select, {"files": ["a.py"], "tests": ["b.py::t"]}) is True
    assert select.deselected_files == frozenset({"a.py"})
    assert select.deselected_tests == frozenset({"b.py::t"})


def test_adopt_stops_the_duration_sort_and_keeps_other_attributes() -> None:
    select = _Select([], [])
    sync.adopt_payload(select, {"files": [], "tests": []})
    durations = select.testmon_data.avg_durations
    assert isinstance(durations, defaultdict)
    assert durations["tests/test_a.py::test_one"] == 0
    assert select.testmon_data.marker == "kept"


def test_adopt_twice_wraps_the_data_once() -> None:
    select = _Select([], [])
    sync.adopt_payload(select, {"files": [], "tests": []})
    first = select.testmon_data
    sync.adopt_payload(select, {"files": ["a.py"], "tests": []})
    assert select.testmon_data is first


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "files",
        [],
        {},
        {"files": ["a.py"]},
        {"tests": []},
        {"files": "a.py", "tests": []},
        {"files": [], "tests": [1]},
        {"files": [None], "tests": []},
    ],
)
def test_adopt_ignores_a_payload_that_is_not_two_string_lists(payload: object) -> None:
    select = _Select(["local.py"], ["local.py::t"])
    original = select.testmon_data
    assert sync.adopt_payload(select, payload) is False
    assert select.deselected_files == ["local.py"]
    assert select.deselected_tests == ["local.py::t"]
    assert select.testmon_data is original


def test_controller_hook_adds_the_payload_to_workerinput() -> None:
    node = _Node({})
    _controller(_Select(["a.py"], ["a.py::t", "b.py::t"])).pytest_configure_node(node)
    assert node.workerinput[sync.WORKERINPUT_KEY] == {"files": ["a.py"], "tests": ["b.py::t"]}


def test_controller_hook_does_nothing_without_testmon_selection() -> None:
    node = _Node({})
    _controller(None).pytest_configure_node(node)
    assert node.workerinput == {}


def test_controller_hook_does_nothing_without_workerinput() -> None:
    _controller(_Select(["a.py"], [])).pytest_configure_node(_Node(None))


def test_worker_adopts_the_controller_choice_over_its_own_read() -> None:
    select = _Select(["local.py"], ["local.py::t"])
    payload = {"files": ["a.py"], "tests": ["b.py::t"]}
    config = _Config(select, {sync.WORKERINPUT_KEY: payload})
    sync._SelectionBroadcast(config).pytest_sessionstart(object())
    assert select.deselected_files == frozenset({"a.py"})
    assert select.deselected_tests == frozenset({"b.py::t"})


def test_worker_without_a_payload_keeps_testmon_default() -> None:
    select = _Select(["local.py"], ["local.py::t"])
    sync._SelectionBroadcast(_Config(select, {})).pytest_sessionstart(object())
    assert select.deselected_files == ["local.py"]
    assert select.deselected_tests == ["local.py::t"]


def test_controller_session_start_changes_nothing() -> None:
    select = _Select(["local.py"], [])
    sync._SelectionBroadcast(_Config(select)).pytest_sessionstart(object())
    assert select.deselected_files == ["local.py"]


def test_worker_without_testmon_selection_is_left_alone() -> None:
    config = _Config(None, {sync.WORKERINPUT_KEY: {"files": [], "tests": []}})
    sync._SelectionBroadcast(config).pytest_sessionstart(object())


def test_configure_registers_the_broadcast_once() -> None:
    config = _Config(None)
    sync.pytest_configure(config)
    first = config.pluginmanager.get_plugin(sync._BROADCAST_PLUGIN)
    sync.pytest_configure(config)
    assert isinstance(first, sync._SelectionBroadcast)
    assert config.pluginmanager.get_plugin(sync._BROADCAST_PLUGIN) is first


# The replay: worker 0 reads the database, a sibling pytest run then saves fresh
# records, and only then may worker 1 read. The gate file holds worker 1 inside
# ``pytest_configure``, which runs before testmon's, so its read comes after the save.
_CONFTEST = """
import os
import time
from pathlib import Path

GATE = os.environ.get("TESTMON_TEST_GATE")


def pytest_configure(config):
    worker = getattr(config, "workerinput", {}).get("workerid")
    if GATE and worker and worker != "gw0":
        deadline = time.monotonic() + GATE_SECONDS
        while not Path(GATE).exists() and time.monotonic() < deadline:
            time.sleep(0.05)


def pytest_sessionstart(session):
    worker = getattr(session.config, "workerinput", {}).get("workerid")
    if GATE and worker == "gw0":
        Path(GATE + ".ready").write_text("ready", encoding="utf-8")
""".replace("GATE_SECONDS", str(GATE_SECONDS))

_PARAM_TEST = """
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"


@pytest.mark.parametrize("name", sorted(path.name for path in DATA.glob("*.txt")))
def test_each_data_file(name):
    assert name is not None
"""


def _env(gate: Path | None) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    env.pop("TESTMON_DATAFILE", None)
    env.pop("TESTMON_TEST_GATE", None)
    env["COVERAGE_CORE"] = "ctrace"
    env["PYTHONPATH"] = str(REPO_ROOT)
    if gate is not None:
        env["TESTMON_TEST_GATE"] = str(gate)
    return env


def _pytest(
    project: Path, *, workers: int, plugin: bool, select: bool, gate: Path | None = None
) -> subprocess.Popen[str]:
    flags = ["--testmon"] + (["--testmon-forceselect"] if select else [])
    flags += [PLUGIN_FLAG] if plugin else []
    flags += ["-n", str(workers)] if workers else []
    return subprocess.Popen(
        [sys.executable, "-m", "pytest", *flags, "-q", "-o", "addopts=", "tests"],
        cwd=project,
        env=_env(gate),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    )


def _finish(process: subprocess.Popen[str]) -> tuple[int, str]:
    output, _ = process.communicate(timeout=120)
    return process.returncode, output


def _wait_for(path: Path) -> None:
    deadline = time.monotonic() + GATE_SECONDS
    while not path.exists():
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.05)


def _build_project(project: Path) -> None:
    (project / "conftest.py").write_text(_CONFTEST, encoding="utf-8")
    tests = project / "tests"
    (tests / "data").mkdir(parents=True)
    for name in ("a", "b", "c"):
        (tests / "data" / f"{name}.txt").write_text("x", encoding="utf-8")
    (tests / "test_param.py").write_text(_PARAM_TEST, encoding="utf-8")
    for index in range(4):
        (tests / f"test_plain_{index}.py").write_text(
            "def test_one():\n    assert True\n", encoding="utf-8"
        )


def _replay(project: Path, *, plugin: bool) -> tuple[int, str]:
    """Return the exit code and output of a two-worker run that a sibling run interrupts."""
    pytest.importorskip("testmon")
    pytest.importorskip("xdist")
    _build_project(project)
    code, output = _finish(_pytest(project, workers=0, plugin=plugin, select=False))
    assert code == 0, output
    # An edit leaves test_param.py unstable for any run that has not yet re-recorded it.
    body = (project / "tests" / "test_param.py").read_text(encoding="utf-8")
    (project / "tests" / "test_param.py").write_text(
        body.replace("is not None", "is not None and True"), encoding="utf-8"
    )

    gate = project / "gate"
    first = _pytest(project, workers=2, plugin=plugin, select=True, gate=gate)
    _wait_for(Path(f"{gate}.ready"))
    code, output = _finish(_pytest(project, workers=0, plugin=plugin, select=False))
    assert code == 0, output
    gate.write_text("go", encoding="utf-8")
    return _finish(first)


def test_control_without_the_plugin_collects_different_tests_per_worker(tmp_path: Path) -> None:
    """Pins the testmon 2.2.0 behavior the plugin works around (issue #6747).

    If an upgrade makes this pass, testmon fixed the per-worker read and the
    deselection broadcast can be removed.
    """
    code, output = _replay(tmp_path, plugin=False)
    assert code != 0
    assert "Different tests were collected" in output


def test_the_plugin_makes_every_worker_collect_the_same_tests(tmp_path: Path) -> None:
    code, output = _replay(tmp_path, plugin=True)
    assert code == 0, output
    assert "Different tests were collected" not in output
