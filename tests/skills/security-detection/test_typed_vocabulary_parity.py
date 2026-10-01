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


VOCABULARY: dict[str, str] = vars(_load())["TYPED_RESULT_VOCABULARY"]


def parity_errors(vocabulary: dict[str, str]) -> list[str]:
    """Return every mirrored value that ``evidence.py`` does not define."""
    errors: list[str] = []
    for name, value in sorted(vocabulary.items()):
        if name.startswith("REASON_"):
            if getattr(evidence, name, None) != value:
                errors.append(f"{name}={value!r} is not the evidence constant of that name")
        elif name != value or value not in {s.value for s in evidence.EvidenceState}:
            errors.append(f"{name}={value!r} is not an EvidenceState")
    return errors


def test_the_mirror_names_every_state_the_skill_can_emit() -> None:
    states = {name for name in VOCABULARY if not name.startswith("REASON_")}
    assert states == {"PASS", "FAIL", "SKIP", "BLOCKED", "UNKNOWN"}


def test_every_mirrored_value_is_defined_by_evidence() -> None:
    assert parity_errors(VOCABULARY) == []


@pytest.mark.parametrize(
    "mutation",
    [
        {"REASON_TIMEOUT": "time_out"},
        {"REASON_NOT_A_REAL_CODE": "x.y"},
        {"MAYBE": "MAYBE"},
        {"PASS": "OK"},
    ],
)
def test_the_parity_check_fails_on_a_drifted_mirror(mutation: dict[str, str]) -> None:
    """Negative control: a check that cannot fail proves nothing."""
    assert len(parity_errors({**VOCABULARY, **mutation})) == 1
