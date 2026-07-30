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
        scenarios = [_make_scenario(baseline=0, description=0, full=5)]

        summary = eval_mod.aggregate(scenarios)

        assert summary["baseline_avg"] == 0.0
        assert summary["delta_description_vs_baseline"] == 0.0
        assert summary["delta_full_vs_baseline"] == 5.0
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

    def test_uneven_failure_rates_do_not_invert_ranking(self):
        # full genuinely outscores description, but fails the judge more often.
        # Scoring failures as zero ranked description above full.
        scenarios = [
            _make_scenario(baseline=1, description=2, full=5),
            _make_scenario(baseline=1, description=2, full=5),
        ]
        scenarios[1]["mechanisms"]["full"] = _ungraded_mech()

        summary = eval_mod.aggregate(scenarios)

        assert summary["per_mechanism"]["full"]["avg_score"] == 5.0
        assert summary["per_mechanism"]["description"]["avg_score"] == 2.0
        assert summary["best_mechanism"] == "full"

    def test_ungraded_cell_still_counts_as_a_judge_failure(self):
        scenarios = [_make_scenario(baseline=5, description=5, full=5)]
        scenarios[0]["mechanisms"]["full"] = _ungraded_mech()

        summary = eval_mod.aggregate(scenarios)

        assert summary["per_mechanism"]["full"]["judge_failures"] == 1
        assert summary["total_judge_failures"] >= 1
        assert summary["verdict"] == "FAIL_JUDGE_ERRORS"

    def test_every_cell_ungraded_yields_zero_average_not_a_pass(self):
        scenarios = [_make_scenario(baseline=5, description=5, full=5)]
        for mech in ("baseline", "description", "full"):
            scenarios[0]["mechanisms"][mech] = _ungraded_mech()

        summary = eval_mod.aggregate(scenarios)

        assert summary["per_mechanism"]["description"]["avg_score"] == 0.0
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

        assert "Graded" in table
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
