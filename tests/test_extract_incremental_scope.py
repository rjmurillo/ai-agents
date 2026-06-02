from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "scripts"
    / "extract_incremental_scope.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("extract_incremental_scope", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extracts_phase_with_issue_number() -> None:
    module = _load_module()

    assert (
        module.extract_incremental_scope("Phase 2 of #1799: finish cache guard")
        == "Phase 2 of #1799"
    )


def test_extracts_pr_slice() -> None:
    module = _load_module()

    assert module.extract_incremental_scope("PR 1 of 3: add validator") == "PR 1 of 3"


def test_ignores_plain_phase_text() -> None:
    module = _load_module()

    assert module.extract_incremental_scope("Fix phase 2 rollout bug") == ""
