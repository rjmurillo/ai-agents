"""Wiring test: the pre-PR sequence must actually run the manifest validator.

`.claude/rules/testing.md` SHOULD 6 ("prove the wiring, not only the guard"):
the validator's own unit tests (`test_skill_routing_manifest.py`) prove the
guard, but they cannot prove any call site reaches it. This module drives the
real `pre_pr_sequence.run_all_validations` and the `pre_pr` facade so a future
edit that drops the gate, or drops the re-export, fails here.

The gate is driven twice over the same repo root, differing only in whether the
underlying validator returns True or False, so a gate that fails for an
unrelated reason fails its own control too.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import pre_pr
import pre_pr_sequence

GATE_NAME = "Skill Routing Manifest"


@pytest.fixture(autouse=True)
def _clear_fast_stage_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(pre_pr_sequence.FAST_STAGE_RAN_ENV, raising=False)


def _run_gate(monkeypatch: pytest.MonkeyPatch, *, validator_result: bool) -> bool | None:
    """Run only the manifest gate and return the pass/fail it recorded."""
    recorded: dict[str, bool] = {}
    calls: list[Path] = []

    def _spy(repo_root: Path) -> bool:
        calls.append(repo_root)
        return validator_result

    # ``_root_only`` resolves the validator by name from the module globals at
    # call time, so rebinding the attribute is observed by the gate.
    monkeypatch.setattr(pre_pr_sequence, "validate_skill_routing_manifest", _spy)

    def fake_run_validation(name, _state, callback, skip=False):
        if name == GATE_NAME and not skip:
            recorded[name] = bool(callback())
        return True

    args = SimpleNamespace(quick=False, skip_tests=False, verbose=False)
    state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
    pre_pr_sequence.run_all_validations(REPO_ROOT, args, state, fake_run_validation)
    assert calls, f"{GATE_NAME} gate did not invoke validate_skill_routing_manifest"
    assert all(path == REPO_ROOT for path in calls)
    return recorded.get(GATE_NAME)


class TestManifestGateWiring:
    def test_gate_is_present_in_the_sequence(self) -> None:
        names = [gate.name for gate in pre_pr_sequence._SEQUENCE]
        assert GATE_NAME in names

    def test_gate_passes_when_validator_returns_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert _run_gate(monkeypatch, validator_result=True) is True

    def test_gate_fails_when_validator_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert _run_gate(monkeypatch, validator_result=False) is False

    def test_pre_pr_reexports_the_identical_validator(self) -> None:
        assert (
            pre_pr.validate_skill_routing_manifest
            is pre_pr_sequence.validate_skill_routing_manifest
        )
