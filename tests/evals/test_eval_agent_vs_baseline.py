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

AnthropicAPIAdapter = adapter_mod.AnthropicAPIAdapter
APICallResult = adapter_mod.APICallResult
ERR_RATE_LIMIT = adapter_mod.ERR_RATE_LIMIT
ERR_SERVER_ERROR = adapter_mod.ERR_SERVER_ERROR
ERR_TIMEOUT = adapter_mod.ERR_TIMEOUT
ERR_CLIENT_ERROR = adapter_mod.ERR_CLIENT_ERROR

RunPersistence = persistence_mod.RunPersistence
DuplicateRunError = persistence_mod.DuplicateRunError

ReportAggregator = aggregator_mod.ReportAggregator
AggregateResult = aggregator_mod.AggregateResult
ReportWriter = writer_mod.ReportWriter

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


# ===========================================================================
# T4-2: AnthropicAPIAdapter (mocked transport)
# ===========================================================================


class _FakeTransport:
    """Records calls and returns scripted responses or raises scripted errors.

    `script` is a list where each element is either a `str` (success body) or
    a callable that raises an exception. The transport advances through the
    script on each call; running off the end raises IndexError so tests
    notice unintended extra retries.
    """

    def __init__(self, script: list):
        self.script = list(script)
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, prompt: str, model_id: str, system: str) -> str:
        self.calls.append((prompt, model_id, system))
        item = self.script.pop(0)
        if isinstance(item, str):
            return item
        item()  # callable that raises
        raise AssertionError("script item must return str or raise")


def _http_error(code: int) -> Exception:
    return RuntimeError(f"Anthropic API returned HTTP {code}: ...")


def _timeout_error() -> Exception:
    return RuntimeError("Anthropic API request timed out after 120s. ...")


class TestAnthropicAPIAdapterSuccess:
    def test_first_call_succeeds(self):
        transport = _FakeTransport(script=["IDENTIFY: ok"])
        adapter = AnthropicAPIAdapter(
            transport=transport, sleep=lambda _s: None
        )
        result = adapter.call_model(
            prompt="hi",
            model_id="claude-sonnet-4-6",
            fixture_id="F001",
            variant="agent",
            run_index=0,
        )
        assert result.outcome == "success"
        assert result.raw_response == "IDENTIFY: ok"
        assert result.attempts == 1
        assert result.error_category is None
        assert result.tokens_in > 0
        assert result.tokens_out > 0
        assert result.latency_ms >= 0

    def test_429_then_success_categorizes_rate_limit(self):
        transport = _FakeTransport(
            script=[lambda: (_ for _ in ()).throw(_http_error(429)), "OK"]
        )
        adapter = AnthropicAPIAdapter(
            transport=transport, sleep=lambda _s: None
        )
        result = adapter.call_model(
            prompt="x",
            model_id="claude-sonnet-4-6",
            fixture_id="F002",
            variant="baseline",
            run_index=0,
        )
        assert result.outcome == "success"
        assert result.attempts == 2
        assert result.raw_response == "OK"

    def test_timeout_then_success(self):
        transport = _FakeTransport(
            script=[lambda: (_ for _ in ()).throw(_timeout_error()), "ESCALATE"]
        )
        adapter = AnthropicAPIAdapter(
            transport=transport, sleep=lambda _s: None
        )
        result = adapter.call_model(
            prompt="x",
            model_id="claude-sonnet-4-6",
            fixture_id="F003",
            variant="agent",
            run_index=1,
        )
        assert result.outcome == "success"
        assert result.attempts == 2


class TestAnthropicAPIAdapterErrors:
    def test_500_retried_then_error(self):
        transport = _FakeTransport(
            script=[
                lambda: (_ for _ in ()).throw(_http_error(500)),
                lambda: (_ for _ in ()).throw(_http_error(500)),
                lambda: (_ for _ in ()).throw(_http_error(500)),
            ]
        )
        adapter = AnthropicAPIAdapter(
            transport=transport, sleep=lambda _s: None
        )
        result = adapter.call_model(
            prompt="x",
            model_id="claude-sonnet-4-6",
            fixture_id="F004",
            variant="agent",
            run_index=0,
        )
        assert result.outcome == "error"
        assert result.error_category == ERR_SERVER_ERROR
        assert result.attempts == 3
        assert result.raw_response is None

    def test_400_immediate_error_no_retry(self):
        transport = _FakeTransport(
            script=[lambda: (_ for _ in ()).throw(_http_error(400))]
        )
        adapter = AnthropicAPIAdapter(
            transport=transport, sleep=lambda _s: None
        )
        result = adapter.call_model(
            prompt="x",
            model_id="claude-sonnet-4-6",
            fixture_id="F005",
            variant="agent",
            run_index=0,
        )
        assert result.outcome == "error"
        assert result.error_category == ERR_CLIENT_ERROR
        assert result.attempts == 1

    def test_408_retried_then_success(self):
        transport = _FakeTransport(
            script=[lambda: (_ for _ in ()).throw(_http_error(408)), "OK"]
        )
        adapter = AnthropicAPIAdapter(
            transport=transport, sleep=lambda _s: None
        )
        result = adapter.call_model(
            prompt="x",
            model_id="claude-sonnet-4-6",
            fixture_id="F006",
            variant="agent",
            run_index=0,
        )
        assert result.outcome == "success"
        assert result.attempts == 2


class TestAnthropicAPIAdapterLogging:
    def test_no_api_key_in_log_lines(self, monkeypatch, capsys):
        secret = "sk-ant-FAKEKEY-DO-NOT-LEAK-1234567890"
        monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
        transport = _FakeTransport(
            script=[
                lambda: (_ for _ in ()).throw(_http_error(429)),
                "scored response",
            ]
        )
        adapter = AnthropicAPIAdapter(
            transport=transport, sleep=lambda _s: None
        )
        adapter.call_model(
            prompt="user prompt",
            model_id="claude-sonnet-4-6",
            fixture_id="F007",
            variant="agent",
            run_index=0,
            system="system prompt",
        )
        captured = capsys.readouterr()
        # Both stdout and stderr must be free of the secret.
        assert secret not in captured.err
        assert secret not in captured.out
        # Two structured log lines (one per attempt).
        log_lines = [ln for ln in captured.err.splitlines() if ln.startswith("{")]
        assert len(log_lines) == 2
        for line in log_lines:
            payload = json.loads(line)
            assert payload["fixture_id"] == "F007"
            assert "attempt" in payload
            assert "outcome" in payload


# ===========================================================================
# T4-2: RunPersistence
# ===========================================================================


def _make_record(
    fixture_id: str = "F001",
    variant: str = "agent",
    run_index: int = 0,
    outcome: str = "success",
) -> RunRecord:
    return RunRecord(
        fixture_id=fixture_id,
        variant=variant,
        run_index=run_index,
        model_id="claude-sonnet-4-6",
        prompt_sha="a" * 64,
        prompt_ref="templates/agents/security.shared.md",
        fixture_sha="b" * 64,
        raw_response="IDENTIFY: ok",
        assertions=[
            AssertionResult(
                kind=AssertionKind.VERDICT,
                pattern=None,
                expected_value="IDENTIFY",
                passed=True,
                extracted="IDENTIFY",
            )
        ],
        outcome=outcome,
        latency_ms=100.0,
        tokens_in=10,
        tokens_out=20,
        error_category=None,
        attempts=1,
    )


class TestRunPersistenceFresh:
    def test_first_write_succeeds(self, tmp_path):
        persistence = RunPersistence(tmp_path / "run-1", resume=False)
        wrote = persistence.write_record(_make_record())
        assert wrote is True
        assert persistence.jsonl_path.exists()
        line = persistence.jsonl_path.read_text(encoding="utf-8").strip()
        payload = json.loads(line)
        assert payload["fixture_id"] == "F001"
        assert payload["schemaVersion"] == 1
        assert payload["assertions"][0]["kind"] == "verdict"

    def test_duplicate_write_raises_in_fresh_mode(self, tmp_path):
        persistence = RunPersistence(tmp_path / "run-2", resume=False)
        persistence.write_record(_make_record())
        with pytest.raises(DuplicateRunError, match="duplicate"):
            persistence.write_record(_make_record())

    def test_duplicate_message_includes_path_and_key(self, tmp_path):
        persistence = RunPersistence(tmp_path / "run-3", resume=False)
        persistence.write_record(_make_record(fixture_id="F009"))
        try:
            persistence.write_record(_make_record(fixture_id="F009"))
        except DuplicateRunError as exc:
            assert "F009" in str(exc)
            assert "runs.jsonl" in str(exc)
        else:
            pytest.fail("expected DuplicateRunError")


class TestRunPersistenceResume:
    def test_resume_skips_existing_triple(self, tmp_path):
        run_dir = tmp_path / "run-resume"
        first = RunPersistence(run_dir, resume=False)
        first.write_record(_make_record())
        # Second open in resume mode: same triple is "already done".
        second = RunPersistence(run_dir, resume=True)
        wrote = second.write_record(_make_record())
        assert wrote is False
        assert second.skipped_count() == 1
        assert second.written_count() == 0
        # Different triple still writes.
        wrote_other = second.write_record(_make_record(run_index=1))
        assert wrote_other is True
        assert second.written_count() == 1

    def test_resume_loads_keys_from_disk(self, tmp_path):
        run_dir = tmp_path / "run-load"
        run_dir.mkdir()
        # Hand-craft a JSONL file with two records.
        persistence = RunPersistence(run_dir, resume=True)
        persistence.write_record(_make_record(run_index=0))
        persistence.write_record(_make_record(run_index=1))
        # Reopen: both keys should be visible.
        reopened = RunPersistence(run_dir, resume=True)
        assert reopened.is_completed("F001", "agent", 0)
        assert reopened.is_completed("F001", "agent", 1)
        assert not reopened.is_completed("F001", "agent", 2)


class TestRunPersistenceJsonlRoundTrip:
    def test_iter_records_round_trips(self, tmp_path):
        persistence = RunPersistence(tmp_path / "rt", resume=False)
        original = _make_record()
        persistence.write_record(original)
        # Round-trip via iter_records.
        records = list(persistence.iter_records())
        assert len(records) == 1
        assert records[0].fixture_id == original.fixture_id
        assert records[0].variant == original.variant
        assert records[0].run_index == original.run_index
        assert records[0].schema_version == 1


class TestRunPersistenceSchemaGuard:
    def test_record_with_wrong_schema_version_raises(self, tmp_path):
        persistence = RunPersistence(tmp_path / "sv", resume=False)
        record = _make_record()
        # Mutate the schema_version on the dataclass (frozen=False on RunRecord).
        record.schema_version = 99
        with pytest.raises(DuplicateRunError, match="schemaVersion"):
            persistence.write_record(record)


# ===========================================================================
# T4-2: CLI integration with mocked adapter
# ===========================================================================


class _StubAdapter:
    """Adapter substitute. Returns scripted APICallResults by call order."""

    def __init__(self, results: list):
        self.results = list(results)
        self.call_count = 0

    def call_model(self, **_kwargs):
        self.call_count += 1
        return self.results.pop(0)


class TestRunnerLiveLoop:
    def _setup(self, tmp_path, monkeypatch):
        # Steer the runner at a temporary REPO_ROOT so writes land under tmp_path.
        agents_dir = tmp_path / "templates" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "security.shared.md").write_text(
            "you are the security agent prompt", encoding="utf-8"
        )
        monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
        # Stub the adapter constructor.
        return agents_dir

    def test_live_run_writes_jsonl_and_no_secret_in_logs(
        self, tmp_path, monkeypatch, capsys
    ):
        self._setup(tmp_path, monkeypatch)
        secret = "sk-ant-MUST-NOT-LEAK-9999"
        monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        _write_fixture(
            fixtures_dir,
            "F001.json",
            _valid_fixture_payload(),
        )

        # 6 calls = 1 fixture × 2 variants × 3 runs.
        results = [
            APICallResult(
                outcome="success",
                raw_response="IDENTIFY: clean",
                tokens_in=50,
                tokens_out=20,
                latency_ms=10.0,
                error_category=None,
                attempts=1,
            )
            for _ in range(6)
        ]
        adapter = _StubAdapter(results)
        monkeypatch.setattr(cli_mod, "AnthropicAPIAdapter", lambda: adapter)

        rc = cli_main([
            "--agent",
            "security",
            "--fixtures",
            str(fixtures_dir),
            "--n-runs",
            "3",
        ])
        assert rc == 0
        assert adapter.call_count == 6
        # Captured logs MUST NOT contain the API key.
        captured = capsys.readouterr()
        assert secret not in captured.err
        assert secret not in captured.out
        # JSONL file exists with 6 lines.
        run_dirs = list((tmp_path / "evals" / "security-spike" / "runs").iterdir())
        assert len(run_dirs) == 1
        jsonl = run_dirs[0] / "runs.jsonl"
        lines = [ln for ln in jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 6
        for line in lines:
            payload = json.loads(line)
            assert payload["schemaVersion"] == 1
            assert payload["model_id"] == "claude-sonnet-4-6"

    def test_resume_does_not_recall_completed_triples(
        self, tmp_path, monkeypatch
    ):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-resume2")
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        _write_fixture(fixtures_dir, "F001.json", _valid_fixture_payload())

        # First run: complete all 6 calls.
        all_six = [
            APICallResult(
                outcome="success",
                raw_response="IDENTIFY: ok",
                tokens_in=10,
                tokens_out=5,
                latency_ms=5.0,
                error_category=None,
                attempts=1,
            )
            for _ in range(6)
        ]
        adapter1 = _StubAdapter(list(all_six))
        monkeypatch.setattr(cli_mod, "AnthropicAPIAdapter", lambda: adapter1)
        run_id = "20260503T130000Z-cafebabe"
        rc = cli_main([
            "--agent",
            "security",
            "--fixtures",
            str(fixtures_dir),
            "--n-runs",
            "3",
            "--run-id",
            run_id,
        ])
        assert rc == 0
        assert adapter1.call_count == 6

        # Resume: adapter should not be called at all because all 6 triples
        # are already completed.
        adapter2 = _StubAdapter([])  # empty: any call would IndexError
        monkeypatch.setattr(cli_mod, "AnthropicAPIAdapter", lambda: adapter2)
        rc2 = cli_main([
            "--agent",
            "security",
            "--fixtures",
            str(fixtures_dir),
            "--n-runs",
            "3",
            "--resume",
            run_id,
        ])
        assert rc2 == 0
        assert adapter2.call_count == 0

    def test_error_rate_above_10pct_exits_one(self, tmp_path, monkeypatch, capsys):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-err")
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        _write_fixture(fixtures_dir, "F001.json", _valid_fixture_payload())

        # All 6 calls error → 100% error rate → exits 1.
        all_errors = [
            APICallResult(
                outcome="error",
                raw_response=None,
                tokens_in=0,
                tokens_out=0,
                latency_ms=5.0,
                error_category=ERR_SERVER_ERROR,
                attempts=3,
            )
            for _ in range(6)
        ]
        adapter = _StubAdapter(all_errors)
        monkeypatch.setattr(cli_mod, "AnthropicAPIAdapter", lambda: adapter)
        rc = cli_main([
            "--agent",
            "security",
            "--fixtures",
            str(fixtures_dir),
            "--n-runs",
            "3",
        ])
        assert rc == 1
        captured = capsys.readouterr()
        assert "error rate exceeds 10%" in captured.err


# ===========================================================================
# T4-3: ReportAggregator
# ===========================================================================


def _success_record(
    fixture_id: str,
    variant: str,
    run_index: int,
    *,
    passed: bool = True,
    n_assertions: int = 1,
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
            for _ in range(n_assertions)
        ],
        outcome="success",
        latency_ms=10.0,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        error_category=None,
        attempts=1,
    )


def _error_record(fixture_id: str, variant: str, run_index: int) -> RunRecord:
    return RunRecord(
        fixture_id=fixture_id,
        variant=variant,
        run_index=run_index,
        model_id="claude-sonnet-4-6",
        prompt_sha="a" * 64,
        prompt_ref="<test>",
        fixture_sha="b" * 64,
        raw_response=None,
        assertions=[
            AssertionResult(
                kind=AssertionKind.VERDICT,
                pattern=None,
                expected_value="IDENTIFY",
                passed=False,
                extracted=None,
            )
        ],
        outcome="error",
        latency_ms=10.0,
        tokens_in=0,
        tokens_out=0,
        error_category="server_error",
        attempts=3,
    )


def _build_records(
    fixture_ids: list[str],
    *,
    agent_passed: bool,
    baseline_passed: bool,
    n_runs: int = 3,
) -> list[RunRecord]:
    records: list[RunRecord] = []
    for fid in fixture_ids:
        for ri in range(n_runs):
            records.append(
                _success_record(fid, "agent", ri, passed=agent_passed)
            )
            records.append(
                _success_record(fid, "baseline", ri, passed=baseline_passed)
            )
    return records


class TestReportAggregatorRecall:
    def test_all_pass_recall_is_one(self):
        records = _build_records(
            ["F001", "F002"], agent_passed=True, baseline_passed=True
        )
        result = ReportAggregator(records, model_id="claude-sonnet-4-6").aggregate()
        assert result.agent_recall == 1.0
        assert result.baseline_recall == 1.0
        assert result.recall_delta == 0.0

    def test_all_fail_recall_is_zero(self):
        records = _build_records(
            ["F001", "F002"], agent_passed=False, baseline_passed=False
        )
        result = ReportAggregator(records, model_id="claude-sonnet-4-6").aggregate()
        assert result.agent_recall == 0.0
        assert result.baseline_recall == 0.0

    def test_recall_with_errors_includes_errors_in_denominator(self):
        # 1 success run, 1 error run (agent variant). Both variants identical
        # for symmetry; we focus on the agent recall fields.
        records = [
            _success_record("F001", "agent", 0, passed=True),
            _error_record("F001", "agent", 1),
            _success_record("F001", "baseline", 0, passed=True),
            _success_record("F001", "baseline", 1, passed=True),
        ]
        result = ReportAggregator(records, model_id="claude-sonnet-4-6").aggregate()
        # Agent: 1 passed, 2 total assertions → recall_with_errors = 0.5.
        # Excluding errors: 1 passed, 1 total → recall_excluding_errors = 1.0.
        assert result.recall_with_errors == 0.5
        assert result.recall_excluding_errors == 1.0
        assert result.error_count == 1

    def test_recall_uses_assertion_count_not_fixture_count(self):
        # One fixture, two assertions on the same response — recall denom
        # MUST be the assertion count (2), not the fixture count (1).
        record = RunRecord(
            fixture_id="F001",
            variant="agent",
            run_index=0,
            model_id="claude-sonnet-4-6",
            prompt_sha="a" * 64,
            prompt_ref="<test>",
            fixture_sha="b" * 64,
            raw_response="IDENTIFY",
            assertions=[
                AssertionResult(
                    kind=AssertionKind.VERDICT,
                    pattern=None,
                    expected_value="IDENTIFY",
                    passed=True,
                    extracted="IDENTIFY",
                ),
                AssertionResult(
                    kind=AssertionKind.REGEX,
                    pattern="CWE-22",
                    expected_value=None,
                    passed=False,
                    extracted=None,
                ),
            ],
            outcome="success",
            latency_ms=10.0,
            tokens_in=10,
            tokens_out=5,
            error_category=None,
            attempts=1,
        )
        result = ReportAggregator(
            [record], model_id="claude-sonnet-4-6"
        ).aggregate()
        # 1 passed of 2 assertions → 0.5.
        assert result.agent_recall == 0.5


class TestReportAggregatorCI:
    def test_ci_bounds_are_real_numbers(self):
        records = _build_records(
            ["F001", "F002", "F003"],
            agent_passed=True,
            baseline_passed=False,
        )
        # Use a small bootstrap iteration count to keep the test fast; the
        # public default is 10000.
        result = ReportAggregator(
            records,
            model_id="claude-sonnet-4-6",
            bootstrap_iterations=200,
            rng=__import__("random").Random(123),
        ).aggregate()
        ci_low, ci_high = result.bootstrap_ci_95
        assert isinstance(ci_low, float)
        assert isinstance(ci_high, float)
        assert ci_low <= ci_high

    def test_ci_for_identical_variants_centered_on_zero(self):
        records = _build_records(
            ["F001", "F002", "F003"],
            agent_passed=True,
            baseline_passed=True,
        )
        result = ReportAggregator(
            records,
            model_id="claude-sonnet-4-6",
            bootstrap_iterations=500,
        ).aggregate()
        ci_low, ci_high = result.bootstrap_ci_95
        assert ci_low == 0.0
        assert ci_high == 0.0


class TestReportAggregatorFlakiness:
    def test_identical_runs_no_flakiness(self):
        records = _build_records(
            ["F001", "F002"], agent_passed=True, baseline_passed=False
        )
        result = ReportAggregator(records, model_id="claude-sonnet-4-6").aggregate()
        assert result.flakiness is False
        assert result.flaky_fixtures_excluded == []

    def test_synthetic_variance_marks_flaky(self):
        # F001 agent variant: pass / fail / pass → variance > 0.
        records = [
            _success_record("F001", "agent", 0, passed=True),
            _success_record("F001", "agent", 1, passed=False),
            _success_record("F001", "agent", 2, passed=True),
            _success_record("F002", "agent", 0, passed=True),
            _success_record("F002", "agent", 1, passed=True),
            _success_record("F002", "agent", 2, passed=True),
            _success_record("F001", "baseline", 0, passed=False),
            _success_record("F001", "baseline", 1, passed=False),
            _success_record("F001", "baseline", 2, passed=False),
            _success_record("F002", "baseline", 0, passed=False),
            _success_record("F002", "baseline", 1, passed=False),
            _success_record("F002", "baseline", 2, passed=False),
        ]
        result = ReportAggregator(records, model_id="claude-sonnet-4-6").aggregate()
        assert result.flakiness is True
        # 1 of 2 fixtures flaky = 50%, > 30% halt threshold.
        assert result.halt_due_to_flakiness is True

    def test_one_flaky_of_four_excluded_not_halted(self):
        # F001 flaky; F002, F003, F004 stable. 25% flaky → ≤ 30%, no halt.
        records: list = []
        for fid in ("F002", "F003", "F004"):
            for ri in range(3):
                records.append(_success_record(fid, "agent", ri, passed=True))
                records.append(_success_record(fid, "baseline", ri, passed=False))
        # F001 agent variance.
        records += [
            _success_record("F001", "agent", 0, passed=True),
            _success_record("F001", "agent", 1, passed=False),
            _success_record("F001", "agent", 2, passed=True),
            _success_record("F001", "baseline", 0, passed=False),
            _success_record("F001", "baseline", 1, passed=False),
            _success_record("F001", "baseline", 2, passed=False),
        ]
        result = ReportAggregator(
            records, model_id="claude-sonnet-4-6", bootstrap_iterations=200
        ).aggregate()
        assert result.flakiness is True
        assert result.halt_due_to_flakiness is False
        assert result.flaky_fixtures_excluded == ["F001"]
        # Stable subset: F002 F003 F004, agent always passes → recall = 1.0.
        assert result.agent_recall == 1.0
        assert result.baseline_recall == 0.0


class TestReportAggregatorCost:
    def test_cost_uses_pricing_constants(self):
        records = _build_records(
            ["F001"], agent_passed=True, baseline_passed=True
        )
        result = ReportAggregator(records, model_id="claude-sonnet-4-6").aggregate()
        # 6 records × tokens_in=100, tokens_out=50.
        # cost = (600 * 0.003 + 300 * 0.015) / 1000 = (1.8 + 4.5)/1000 = 0.0063
        assert result.cost_estimate_usd == pytest.approx(0.0063)
        assert result.pricing_rate_as_of == "2026-05-03"


# ===========================================================================
# T4-3: ReportWriter
# ===========================================================================


class TestReportWriter:
    def _aggregate(self) -> AggregateResult:
        return AggregateResult(
            agent_recall=0.82,
            baseline_recall=0.60,
            recall_delta=0.22,
            bootstrap_ci_95=(0.10, 0.34),
            recall_with_errors=0.80,
            recall_excluding_errors=0.82,
            per_fixture_pass_rates={
                "F001": {"agent": [1.0, 1.0, 1.0], "baseline": [0.5, 0.5, 0.5]},
            },
            flakiness=False,
            flaky_fixtures_excluded=[],
            total_tokens_in=15360,
            total_tokens_out=2400,
            cost_estimate_usd=0.09,
            pricing_rate_as_of="2026-05-03",
            error_count=0,
            halt_due_to_flakiness=False,
        )

    def test_writes_both_files_atomically(self, tmp_path):
        writer = ReportWriter(tmp_path / "reports")
        json_path, md_path = writer.write(
            aggregate=self._aggregate(),
            run_id="20260503T140000Z-aaaaaaaa",
            model_id="claude-sonnet-4-6",
            agent_prompt_sha="a" * 64,
            baseline_prompt_sha="b" * 64,
            fixture_set_sha="c" * 64,
            wall_clock_seconds=187.0,
        )
        assert json_path.exists()
        assert md_path.exists()
        # No leftover .tmp files in the directory.
        leftovers = list(json_path.parent.glob(".*tmp"))
        assert leftovers == []

    def test_report_json_schema_fields(self, tmp_path):
        writer = ReportWriter(tmp_path / "reports")
        json_path, _ = writer.write(
            aggregate=self._aggregate(),
            run_id="r1",
            model_id="claude-sonnet-4-6",
            agent_prompt_sha="a" * 64,
            baseline_prompt_sha="b" * 64,
            fixture_set_sha="c" * 64,
            wall_clock_seconds=10.0,
        )
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        # Required schema fields per DESIGN-004 §5.6.
        for key in (
            "schemaVersion",
            "run_id",
            "model_id",
            "agent_prompt_sha",
            "baseline_prompt_sha",
            "fixture_set_sha",
            "agent_recall",
            "baseline_recall",
            "recall_delta",
            "bootstrap_ci_95",
            "recall_with_errors",
            "recall_excluding_errors",
            "per_fixture_pass_rates",
            "flakiness",
            "flaky_fixtures_excluded",
            "total_tokens_in",
            "total_tokens_out",
            "wall_clock_seconds",
            "cost_estimate_usd",
            "error_count",
            "pricing_rate_as_of",
            "recommendation",
        ):
            assert key in payload, f"missing field: {key}"
        assert payload["schemaVersion"] == 1
        assert payload["recommendation"] is None  # T4-7 fills in

    def test_report_md_contains_required_sections(self, tmp_path):
        writer = ReportWriter(tmp_path / "reports")
        _, md_path = writer.write(
            aggregate=self._aggregate(),
            run_id="r2",
            model_id="claude-sonnet-4-6",
            agent_prompt_sha="a" * 64,
            baseline_prompt_sha="b" * 64,
            fixture_set_sha="c" * 64,
            wall_clock_seconds=10.0,
        )
        body = md_path.read_text(encoding="utf-8")
        for heading in (
            "# Eval Report:",
            "## Summary",
            "## Per-Fixture Pass Rates",
            "## Confidence Interval",
            "## Recommendation",
            "## Cost and Resource Summary",
            "## Flakiness",
        ):
            assert heading in body, f"missing heading: {heading}"


# ===========================================================================
# T4-3: end-to-end runner with report
# ===========================================================================


class TestRunnerEndToEndReport:
    def _setup(self, tmp_path, monkeypatch):
        agents_dir = tmp_path / "templates" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "security.shared.md").write_text(
            "agent prompt", encoding="utf-8"
        )
        monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
        return agents_dir

    def test_e2e_writes_report(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-e2e")
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        _write_fixture(fixtures_dir, "F001.json", _valid_fixture_payload())

        adapter = _StubAdapter(
            [
                APICallResult(
                    outcome="success",
                    raw_response="IDENTIFY: clean",
                    tokens_in=100,
                    tokens_out=50,
                    latency_ms=10.0,
                    error_category=None,
                    attempts=1,
                )
                for _ in range(6)
            ]
        )
        monkeypatch.setattr(cli_mod, "AnthropicAPIAdapter", lambda: adapter)
        rc = cli_main([
            "--agent",
            "security",
            "--fixtures",
            str(fixtures_dir),
            "--n-runs",
            "3",
        ])
        assert rc == 0
        # Report files exist under the run-id directory.
        reports_root = tmp_path / "evals" / "security-spike" / "reports"
        run_dirs = list(reports_root.iterdir())
        assert len(run_dirs) == 1
        report_json = run_dirs[0] / "report.json"
        report_md = run_dirs[0] / "REPORT.md"
        assert report_json.exists()
        assert report_md.exists()
        payload = json.loads(report_json.read_text(encoding="utf-8"))
        assert payload["schemaVersion"] == 1
        assert payload["recommendation"] is None
