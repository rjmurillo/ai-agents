"""Run the real ``check_skill_md_portability`` checker on its own (issue #6211).

This one case took 25.8s of the 41s that test_pre_pr_covers_vendor_portability.py
spent, because the checker scans every SKILL.md in the tree. Under xdist
``--dist loadfile`` it gets its own file so it does not hold one worker while
the others sit idle. The other real-checker cases run in
test_pre_pr_vendor_portability_real_checker.py, which also holds the guard that
the two files together cover every validator.
"""

from __future__ import annotations

import pytest

from tests.validation.vendor_portability_gate_helpers import (
    REPO_ROOT,
    real_checker_cases,
    validator,
)


@pytest.mark.parametrize(("gate_name", "validator_name"), real_checker_cases(isolated=True))
def test_validator_argv_is_accepted_by_the_real_checker(
    gate_name: str, validator_name: str
) -> None:
    """Run the real checker, because every other test stubs the subprocess.

    Without this, a wrapper could pass a flag the script rejects and the stubbed
    assertions would still be green: argparse would exit 2 only in production.
    """
    assert validator(validator_name)(REPO_ROOT) is True
