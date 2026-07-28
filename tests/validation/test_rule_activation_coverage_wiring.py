"""Wiring tests for the rule activation coverage pre-PR wrapper.

The gate's own fail-closed behavior is covered exhaustively in
``test_rule_activation_coverage.py``. This file proves the thin wrapper in
``checks_spec.validate_rule_activation_coverage`` propagates every exit code
correctly: exit 0 is a pass, exit 1 (ratchet) and exit 2 (config) are both
failures, and a missing script raises ``MissingScriptSkip`` rather than reading
as clean.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.validation import check_rule_activation_coverage as gate
from scripts.validation.checks_spec import validate_rule_activation_coverage
from scripts.validation.pre_pr import MissingScriptSkip

GATE_SOURCE = Path(gate.__file__).resolve()
POSITIVE_PROMPT = "Fix the token expiration bug in auth.py before it ships."


def _build_repo(root: Path, *, with_script: bool = True) -> Path:
    """Build a hermetic repo tree; return the baseline path."""
    (root / ".claude" / "rules").mkdir(parents=True)
    (root / ".claude" / "rules" / "r.md").write_text("# r\n", encoding="utf-8")
    skill_dir = root / ".claude" / "skills" / "s"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# s\n", encoding="utf-8")

    rule_scen = root / "tests" / "evals" / "rule-scenarios"
    rule_scen.mkdir(parents=True)
    (rule_scen / "r.json").write_text(
        json.dumps(
            {
                "rule_path": ".claude/rules/r.md",
                "scenarios": [{"id": "c", "input": POSITIVE_PROMPT}],
            }
        ),
        encoding="utf-8",
    )
    skill_scen = root / "tests" / "evals" / "skill-scenarios"
    skill_scen.mkdir(parents=True)
    (skill_scen / "s.json").write_text(
        json.dumps(
            {
                "skill_path": ".claude/skills/s/SKILL.md",
                "scenarios": [{"id": "c", "input": POSITIVE_PROMPT}],
            }
        ),
        encoding="utf-8",
    )

    validation_dir = root / "scripts" / "validation"
    validation_dir.mkdir(parents=True)
    if with_script:
        shutil.copy(GATE_SOURCE, validation_dir / GATE_SOURCE.name)
    baseline = validation_dir / gate.DEFAULT_BASELINE_NAME
    baseline.write_text(
        json.dumps(gate.build_baseline_payload(set(), set())), encoding="utf-8"
    )
    return baseline


def test_wrapper_returns_true_on_exit_zero(tmp_path: Path) -> None:
    _build_repo(tmp_path)
    assert validate_rule_activation_coverage(tmp_path) is True


def test_wrapper_returns_false_on_ratchet_exit_one(tmp_path: Path) -> None:
    _build_repo(tmp_path)
    # Add an uncovered rule not in the baseline: the gate exits 1.
    (tmp_path / ".claude" / "rules" / "new.md").write_text("# new\n", encoding="utf-8")
    assert validate_rule_activation_coverage(tmp_path) is False


def test_wrapper_returns_false_on_config_exit_two(tmp_path: Path) -> None:
    baseline = _build_repo(tmp_path)
    # Remove the baseline: the gate exits 2 (config error), still a failure.
    baseline.unlink()
    assert validate_rule_activation_coverage(tmp_path) is False


def test_wrapper_returns_false_on_orphan_exit_two(tmp_path: Path) -> None:
    _build_repo(tmp_path)
    # A scenario pointing at a deleted rule (the #3507 shape) exits 2.
    orphan = tmp_path / "tests" / "evals" / "rule-scenarios" / "ghost.json"
    orphan.write_text(
        json.dumps(
            {
                "rule_path": ".claude/rules/ghost.md",
                "scenarios": [{"id": "c", "input": POSITIVE_PROMPT}],
            }
        ),
        encoding="utf-8",
    )
    assert validate_rule_activation_coverage(tmp_path) is False


def test_wrapper_raises_when_script_absent(tmp_path: Path) -> None:
    _build_repo(tmp_path, with_script=False)
    with pytest.raises(MissingScriptSkip):
        validate_rule_activation_coverage(tmp_path)
