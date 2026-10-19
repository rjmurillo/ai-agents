"""Reference scenarios must satisfy the same skill path spelling rule as skill scenarios."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation import check_rule_activation_coverage as gate

POSITIVE_PROMPT = "Fix the token expiration bug in auth.py before it ships."


def _write_skill(root: Path, skill_id: str) -> None:
    skill_dir = root / ".claude" / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"# {skill_id}\n", encoding="utf-8")


def _write_rule_scenario(root: Path, name: str, payload: dict[str, object]) -> None:
    scen_dir = root / "tests" / "evals" / "rule-scenarios"
    scen_dir.mkdir(parents=True, exist_ok=True)
    (scen_dir / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def _reference_scenario(skill_path: str, reference_path: str) -> dict[str, object]:
    return {
        "skill_path": skill_path,
        "reference_path": reference_path,
        "scenarios": [{"id": "case-1", "input": POSITIVE_PROMPT}],
    }


def test_reference_scenario_with_direct_src_claude_skill_path_is_refused(tmp_path: Path) -> None:
    shipped = tmp_path / "src" / "claude" / "skills" / "alpha"
    (shipped / "references").mkdir(parents=True)
    (shipped / "SKILL.md").write_text("x", encoding="utf-8")
    (shipped / "references" / "r.md").write_text("x", encoding="utf-8")
    _write_rule_scenario(
        tmp_path,
        "ref",
        _reference_scenario(
            "src/claude/skills/alpha/SKILL.md", "src/claude/skills/alpha/references/r.md"
        ),
    )
    with pytest.raises(gate.CoverageConfigError, match="direct src/claude/skills/ path"):
        gate.covered_ids(tmp_path, "rule")


def test_reference_scenario_with_claude_spelling_is_excluded_from_rule_coverage(
    tmp_path: Path,
) -> None:
    _write_skill(tmp_path, "alpha")
    ref = tmp_path / ".claude" / "skills" / "alpha" / "references"
    ref.mkdir()
    (ref / "r.md").write_text("x", encoding="utf-8")
    _write_rule_scenario(
        tmp_path,
        "ref",
        _reference_scenario(
            ".claude/skills/alpha/SKILL.md", ".claude/skills/alpha/references/r.md"
        ),
    )
    assert gate.covered_ids(tmp_path, "rule") == set()
