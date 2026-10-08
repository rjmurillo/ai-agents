"""A change to a vendor-portability checker selects its real-checker tests.

Issue #6211 split the real-checker cases out of
test_pre_pr_covers_vendor_portability.py. The checkers run as subprocesses, so
no import edge links those tests to the scripts they run. The original file
was selected through its ``pre_pr_sequence`` import, and
vendor_portability_gate_helpers.py imports it for the same reason. If that
import is removed as unused, a change to a checker script stops running the
only tests that execute it, and every push still looks green.
"""

from __future__ import annotations

import pytest

from scripts.test_selection import select_tests
from tests.validation.vendor_portability_gate_helpers import EXPECTED, REPO_ROOT

_REAL_CHECKER_FILES = (
    "tests/validation/test_pre_pr_vendor_portability_real_checker.py",
    "tests/validation/test_pre_pr_vendor_portability_real_checker_skill_md.py",
)


def _script_path(command: str) -> str:
    """Return the repository path of the checker a workflow command runs."""
    tokens = command.split()
    if "-m" in tokens:
        return tokens[tokens.index("-m") + 1].replace(".", "/") + ".py"
    return next(token for token in tokens if token.endswith(".py"))


@pytest.mark.parametrize("command", sorted(EXPECTED))
def test_checker_change_selects_both_real_checker_files(command: str) -> None:
    """SPEC-6211 AC9: selection still runs the real checker for its script."""
    script = _script_path(command)
    assert (REPO_ROOT / script).is_file(), f"{script} does not exist"

    selection = select_tests.select([script], REPO_ROOT)

    # A full-suite fallback would run both files, but it would also pass with
    # the pre_pr_sequence import gone, so it cannot prove the edge exists. If a
    # policy change makes these scripts fall back on purpose, update this test.
    assert not selection.full, f"{script} fell back to the full suite: {selection.reason}"
    missing = [path for path in _REAL_CHECKER_FILES if path not in selection.tests]
    assert not missing, f"{script} change does not select {missing}: {selection.reason}"
