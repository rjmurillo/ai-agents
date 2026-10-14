"""Keep one pytest-testmon run from deleting a sibling run's records (issue #6406).

The pre-push hook runs its pytest partitions at the same time against one
``.testmondata`` (issue #6345). testmon 2.2.0 collects in
``TestmonData.sync_db_fs_tests``, which deletes every recorded test that this run
neither collected nor found stable. A partition that reaches that step after a
sibling has saved deletes the sibling's fresh rows. CI recorded 30 tests where
60 were expected, and a real push loses the same history: the next selection
re-runs tests it could have skipped.

This plugin wraps that method so the delete covers only:

- tests whose file this run collected (a test removed or renamed in a file this
  partition owns), and
- tests whose file no longer exists on disk (a deleted test file).

A test in an existing file this run did not collect belongs to another partition
and stays. Pre-push loads the plugin with ``-pscripts.validation.testmon_scoped_sync``
from ``git_hook_policy._TESTMON_FLAGS``.

The wrapper swaps ``delete_test_executions`` on the instance's database for the
length of one call, so the add step and the delete SQL stay testmon's own.
"""

from __future__ import annotations

import functools
import os
from collections.abc import Callable, Collection
from typing import Protocol

_WRAPPED_MARKER = "_ai_agents_scoped_sync"


class _Database(Protocol):
    delete_test_executions: Callable[..., None]


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


def pytest_configure(config: object) -> None:
    """Install the wrapper as pytest starts; a missing testmon is not an error."""
    install()
