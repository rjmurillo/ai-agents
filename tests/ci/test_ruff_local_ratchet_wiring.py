"""Pre-push wiring tests for the ruff ratchets."""

from __future__ import annotations

import sys
from pathlib import Path

from tests.ci.ratchet_test_helpers import ci_owners_of

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import checks_ratchet  # noqa: E402


def test_ruff_ratchets_block_through_required_ci_jobs() -> None:
    """CI owns both ruff ratchets since the pre-push job was removed on 2026-11-27."""
    assert ci_owners_of("scripts/ci/ruff_count_ratchet.py") == ["pytest.yml count-ratchet-guard"]
    assert ci_owners_of("scripts/ci/ruff_ratchet.py") == ["pytest.yml test"]


def test_registry_contains_both_ruff_ratchets() -> None:
    by_name = {ratchet.job_name: ratchet for ratchet in checks_ratchet.RATCHETS}
    assert by_name["python-lint-ratchet"].script == "scripts/ci/ruff_ratchet.py"
    assert by_name["python-lint-count-ratchet"].script == ("scripts/ci/ruff_count_ratchet.py")


def test_ruff_ratchets_keep_the_dev_extra() -> None:
    by_name = {ratchet.job_name: ratchet for ratchet in checks_ratchet.RATCHETS}
    assert by_name["python-lint-ratchet"].extra_dev is True
    assert by_name["python-lint-count-ratchet"].extra_dev is True


def test_whole_tree_ruff_count_ratchet_keeps_base_ref() -> None:
    by_name = {ratchet.job_name: ratchet for ratchet in checks_ratchet.RATCHETS}
    assert by_name["python-lint-count-ratchet"].uses_base_ref is True
