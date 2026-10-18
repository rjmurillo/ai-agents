"""The diff-scoped pre-PR gates fail closed without a fresh base ref (issue #6506).

Four gates in ``checks_ci_parity`` diff the branch against its base. With no
resolvable base they used to SKIP, and a failed refresh only warned and used the
stale ``origin/<branch>`` cache. Either way the gate judged the wrong file set
and could read clean while the matching required check failed. Both cases now
raise ``BaseRefUnavailable``, which the runner records as a FAIL.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import checks_ci_parity
import pre_pr

_DIFF_GATES = (
    "validate_placeholder_identity",
    "validate_security_suppressions_diff",
    "validate_memory_placement",
    "validate_route_scenario_coverage",
)


def _stub_base(
    monkeypatch: pytest.MonkeyPatch, base: str | None, refresh: str | None = ""
) -> list[str]:
    """Stub base resolution and refresh; return the refs the refresh was asked about."""
    refreshed: list[str] = []

    def fake_refresh(base_ref: str, _root: Path) -> str | None:
        refreshed.append(base_ref)
        return refresh

    monkeypatch.setattr(checks_ci_parity, "_resolve_default_base_ref", lambda _root: base)
    monkeypatch.setattr(checks_ci_parity, "_refresh_remote_base", fake_refresh)
    return refreshed


def test_the_base_is_refreshed_before_the_gate_diffs(monkeypatch: pytest.MonkeyPatch) -> None:
    refreshed = _stub_base(monkeypatch, "origin/main")

    assert checks_ci_parity._require_base_ref(REPO_ROOT, "test gate") == "origin/main"
    assert refreshed == ["origin/main"]


def test_a_base_that_needs_no_refresh_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """``None`` means no fetch was attempted (a local ref, or CI already fetched)."""
    _stub_base(monkeypatch, "main", refresh=None)

    assert checks_ci_parity._require_base_ref(REPO_ROOT, "test gate") == "main"


def test_a_failed_refresh_fails_instead_of_using_the_stale_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_base(monkeypatch, "origin/main", refresh="offline")

    with pytest.raises(checks_ci_parity.BaseRefUnavailable, match=r"could not refresh origin/main"):
        checks_ci_parity._require_base_ref(REPO_ROOT, "test gate")


def test_an_unresolved_base_fails_instead_of_skipping(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_base(monkeypatch, None)

    with pytest.raises(checks_ci_parity.BaseRefUnavailable, match="none resolved"):
        checks_ci_parity._require_base_ref(REPO_ROOT, "test gate")


@pytest.mark.parametrize("gate", _DIFF_GATES)
def test_each_diff_gate_raises_without_a_base_and_never_runs_its_validator(
    monkeypatch: pytest.MonkeyPatch, gate: str
) -> None:
    _stub_base(monkeypatch, None)
    monkeypatch.setattr(
        checks_ci_parity,
        "_run_workflow_validator",
        lambda *_a, **_k: pytest.fail("the validator must not run without a base"),
    )

    with pytest.raises(checks_ci_parity.BaseRefUnavailable):
        getattr(checks_ci_parity, gate)(REPO_ROOT)


@pytest.mark.parametrize("gate", _DIFF_GATES)
def test_each_diff_gate_raises_when_the_refresh_fails(
    monkeypatch: pytest.MonkeyPatch, gate: str
) -> None:
    _stub_base(monkeypatch, "origin/main", refresh="offline")
    monkeypatch.setattr(
        checks_ci_parity,
        "_run_workflow_validator",
        lambda *_a, **_k: pytest.fail("the validator must not run on a stale base"),
    )

    with pytest.raises(checks_ci_parity.BaseRefUnavailable):
        getattr(checks_ci_parity, gate)(REPO_ROOT)


def test_the_runner_records_a_missing_base_as_a_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_base(monkeypatch, None)
    state = pre_pr.ValidationState()

    passed = pre_pr.run_validation(
        "Placeholder Identity",
        state,
        lambda: checks_ci_parity.validate_placeholder_identity(REPO_ROOT),
    )

    assert passed is False
    assert "none resolved" in capsys.readouterr().out
