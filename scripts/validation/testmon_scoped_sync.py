"""Keep one pytest-testmon run from deleting a sibling run's records (issue #6406).

Two pytest partitions can run at the same time against one ``.testmondata``.
The pre-push hook did so (issue #6345) until issue #6477 gave each overlapping
lane its own copy; a shared database still occurs when two runs overlap by hand
or in a test. testmon 2.2.0 collects in ``TestmonData.sync_db_fs_tests``, which
deletes every recorded test that this run neither collected nor found stable. A
partition that reaches that step after a sibling has saved deletes the sibling's
fresh rows. CI recorded 30 tests where 60 were expected; the next selection then
re-runs tests it could have skipped.

This plugin wraps that method so the delete covers only:

- tests whose file this run collected (a test removed or renamed in a file this
  partition owns), and
- tests whose file no longer exists on disk (a deleted test file).

A test in an existing file this run did not collect belongs to another partition
and stays.

Known trade-off: an existing file that now holds no tests keeps its old rows.
Under xdist the controller syncs from worker test ids alone
(``pytest_xdist_node_collection_finished``), so it cannot tell an empty file
from a sibling's file. Those rows are inert: testmon only selects collected
tests. They go once the file is deleted or collects a test again.

Pre-push loads the plugin with ``-pscripts.validation.testmon_scoped_sync``
from ``git_hook_policy._TESTMON_FLAGS``.

The wrapper swaps ``delete_test_executions`` on the instance's database for the
length of one call, so the add step and the delete SQL stay testmon's own.

The same plugin also pins what every xdist worker deselects (issue #6747).
testmon 2.2.0 has each worker read the database on its own and decide which
files and tests to skip. If another pytest process saves records to the same
database while the workers start, an early worker and a late worker see
different records and collect different tests. xdist then fails the partition
with "Different tests were collected" before any test runs. The controller's
read happens once, so it sends that read to each worker through
``workerinput`` and the worker adopts it in place of its own. A worker that
gets no payload keeps testmon's own choice.

Order matters as much as the set, because xdist compares the collected lists
item by item. testmon sorts each worker's items by average duration read from the
database, so two workers with the same set can still disagree. A worker that
adopts the payload also stops sorting and keeps pytest's own collection order,
which is the same on every worker. The cost is that the fast-first ordering is
gone for workers that adopt a payload.
"""

from __future__ import annotations

import functools
import os
from collections import defaultdict
from collections.abc import Callable, Collection
from typing import Protocol, cast

import pytest

_WRAPPED_MARKER = "_ai_agents_scoped_sync"
_SELECT_PLUGIN = "TestmonSelect"
_BROADCAST_PLUGIN = "ai_agents_testmon_selection_broadcast"
WORKERINPUT_KEY = "ai_agents_testmon_deselected"


class _Database(Protocol):
    delete_test_executions: Callable[..., None]


class _Selection(Protocol):
    """The slice of testmon's ``TestmonSelect`` plugin that this module reads and sets."""

    deselected_files: Collection[str]
    deselected_tests: Collection[str]
    testmon_data: object


class _PluginManager(Protocol):
    def get_plugin(self, name: str) -> object | None: ...

    def has_plugin(self, name: str) -> bool: ...

    def register(self, plugin: object, name: str) -> object: ...


class _Config(Protocol):
    """The slice of ``pytest.Config`` that this module reads."""

    @property
    def pluginmanager(self) -> _PluginManager: ...


class _Node(Protocol):
    """The slice of an xdist worker controller that the controller hook writes to."""

    workerinput: dict[str, object]


class _TestmonData(Protocol):
    rootdir: str
    db: _Database


def _home_file(test_name: str) -> str:
    """Return the file part of a testmon test name (``path::class::test``)."""
    return test_name.split("::", 1)[0]


def scoped_deletions(
    test_names: Collection[str],
    collected_files: Collection[str],
    file_exists: Callable[[str], bool],
) -> list[str]:
    """Return the test names this run may delete, in the order given.

    Args:
        test_names: Recorded tests that this run did not collect and did not find stable.
        collected_files: Files this run collected tests from.
        file_exists: Whether a recorded test's file is still on disk.
    """
    return [
        name
        for name in test_names
        if _home_file(name) in collected_files or not file_exists(_home_file(name))
    ]


def _scoped(original: Callable[..., None]) -> Callable[..., None]:
    @functools.wraps(original)
    def sync_db_fs_tests(self: _TestmonData, retain: Collection[str]) -> None:
        collected_files = {_home_file(name) for name in retain}
        rootdir = str(self.rootdir)
        database = self.db
        delete = database.delete_test_executions

        def scoped_delete(test_names: Collection[str], exec_id: int) -> None:
            kept = scoped_deletions(
                list(test_names),
                collected_files,
                lambda file: os.path.exists(os.path.join(rootdir, file)),
            )
            delete(kept, exec_id)

        database.delete_test_executions = scoped_delete
        try:
            original(self, retain)
        finally:
            del database.delete_test_executions

    setattr(sync_db_fs_tests, _WRAPPED_MARKER, True)
    return sync_db_fs_tests


def install() -> bool:
    """Wrap testmon's sync once. Return False when testmon or the hook is absent."""
    try:
        from testmon.testmon_core import TestmonData
    except ImportError:
        return False
    current = getattr(TestmonData, "sync_db_fs_tests", None)
    if current is None:
        return False
    if not getattr(current, _WRAPPED_MARKER, False):
        TestmonData.sync_db_fs_tests = _scoped(current)
    return True


def selection_payload(
    deselected_files: Collection[str], deselected_tests: Collection[str]
) -> dict[str, list[str]]:
    """Return the controller's deselection as plain sorted lists for ``workerinput``.

    When testmon selects, a deselected file is never collected, so a test inside
    one carries no information and is left out to keep the message to each
    worker small. When testmon only collects, such a test runs in the first
    group instead of the last. The set that runs is the same.
    """
    files = sorted(set(deselected_files))
    skipped = set(files)
    tests = sorted(name for name in set(deselected_tests) if _home_file(name) not in skipped)
    return {"files": files, "tests": tests}


class _NeutralDurations:
    """Wrap testmon's data so every test sorts as equal and collection order stays.

    Every other attribute comes from the wrapped data unchanged.
    """

    def __init__(self, wrapped: object) -> None:
        self._wrapped = wrapped

    @property
    def avg_durations(self) -> defaultdict[str, int]:
        return defaultdict(int)

    def __getattr__(self, name: str) -> object:
        return getattr(self._wrapped, name)


def adopt_payload(select: _Selection, payload: object) -> bool:
    """Replace a worker's own deselection and order with the controller's.

    Return True when adopted.

    A payload that is not a mapping of two string lists is ignored, so a worker
    never trades a working default for a malformed one.
    """
    if not isinstance(payload, dict):
        return False
    files, tests = payload.get("files"), payload.get("tests")
    if not (isinstance(files, list) and isinstance(tests, list)):
        return False
    if not all(isinstance(name, str) for name in (*files, *tests)):
        return False
    select.deselected_files = frozenset(files)
    select.deselected_tests = frozenset(tests)
    if not isinstance(select.testmon_data, _NeutralDurations):
        select.testmon_data = _NeutralDurations(select.testmon_data)
    return True


class _SelectionBroadcast:
    """Send the controller's deselection to each worker and adopt it there."""

    def __init__(self, config: _Config) -> None:
        self._config = config

    @pytest.hookimpl(optionalhook=True)
    def pytest_configure_node(self, node: _Node) -> None:
        """Controller side, once per worker: add the deselection to ``workerinput``."""
        workerinput = getattr(node, "workerinput", None)
        select = cast(_Selection | None, self._config.pluginmanager.get_plugin(_SELECT_PLUGIN))
        if workerinput is None or select is None:
            return
        workerinput[WORKERINPUT_KEY] = selection_payload(
            select.deselected_files, select.deselected_tests
        )

    def pytest_sessionstart(self, session: object) -> None:
        """Worker side, before collection: adopt the controller's deselection."""
        workerinput = getattr(self._config, "workerinput", None)
        select = cast(_Selection | None, self._config.pluginmanager.get_plugin(_SELECT_PLUGIN))
        if workerinput is None or select is None:
            return
        adopt_payload(select, workerinput.get(WORKERINPUT_KEY))


def pytest_configure(config: _Config) -> None:
    """Install the wrapper as pytest starts; a missing testmon is not an error."""
    install()
    manager = getattr(config, "pluginmanager", None)
    if manager is not None and not manager.has_plugin(_BROADCAST_PLUGIN):
        manager.register(_SelectionBroadcast(config), _BROADCAST_PLUGIN)
