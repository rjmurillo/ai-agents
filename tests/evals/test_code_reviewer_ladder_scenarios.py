"""Structure checks for the minimal-implementation ladder eval scenarios.

Issue #5397 requires evals that separate legitimate minimalism from negligent
omission. These checks do not call a model and never gate on LLM judgment.
They load the file with the eval runner's own loader and assert the three
cases exist with distinct expected verdicts, so the control cannot be deleted
or collapsed into a reject-only set unnoticed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNNER = _REPO_ROOT / "scripts" / "eval" / "eval-prompt-change.py"
_SCENARIOS = _REPO_ROOT / "tests" / "evals" / "code-reviewer-scenarios.json"

_REUSE, _OMISSION, _CONTROL = "CR18", "CR19", "CR20"


def _load_runner() -> ModuleType:
    # The runner imports sibling modules (for example `_anthropic_api`) by flat name.
    if str(_RUNNER.parent) not in sys.path:
        sys.path.insert(0, str(_RUNNER.parent))
    spec = importlib.util.spec_from_file_location("eval_prompt_change", _RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _by_id() -> dict[str, dict[str, Any]]:
    scenarios = _load_runner().load_scenarios(str(_SCENARIOS))
    return {s["id"]: s for s in scenarios}


def test_file_passes_the_runner_loader() -> None:
    assert len(_by_id()) >= 20


def test_ladder_scenarios_exist() -> None:
    scenarios = _by_id()
    for scenario_id in (_REUSE, _OMISSION, _CONTROL):
        assert scenario_id in scenarios


def test_rejection_cases_expect_rejection() -> None:
    scenarios = _by_id()
    assert scenarios[_REUSE]["expected_verdict"].startswith("REJECT")
    assert scenarios[_OMISSION]["expected_verdict"].startswith("REJECT")


def test_negative_control_expects_no_finding() -> None:
    assert _by_id()[_CONTROL]["expected_verdict"].startswith("NO_FINDING")


def test_scenario_ids_are_unique() -> None:
    ids = [s["id"] for s in json.loads(_SCENARIOS.read_text(encoding="utf-8"))["scenarios"]]
    assert len(ids) == len(set(ids))
