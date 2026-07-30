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
        ],
    )
    def test_malformed_judge_score_object_sets_judge_failed(
        self, monkeypatch, judge_json
    ):
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
    expected_skill = (
        REPO_ROOT / ".claude" / "skills" / "software-engineering-library" / "SKILL.md"
    )
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
            (10, 5),
            ("4", 4),
            ("abc", 0),
            (None, 0),
            (True, 1),  # bool is int subclass; True -> 1, False -> 0
            (3.7, 3),  # float coerces to int via int()
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

        _rule_id, result, calls = eval_mod._process_one_rule(
            "key", scenarios_data, rule_path, args
        )

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


def test_extract_json_object_skips_leading_cli_tool_trace():
    text = (
        "\u25cf List working directory contents (shell)\n"
        "  \u2502 ls -la /tmp/eval-copilot-abc 2>&1 | head -50\n"
        "  \u2514 4 lines\u2026\n\n" + _JUDGE
    )
    assert eval_mod._extract_json_object(text) == _JUDGE


def test_extract_json_object_drops_trailing_prose():
    assert (
        eval_mod._extract_json_object(_JUDGE + "\n\nLet me know if you want more.")
        == _JUDGE
    )


def test_extract_json_object_handles_nested_objects():
    text = 'noise {"a": {"b": 1}, "c": 2} tail'
    assert eval_mod._extract_json_object(text) == '{"a": {"b": 1}, "c": 2}'


def test_extract_json_object_returns_none_without_any_brace():
    assert eval_mod._extract_json_object("I cannot score this response.") is None


def test_extract_json_object_returns_none_on_unbalanced_object():
    assert eval_mod._extract_json_object('{"activation_score": 5') is None


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


def test_extract_json_object_advances_past_unbalanced_leading_candidate():
    text = '{ unterminated\n' + _JUDGE
    assert eval_mod._extract_json_object(text) == _JUDGE


def test_extract_json_object_result_parses_as_json():
    text = "trace line\n" + _JUDGE + "\ntrailing"
    extracted = eval_mod._extract_json_object(text)
    assert extracted is not None
    assert json.loads(extracted)["activation_score"] == 5


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
    return {
        "scores": eval_mod._reduce_score_samples(
            [_sample(0, judge_failed=True)], "median"
        )
    }


class TestReduceScoreSamples:
    def test_all_samples_graded_reduces_normally(self):
        reduced = eval_mod._reduce_score_samples(
            [_sample(5), _sample(3), _sample(4)], "median"
        )
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
