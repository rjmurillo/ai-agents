"""pre_pr.py reaches the skill frontmatter gate, and a failing result blocks the run.

The gate's own checks are covered in ``tests/test_validation_skill_frontmatter.py``
and ``tests/test_skill_frontmatter_spec.py``. This file proves the pre-PR
sequence calls it with the repository root (``testing.md`` SHOULD 6: prove the
wiring, not only the guard).
"""

from __future__ import annotations

import io
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import pre_pr_sequence

GATE_NAME = "Skill Frontmatter (all skill trees)"


def _drive(
    monkeypatch: pytest.MonkeyPatch, verdict: bool
) -> tuple[list[str], list[Path], list[object]]:
    seen: list[Path] = []
    returned: list[object] = []

    def spy(repo_root: Path) -> bool:
        seen.append(repo_root)
        return verdict

    monkeypatch.setattr(pre_pr_sequence, "validate_skill_frontmatter", spy)
    names: list[str] = []

    def fake_run_validation(
        name: str,
        _state: SimpleNamespace,
        callback: Callable[[], object],
        skip: bool = False,
    ) -> bool:
        names.append(name)
        if name == GATE_NAME and not skip:
            returned.append(callback())
        return True

    args = SimpleNamespace(quick=False, skip_tests=False, verbose=False)
    state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
    with redirect_stdout(io.StringIO()):
        pre_pr_sequence.run_all_validations(REPO_ROOT, args, state, fake_run_validation)
    return names, seen, returned


def test_the_sequence_emits_the_gate_once(monkeypatch: pytest.MonkeyPatch) -> None:
    names, _, _ = _drive(monkeypatch, True)

    assert names.count(GATE_NAME) == 1


def test_the_gate_calls_the_validator_with_the_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    _, seen, _ = _drive(monkeypatch, True)

    assert seen == [REPO_ROOT]


@pytest.mark.parametrize("verdict", [True, False])
def test_the_gate_returns_the_validator_verdict(
    monkeypatch: pytest.MonkeyPatch, verdict: bool
) -> None:
    _, _, returned = _drive(monkeypatch, verdict)

    assert returned == [verdict]
