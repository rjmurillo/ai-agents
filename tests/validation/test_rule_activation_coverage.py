"""Tests for the rule and skill activation coverage gate.

These tests build hermetic repo trees under tmp_path so no test depends on the
real `.claude` inventory. Each fail-open vector enumerated in the gate docstring
gets a test that proves the vector fails closed (exit 1 for ratchet, exit 2 for
config), and the ratchet contract gets the two tests the brief requires: a new
uncovered artifact fails, and removing a now-covered artifact from the baseline
passes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from scripts.validation import check_rule_activation_coverage as gate

POSITIVE_PROMPT = "Fix the token expiration bug in auth.py before it ships."
NEGATIVE_PROMPT = "Write a haiku about the weather."


def _write_rule(root: Path, rule_id: str) -> None:
    rules_dir = root / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / f"{rule_id}.md").write_text(f"# {rule_id}\n", encoding="utf-8")


def _write_skill(root: Path, skill_id: str) -> None:
    skill_dir = root / ".claude" / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"# {skill_id}\n", encoding="utf-8")


def _rule_scenario(rule_id: str, *, positive: bool = True) -> dict[str, object]:
    scenario: dict[str, object] = {"id": "case-1", "input": POSITIVE_PROMPT}
    if not positive:
        scenario = {
            "id": "case-1",
            "input": NEGATIVE_PROMPT,
            "expected_gate": gate.NEGATIVE_GATE,
        }
    return {
        "rule_path": f".claude/rules/{rule_id}.md",
        "rule_id": rule_id,
        "scenarios": [scenario],
    }


def _skill_scenario(skill_id: str) -> dict[str, object]:
    return {
        "skill_path": f".claude/skills/{skill_id}/SKILL.md",
        "skill_id": skill_id,
        "scenarios": [{"id": "case-1", "input": POSITIVE_PROMPT}],
    }


def _write_rule_scenario(root: Path, rule_id: str, payload: Mapping[str, object]) -> Path:
    scen_dir = root / "tests" / "evals" / "rule-scenarios"
    scen_dir.mkdir(parents=True, exist_ok=True)
    path = scen_dir / f"{rule_id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_skill_scenario(root: Path, skill_id: str, payload: Mapping[str, object]) -> Path:
    scen_dir = root / "tests" / "evals" / "skill-scenarios"
    scen_dir.mkdir(parents=True, exist_ok=True)
    path = scen_dir / f"{skill_id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_baseline(
    root: Path, uncovered_rules: list[str], uncovered_skills: list[str]
) -> Path:
    path = root / "baseline.json"
    payload = gate.build_baseline_payload(set(uncovered_rules), set(uncovered_skills))
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _make_tree(root: Path) -> None:
    """Build a minimal valid tree: one covered rule, one covered skill.

    Ensures both scenario directories exist so directory-missing failures do not
    mask the case under test.
    """
    _write_rule(root, "covered-rule")
    _write_rule(root, "bare-rule")
    _write_skill(root, "covered-skill")
    _write_skill(root, "bare-skill")
    _write_rule_scenario(root, "covered-rule", _rule_scenario("covered-rule"))
    _write_skill_scenario(root, "covered-skill", _skill_scenario("covered-skill"))


def _run(root: Path, baseline: Path, *, update: bool = False) -> int:
    argv = ["--repo-root", str(root), "--baseline", str(baseline)]
    if update:
        argv.append("--update-baseline")
    return gate.main(argv)


# ---------------------------------------------------------------------------
# Happy path and the two required ratchet tests
# ---------------------------------------------------------------------------


def test_passes_when_uncovered_within_baseline(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    baseline = _write_baseline(tmp_path, ["bare-rule"], ["bare-skill"])
    assert _run(tmp_path, baseline) == gate.EXIT_OK


def test_new_uncovered_rule_fails_ratchet(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    baseline = _write_baseline(tmp_path, ["bare-rule"], ["bare-skill"])
    _write_rule(tmp_path, "brand-new-rule")
    assert _run(tmp_path, baseline) == gate.EXIT_RATCHET


def test_new_uncovered_skill_fails_ratchet(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    baseline = _write_baseline(tmp_path, ["bare-rule"], ["bare-skill"])
    _write_skill(tmp_path, "brand-new-skill")
    assert _run(tmp_path, baseline) == gate.EXIT_RATCHET


def test_removing_now_covered_rule_from_baseline_passes(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    _write_rule_scenario(tmp_path, "bare-rule", _rule_scenario("bare-rule"))
    baseline = _write_baseline(tmp_path, [], ["bare-skill"])
    assert _run(tmp_path, baseline) == gate.EXIT_OK


def test_stale_baseline_entry_reports_but_passes(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    _write_rule_scenario(tmp_path, "bare-rule", _rule_scenario("bare-rule"))
    baseline = _write_baseline(tmp_path, ["bare-rule"], ["bare-skill"])
    assert _run(tmp_path, baseline) == gate.EXIT_OK


# ---------------------------------------------------------------------------
# Inventory discovery fails closed
# ---------------------------------------------------------------------------


def test_missing_rules_dir_is_config_error(tmp_path: Path) -> None:
    _write_skill(tmp_path, "covered-skill")
    _write_skill_scenario(tmp_path, "covered-skill", _skill_scenario("covered-skill"))
    baseline = _write_baseline(tmp_path, [], [])
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_zero_rule_files_is_config_error(tmp_path: Path) -> None:
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    _write_skill(tmp_path, "covered-skill")
    _write_skill_scenario(tmp_path, "covered-skill", _skill_scenario("covered-skill"))
    baseline = _write_baseline(tmp_path, [], [])
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_missing_skills_dir_is_config_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "covered-rule")
    _write_rule_scenario(tmp_path, "covered-rule", _rule_scenario("covered-rule"))
    baseline = _write_baseline(tmp_path, [], [])
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_zero_skill_files_is_config_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "covered-rule")
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    _write_rule_scenario(tmp_path, "covered-rule", _rule_scenario("covered-rule"))
    baseline = _write_baseline(tmp_path, [], [])
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_missing_rule_scenario_dir_is_config_error(tmp_path: Path) -> None:
    _write_rule(tmp_path, "covered-rule")
    _write_skill(tmp_path, "covered-skill")
    _write_skill_scenario(tmp_path, "covered-skill", _skill_scenario("covered-skill"))
    baseline = _write_baseline(tmp_path, ["covered-rule"], [])
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


# ---------------------------------------------------------------------------
# Scenario shape fails closed
# ---------------------------------------------------------------------------


def test_unparseable_scenario_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    bad = tmp_path / "tests" / "evals" / "rule-scenarios" / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    baseline = _write_baseline(tmp_path, ["bare-rule"], ["bare-skill"])
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_scenario_missing_target_key_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    payload = {"scenarios": [{"id": "x", "input": POSITIVE_PROMPT}]}
    _write_rule_scenario(tmp_path, "covered-rule", payload)
    baseline = _write_baseline(tmp_path, ["bare-rule"], ["bare-skill"])
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_scenario_with_both_target_keys_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    payload = _rule_scenario("covered-rule")
    payload["skill_path"] = ".claude/skills/covered-skill/SKILL.md"
    _write_rule_scenario(tmp_path, "covered-rule", payload)
    baseline = _write_baseline(tmp_path, ["bare-rule"], ["bare-skill"])
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_rule_dir_with_skill_path_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    payload = _skill_scenario("covered-skill")
    _write_rule_scenario(tmp_path, "misfiled", payload)
    baseline = _write_baseline(tmp_path, ["bare-rule"], ["bare-skill"])
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_orphan_rule_scenario_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    _write_rule_scenario(tmp_path, "ghost", _rule_scenario("ghost"))
    baseline = _write_baseline(tmp_path, ["bare-rule"], ["bare-skill"])
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_orphan_skill_scenario_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    _write_skill_scenario(tmp_path, "ghost", _skill_scenario("ghost"))
    baseline = _write_baseline(tmp_path, ["bare-rule"], ["bare-skill"])
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_empty_scenarios_list_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    payload = {
        "rule_path": ".claude/rules/covered-rule.md",
        "rule_id": "covered-rule",
        "scenarios": [],
    }
    _write_rule_scenario(tmp_path, "covered-rule", payload)
    baseline = _write_baseline(tmp_path, ["bare-rule"], ["bare-skill"])
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_all_negative_scenarios_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    _write_rule_scenario(
        tmp_path, "covered-rule", _rule_scenario("covered-rule", positive=False)
    )
    baseline = _write_baseline(tmp_path, ["bare-rule"], ["bare-skill"])
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_empty_input_scenario_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    payload = {
        "rule_path": ".claude/rules/covered-rule.md",
        "scenarios": [{"id": "x", "input": "   "}],
    }
    _write_rule_scenario(tmp_path, "covered-rule", payload)
    baseline = _write_baseline(tmp_path, ["bare-rule"], ["bare-skill"])
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_path_traversal_target_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    payload = {
        "rule_path": "../../../etc/passwd",
        "scenarios": [{"id": "x", "input": POSITIVE_PROMPT}],
    }
    _write_rule_scenario(tmp_path, "evil", payload)
    baseline = _write_baseline(tmp_path, ["bare-rule"], ["bare-skill"])
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


# ---------------------------------------------------------------------------
# Baseline load fails closed
# ---------------------------------------------------------------------------


def test_missing_baseline_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    missing = tmp_path / "does-not-exist.json"
    assert _run(tmp_path, missing) == gate.EXIT_CONFIG


def test_unparseable_baseline_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{not json", encoding="utf-8")
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_baseline_non_object_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text("[]", encoding="utf-8")
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_baseline_missing_key_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"uncovered_rules": []}), encoding="utf-8")
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_baseline_non_list_value_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"uncovered_rules": "bare-rule", "uncovered_skills": []}),
        encoding="utf-8",
    )
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_baseline_non_string_entry_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"uncovered_rules": [123], "uncovered_skills": []}),
        encoding="utf-8",
    )
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_baseline_duplicate_entry_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {"uncovered_rules": ["bare-rule", "bare-rule"], "uncovered_skills": []}
        ),
        encoding="utf-8",
    )
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


# ---------------------------------------------------------------------------
# --update-baseline
# ---------------------------------------------------------------------------


def test_update_baseline_writes_current_uncovered(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    baseline = tmp_path / "baseline.json"
    assert _run(tmp_path, baseline, update=True) == gate.EXIT_OK
    rules, skills = gate.load_baseline(baseline)
    assert rules == {"bare-rule"}
    assert skills == {"bare-skill"}


def test_update_baseline_then_check_passes(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    baseline = tmp_path / "baseline.json"
    assert _run(tmp_path, baseline, update=True) == gate.EXIT_OK
    assert _run(tmp_path, baseline) == gate.EXIT_OK


# ---------------------------------------------------------------------------
# Unit-level checks on the helpers
# ---------------------------------------------------------------------------


def test_discover_rules_reads_stems(tmp_path: Path) -> None:
    _write_rule(tmp_path, "alpha")
    _write_rule(tmp_path, "beta")
    assert gate.discover_rules(tmp_path) == {"alpha", "beta"}


def test_discover_skills_reads_dir_names(tmp_path: Path) -> None:
    _write_skill(tmp_path, "alpha")
    _write_skill(tmp_path, "beta")
    assert gate.discover_skills(tmp_path) == {"alpha", "beta"}


def test_diff_uncovered_splits_new_and_resolved() -> None:
    new, resolved = gate.diff_uncovered({"a", "b"}, {"b", "c"})
    assert new == {"a"}
    assert resolved == {"c"}


def test_covered_ids_requires_positive_case(tmp_path: Path) -> None:
    _write_rule(tmp_path, "r")
    _write_rule_scenario(tmp_path, "r", _rule_scenario("r", positive=False))
    (tmp_path / "tests" / "evals" / "skill-scenarios").mkdir(parents=True)
    with pytest.raises(gate.CoverageConfigError):
        gate.covered_ids(tmp_path, "rule")


def test_unreadable_baseline_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_bytes(b"\xff\xfe\x00broken")
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG


def test_unwritable_baseline_update_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    baseline = tmp_path / "no-such-dir" / "baseline.json"
    assert _run(tmp_path, baseline, update=True) == gate.EXIT_CONFIG


def test_empty_scenario_dir_is_config_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    scenario_dir = tmp_path / "tests" / "evals" / "rule-scenarios"
    for path in scenario_dir.glob("*.json"):
        path.unlink()
    baseline = _write_baseline(
        tmp_path, ["bare-rule", "covered-rule"], ["bare-skill"]
    )
    assert _run(tmp_path, baseline) == gate.EXIT_CONFIG
