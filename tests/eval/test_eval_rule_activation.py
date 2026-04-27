"""Unit tests for scripts/eval/eval-rule-activation.py.

Covers:
- aggregate() verdict outcomes (PASS, FAIL_THRESHOLD, FAIL_NO_DELTA,
  FAIL_JUDGE_ERRORS, NO_POSITIVE_CASES)
- _load_scenarios_file() rule_path validation: must resolve under
  .claude/rules/ with a .md suffix; rejects path traversal, repo-internal
  exfiltration paths, and non-rule files.
- best_mechanism selection excludes baseline so a high-baseline / low-rule
  scenario does not silently pass.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"

# eval-rule-activation.py imports sibling modules (_anthropic_api, _eval_common)
# via plain `from X import Y` statements, so EVAL_DIR must be on sys.path
# while the module loads. Scope the mutation to the load itself and remove
# it afterward so we do not change import resolution for other test modules.
_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    _spec = importlib.util.spec_from_file_location(
        "eval_rule_activation", EVAL_DIR / "eval-rule-activation.py"
    )
    assert _spec and _spec.loader
    eval_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(eval_mod)
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_mech(score: int, judge_failed: bool = False) -> dict[str, object]:
    """Build a single-mechanism result with uniform scores."""
    return {
        "scores": {
            "activation_score": score,
            "citation_score": score,
            "behavior_score": score,
            "judge_failed": judge_failed,
        }
    }


def _make_scenario(
    baseline: int,
    description: int,
    full: int,
    negative: bool = False,
    judge_failed: bool = False,
) -> dict[str, object]:
    return {
        "negative_case": negative,
        "mechanisms": {
            "baseline": _make_mech(baseline, judge_failed),
            "description": _make_mech(description),
            "full": _make_mech(full),
        },
    }


# ---------------------------------------------------------------------------
# aggregate() verdicts
# ---------------------------------------------------------------------------


class TestAggregateVerdicts:
    def test_pass_when_full_clears_threshold_and_beats_baseline(self):
        scenarios = [_make_scenario(baseline=1, description=4, full=5)]
        summary = eval_mod.aggregate(scenarios)
        assert summary["verdict"] == "PASS"
        assert summary["best_mechanism"] in ("description", "full")
        assert summary["best_mechanism"] != "baseline"

    def test_fail_threshold_when_below_min_activation(self):
        # All mechanisms score below 3.5; even though full beats baseline by
        # 1.0 the absolute quality bar is not met.
        scenarios = [_make_scenario(baseline=1, description=2, full=2)]
        summary = eval_mod.aggregate(scenarios)
        assert summary["verdict"] == "FAIL_THRESHOLD"

    def test_fail_no_delta_when_baseline_keeps_pace(self):
        # Full clears 3.5 but only by 0.0 over baseline.
        scenarios = [_make_scenario(baseline=4, description=4, full=4)]
        summary = eval_mod.aggregate(scenarios)
        assert summary["verdict"] == "FAIL_NO_DELTA"

    def test_baseline_not_chosen_as_best_mechanism(self):
        # Baseline scores high, rule-enhanced mechanisms low. Without the
        # exclusion of baseline from best_mechanism selection, the verdict
        # would be FAIL_NO_DELTA. With the fix, the verdict reports the
        # rule-enhanced mechanism's actual failure.
        scenarios = [_make_scenario(baseline=5, description=2, full=2)]
        summary = eval_mod.aggregate(scenarios)
        assert summary["best_mechanism"] != "baseline"
        assert summary["verdict"] == "FAIL_THRESHOLD"

    def test_judge_failures_force_fail_judge_errors_verdict(self):
        scenarios = [
            _make_scenario(baseline=1, description=4, full=5, judge_failed=True),
        ]
        summary = eval_mod.aggregate(scenarios)
        assert summary["verdict"] == "FAIL_JUDGE_ERRORS"
        assert summary["total_judge_failures"] >= 1

    def test_no_positive_cases_when_only_negative_scenarios(self):
        scenarios = [_make_scenario(baseline=4, description=4, full=4, negative=True)]
        summary = eval_mod.aggregate(scenarios)
        assert summary["verdict"] == "NO_POSITIVE_CASES"

    def test_failed_scenarios_count_in_average(self):
        # One passing scenario + one failed (judge_failed) scenario should
        # not let the rule PASS by silently dropping the failure.
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=1, description=5, full=5, judge_failed=True),
        ]
        summary = eval_mod.aggregate(scenarios)
        # judge_failed forces the FAIL_JUDGE_ERRORS path before averages decide
        assert summary["verdict"] == "FAIL_JUDGE_ERRORS"


# ---------------------------------------------------------------------------
# _load_scenarios_file() path validation
# ---------------------------------------------------------------------------


class TestLoadScenariosFile:
    def test_rejects_invalid_json(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("{ not json", encoding="utf-8")
        result = eval_mod._load_scenarios_file(str(bad))
        assert result == 2

    def test_rejects_non_dict_json(self, tmp_path: Path):
        # JSON parses but is a list, not an object: must reject before .get() crashes.
        f = tmp_path / "list.json"
        f.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
        result = eval_mod._load_scenarios_file(str(f))
        assert result == 2

    def test_rejects_missing_rule_path(self, tmp_path: Path):
        f = tmp_path / "no_rule_path.json"
        f.write_text(json.dumps({"scenarios": []}), encoding="utf-8")
        result = eval_mod._load_scenarios_file(str(f))
        assert result == 2

    def test_rejects_path_outside_rules_dir(self, tmp_path: Path):
        # Path resolves inside the repo but outside .claude/rules/
        f = tmp_path / "outside_rules.json"
        f.write_text(
            json.dumps({"rule_path": "AGENTS.md", "scenarios": []}),
            encoding="utf-8",
        )
        result = eval_mod._load_scenarios_file(str(f))
        assert result == 2

    def test_rejects_path_traversal(self, tmp_path: Path):
        f = tmp_path / "traversal.json"
        f.write_text(
            json.dumps(
                {
                    "rule_path": "../../etc/passwd",
                    "scenarios": [],
                }
            ),
            encoding="utf-8",
        )
        result = eval_mod._load_scenarios_file(str(f))
        assert result == 2

    def test_rejects_non_md_suffix(self, tmp_path: Path):
        # Even within .claude/rules/, non-.md files must be rejected.
        f = tmp_path / "non_md.json"
        f.write_text(
            json.dumps(
                {"rule_path": ".claude/rules/", "scenarios": []}
            ),
            encoding="utf-8",
        )
        result = eval_mod._load_scenarios_file(str(f))
        assert result == 2

    def test_rejects_missing_scenarios_file(self):
        result = eval_mod._load_scenarios_file("/nonexistent/path.json")
        assert result == 2

    def test_accepts_valid_rule_under_rules_dir(self, tmp_path: Path):
        # Use an actual rule file shipping in this repo as the target.
        target = REPO_ROOT / ".claude" / "rules" / "working-with-legacy-code.md"
        if not target.is_file():
            pytest.skip("working-with-legacy-code.md not present in this checkout")
        f = tmp_path / "ok.json"
        f.write_text(
            json.dumps(
                {
                    "rule_path": ".claude/rules/working-with-legacy-code.md",
                    "rule_id": "working-with-legacy-code",
                    "scenarios": [],
                }
            ),
            encoding="utf-8",
        )
        result = eval_mod._load_scenarios_file(str(f))
        assert isinstance(result, tuple)
        scenarios_data, rule_path = result
        assert scenarios_data["rule_id"] == "working-with-legacy-code"
        assert rule_path.is_file()


# ---------------------------------------------------------------------------
# _clamp_score
# ---------------------------------------------------------------------------


class TestClampScore:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (3, 3),
            (0, 0),
            (5, 5),
            (-1, 0),
            (10, 5),
            ("4", 4),
            ("abc", 0),
            (None, 0),
            (True, 1),  # bool is int subclass; True -> 1, False -> 0
            (3.7, 3),  # float coerces to int via int()
        ],
    )
    def test_clamps_to_zero_to_five(self, value: object, expected: int):
        assert eval_mod._clamp_score(value) == expected
