"""Unit tests for scripts/eval/eval-rule-activation.py.

Covers:
- aggregate() verdict outcomes (PASS, FAIL_THRESHOLD, FAIL_NO_DELTA,
  FAIL_JUDGE_ERRORS, NO_POSITIVE_CASES)
- _load_scenarios_file() target validation: rule paths must resolve under
  .claude/rules/ and skill references must resolve under one skill's
  references/ directory.
- best_mechanism selection excludes baseline so a high-baseline / low-rule
  scenario does not silently pass.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any

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
    def test_pass_when_description_clears_threshold_and_beats_baseline(self):
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

    def test_full_cannot_rescue_description_failure(self):
        # 1, not 0. Zero is not on the 1..5 rubric, so it now reads as an
        # unmeasured cell and trips the coverage gate before the threshold one
        # ever runs, which tested a different thing than the name claims.
        scenarios = [_make_scenario(baseline=1, description=1, full=5)]

        summary = eval_mod.aggregate(scenarios)

        assert summary["baseline_avg"] == 1.0
        assert summary["delta_description_vs_baseline"] == 0.0
        assert summary["delta_full_vs_baseline"] == 4.0
        assert summary["best_mechanism"] == "full"
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


class TestScoreResponseJudgeShape:
    @pytest.mark.parametrize(
        "judge_json",
        [
            "{}",
            '{"activation_score": 5, "citation_score": "5", "behavior_score": 5}',
            '{"activation_score": 5, "citation_score": 5}',
            '{"activation_score": NaN, "citation_score": 5, "behavior_score": 5}',
            '{"activation_score": Infinity, "citation_score": 5, "behavior_score": 5}',
            '{"activation_score": 6, "citation_score": 5, "behavior_score": 5}',
            '{"activation_score": 0, "citation_score": 5, "behavior_score": 5}',
            '{"activation_score": -1, "citation_score": 5, "behavior_score": 5}',
            '{"activation_score": 4.9, "citation_score": 5, "behavior_score": 5}',
            '{"activation_score": 5.0, "citation_score": 5, "behavior_score": 5}',
            '{"activation_score": 5e0, "citation_score": 5, "behavior_score": 5}',
        ],
    )
    def test_malformed_judge_score_object_sets_judge_failed(self, monkeypatch, judge_json):
        monkeypatch.setattr(eval_mod, "_call_api", lambda *_args, **_kwargs: judge_json)

        scores = eval_mod.score_response(
            "sk-test",
            {"input": "x", "expected_gate": "apply-rule"},
            "response",
        )

        assert scores["judge_failed"] is True
        assert scores["activation_score"] == 0


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

    def test_rejects_non_string_rule_path(self, tmp_path: Path):
        # rule_path must be a string. List/dict/int values must reject cleanly
        # rather than crash at Path joining.
        f = tmp_path / "non_string.json"
        f.write_text(
            json.dumps({"rule_path": ["a", "b"], "scenarios": []}),
            encoding="utf-8",
        )
        assert eval_mod._load_scenarios_file(str(f)) == 2

    def test_rejects_empty_string_rule_path(self, tmp_path: Path):
        f = tmp_path / "empty.json"
        f.write_text(
            json.dumps({"rule_path": "   ", "scenarios": []}),
            encoding="utf-8",
        )
        assert eval_mod._load_scenarios_file(str(f)) == 2

    def test_rejects_scenarios_not_a_list(self, tmp_path: Path):
        f = tmp_path / "scenarios_dict.json"
        f.write_text(
            json.dumps(
                {
                    "rule_path": ".claude/rules/unified-software-engineering.md",
                    "scenarios": {"id": "S1"},
                }
            ),
            encoding="utf-8",
        )
        assert eval_mod._load_scenarios_file(str(f)) == 2

    def test_rejects_scenario_missing_id(self, tmp_path: Path):
        f = tmp_path / "missing_id.json"
        f.write_text(
            json.dumps(
                {
                    "rule_path": ".claude/rules/unified-software-engineering.md",
                    "scenarios": [{"input": "test"}],
                }
            ),
            encoding="utf-8",
        )
        assert eval_mod._load_scenarios_file(str(f)) == 2

    def test_rejects_scenario_missing_input(self, tmp_path: Path):
        f = tmp_path / "missing_input.json"
        f.write_text(
            json.dumps(
                {
                    "rule_path": ".claude/rules/unified-software-engineering.md",
                    "scenarios": [{"id": "S1"}],
                }
            ),
            encoding="utf-8",
        )
        assert eval_mod._load_scenarios_file(str(f)) == 2

    def test_rejects_non_dict_scenario_item(self, tmp_path: Path):
        f = tmp_path / "scalar_scenario.json"
        f.write_text(
            json.dumps(
                {
                    "rule_path": ".claude/rules/unified-software-engineering.md",
                    "scenarios": ["S1"],
                }
            ),
            encoding="utf-8",
        )
        assert eval_mod._load_scenarios_file(str(f)) == 2

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
            json.dumps({"rule_path": ".claude/rules/", "scenarios": []}),
            encoding="utf-8",
        )
        result = eval_mod._load_scenarios_file(str(f))
        assert result == 2

    def test_rejects_missing_scenarios_file(self):
        result = eval_mod._load_scenarios_file("/nonexistent/path.json")
        assert result == 2

    def test_accepts_valid_rule_under_rules_dir(self, tmp_path: Path):
        # Use an actual rule file shipping in this repo as the target.
        target = REPO_ROOT / ".claude" / "rules" / "unified-software-engineering.md"
        if not target.is_file():
            pytest.skip("unified-software-engineering.md not present in this checkout")
        f = tmp_path / "ok.json"
        f.write_text(
            json.dumps(
                {
                    "rule_path": ".claude/rules/unified-software-engineering.md",
                    "rule_id": "unified-software-engineering",
                    "scenarios": [],
                }
            ),
            encoding="utf-8",
        )
        result = eval_mod._load_scenarios_file(str(f))
        assert isinstance(result, tuple)
        scenarios_data, target_paths = result
        rule_path, reference_path = target_paths
        assert scenarios_data["rule_id"] == "unified-software-engineering"
        assert rule_path.is_file()
        assert reference_path is None

    def test_accepts_valid_software_engineering_skill_reference(self, tmp_path: Path):
        f = tmp_path / "skill.json"
        f.write_text(
            json.dumps(
                {
                    "skill_path": ".claude/skills/software-engineering-library/SKILL.md",
                    "reference_path": (
                        ".claude/skills/software-engineering-library/"
                        "references/working-with-legacy-code.md"
                    ),
                    "rule_id": "working-with-legacy-code",
                    "scenarios": [],
                }
            ),
            encoding="utf-8",
        )

        result = eval_mod._load_scenarios_file(str(f))

        assert isinstance(result, tuple)
        _, target_paths = result
        skill_path, reference_path = target_paths
        assert skill_path.name == "SKILL.md"
        assert reference_path is not None
        assert reference_path.name == "working-with-legacy-code.md"

    def test_rejects_skill_reference_outside_reference_directory(self, tmp_path: Path):
        f = tmp_path / "bad_skill_ref.json"
        f.write_text(
            json.dumps(
                {
                    "skill_path": ".claude/skills/software-engineering-library/SKILL.md",
                    "reference_path": ".claude/skills/autoplan/SKILL.md",
                    "scenarios": [],
                }
            ),
            encoding="utf-8",
        )

        assert eval_mod._load_scenarios_file(str(f)) == 2


def _assert_fixture_routes_to_library(rule_id: str) -> None:
    fixture = REPO_ROOT / "tests" / "evals" / "rule-scenarios" / f"{rule_id}.json"
    loaded = eval_mod._load_scenarios_file(str(fixture))
    assert isinstance(loaded, tuple)
    data, target_paths = loaded
    skill_path, reference_path = target_paths
    assert data["rule_id"] == rule_id
    expected_skill = REPO_ROOT / ".claude" / "skills" / "software-engineering-library" / "SKILL.md"
    assert skill_path == expected_skill
    assert reference_path == (
        REPO_ROOT
        / ".claude"
        / "skills"
        / "software-engineering-library"
        / "references"
        / f"{rule_id}.md"
    )


def test_activation_fixture_routes_clean_architecture_to_library():
    _assert_fixture_routes_to_library("clean-architecture")


def test_activation_fixture_routes_domain_driven_design_to_library():
    _assert_fixture_routes_to_library("domain-driven-design")


def test_activation_fixture_routes_enterprise_patterns_to_library():
    _assert_fixture_routes_to_library("enterprise-patterns")


def test_activation_fixture_routes_refactoring_to_library():
    _assert_fixture_routes_to_library("refactoring")


def test_activation_fixture_routes_working_with_legacy_code_to_library():
    _assert_fixture_routes_to_library("working-with-legacy-code")


def test_activation_fixture_routes_data_intensive_applications_to_library():
    _assert_fixture_routes_to_library("data-intensive-applications")


def test_activation_fixture_routes_release_it_to_library():
    _assert_fixture_routes_to_library("release-it")


def test_activation_fixture_routes_philosophy_of_software_design_to_library():
    _assert_fixture_routes_to_library("philosophy-of-software-design")


def _read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _software_engineering_library_route(
    request: str,
    discovered_evidence: str,
) -> tuple[str | None, str | None]:
    """Offline proxy for the autoplan to analyze to skill route.

    The test reads the real routing surfaces. It does not trust the fixture's
    declared target path, so removing the autoplan row, analyze handoff, or
    frontmatter trigger breaks the route.
    """
    autoplan = _read_text(".claude/skills/autoplan/SKILL.md").lower()
    analyze = _read_text(".claude/skills/analyze/SKILL.md").lower()
    library = _read_text(".claude/skills/software-engineering-library/SKILL.md").lower()
    combined = f"{request} {discovered_evidence}".lower()

    if "software-engineering-library" not in library:
        return None, None

    direct_trigger = "software-engineering-library" in autoplan and any(
        trigger in combined and trigger in library
        for trigger in (
            "architecture review",
            "architecture boundaries",
            "software design depth",
            "dependency boundary",
            "module interface shape",
            "domain modeling",
            "bounded context",
            "refactoring",
            "code smell",
            "external api",
            "queues",
            "retries",
            "transactions",
            "event ordering",
            "schema evolution",
            "timeout",
            "circuit breaker",
            "bulkhead",
        )
    )
    bug_to_analyze = "fix " in request.lower() and "skill: analyze" in autoplan
    analyze_discovers_risk = any(
        trigger in combined and trigger in analyze and trigger in library
        for trigger in (
            "low test coverage",
            "old file",
            "hard-to-test",
            "external api",
            "queues",
            "retries",
            "transaction",
            "event ordering",
            "schema evolution",
            "layer dependency",
            "bounded context",
            "module interface shape",
        )
    )
    if not (direct_trigger or (bug_to_analyze and analyze_discovers_risk)):
        return None, None

    reference_signals = (
        (
            "clean-architecture",
            ("architecture review", "dependency boundary", "layer boundary"),
        ),
        (
            "domain-driven-design",
            ("domain modeling", "bounded context"),
        ),
        (
            "enterprise-patterns",
            ("repository", "unit-of-work", "transactions"),
        ),
        (
            "refactoring",
            ("refactoring", "code smell"),
        ),
        (
            "working-with-legacy-code",
            ("low test coverage", "old file", "characterization test"),
        ),
        (
            "data-intensive-applications",
            ("schema evolution", "event ordering", "data consistency"),
        ),
        (
            "release-it",
            ("external api", "queues", "retries", "timeout", "circuit breaker", "bulkhead"),
        ),
        (
            "philosophy-of-software-design",
            ("module interface shape", "complexity hiding"),
        ),
    )
    for reference, signals in reference_signals:
        path = f"references/{reference}.md"
        if path in library and any(signal in combined for signal in signals):
            return "software-engineering-library", path
    return "software-engineering-library", None


@pytest.mark.parametrize(
    ("test_name", "user_request", "evidence", "expected_reference"),
    [
        (
            "clean_architecture_boundary_change",
            "Architecture boundaries review for a dependency boundary between domain "
            "and infrastructure.",
            "Layer boundary direction is the risk.",
            "references/clean-architecture.md",
        ),
        (
            "domain_driven_design_bounded_context",
            "Domain modeling for billing and fulfillment bounded contexts.",
            "The model needs context translation rules.",
            "references/domain-driven-design.md",
        ),
        (
            "enterprise_patterns_repository_transaction",
            "Design a repository with unit-of-work handling for transactions.",
            "Persistence orchestration is central.",
            "references/enterprise-patterns.md",
        ),
        (
            "refactoring_code_smell",
            "Refactoring request for a code smell in pricing.py.",
            "Behavior must stay the same.",
            "references/refactoring.md",
        ),
        (
            "working_with_legacy_code_low_coverage",
            "Fix token expiration in auth.py.",
            "Analysis found low test coverage, old file age, and a characterization test need.",
            "references/working-with-legacy-code.md",
        ),
        (
            "data_intensive_schema_evolution",
            "Plan schema evolution for event ordering and data consistency.",
            "Consumers read old and new records during rollout.",
            "references/data-intensive-applications.md",
        ),
        (
            "release_it_resilience",
            "Review external API calls with queues, retries, timeout, and circuit "
            "breaker behavior.",
            "Production resilience is the primary risk.",
            "references/release-it.md",
        ),
        (
            "philosophy_of_software_design_interface_shape",
            "Software design depth review for module interface shape and complexity hiding.",
            "The public surface is shallow and leaks implementation details.",
            "references/philosophy-of-software-design.md",
        ),
    ],
)
def test_behavioral_request_routes_to_library_reference(
    test_name: str,
    user_request: str,
    evidence: str,
    expected_reference: str,
) -> None:
    selected_skill, selected_reference = _software_engineering_library_route(
        user_request,
        evidence,
    )

    assert selected_skill == "software-engineering-library", test_name
    assert selected_reference == expected_reference, test_name


def test_skill_description_prompt_exposes_only_umbrella_skill() -> None:
    skill_path = REPO_ROOT / ".claude" / "skills" / "software-engineering-library" / "SKILL.md"
    reference_path = skill_path.parent / "references" / "working-with-legacy-code.md"
    rule = eval_mod.parse_skill_reference(skill_path, reference_path)

    prompt = eval_mod.build_system_prompt("description", rule, "working-with-legacy-code")

    assert "software-engineering-library" in prompt
    assert "working-with-legacy-code" not in prompt
    assert "references/working-with-legacy-code.md" not in prompt


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
            (10, 0),
            ("4", 0),
            ("abc", 0),
            (None, 0),
            (True, 0),
            (3.7, 0),
            (float("inf"), 0),
        ],
    )
    def test_clamps_to_zero_to_five(self, value: object, expected: int):
        assert eval_mod._clamp_score(value) == expected

    @pytest.mark.parametrize("value", [float("inf"), float("-inf")])
    def test_non_finite_floats_fail_closed_to_zero(self, value: object):
        # json.loads accepts Infinity / -Infinity by default, so a judge can
        # emit a non-finite score. int(float("inf")) raises OverflowError, which
        # is not caught by the (TypeError, ValueError) handler and crashes the
        # evaluator. A non-finite score is garbage: it must clamp to 0 (fail
        # closed, lowering the activation average) rather than crash or inflate.
        assert eval_mod._clamp_score(value) == 0

    def test_nan_fails_closed_to_zero(self):
        # NaN reaches int() and raises ValueError today; lock the fail-closed 0.
        assert eval_mod._clamp_score(float("nan")) == 0


# ---------------------------------------------------------------------------
# skill_path resolution (activation measurement extended from rules to skills)
# ---------------------------------------------------------------------------


class TestSkillPathResolution:
    """skill_path validation mirrors rule_path: it must resolve under
    .claude/skills/ as a SKILL.md file, and rejects traversal, out-of-tree
    paths, and non-skill files so the `full` mechanism cannot exfiltrate
    arbitrary repository content to the API.
    """

    def test_accepts_valid_skill_under_skills_dir(self, tmp_path: Path):
        target = REPO_ROOT / ".claude" / "skills" / "security-scan" / "SKILL.md"
        if not target.is_file():
            pytest.skip("security-scan/SKILL.md not present in this checkout")
        f = tmp_path / "ok.json"
        f.write_text(
            json.dumps(
                {
                    "skill_path": ".claude/skills/security-scan/SKILL.md",
                    "skill_id": "security-scan",
                    "scenarios": [{"id": "S1", "input": "scan for injection"}],
                }
            ),
            encoding="utf-8",
        )
        result = eval_mod._load_scenarios_file(str(f))
        assert isinstance(result, tuple)
        _data, target_paths = result
        resolved, reference_path = target_paths
        assert resolved.is_file()
        assert resolved.name == "SKILL.md"
        assert reference_path is None

    def test_rejects_skill_path_outside_skills_dir(self, tmp_path: Path):
        f = tmp_path / "outside.json"
        f.write_text(
            json.dumps(
                {
                    "skill_path": ".claude/rules/universal.md",
                    "scenarios": [{"id": "S1", "input": "x"}],
                }
            ),
            encoding="utf-8",
        )
        assert eval_mod._load_scenarios_file(str(f)) == 2

    def test_rejects_skill_path_traversal(self, tmp_path: Path):
        f = tmp_path / "traversal.json"
        f.write_text(
            json.dumps(
                {
                    "skill_path": ".claude/skills/../../etc/passwd",
                    "scenarios": [{"id": "S1", "input": "x"}],
                }
            ),
            encoding="utf-8",
        )
        assert eval_mod._load_scenarios_file(str(f)) == 2

    def test_rejects_non_skill_md_filename(self, tmp_path: Path):
        # A file under skills that is not named SKILL.md is rejected on name,
        # before the is_file() check, so a crafted path cannot target other
        # skill-tree files even if they exist.
        f = tmp_path / "not_skill.json"
        f.write_text(
            json.dumps(
                {
                    "skill_path": ".claude/skills/security-scan/README.md",
                    "scenarios": [{"id": "S1", "input": "x"}],
                }
            ),
            encoding="utf-8",
        )
        assert eval_mod._load_scenarios_file(str(f)) == 2

    def test_rejects_missing_skill_file(self, tmp_path: Path):
        f = tmp_path / "missing.json"
        f.write_text(
            json.dumps(
                {
                    "skill_path": ".claude/skills/does-not-exist-xyz/SKILL.md",
                    "scenarios": [{"id": "S1", "input": "x"}],
                }
            ),
            encoding="utf-8",
        )
        assert eval_mod._load_scenarios_file(str(f)) == 2

    def test_rejects_both_rule_and_skill_path(self, tmp_path: Path):
        f = tmp_path / "both.json"
        f.write_text(
            json.dumps(
                {
                    "rule_path": ".claude/rules/universal.md",
                    "skill_path": ".claude/skills/security-scan/SKILL.md",
                    "scenarios": [{"id": "S1", "input": "x"}],
                }
            ),
            encoding="utf-8",
        )
        assert eval_mod._load_scenarios_file(str(f)) == 2

    def test_rejects_neither_rule_nor_skill_path(self, tmp_path: Path):
        f = tmp_path / "neither.json"
        f.write_text(
            json.dumps({"scenarios": [{"id": "S1", "input": "x"}]}),
            encoding="utf-8",
        )
        assert eval_mod._load_scenarios_file(str(f)) == 2

    def test_process_one_rule_derives_skill_id_from_dir(self):
        import types

        target = REPO_ROOT / ".claude" / "skills" / "security-scan" / "SKILL.md"
        if not target.is_file():
            pytest.skip("security-scan/SKILL.md not present in this checkout")
        scenarios_data = {"scenarios": [{"id": "S1", "input": "x"}]}
        args = types.SimpleNamespace(
            dry_run=True,
            model="m",
            seed=0,
            judge_repeats=eval_mod.DEFAULT_JUDGE_REPEATS,
            judge_reducer=eval_mod.DEFAULT_JUDGE_REDUCER,
        )
        rule_id, result, _n = eval_mod._process_one_rule(
            "key", scenarios_data, (target, None), args
        )
        assert rule_id == "security-scan"
        assert result is None


class TestJudgeSampleReduction:
    def _scenario(self) -> dict[str, object]:
        return {
            "id": "S1",
            "desc": "sample scenario",
            "input": "do the thing",
            "expected_gate": "apply-rule",
        }

    def _rule(self) -> dict[str, str]:
        return {"description": "desc", "body": "body"}

    def test_eval_one_scenario_persists_samples_and_median_scores(self, monkeypatch):
        monkeypatch.setattr(eval_mod, "RATE_LIMIT_SLEEP_SEC", 0)
        monkeypatch.setattr(eval_mod, "_call_api", lambda *args, **kwargs: "response")
        samples = [
            {
                "activation_score": 1,
                "citation_score": 1,
                "behavior_score": 1,
                "judge_failed": False,
            },
            {
                "activation_score": 5,
                "citation_score": 5,
                "behavior_score": 5,
                "judge_failed": False,
            },
            {
                "activation_score": 5,
                "citation_score": 5,
                "behavior_score": 5,
                "judge_failed": False,
            },
        ]
        calls: list[int] = []

        def fake_score(*args, **kwargs):
            sample = dict(samples[len(calls) % len(samples)])
            calls.append(1)
            return sample

        monkeypatch.setattr(eval_mod, "score_response", fake_score)

        result = eval_mod.eval_one_scenario(
            "key",
            self._rule(),
            "rule",
            self._scenario(),
            "model",
            dry_run=False,
            seed=10,
            judge_repeats=3,
            judge_reducer="median",
        )

        full = result["mechanisms"]["full"]
        assert full["judge_repeats"] == 3
        assert full["score_reducer"] == "median"
        assert len(full["score_samples"]) == 3
        assert full["scores"]["activation_score"] == 5
        assert full["scores"]["citation_score"] == 5
        assert full["scores"]["behavior_score"] == 5

    def test_eval_one_scenario_persists_failed_sample_without_reducing_it(self, monkeypatch):
        monkeypatch.setattr(eval_mod, "RATE_LIMIT_SLEEP_SEC", 0)
        monkeypatch.setattr(eval_mod, "_call_api", lambda *args, **kwargs: "response")
        samples = [
            {
                "activation_score": 5,
                "citation_score": 5,
                "behavior_score": 5,
                "judge_failed": False,
            },
            RuntimeError("judge timeout"),
            {
                "activation_score": 5,
                "citation_score": 5,
                "behavior_score": 5,
                "judge_failed": False,
            },
        ]
        calls: list[int] = []

        def fake_score(*args, **kwargs):
            value = samples[len(calls) % len(samples)]
            calls.append(1)
            if isinstance(value, RuntimeError):
                raise value
            return dict(value)

        monkeypatch.setattr(eval_mod, "score_response", fake_score)

        result = eval_mod.eval_one_scenario(
            "key",
            self._rule(),
            "rule",
            self._scenario(),
            "model",
            dry_run=False,
            seed=10,
            judge_repeats=3,
            judge_reducer="median",
        )

        full = result["mechanisms"]["full"]
        assert full["score_samples"][1]["judge_failed"] is True
        assert "judge API failure" in full["score_samples"][1]["reasoning"]
        assert full["scores"]["judge_failed"] is True

    def test_dry_run_counts_repeated_judge_calls(self, tmp_path, capsys):
        rule_path = REPO_ROOT / ".claude" / "rules" / "working-with-legacy-code.md"
        if not rule_path.is_file():
            pytest.skip("working-with-legacy-code.md not present in this checkout")
        scenarios_data = {
            "rule_id": "working-with-legacy-code",
            "scenarios": [self._scenario()],
        }
        args = type(
            "Args",
            (),
            {
                "dry_run": True,
                "model": "model",
                "seed": 10,
                "judge_repeats": 3,
                "judge_reducer": "median",
            },
        )()

        _rule_id, result, calls = eval_mod._process_one_rule("key", scenarios_data, rule_path, args)

        assert result is None
        assert calls == len(eval_mod.MECHANISMS) * 4

    def test_main_rejects_non_positive_judge_repeats(self, tmp_path, capsys):
        scenario_file = tmp_path / "scenarios.json"
        scenario_file.write_text(
            json.dumps(
                {
                    "rule_path": ".claude/rules/working-with-legacy-code.md",
                    "scenarios": [{"id": "S1", "input": "do the thing"}],
                }
            ),
            encoding="utf-8",
        )
        old_argv = sys.argv
        sys.argv = [
            "eval-rule-activation.py",
            "--scenarios",
            str(scenario_file),
            "--dry-run",
            "--judge-repeats",
            "0",
        ]
        try:
            code = eval_mod.main()
        finally:
            sys.argv = old_argv

        captured = capsys.readouterr()
        assert code == 2
        assert "--judge-repeats must be positive" in captured.err


# ---------------------------------------------------------------------------
# _extract_json_object: recovering judge scores from agentic CLI output
#
# The judge is told to answer with JSON only. The Anthropic path obeys, so a
# whole-string json.loads succeeds and the extractor is never consulted.
# Agentic CLI providers interleave tool-call traces and trailing prose around
# the answer, which made every such judge call score 0 and flip mechanism
# rankings. These cover the recovery path, the refusals, and the string-scan
# edges that a naive brace count gets wrong.
# ---------------------------------------------------------------------------


_JUDGE = '{"activation_score": 5, "citation_score": 4, "behavior_score": 5}'


def test_extract_json_object_returns_plain_object_unchanged():
    assert eval_mod._extract_json_object(_JUDGE) == _JUDGE


def _score_with_judge_text(monkeypatch: pytest.MonkeyPatch, judge_text: str) -> dict[str, Any]:
    """Run ``score_response`` against a fixed judge payload.

    Takes ``monkeypatch`` rather than assigning the attribute directly so the
    stub is torn down even when the call under test raises, and so the module
    attribute is set the way the rest of this file sets it.
    """
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_args, **_kwargs: judge_text)
    return eval_mod.score_response(
        "sk-test",
        {"input": "x", "expected_gate": "apply-rule"},
        "response",
    )


def test_extract_json_object_refuses_a_leading_cli_tool_trace():
    """A payload that leads with prose has no readable verdict.

    The searching version walked past this trace and returned the object after
    it. That search is what produced twelve fabrication defects, each one a
    disagreement about which candidate was the answer. The trace is also not a
    shape the harness still sees: ``_copilot_cli._read_session_transcript``
    reads ``assistant.message`` events, where tool calls sit in a sibling
    field. Refusing costs one of three judge samples and is recorded as a
    failure; searching cost a published number and was recorded as nothing.
    """
    text = (
        "\u25cf List working directory contents (shell)\n"
        "  \u2502 ls -la /tmp/eval-copilot-abc 2>&1 | head -50\n"
        "  \u2514 4 lines\u2026\n\n" + _JUDGE
    )
    assert eval_mod._extract_json_object(text) is None


def test_extract_json_object_drops_trailing_prose():
    assert eval_mod._extract_json_object(_JUDGE + "\n\nLet me know if you want more.") == _JUDGE


def test_extract_json_object_handles_nested_objects():
    """A nested object must not end the scan early, and a tail must not extend it."""
    text = '{"a": {"b": 1}, "c": 2} tail'
    assert eval_mod._extract_json_object(text) == '{"a": {"b": 1}, "c": 2}'


def test_extract_json_object_refuses_when_the_payload_leads_with_prose():
    """Offset zero is the whole rule. One leading word is enough to refuse."""
    assert eval_mod._extract_json_object('noise {"a": {"b": 1}, "c": 2}') is None


def test_extract_json_object_returns_none_without_any_brace():
    assert eval_mod._extract_json_object("I cannot score this response.") is None


def test_extract_json_object_returns_none_on_unbalanced_object():
    assert eval_mod._extract_json_object('{"activation_score": 5') is None


def test_a_leading_tool_result_is_refused_rather_than_searched_past(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The verdict is never taken from past a leading object.

    The searching version checked each candidate against the score shape and
    returned the one that matched, so it walked past this trace and graded the
    object after it. Now the leading object is the only one read; it fails the
    caller's shape check, salvage finds no score fields in it, and the sample
    is refused. No score is produced from anywhere else in the payload.
    """
    text = '{"command": "ls", "exit_code": 0}\n\nHere is my grade:\n' + _JUDGE

    assert eval_mod._extract_json_object(text) == '{"command": "ls", "exit_code": 0}'
    assert eval_mod._salvage_scores(text) is None
    assert _score_with_judge_text(monkeypatch, text)["judge_failed"] is True


def test_extract_json_object_refuses_an_unparseable_leading_object():
    """A broken leading object ends the read. It does not start a search."""
    text = '{"broken": }\n' + _JUDGE

    assert eval_mod._extract_json_object(text) is None


def test_extract_json_object_refuses_a_partial_object_followed_by_a_full_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A near-miss must not win, and the search that found it is gone.

    Two objects each naming ``activation_score`` is exactly the ambiguity the
    name count refuses, so the extractor declines before shape is considered.
    The searching version instead picked the second, which is the same move
    that let a quoted exemplar outrank the judge's own answer.
    """
    partial = '{"activation_score": 5, "citation_score": 4}'
    text = partial + "\n\n" + _JUDGE

    assert eval_mod._extract_json_object(text) is None
    assert _score_with_judge_text(monkeypatch, text)["judge_failed"] is True


def test_extract_json_object_returns_a_partial_object_for_the_caller_to_refuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The extractor no longer judges shape; the caller still does.

    With no second copy of a score field there is no ambiguity, so the leading
    object is returned. It is not a verdict, and the caller's existing shape
    check is what says so. The visible outcome is unchanged.
    """
    partial = '{"activation_score": 5, "citation_score": 4}'
    text = partial + "\n\nthat is all"

    assert eval_mod._extract_json_object(text) == partial
    assert _score_with_judge_text(monkeypatch, text)["judge_failed"] is True


def test_extract_json_object_falls_back_to_the_first_parseable_object():
    """No verdict anywhere still returns content, so the caller can report a
    shape error against what the judge actually said rather than a bare parse
    failure."""
    text = '{"refusal": "cannot grade"}\n{"also": "not a verdict"}'

    assert eval_mod._extract_json_object(text) == '{"refusal": "cannot grade"}'


def test_a_balanced_object_scan_does_not_reenter_nested_ones():
    """Coverage moved here when ``_iter_json_objects`` was deleted.

    The walker existed only to feed the candidate search. With the search
    gone, the property that still matters is that a nested object does not
    terminate the scan of the one that contains it.
    """
    text = '{"x": {"y": 1}} b {"z": 2} c'

    assert eval_mod._scan_balanced_object(text, 0) == len('{"x": {"y": 1}}')


# ---------------------------------------------------------------------------
# _salvage_scores / _judge_parse_failure: an unparseable `reasoning` field must
# not discard the three numbers the eval actually scores on.
#
# Observed in production: 24 of 144 Opus judge samples were thrown away, every
# one of them carrying its scores in plain sight. The judge quotes the response
# it is grading, and a malformed `reasoning` string invalidates the whole
# object. The loss lands entirely in Opus-labelled positive-scenario cells, so
# it was not random with respect to the comparison being made.
# ---------------------------------------------------------------------------


_UNESCAPED_QUOTE_JUDGE = (
    '{"activation_score": 5, "citation_score": 4, "behavior_score": 5, '
    '"reasoning": "rejected it as "a rename" rather than a layer"}'
)


def test_score_response_refuses_a_malformed_verdict_behind_a_tool_trace(monkeypatch):
    """A verdict that does not lead the payload is discarded, not salvaged.

    Salvage used to search for the right object among several. Seven review
    rounds produced eleven ways for that search to pick the wrong one, so the
    anchor is now fixed at the start of the payload. A leading tool trace is
    the shape that costs: the judge's real verdict is right there, unread.

    Losing it discards one of three samples. Reading it required a search, and
    the search is what returned a quoted exemplar as the judge's answer.
    """
    monkeypatch.setattr(
        eval_mod,
        "_call_api",
        lambda *_args, **_kwargs: (
            '{"activation_score": 1, "command": "ls"}\n' + _UNESCAPED_QUOTE_JUDGE
        ),
    )

    result = eval_mod.score_response(
        "sk-test",
        {"input": "x", "expected_gate": "apply-rule"},
        "response",
    )

    assert result["judge_failed"] is True


_SECOND_VERDICT_PAYLOADS = [
    pytest.param(
        json.dumps(
            {
                "activation_score": 5,
                "citation_score": 5,
                "behavior_score": 5,
                "reasoning": "first pass",
                "revised": {
                    "activation_score": 1,
                    "citation_score": 1,
                    "behavior_score": 1,
                    "reasoning": "on reflection",
                },
            }
        ),
        id="nested-correction",
    ),
    pytest.param(
        json.dumps(
            {
                "activation_score": 5,
                "citation_score": 5,
                "behavior_score": 5,
                "alternatives": [
                    {
                        "activation_score": 1,
                        "citation_score": 2,
                        "behavior_score": 3,
                    }
                ],
            }
        ),
        id="verdict-in-a-list",
    ),
    pytest.param(
        json.dumps(
            {
                "activation_score": 5,
                "citation_score": 5,
                "behavior_score": 5,
                "reasoning": (
                    'earlier I wrote {"activation_score": 1, '
                    '"citation_score": 1, "behavior_score": 1}'
                ),
            }
        ),
        id="verdict-quoted-inside-a-string",
    ),
    pytest.param(
        json.dumps(
            {
                "activation_score": 1,
                "citation_score": 1,
                "behavior_score": 1,
                "meta": {
                    "audit": {
                        "final": {
                            "activation_score": 5,
                            "citation_score": 5,
                            "behavior_score": 5,
                        }
                    }
                },
            }
        ),
        id="verdict-nested-three-deep",
    ),
]


@pytest.mark.parametrize("payload", _SECOND_VERDICT_PAYLOADS)
def test_valid_json_carrying_a_second_verdict_refuses(monkeypatch, payload):
    """The seventeenth defect: a clean parse is not proof of a single answer.

    Every payload here is valid JSON, so ``_strict_json_loads`` accepted it
    and the result returned through the clean-parse branch. That branch sets
    no ``judge_salvaged`` marker, so the guess was not merely wrong, it was
    unauditable, which the recovery-path defects at least were not.

    Nesting is why the parse proves nothing. A second verdict can sit inside
    the first as a member, a list element, or a quoted string, and the
    grammar is satisfied either way. ``_reject_duplicate_keys`` does not see
    these because a nested key is not a repeated one.
    """
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_args, **_kwargs: payload)

    result = eval_mod.score_response(
        "sk-test",
        {"input": "x", "expected_gate": "apply-rule"},
        "response",
    )

    assert result["judge_failed"] is True
    assert result["activation_score"] == 0
    assert result["citation_score"] == 0
    assert result["behavior_score"] == 0
    assert "judge_salvaged" not in result


def test_the_ambiguity_refusal_names_itself_rather_than_a_parse_error(monkeypatch):
    """Pins where the guard runs, not just that it runs.

    The guard sits before the parse so every path inherits it, including one
    nobody has written yet. Routing an ambiguous payload through
    ``_judge_parse_failure`` would also refuse it today, but only because
    ``_salvage_scores`` happens to carry its own copy of the guard. Depending
    on a downstream helper to do the refusing is the coupling that produced
    this defect; asserting on the reason string is what stops a later edit
    from quietly reintroducing it.
    """
    payload = json.dumps(
        {
            "activation_score": 5,
            "citation_score": 5,
            "behavior_score": 5,
            "revised": {
                "activation_score": 1,
                "citation_score": 1,
                "behavior_score": 1,
            },
        }
    )
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_args, **_kwargs: payload)

    result = eval_mod.score_response(
        "sk-test",
        {"input": "x", "expected_gate": "apply-rule"},
        "response",
    )

    assert result["reasoning"].startswith("ambiguous judge output")
    assert "judge parse error" not in result["reasoning"]


def test_a_single_verdict_beside_unrelated_nesting_still_parses(monkeypatch):
    """The guard must cost nothing on the payloads the judge actually sends.

    A refusal is the safe direction but it is not free: it discards one of
    three judge samples. This is the negative control that keeps the guard
    from being tightened into refusing every structured answer, which would
    drain samples without any fabrication to show for it.
    """
    payload = json.dumps(
        {
            "activation_score": 4,
            "citation_score": 3,
            "behavior_score": 2,
            "reasoning": "the rule fired and was cited",
            "evidence": {"quoted_line": 12, "tags": ["cited", "applied"]},
        }
    )
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_args, **_kwargs: payload)

    result = eval_mod.score_response(
        "sk-test",
        {"input": "x", "expected_gate": "apply-rule"},
        "response",
    )

    assert result["judge_failed"] is False
    assert result["activation_score"] == 4
    assert result["citation_score"] == 3
    assert result["behavior_score"] == 2


# A judge that writes an em-dash, a curly quote, or an accented name emits a
# unicode escape, because JSON encoders default to ASCII output. These are the
# healthy payloads that the raw-text guard refused for prose, and they are the
# regression tests for that false refusal.
_UNICODE_ESCAPE_BODY = (
    '{"activation_score": 4, "citation_score": 3, "behavior_score": 2,'
    ' "reasoning": "the rule fired \\u2014 and was cited \\u201cexactly\\u201d"}'
)


@pytest.mark.parametrize(
    ("payload", "label"),
    [
        (_UNICODE_ESCAPE_BODY, "plain"),
        (f"```json\n{_UNICODE_ESCAPE_BODY}\n```", "fenced"),
    ],
    ids=["plain", "fenced"],
)
def test_a_unicode_escape_in_reasoning_is_not_an_ambiguity(monkeypatch, payload, label):
    """A verdict whose prose carries an escape must score, not be refused.

    The raw-text guard refuses any payload containing ``\\u``, because a field
    name spelled with an escape would slip a count of raw key shapes. On a
    payload that failed to parse that blanket costs nothing. On one that parses
    it discards a healthy verdict for the sole reason that the judge used a
    dash, and dashes are ordinary.

    Both spellings are covered because they reach the check by different
    routes: the plain body parses whole, the fenced one only after unwrapping.
    """
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_args, **_kwargs: payload)

    result = eval_mod.score_response(
        "sk-test",
        {"input": "x", "expected_gate": "apply-rule"},
        "response",
    )

    assert result["judge_failed"] is False, label
    assert result["activation_score"] == 4
    assert result["citation_score"] == 3
    assert result["behavior_score"] == 2


def test_a_second_verdict_after_the_object_is_still_refused(monkeypatch):
    """Narrowing the raw guard must not open the hole it was written to close.

    The guard now yields to the exact structural check only when the object is
    the whole payload. When text follows it, that text is never parsed, so a
    second verdict could hide there and only the raw count can see it. This is
    the control that proves the narrowing is conditional rather than a removal.
    """
    payload = (
        '{"activation_score": 1, "citation_score": 1, "behavior_score": 1,'
        ' "reasoning": "first"}\n'
        '{"activation_score": 5, "citation_score": 5, "behavior_score": 5,'
        ' "reasoning": "second"}'
    )
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_args, **_kwargs: payload)

    result = eval_mod.score_response(
        "sk-test",
        {"input": "x", "expected_gate": "apply-rule"},
        "response",
    )

    assert result["judge_failed"] is True
    assert result["activation_score"] == 0


def test_count_score_bearing_objects_finds_every_depth():
    count = eval_mod._count_score_bearing_objects
    verdict = {"activation_score": 1, "citation_score": 1, "behavior_score": 1}

    assert count({}) == 0
    assert count({"reasoning": "none here"}) == 0
    assert count(verdict) == 1
    assert count({**verdict, "revised": dict(verdict)}) == 2
    assert count({**verdict, "alts": [dict(verdict), dict(verdict)]}) == 3
    assert count({"meta": {"audit": {"final": dict(verdict)}}}) == 1


def test_a_verdict_serialized_into_a_string_is_two_verdicts():
    """A quoted verdict is a second candidate, so the payload is ambiguous.

    The structural count cannot see it, because a string is one value however
    much JSON it spells. The string check is what covers this, and it runs on
    decoded text so an escape in ordinary prose does not trip it.

    Prose that merely mentions a field name refuses too, and that is the
    deliberate outcome of round 22 rather than an accident. ``Final
    activation_score: 1, not 5.`` published two fabricated scores, and no
    bounded rule separates it from ``the activation_score was low``: the only
    difference is a separator and a value, and enumerating those is what broke
    rounds 19, 20, 21, and 22 in turn. So the whole class refuses. The cost was
    measured, not assumed: across the 264 nested reasoning values in the 288
    archived payloads, zero name a score field, so this refuses no sample a
    real judge has produced. The second assertion is the control that keeps
    this honest, because a check that refused everything would pass the first
    and third arms too.
    """
    names_two = eval_mod._parsed_names_two_verdicts
    verdict = {"activation_score": 1, "citation_score": 1, "behavior_score": 1}

    assert names_two({**verdict, "reasoning": "the activation_score was low"}) is True
    assert names_two({**verdict, "reasoning": "fired \u2014 and cited"}) is False
    assert names_two({**verdict, "reasoning": 'was {"activation_score": 5}'}) is True


def test_ordinary_backslash_prose_is_not_refused(monkeypatch):
    """Peeling further layers must not turn a backslash into an accusation.

    ``\\b`` is a JSON escape, so ``C:\\Users\\bob`` survives a parse still
    carrying one, and a check that refuses any layer with decodable content
    left would refuse a judge who merely quoted a Windows path or a regex.
    That refusal is invisible in the published median, which is exactly why it
    has to be tested rather than reasoned about: only the truncated walk is a
    reason to refuse, not the presence of an escape.
    """
    for label, reasoning in {
        "windows path": r"the rule at C:\Users\bob\rules.md fired",
        "regex": r"matched \d+ in the diff",
        "newline": "line one\nline two",
        "tab": "col\tcol",
    }.items():
        payload = json.dumps(
            {
                "activation_score": 5,
                "citation_score": 4,
                "behavior_score": 5,
                "reasoning": reasoning,
            }
        )
        monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, _p=payload, **_k: _p)
        result = eval_mod.score_response(
            "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
        )
        assert result["judge_failed"] is False, f"{label} was refused"
        assert result["activation_score"] == 5


def test_a_twice_serialized_verdict_is_still_two_verdicts(monkeypatch):
    """Two genuine serialization layers double the backslash, not the escape.

    A decoder that matches only ``\\uXXXX`` consumes the second backslash of
    ``\\\\u0061`` and leaves ``\\activation_score``, which no further peel can
    decode and no field pattern can match. This is what ordinary nesting
    produces: ``json.dumps`` applied twice, not a crafted string.
    """
    inner = r'{"\u0061ctivation_score":5,"\u0063itation_score":5,"\u0062ehavior_score":5}'
    payload = json.dumps(
        {
            "activation_score": 1,
            "citation_score": 1,
            "behavior_score": 1,
            "reasoning": "Corrected verdict: " + json.dumps(inner),
        }
    )
    buried = json.loads(payload)["reasoning"].removeprefix("Corrected verdict: ")
    assert json.loads(json.loads(buried)) == {
        "activation_score": 5,
        "citation_score": 5,
        "behavior_score": 5,
    }

    for label, text in {"plain": payload, "fenced": f"```json\n{payload}\n```"}.items():
        monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, _p=text, **_k: _p)
        result = eval_mod.score_response(
            "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
        )
        assert result["judge_failed"] is True, f"{label} accepted a twice-serialized verdict"


def test_a_non_integer_score_token_is_not_an_agreement(monkeypatch):
    """Equality must be established on the whole token, not a leading integer.

    Reading ``1.5`` as ``1`` makes a contradiction look like a restatement of
    the filed ``1``, which is the exact direction that publishes a fabricated
    number. Exponent form does the same thing with ``1e1``. Neither is
    comparable to a filed integer, so both are refused rather than equated.
    """
    for label, values in {
        "float": ("1.5", "4.5", "5.0"),
        "exponent": ("1e1", "4e1", "5e1"),
        "quoted": ('\\"1\\"', '\\"4\\"', '\\"5\\"'),
    }.items():
        payload = (
            '{"activation_score":1,"citation_score":4,"behavior_score":5,'
            '"reasoning":"Corrected verdict: {'
            f'\\"activation_score\\":{values[0]},'
            f'\\"citation_score\\":{values[1]},'
            f'\\"behavior_score\\":{values[2]}'
            '}"}'
        )
        monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, _p=payload, **_k: _p)
        result = eval_mod.score_response(
            "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
        )
        assert result["judge_failed"] is True, f"{label} was read as an agreement"


def test_an_exhausted_decode_budget_refuses_rather_than_accepts(monkeypatch):
    """The peel bound must fail closed; an unread remainder is not agreement.

    Accepting when the budget runs out accepts precisely the payload the check
    failed to read, so the bound would become the bypass.

    The payload carries no score field at all, so the contradiction arm cannot
    fire and the refusal is attributable to truncation alone. An earlier
    version of this test buried a real field past the bound and kept passing
    when the bound was raised, because the field then decoded into view and
    refused as a contradiction: it asserted the right outcome for the wrong
    reason. A run of backslashes halves per layer, so 512 is the smallest
    power of two that outlasts the budget, and the companion test below pins
    the other side of that boundary.
    """
    payload = json.dumps(
        {
            "activation_score": 5,
            "citation_score": 4,
            "behavior_score": 5,
            "reasoning": "\\" * 512 + " is a lot of escaping",
        }
    )
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, **_k: payload)

    result = eval_mod.score_response(
        "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
    )

    assert result["judge_failed"] is True


def test_backslash_prose_within_the_budget_is_not_refused(monkeypatch):
    """Escaping a judge can plausibly write must decode, not exhaust the bound.

    This is the other side of the boundary the test above pins. At a bound of
    three layers a judge discussing regex escaping was refused over a
    remainder that held no score field, which is a lost sample charged to the
    payload rather than to the checker. 256 backslashes is far past anything
    prose produces and still resolves inside the budget.
    """
    payload = json.dumps(
        {
            "activation_score": 5,
            "citation_score": 4,
            "behavior_score": 5,
            "reasoning": "The pattern needs " + "\\" * 256 + " before the class",
        }
    )
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, **_k: payload)

    result = eval_mod.score_response(
        "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
    )

    assert result["judge_failed"] is False
    assert result["activation_score"] == 5


def test_an_arithmetic_expression_beside_an_equal_token_is_not_agreement(
    monkeypatch,
):
    """``5 - 1`` beside a filed 5 states 4, and the leading token cannot say so.

    The value token stops at whitespace, so the capture is ``5``, which equals
    the filed score exactly. Reading that as agreement publishes a 5 the judge
    corrected to 4, with nothing in the record marking it: the worst outcome
    available to this check, since a refusal is visible through the sample
    count and a fabrication is not.
    """
    payload = json.dumps(
        {
            "activation_score": 5,
            "citation_score": 4,
            "behavior_score": 5,
            "reasoning": 'Corrected: {"activation_score": 5 - 1, "citation_score": 4}',
        }
    )
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, **_k: payload)

    result = eval_mod.score_response(
        "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
    )

    assert result["judge_failed"] is True


def test_a_value_token_past_the_integer_conversion_limit_does_not_raise(
    monkeypatch,
):
    """A long digit run must refuse, not end the run.

    CPython refuses to convert an integer literal longer than 4300 digits,
    raising ``ValueError``. ``eval_one_scenario`` catches ``RuntimeError``, so
    converting before comparing let a single judge response abort every
    remaining scenario. Comparing decimal spellings never converts, so length
    is just inequality.
    """
    payload = json.dumps(
        {
            "activation_score": 5,
            "citation_score": 4,
            "behavior_score": 5,
            "reasoning": 'Restated "activation_score": ' + "9" * 4400,
        }
    )
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, **_k: payload)

    result = eval_mod.score_response(
        "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
    )

    assert result["judge_failed"] is True




def test_a_leading_zero_spelling_is_not_an_exact_restatement(monkeypatch):
    """``05`` is not a JSON integer, so it cannot establish equality exactly.

    Converting first accepted it as 5. The claim this check makes is equality
    of spelling, and ``05`` does not spell the filed value; refusing costs a
    visible sample, while accepting asserts an exactness that was not tested.
    """
    payload = json.dumps(
        {
            "activation_score": 5,
            "citation_score": 4,
            "behavior_score": 5,
            "reasoning": 'Restated "activation_score": 05',
        }
    )
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, **_k: payload)

    result = eval_mod.score_response(
        "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
    )

    assert result["judge_failed"] is True


def test_a_restated_score_field_is_uncomparable_and_refused(monkeypatch):
    """Naming a score field in a decoded string makes the payload ambiguous.

    This test used to assert the opposite, that a judge writing
    ``I assigned "activation_score": 5 because ...`` beside a filed 5 had
    restated its answer and should score. The argument was that a dropped
    sample moves a published median exactly as a fabricated one does, so an
    over-eager refusal is a defect in the same family as an over-eager accept.
    That argument still holds. What changed is the evidence that the
    restatement can be recognised at all.

    Three rounds of adversarial review broke three successive proofs of
    equality. Comparing the value token accepted ``5 - 1``. Naming the
    operators that could follow accepted ``5 ^ 1`` and ``5 if False else 1``.
    Requiring a second digit accepted ``5 - True`` and ``5 minus one``, and
    refused ``5 because all 3 concepts were present``, which is ordinary
    judge prose. Each proof was lexical, and lexical equality over prose is
    not equality.

    The cost of giving up is measured, not assumed. The archive stores a raw
    payload for all 288 samples, successes included, and parsing all of them
    yields 264 nested reasoning values. Zero name a score field, so this
    refuses no sample any real judge in the archive has produced.
    """
    for reasoning in (
        'I assigned "activation_score": 5 because the rule was applied.',
        'I set "activation_score": 5 (the rule clearly applied)',
        'I set "activation_score": 5. The rule fired throughout.',
        'Restating: {"activation_score":5,"citation_score":4,"behavior_score":5}',
        # Round 22: refusing only a *quoted* name left the unquoted dialects
        # open. JSON5 permits a bare identifier key, Python spells the same
        # verdict with `=`, and prose needs no bracket at all. Enumerating
        # quoting styles and separators is the same unbounded chase that broke
        # rounds 19 through 21, so the name alone is what refuses.
        "Corrected: {activation_score:1,citation_score:1,behavior_score:1}",
        "Corrected: dict(activation_score=1, citation_score=1)",
        "Final activation_score: 1, not 5.",
        "On reflection my activation_score was too generous.",
    ):
        payload = json.dumps(
            {
                "activation_score": 5,
                "citation_score": 4,
                "behavior_score": 5,
                "reasoning": reasoning,
            }
        )
        monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, _p=payload, **_k: _p)

        result = eval_mod.score_response(
            "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
        )

        assert result["judge_failed"] is True, reasoning


def test_no_written_form_of_a_second_verdict_is_accepted(monkeypatch):
    """The forms that broke each previous proof, kept as a regression set.

    Every entry here published a fabricated score under some earlier version
    of this check. They are grouped because the fix is one rule rather than
    one clause per form: none of them is recognised, so none of them is
    accepted. An operand need not be a digit (``True``, ``len([None])``,
    ``one``), punctuation is not always punctuation (``5!`` is a factorial),
    and a delimiter can arrive before the correction does
    (``5, but corrected it to 1``).
    """
    for expression in (
        "5 - 1",
        "5-1",
        "5 ^ 1",
        "5 & 1",
        "5 << 1",
        "5 and 0",
        "5 if False else 1",
        "5 ? 0 : 1",
        "5 - True",
        "5 ^ True",
        "5 - len([None])",
        "5 if False else True",
        "5 minus one",
        "5!",
        "5, but corrected it to 1.",
        "5 \\\n- True",
        "05",
        "1.5",
    ):
        payload = json.dumps(
            {
                "activation_score": 5,
                "citation_score": 4,
                "behavior_score": 5,
                "reasoning": f'Corrected: "activation_score": {expression}',
            }
        )
        monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, _p=payload, **_k: _p)

        result = eval_mod.score_response(
            "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
        )

        assert result["judge_failed"] is True, expression


def test_reasoning_that_names_no_score_field_still_scores(monkeypatch):
    """The refusal must key on the field name, not on prose or on digits.

    Without this, "refuse anything ambiguous" could quietly widen until it
    dropped every judge who wrote a number in a sentence, and the sample loss
    would show up only as a smaller denominator. These are the payloads the
    check has to keep letting through.
    """
    for reasoning in (
        "The rule was applied and cited, scoring 5 on the 1-5 scale.",
        "All 3 expected concepts were present throughout the response.",
        "Rung 1 was followed, then rung 2; the citation appears at line 40.",
        "No score field is named here at all.",
    ):
        payload = json.dumps(
            {
                "activation_score": 5,
                "citation_score": 4,
                "behavior_score": 5,
                "reasoning": reasoning,
            }
        )
        monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, _p=payload, **_k: _p)

        result = eval_mod.score_response(
            "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
        )

        assert result["judge_failed"] is False, reasoning
        assert (
            result["activation_score"],
            result["citation_score"],
            result["behavior_score"],
        ) == (5, 4, 5), reasoning


def test_a_nested_verdict_disagreeing_on_a_later_field_is_still_detected(
    monkeypatch,
):
    """Every named field must stay discoverable, not just the first.

    A greedy tail group in the field pattern consumed the rest of the layer,
    so ``finditer`` returned one match per layer and the fields after it were
    never examined. A judge restating ``5/1/1`` beside a filed ``5/4/5`` then
    agreed on ``activation_score`` and published, because the two fields that
    disagreed were inside the text the first match had already eaten. The
    guard checked exactly the field least likely to differ.
    """
    payload = json.dumps(
        {
            "activation_score": 5,
            "citation_score": 4,
            "behavior_score": 5,
            "reasoning": (
                'Corrected verdict: {"activation_score":5,'
                '"citation_score":1,"behavior_score":1}'
            ),
        }
    )
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, **_k: payload)

    assert len(eval_mod._SCORE_FIELDS) == len(
        list(
            eval_mod._NAMED_SCORE_FIELD_RE.finditer(
                '{"activation_score":5,"citation_score":1,"behavior_score":1}'
            )
        )
    )

    result = eval_mod.score_response(
        "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
    )

    assert result["judge_failed"] is True










def test_the_ambiguity_walkers_terminate_on_a_self_referential_object():
    """JSON cannot build a cycle, but the private helpers should still be total.

    Both walkers are reachable from any caller holding a parsed-looking object,
    and a walk that hangs is worse than one that answers, so identity tracking
    costs one set membership per container to remove the failure mode entirely.

    The exact yielded set is the assertion because a finite set is the direct
    evidence of termination, and this one carries a key and a value so both
    branches are shown to run. ``activation_score`` is absent by design: it is
    a schema slot, and ``_string_values`` skips those keys so a healthy payload
    does not refuse itself. That skip has its own test.
    """
    cyclic: dict[str, Any] = {"activation_score": 1, "note": "cited"}
    cyclic["self"] = cyclic
    listish: list[Any] = []
    listish.append(listish)

    assert eval_mod._parsed_names_two_verdicts(cyclic) is False
    assert eval_mod._count_score_bearing_objects(listish) == 0
    assert set(eval_mod._string_values(cyclic)) == {"note", "cited", "self"}


def test_a_verdict_spelled_with_unicode_escapes_is_still_two_verdicts(monkeypatch):
    """A parse decodes one layer of escaping, so a verdict can hide under two.

    ``{\\"\\u0061ctivation_score\\":5}`` inside ``reasoning`` survives the parse
    as literal backslash-u text, which no pattern for ``"activation_score"``
    matches. The payload plainly carries a corrected 5/5/5 next to a filed
    1/1/1, and both parsed-region paths published the 1/1/1 unchallenged.

    Peeling further escape layers asks what the string says once fully decoded.
    The control is the shape that motivated dropping the old raw guard: JSON
    encoders default to ASCII, so an em-dash in prose arrives as an escape and
    is decoded by the parse itself, leaving nothing for this to trip on.
    """
    payload = (
        '{"activation_score": 1, "citation_score": 1, "behavior_score": 1,'
        ' "reasoning": "Corrected verdict:'
        ' {\\"\\\\u0061ctivation_score\\":5,\\"\\\\u0063itation_score\\":5,'
        '\\"\\\\u0062ehavior_score\\":5}"}'
    )
    assert json.loads(json.loads(payload)["reasoning"].removeprefix("Corrected verdict: ")) == {
        "activation_score": 5,
        "citation_score": 5,
        "behavior_score": 5,
    }

    for label, text in {
        "plain": payload,
        "fenced": f"```json\n{payload}\n```",
        "tail": f"{payload}\ntail",
    }.items():
        monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, _p=text, **_k: _p)
        result = eval_mod.score_response(
            "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
        )
        assert result["judge_failed"] is True, f"{label} accepted an escaped verdict"

    unambiguous = json.dumps(
        {
            "activation_score": 5,
            "citation_score": 4,
            "behavior_score": 5,
            "reasoning": "the rule fired \u2014 and the response cited it",
        }
    )
    assert "\\u" in unambiguous
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, **_k: unambiguous)
    control = eval_mod.score_response(
        "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
    )
    assert control["judge_failed"] is False
    assert control["activation_score"] == 5




def test_a_healthy_payload_with_deep_nesting_still_scores(monkeypatch):
    """The ambiguity walkers must not turn valid nesting into an API failure.

    The JSON decoder's C scanner accepts far deeper input than a recursive
    Python walk survives, so the walkers, not the parse, were the binding
    constraint. ``RecursionError`` subclasses ``RuntimeError``, which the
    scoring call site catches as a transport error, so a healthy verdict
    carrying a deeply nested member was filed as a judge API failure and
    dropped. Both walkers are iterative for that reason.
    """
    payload = (
        '{"activation_score":5,"citation_score":4,"behavior_score":5,'
        '"reasoning":"ok","meta":' + "[" * 996 + "0" + "]" * 996 + "}"
    )
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, **_k: payload)

    result = eval_mod.score_response(
        "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
    )

    assert result["judge_failed"] is False
    assert (
        result["activation_score"],
        result["citation_score"],
        result["behavior_score"],
    ) == (5, 4, 5)


def test_a_verdict_hidden_in_an_object_key_is_two_verdicts(monkeypatch):
    """An object key is a string, so a verdict can hide on the left of a colon.

    This is a regression guard on the check that replaced the old raw-text
    scan. The scan read the whole payload, so it saw a verdict wherever it sat;
    the structural replacement first walked only ``dict.values()`` and let this
    shape through as a clean 1/1/1. That made the replacement weaker than what
    it replaced, on precisely the case it exists to stop.

    The control at the end is the reason the walk cannot simply be widened back
    into a blanket text scan: a legitimate verdict whose prose merely mentions
    scoring must still parse.
    """
    hidden = json.dumps(
        {
            "activation_score": 1,
            "citation_score": 1,
            "behavior_score": 1,
            "reasoning": "first",
            'corrected verdict: {"activation_score": 5, "citation_score": 5,'
            ' "behavior_score": 5}': True,
        }
    )
    shapes = {
        "plain": hidden,
        "fenced": f"```json\n{hidden}\n```",
        "tail": f"{hidden}\nalso: 5/5/5",
    }
    for label, payload in shapes.items():
        monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, _p=payload, **_k: _p)
        result = eval_mod.score_response(
            "sk-test",
            {"input": "x", "expected_gate": "apply-rule"},
            "response",
        )
        assert result["judge_failed"] is True, f"{label} shape accepted a hidden verdict"

    unambiguous = json.dumps(
        {
            "activation_score": 5,
            "citation_score": 4,
            "behavior_score": 5,
            "reasoning": "the rule fired \u2014 and the response cited it",
        }
    )
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, **_k: unambiguous)
    control = eval_mod.score_response(
        "sk-test",
        {"input": "x", "expected_gate": "apply-rule"},
        "response",
    )
    assert control["judge_failed"] is False
    assert control["activation_score"] == 5
    assert control["citation_score"] == 4


def test_adjacent_string_literals_are_a_known_undetected_shape(monkeypatch):
    """Record the limit that no textual check closes, so it stays measured.

    A second verdict spelled so the field name is never a contiguous substring
    evades any text scan; Python's adjacent string literal concatenation is one
    such spelling and the encoding space is open, so enumerating spellings does
    not converge. This asserts today's behavior rather than a fix: the top
    level is the schema's answer slot, so the filed verdict wins over prose.

    Zero of the 264 recovered judge payloads carry this shape. If that ever
    changes, this test is where the argument gets reopened.
    """
    payload = (
        '{"activation_score": 1, "citation_score": 1, "behavior_score": 1,'
        " \"reasoning\": \"corrected: {'activation' '_score': 5}\"}"
    )
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_args, **_kwargs: payload)

    result = eval_mod.score_response(
        "sk-test",
        {"input": "x", "expected_gate": "apply-rule"},
        "response",
    )

    assert result["judge_failed"] is False
    assert result["activation_score"] == 1


def test_judge_parse_failure_does_not_combine_partial_objects():
    result = eval_mod._judge_parse_failure(
        '{"activation_score": 5}\n{"citation_score": 4, "behavior_score": 3}',
        "parse error",
    )

    assert result["judge_failed"] is True


def test_salvage_refuses_when_reasoning_prose_names_a_score_field():
    """Naming a score field twice is refused, wherever the second name sits.

    ``_scan_root_members`` halts at ``reasoning`` because string boundaries
    past an unescaped quote are unknowable, which left it blind to a duplicate
    key placed after that halt:

        {"activation_score": 1, ..., "reasoning": "bad "quote",
         "activation_score": 5, ...}

    It salvaged ``1`` where a lenient parse says ``5``. Counting raw names is
    the only check that sees the tail without trusting it, and it cannot tell
    a duplicate key from prose quoting a field name, so both are refused.

    The cost is measured, not assumed: all 24 archived recoveries name each
    field once and are unaffected.
    """
    assert (
        eval_mod._salvage_scores(
            '{"activation_score": 4, "citation_score": 3, "behavior_score": 5, '
            '"reasoning": "the rubric says "activation_score": 1"}'
        )
        is None
    )


def test_salvage_refuses_a_duplicate_score_field_after_reasoning():
    """The shape the raw-name count exists to catch."""
    assert (
        eval_mod._salvage_scores(
            '{"activation_score": 1, "citation_score": 1, "behavior_score": 1, '
            '"reasoning": "bad "quote", "activation_score": 5, '
            '"citation_score": 5, "behavior_score": 5}'
        )
        is None
    )


def test_salvage_refuses_a_score_field_spelled_with_a_unicode_escape():
    """A ``\\u`` escape could hide a duplicate from the raw-name count."""
    assert (
        eval_mod._salvage_scores(
            '{"activation_score": 1, "citation_score": 1, "behavior_score": 1, '
            '"reasoning": "x "y", "\\u0061ctivation_score": 5}'
        )
        is None
    )


def test_salvage_scores_reject_duplicate_fields_before_reasoning():
    result = eval_mod._judge_parse_failure(
        '{"activation_score": 4, "activation_score": 5, '
        '"citation_score": 3, "behavior_score": 5, "reasoning": "broken"}',
        "parse error",
    )

    assert result["judge_failed"] is True


def test_judge_parse_failure_salvages_scores_from_unescaped_quote_prose():
    result = eval_mod._judge_parse_failure(_UNESCAPED_QUOTE_JUDGE, "judge parse error")

    assert result["judge_failed"] is False
    assert result["judge_salvaged"] is True
    assert result["activation_score"] == 5
    assert result["citation_score"] == 4
    assert result["behavior_score"] == 5


def test_judge_parse_failure_still_fails_when_no_scores_are_present():
    result = eval_mod._judge_parse_failure("I refuse to grade this.", "parse error")

    assert result["judge_failed"] is True
    assert result["activation_score"] == 0
    assert "judge_salvaged" not in result


def test_judge_parse_failure_does_not_invent_a_missing_field():
    """Two of three is not a score. Salvage must be all-or-nothing."""
    result = eval_mod._judge_parse_failure(
        '{"activation_score": 5, "citation_score": 4}', "missing behavior_score"
    )

    assert result["judge_failed"] is True
    assert result["behavior_score"] == 0


def test_judge_parse_failure_rejects_a_non_numeric_score():
    result = eval_mod._judge_parse_failure(
        '{"activation_score": "high", "citation_score": 4, "behavior_score": 5}',
        "non-numeric activation_score",
    )

    assert result["judge_failed"] is True


@pytest.mark.parametrize("activation_score", ["0", "6", "-1", "05", "5.0", "5e0", "5junk"])
def test_salvage_scores_rejects_an_invalid_value(activation_score):
    salvaged = eval_mod._judge_parse_failure(
        f'{{"activation_score": {activation_score}, "citation_score": 4, "behavior_score": 3}} "',
        "parse error",
    )

    assert salvaged["judge_failed"] is True
    assert salvaged["activation_score"] == 0
    assert salvaged["behavior_score"] == 0


def test_salvage_rejects_non_integral_scores():
    """A non-integral score is a failed measurement, not something to round.
    Reading only the integer part would turn 4.5 into a 4 the judge never
    gave, which is fabrication rather than salvage."""
    assert (
        eval_mod._salvage_scores(
            '{"activation_score": 4.5, "citation_score": 3, "behavior_score": 5}'
        )
        is None
    )


def test_salvage_returns_ints_so_the_shape_gate_accepts_them():
    """Regression guard on a cross-branch break. The shape gate requires an
    exact int; salvage returning floats made every salvage fail that gate and
    silently reverted the cell to a zeroed judge failure. The two paths must
    agree on the score type."""
    salvaged = eval_mod._salvage_scores(
        '{"activation_score": 4, "citation_score": 3, "behavior_score": 5}'
    )

    assert salvaged == {
        "activation_score": 4,
        "citation_score": 3,
        "behavior_score": 5,
    }
    assert all(type(v) is int for v in salvaged.values())
    assert eval_mod._judge_score_shape_error(salvaged) is None


def test_salvage_takes_a_whole_verdict_rather_than_stitching_two_objects():
    """An agentic judge emits tool traces and retries alongside its verdict.
    Unanchored field searches would take one score from each and report a
    composite the judge never gave, with judge_failed set to False.

    Round 7 turned the blanket rejection into a recovery by ranking candidate
    objects. Round 8 restored the rejection: ranking candidates is the search
    that produced eleven fabrication defects, and here the trace both names a
    field twice and displaces the verdict from the anchor. Two independent
    reasons to refuse, which is the posture this payload deserves.
    """
    assert (
        eval_mod._salvage_scores(
            '{"activation_score": 1} trace '
            '{"activation_score": 4, "citation_score": 3, "behavior_score": 5}'
        )
        is None
    )


def test_salvage_rejects_scientific_notation():
    """5e-1 is 0.5. Reading the mantissa alone turns it into a 5, which is a
    fabricated passing score rather than a recovered one."""
    assert (
        eval_mod._salvage_scores(
            '{"activation_score": 5e-1, "citation_score": 3, "behavior_score": 5}'
        )
        is None
    )


def test_salvage_ignores_score_fields_quoted_inside_reasoning():
    """A judge that quotes the rubric back names a score field twice.

    Round 6 refused on that name count. Round 7 dropped it, arguing the scan
    halts at ``reasoning`` so prose cannot donate a number. True, and beside
    the point: the halt also hides a duplicate *key* after it, which round 8
    showed silently returned the wrong one of two stated scores. The count is
    back, and it refuses prose and duplicate alike because past an unescaped
    quote there is no way to tell them apart.
    """
    assert (
        eval_mod._salvage_scores(
            '{"activation_score": 4, "citation_score": 3, "behavior_score": 5, '
            '"reasoning": "the rubric says "activation_score": 1 for this"'
        )
        is None
    )


def test_salvage_rejects_scores_found_only_inside_reasoning():
    """Scores that appear only after the reasoning key are quoted text, not a
    verdict. Salvaging them would grade the response on its own words."""
    assert (
        eval_mod._salvage_scores(
            '{"reasoning": "it claimed "activation_score": 4, '
            '"citation_score": 3, "behavior_score": 5"}'
        )
        is None
    )


def test_salvage_requires_an_object_to_anchor_on():
    assert (
        eval_mod._salvage_scores("activation_score: 4 citation_score: 3 behavior_score: 5") is None
    )


def test_salvage_skips_a_nested_rubric_and_takes_the_real_verdict():
    """A verdict behind a nested rubric is refused, not recovered.

    Reading past the rubric needed depth tracking, and the two independently
    written scanners that did it both counted braces without brackets, so an
    object inside a top-level array read as a root-level verdict. Skipping
    machinery is what made an exemplar reachable at all; without it the scan
    stops at the first non-integer value and this payload yields nothing.
    """
    assert (
        eval_mod._salvage_scores(
            '{"rubric": {"activation_score": 1, "citation_score": 1, '
            '"behavior_score": 1, "reasoning": "example of a bad response"}, '
            '"activation_score": 5, "citation_score": 3, "behavior_score": 4, '
            '"reasoning": "the real "verdict" prose"}'
        )
        is None
    )


def test_salvage_rejects_fields_completed_by_a_second_root_object():
    """Exactly-once matching is not enough on its own: two disjoint objects
    can each contribute a different field and satisfy it. Only depth-1 members
    of the first object count, so the second object is never reached and the
    incomplete first object fails."""
    assert (
        eval_mod._salvage_scores(
            '{"activation_score": 1} {"citation_score": 2, "behavior_score": 3, "reasoning": "x"}'
        )
        is None
    )


@pytest.mark.parametrize(
    ("raw", "why"),
    [
        ("5junk", "trailing garbage is not a JSON number"),
        ("05", "leading zeros are invalid JSON and hint at a truncated token"),
        ("5.", "a bare trailing point is not a JSON number"),
        ("5e", "a bare exponent marker is not a JSON number"),
        ("\u00a05", "a non-breaking space is not JSON whitespace"),
        ("+5", "JSON forbids a leading plus"),
    ],
)
def test_salvage_requires_the_full_json_integer_grammar(raw, why):
    """Matching leading digits reads 5junk and 05 as 5. Each is a fabricated
    score, not a recovered one, so the whole token has to match."""
    assert (
        eval_mod._salvage_scores(
            f'{{"activation_score": {raw}, "citation_score": 3, '
            '"behavior_score": 4, "reasoning": "x"}'
        )
        is None
    ), why


def test_salvage_rejects_a_duplicate_member_key():
    """Two values for one field means the payload is ambiguous. There is no
    principled way to pick, so the sample fails rather than guessing."""
    assert (
        eval_mod._salvage_scores(
            '{"activation_score": 5, "activation_score": 2, '
            '"citation_score": 3, "behavior_score": 4, "reasoning": "x"}'
        )
        is None
    )


def test_salvage_rejects_reasoning_before_scores():
    """Documents a deliberate limitation. Text after a malformed string value
    cannot be trusted, because the unescaped quote that broke the parse also
    desynchronizes every later read. The judge prompt asks for scores first;
    if that ordering ever changes, this test fails loudly instead of the
    salvage path silently returning nothing."""
    assert (
        eval_mod._salvage_scores(
            '{"reasoning": "the "quote" broke it", "activation_score": 5, '
            '"citation_score": 3, "behavior_score": 4}'
        )
        is None
    )


@pytest.mark.parametrize(
    ("label", "payload"),
    [
        ("bare_open_brace", "{"),
        ("empty_object", "{}"),
        ("member_missing_value", '{"activation_score":,"citation_score":3}'),
        ("truncated_after_colon", '{"activation_score": '),
        ("unterminated_nested_object", '{"n":{"a":1,"activation_score":5'),
        ("unbalanced_bracket_in_array", '{"n":[{"a":1},"activation_score":5}'),
        ("score_value_is_object", '{"activation_score":{"v":5},"citation_score":3}'),
        ("score_value_is_boolean", '{"activation_score":true,"citation_score":3}'),
    ],
)
def test_salvage_rejects_malformed_structures(label, payload):
    """A hand-written scanner has a failure class the old regex did not: it can
    desynchronize on truncated or malformed structure and hand back a
    plausible-looking triple assembled from the wrong bytes. Every payload here
    must return None rather than a partial reading."""
    assert eval_mod._salvage_scores(payload) is None, label


@pytest.mark.parametrize(
    ("label", "payload"),
    [
        (
            "depth_one_key_after_nested_object",
            '{"n":{"deep":{"a":1}},"activation_score":5,"citation_score":3,'
            '"behavior_score":4,"reasoning":"y"}',
        ),
        (
            "non_string_scalars_before_scores",
            '{"ok":true,"x":null,"activation_score":5,"citation_score":3,'
            '"behavior_score":4,"reasoning":"y"}',
        ),
        (
            "trailing_comma_before_close",
            '{"activation_score":5,"citation_score":3,"behavior_score":4,}',
        ),
        (
            "no_closing_brace",
            '{"activation_score":5,"citation_score":3,"behavior_score":4',
        ),
    ],
)
def test_salvage_recovers_despite_structural_noise(label, payload):
    """The scanner must skip nested containers and non-string scalars whole
    rather than giving up, otherwise it recovers less than the regex it
    replaced. A score nested inside a skipped array must never be mistaken for
    the top-level verdict: every case here carries 5/3/4 at depth one."""
    assert eval_mod._salvage_scores(payload) == {
        "activation_score": 5,
        "citation_score": 3,
        "behavior_score": 4,
    }, label


def test_salvage_rejects_an_out_of_range_score():
    """Salvage runs *after* the shape gate has already rejected the payload,
    so it cannot defer range checking to that gate without re-admitting what
    the gate just refused.

    That is what happened: a judge answer of 6 failed the shape gate, reached
    salvage, passed the integer-grammar check, and came back as a clean 5 once
    _clamp_score had squeezed it into the rubric. The score was reported as
    the judge's own with judge_failed set to False.
    """
    overflow = 10**20
    for value in (0, 6, -1, overflow):
        assert (
            eval_mod._salvage_scores(
                f'{{"activation_score":{value},"citation_score":3,'
                '"behavior_score":4,"reasoning":"y"}'
            )
            is None
        ), value


def test_salvage_rejects_a_desynchronized_nested_object():
    """The attack the depth check was built to stop, which it did not stop.

    An unescaped quote in prose inside a nested object flips the scanner's
    string state. A later brace that is really prose then reads as a
    structural close, so the skip lands *inside* the nested object and its
    members are harvested as if they were top-level. Here that hands back the
    exemplar's zeros while the real 5/5/5 verdict sits unread further along:
    fabrication in the worst possible direction, reported as a clean parse.

    Counting quotes does not catch this. The stray quote makes the count even,
    which is precisely why the state flips. Re-parsing the skipped span does
    catch it, because the span is not valid JSON.
    """
    assert (
        eval_mod._salvage_scores(
            '{"rubric": {"note": "he said "hi and }, "activation_score": 0, '
            '"citation_score": 0, "behavior_score": 0}, "activation_score": 5, '
            '"citation_score": 5, "behavior_score": 5}'
        )
        is None
    )


@pytest.mark.parametrize(
    ("label", "payload"),
    [
        (
            "structure_valued_first_occurrence",
            '{"activation_score": {"x": 1}, "activation_score": 5, '
            '"citation_score": 4, "behavior_score": 3}',
        ),
        (
            "escape_encoded_key",
            '{"activation_score": 5, "\\u0061ctivation_score": 0, '
            '"citation_score": 4, "behavior_score": 3}',
        ),
        (
            "duplicate_structure_valued_key",
            '{"rubric":{"a":1},"rubric":{"b":2},"activation_score":5,'
            '"citation_score":3,"behavior_score":4}',
        ),
        (
            "escaped_quote_in_key",
            r'{"we\"ird":1,"activation_score":5,"citation_score":3,'
            r'"behavior_score":4,"reasoning":"y"}',
        ),
    ],
)
def test_salvage_rejects_keys_that_defeat_duplicate_detection(label, payload):
    """Duplicate rejection is the invariant that stops a permissive parser from
    choosing between two conflicting answers, so anything that hides a
    collision from it has to reject.

    Two holes closed here. A structure-valued member used to be skipped
    without being recorded, so a later repeat of the same key won unopposed.
    And keys are compared as raw undecoded text, so an escape makes two
    spellings of one name look like two names. Escapes never appear in the
    fixed field names the judge is given, so refusing any escaped key costs a
    recovery that would never have been legitimate.
    """
    assert eval_mod._salvage_scores(payload) is None, label


@pytest.mark.parametrize(
    ("label", "payload"),
    [
        (
            "nested_object_containing_a_string",
            '{"n":{"a":"x"},"activation_score":5,"citation_score":3,'
            '"behavior_score":4,"reasoning":"y"}',
        ),
        (
            "nested_string_containing_a_brace",
            '{"n":{"a":"}"},"activation_score":5,"citation_score":3,'
            '"behavior_score":4,"reasoning":"y"}',
        ),
        (
            "nested_string_with_escaped_quotes",
            r'{"n":{"a":"say \"hi\""},"activation_score":5,'
            r'"citation_score":3,"behavior_score":4,"reasoning":"y"}',
        ),
        (
            "empty_nested_object",
            '{"n":{},"activation_score":5,"citation_score":3,"behavior_score":4,"reasoning":"y"}',
        ),
    ],
)
def test_salvage_still_skips_well_formed_nested_structures(label, payload):
    """The span re-parse must not turn every nested object into a rejection.

    A nested container that is itself valid JSON has a trustworthy end, so it
    is skipped and the scan continues. These are the shapes a real judge
    emits, including a rubric carrying its own zeroed exemplar, and all of
    them must still yield the depth-one 5/3/4.
    """
    assert eval_mod._salvage_scores(payload) == {
        "activation_score": 5,
        "citation_score": 3,
        "behavior_score": 4,
    }, label


def test_salvage_handles_deep_nesting_without_recursion():
    """`_skip_balanced` iterates, but the span re-parse calls `json.loads`,
    which recurses. Deep nesting must skip cleanly rather than raise."""
    deep = (
        '{"n":'
        + '{"a":' * 50
        + "1"
        + "}" * 50
        + (',"activation_score":5,"citation_score":3,"behavior_score":4}')
    )
    assert eval_mod._salvage_scores(deep) == {
        "activation_score": 5,
        "citation_score": 3,
        "behavior_score": 4,
    }


@pytest.mark.parametrize(
    "label,payload",
    [
        (
            "two_disjoint_objects_exemplar_first",
            '{"activation_score":1,"citation_score":1,"behavior_score":1} '
            '{"activation_score":5,"citation_score":5,"behavior_score":5}',
        ),
        (
            "two_disjoint_objects_exemplar_second",
            '{"activation_score":5,"citation_score":5,"behavior_score":5} '
            '{"activation_score":1,"citation_score":1,"behavior_score":1}',
        ),
        (
            "second_verdict_trails_a_malformed_first",
            '{"activation_score":1,"citation_score":1,"behavior_score":1} '
            '{"activation_score":5,"citation_score":5,"behavior_score":5,'
            '"reasoning":"he said "x"',
        ),
    ],
)
def test_salvage_rejects_payloads_offering_two_candidate_verdicts(label, payload):
    """A payload offering two complete verdicts is refused outright.

    Review round 6 found that reading the first object and never reaching the
    second is safe against a second object *donating a field*, but not against
    it *being the real verdict*. An exemplar echoed ahead of the answer
    returned the exemplar's scores and reported a clean parse, which is the
    same fabrication class as the round-5 desynchronization defect.

    Round 6 answered that by counting field names across the whole payload.
    Round 7 replaced the count with this rule, because the count also refused
    a leading tool trace that merely mentions a field, which is the ordinary
    agentic-CLI shape salvage exists to serve. Requiring exactly one
    *complete* candidate rejects everything the count rejected here while
    still recovering the trace case, so it is not a loosening.

    Note that every exemplar below scores 1 rather than 0. A 0 is out of the
    1-5 rubric and is discarded before it can compete, so a zero-valued
    exemplar would make these pass without exercising the ambiguity rule at
    all. The earlier version of this test had exactly that defect.
    """
    assert eval_mod._salvage_scores(payload) is None, label


@pytest.mark.parametrize(
    "label,payload",
    [
        (
            "nested_rubric_carrying_an_exemplar_verdict",
            '{"rubric":{"activation_score":1,"citation_score":1,'
            '"behavior_score":1},"activation_score":5,"citation_score":3,'
            '"behavior_score":4,"reasoning":"y"}',
        ),
        (
            "exemplar_inside_an_array",
            '{"examples":[{"activation_score":1,"citation_score":1,'
            '"behavior_score":1}],"activation_score":5,"citation_score":3,'
            '"behavior_score":4}',
        ),
    ],
)
def test_salvage_refuses_an_exemplar_it_cannot_tell_from_the_verdict(label, payload):
    """Every shape here needed a search to get past, so every one is refused.

    A nested object, an array element, and prose naming a field are the three
    ways an exemplar reached the scan. Round 7 answered each with a separate
    disqualifier and kept the recovery. Round 8 found the disqualifiers shared
    a brace-counting definition of "root" that admitted array elements, and
    that adding a fourth would only narrow the set of wrong answers still
    reachable. Refusing all three removes the question instead of re-asking it.
    """
    assert eval_mod._salvage_scores(payload) is None, label


def test_salvage_reads_a_verdict_whose_prose_names_a_score_field():
    """Prose naming a dimension is not a second verdict.

    An earlier version counted the *bare* identifier and refused this payload.
    The stated justification was that the refusal is free, measured as: across
    the 264 graded samples in the archived runs, no judge reasoning names a
    score field. That measurement is real but it does not support the claim.
    It describes one judge, one prompt, and one provider; a judge that states
    its verdict and then explains it ("I set activation_score high because...")
    is ordinary output, and this payload carries exactly one verdict, so
    refusing it discards a sample to protect against nothing.

    The guard now counts the JSON *key* shape, quoted or escaped-quoted, which
    keeps the evasion closed (see the test below) without charging prose for
    it.
    """
    assert eval_mod._salvage_scores(
        '{"activation_score":5,"citation_score":3,"behavior_score":4,'
        '"reasoning":"I set activation_score high because"}'
    ) == {"activation_score": 5, "citation_score": 3, "behavior_score": 4}


def test_salvage_refuses_a_second_verdict_serialized_inside_a_string():
    """The evasion the bare-name count exists to close.

    The payload states which triple is the answer and salvage cannot read
    that, so it must decline rather than pick. Counting the quoted spelling
    returned the first triple; counting the bare name refuses.
    """
    payload = (
        '{"activation_score":1,"citation_score":1,'
        '"behavior_score":1,"reasoning":"rubric "example""}\n'
        '{"final_answer":"{\\"activation_score\\":5,\\"citation_score\\":5,'
        '\\"behavior_score\\":5}"}'
    )

    assert eval_mod._names_a_score_field_twice(payload) is True
    assert eval_mod._salvage_scores(payload) is None


def test_salvage_refuses_a_second_verdict_spelled_in_the_single_quote_dialect():
    """The third spelling of a JSON key, and the fourteenth defect.

    Salvage runs only on payloads that already failed a strict parse, so the
    input is malformed by construction and the JSON5/Python dialect
    (``'activation_score': 5``) is exactly the kind of malformation a lenient
    model emits. A guard that recognized only the double-quoted and
    escaped-double-quoted spellings read this payload as carrying one verdict
    and returned the 1/1/1 at offset zero, discarding a stated 5/5/5 without
    recording that it had made a choice.

    Same selection class as the thirteen before it: the guard did not see the
    second candidate, so the first won by default. Found by adversarial review
    round 11.

    The false-refusal cost is measured at zero on this corpus: no reasoning in
    the 264 graded samples and none of the 24 stored failure prefixes spells a
    score key with single quotes. That is one judge, one prompt, and one
    provider, so the cost is measured-here, not free. A judge that quotes JSON
    in its prose would pay it.
    """
    payload = (
        '{"activation_score":1,"citation_score":1,"behavior_score":1,'
        '"reasoning":"bad "quote", \'activation_score\':5,'
        "'citation_score':5, 'behavior_score':5}"
    )

    assert eval_mod._names_a_score_field_twice(payload) is True
    assert eval_mod._salvage_scores(payload) is None


def test_a_mismatched_quote_pair_is_not_a_key():
    """Each spelling pairs its own quotes rather than mixing them.

    A guard written as ``(?:"|')field(?:"|')`` would accept ``"field':`` and
    ``'field":``, neither of which any decoder reads as a key. Refusing on a
    non-key costs a real sample, which is the false-refusal failure round 10
    finding 5 already charged this guard for once.
    """
    single_verdict = (
        '{"activation_score":5,"citation_score":3,"behavior_score":4,'
        "\"reasoning\":\"the rubric line read \\\"activation_score': high\\\"\"}"
    )

    assert eval_mod._names_a_score_field_twice(single_verdict) is False


def test_a_prematurely_closed_rubric_is_refused_by_both_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trailing root-level score fields make the payload ambiguous.

    This payload closes a complete object and then continues with bare
    ``"activation_score":5`` members that belong to no object. It reads like a
    judge whose rubric block closed one brace early, so the 5/5/5 tail is
    plausibly the answer it meant to give.

    Both paths now refuse on the same name count. Previously the strict path
    took 1/1/1 while salvage refused, so the instrument's two readers of one
    payload disagreed and only the quieter one was audited. Where two stated
    numbers disagree, the safe move is to state neither.
    """
    payload = (
        '{"rubric":{"note":"x"},"activation_score":1,"citation_score":1,'
        '"behavior_score":1},"activation_score":5,"citation_score":5,'
        '"behavior_score":5}'
    )

    assert eval_mod._extract_json_object(payload) is None
    assert eval_mod._salvage_scores(payload) is None
    assert _score_with_judge_text(monkeypatch, payload)["judge_failed"] is True


def test_salvage_survives_trailing_content_carrying_no_scores():
    """Strictness is scoped to ambiguity, not to any trailing bytes.

    Junk after a complete verdict leaves exactly one candidate answer, so
    refusing it would cost recoveries without removing a fabrication path.
    """
    assert eval_mod._salvage_scores(
        '{"activation_score":5,"citation_score":3,"behavior_score":4} trailing'
    ) == {"activation_score": 5, "citation_score": 3, "behavior_score": 4}


def test_extract_json_object_returns_none_on_empty_input():
    assert eval_mod._extract_json_object("") is None


def test_extract_json_object_ignores_braces_inside_strings():
    text = '{"reasoning": "avoid {} literals here", "activation_score": 3}'
    assert eval_mod._extract_json_object(text) == text


def test_extract_json_object_ignores_escaped_quotes_inside_strings():
    text = '{"reasoning": "the model said \\"do not extract\\" here", "s": 1}'
    assert eval_mod._extract_json_object(text) == text


def test_extract_json_object_ignores_escaped_backslash_before_quote():
    text = '{"reasoning": "trailing backslash \\\\", "s": 1}'
    assert eval_mod._extract_json_object(text) == text


def test_extract_json_object_stops_at_an_unbalanced_leading_candidate():
    """An unbalanced opener ends the walk instead of restarting inside it.

    This test previously asserted recovery: skip the junk, take the verdict
    that follows. Review round 6 showed that is unsafe. Once the first opener
    never closes, every later brace is textually *inside* it, so advancing to
    the next one descends into the malformed region rather than past it. When
    that region holds a score-shaped object, as it does when a judge quotes
    the rubric inside a broken ``reasoning`` string, the decoy is returned as
    the verdict with judge_failed set to False.

    The two shapes are indistinguishable from the text: junk-then-answer and
    broken-string-containing-decoy differ only in which object you happen to
    land on. So the recovery is given up. The cost is one judge sample; the
    alternative cost is a fabricated score in a published mean.
    """
    text = "{ unterminated\n" + _JUDGE
    assert eval_mod._extract_json_object(text) is None
    assert eval_mod._salvage_scores(text) is None


def test_extract_json_object_result_parses_as_json():
    text = _JUDGE + "\ntrailing"
    extracted = eval_mod._extract_json_object(text)
    assert extracted is not None
    assert json.loads(extracted)["activation_score"] == 5


def test_a_verdict_recovered_from_the_prefix_is_marked_salvaged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every recovery must be auditable after the run.

    A whole-payload parse failure followed by a prefix recovery used to return
    through the ordinary success branch, so it was indistinguishable from a
    clean parse. No post-hoc audit could count how often the instrument had
    read past a broken payload, which is why twelve defects of one class went
    twelve rounds without the archive showing a single one.
    """
    result = _score_with_judge_text(monkeypatch, _JUDGE + "\ntrailing prose")

    assert result["judge_failed"] is False
    assert result["judge_salvaged"] is True
    assert result["activation_score"] == 5


def test_a_clean_payload_is_not_marked_salvaged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative control: the marker must distinguish, not decorate."""
    result = _score_with_judge_text(monkeypatch, _JUDGE)

    assert result["judge_failed"] is False
    assert "judge_salvaged" not in result


# ---------------------------------------------------------------------------
# Markdown fences (the thirteenth defect of the selection class)
# ---------------------------------------------------------------------------

_FENCE = "`" * 3


def _fenced(body: str) -> str:
    return f"{_FENCE}json\n{body}\n{_FENCE}"


def test_a_fenced_exemplar_after_the_verdict_does_not_win(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fence pre-parser was an unanchored search, and it ran first.

    ``re.search`` for a fence found the exemplar, replaced the *entire*
    payload with it, and handed the result to a strict parse that succeeded.
    Both the offset-zero anchor and the duplicate-name guard were bypassed
    because neither ever saw the real payload, and the recovery carried no
    marker because the substituted text parsed cleanly. That is the thirteenth
    defect of the selection class and the first one found upstream of
    ``_extract_json_object``.
    """
    payload = (
        '{"activation_score":1,"citation_score":1,"behavior_score":1,'
        '"reasoning":"actual verdict"}\nRubric exemplar:\n'
        + _fenced(
            '{"activation_score":5,"citation_score":5,"behavior_score":5,'
            '"reasoning":"rubric exemplar"}'
        )
    )

    result = _score_with_judge_text(monkeypatch, payload)

    assert result["judge_failed"] is True
    assert result["activation_score"] == 0
    # The recorded payload is the original, not the fence body, so the
    # archived error prefix shows what the judge actually emitted.
    assert "actual verdict" in result["reasoning"]


def test_a_lone_fenced_verdict_is_recovered_and_marked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One fence is not a selection, so unwrapping it invents nothing.

    Refusing every fence would discard a shape judges really emit. The
    recovery is marked because the raw payload did not parse.
    """
    result = _score_with_judge_text(
        monkeypatch,
        _fenced(
            '{"activation_score":4,"citation_score":3,"behavior_score":2,"reasoning":"actual"}'
        ),
    )

    assert result["judge_failed"] is False
    assert result["judge_salvaged"] is True
    assert (result["activation_score"], result["citation_score"]) == (4, 3)


def test_two_fences_refuse_rather_than_pick_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Several fences is a choice, and choosing is the defect."""
    payload = (
        "Consider:\n"
        + _fenced('{"activation_score":5}')
        + "\nverdict:\n"
        + _fenced('{"activation_score":2,"citation_score":2,"behavior_score":2,"reasoning":"r"}')
    )

    result = _score_with_judge_text(monkeypatch, payload)

    assert result["judge_failed"] is True


def test_a_fence_whose_body_is_not_json_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unwrapping does not lower the parse bar."""
    result = _score_with_judge_text(monkeypatch, _fenced("activation_score: five"))

    assert result["judge_failed"] is True


def test_unwrap_lone_fence_returns_none_when_absent() -> None:
    assert eval_mod._unwrap_lone_fence(_JUDGE) is None


# ---------------------------------------------------------------------------
# Fence width pairing (adversarial review round 12)
# ---------------------------------------------------------------------------

_WIDE_FENCE = "`" * 4


def test_a_four_backtick_fence_survives_a_three_backtick_run_in_its_body() -> None:
    """A judge reaches for four backticks because its reasoning quotes three.

    Closing on a bare three-run cut the body at the inner quote and handed
    back something that would not parse, so the sample was dropped. Pairing
    the close to the opening width is the CommonMark rule and is what makes
    the shape legal in the first place.
    """
    body = (
        '{"activation_score":4,"citation_score":3,"behavior_score":2,'
        f'"reasoning":"the response used {_FENCE} to open a block"}}'
    )
    text = f"{_WIDE_FENCE}json\n{body}\n{_WIDE_FENCE}"

    assert eval_mod._unwrap_lone_fence(text) == body


def test_two_four_backtick_fences_still_refuse() -> None:
    """Widening the delimiter must not buy back a selection.

    The exactly-one-block rule is what removed the thirteenth defect. It has
    to hold at every delimiter width, not just at three.
    """
    block = f'{_WIDE_FENCE}json\n{{"activation_score":5}}\n{_WIDE_FENCE}'

    assert eval_mod._unwrap_lone_fence(f"{block}\n{block}") is None


def test_a_three_backtick_run_does_not_close_a_four_backtick_fence() -> None:
    """A narrower run is body text, so the block stays open and is refused."""
    text = f'{_WIDE_FENCE}json\n{{"activation_score":5}}\n{_FENCE}'

    assert eval_mod._unwrap_lone_fence(text) is None


def test_an_unterminated_fence_refuses_rather_than_running_to_the_end() -> None:
    """Truncated judge output must not hand back the prose that followed."""
    text = f'{_FENCE}json\n{{"activation_score":5}}'

    assert eval_mod._unwrap_lone_fence(text) is None


def test_a_wider_run_may_close_a_narrower_fence() -> None:
    """CommonMark lets the close exceed the open, and judges do emit that."""
    body = '{"activation_score":4,"citation_score":3,"behavior_score":2}'
    text = f"{_FENCE}json\n{body}\n{_WIDE_FENCE}"

    assert eval_mod._unwrap_lone_fence(text) == body


def test_an_unfenced_verdict_beside_a_lone_fenced_exemplar_refuses() -> None:
    """One fence is not one candidate, which was the sixteenth defect.

    The judge wrote its real verdict as unfenced prose and fenced a rubric
    exemplar it had explicitly labelled as one. Requiring exactly one fence
    removed the choice among fences and left the choice between the fence and
    everything around it, so the exemplar was published as the verdict.
    """
    text = (
        "Actual verdict:\n"
        "activation_score: 1\n"
        "citation_score: 1\n"
        "behavior_score: 1\n"
        "\n"
        "Rubric exemplar (do not use):\n"
        f"{_FENCE}json\n"
        '{"activation_score":5,"citation_score":5,"behavior_score":5}\n'
        f"{_FENCE}"
    )

    assert eval_mod._unwrap_lone_fence(text) is None
    assert eval_mod._recover_verdict(text) is None


def test_blank_lines_around_a_lone_fence_still_recover() -> None:
    """The refusal is about competing content, not about tidy whitespace."""
    body = '{"activation_score":4,"citation_score":4,"behavior_score":4}'

    assert eval_mod._unwrap_lone_fence(f"\n  \n{_fenced(body)}\n\t\n") == body


@pytest.mark.parametrize(
    "outside",
    [
        "the real verdict was 1/1/1",
        '{"activation_score":1,"citation_score":1,"behavior_score":1}',
        ".",
        "\u200b",
        "\u2060",
    ],
)
def test_content_outside_a_recoverable_fence_may_only_cause_refusal(
    outside: str,
) -> None:
    """Adding text outside a fence must never preserve or change a score.

    The property adversarial review asked for: a payload that recovers must
    stop recovering the moment something else could have been the answer. It
    may never keep the old scores and it may never produce new ones.
    """
    body = '{"activation_score":5,"citation_score":5,"behavior_score":5}'
    fenced = _fenced(body)
    assert eval_mod._unwrap_lone_fence(fenced) == body

    for polluted in (f"{outside}\n{fenced}", f"{fenced}\n{outside}"):
        assert eval_mod._unwrap_lone_fence(polluted) is None
        assert eval_mod._recover_verdict(polluted) is None


def test_prose_naming_a_score_field_does_not_block_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Counting bare identifiers refused output judges really produce.

    A verdict followed by a plain-English explanation naming a dimension is
    ordinary judge behavior, not a second verdict. The guard counts the JSON
    *key* shape instead, quoted or escaped-quoted, so prose costs nothing.
    """
    payload = _JUDGE + "\nThe activation_score reflects strong compliance."

    assert eval_mod._names_a_score_field_twice(payload) is False
    result = _score_with_judge_text(monkeypatch, payload)

    assert result["judge_failed"] is False
    assert result["judge_salvaged"] is True
    assert result["activation_score"] == 5


def test_an_escaped_quote_duplicate_still_refuses() -> None:
    """Regression: the key-shaped count must keep round nine's fix.

    A second verdict serialized inside a string spells its keys with escaped
    quotes. Matching only the plain quoted form would let it through.
    """
    payload = (
        '{"activation_score":1,"citation_score":1,"behavior_score":1,'
        '"reasoning":"the real answer was '
        '{\\"activation_score\\":5,\\"citation_score\\":5,\\"behavior_score\\":5}"}'
    )

    assert eval_mod._names_a_score_field_twice(payload) is True
    assert eval_mod._salvage_scores(payload) is None


# ---------------------------------------------------------------------------
# Judge failures must not be scored as zero (issue #3915)
# ---------------------------------------------------------------------------


def _sample(score: int, judge_failed: bool = False) -> dict[str, object]:
    return {
        "activation_score": score,
        "citation_score": score,
        "behavior_score": score,
        "judge_failed": judge_failed,
    }


def _ungraded_mech() -> dict[str, object]:
    """A cell where every judge sample failed, as the reducer emits it."""
    return {"scores": eval_mod._reduce_score_samples([_sample(0, judge_failed=True)], "median")}


def _unscored_mech() -> dict[str, object]:
    """A cell the judge returned without a usable score, and did not fail on.

    Not the same as `_ungraded_mech`, whose samples all failed. Both read as
    unmeasured when averaging, and only this one leaves `judge_failures` at
    zero, so only this one can reach a verdict past `FAIL_JUDGE_ERRORS`.
    Swapping the two silently changes which gate a test exercises.
    """
    return {"scores": {"cell_score": None}}


class TestReduceScoreSamples:
    def test_all_samples_graded_reduces_normally(self):
        reduced = eval_mod._reduce_score_samples([_sample(5), _sample(3), _sample(4)], "median")
        assert reduced["activation_score"] == 4
        assert reduced["judge_failed"] is False
        assert reduced["graded"] is True
        assert reduced["graded_sample_count"] == 3
        assert reduced["failed_sample_count"] == 0

    def test_partial_failure_reduces_over_graded_samples_only(self):
        # The live regression: 2 of 3 samples scored 5, one failed to parse.
        # Folding the failure in as a zero reported the cell as 0/0/0.
        reduced = eval_mod._reduce_score_samples(
            [_sample(0, judge_failed=True), _sample(5), _sample(5)], "median"
        )
        assert reduced["activation_score"] == 5
        assert reduced["citation_score"] == 5
        assert reduced["behavior_score"] == 5
        assert reduced["graded"] is True
        assert reduced["graded_sample_count"] == 2
        assert reduced["failed_sample_count"] == 1

    def test_partial_failure_still_flags_judge_failed(self):
        reduced = eval_mod._reduce_score_samples(
            [_sample(0, judge_failed=True), _sample(5)], "median"
        )
        assert reduced["judge_failed"] is True

    def test_all_samples_failed_yields_ungraded_cell(self):
        reduced = eval_mod._reduce_score_samples(
            [_sample(0, judge_failed=True), _sample(0, judge_failed=True)], "median"
        )
        assert reduced["graded"] is False
        assert reduced["judge_failed"] is True
        assert reduced["activation_score"] is None
        assert reduced["citation_score"] is None
        assert reduced["behavior_score"] is None
        assert reduced["graded_sample_count"] == 0
        assert reduced["failed_sample_count"] == 2

    def test_single_graded_sample_survives(self):
        reduced = eval_mod._reduce_score_samples([_sample(2)], "median")
        assert reduced["activation_score"] == 2
        assert reduced["graded_sample_count"] == 1


class TestUngradedCellsExcludedFromAverage:
    def test_ungraded_cell_does_not_drag_mean_to_zero(self):
        scenarios = [
            _make_scenario(baseline=5, description=5, full=5),
            _make_scenario(baseline=5, description=5, full=5),
        ]
        scenarios[1]["mechanisms"]["full"] = _ungraded_mech()

        summary = eval_mod.aggregate(scenarios)

        # Averaging the ungraded cell as zero would report 2.5.
        assert summary["per_mechanism"]["full"]["avg_score"] == 5.0
        assert summary["per_mechanism"]["full"]["graded_count"] == 1
        assert summary["per_mechanism"]["full"]["scenario_count"] == 2

    def test_uneven_failure_rates_do_not_zero_the_average(self):
        # full genuinely outscores description, but fails the judge more often.
        # Scoring failures as zero dragged its average down toward description.
        scenarios = [
            _make_scenario(baseline=1, description=2, full=5),
            _make_scenario(baseline=1, description=2, full=5),
        ]
        scenarios[1]["mechanisms"]["full"] = _ungraded_mech()

        summary = eval_mod.aggregate(scenarios)

        assert summary["per_mechanism"]["full"]["avg_score"] == 5.0
        assert summary["per_mechanism"]["description"]["avg_score"] == 2.0
        # Was `best_mechanism == "full"`. That ranked an average over one
        # scenario above an average over two, which is the comparison the
        # delta beside it refuses. The average above is what this pins; the
        # headline is pinned in TestTheHeadlineNeedsAWholePool.
        assert summary["best_mechanism"] == "description"

    def test_ungraded_cell_still_counts_as_a_judge_failure(self):
        scenarios = [_make_scenario(baseline=5, description=5, full=5)]
        scenarios[0]["mechanisms"]["full"] = _ungraded_mech()

        summary = eval_mod.aggregate(scenarios)

        assert summary["per_mechanism"]["full"]["judge_failures"] == 1
        assert summary["total_judge_failures"] >= 1
        assert summary["verdict"] == "FAIL_JUDGE_ERRORS"

    def test_every_cell_ungraded_reports_no_average_and_does_not_pass(self):
        scenarios = [_make_scenario(baseline=5, description=5, full=5)]
        for mech in ("baseline", "description", "full"):
            scenarios[0]["mechanisms"][mech] = _ungraded_mech()

        summary = eval_mod.aggregate(scenarios)

        # Was `== 0.0`. That average was over an empty set, so it named a
        # score no judge returned. The verdict below is what this pins.
        assert summary["per_mechanism"]["description"]["avg_score"] is None
        assert summary["per_mechanism"]["description"]["graded_count"] == 0
        assert summary["verdict"] == "FAIL_JUDGE_ERRORS"

    def test_api_error_cell_is_excluded_and_counted(self):
        scenarios = [
            _make_scenario(baseline=5, description=5, full=5),
            _make_scenario(baseline=5, description=5, full=5),
        ]
        scenarios[1]["mechanisms"]["full"] = {"error": "API network error", "scores": {}}

        summary = eval_mod.aggregate(scenarios)

        assert summary["per_mechanism"]["full"]["avg_score"] == 5.0
        assert summary["per_mechanism"]["full"]["graded_count"] == 1
        assert summary["per_mechanism"]["full"]["judge_failures"] == 1

    def test_graded_count_appears_in_rendered_table(self):
        scenarios = [
            _make_scenario(baseline=5, description=5, full=5),
            _make_scenario(baseline=5, description=5, full=5),
        ]
        scenarios[1]["mechanisms"]["full"] = _ungraded_mech()

        table = eval_mod.render_table("r", eval_mod.aggregate(scenarios))

        assert "Pos graded" in table
        assert "Neg graded" in table
        assert "1/2" in table
        assert "2/2" in table


_ARRAY_EXEMPLAR = (
    '{"activation_score": 5, "citation_score": 5, "behavior_score": 5, "reasoning": "exemplar"}'
)


@pytest.mark.parametrize(
    "label,payload",
    [
        (
            "array_exemplar_then_reasoning_first_real_verdict",
            f"[{_ARRAY_EXEMPLAR}]\n"
            '{"reasoning": "no citations", "activation_score": 1, '
            '"citation_score": 1, "behavior_score": 1}',
        ),
        (
            "prose_then_array_exemplar_then_refusal",
            f"Here is the rubric example:\n[{_ARRAY_EXEMPLAR}]\nI cannot score the response.",
        ),
        (
            "array_exemplar_with_a_broken_string",
            '[{"activation_score": 5, "citation_score": 5, '
            '"behavior_score": 5, "reasoning": "he said "hi" ok"}]',
        ),
        ("bare_valid_array", f"[{_ARRAY_EXEMPLAR}]"),
    ],
)
def test_an_object_inside_a_top_level_array_is_never_a_verdict(label, payload):
    """An array element is a quoted exemplar, not the judge's answer.

    Both root-object walkers counted braces and ignored brackets, so ``[{...}]``
    satisfied "root level". The bare-array case is the tell: the same payload
    with one broken string was salvaged as 5/5/5 while the intact version was
    correctly refused as non-object JSON, which is a parser that grades higher
    the more malformed its input gets.

    The second case is the worst of them. It carried no ``judge_salvaged``
    marker, so a fabricated 5/5/5 was indistinguishable from a clean parse in
    the artifact and no post-hoc audit could have surfaced it.
    """
    assert eval_mod._salvage_scores(payload) is None, label
    extracted = eval_mod._extract_json_object(payload)
    if extracted is not None:
        parsed = eval_mod._strict_json_loads(extracted)
        assert parsed.get("activation_score") != 5, label


def test_adding_a_second_candidate_can_only_withdraw_a_salvage():
    """The invariant every one of the eleven fabrication defects violated.

    Appending text to a payload may cause salvage to refuse. It must never
    change which numbers come back, because a changed number means appended
    text donated a score. Anchoring at offset 0 makes this structural rather
    than a property each disqualifier has to preserve on its own.
    """
    base = (
        '{"activation_score": 4, "citation_score": 3, "behavior_score": 5, '
        '"reasoning": "he said "hi" then left"}'
    )
    original = eval_mod._salvage_scores(base)
    assert original == {
        "activation_score": 4,
        "citation_score": 3,
        "behavior_score": 5,
    }
    for suffix in (
        f"\n{_ARRAY_EXEMPLAR}",
        f"\n[{_ARRAY_EXEMPLAR}]",
        '\n{"activation_score": 5, "citation_score": 5, "behavior_score": 5}',
        "\nOn reflection I would score it 5/5/5.",
    ):
        after = eval_mod._salvage_scores(base + suffix)
        assert after in (None, original), suffix


_ARCHIVE_DIR = (
    REPO_ROOT
    / ".agents"
    / "analysis"
    / "eval-artifacts"
    / "2026-07-29-unified-software-engineering"
)
_RECOVERED_PAYLOADS = _ARCHIVE_DIR / "recovered-judge-payloads.json"


def _published_triples() -> dict[tuple[str, str, str, str, int], tuple[int, int, int]]:
    """Index every published score sample by its artifact coordinates."""
    published = {}
    for path in sorted(_ARCHIVE_DIR.glob("*.json")):
        if path.name == _RECOVERED_PAYLOADS.name:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for rule_name, rule in (data.get("rules") or {}).items():
            for scenario in rule.get("scenarios", []):
                for mech_name, mech in (scenario.get("mechanisms") or {}).items():
                    for sample in mech.get("score_samples") or []:
                        key = (
                            path.stem,
                            rule_name,
                            scenario.get("id"),
                            mech_name,
                            sample.get("sample_index"),
                        )
                        published[key] = sample
    return published


def test_every_published_cell_still_scores_to_its_archived_triple(monkeypatch):
    """Replay the published table through the current parser, cell by cell.

    For most of this parser's history only the 24 *failed* samples could be
    replayed, because those are the ones that store raw text. That made a
    defect on the success path unmeasurable, and the gap was published as a
    limit rather than worked around.

    It was not a real limit. The judge payloads survive in the harness session
    transcripts, so all 288 samples were recovered and archived beside the
    results they produced. This test is what that buys: any change to verdict
    parsing is now checked against every published number, not against the
    eighth of them that happened to fail.

    A mismatch here means a parser change would have altered a result that has
    already been published and argued from. That is the failure this suite
    exists to catch.

    The coverage and uniqueness assertions below are not decoration. A replay
    that only walks the archive can stay green while the archive quietly loses
    a coordinate, or while two coordinates are handed the same source event.
    Both were real: an earlier archive attributed six coordinates to the wrong
    event because it matched payloads to cells by the parsed triple and then
    checked the match with the parsed triple.

    Two populations, two contracts. The 264 samples that scored at publication
    time must still produce the exact triple that was published. The 24 that
    were refused then are all recovered by the current parser, so they are
    pinned to what they now yield rather than to a published number they never
    had. That gap is the recovery divergence tracked in issue #3999; pinning it
    keeps it from drifting further without anyone noticing.
    """
    recovered = json.loads(_RECOVERED_PAYLOADS.read_text(encoding="utf-8"))
    published = _published_triples()
    assert recovered["sample_count"] == len(recovered["payloads"])

    archived_keys = {
        (e["artifact"], e["rule"], e["scenario"], e["mechanism"], e["sample_index"])
        for e in recovered["payloads"]
    }
    assert archived_keys == set(published), (
        "archive and published table disagree on which cells exist: "
        f"{len(archived_keys - set(published))} archived-only, "
        f"{len(set(published) - archived_keys)} published-only"
    )
    sources = [
        (e["source_session"], e["source_event_index"]) for e in recovered["payloads"]
    ]
    assert len(set(sources)) == len(sources), (
        "a source judge call is attributed to more than one published cell; "
        "at most one of those attributions can be right"
    )

    mismatches = []
    for entry in recovered["payloads"]:
        key = (
            entry["artifact"],
            entry["rule"],
            entry["scenario"],
            entry["mechanism"],
            entry["sample_index"],
        )
        sample = published[key]
        monkeypatch.setattr(
            eval_mod, "_call_api", lambda *_a, _p=entry["raw"], **_k: _p
        )
        result = eval_mod.score_response(
            "sk-test",
            {"input": "x", "expected_gate": "apply-rule"},
            "response",
        )
        if entry["judge_failed"]:
            if result["judge_failed"]:
                mismatches.append((key, "still refused", entry["recovered_triple"], True))
                continue
            now = [
                result["activation_score"],
                result["citation_score"],
                result["behavior_score"],
            ]
            if now != entry["recovered_triple"]:
                mismatches.append((key, now, entry["recovered_triple"], False))
            continue
        got = (
            result["activation_score"],
            result["citation_score"],
            result["behavior_score"],
        )
        want = (
            sample["activation_score"],
            sample["citation_score"],
            sample["behavior_score"],
        )
        if result["judge_failed"] or got != want:
            mismatches.append((key, got, want, result["judge_failed"]))

    assert not mismatches, f"{len(mismatches)} published cells changed: {mismatches[:5]}"


def _deeply_nested_payload(depth: int = 200_000) -> str:
    """A payload whose nesting exceeds the JSON decoder's own recursion limit.

    Nests objects rather than arrays on purpose. The recovery helpers anchor on
    a brace, so an array-only payload is rejected before it ever reaches the
    parse and would pass whether or not the seam converts the error.
    """
    return '{"a":' * depth + "1" + "}" * depth


def test_deep_nesting_raises_value_error_not_recursion_error():
    """The decoder's own limit must not leak past the parse seam.

    ``RecursionError`` subclasses ``RuntimeError``, and the scoring call site
    reads ``RuntimeError`` as a judge API outage. An unparseable payload filed
    as an outage is a different count, so the two must not be confused.
    """
    with pytest.raises(ValueError):
        eval_mod._strict_json_loads(_deeply_nested_payload())


@pytest.mark.parametrize("helper", ["_extract_json_object", "_recover_verdict"])
@pytest.mark.parametrize("shape", ["bare", "tail", "fenced"])
def test_deep_nesting_is_refused_by_the_recovery_helpers(helper, shape):
    """Both recovery helpers catch only ValueError, so the seam must supply it.

    The payload has to *start* with the object. ``_salvage_anchor`` refuses
    anything else outright (round 12), so a prose prefix short-circuits before
    the parse and the test would pass whether or not the seam converts the
    error.
    """
    nested = _deeply_nested_payload()
    payload = {
        "bare": nested,
        "tail": nested + " trailing prose",
        "fenced": "```json\n" + nested + "\n```",
    }[shape]
    assert getattr(eval_mod, helper)(payload) is None


def test_deep_nesting_scores_as_a_parse_failure_not_an_api_failure(monkeypatch):
    """The live path must file deep nesting as unparseable, not as an outage."""
    payload = _deeply_nested_payload()
    monkeypatch.setattr(eval_mod, "_call_api", lambda *_a, **_k: payload)
    result = eval_mod.score_response(
        "sk-test", {"input": "x", "expected_gate": "apply-rule"}, "response"
    )
    assert result["judge_failed"] is True
    assert result["activation_score"] == 0
    assert "judge API failure" not in result["reasoning"]


def test_the_exact_name_exemption_cannot_carry_a_verdict():
    """Only an exact field-name *key* is skipped, and a value never is.

    ``_string_values`` yields object keys, so a healthy payload's own root key
    reaches the refusal as a string and has to be skipped or every real payload
    fails. The skip is equality against ``_SCORE_FIELDS`` and applies to keys
    only, which is the distinction round 23 forced.

    The first repair skipped any *string* equal to a field name, on the
    reasoning that a string holding only a name holds no number. That is true
    of the string and false of the payload: a ``{"field": "activation_score",
    "value": 1}`` record puts the name in one slot and the competing number in
    its sibling, and it published a fabricated 5/4/5 over a stated 1/1/1. So a
    field name in value position refuses, and the last case here is that
    payload.

    Padding refuses too, because the skip does not strip. A key of
    ``"  activation_score  "`` is not the slot the schema defines, so a judge
    that emits one is naming a field somewhere the parser does not read, which
    is the whole trigger for a refusal.
    """
    names_two = eval_mod._parsed_names_two_verdicts
    verdict = {"activation_score": 1, "citation_score": 1, "behavior_score": 1}

    assert names_two({**verdict, "reasoning": "ok"}) is False
    assert names_two({**verdict, "notes": "the rule fired and was cited"}) is False

    for label, key in {
        "ascii padding": "  activation_score  ",
        "non breaking space": "\u00a0activation_score\u00a0",
        "newline padding": "\nactivation_score\n",
    }.items():
        assert names_two({**verdict, key: True}) is True, label

    assert names_two({**verdict, "reasoning": "activation_score"}) is True
    assert names_two({**verdict, "reasoning": ["activation_score"]}) is True
    assert names_two({**verdict, "activation_score2": '{"activation_score": 5}'}) is True
    assert names_two({**verdict, "reasoning": {"activation_score": 5}}) is True
    assert names_two({**verdict, "reasoning": "activation_score\uff1a5"}) is True


def test_a_verdict_split_across_field_and_value_slots_is_refused():
    """A record naming a field in one slot and its number in a sibling refuses.

    Round 23's blocking case, kept as its own test because it is the payload
    that broke the previous repair rather than a variation on it. The judge
    files 5/4/5 and then states a corrected 1/1/1 as structured records, so
    every field name sits in value position and every number sits beside it.
    Nothing here is a schema slot, nothing is a nested score-bearing object
    that ``_count_score_bearing_objects`` would count, and the published result
    was an unmarked 5/4/5.
    """
    names_two = eval_mod._parsed_names_two_verdicts
    payload = {
        "activation_score": 5,
        "citation_score": 4,
        "behavior_score": 5,
        "reasoning": "initial",
        "corrected_verdict": [
            {"field": "activation_score", "value": 1},
            {"field": "citation_score", "value": 1},
            {"field": "behavior_score", "value": 1},
        ],
    }
    assert names_two(payload) is True


def test_a_field_name_spelled_in_another_encoding_is_a_known_undetected_shape():
    """Homoglyph and zero-width spellings pass, and the docstring says so.

    The limit is one cause with three shapes: a field name that is not the
    literal codepoint sequence, whether split, substituted, or interleaved. No
    textual check closes it, so the honest move is to pin the behaviour in a
    test rather than let a future round rediscover it as a defect. Zero of the
    264 recovered payloads contain any of these shapes.
    """
    names_two = eval_mod._parsed_names_two_verdicts
    verdict = {"activation_score": 1, "citation_score": 1, "behavior_score": 1}

    assert names_two({**verdict, "reasoning": "activation_sc\u043ere: 5"}) is False
    assert names_two({**verdict, "reasoning": "activation\u200b_score: 5"}) is False


# ---------------------------------------------------------------------------
# Coordinate-wise reduction publishes a triple no judge gave (issue #3989)
# ---------------------------------------------------------------------------


def _mixed(activation: int, citation: int, behavior: int) -> dict[str, object]:
    """One judge sample whose three fields disagree."""
    return {
        "activation_score": activation,
        "citation_score": citation,
        "behavior_score": behavior,
        "judge_failed": False,
    }


def _mech_from(samples: list[dict[str, object]], reducer: str = "median") -> dict[str, object]:
    """A mechanism cell built the way a real run builds it."""
    return {"scores": eval_mod._reduce_score_samples(samples, reducer)}


def _scenario_from(mech: dict[str, object], negative: bool = False) -> dict[str, object]:
    """A scenario carrying the same cell at every mechanism."""
    return {
        "negative_case": negative,
        "mechanisms": {name: mech for name in eval_mod.MECHANISMS},
    }


class TestCellScoreReduction:
    """The published cell must be an observation, or the midpoint of two.

    Not "a score some judge could have given": with an even number of graded
    samples the median is the midpoint of the middle pair, which no judge
    wrote. The point of reducing each sample to a scalar first is that the
    result stays tied to real observations, not that it is always one of them.
    """

    def test_per_field_medians_can_beat_every_sample(self):
        # The issue's case. No judge gave better than 3.67, yet reducing each
        # field on its own publishes a perfect 5/5/5.
        samples = [_mixed(5, 5, 1), _mixed(5, 1, 5), _mixed(1, 5, 5)]
        reduced = eval_mod._reduce_score_samples(samples, "median")

        assert reduced["activation_score"] == 5
        assert reduced["citation_score"] == 5
        assert reduced["behavior_score"] == 5
        # Every sample's own mean, for contrast.
        assert [round(eval_mod._sample_scalar(s), 2) for s in samples] == [3.67] * 3
        assert round(reduced["cell_score"], 2) == 3.67

    def test_scenario_score_prefers_the_cell_score(self):
        scenario = _scenario_from(_mech_from([_mixed(5, 5, 1), _mixed(5, 1, 5), _mixed(1, 5, 5)]))
        score, failed, legacy = eval_mod._scenario_score_triple(scenario, "full")

        assert failed is False
        assert legacy is False, "a cell carrying cell_score is not a legacy cell"
        assert round(score, 2) == 3.67, "must not read the 5/5/5 the fields reduce to"

    def test_legacy_cell_without_cell_score_falls_back_to_the_triple_mean(self):
        # Artifacts written before cell_score existed carry only the per-field
        # reduction. Reading those must reproduce what the run published, not
        # restate an archived result under a rule it was not computed with.
        legacy_cell = {
            "negative_case": False,
            "mechanisms": {
                "full": {
                    "scores": {
                        "activation_score": 5,
                        "citation_score": 5,
                        "behavior_score": 2,
                        "judge_failed": False,
                        "graded": True,
                    }
                }
            },
        }
        score, failed, legacy = eval_mod._scenario_score_triple(legacy_cell, "full")

        assert failed is False
        assert round(score, 2) == 4.0
        assert legacy is True, "the substitution must be reported, not silent"

    def test_a_present_but_off_rubric_cell_score_is_reported_as_unmeasured(self):
        # `True` is an int in Python. A bool here means a corrupt artifact, not
        # a score of 1. NaN is worse: every comparison against it is False, so
        # an unguarded gate waves it through. A cell_score that is present and
        # unusable is damage, not a legacy artifact, so falling back to the
        # triple would restate a corrupt cell under a second reduction rule.
        for corrupt in (True, "4.0", [], float("nan"), float("inf"), 0, 7.5, -1):
            scenario = {
                "negative_case": False,
                "mechanisms": {
                    "full": {
                        "scores": {
                            "activation_score": 3,
                            "citation_score": 3,
                            "behavior_score": 3,
                            "cell_score": corrupt,
                            "graded": True,
                        }
                    }
                },
            }
            score, _, legacy = eval_mod._scenario_score_triple(scenario, "full")
            assert score is None, f"corrupt cell_score {corrupt!r} was read as a score"
            assert legacy is False

    def test_an_unconvertible_integer_cell_score_reads_as_unmeasured(self):
        # JSON has no integer width limit, so a damaged artifact can carry a
        # literal that Python parses to an int too large to convert to float.
        # `math.isfinite` converts, so asking it about that value raises
        # OverflowError and takes the whole run down. An off-rubric cell must
        # report as unmeasured; a crash is not a verdict.
        huge = json.loads('{"cell_score": ' + "1" + "0" * 400 + "}")["cell_score"]
        assert isinstance(huge, int), "the JSON parser must yield an int here"

        for corrupt in (huge, -huge):
            assert eval_mod._is_valid_score(corrupt) is False

            scenario = {
                "negative_case": False,
                "mechanisms": {
                    "full": {
                        "scores": {
                            "activation_score": 3,
                            "citation_score": 3,
                            "behavior_score": 3,
                            "cell_score": corrupt,
                            "graded": True,
                        }
                    }
                },
            }
            score, _, legacy = eval_mod._scenario_score_triple(scenario, "full")
            assert score is None, "an unconvertible cell_score was read as a score"
            assert legacy is False, "damage is not a pre-cell_score artifact"

    def test_a_null_cell_score_is_damage_rather_than_a_legacy_artifact(self):
        # `_reduce_score_samples` writes `cell_score` only on a graded cell and
        # always from a reducer over a non-empty list, so it cannot emit null.
        # A present null therefore did not come from the writer. Reducing the
        # triple instead would relabel a corrupt modern cell as a pre-cell_score
        # artifact, which is a false claim about how the number was produced.
        scenario = {
            "negative_case": False,
            "mechanisms": {
                "full": {
                    "scores": {
                        "activation_score": 3,
                        "citation_score": 3,
                        "behavior_score": 3,
                        "cell_score": None,
                        "graded": True,
                    }
                }
            },
        }
        score, _, legacy = eval_mod._scenario_score_triple(scenario, "full")

        assert score is None
        assert legacy is False

    def test_an_off_rubric_triple_field_is_reported_as_unmeasured(self):
        for corrupt in (float("nan"), float("inf"), 0, 7.5, True, "3"):
            scenario = {
                "negative_case": False,
                "mechanisms": {
                    "full": {
                        "scores": {
                            "activation_score": corrupt,
                            "citation_score": 3,
                            "behavior_score": 3,
                            "graded": True,
                        }
                    }
                },
            }
            score, _, _legacy = eval_mod._scenario_score_triple(scenario, "full")
            assert score is None, f"off-rubric triple field {corrupt!r} was averaged"

    def test_single_sample_publishes_that_sample_exactly(self):
        reduced = eval_mod._reduce_score_samples([_mixed(4, 2, 3)], "median")

        assert round(reduced["cell_score"], 2) == 3.0

    def test_an_ungraded_cell_carries_no_cell_score(self):
        reduced = eval_mod._reduce_score_samples([_sample(0, judge_failed=True)], "median")

        assert reduced["graded"] is False
        assert "cell_score" not in reduced

    def test_the_mean_reducer_agrees_with_the_per_field_mean(self):
        # Averaging commutes, so under `mean` the two orders coincide. The
        # divergence is a property of order statistics, not of reducing twice.
        samples = [_mixed(5, 5, 1), _mixed(5, 1, 5), _mixed(1, 5, 5)]
        reduced = eval_mod._reduce_score_samples(samples, "mean")
        per_field = [reduced[key] for key in eval_mod._SCORE_KEYS]

        assert round(reduced["cell_score"], 2) == round(sum(per_field) / 3, 2) == 3.67


# ---------------------------------------------------------------------------
# Negative scenarios must be able to fail a verdict (issue #3933)
# ---------------------------------------------------------------------------


def _ungraded_negative() -> dict[str, object]:
    """A negative scenario nobody graded, with no judge failure to explain it."""
    cell = {
        "scores": {
            "activation_score": None,
            "citation_score": None,
            "behavior_score": None,
            "graded": False,
            "judge_failed": False,
        }
    }
    return {
        "negative_case": True,
        "mechanisms": {name: cell for name in eval_mod.MECHANISMS},
    }


class TestNegativeCaseGate:
    """Negative scenarios grade restraint on an inverted rubric: 5 is good."""

    def test_a_rule_that_fires_where_it_must_not_fails(self):
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=5, description=1, full=1, negative=True),
        ]
        summary = eval_mod.aggregate(scenarios)

        assert summary["verdict"] == "FAIL_OVER_ACTIVATION"
        assert summary["worst_negative_avg"] == 1.0

    def test_the_gate_outranks_the_positive_gates(self):
        # The positive side of this suite passes outright. Over-activation has
        # to win anyway: firing where it must not is harmful, under-firing is
        # merely useless.
        scenarios = [_make_scenario(baseline=1, description=5, full=5)]
        assert eval_mod.aggregate(scenarios)["verdict"] == "PASS"

        scenarios.append(_make_scenario(baseline=5, description=1, full=1, negative=True))
        assert eval_mod.aggregate(scenarios)["verdict"] == "FAIL_OVER_ACTIVATION"

    def test_judge_errors_still_outrank_over_activation(self):
        # A broken judge means there is no trustworthy number to gate on, so
        # that verdict has to stay first.
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5, judge_failed=True),
            _make_scenario(baseline=5, description=1, full=1, negative=True),
        ]

        assert eval_mod.aggregate(scenarios)["verdict"] == "FAIL_JUDGE_ERRORS"

    def test_restraint_at_the_floor_passes(self):
        # 3.5 is the floor, not the first failing value. No single triple of
        # integer scores averages 3.5, so this is the midpoint of two: 10/3
        # and 11/3 straddle it.
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _scenario_from(_mech_from([_mixed(4, 3, 3), _mixed(4, 4, 3)]), negative=True),
        ]
        summary = eval_mod.aggregate(scenarios)

        assert summary["worst_negative_avg"] == eval_mod.MIN_RESTRAINT_SCORE
        assert summary["verdict"] == "PASS"

    def test_restraint_just_under_the_floor_fails(self):
        # One notch below the case above, to pin the boundary from both sides.
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _scenario_from(_mech_from([_mixed(4, 3, 3), _mixed(3, 3, 4)]), negative=True),
        ]
        summary = eval_mod.aggregate(scenarios)

        assert summary["worst_negative_avg"] < eval_mod.MIN_RESTRAINT_SCORE
        assert summary["verdict"] == "FAIL_OVER_ACTIVATION"

    def test_a_rule_that_holds_back_is_not_failed(self):
        # The negative control. A gate that fires here would fail every rule.
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=1, description=5, full=5, negative=True),
        ]
        summary = eval_mod.aggregate(scenarios)

        assert summary["verdict"] == "PASS"
        assert summary["worst_negative_avg"] == 5.0

    def test_baseline_restraint_is_not_the_rules_doing(self):
        # baseline carries no rule, so its behaviour cannot indict one. Were it
        # counted, this suite's worst would be 1.0 and the gate would fire.
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=1, description=5, full=5, negative=True),
        ]
        summary = eval_mod.aggregate(scenarios)

        assert summary["negative_case_per_mechanism"]["baseline"]["avg_score"] == 1.0
        assert summary["worst_negative_avg"] == 5.0
        assert summary["verdict"] == "PASS"

    def test_the_worst_rule_mechanism_decides_not_the_front_door(self):
        # `description` holds back perfectly; `full` does not. A benefit has to
        # be earned at the front door, but a harm counts wherever it appears.
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=5, description=5, full=1, negative=True),
        ]
        summary = eval_mod.aggregate(scenarios)

        assert summary["negative_case_per_mechanism"]["description"]["avg_score"] == 5.0
        assert summary["worst_negative_avg"] == 1.0
        assert summary["verdict"] == "FAIL_OVER_ACTIVATION"

    def test_a_suite_with_no_negative_scenarios_is_not_failed(self):
        # An empty pool has no average. It used to report 0.0, which sits below
        # every floor, so gating on it unguarded failed every rule. The guard
        # stays either way: `None` is not comparable against a floor at all.
        summary = eval_mod.aggregate([_make_scenario(baseline=1, description=5, full=5)])

        assert summary["negative_case_per_mechanism"]["full"]["avg_score"] is None
        assert summary["worst_negative_avg"] is None
        assert summary["verdict"] == "PASS"

    def test_negative_scenarios_nobody_graded_fail_rather_than_pass(self):
        # One step in from the empty pool: the pool is non-empty but nothing in
        # it was measured. There is no number to gate on, and passing here would
        # report restraint that was never demonstrated.
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _ungraded_negative(),
        ]
        summary = eval_mod.aggregate(scenarios)

        assert summary["negative_case_per_mechanism"]["full"]["graded_count"] == 0
        assert summary["worst_negative_avg"] is None
        assert summary["total_judge_failures"] == 0
        assert summary["negative_gate_incomplete"] == ["description", "full"]
        assert summary["verdict"] == "FAIL_NEGATIVE_INCOMPLETE"

    def test_a_partly_graded_negative_pool_fails_rather_than_averaging_a_subset(self):
        # The average over the graded half looks clean. Reporting it as the
        # pool's restraint attaches a number to a population it was not
        # computed over, which is the defect this gate exists to remove.
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=5, description=5, full=5, negative=True),
            _ungraded_negative(),
        ]
        summary = eval_mod.aggregate(scenarios)

        neg = summary["negative_case_per_mechanism"]["full"]
        assert (neg["graded_count"], neg["scenario_count"]) == (1, 2)
        assert summary["worst_negative_avg"] == 5.0, "the graded subset looks clean"
        assert summary["verdict"] == "FAIL_NEGATIVE_INCOMPLETE"

    def test_an_observed_violation_outranks_incomplete_coverage(self):
        # A floor violation seen on part of the pool is still a violation.
        # Naming the harm beats naming the gap that would have found more of it.
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=5, description=1, full=1, negative=True),
            _ungraded_negative(),
        ]
        summary = eval_mod.aggregate(scenarios)

        assert summary["negative_gate_incomplete"] == ["description", "full"]
        assert summary["verdict"] == "FAIL_OVER_ACTIVATION"

    def test_a_fully_graded_negative_pool_passes(self):
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=5, description=5, full=5, negative=True),
        ]
        summary = eval_mod.aggregate(scenarios)

        assert summary["negative_gate_incomplete"] == []
        assert summary["verdict"] == "PASS"

    def test_a_routed_target_does_not_gate_on_the_forced_full_mechanism(self):
        # For a skill reference, `full` force-injects the reference that routing
        # exists to keep out of context. No deployment performs that treatment,
        # so failing a correctly routing skill on it invents a harm.
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=5, description=5, full=1, negative=True),
        ]

        as_rule = eval_mod.aggregate(scenarios, routed=False)
        as_skill = eval_mod.aggregate(scenarios, routed=True)

        assert as_rule["negative_gate_mechanisms"] == ["description", "full"]
        assert as_rule["worst_negative_avg"] == 1.0
        assert as_rule["verdict"] == "FAIL_OVER_ACTIVATION"

        assert as_skill["negative_gate_mechanisms"] == ["description"]
        assert as_skill["worst_negative_avg"] == 5.0
        assert as_skill["verdict"] == "PASS"

    def test_a_routed_target_still_fails_when_the_routed_surface_over_activates(self):
        # Excluding `full` must not make the gate unreachable for skills.
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=5, description=1, full=5, negative=True),
        ]
        summary = eval_mod.aggregate(scenarios, routed=True)

        assert summary["worst_negative_avg"] == 1.0
        assert summary["verdict"] == "FAIL_OVER_ACTIVATION"

    def test_a_nan_negative_average_cannot_pass_the_floor(self):
        # Every comparison against NaN is False, so an unguarded `< 3.5` waves
        # it through. The cell must be rejected before it reaches the gate.
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=5, description=5, full=5, negative=True),
        ]
        scenarios[1]["mechanisms"]["description"]["scores"]["cell_score"] = float("nan")
        summary = eval_mod.aggregate(scenarios)

        worst = summary["worst_negative_avg"]
        assert worst is None or math.isfinite(worst)
        assert summary["verdict"] == "FAIL_NEGATIVE_INCOMPLETE"


class TestRenderTableRestraint:
    def test_an_unmeasured_negative_pool_is_not_printed_as_a_zero(self):
        summary = eval_mod.aggregate([_make_scenario(baseline=1, description=5, full=5)])
        table = eval_mod.render_table("some-rule", summary)

        assert "Restraint on negative cases: not measured" in table
        assert "| full         |     5.0 |       - |" in table

    def test_a_measured_negative_pool_is_printed_with_its_floor(self):
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=5, description=5, full=1, negative=True),
        ]
        table = eval_mod.render_table("some-rule", eval_mod.aggregate(scenarios))

        assert "worst of [description, full] 1.0 (floor 3.5)" in table
        assert "| full         |     5.0 |     1.0 |" in table


class TestArchivedSummariesStillAggregate:
    """Replay every archived run through `aggregate` and compare to what it published.

    The cell-level replay above pins the parser. This pins the reducer. A change
    to how cells are reduced, which mechanisms gate, or which population an
    average is read off can leave every cell identical and still move a
    published verdict, and nothing caught that until this class existed.

    The count assertions are the load-bearing part. The first version of this
    check globbed a directory and compared seven scalars: an empty glob passed,
    a missing field compared `None` against `None` and passed, and the nested
    per-mechanism summaries were never looked at. A guard that inspects nothing
    reports success. These tests fail if the archive shrinks.
    """

    EXPECTED_ARTIFACTS = 8
    EXPECTED_CELLS = 96
    PUBLISHED_FIELDS = (
        "verdict",
        "baseline_avg",
        "best_avg_score",
        "best_mechanism",
        "delta_full_vs_baseline",
        "delta_description_vs_baseline",
        "total_judge_failures",
    )
    # Keys this change adds. Present in the recomputed summary and absent from
    # the closed record, so not a regression. Anything else appearing on only
    # one side is.
    NEW_KEYS = frozenset(
        {
            "negative_gate_mechanisms",
            "negative_gate_incomplete",
            "worst_negative_avg",
            "legacy_reduced_count",
        }
    )

    @staticmethod
    def _runs():
        for path in sorted(_ARCHIVE_DIR.glob("*.json")):
            if path.name == _RECOVERED_PAYLOADS.name:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            for rule_id, rule in (data.get("rules") or {}).items():
                yield path.stem, rule_id, rule

    def test_the_archive_is_the_size_this_suite_believes_it_is(self):
        runs = list(self._runs())
        cells = sum(
            len(s["mechanisms"]) for _, _, rule in runs for s in rule["scenarios"]
        )

        assert len(runs) == self.EXPECTED_ARTIFACTS
        assert cells == self.EXPECTED_CELLS

    def test_every_archived_summary_reproduces_field_for_field(self):
        for tag, rule_id, rule in self._runs():
            published = rule["summary"]
            recomputed = eval_mod.aggregate(rule["scenarios"])
            for field in self.PUBLISHED_FIELDS:
                assert field in published, f"{tag}/{rule_id}: {field} left the record"
                assert field in recomputed, f"{tag}/{rule_id}: {field} left the summary"
                assert published[field] == recomputed[field], f"{tag}/{rule_id}.{field}"

    def test_every_archived_mechanism_summary_reproduces_key_for_key(self):
        for tag, rule_id, rule in self._runs():
            published = rule["summary"]
            recomputed = eval_mod.aggregate(rule["scenarios"])
            for pool in ("per_mechanism", "negative_case_per_mechanism"):
                pub_pool, rec_pool = published[pool], recomputed[pool]
                assert set(pub_pool) == set(rec_pool), f"{tag}/{rule_id}.{pool}"
                for mech, pub_stats in pub_pool.items():
                    rec_stats = rec_pool[mech]
                    for key, value in pub_stats.items():
                        if key in self.NEW_KEYS:
                            continue
                        assert key in rec_stats, f"{tag}/{rule_id}.{pool}.{mech}.{key}"
                        assert value == rec_stats[key], (
                            f"{tag}/{rule_id}.{pool}.{mech}.{key}: "
                            f"published={value!r} recomputed={rec_stats[key]!r}"
                        )

    def test_every_archived_cell_is_reported_as_legacy_reduced(self):
        """The replay above compares published keys, and this key is new.

        `legacy_reduced_count` is absent from every archived summary, so the
        key-for-key loop skips it and a reducer that stopped counting legacy
        cells would still replay clean. Every one of the 96 archived cells
        predates `cell_score`, so each graded cell must be reported as reduced
        from the triple. Anything less means the count is not tracking the
        thing it is named for.
        """
        total_graded = total_legacy = 0
        for tag, rule_id, rule in self._runs():
            recomputed = eval_mod.aggregate(rule["scenarios"])
            for pool in ("per_mechanism", "negative_case_per_mechanism"):
                for mech, stats in recomputed[pool].items():
                    assert stats["legacy_reduced_count"] == stats["graded_count"], (
                        f"{tag}/{rule_id}.{pool}.{mech}"
                    )
                    total_graded += stats["graded_count"]
                    total_legacy += stats["legacy_reduced_count"]

        # Pins the population, so the assertion above cannot pass by iterating
        # nothing. Every archived cell is graded, so this equals the cell count.
        assert total_graded == self.EXPECTED_CELLS
        assert total_legacy == self.EXPECTED_CELLS

    def test_a_cell_carrying_a_cell_score_is_not_counted_as_legacy(self):
        """Negative control for the count above.

        Without it, a `legacy_reduced_count` hardwired to `graded_count` would
        satisfy every assertion in this class.
        """
        scenarios = [
            {
                "negative_case": False,
                "mechanisms": {
                    m: {"scores": {"cell_score": 4, "graded": True}}
                    for m in eval_mod.MECHANISMS
                },
            }
        ]

        summary = eval_mod.aggregate(scenarios)

        for mech in eval_mod.MECHANISMS:
            stats = summary["per_mechanism"][mech]
            assert stats["graded_count"] == 1
            assert stats["legacy_reduced_count"] == 0

    def test_the_comparison_can_fail(self):
        """Negative control. A guard nobody has seen fail has not been run."""
        _tag, _rule_id, rule = next(iter(self._runs()))
        recomputed = eval_mod.aggregate(rule["scenarios"])
        corrupted = dict(rule["summary"], baseline_avg=-999.0)

        mismatches = [
            f for f in self.PUBLISHED_FIELDS if corrupted[f] != recomputed.get(f)
        ]

        assert mismatches == ["baseline_avg"]

    def test_the_archived_rule_is_always_on_so_full_gates(self):
        # These runs measured a `.claude/rules/` file, not a skill reference, so
        # `full` is a shipped surface and belongs in the restraint population.
        # If this ever flips, the archived verdicts were read off a population
        # they were not computed over.
        for tag, rule_id, rule in self._runs():
            recomputed = eval_mod.aggregate(rule["scenarios"])
            assert recomputed["negative_gate_mechanisms"] == ["description", "full"], (
                f"{tag}/{rule_id}"
            )
            assert recomputed["negative_gate_incomplete"] == [], f"{tag}/{rule_id}"


def _scenario_of_mechs(mechs: dict[str, dict[str, object]], negative: bool = False):
    """A scenario whose mechanisms are given cell by cell.

    Distinct from `_scenario_from` above, which repeats one cell across every
    mechanism. These tests need the mechanisms to differ.
    """
    return {"negative_case": negative, "mechanisms": mechs}


class TestUnreachableMechanismsDoNotDecideVerdicts:
    """A routed target must not fail on a treatment no deployment performs.

    `full` force-injects the reference that progressive disclosure exists to
    keep out of context. Its scores are a diagnostic. Before this, a judge
    error on that unreachable cell reached `total_judge_failures`, which is
    checked first, so a routed rule failed for a broken measurement of
    something nobody ships.
    """

    def test_a_routed_target_survives_judge_errors_on_the_unreachable_mechanism(self):
        scenarios = [
            _scenario_of_mechs(
                {
                    "baseline": _make_mech(1),
                    "description": _make_mech(5),
                    "full": _make_mech(5, judge_failed=True),
                }
            ),
            _scenario_of_mechs(
                {
                    "baseline": _make_mech(5),
                    "description": _make_mech(5),
                    "full": _make_mech(5, judge_failed=True),
                },
                negative=True,
            ),
        ]

        summary = eval_mod.aggregate(scenarios, routed=True)

        assert summary["verdict"] == "PASS"
        # The record still carries the failure. Only the verdict ignores it.
        assert summary["total_judge_failures"] == 2
        assert summary["gating_judge_failures"] == 0
        assert summary["unreachable_mechanisms"] == ["full"]

    def test_a_routed_target_still_fails_on_judge_errors_at_the_front_door(self):
        scenarios = [
            _scenario_of_mechs(
                {
                    "baseline": _make_mech(1),
                    "description": _make_mech(5, judge_failed=True),
                    "full": _make_mech(5),
                }
            )
        ]

        summary = eval_mod.aggregate(scenarios, routed=True)

        assert summary["verdict"] == "FAIL_JUDGE_ERRORS"
        assert summary["gating_judge_failures"] == 1

    def test_an_always_on_rule_still_fails_on_judge_errors_anywhere(self):
        """Negative control. `full` ships for an always-on rule, so it gates."""
        scenarios = [
            _scenario_of_mechs(
                {
                    "baseline": _make_mech(1),
                    "description": _make_mech(5),
                    "full": _make_mech(5, judge_failed=True),
                }
            )
        ]

        summary = eval_mod.aggregate(scenarios)

        assert summary["verdict"] == "FAIL_JUDGE_ERRORS"
        assert summary["gating_judge_failures"] == 1
        assert summary["unreachable_mechanisms"] == []


class TestPositivePoolCoverageGates:
    """The same partial-pool hole the negative gate closed was open here.

    An off-rubric positive cell is dropped from the average without setting
    `judge_failed`, so nothing forced a failure and `PASS` could be published
    over a subset of the scenarios the verdict names.
    """

    def test_a_partly_graded_positive_pool_fails_rather_than_averaging_a_subset(self):
        graded = _make_scenario(baseline=1, description=5, full=5)
        ungraded = _scenario_of_mechs(
            {
                "baseline": _make_mech(1),
                "description": {
                    "scores": {
                        "activation_score": float("nan"),
                        "citation_score": float("nan"),
                        "behavior_score": float("nan"),
                        "graded": True,
                    }
                },
                "full": _make_mech(5),
            }
        )

        summary = eval_mod.aggregate([graded, ungraded])

        assert summary["verdict"] == "FAIL_POSITIVE_INCOMPLETE"
        assert summary["positive_gate_incomplete"] == ["description"]
        # The average is still published, and it is still 5.0, but it now sits
        # beside a count saying it rests on one of the two scenarios.
        assert summary["per_mechanism"]["description"]["graded_count"] == 1
        assert summary["per_mechanism"]["description"]["scenario_count"] == 2

    def test_a_partly_graded_baseline_fails_the_same_way(self):
        """`baseline` is a gate mechanism, and the gate has to prove it on it.

        Every other damaged fixture in this class targets `description` or
        `full`, so a detector that skipped `baseline` entirely passed all of
        them. The control it establishes is the one the deltas are measured
        against, so a partial baseline invalidates every delta published
        beside it.
        """
        graded = _make_scenario(baseline=1, description=5, full=5)
        ungraded = _scenario_of_mechs(
            {
                "baseline": {
                    "scores": {
                        "activation_score": float("nan"),
                        "citation_score": float("nan"),
                        "behavior_score": float("nan"),
                        "graded": True,
                    }
                },
                "description": _make_mech(5),
                "full": _make_mech(5),
            }
        )

        summary = eval_mod.aggregate([graded, ungraded])

        assert summary["verdict"] == "FAIL_POSITIVE_INCOMPLETE"
        assert summary["positive_gate_incomplete"] == ["baseline"]
        assert summary["per_mechanism"]["baseline"]["graded_count"] == 1
        assert summary["per_mechanism"]["baseline"]["scenario_count"] == 2

    def test_a_fully_graded_positive_pool_passes(self):
        """Negative control. Without it the gate could be failing everything."""
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=1, description=5, full=5),
        ]

        summary = eval_mod.aggregate(scenarios)

        assert summary["verdict"] == "PASS"
        assert summary["positive_gate_incomplete"] == []

    def test_an_observed_over_activation_outranks_positive_incompleteness(self):
        """Ordering. An unproven benefit never outranks a demonstrated harm."""
        scenarios = [
            _scenario_of_mechs(
                {
                    "baseline": _make_mech(1),
                    "description": {
                        "scores": {
                            "activation_score": float("nan"),
                            "citation_score": float("nan"),
                            "behavior_score": float("nan"),
                            "graded": True,
                        }
                    },
                    "full": _make_mech(5),
                }
            ),
            _make_scenario(baseline=5, description=1, full=1, negative=True),
        ]

        summary = eval_mod.aggregate(scenarios)

        assert summary["positive_gate_incomplete"] == ["description"]
        assert summary["verdict"] == "FAIL_OVER_ACTIVATION"

    def test_full_is_not_a_positive_gate_mechanism(self):
        """`full` cannot rescue the front door, so it does not gate coverage."""
        scenarios = [
            _scenario_of_mechs(
                {
                    "baseline": _make_mech(1),
                    "description": _make_mech(5),
                    "full": {
                        "scores": {
                            "activation_score": 99,
                            "citation_score": 99,
                            "behavior_score": 99,
                            "graded": True,
                        }
                    },
                }
            )
        ]

        summary = eval_mod.aggregate(scenarios)

        assert summary["positive_gate_mechanisms"] == ["baseline", "description"]
        assert summary["verdict"] == "PASS"
        assert summary["per_mechanism"]["full"]["graded_count"] == 0


class TestWorstNegativeNamesItsPopulation:
    """`worst_negative_avg` is a min across mechanisms that need not have
    graded the same scenarios, so the number alone does not say what it covers.
    """

    def test_the_worst_negative_average_names_its_mechanism_and_its_count(self):
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=5, description=5, full=2, negative=True),
        ]

        summary = eval_mod.aggregate(scenarios)

        assert summary["worst_negative_avg"] == 2.0
        assert summary["worst_negative_mechanism"] == "full"
        assert summary["worst_negative_graded"] == 1

    def test_an_empty_negative_pool_names_no_mechanism(self):
        summary = eval_mod.aggregate([_make_scenario(baseline=1, description=5, full=5)])

        assert summary["worst_negative_avg"] is None
        assert summary["worst_negative_mechanism"] is None
        assert summary["worst_negative_graded"] == 0


class TestTableDisclosesItsPopulations:
    """A number printed beside a verdict must say what it was measured over."""

    def test_the_restraint_line_names_the_source_mechanism_and_its_count(self):
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=5, description=5, full=2, negative=True),
        ]

        table = eval_mod.render_table("r", eval_mod.aggregate(scenarios))

        assert "from full over 1/1 negative scenario(s)" in table

    def test_an_incomplete_positive_pool_is_named_in_the_table(self):
        ungraded = _scenario_of_mechs(
            {
                "baseline": _make_mech(1),
                "description": {
                    "scores": {"activation_score": 9, "graded": True},
                },
                "full": _make_mech(5),
            }
        )

        table = eval_mod.render_table(
            "r", eval_mod.aggregate([_make_scenario(1, 5, 5), ungraded])
        )

        assert "Positive pool incomplete at: description" in table

    def test_a_routed_exclusion_is_named_with_both_judge_counts(self):
        scenarios = [
            _scenario_of_mechs(
                {
                    "baseline": _make_mech(1),
                    "description": _make_mech(5),
                    "full": _make_mech(5, judge_failed=True),
                }
            )
        ]

        table = eval_mod.render_table("r", eval_mod.aggregate(scenarios, routed=True))

        assert "Excluded as unreachable for a routed target: full" in table
        # The counts moved onto their own line, which now fires on any
        # divergence rather than only on a routed exclusion. Same guarantee:
        # a reader is told the record holds a failure the verdict ignored.
        assert "Judge failures: 1 in the record, 0 on gating surfaces" in table
        assert "positive full" in table

    def test_an_always_on_rule_prints_no_exclusion_line(self):
        """Negative control. The line must not appear when nothing is excluded."""
        table = eval_mod.render_table(
            "r", eval_mod.aggregate([_make_scenario(1, 5, 5)])
        )

        assert "Excluded as unreachable" not in table
        assert "Positive pool incomplete" not in table


class TestPositiveVerdictIsTotal:
    """The extracted positive branch must decide every input, NaN included."""

    def test_it_agrees_with_the_inline_form_it_replaced(self):
        # The original wrote `passes and beats` first, then `not passes`. This
        # pins all four combinations so a later simplification to `<` cannot
        # quietly change one of them.
        cases = [
            (5.0, 1.0, "PASS"),
            (1.0, 1.0, "FAIL_THRESHOLD"),
            (
                eval_mod.MIN_ACTIVATION_SCORE,
                eval_mod.MIN_ACTIVATION_SCORE,
                "FAIL_NO_DELTA",
            ),
            (1.0, 5.0, "FAIL_THRESHOLD"),
        ]
        for desc, base, expected in cases:
            assert eval_mod._positive_verdict(desc, base) == expected, (desc, base)

    def test_a_non_comparable_average_fails_closed(self):
        # Every comparison against NaN is False, so a `<` form would fall
        # through to PASS. The negated `>=` form reports the threshold miss.
        nan = float("nan")
        assert eval_mod._positive_verdict(nan, 1.0) == "FAIL_THRESHOLD"
        assert eval_mod._positive_verdict(5.0, nan) == "FAIL_NO_DELTA"


class TestVerdictRankingLivesInOnePlace:
    """The gate order is load-bearing, so pin it against reordering."""

    def _summary(self, *, neg_incomplete=(), pos_incomplete=()):
        return {
            "negative_gate_incomplete": list(neg_incomplete),
            "positive_gate_incomplete": list(pos_incomplete),
        }

    def test_a_judge_failure_outranks_every_other_gate(self):
        verdict = eval_mod._decide_verdict(
            self._summary(neg_incomplete=["description"], pos_incomplete=["baseline"]),
            gating_judge_failures=1,
            worst_neg_avg=1.0,
            has_positive_cases=False,
            desc_avg=1.0,
            baseline_avg=5.0,
        )
        assert verdict == "FAIL_JUDGE_ERRORS"

    def test_an_observed_harm_outranks_an_incomplete_negative_pool(self):
        verdict = eval_mod._decide_verdict(
            self._summary(neg_incomplete=["description"]),
            gating_judge_failures=0,
            worst_neg_avg=1.0,
            has_positive_cases=True,
            desc_avg=5.0,
            baseline_avg=1.0,
        )
        assert verdict == "FAIL_OVER_ACTIVATION"

    def test_an_unproven_harm_outranks_an_unproven_benefit(self):
        verdict = eval_mod._decide_verdict(
            self._summary(neg_incomplete=["description"], pos_incomplete=["baseline"]),
            gating_judge_failures=0,
            worst_neg_avg=5.0,
            has_positive_cases=True,
            desc_avg=5.0,
            baseline_avg=1.0,
        )
        assert verdict == "FAIL_NEGATIVE_INCOMPLETE"

    def test_a_clean_run_still_reaches_the_positive_branch(self):
        verdict = eval_mod._decide_verdict(
            self._summary(),
            gating_judge_failures=0,
            worst_neg_avg=5.0,
            has_positive_cases=True,
            desc_avg=5.0,
            baseline_avg=1.0,
        )
        assert verdict == "PASS"


class TestUnmeasuredPoolsPublishNoNumber:
    """A mechanism nothing graded has no average, and no delta against one.

    An average over an empty set was reported as `0.0`, which is not on the
    1..5 rubric and is not a value any judge returned. It then flowed into
    `delta_*_vs_baseline` and into the rendered table, so a run could publish
    `PASS` beside a fabricated score and a fabricated delta, with nothing on
    the row to say the pool was empty except a `0/n` count.
    """

    @staticmethod
    def _full_ungraded() -> list[dict]:
        return [
            _scenario_of_mechs(
                {
                    "baseline": _make_mech(1),
                    "description": _make_mech(5),
                    "full": _unscored_mech(),
                }
            )
        ]

    def test_an_ungraded_mechanism_reports_no_average(self):
        summary = eval_mod.aggregate(self._full_ungraded())

        assert summary["per_mechanism"]["full"]["graded_count"] == 0
        assert summary["per_mechanism"]["full"]["avg_score"] is None

    def test_no_delta_is_published_against_an_ungraded_mechanism(self):
        summary = eval_mod.aggregate(self._full_ungraded())

        assert summary["delta_full_vs_baseline"] is None
        # The sibling delta is still measured, so the run is not blanked out.
        assert summary["delta_description_vs_baseline"] == 4.0

    def test_the_table_prints_no_score_for_an_ungraded_pool(self):
        summary = eval_mod.aggregate(self._full_ungraded())

        table = eval_mod.render_table("probe", summary)

        full_row = [r for r in table.splitlines() if r.startswith("| full")]
        assert len(full_row) == 1
        assert "0.0" not in full_row[0]
        assert "-1.0" not in full_row[0]
        assert [c.strip() for c in full_row[0].split("|")][1:7] == [
            "full",
            "-",
            "-",
            "",
            "0/1",
            "0/0",
        ]

    def test_an_ungraded_mechanism_is_never_the_best_one(self):
        """`max` over a `0.0` still ranks it above nothing; over `None` it errors."""
        scenarios = [
            _scenario_of_mechs(
                {
                    "baseline": _make_mech(1),
                    "description": _unscored_mech(),
                    "full": _unscored_mech(),
                }
            )
        ]

        summary = eval_mod.aggregate(scenarios)

        assert summary["best_mechanism"] is None
        assert summary["best_avg_score"] is None
        assert "none measured" in eval_mod.render_table("probe", summary)


class TestNegativeJudgeFailuresGateOnTheirOwnPool:
    """A broken judgement of the baseline on a negative case cannot fail a rule.

    `negative_gate_mechanisms` excludes `baseline` because a mechanism that
    carries no rule cannot over-activate on one. The judge-failure count that
    gates the same pool was summed over every mechanism, so the excluded cell
    could still decide the verdict through the other door.
    """

    @staticmethod
    def _neg_baseline_broken() -> list[dict]:
        neg = _scenario_of_mechs(
            {
                "baseline": {"scores": {"judge_failed": True}},
                "description": _make_mech(5),
                "full": _make_mech(5),
            }
        )
        neg["negative_case"] = True
        return [_make_scenario(baseline=1, description=5, full=5), neg]

    def test_a_broken_negative_baseline_does_not_fail_the_rule(self):
        summary = eval_mod.aggregate(self._neg_baseline_broken())

        assert summary["verdict"] != "FAIL_JUDGE_ERRORS"
        assert summary["gating_judge_failures"] == 0

    def test_the_failure_is_still_published_in_the_whole_run_count(self):
        """It is excluded from the gate, not hidden. C3 keeps the wide count."""
        summary = eval_mod.aggregate(self._neg_baseline_broken())

        assert summary["total_judge_failures"] == 1

    def test_a_broken_negative_description_still_fails_the_rule(self):
        """Negative control. The gate did not simply stop counting."""
        neg = _scenario_of_mechs(
            {
                "baseline": _make_mech(5),
                "description": {"scores": {"judge_failed": True}},
                "full": _make_mech(5),
            }
        )
        neg["negative_case"] = True
        scenarios = [_make_scenario(baseline=1, description=5, full=5), neg]

        summary = eval_mod.aggregate(scenarios)

        assert summary["verdict"] == "FAIL_JUDGE_ERRORS"
        assert summary["gating_judge_failures"] == 1


class TestDeltasRequireACommonPopulation:
    """A delta between two partly graded pools describes neither of them.

    Guarding only against a `None` average was not enough. Two averages can
    both exist and still cover different scenario sets, and their difference
    is then a number no scenario produced. With `baseline` graded 1/2 at 1.0
    and `description` graded 2/2 at 3.0, the instrument published 2.0 while
    the only scenario both measured differed by 4.0.
    """

    @staticmethod
    def _partial_baseline() -> list[dict]:
        return [
            _make_scenario(baseline=1, description=5, full=5),
            _scenario_of_mechs(
                {
                    "baseline": _unscored_mech(),
                    "description": _make_mech(1),
                    "full": _make_mech(1),
                }
            ),
        ]

    def test_no_delta_is_published_across_different_populations(self):
        summary = eval_mod.aggregate(self._partial_baseline())

        assert summary["per_mechanism"]["baseline"]["graded_count"] == 1
        assert summary["per_mechanism"]["description"]["graded_count"] == 2
        assert summary["delta_description_vs_baseline"] is None
        assert summary["delta_full_vs_baseline"] is None

    def test_an_unmeasured_control_does_not_crash_the_treatment_delta(self):
        """The sibling of the treatment guard. Only the treatment side was tested.

        Mutating `_delta` to check the treatment alone left every earlier test
        passing, and a measured description over an unmeasured baseline then
        raised `TypeError` on the subtraction.
        """
        scenarios = [
            _scenario_of_mechs(
                {
                    "baseline": _unscored_mech(),
                    "description": _make_mech(5),
                    "full": _make_mech(5),
                }
            )
        ]

        summary = eval_mod.aggregate(scenarios)

        assert summary["per_mechanism"]["baseline"]["avg_score"] is None
        assert summary["delta_description_vs_baseline"] is None
        assert summary["delta_full_vs_baseline"] is None
        assert summary["verdict"] == "FAIL_POSITIVE_INCOMPLETE"
        assert "baseline" in summary["positive_gate_incomplete"]
        # Rendering is where the raw subtraction used to happen.
        assert eval_mod.render_table("probe", summary)

    def test_the_table_prints_no_delta_across_different_populations(self):
        summary = eval_mod.aggregate(self._partial_baseline())

        table = eval_mod.render_table("probe", summary)

        for mech in ("description", "full"):
            row = [r for r in table.splitlines() if r.startswith(f"| {mech}")]
            assert len(row) == 1
            assert [c.strip() for c in row[0].split("|")][4] == ""

    def test_a_fully_graded_pair_still_publishes_its_delta(self):
        """Negative control. The guard did not simply suppress every delta."""
        summary = eval_mod.aggregate(
            [
                _make_scenario(baseline=1, description=5, full=5),
                _make_scenario(baseline=1, description=5, full=5),
            ]
        )

        assert summary["delta_description_vs_baseline"] == 4.0
        assert summary["delta_full_vs_baseline"] == 4.0


class TestExcludedJudgeFailuresAreDisclosed:
    """A verdict that ignored a recorded failure has to say which one.

    The disclosure fired only when `unreachable_mechanisms` was non-empty,
    which covered the routed exclusion and nothing else. The negative-baseline
    exclusion added alongside it printed nothing, so a reader saw a clean
    `PASS` table over a record holding a judge failure.
    """

    @staticmethod
    def _neg_baseline_broken() -> list[dict]:
        neg = _scenario_of_mechs(
            {
                "baseline": {"scores": {"judge_failed": True}},
                "description": _make_mech(5),
                "full": _make_mech(5),
            }
        )
        neg["negative_case"] = True
        return [_make_scenario(baseline=1, description=5, full=5), neg]

    def test_the_excluded_cell_is_named_in_the_summary(self):
        summary = eval_mod.aggregate(self._neg_baseline_broken())

        assert summary["excluded_judge_failure_cells"] == ["negative baseline"]

    def test_the_table_discloses_the_divergence_without_an_unreachable_mechanism(self):
        summary = eval_mod.aggregate(self._neg_baseline_broken())

        assert summary["unreachable_mechanisms"] == []
        assert summary["verdict"] == "PASS"

        table = eval_mod.render_table("probe", summary)

        disclosure = [r for r in table.splitlines() if r.startswith("Judge failures:")]
        assert len(disclosure) == 1
        assert "1 in the record" in disclosure[0]
        assert "0 on gating surfaces" in disclosure[0]
        assert "negative baseline" in disclosure[0]

    def test_a_run_with_no_divergence_prints_no_disclosure(self):
        """Negative control. The line is a signal, not decoration."""
        summary = eval_mod.aggregate(
            [_make_scenario(baseline=1, description=5, full=5)]
        )

        assert summary["excluded_judge_failure_cells"] == []
        assert "Judge failures:" not in eval_mod.render_table("probe", summary)


class TestBothExclusionsCanFireAtOnce:
    """A routed target can exclude a positive and a negative cell together.

    Each exclusion was tested alone. Together they exercise the branch that
    builds the excluded-cell list across both pools, which is where an
    off-by-one pool key or a shadowed loop variable would show up.
    """

    @staticmethod
    def _both() -> list[dict[str, object]]:
        """A routed run failing in all three cells that gate nothing.

        `full` is unreachable on both sides of a routed target, and the
        negative pool never gates on `baseline`, so all three are excluded.
        """
        broken = _make_mech(0, judge_failed=True)
        return [
            _scenario_of_mechs(
                {
                    "baseline": _make_mech(1),
                    "description": _make_mech(5),
                    "full": broken,
                }
            ),
            _scenario_of_mechs(
                {
                    "baseline": broken,
                    "description": _make_mech(5),
                    "full": broken,
                },
                negative=True,
            ),
        ]

    def test_every_excluded_cell_is_named(self):
        summary = eval_mod.aggregate(self._both(), routed=True)

        assert summary["total_judge_failures"] == 3
        assert summary["gating_judge_failures"] == 0
        assert summary["excluded_judge_failure_cells"] == [
            "positive full",
            "negative baseline",
            "negative full",
        ]
        assert summary["verdict"] == "PASS"

    def test_the_table_names_every_exclusion(self):
        summary = eval_mod.aggregate(self._both(), routed=True)

        table = eval_mod.render_table("r", summary)

        assert "Excluded as unreachable for a routed target: full" in table
        assert "Judge failures: 3 in the record, 0 on gating surfaces" in table
        assert "positive full, negative baseline, negative full" in table


class TestPartialPoolsStillReportObservedHarm:
    """The restraint floor and the deltas treat partial coverage differently.

    A delta needs both sides to cover the same pool, because a difference
    between two populations describes neither. The restraint floor needs only
    one graded cell, because a cell that scored 1.0 is real observed harm
    whatever else went unmeasured. Requiring full coverage there would
    suppress a true harm signal to avoid an incomplete one, which is the
    trade in the wrong direction.

    These are pinned together so that a later pass unifying the two rules has
    to argue with this test rather than quietly lose the harm signal.
    """

    def test_a_partly_graded_negative_pool_still_fails_on_harm(self):
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _make_scenario(baseline=5, description=1, full=1, negative=True),
            _scenario_of_mechs(
                {
                    "baseline": _make_mech(5),
                    "description": _unscored_mech(),
                    "full": _make_mech(5),
                },
                negative=True,
            ),
        ]

        summary = eval_mod.aggregate(scenarios)

        assert summary["negative_gate_incomplete"] == ["description"]
        assert summary["worst_negative_avg"] == 1.0
        assert summary["worst_negative_graded"] == 1
        # Harm outranks incompleteness. The pool is admittedly partial and the
        # verdict still names the harm it did observe.
        assert summary["verdict"] == "FAIL_OVER_ACTIVATION"

    def test_the_same_partial_coverage_suppresses_a_delta(self):
        """The other half of the contrast, on the positive pool."""
        scenarios = [
            _make_scenario(baseline=1, description=5, full=5),
            _scenario_of_mechs(
                {
                    "baseline": _unscored_mech(),
                    "description": _make_mech(5),
                    "full": _make_mech(5),
                }
            ),
        ]

        summary = eval_mod.aggregate(scenarios)

        assert summary["per_mechanism"]["description"]["avg_score"] == 5.0
        assert summary["delta_description_vs_baseline"] is None



class TestTheHeadlineNeedsAWholePool:
    """`best_mechanism` is a ranking, so it needs what a delta needs.

    Reported by an adversarial review that noticed the same summary could
    refuse `delta_full_vs_baseline` for thin coverage and still print
    `Best mechanism: full` off that same thin cell, two lines apart.
    """

    @staticmethod
    def _thin_full() -> list[dict[str, object]]:
        return [
            _make_scenario(baseline=3, description=4, full=5),
            _scenario_of_mechs(
                {
                    "baseline": _make_mech(3),
                    "description": _make_mech(4),
                    "full": _unscored_mech(),
                }
            ),
            _make_scenario(baseline=1, description=5, full=5, negative=True),
        ]

    def test_a_thinner_pool_does_not_take_the_headline(self):
        summary = eval_mod.aggregate(self._thin_full())

        # `full` scores higher, on half the scenarios.
        assert summary["per_mechanism"]["full"]["avg_score"] == 5.0
        assert summary["per_mechanism"]["full"]["graded_count"] == 1
        assert summary["per_mechanism"]["description"]["avg_score"] == 4.0
        assert summary["per_mechanism"]["description"]["graded_count"] == 2

        assert summary["best_mechanism"] == "description"
        assert summary["best_avg_score"] == 4.0

    def test_the_headline_agrees_with_the_delta_beside_it(self):
        summary = eval_mod.aggregate(self._thin_full())

        # The pair that made this a defect: one line refused the comparison,
        # the next line published it.
        assert summary["delta_full_vs_baseline"] is None
        assert summary["best_mechanism"] != "full"

    def test_no_mechanism_fully_graded_says_so_without_claiming_none_ran(self):
        summary = eval_mod.aggregate(
            [
                _make_scenario(baseline=3, description=4, full=5),
                _scenario_of_mechs(
                    {
                        "baseline": _make_mech(3),
                        "description": _unscored_mech(),
                        "full": _unscored_mech(),
                    }
                ),
            ]
        )

        assert summary["best_mechanism"] is None
        assert summary["best_mechanism_partial"] is True
        table = eval_mod.render_table("r", summary)
        assert "Best mechanism: none graded on every scenario" in table
        assert "none measured" not in table

    def test_nothing_graded_at_all_still_says_none_measured(self):
        summary = eval_mod.aggregate(
            [
                _scenario_of_mechs(
                    {
                        "baseline": _unscored_mech(),
                        "description": _unscored_mech(),
                        "full": _unscored_mech(),
                    }
                )
            ]
        )

        assert summary["best_mechanism"] is None
        assert summary["best_mechanism_partial"] is False
        assert "Best mechanism: none measured" in eval_mod.render_table("r", summary)
