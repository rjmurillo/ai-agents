"""The skill's mirrored result vocabulary must stay inside ``evidence.py``.

``detect_infrastructure.py`` cannot import ``scripts/validation/evidence.py``:
the skill ships as a self-contained directory (``plugin-self-containment.md``).
It mirrors the states and reason codes it needs in ``TYPED_RESULT_VOCABULARY``.
Without this test a rename in ``evidence.py`` would leave the skill emitting a
state no consumer recognizes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from scripts.validation import evidence

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude/skills/security-detection/detect_infrastructure.py"


def _load() -> object:
    spec = importlib.util.spec_from_file_location("detect_infrastructure_parity", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VOCABULARY: dict[str, str] = _load().TYPED_RESULT_VOCABULARY  # type: ignore[attr-defined]
STATES = {name: value for name, value in VOCABULARY.items() if not name.startswith("REASON_")}
REASONS = {name: value for name, value in VOCABULARY.items() if name.startswith("REASON_")}


def test_the_vocabulary_names_every_state_the_skill_can_emit() -> None:
    assert set(STATES) == {"PASS", "FAIL", "SKIP", "BLOCKED", "UNKNOWN"}


@pytest.mark.parametrize(("name", "value"), sorted(STATES.items()))
def test_each_state_equals_an_evidence_state(name: str, value: str) -> None:
    assert name == value
    assert evidence.EvidenceState(value).value == value


@pytest.mark.parametrize(("name", "value"), sorted(REASONS.items()))
def test_each_reason_equals_the_evidence_constant_of_the_same_name(
    name: str, value: str
) -> None:
    assert getattr(evidence, name) == value


def test_a_value_evidence_does_not_define_is_rejected() -> None:
    """Negative control: the parity check must be able to fail."""
    with pytest.raises(ValueError):
        evidence.EvidenceState("MAYBE")
    assert not hasattr(evidence, "REASON_NOT_A_REAL_CODE")
