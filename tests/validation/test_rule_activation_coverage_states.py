"""Tests for the evidence-state report of the activation coverage gate (issue #4882).

The report keeps baseline exemption, scenario presence, and scored efficacy
distinct so a consumer (issue #4871) cannot read baseline membership as proof
that an always-loaded rule earns its context cost.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation import check_rule_activation_coverage as gate
from scripts.validation import report_rule_activation_states as report_mod

PROMPT = "Fix the token expiration bug in auth.py before it ships."


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _cases(*, negative: bool) -> list[dict[str, str]]:
    cases = [{"id": "case-1", "input": PROMPT}]
    if negative:
        cases.append({"id": "case-2", "input": PROMPT, "expected_gate": gate.NEGATIVE_GATE})
    return cases


def _rule(root: Path, rule_id: str, *, scenario: bool, negative: bool = True) -> None:
    _write(root / ".claude" / "rules" / f"{rule_id}.md", f"# {rule_id}\n")
    if scenario:
        payload = {
            "rule_path": f".claude/rules/{rule_id}.md",
            "rule_id": rule_id,
            "scenarios": _cases(negative=negative),
        }
        _write(root / gate.RULE_SCENARIOS_SUBDIR / f"{rule_id}.json", json.dumps(payload))


def _skill(root: Path, skill_id: str, *, scenario: bool, negative: bool = True) -> None:
    _write(root / ".claude" / "skills" / skill_id / "SKILL.md", f"# {skill_id}\n")
    if scenario:
        payload = {
            "skill_path": f".claude/skills/{skill_id}/SKILL.md",
            "skill_id": skill_id,
            "scenarios": _cases(negative=negative),
        }
        _write(root / gate.SKILL_SCENARIOS_SUBDIR / f"{skill_id}.json", json.dumps(payload))


def _baseline(root: Path, rules: list[str], skills: list[str]) -> Path:
    path = root / "baseline.json"
    _write(path, json.dumps({gate.BASELINE_RULE_KEY: rules, gate.BASELINE_SKILL_KEY: skills}))
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Two rules and two skills: one covered and one baseline-exempt of each."""
    _rule(tmp_path, "covered-rule", scenario=True)
    _rule(tmp_path, "exempt-rule", scenario=False)
    _skill(tmp_path, "covered-skill", scenario=True)
    _skill(tmp_path, "exempt-skill", scenario=False)
    # Scenario dirs must exist and be non-empty for both kinds; the covered
    # artifacts above satisfy that.
    return tmp_path


def test_states_split_exempt_from_scenario_defined(repo: Path) -> None:
    baseline = _baseline(repo, ["exempt-rule"], ["exempt-skill"])
    states = report_mod.coverage_states(repo, baseline)
    assert states["rules"]["baseline_exempt"] == ["exempt-rule"]
    assert states["rules"]["scenario_defined_not_scored"] == ["covered-rule"]
    assert states["skills"]["baseline_exempt"] == ["exempt-skill"]
    assert states["skills"]["scenario_defined_not_scored"] == ["covered-skill"]
    assert states["rules"]["not_baselined"] == []


def test_scored_is_null_never_a_count(repo: Path) -> None:
    baseline = _baseline(repo, ["exempt-rule"], ["exempt-skill"])
    states = report_mod.coverage_states(repo, baseline)
    assert states["scored"] is None
    assert states["scored_source"] == report_mod.SCORED_SOURCE


def test_uncovered_outside_baseline_is_listed_not_dropped(repo: Path) -> None:
    baseline = _baseline(repo, [], ["exempt-skill"])
    states = report_mod.coverage_states(repo, baseline)
    assert states["rules"]["not_baselined"] == ["exempt-rule"]
    assert states["rules"]["baseline_exempt"] == []


def _run(repo: Path, baseline: Path, out: Path) -> int:
    return report_mod.main(
        ["--repo-root", str(repo), "--baseline", str(baseline), "--output", str(out)]
    )


def test_cli_writes_report(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = _baseline(repo, ["exempt-rule"], ["exempt-skill"])
    out = repo / "report.json"
    assert _run(repo, baseline, out) == report_mod.EXIT_OK
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["rules"]["baseline_exempt"] == ["exempt-rule"]
    assert data["scored"] is None
    assert "Report written" in capsys.readouterr().out


def test_report_is_deterministic(repo: Path) -> None:
    baseline = _baseline(repo, ["exempt-rule"], ["exempt-skill"])
    first, second = repo / "a.json", repo / "b.json"
    _run(repo, baseline, first)
    _run(repo, baseline, second)
    assert first.read_bytes() == second.read_bytes()


def test_unwritable_output_is_config_error(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = _baseline(repo, ["exempt-rule"], ["exempt-skill"])
    code = _run(repo, baseline, repo / "missing-dir" / "report.json")
    assert code == report_mod.EXIT_CONFIG
    assert "cannot write report" in capsys.readouterr().err


def test_missing_baseline_is_config_error(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = _run(repo, repo / "nope.json", repo / "report.json")
    assert code == report_mod.EXIT_CONFIG
    assert "ERROR" in capsys.readouterr().err


def test_ok_message_disclaims_efficacy(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = _baseline(repo, ["exempt-rule"], ["exempt-skill"])
    code = gate.main(["--repo-root", str(repo), "--baseline", str(baseline)])
    assert code == gate.EXIT_OK
    assert "not efficacy evidence" in capsys.readouterr().out


def test_positive_only_scenario_is_not_runnable(tmp_path: Path) -> None:
    """The gate counts it covered; the evaluator refuses it before scoring (Devin, PR #6072)."""
    _rule(tmp_path, "full-rule", scenario=True)
    _rule(tmp_path, "positive-only-rule", scenario=True, negative=False)
    _skill(tmp_path, "full-skill", scenario=True)
    _skill(tmp_path, "positive-only-skill", scenario=True, negative=False)
    baseline = _baseline(tmp_path, [], [])
    states = report_mod.coverage_states(tmp_path, baseline)
    assert states["rules"]["scenario_defined_not_runnable"] == ["positive-only-rule"]
    assert states["rules"]["scenario_defined_not_scored"] == ["full-rule"]
    assert states["skills"]["scenario_defined_not_runnable"] == ["positive-only-skill"]
    assert states["skills"]["scenario_defined_not_scored"] == ["full-skill"]
    assert states["skills"]["not_baselined"] == []


def test_reference_scenarios_are_ignored_by_the_negative_case_scan(tmp_path: Path) -> None:
    """An ADR-088 reference scenario names a skill_path but no rule_path."""
    _rule(tmp_path, "full-rule", scenario=True)
    _skill(tmp_path, "full-skill", scenario=True)
    reference = tmp_path / gate.RULE_SCENARIOS_SUBDIR / "ref.json"
    _write(reference, json.dumps({"skill_path": ".claude/skills/full-skill/SKILL.md"}))
    assert report_mod._without_negative_case(tmp_path, "rule") == set()


def test_non_list_scenarios_field_counts_as_no_negative_case(tmp_path: Path) -> None:
    _rule(tmp_path, "odd-rule", scenario=False)
    payload = {"rule_path": ".claude/rules/odd-rule.md", "scenarios": "nope"}
    _write(tmp_path / gate.RULE_SCENARIOS_SUBDIR / "odd-rule.json", json.dumps(payload))
    assert report_mod._without_negative_case(tmp_path, "rule") == {"odd-rule"}


def test_unknown_artifact_kind_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(gate.CoverageConfigError, match="unknown artifact kind"):
        report_mod._without_negative_case(tmp_path, "agent")
