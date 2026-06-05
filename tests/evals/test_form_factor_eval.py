"""Form-factor eval tests (Issue #1875, follow-on to ADR-058).

Covers the `skill` variant added to scripts/eval/eval-agent-vs-baseline.py and
the form-factor comparison added to scripts/eval/_report_aggregator.py:

- _build_prompt / _resolve_prompt_metadata for the skill variant (pos/neg/edge)
- PlanRunner.build_plan with the three-variant FORM_FACTOR_VARIANTS
- pairwise_bootstrap_ci generalization (any variant pair)
- compute_form_factor verdicts: prefer-agent-form, prefer-skill-form,
  inconclusive, plus the missing-variant and empty-record error paths

No live API calls. All inputs are constructed RunRecords.
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"


def _load_module(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, EVAL_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    types_mod = _load_module("_eval_agent_types.py", "_eval_agent_types")
    scoring_mod = _load_module("_scoring_engine.py", "_scoring_engine")
    plan_mod = _load_module("_plan_runner.py", "_plan_runner")
    adapter_mod = _load_module("_eval_api_adapter.py", "_eval_api_adapter")
    persistence_mod = _load_module("_run_persistence.py", "_run_persistence")
    aggregator_mod = _load_module("_report_aggregator.py", "_report_aggregator")
    writer_mod = _load_module("_report_writer.py", "_report_writer")
    cli_mod = _load_module("eval-agent-vs-baseline.py", "eval_agent_vs_baseline")
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))


Assertion = types_mod.Assertion
AssertionKind = types_mod.AssertionKind
AssertionResult = types_mod.AssertionResult
Fixture = types_mod.Fixture
RunRecord = types_mod.RunRecord

PlanRunner = plan_mod.PlanRunner
VARIANTS = plan_mod.VARIANTS
FORM_FACTOR_VARIANTS = plan_mod.FORM_FACTOR_VARIANTS

compute_form_factor = aggregator_mod.compute_form_factor
pairwise_bootstrap_ci = aggregator_mod.pairwise_bootstrap_ci
_records_by_fixture_variant = aggregator_mod._records_by_fixture_variant
EmptyRunError = aggregator_mod.EmptyRunError


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _fixture(fixture_id: str = "F001") -> Fixture:
    return Fixture(
        id=fixture_id,
        input="Review this code.",
        provenance="synthetic",
        assertions=[Assertion(kind=AssertionKind.VERDICT, expected_value="IDENTIFY")],
    )


def _record(
    fixture_id: str,
    variant: str,
    run_index: int,
    *,
    passed: bool,
    tokens_in: int = 100,
    tokens_out: int = 50,
) -> RunRecord:
    return RunRecord(
        fixture_id=fixture_id,
        variant=variant,
        run_index=run_index,
        model_id="claude-sonnet-4-6",
        prompt_sha="a" * 64,
        prompt_ref="<test>",
        fixture_sha="b" * 64,
        raw_response="IDENTIFY: ok",
        assertions=[
            AssertionResult(
                kind=AssertionKind.VERDICT,
                pattern=None,
                expected_value="IDENTIFY",
                passed=passed,
                extracted="IDENTIFY" if passed else None,
            )
        ],
        outcome="success",
        latency_ms=10.0,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        error_category=None,
        attempts=1,
    )


def _three_variant_records(
    fixture_ids: list[str],
    *,
    agent_passed: bool,
    baseline_passed: bool,
    skill_passed: bool,
    agent_tokens: tuple[int, int] = (100, 50),
    skill_tokens: tuple[int, int] = (100, 50),
    n_runs: int = 3,
) -> list[RunRecord]:
    records: list[RunRecord] = []
    for fid in fixture_ids:
        for ri in range(n_runs):
            records.append(
                _record(
                    fid,
                    "agent",
                    ri,
                    passed=agent_passed,
                    tokens_in=agent_tokens[0],
                    tokens_out=agent_tokens[1],
                )
            )
            records.append(_record(fid, "baseline", ri, passed=baseline_passed))
            records.append(
                _record(
                    fid,
                    "skill",
                    ri,
                    passed=skill_passed,
                    tokens_in=skill_tokens[0],
                    tokens_out=skill_tokens[1],
                )
            )
    return records


# ---------------------------------------------------------------------------
# _build_prompt / _resolve_prompt_metadata: skill variant
# ---------------------------------------------------------------------------


class TestSkillVariantPrompt:
    def test_skill_variant_uses_skill_content_as_system(self):
        system, user = cli_mod._build_prompt(
            "skill", "AGENT", "Review this.", skill_prompt="SKILL CONTENT"
        )
        assert system == "SKILL CONTENT"
        assert user.startswith("Review this.")

    def test_skill_variant_user_suffix_matches_agent_variant(self):
        # The output-shape suffix must be identical across variants so the
        # verdict scorer sees the same contract (methodology symmetry).
        _, agent_user = cli_mod._build_prompt("agent", "AGENT", "X")
        _, skill_user = cli_mod._build_prompt(
            "skill", "AGENT", "X", skill_prompt="SKILL"
        )
        assert agent_user == skill_user

    def test_skill_variant_without_content_raises(self):
        with pytest.raises(ValueError, match="skill variant requires skill_prompt"):
            cli_mod._build_prompt("skill", "AGENT", "X", skill_prompt=None)

    def test_skill_metadata_uses_skill_sha_and_ref(self):
        sha, ref = cli_mod._resolve_prompt_metadata(
            "skill",
            "AGENT",
            "<agent-ref>",
            skill_prompt="SKILL",
            skill_prompt_ref="<skill-ref>",
        )
        assert ref == "<skill-ref>"
        assert sha == cli_mod._sha256_text("SKILL")

    def test_skill_metadata_without_ref_raises(self):
        with pytest.raises(ValueError, match="skill variant requires"):
            cli_mod._resolve_prompt_metadata(
                "skill", "AGENT", "<ref>", skill_prompt="SKILL", skill_prompt_ref=None
            )


# ---------------------------------------------------------------------------
# --skill-path argument validation (path-traversal guard)
# ---------------------------------------------------------------------------


class TestSkillPathArg:
    def test_valid_skill_path_accepted(self):
        value = ".claude/skills/security-review/SKILL.md"
        assert cli_mod._skill_path_arg(value) == value

    def test_traversal_rejected(self):
        import argparse

        with pytest.raises(argparse.ArgumentTypeError):
            cli_mod._skill_path_arg(".claude/skills/../../etc/SKILL.md")

    def test_non_skill_path_rejected(self):
        import argparse

        with pytest.raises(argparse.ArgumentTypeError):
            cli_mod._skill_path_arg("scripts/eval/eval-agent-vs-baseline.py")

    @pytest.mark.parametrize(
        "value",
        [
            "/repo/.claude/skills/security-review/SKILL.md",
            ".claude/skills/security-review/SKILL.md\x00",
            ".claude/skills/security-review/SKILL.md\n",
            ".claude/skills/security-review/SKILL.md\t",
        ],
    )
    def test_hostile_path_inputs_rejected(self, value):
        import argparse

        with pytest.raises(argparse.ArgumentTypeError):
            cli_mod._skill_path_arg(value)


# ---------------------------------------------------------------------------
# PlanRunner: three-variant plan
# ---------------------------------------------------------------------------


class TestThreeVariantPlan:
    def test_default_plan_stays_two_variant(self):
        plan = PlanRunner.build_plan(
            fixtures=[_fixture("F001"), _fixture("F002")],
            model_id="claude-sonnet-4-6",
            n_runs=3,
        )
        # 2 fixtures x 2 variants x 3 runs. Unchanged from v1.
        assert plan.planned_calls == 12
        assert plan.variants == VARIANTS

    def test_form_factor_plan_is_three_variant(self):
        plan = PlanRunner.build_plan(
            fixtures=[_fixture("F001"), _fixture("F002")],
            model_id="claude-sonnet-4-6",
            n_runs=3,
            variants=FORM_FACTOR_VARIANTS,
        )
        # 2 fixtures x 3 variants x 3 runs.
        assert plan.planned_calls == 18
        assert plan.variants == FORM_FACTOR_VARIANTS

    def test_empty_variants_raises(self):
        with pytest.raises(ValueError, match="at least one variant"):
            PlanRunner.build_plan(
                fixtures=[_fixture("F001")],
                model_id="claude-sonnet-4-6",
                variants=(),
            )

    def test_duplicate_variants_raise(self):
        with pytest.raises(ValueError, match="duplicate"):
            PlanRunner.build_plan(
                fixtures=[_fixture("F001")],
                model_id="claude-sonnet-4-6",
                variants=("agent", "agent"),
            )

    def test_unknown_variant_raises(self):
        with pytest.raises(ValueError, match="unsupported variant"):
            PlanRunner.build_plan(
                fixtures=[_fixture("F001")],
                model_id="claude-sonnet-4-6",
                variants=("agent", "baseline", "bogus"),
            )


# ---------------------------------------------------------------------------
# pairwise_bootstrap_ci generalization
# ---------------------------------------------------------------------------


class TestPairwiseBootstrapCi:
    def test_skill_baseline_ci_positive_when_skill_dominates(self):
        records = _three_variant_records(
            ["F001", "F002", "F003"],
            agent_passed=True,
            baseline_passed=False,
            skill_passed=True,
        )
        grouped = _records_by_fixture_variant(records)
        low, high = pairwise_bootstrap_ci(
            grouped,
            ["F001", "F002", "F003"],
            "skill",
            "baseline",
            iterations=200,
            rng=random.Random(1),
        )
        # skill=1.0, baseline=0.0 on every fixture: the delta is a constant 1.0.
        assert low == 1.0
        assert high == 1.0

    def test_empty_fixture_ids_returns_zero_interval(self):
        assert pairwise_bootstrap_ci({}, [], "agent", "skill") == (0.0, 0.0)


# ---------------------------------------------------------------------------
# compute_form_factor verdicts
# ---------------------------------------------------------------------------


class TestComputeFormFactor:
    def test_prefer_agent_form_when_agent_beats_skill_with_ci_above_zero(self):
        # agent passes, skill fails: agent - skill delta is a constant +1.0, so
        # the CI lower bound is > 0 -> the agent form genuinely helps.
        records = _three_variant_records(
            ["F001", "F002", "F003"],
            agent_passed=True,
            baseline_passed=False,
            skill_passed=False,
        )
        result = compute_form_factor(records, iterations=200, rng=random.Random(2))
        assert result.verdict == "prefer-agent-form"
        assert result.agent_skill_ci[0] > 0
        assert result.agent_recall == 1.0
        assert result.skill_recall == 0.0

    def test_prefer_skill_form_when_equal_recall_and_skill_cheaper(self):
        # agent and skill have identical recall (CI spans zero) but the skill
        # variant uses fewer tokens -> prefer the cheaper form.
        records = _three_variant_records(
            ["F001", "F002", "F003"],
            agent_passed=True,
            baseline_passed=False,
            skill_passed=True,
            agent_tokens=(200, 100),
            skill_tokens=(100, 50),
        )
        result = compute_form_factor(records, iterations=200, rng=random.Random(3))
        assert result.verdict == "prefer-skill-form"
        assert result.agent_skill_ci[0] <= 0 <= result.agent_skill_ci[1]
        skill_total = result.skill_tokens_in + result.skill_tokens_out
        agent_total = result.agent_tokens_in + result.agent_tokens_out
        assert skill_total < agent_total

    def test_prefer_skill_form_when_skill_beats_agent_with_ci_below_zero(self):
        records = _three_variant_records(
            ["F001", "F002", "F003"],
            agent_passed=False,
            baseline_passed=False,
            skill_passed=True,
            agent_tokens=(100, 50),
            skill_tokens=(150, 75),
        )

        result = compute_form_factor(records, iterations=200, rng=random.Random(7))

        assert result.verdict == "prefer-skill-form"
        assert result.agent_skill_ci[1] < 0

    def test_inconclusive_when_equal_recall_and_equal_cost(self):
        # Identical recall AND identical cost: no cost reason to prefer either.
        records = _three_variant_records(
            ["F001", "F002", "F003"],
            agent_passed=True,
            baseline_passed=False,
            skill_passed=True,
            agent_tokens=(100, 50),
            skill_tokens=(100, 50),
        )
        result = compute_form_factor(records, iterations=200, rng=random.Random(4))
        assert result.verdict == "inconclusive"

    def test_per_variant_token_usage_is_distinct(self):
        # AC: cost tracking distinguishes per-variant token usage.
        records = _three_variant_records(
            ["F001", "F002"],
            agent_passed=True,
            baseline_passed=True,
            skill_passed=True,
            agent_tokens=(300, 150),
            skill_tokens=(120, 60),
        )
        result = compute_form_factor(records, iterations=100, rng=random.Random(5))
        # 2 fixtures x 3 runs = 6 records per variant.
        assert result.agent_tokens_in == 300 * 6
        assert result.skill_tokens_in == 120 * 6

    def test_missing_skill_variant_raises(self):
        records = [
            _record("F001", "agent", 0, passed=True),
            _record("F001", "baseline", 0, passed=False),
        ]
        with pytest.raises(ValueError, match="missing"):
            compute_form_factor(records)

    def test_missing_variant_for_one_fixture_raises(self):
        records = [
            _record("F001", "agent", 0, passed=True),
            _record("F001", "baseline", 0, passed=False),
            _record("F001", "skill", 0, passed=True),
            _record("F002", "agent", 0, passed=True),
            _record("F002", "baseline", 0, passed=False),
        ]

        with pytest.raises(ValueError, match="same fixture set"):
            compute_form_factor(records)

    def test_excluded_flaky_fixtures_are_removed_from_form_factor(self):
        records = [
            _record("F001", "agent", 0, passed=True),
            _record("F001", "baseline", 0, passed=False),
            _record("F001", "skill", 0, passed=False),
            _record("F002", "agent", 0, passed=False),
            _record("F002", "baseline", 0, passed=False),
            _record("F002", "skill", 0, passed=True),
        ]

        result = compute_form_factor(
            records,
            iterations=200,
            rng=random.Random(13),
            exclude_fixture_ids={"F001"},
        )

        assert result.agent_recall == 0.0
        assert result.baseline_recall == 0.0
        assert result.skill_recall == 1.0

    def test_empty_records_raises(self):
        with pytest.raises(EmptyRunError):
            compute_form_factor([])


class TestReportWriterFormFactor:
    def test_write_includes_form_factor_payload_and_markdown(self, tmp_path):
        records = _three_variant_records(
            ["F001", "F002", "F003"],
            agent_passed=True,
            baseline_passed=False,
            skill_passed=True,
            agent_tokens=(200, 100),
            skill_tokens=(100, 50),
        )
        aggregate = aggregator_mod.ReportAggregator(
            [record for record in records if record.variant != "skill"],
            model_id="claude-sonnet-4-6",
            bootstrap_iterations=200,
        ).aggregate()
        form_factor = compute_form_factor(records, iterations=200, rng=random.Random(11))

        json_path, md_path = writer_mod.ReportWriter(tmp_path / "reports").write(
            aggregate=aggregate,
            run_id="r1",
            model_id="claude-sonnet-4-6",
            agent_prompt_sha="a" * 64,
            baseline_prompt_sha="b" * 64,
            fixture_set_sha="c" * 64,
            wall_clock_seconds=10.0,
            form_factor=form_factor,
        )

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["form_factor"]["verdict"] == "prefer-skill-form"
        assert "agent_skill_ci_95" in payload["form_factor"]
        assert "skill_baseline_ci_95" in payload["form_factor"]
        assert "## Form-Factor Comparison" in md_path.read_text(encoding="utf-8")


class TestDryRunSkillValidation:
    def test_include_skill_dry_run_checks_skill_file(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        fixture = Fixture(
            id="F001",
            input="Review this code.",
            provenance="synthetic",
            assertions=[Assertion(kind=AssertionKind.VERDICT, expected_value="IDENTIFY")],
        )
        (fixtures_dir / "F001.json").write_text(
            json.dumps(
                {
                    "schemaVersion": fixture.schema_version,
                    "id": fixture.id,
                    "input": fixture.input,
                    "provenance": fixture.provenance,
                    "assertions": [
                        {"kind": "verdict", "expected_value": "IDENTIFY"},
                    ],
                }
            ),
            encoding="utf-8",
        )

        rc = cli_mod.main(
            [
                "--agent",
                "security",
                "--fixtures",
                str(fixtures_dir),
                "--dry-run",
                "--include-skill",
            ]
        )

        assert rc == cli_mod.EXIT_CONFIG
        assert "skill prompt not found" in capsys.readouterr().err


class _FakePersistence:
    def written_count(self) -> int:
        return 3

    def skipped_count(self) -> int:
        return 0


class TestGenerateReportFormFactorFailure:
    def test_form_factor_failure_still_writes_v1_report(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
        fixture_path = tmp_path / "F001.json"
        fixture_path.write_text("{}", encoding="utf-8")
        records = [
            _record("F001", "agent", 0, passed=True),
            _record("F001", "baseline", 0, passed=False),
            _record("F001", "skill", 0, passed=True),
            _record("F002", "agent", 0, passed=True),
            _record("F002", "baseline", 0, passed=False),
        ]

        rc = cli_mod._generate_report(
            records=records,
            run_id="r-form-factor-invalid",
            model_id="claude-sonnet-4-6",
            agent="security",
            agent_prompt="agent prompt",
            fixture_paths=[fixture_path],
            wall_clock_seconds=1.0,
            run_dir=tmp_path / "runs" / "r-form-factor-invalid",
            persistence=_FakePersistence(),
            error_count=0,
        )

        assert rc == cli_mod.EXIT_LOGIC
        report_json = (
            tmp_path
            / "evals"
            / "security-spike"
            / "reports"
            / "r-form-factor-invalid"
            / "report.json"
        )
        payload = json.loads(report_json.read_text(encoding="utf-8"))
        assert payload["recommendation"] == "form-factor-invalid"
        assert "form_factor_invalid" in capsys.readouterr().err
