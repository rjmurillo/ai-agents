"""The blocking routing gate never runs the checkout's resolver; only `--report` does.

Evidence imports autoplan's resolver from the checkout under test. The gate
reads declarations as data, so a broken or hostile resolver cannot reach it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_skill_routing_roles as gate


class _ResolverRan(Exception):
    """Raised by the stand-in evidence step to prove it was called."""


@pytest.fixture
def evidence_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args: object, **_kwargs: object) -> object:
        raise _ResolverRan("evidence was computed")

    monkeypatch.setattr(gate, "compute_evidence", _boom)


@pytest.mark.usefixtures("evidence_raises")
def test_the_pre_pr_entry_point_computes_no_evidence() -> None:
    assert gate.validate_skill_routing_roles(_REPO_ROOT) is True


@pytest.mark.usefixtures("evidence_raises")
def test_the_cli_without_report_computes_no_evidence() -> None:
    assert gate.main(["--repo-root", str(_REPO_ROOT)]) == 0


@pytest.mark.usefixtures("evidence_raises")
def test_the_cli_with_report_still_computes_evidence() -> None:
    with pytest.raises(_ResolverRan):
        gate.main(["--repo-root", str(_REPO_ROOT), "--report"])
