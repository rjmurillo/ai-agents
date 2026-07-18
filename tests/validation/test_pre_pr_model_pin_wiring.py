"""Wiring tests for the model-pin governance gate in the pre-PR runner (Issue #3073).

Covers the ADR-080 model-pin check being wired into ``pre_pr`` in warn mode:

- positive: the wrapper passes in warn mode against the real tree, and
  ``check_model_pins.py`` runs as a plain standalone script (the import-path
  bug this issue fixed);
- negative: a config-error exit (2) from the wrapped script fails the wrapper,
  and an absent script raises ``MissingScriptSkip``;
- edge: the sequence extraction keeps ``pre_pr.py`` under its size ceiling and
  places the new gate immediately after the spec-contradiction check.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the pre-PR runner modules the way they are designed to be imported: add
# ``scripts/validation`` to ``sys.path`` and import by bare name. These modules
# self-insert their own directory and use bare intra-package imports (Issue
# #2223), so a package-path import (``from scripts.validation import ...``) makes
# mypy at repo root type-check them and surface the pre-existing #2876 bare-Any
# ``no-any-return`` debt in unrelated code. The bare import keeps this test
# scoped to the wiring it verifies.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import checks_spec  # noqa: E402
import pre_pr  # noqa: E402
import pre_pr_sequence  # noqa: E402


def test_validate_model_pins_passes_in_warn_mode() -> None:
    """Positive: warn mode reports and exits 0 against the current tree."""
    assert checks_spec.validate_model_pins(REPO_ROOT) is True


def test_validate_model_pins_fails_on_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative: a config-error exit (2) from the wrapped script fails the gate.

    Warn mode never exits nonzero on a policy violation, so a nonzero exit here
    is a real defect (missing baseline or manifest) and must not pass.
    """
    monkeypatch.setattr(
        checks_spec, "_run_subprocess", lambda *_a, **_k: (2, "", "config error")
    )
    assert checks_spec.validate_model_pins(REPO_ROOT) is False


def test_validate_model_pins_skips_when_script_absent(tmp_path: Path) -> None:
    """Edge: an absent check script raises the SKIP signal, not a hard failure."""
    # Use the exception class ``checks_spec`` actually raises (its bare-module
    # ``checks_common`` import), not the package-path copy, to avoid the
    # duplicate-module class-identity mismatch.
    with pytest.raises(checks_spec.MissingScriptSkip):
        checks_spec.validate_model_pins(tmp_path)


def test_pre_pr_facade_reexports_validate_model_pins() -> None:
    """Positive: ``pre_pr`` re-exports the wrapper for existing importers."""
    assert hasattr(pre_pr, "validate_model_pins")
    assert callable(pre_pr.validate_model_pins)


def test_run_all_validations_wires_model_pins_after_spec_contradiction() -> None:
    """Edge: the gate runs, and directly after the spec-contradiction check.

    Injects a recording ``run_validation`` so the ordered sequence is asserted
    without invoking the real validators. Locks the placement against an
    accidental reorder in a future refactor.
    """
    recorded: list[str] = []

    def fake_run_validation(
        name: str, _state: object, _callback: object, skip: bool = False
    ) -> bool:
        recorded.append(name)
        return True

    state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
    args = SimpleNamespace(quick=True, skip_tests=False, verbose=False)
    pre_pr_sequence.run_all_validations(REPO_ROOT, args, state, fake_run_validation)

    assert "Model Pin Governance (warn)" in recorded
    idx = recorded.index("Spec Contradiction Check")
    assert recorded[idx + 1] == "Model Pin Governance (warn)"


def test_check_model_pins_runs_as_standalone_script() -> None:
    """Negative/regression: the script must run outside ``-m`` and pre-commit.

    ``skill_frontmatter`` imports ``scripts.validation.models`` absolutely, so
    ``check_model_pins.py`` must add the repo root to ``sys.path``. Without the
    Issue #3073 fix this exits nonzero with ``ModuleNotFoundError: scripts``.
    """
    script = REPO_ROOT / "scripts" / "validation" / "check_model_pins.py"
    result = subprocess.run(
        [sys.executable, str(script), "--mode", "warn"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr


def test_pre_pr_under_size_ceiling() -> None:
    """Edge: extraction keeps ``pre_pr.py`` under 500 lines (Issue #3073)."""
    text = (REPO_ROOT / "scripts" / "validation" / "pre_pr.py").read_text(
        encoding="utf-8"
    )
    assert len(text.splitlines()) < 500
