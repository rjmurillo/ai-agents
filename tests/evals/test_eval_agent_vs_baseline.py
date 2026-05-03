"""Unit tests for scripts/eval/eval-agent-vs-baseline.py (T4-1 scaffolding).

Covers:
- ScoringEngine and concrete scorers (REGEX, VERDICT)
- FixtureValidator (REQ-004 AC-4) including schemaVersion guard
- PlanRunner.build_plan (DESIGN-004 §5.3a, REQ-004 AC-8)
- All dataclasses carry schemaVersion=1

No live API calls. T4-2 will add adapter and persistence tests.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"


def _load_module(filename: str, module_name: str):
    """Load a script-style module (filename has hyphens, or sibling helper)."""
    spec = importlib.util.spec_from_file_location(
        module_name, EVAL_DIR / filename
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Sibling modules use plain `from _eval_common import ...` so EVAL_DIR must
# be on sys.path during loading. Scope the mutation, then remove it.
_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    types_mod = _load_module("_eval_agent_types.py", "_eval_agent_types")
    scoring_mod = _load_module("_scoring_engine.py", "_scoring_engine")
    plan_mod = _load_module("_plan_runner.py", "_plan_runner")
    cli_mod = _load_module("eval-agent-vs-baseline.py", "eval_agent_vs_baseline")
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))


Assertion = types_mod.Assertion
AssertionKind = types_mod.AssertionKind
AssertionResult = types_mod.AssertionResult
ExecutionPlan = types_mod.ExecutionPlan
Fixture = types_mod.Fixture
FixtureValidationError = types_mod.FixtureValidationError
Report = types_mod.Report
RunRecord = types_mod.RunRecord
SchemaVersionError = types_mod.SchemaVersionError
SCHEMA_VERSION = types_mod.SCHEMA_VERSION

ScoringEngine = scoring_mod.ScoringEngine
RegexScorer = scoring_mod.RegexScorer
VerdictScorer = scoring_mod.VerdictScorer
build_default_engine = scoring_mod.build_default_engine

PlanRunner = plan_mod.PlanRunner
UnsupportedModelError = plan_mod.UnsupportedModelError

FixtureValidator = cli_mod.FixtureValidator
cli_main = cli_mod.main


# ---------------------------------------------------------------------------
# ScoringEngine
# ---------------------------------------------------------------------------


class TestScoringEngineRegex:
    def test_regex_match_passes(self):
        a = Assertion(kind=AssertionKind.REGEX, pattern=r"CWE-\d+")
        engine = build_default_engine()
        result = engine.score(a, "Found CWE-22 in the source")
        assert result.passed is True
        assert result.extracted == "CWE-22"
        assert result.kind == AssertionKind.REGEX
        assert result.pattern == r"CWE-\d+"
        assert result.expected_value is None

    def test_regex_no_match_fails(self):
        a = Assertion(kind=AssertionKind.REGEX, pattern=r"CWE-\d+")
        engine = build_default_engine()
        result = engine.score(a, "Nothing of interest here")
        assert result.passed is False
        assert result.extracted is None

    def test_regex_case_insensitive(self):
        a = Assertion(kind=AssertionKind.REGEX, pattern="ESCALATE")
        engine = build_default_engine()
        result = engine.score(a, "the answer is escalate")
        assert result.passed is True


class TestScoringEngineVerdict:
    def test_verdict_match(self):
        a = Assertion(kind=AssertionKind.VERDICT, expected_value="IDENTIFY")
        engine = build_default_engine()
        result = engine.score(a, "IDENTIFY: CWE-22 path traversal")
        assert result.passed is True
        assert result.extracted == "IDENTIFY"

    def test_verdict_match_case_insensitive(self):
        a = Assertion(kind=AssertionKind.VERDICT, expected_value="ESCALATE")
        engine = build_default_engine()
        result = engine.score(a, "escalate to security agent now")
        assert result.passed is True
        assert result.extracted == "ESCALATE"

    def test_verdict_mismatch(self):
        a = Assertion(kind=AssertionKind.VERDICT, expected_value="OK")
        engine = build_default_engine()
        result = engine.score(a, "ESCALATE: this is suspicious")
        assert result.passed is False
        assert result.extracted == "ESCALATE"

    def test_verdict_absent_returns_none(self):
        a = Assertion(kind=AssertionKind.VERDICT, expected_value="OK")
        engine = build_default_engine()
        result = engine.score(a, "I don't know what to say")
        assert result.passed is False
        assert result.extracted is None


class TestScoringEngineDispatch:
    def test_unknown_kind_raises(self):
        engine = ScoringEngine()  # empty engine; no scorers registered
        a = Assertion(kind=AssertionKind.REGEX, pattern="x")
        with pytest.raises(ValueError, match="No scorer registered"):
            engine.score(a, "anything")

    def test_score_all_runs_each_assertion(self):
        engine = build_default_engine()
        assertions = [
            Assertion(kind=AssertionKind.VERDICT, expected_value="IDENTIFY"),
            Assertion(kind=AssertionKind.REGEX, pattern=r"CWE-22"),
        ]
        results = engine.score_all(assertions, "IDENTIFY: CWE-22 reported")
        assert len(results) == 2
        assert all(r.passed for r in results)


# ---------------------------------------------------------------------------
# FixtureValidator
# ---------------------------------------------------------------------------


def _write_fixture(dir_: Path, name: str, payload: dict) -> Path:
    path = dir_ / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _valid_fixture_payload(**overrides) -> dict:
    base = {
        "schemaVersion": 1,
        "id": "F001",
        "input": "Review this code for security issues",
        "provenance": "synthetic",
        "assertions": [
            {"kind": "verdict", "expected_value": "IDENTIFY"},
        ],
        "tags": ["cwe-22", "owasp:a01"],
    }
    base.update(overrides)
    return base


class TestFixtureValidatorMissingFields:
    @pytest.mark.parametrize("field", ["id", "input", "provenance"])
    def test_missing_required_field_raises(self, tmp_path, field):
        payload = _valid_fixture_payload()
        del payload[field]
        path = _write_fixture(tmp_path, "F001.json", payload)
        with pytest.raises(FixtureValidationError):
            FixtureValidator.validate_fixtures([path])

    def test_missing_assertions_raises(self, tmp_path):
        payload = _valid_fixture_payload()
        del payload["assertions"]
        path = _write_fixture(tmp_path, "F001.json", payload)
        with pytest.raises(FixtureValidationError, match="assertions"):
            FixtureValidator.validate_fixtures([path])

    def test_empty_assertions_raises(self, tmp_path):
        payload = _valid_fixture_payload(assertions=[])
        path = _write_fixture(tmp_path, "F001.json", payload)
        with pytest.raises(FixtureValidationError, match="assertions"):
            FixtureValidator.validate_fixtures([path])


class TestFixtureValidatorProvenance:
    def test_invalid_provenance_raises(self, tmp_path):
        payload = _valid_fixture_payload(provenance="real-cve-leaked")
        path = _write_fixture(tmp_path, "F001.json", payload)
        with pytest.raises(FixtureValidationError, match="provenance"):
            FixtureValidator.validate_fixtures([path])


class TestFixtureValidatorTags:
    def test_invalid_tag_format_raises(self, tmp_path):
        payload = _valid_fixture_payload(tags=["UPPER_CASE"])
        path = _write_fixture(tmp_path, "F001.json", payload)
        with pytest.raises(FixtureValidationError, match="invalid tag"):
            FixtureValidator.validate_fixtures([path])

    def test_non_list_tags_raises(self, tmp_path):
        payload = _valid_fixture_payload(tags="not-a-list")
        path = _write_fixture(tmp_path, "F001.json", payload)
        with pytest.raises(FixtureValidationError, match="tags"):
            FixtureValidator.validate_fixtures([path])


class TestFixtureValidatorSchemaVersion:
    def test_schema_version_two_raises(self, tmp_path):
        """Reader rejects unknown major version (REQ-004 AC-7)."""
        payload = _valid_fixture_payload(schemaVersion=2)
        path = _write_fixture(tmp_path, "F001.json", payload)
        with pytest.raises(SchemaVersionError):
            FixtureValidator.validate_fixtures([path])

    def test_missing_schema_version_raises(self, tmp_path):
        payload = _valid_fixture_payload()
        del payload["schemaVersion"]
        path = _write_fixture(tmp_path, "F001.json", payload)
        with pytest.raises(SchemaVersionError):
            FixtureValidator.validate_fixtures([path])


class TestFixtureValidatorRoundTrip:
    def test_valid_fixture_round_trips(self, tmp_path):
        payload = _valid_fixture_payload()
        path = _write_fixture(tmp_path, "F001.json", payload)
        fixtures = FixtureValidator.validate_fixtures([path])
        assert len(fixtures) == 1
        f = fixtures[0]
        assert f.id == "F001"
        assert f.provenance == "synthetic"
        assert f.schema_version == 1
        assert len(f.assertions) == 1
        assert f.assertions[0].kind == AssertionKind.VERDICT


# ---------------------------------------------------------------------------
# PlanRunner
# ---------------------------------------------------------------------------


def _make_fixtures(n: int) -> list:
    return [
        Fixture(
            id=f"F{i:03d}",
            input=f"input {i}",
            provenance="synthetic",
            assertions=[
                Assertion(kind=AssertionKind.VERDICT, expected_value="IDENTIFY")
            ],
        )
        for i in range(1, n + 1)
    ]


class TestPlanRunner:
    def test_empty_fixtures_raises(self):
        with pytest.raises(ValueError, match="at least one fixture"):
            PlanRunner.build_plan(fixtures=[], model_id="claude-sonnet-4-6")

    def test_one_fixture_two_variants_three_runs_six_calls(self):
        plan = PlanRunner.build_plan(
            fixtures=_make_fixtures(1),
            model_id="claude-sonnet-4-6",
            n_runs=3,
        )
        assert plan.planned_calls == 6

    def test_ten_fixtures_yields_sixty_calls(self):
        plan = PlanRunner.build_plan(
            fixtures=_make_fixtures(10),
            model_id="claude-sonnet-4-6",
            n_runs=3,
        )
        assert plan.planned_calls == 60

    def test_invalid_n_runs_raises(self):
        with pytest.raises(ValueError, match="n_runs"):
            PlanRunner.build_plan(
                fixtures=_make_fixtures(1),
                model_id="claude-sonnet-4-6",
                n_runs=0,
            )

    def test_unsupported_model_raises(self):
        with pytest.raises(UnsupportedModelError):
            PlanRunner.build_plan(
                fixtures=_make_fixtures(1),
                model_id="model-without-pricing",
            )

    def test_cost_line_format(self):
        plan = PlanRunner.build_plan(
            fixtures=_make_fixtures(1),
            model_id="claude-sonnet-4-6",
            n_runs=3,
        )
        lines = PlanRunner.format_plan_lines(plan)
        cost_line = [line for line in lines if line.startswith("cost_estimate_usd=")]
        assert len(cost_line) == 1
        assert re.match(
            r"^cost_estimate_usd=\d+\.\d+ rate_as_of=\d{4}-\d{2}-\d{2}$",
            cost_line[0],
        )

    def test_plan_carries_schema_version(self):
        plan = PlanRunner.build_plan(
            fixtures=_make_fixtures(1),
            model_id="claude-sonnet-4-6",
        )
        assert plan.schema_version == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Schema version sanity (every serializable dataclass carries schemaVersion=1)
# ---------------------------------------------------------------------------


class TestDataclassSchemaVersions:
    def test_fixture_default_schema_version(self):
        f = Fixture(
            id="F001",
            input="x",
            provenance="synthetic",
            assertions=[Assertion(kind=AssertionKind.REGEX, pattern="x")],
        )
        assert f.schema_version == 1

    def test_run_record_default_schema_version(self):
        record = RunRecord(
            fixture_id="F001",
            variant="agent",
            run_index=0,
            model_id="claude-sonnet-4-6",
            prompt_sha="x" * 64,
            prompt_ref="templates/agents/security.shared.md",
            fixture_sha="y" * 64,
            raw_response="IDENTIFY: ok",
            assertions=[],
            outcome="success",
            latency_ms=10.0,
            tokens_in=10,
            tokens_out=20,
            error_category=None,
            attempts=1,
        )
        assert record.schema_version == 1

    def test_report_default_schema_version(self):
        report = Report(
            run_id="r",
            model_id="claude-sonnet-4-6",
            agent_prompt_sha="a",
            baseline_prompt_sha="b",
            fixture_set_sha="c",
            agent_recall=0.0,
            baseline_recall=0.0,
            recall_delta=0.0,
            bootstrap_ci_95=(0.0, 0.0),
            recall_with_errors=0.0,
            recall_excluding_errors=0.0,
            per_fixture_pass_rates={},
            flakiness=False,
            total_tokens_in=0,
            total_tokens_out=0,
            wall_clock_seconds=0.0,
            cost_estimate_usd=0.0,
            error_count=0,
            pricing_rate_as_of="2026-05-03",
        )
        assert report.schema_version == 1
        assert report.recommendation is None  # T4-5 leaves null; T4-7 sets

    def test_assertion_requires_pattern_or_expected_value(self):
        with pytest.raises(ValueError):
            Assertion(kind=AssertionKind.REGEX)


# ---------------------------------------------------------------------------
# CLI exit codes
# ---------------------------------------------------------------------------


class TestCliExitCodes:
    def test_missing_fixtures_dir_exits_two(self, tmp_path, capsys):
        missing = tmp_path / "does-not-exist"
        rc = cli_main([
            "--dry-run",
            "--agent",
            "security",
            "--fixtures",
            str(missing),
        ])
        assert rc == 2
        captured = capsys.readouterr()
        assert "no fixtures found" in captured.err

    def test_empty_fixtures_dir_exits_two(self, tmp_path, capsys):
        empty = tmp_path / "fixtures"
        empty.mkdir()
        rc = cli_main([
            "--dry-run",
            "--agent",
            "security",
            "--fixtures",
            str(empty),
        ])
        assert rc == 2
        captured = capsys.readouterr()
        assert "no fixtures found" in captured.err

    def test_dry_run_with_valid_fixtures_exits_zero(self, tmp_path, capsys):
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        _write_fixture(fixtures_dir, "F001.json", _valid_fixture_payload())
        rc = cli_main([
            "--dry-run",
            "--agent",
            "security",
            "--fixtures",
            str(fixtures_dir),
        ])
        assert rc == 0
        captured = capsys.readouterr()
        assert "planned_calls=6" in captured.out
        assert "cost_estimate_usd=" in captured.out
        assert "rate_as_of=" in captured.out
