"""Run each vendor-portability gate's real checker (issue #5670).

Split from test_pre_pr_covers_vendor_portability.py (issue #6211). Every other
test there stubs the subprocess, so this is the only place a wrapper's argv
meets the real script. It is slow by design. Under xdist ``--dist loadfile``
one worker runs a whole file, so the cases are spread over two files:
``check_skill_md_portability`` alone takes about 26s and runs in
test_pre_pr_vendor_portability_real_checker_skill_md.py; the rest run here.
"""

from __future__ import annotations

from typing import Any

import pytest

# Imported as a module, never by test name: a test function bound in this
# namespace would be collected and run a second time from this file.
from tests.validation import (
    test_pre_pr_vendor_portability_real_checker_skill_md as skill_md_module,
)
from tests.validation.vendor_portability_gate_helpers import (
    EXPECTED,
    REAL_CHECKER_ISOLATED,
    REPO_ROOT,
    real_checker_cases,
    validator,
)


@pytest.mark.parametrize(("gate_name", "validator_name"), real_checker_cases(isolated=False))
def test_validator_argv_is_accepted_by_the_real_checker(
    gate_name: str, validator_name: str
) -> None:
    """Run the real checker, because every other test stubs the subprocess.

    Without this, a wrapper could pass a flag the script rejects and the stubbed
    assertions would still be green: argparse would exit 2 only in production.
    """
    assert validator(validator_name)(REPO_ROOT) is True


def test_real_checker_cases_cover_every_validator_exactly_once() -> None:
    """The two real-checker files together run every expected validator once.

    SPEC-6211 AC5. The isolated list names validators by hand, so a rename or
    removal in ``EXPECTED`` would leave its file with an empty parameter set.
    pytest skips an empty set instead of failing it, so without this guard the
    slowest checker would stop running with nothing red. The last two asserts
    check that each file parametrizes the list meant for it.
    """
    expected = sorted(EXPECTED.values())
    shared = real_checker_cases(isolated=False)
    isolated = real_checker_cases(isolated=True)

    assert sorted(shared + isolated) == expected
    assert not set(shared) & set(isolated)
    assert {name for _, name in isolated} == REAL_CHECKER_ISOLATED
    assert _parametrized_cases(test_validator_argv_is_accepted_by_the_real_checker) == shared
    assert (
        _parametrized_cases(skill_md_module.test_validator_argv_is_accepted_by_the_real_checker)
        == isolated
    )


def _parametrized_cases(test_function: Any) -> list[tuple[str, str]]:
    """Return the cases a test's ``parametrize`` mark actually runs."""
    mark = next(mark for mark in test_function.pytestmark if mark.name == "parametrize")
    return list(mark.args[1])
