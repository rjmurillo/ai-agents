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
ERR_AUTH = adapter_mod.ERR_AUTH
ERR_TOTAL_TIMEOUT = adapter_mod.ERR_TOTAL_TIMEOUT

RunPersistence = persistence_mod.RunPersistence
DuplicateRunError = persistence_mod.DuplicateRunError
MalformedRunRecordError = persistence_mod.MalformedRunRecordError
RunDirectoryNotFreshError = persistence_mod.RunDirectoryNotFreshError

ReportAggregator = aggregator_mod.ReportAggregator
AggregateResult = aggregator_mod.AggregateResult
EmptyRunError = aggregator_mod.EmptyRunError
_flaky_halt_count = aggregator_mod._flaky_halt_count
ReportWriter = writer_mod.ReportWriter

FixtureValidator = cli_mod.FixtureValidator
cli_main = cli_mod.main


# ---------------------------------------------------------------------------
# _build_prompt: methodology symmetry (SPIKE-1854 diagnosis)
# ---------------------------------------------------------------------------


class TestBuildPromptSymmetry:
    """Both variants must receive the same user-message suffix so the verdict-
    vocabulary contract is symmetric. See
    .agents/critique/SPIKE-1854-methodology-diagnosis.md for context."""

    def test_both_variants_receive_output_shape_suffix(self):
        agent_system = "Some agent system prompt"
        fixture_input = "Review this code."

        _, agent_user = cli_mod._build_prompt(
            "agent", agent_system, fixture_input
        )
        _, baseline_user = cli_mod._build_prompt(
            "baseline", agent_system, fixture_input
        )

        assert cli_mod.OUTPUT_SHAPE_SUFFIX in agent_user
        assert cli_mod.OUTPUT_SHAPE_SUFFIX in baseline_user

    def test_user_messages_are_identical_across_variants(self):
        """The user message is the only place the output-shape contract lives;
        both variants must see the exact same user message so the system prompt
        is the only difference being measured."""
        agent_system = "Some agent system prompt"
        fixture_input = "Review this code."

        _, agent_user = cli_mod._build_prompt(
            "agent", agent_system, fixture_input
        )
        _, baseline_user = cli_mod._build_prompt(
            "baseline", agent_system, fixture_input
        )

        assert agent_user == baseline_user

    def test_system_prompts_differ_between_variants(self):
        """The system prompt is the variable being measured (specialization).
        It must differ between agent and baseline."""
        agent_system = "Curated security-reviewer system prompt"
        fixture_input = "Review this code."

        agent_sys, _ = cli_mod._build_prompt(
            "agent", agent_system, fixture_input
        )
        baseline_sys, _ = cli_mod._build_prompt(
            "baseline", agent_system, fixture_input
        )

        assert agent_sys != baseline_sys
        assert agent_sys == agent_system
        assert baseline_sys == cli_mod.BASELINE_PROMPT

    def test_baseline_prompt_does_not_carry_verdict_instruction(self):
        """The verdict-vocabulary instruction lives in OUTPUT_SHAPE_SUFFIX, not
        in BASELINE_PROMPT, so the baseline's role is role-neutralization only."""
        for token in ("IDENTIFY", "OK", "ESCALATE"):
            assert token not in cli_mod.BASELINE_PROMPT, (
                f"BASELINE_PROMPT must not include verdict token {token!r}; "
                f"the contract belongs in OUTPUT_SHAPE_SUFFIX"
            )

    def test_output_shape_suffix_carries_verdict_instruction(self):
        """The shared suffix must carry the verdict vocabulary so both variants
        see the same contract."""
        for token in ("IDENTIFY", "OK", "ESCALATE"):
            assert token in cli_mod.OUTPUT_SHAPE_SUFFIX, (
                f"OUTPUT_SHAPE_SUFFIX must include verdict token {token!r}"
            )


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

    def test_verdict_match_markdown_bold(self):
        """Verdicts wrapped in markdown bold (**OK**) should be extracted."""
        engine = build_default_engine()
        for expected, response in [
            ("OK", "**OK**\n\nThe code is safe."),
            ("ESCALATE", "**ESCALATE**\n\nThis needs review."),
            ("IDENTIFY", "**IDENTIFY**\n\nFound CWE-22."),
        ]:
            a = Assertion(kind=AssertionKind.VERDICT, expected_value=expected)
            result = engine.score(a, response)
            assert result.passed is True, f"Expected {expected} to pass"
            assert result.extracted == expected

    def test_verdict_match_markdown_italic(self):
        """Verdicts wrapped in markdown italic (*OK*) should be extracted."""
        a = Assertion(kind=AssertionKind.VERDICT, expected_value="OK")
        engine = build_default_engine()
        result = engine.score(a, "*OK*\n\nNo issues found.")
        assert result.passed is True
        assert result.extracted == "OK"


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


class TestAnthropicAPIAdapterTransportConstruction:
    """`call_model` MUST honor its docstring contract:
    'Returns APICallResult regardless of outcome'. Before this guard,
    `_resolve_transport()` ran outside the try/except so a missing
    ANTHROPIC_API_KEY (RuntimeError raised by `load_api_key()` inside
    `_default_transport_factory`) would propagate, forcing every
    caller to special-case construction failure separately from
    transport failure."""

    def test_resolve_failure_returns_auth_error_result(self, monkeypatch):
        # Replace the production transport factory with one that raises
        # the same RuntimeError shape `load_api_key()` would emit.
        def _explode() -> object:
            raise RuntimeError("ANTHROPIC_API_KEY not found in environment")

        monkeypatch.setattr(adapter_mod, "_default_transport_factory", _explode)
        adapter = AnthropicAPIAdapter()  # transport=None -> uses factory
        result = adapter.call_model(
            prompt="x",
            model_id="claude-sonnet-4-6",
            fixture_id="F004",
            variant="agent",
            run_index=0,
        )
        assert result.outcome == "error"
        assert result.error_category == ERR_AUTH
        assert result.attempts == 0
        assert result.raw_response is None
        assert result.tokens_in == 0
        assert result.tokens_out == 0


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
        with pytest.raises(SchemaVersionError, match="schemaVersion"):
            persistence.write_record(record)


class TestRunPersistenceMalformedJsonl:
    """Existing on-disk JSONL that does not parse, or parses but lacks an
    identity field, must surface as `MalformedRunRecordError` so the CLI
    maps it to EXIT_CONFIG (2) per DESIGN-004 §Failure Modes. Treating
    on-disk corruption as a logic-class duplicate misleads operators."""

    def _seed(self, tmp_path, line: str):
        run_dir = tmp_path / "mal"
        run_dir.mkdir(parents=True)
        (run_dir / "runs.jsonl").write_text(line, encoding="utf-8")
        return run_dir

    def test_invalid_json_line_raises_malformed(self, tmp_path):
        run_dir = self._seed(tmp_path, "{not valid json\n")
        with pytest.raises(MalformedRunRecordError, match="not valid JSON"):
            RunPersistence(run_dir, resume=True)

    def test_missing_identity_field_raises_malformed(self, tmp_path):
        # Valid JSON, but missing `variant` and `run_index`.
        run_dir = self._seed(
            tmp_path,
            json.dumps({"fixture_id": "F001", "schemaVersion": 1}) + "\n",
        )
        with pytest.raises(
            MalformedRunRecordError, match=r"missing identity field\(s\): variant, run_index"
        ):
            RunPersistence(run_dir, resume=True)

    @pytest.mark.parametrize(
        "field, bad_value, expected_msg",
        [
            ("fixture_id", 42, r"fixture_id'.*expected str.*got int"),
            ("variant", 0, r"variant'.*expected str.*got int"),
            ("run_index", "0", r"run_index'.*expected int.*got str"),
            ("run_index", True, r"run_index'.*expected int.*got bool"),
        ],
    )
    def test_identity_field_wrong_type_raises_malformed(
        self, tmp_path, field, bad_value, expected_msg
    ):
        # Without type validation, a `"run_index": "0"` line would build
        # a `(str, str, str)` key in `_seen`, while in-memory writes use
        # `(str, str, int)`, letting an idempotency-equivalent triple
        # slip past the duplicate guard.
        payload = {
            "fixture_id": "F001",
            "variant": "agent",
            "run_index": 0,
            "schemaVersion": 1,
        }
        payload[field] = bad_value
        run_dir = self._seed(tmp_path, json.dumps(payload) + "\n")
        with pytest.raises(MalformedRunRecordError, match=expected_msg):
            RunPersistence(run_dir, resume=True)

    def test_malformed_is_distinct_from_duplicate_run_error(self):
        # Sanity: the new exception is its own class, so a CLI catch on
        # `DuplicateRunError` cannot accidentally absorb on-disk
        # corruption and downgrade it to EXIT_LOGIC.
        assert not issubclass(MalformedRunRecordError, DuplicateRunError)
        assert not issubclass(DuplicateRunError, MalformedRunRecordError)

    def test_iter_records_invalid_json_raises_malformed(self, tmp_path):
        # `iter_records` calls `_parse_record`, which calls `json.loads`.
        # Without an explicit catch, a corrupt line escapes as
        # `json.JSONDecodeError` and bypasses the runner's config-class
        # error mapping. The wrapper turns it into
        # `MalformedRunRecordError` with the offending line number.
        # Pattern matches `test_iter_records_rejects_incompatible_schema_version`:
        # seed a valid file so the constructor accepts the resume, then
        # mutate the file to exercise the iterator path.
        run_dir = tmp_path / "iter-mal"
        run_dir.mkdir(parents=True)
        valid = json.dumps(
            {
                "fixture_id": "F001",
                "variant": "agent",
                "run_index": 0,
                "model_id": "claude-sonnet-4-6",
                "prompt_sha": "p" * 64,
                "prompt_ref": "<test>",
                "fixture_sha": "f" * 64,
                "raw_response": "ok",
                "assertions": [],
                "outcome": "success",
                "latency_ms": 1.0,
                "tokens_in": 1,
                "tokens_out": 1,
                "error_category": None,
                "attempts": 1,
                "tokens_estimated": True,
                "schemaVersion": 1,
            }
        )
        (run_dir / "runs.jsonl").write_text(valid + "\n", encoding="utf-8")
        persistence = RunPersistence(run_dir, resume=True)
        # Now corrupt the file to exercise the iterator path.
        (run_dir / "runs.jsonl").write_text(
            valid + "\n{not valid json\n", encoding="utf-8"
        )
        with pytest.raises(MalformedRunRecordError, match=r"line 2 is not valid JSON"):
            list(persistence.iter_records())


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
        # One fixture, two assertions on the same response: recall denom
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

    def test_skill_variant_flakiness_does_not_move_v1_metrics(self):
        records = _build_records(
            ["F001", "F002"], agent_passed=True, baseline_passed=False
        )
        records.extend(
            [
                _success_record("F001", "skill", 0, passed=True),
                _success_record("F001", "skill", 1, passed=False),
                _success_record("F001", "skill", 2, passed=True),
            ]
        )

        result = ReportAggregator(records, model_id="claude-sonnet-4-6").aggregate()

        assert result.flakiness is False
        assert result.agent_recall == 1.0
        assert result.baseline_recall == 0.0

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


def _records_with_flaky_subset(
    *, total: int, flaky: int, bootstrap_iterations: int = 200
) -> list:
    """Build `total` fixtures; the first `flaky` have agent pass-rate variance.

    Stable fixtures: agent passes every run, baseline fails every run.
    Flaky fixtures: agent run series is pass / fail / pass (variance > 0).
    Returns just the records; the caller constructs the aggregator so it can
    pass mode flags.
    """
    records: list = []
    for index in range(total):
        fid = f"F{index + 1:03d}"
        is_flaky = index < flaky
        agent_pass = (
            [True, False, True] if is_flaky else [True, True, True]
        )
        for run_index, passed in enumerate(agent_pass):
            records.append(_success_record(fid, "agent", run_index, passed=passed))
            records.append(
                _success_record(fid, "baseline", run_index, passed=False)
            )
    return records


class TestFlakyHaltCount:
    def test_small_n_floor_applies_at_n10(self):
        # N=10: max(floor(3.0)+1, min(5, 5)) = max(4, 5) = 5.
        assert _flaky_halt_count(10) == 5

    def test_fraction_governs_at_large_n(self):
        # N=30: max(floor(9.0)+1, min(5, 15)) = max(10, 5) = 10.
        # Strict "more than 30%": 9 of 30 is exactly 30% and does NOT halt.
        assert _flaky_halt_count(30) == 10

    def test_tiny_corpus_floor_is_one(self):
        # N=2: max(floor(0.6)+1=1, min(5, 1)=1) = 1.
        assert _flaky_halt_count(2) == 1

    def test_zero_n_returns_zero_inputs_only(self):
        # N<=0 short-circuits to 0. The aggregator guards N>0 separately.
        assert _flaky_halt_count(0) == 0


class TestReportAggregatorNAwareHalt:
    def test_four_flaky_of_ten_does_not_halt(self):
        # N=10, halt count 5. 4 flaky < 5 → continue on the stable subset.
        records = _records_with_flaky_subset(total=10, flaky=4)
        result = ReportAggregator(
            records, model_id="claude-sonnet-4-6", bootstrap_iterations=200
        ).aggregate()
        assert result.flakiness is True
        assert result.halt_due_to_flakiness is False
        assert result.flaky_halt_threshold_crossed is False
        assert result.flaky_fixtures_excluded == [
            "F001",
            "F002",
            "F003",
            "F004",
        ]
        # Stable subset is the 6 non-flaky fixtures; agent always passes.
        assert result.agent_recall == 1.0
        assert result.baseline_recall == 0.0

    def test_five_flaky_of_ten_halts(self):
        # N=10, halt count 5. 5 flaky >= 5 → halt.
        records = _records_with_flaky_subset(total=10, flaky=5)
        result = ReportAggregator(
            records, model_id="claude-sonnet-4-6", bootstrap_iterations=200
        ).aggregate()
        assert result.flakiness is True
        assert result.halt_due_to_flakiness is True
        assert result.flaky_halt_threshold_crossed is True
        # On halt, flaky fixtures are not excluded; the whole run is invalid.
        assert result.flaky_fixtures_excluded == []

    def test_large_n_preserves_thirty_percent(self):
        # N=30, halt count 10. 9 flaky (exactly 30%) → no halt; 10 → halt.
        no_halt = ReportAggregator(
            _records_with_flaky_subset(total=30, flaky=9),
            model_id="claude-sonnet-4-6",
            bootstrap_iterations=100,
        ).aggregate()
        assert no_halt.halt_due_to_flakiness is False
        assert no_halt.flaky_halt_threshold_crossed is False
        halted = ReportAggregator(
            _records_with_flaky_subset(total=30, flaky=10),
            model_id="claude-sonnet-4-6",
            bootstrap_iterations=100,
        ).aggregate()
        assert halted.halt_due_to_flakiness is True
        assert halted.flaky_halt_threshold_crossed is True

    def test_flag_and_continue_records_crossing_without_halting(self):
        # N=10, 5 flaky would halt by default; flag-and-continue suppresses
        # the halt, excludes the flaky fixtures, and records the crossing.
        records = _records_with_flaky_subset(total=10, flaky=5)
        result = ReportAggregator(
            records,
            model_id="claude-sonnet-4-6",
            bootstrap_iterations=200,
            flag_only_on_flaky_halt=True,
        ).aggregate()
        assert result.halt_due_to_flakiness is False
        assert result.flaky_halt_threshold_crossed is True
        assert result.flaky_fixtures_excluded == [
            "F001",
            "F002",
            "F003",
            "F004",
            "F005",
        ]
        # Stable subset is the 5 non-flaky fixtures; agent always passes.
        assert result.agent_recall == 1.0

    def test_flag_and_continue_crossing_serialized_and_warned(self, tmp_path):
        # The crossing must survive to report.json and REPORT.md so the
        # "flag" in flag-and-continue is not lost when the process exits.
        records = _records_with_flaky_subset(total=10, flaky=5)
        aggregate = ReportAggregator(
            records,
            model_id="claude-sonnet-4-6",
            bootstrap_iterations=200,
            flag_only_on_flaky_halt=True,
        ).aggregate()
        json_path, md_path = ReportWriter(tmp_path / "reports").write(
            aggregate=aggregate,
            run_id="r1",
            model_id="claude-sonnet-4-6",
            agent_prompt_sha="a" * 64,
            baseline_prompt_sha="b" * 64,
            fixture_set_sha="c" * 64,
            wall_clock_seconds=10.0,
        )
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["flaky_halt_threshold_crossed"] is True
        assert "30%" in md_path.read_text(encoding="utf-8")


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
    def _aggregate(self, *, tokens_estimated: bool = True) -> AggregateResult:
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
            flaky_fixtures_detected=[],
            flaky_fixtures_excluded=[],
            total_tokens_in=15360,
            total_tokens_out=2400,
            cost_estimate_usd=0.09,
            pricing_rate_as_of="2026-05-03",
            error_count=0,
            halt_due_to_flakiness=False,
            tokens_estimated=tokens_estimated,
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
            "flaky_fixtures_detected",
            "flaky_fixtures_excluded",
            "flaky_halt_threshold_crossed",
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

    def test_e2e_include_skill_writes_form_factor_report(
        self, tmp_path, monkeypatch
    ):
        self._setup(tmp_path, monkeypatch)
        skills_dir = tmp_path / ".claude" / "skills" / "security-review"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text("skill prompt", encoding="utf-8")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-e2e-skill")
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
                for _ in range(9)
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
            "--include-skill",
        ])

        assert rc == 0
        assert adapter.call_count == 9
        reports_root = tmp_path / "evals" / "security-spike" / "reports"
        report_json = next(reports_root.iterdir()) / "report.json"
        payload = json.loads(report_json.read_text(encoding="utf-8"))
        assert payload["form_factor"]["agent_baseline_ci_95"]
        assert payload["form_factor"]["skill_baseline_ci_95"]
        assert payload["form_factor"]["agent_skill_ci_95"]
        assert payload["form_factor"]["verdict"]


# ===========================================================================
# /review iteration 1 fixes: B1, H1-H6, T1
# ===========================================================================


# ---------------------------------------------------------------------------
# B1: fresh-run mode must NOT silently skip existing records
# ---------------------------------------------------------------------------


class TestRunPersistenceFreshRunGuard:
    """B1: fresh-run mode against a populated runs.jsonl raises."""

    def test_fresh_run_against_nonempty_runs_jsonl_raises(self, tmp_path):
        run_dir = tmp_path / "run-fresh-guard"
        # Populate the dir via a first (legal) writer.
        first = RunPersistence(run_dir, resume=False)
        first.write_record(_make_record())
        # Reopening in fresh-run mode must refuse.
        with pytest.raises(RunDirectoryNotFreshError) as excinfo:
            RunPersistence(run_dir, resume=False)
        message = str(excinfo.value)
        assert "runs.jsonl" in message
        assert "--resume" in message

    def test_fresh_run_against_empty_dir_succeeds(self, tmp_path):
        # No file → no guard fires.
        persistence = RunPersistence(tmp_path / "fresh-empty", resume=False)
        assert persistence.write_record(_make_record()) is True

    def test_resume_against_nonempty_runs_jsonl_succeeds(self, tmp_path):
        run_dir = tmp_path / "run-resume-ok"
        first = RunPersistence(run_dir, resume=False)
        first.write_record(_make_record())
        # Resume mode must accept the populated dir.
        second = RunPersistence(run_dir, resume=True)
        assert second.is_completed("F001", "agent", 0)


class TestRunnerFreshRunMode:
    """B1 (runner side): pre-call skip is gated on --resume."""

    def _setup(self, tmp_path, monkeypatch):
        agents_dir = tmp_path / "templates" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "security.shared.md").write_text(
            "agent prompt", encoding="utf-8"
        )
        monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
        return agents_dir

    def test_fresh_run_against_populated_dir_exits_one(
        self, tmp_path, monkeypatch, capsys
    ):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fresh")
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        _write_fixture(fixtures_dir, "F001.json", _valid_fixture_payload())

        # Pre-populate the run dir so the fresh-run guard fires.
        run_id = "20260503T160000Z-deadbeef"
        run_dir = (
            tmp_path / "evals" / "security-spike" / "runs" / run_id
        )
        run_dir.mkdir(parents=True)
        first = RunPersistence(run_dir, resume=False)
        first.write_record(_make_record())

        adapter = _StubAdapter([])  # any call IndexErrors → proves no calls
        monkeypatch.setattr(cli_mod, "AnthropicAPIAdapter", lambda: adapter)
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
        assert rc == 1
        captured = capsys.readouterr()
        assert "runs.jsonl" in captured.err
        assert "--resume" in captured.err
        # Runner refused to call the adapter.
        assert adapter.call_count == 0


# ---------------------------------------------------------------------------
# H1: tokens_estimated flag flows through record and report
# ---------------------------------------------------------------------------


class TestTokensEstimatedFlag:
    """H1: every cost number must carry a "this is an estimate" marker."""

    def test_api_call_result_default_is_estimated(self):
        result = APICallResult(
            outcome="success",
            raw_response="ok",
            tokens_in=10,
            tokens_out=5,
            latency_ms=1.0,
            error_category=None,
            attempts=1,
        )
        assert result.tokens_estimated is True

    def test_record_carries_tokens_estimated_flag(self):
        record = _make_record()
        # New default is True for backward compat across persisted shape.
        assert record.tokens_estimated is True

    def test_record_explicit_false_round_trips_through_persistence(
        self, tmp_path
    ):
        persistence = RunPersistence(tmp_path / "rt-est", resume=False)
        record = _make_record()
        record.tokens_estimated = False
        persistence.write_record(record)
        line = persistence.jsonl_path.read_text(encoding="utf-8").strip()
        payload = json.loads(line)
        assert payload["tokens_estimated"] is False
        # And reads back as False through iter_records.
        reopened = RunPersistence(tmp_path / "rt-est", resume=True)
        records = list(reopened.iter_records())
        assert records[0].tokens_estimated is False

    def test_aggregate_carries_tokens_estimated_flag(self):
        # Build records all marked estimated → aggregate.tokens_estimated=True.
        records = _build_records(
            ["F001"], agent_passed=True, baseline_passed=True
        )
        result = ReportAggregator(
            records, model_id="claude-sonnet-4-6"
        ).aggregate()
        assert result.tokens_estimated is True

    def test_aggregate_all_measured_clears_flag(self):
        records = _build_records(
            ["F001"], agent_passed=True, baseline_passed=True
        )
        for record in records:
            record.tokens_estimated = False
        result = ReportAggregator(
            records, model_id="claude-sonnet-4-6"
        ).aggregate()
        assert result.tokens_estimated is False

    def test_report_json_includes_tokens_estimated(self, tmp_path):
        writer = ReportWriter(tmp_path / "reports")
        aggregate = AggregateResult(
            agent_recall=0.5,
            baseline_recall=0.5,
            recall_delta=0.0,
            bootstrap_ci_95=(0.0, 0.0),
            recall_with_errors=0.5,
            recall_excluding_errors=0.5,
            per_fixture_pass_rates={},
            flakiness=False,
            flaky_fixtures_detected=[],
            flaky_fixtures_excluded=[],
            total_tokens_in=100,
            total_tokens_out=50,
            cost_estimate_usd=0.001,
            pricing_rate_as_of="2026-05-03",
            error_count=0,
            halt_due_to_flakiness=False,
            tokens_estimated=True,
        )
        json_path, md_path = writer.write(
            aggregate=aggregate,
            run_id="r-est",
            model_id="claude-sonnet-4-6",
            agent_prompt_sha="a" * 64,
            baseline_prompt_sha="b" * 64,
            fixture_set_sha="c" * 64,
            wall_clock_seconds=1.0,
        )
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["tokens_estimated"] is True
        # MD includes the caveat footnote when tokens are estimated.
        body = md_path.read_text(encoding="utf-8")
        assert "estimated" in body.lower()
        assert "heuristic" in body.lower()


# ---------------------------------------------------------------------------
# H2: empty records → EmptyRunError, runner exits 1
# ---------------------------------------------------------------------------


class TestEmptyRunError:
    def test_aggregate_with_no_records_raises_empty_run_error(self):
        with pytest.raises(EmptyRunError):
            ReportAggregator([], model_id="claude-sonnet-4-6").aggregate()


# ---------------------------------------------------------------------------
# H3: unsupported model → UnsupportedModelError, runner exits 2
# ---------------------------------------------------------------------------


class TestUnsupportedModelInAggregator:
    def test_aggregate_unsupported_model_raises(self):
        records = _build_records(
            ["F001"], agent_passed=True, baseline_passed=True
        )
        with pytest.raises(UnsupportedModelError):
            ReportAggregator(records, model_id="model-without-pricing").aggregate()


# ---------------------------------------------------------------------------
# H4: total wall budget aborts after threshold
# ---------------------------------------------------------------------------


class _SlowTransport:
    """Fake transport that advances a fake clock and always raises a 500.

    `seconds_per_call` is added to the controlled clock each call. The
    test injects this transport along with a sleep no-op so the wall
    budget is the only mechanism that can stop the retry loop.
    """

    def __init__(self, clock_state: list, seconds_per_call: float):
        self._state = clock_state
        self._sec = seconds_per_call
        self.calls = 0

    def __call__(self, prompt: str, model_id: str, system: str) -> str:
        self.calls += 1
        self._state[0] += self._sec
        raise RuntimeError("Anthropic API returned HTTP 500: synthetic")


class TestAdapterTotalWallBudget:
    def test_total_wall_budget_aborts_after_threshold(self):
        # Each call burns 120s on the controlled clock. Budget=180s.
        # Attempt 1: clock 0→120. Backoff projection 120+~1 < 180; retry.
        # Attempt 2: clock 120→240. Backoff projection 240+~2 >= 180;
        # the guard aborts before attempt 3. Without the guard the loop
        # would run all 3 attempts, taking 360s (worst-case 6 minutes
        # per call in production).
        clock_state = [0.0]

        def clock() -> float:
            return clock_state[0]

        slow = _SlowTransport(clock_state, seconds_per_call=120.0)
        adapter = AnthropicAPIAdapter(
            transport=slow,
            sleep=lambda _s: None,
            clock=clock,
            total_timeout_seconds=180.0,
        )
        result = adapter.call_model(
            prompt="x",
            model_id="claude-sonnet-4-6",
            fixture_id="F-WB",
            variant="agent",
            run_index=0,
        )
        assert result.outcome == "error"
        assert result.error_category == ERR_TOTAL_TIMEOUT
        # 2 calls land; the budget guard prevents a 3rd attempt.
        assert slow.calls == 2

    def test_wall_budget_does_not_fire_on_fast_calls(self):
        # Each call is fast; budget never trips, normal retry exhaustion
        # path runs to completion and returns server_error.
        clock_state = [0.0]

        def clock() -> float:
            return clock_state[0]

        fast = _SlowTransport(clock_state, seconds_per_call=0.5)
        adapter = AnthropicAPIAdapter(
            transport=fast,
            sleep=lambda _s: None,
            clock=clock,
            total_timeout_seconds=180.0,
        )
        result = adapter.call_model(
            prompt="x",
            model_id="claude-sonnet-4-6",
            fixture_id="F-WB-FAST",
            variant="agent",
            run_index=0,
        )
        # Standard retry exhaustion: 3 attempts, server_error category.
        assert result.outcome == "error"
        assert result.error_category == ERR_SERVER_ERROR
        assert fast.calls == 3


# ---------------------------------------------------------------------------
# H5: --resume retries errored triples
# ---------------------------------------------------------------------------


class TestResumeRetriesErrored:
    def test_is_completed_false_for_errored_record(self, tmp_path):
        run_dir = tmp_path / "errored"
        first = RunPersistence(run_dir, resume=False)
        first.write_record(_make_record(outcome="error"))
        # Reopen in resume mode; errored triple should not count as done.
        second = RunPersistence(run_dir, resume=True)
        assert second.is_completed("F001", "agent", 0) is False

    def test_resume_retries_errored_triples(self, tmp_path):
        run_dir = tmp_path / "errored-retry"
        first = RunPersistence(run_dir, resume=False)
        first.write_record(_make_record(outcome="error"))
        # Resume run: writing a new (success) record for the same triple
        # is allowed and replaces the errored line.
        second = RunPersistence(run_dir, resume=True)
        assert second.write_record(_make_record(outcome="success")) is True
        # File now has exactly one record, marked success.
        lines = [
            ln
            for ln in second.jsonl_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["outcome"] == "success"

    def test_resume_skips_successful_triples(self, tmp_path):
        run_dir = tmp_path / "success-skip"
        first = RunPersistence(run_dir, resume=False)
        first.write_record(_make_record(outcome="success"))
        second = RunPersistence(run_dir, resume=True)
        # Successful prior → write_record returns False.
        assert second.write_record(_make_record(outcome="success")) is False
        assert second.skipped_count() == 1


# ---------------------------------------------------------------------------
# H6: resume skips emit a structured log line and a summary count
# ---------------------------------------------------------------------------


class TestResumeSkipLogging:
    def _setup(self, tmp_path, monkeypatch):
        agents_dir = tmp_path / "templates" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "security.shared.md").write_text(
            "agent prompt", encoding="utf-8"
        )
        monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
        return agents_dir

    def test_resume_logs_each_skip(self, tmp_path, monkeypatch, capsys):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-skip")
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        _write_fixture(fixtures_dir, "F001.json", _valid_fixture_payload())

        # Phase 1: complete a full run (6 records).
        adapter1 = _StubAdapter(
            [
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
        )
        monkeypatch.setattr(cli_mod, "AnthropicAPIAdapter", lambda: adapter1)
        run_id = "20260503T160000Z-skiplog0"
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
        capsys.readouterr()  # discard phase-1 logs

        # Phase 2: resume; every triple is already complete → 6 skips.
        adapter2 = _StubAdapter([])
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
        captured = capsys.readouterr()
        # Parse every JSON log line and filter by `event` key. Substring
        # matches on the raw line are fragile across quote boundaries.
        events = []
        for line in captured.err.splitlines():
            if not line.startswith("{"):
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        per_triple = [e for e in events if e.get("event") == "resume_skip"]
        assert len(per_triple) == 6
        summary = [
            e for e in events if e.get("event") == "resume_skip_summary"
        ]
        assert len(summary) == 1
        assert summary[0]["resume_skips_count"] == 6


# ---------------------------------------------------------------------------
# T1: AC-10 contingency rerun behavior at n_runs=5 and n_runs=10
# ---------------------------------------------------------------------------


def _passing_runs(fixture_id: str, variant: str, n_runs: int, *, fail_indices: set):
    return [
        _success_record(
            fixture_id, variant, ri, passed=ri not in fail_indices
        )
        for ri in range(n_runs)
    ]


class TestContingencyRerun:
    def test_contingency_rerun_two_of_five_marks_flaky(self):
        # n_runs=5; agent variant: 2 fail, 3 pass on F001 → flaky=True.
        records: list = []
        records += _passing_runs("F001", "agent", 5, fail_indices={1, 3})
        records += _passing_runs("F001", "baseline", 5, fail_indices=set())
        # Add stable F002 so percentage of flaky <= 30% (no halt).
        for fid in ("F002", "F003", "F004"):
            records += _passing_runs(fid, "agent", 5, fail_indices=set())
            records += _passing_runs(fid, "baseline", 5, fail_indices=set())
        result = ReportAggregator(
            records,
            model_id="claude-sonnet-4-6",
            bootstrap_iterations=200,
        ).aggregate()
        assert result.flakiness is True
        assert "F001" in result.flaky_fixtures_excluded
        # 1 of 4 fixtures flaky = 25%, no halt.
        assert result.halt_due_to_flakiness is False

    def test_contingency_rerun_one_of_five_not_flaky(self):
        # n_runs=5; only 1 fail of 5 → transient, NOT flaky.
        records: list = []
        records += _passing_runs("F001", "agent", 5, fail_indices={2})
        records += _passing_runs("F001", "baseline", 5, fail_indices=set())
        records += _passing_runs("F002", "agent", 5, fail_indices=set())
        records += _passing_runs("F002", "baseline", 5, fail_indices=set())
        result = ReportAggregator(
            records,
            model_id="claude-sonnet-4-6",
            bootstrap_iterations=200,
        ).aggregate()
        assert result.flakiness is False
        assert result.flaky_fixtures_excluded == []

    def _ten_fixture_contingency(self, flaky_ids: set[str]) -> list:
        all_ids = (
            "F001",
            "F002",
            "F003",
            "F004",
            "F005",
            "F006",
            "F007",
            "F008",
            "F009",
            "F010",
        )
        records: list = []
        for fid in all_ids:
            fails = {0, 2} if fid in flaky_ids else set()
            records += _passing_runs(fid, "agent", 5, fail_indices=fails)
            records += _passing_runs(fid, "baseline", 5, fail_indices=set())
        return records

    def test_contingency_four_of_ten_does_not_halt(self):
        # Behavior change (Issue #1878): the old fixed 30% fraction halted on
        # 4 flaky of 10 (40%). The N-aware halt count at N=10 is 5, so 4
        # flaky no longer halts; the flaky fixtures are excluded and the run
        # continues on the stable subset.
        records = self._ten_fixture_contingency(
            {"F001", "F002", "F003", "F004"}
        )
        result = ReportAggregator(
            records,
            model_id="claude-sonnet-4-6",
            bootstrap_iterations=200,
        ).aggregate()
        assert result.flakiness is True
        assert result.halt_due_to_flakiness is False
        assert result.flaky_halt_threshold_crossed is False
        assert sorted(result.flaky_fixtures_excluded) == [
            "F001",
            "F002",
            "F003",
            "F004",
        ]

    def test_contingency_five_of_ten_halts(self):
        # N-aware halt count at N=10 is 5; 5 flaky of 10 reaches it → halt.
        records = self._ten_fixture_contingency(
            {"F001", "F002", "F003", "F004", "F005"}
        )
        result = ReportAggregator(
            records,
            model_id="claude-sonnet-4-6",
            bootstrap_iterations=200,
        ).aggregate()
        assert result.flakiness is True
        assert result.halt_due_to_flakiness is True
        assert sorted(result.flaky_fixtures_excluded) == []  # halt path


# ---------------------------------------------------------------------------
# H2 + H3: runner-side exit codes for new error paths
# ---------------------------------------------------------------------------


class TestRunnerEmptyAndUnsupported:
    def _setup(self, tmp_path, monkeypatch):
        agents_dir = tmp_path / "templates" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "security.shared.md").write_text(
            "agent prompt", encoding="utf-8"
        )
        monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
        return agents_dir

    def test_runner_unsupported_model_exits_two(
        self, tmp_path, monkeypatch, capsys
    ):
        # Model unsupported is caught in plan-build before live run, which
        # already exits 2; this test pins that contract so the new
        # aggregator-side raise does not change CLI behavior for the
        # common case.
        self._setup(tmp_path, monkeypatch)
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        _write_fixture(fixtures_dir, "F001.json", _valid_fixture_payload())
        rc = cli_main([
            "--dry-run",
            "--agent",
            "security",
            "--fixtures",
            str(fixtures_dir),
            "--model",
            "unpriced-model",
        ])
        assert rc == 2
        captured = capsys.readouterr()
        assert "pricing rate" in captured.err.lower()


# ===========================================================================
# Post-PR-1873-review tightening: kind contract, resume schema, per-fixture
# halt, recommendation pass-through, CLI input validators.
# ===========================================================================


class TestAssertionKindContract:
    """`Assertion.__post_init__` enforces kind-vs-field shape (PR 1873)."""

    def test_regex_with_only_pattern_constructs(self):
        a = Assertion(kind=AssertionKind.REGEX, pattern="(?i)\\bok\\b")
        assert a.pattern == "(?i)\\bok\\b"
        assert a.expected_value is None

    def test_regex_without_pattern_raises(self):
        with pytest.raises(ValueError, match="REGEX assertions require pattern"):
            Assertion(kind=AssertionKind.REGEX)

    def test_regex_with_expected_value_raises(self):
        with pytest.raises(ValueError, match="must not set expected_value"):
            Assertion(
                kind=AssertionKind.REGEX,
                pattern="(?i)ok",
                expected_value="OK",
            )

    def test_verdict_with_only_expected_value_constructs(self):
        a = Assertion(kind=AssertionKind.VERDICT, expected_value="OK")
        assert a.expected_value == "OK"
        assert a.pattern is None

    def test_verdict_without_expected_value_raises(self):
        with pytest.raises(ValueError, match="VERDICT assertions require expected_value"):
            Assertion(kind=AssertionKind.VERDICT)

    def test_verdict_with_pattern_raises(self):
        with pytest.raises(ValueError, match="must not set pattern"):
            Assertion(
                kind=AssertionKind.VERDICT,
                pattern="(?i)ok",
                expected_value="OK",
            )

    def test_validator_rejects_invalid_regex_pattern_at_load_time(self, tmp_path):
        """Bad regex MUST surface as FixtureValidationError before any API call."""
        payload = _valid_fixture_payload(
            assertions=[{"kind": "regex", "pattern": "(unclosed"}],
        )
        path = _write_fixture(tmp_path, "F001.json", payload)
        with pytest.raises(FixtureValidationError, match="not a valid regex"):
            FixtureValidator.validate_fixtures([path])

    def test_validator_rejects_empty_expected_value_for_verdict(self, tmp_path):
        payload = _valid_fixture_payload(
            assertions=[{"kind": "verdict", "expected_value": ""}],
        )
        path = _write_fixture(tmp_path, "F001.json", payload)
        with pytest.raises(FixtureValidationError, match="non-empty string"):
            FixtureValidator.validate_fixtures([path])


class TestRunPersistenceResumeSchemaGuard:
    """`_load_existing_keys` + `_parse_record` MUST reject incompatible
    schemaVersion at resume time (PR 1873). A stale runs.jsonl could otherwise
    seed `_seen`/`_completed` with rows whose shape the writer would accept."""

    def _seed_jsonl(self, run_dir: Path, schema_version) -> Path:
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "runs.jsonl"
        record = {
            "schemaVersion": schema_version,
            "fixture_id": "F001",
            "variant": "agent",
            "run_index": 0,
            "model_id": "claude-sonnet-4-6",
            "prompt_sha": "a" * 64,
            "prompt_ref": "<test>",
            "fixture_sha": "b" * 64,
            "raw_response": "OK",
            "assertions": [
                {
                    "kind": "verdict",
                    "pattern": None,
                    "expected_value": "OK",
                    "passed": True,
                    "extracted": "OK",
                }
            ],
            "outcome": "success",
            "latency_ms": 10.0,
            "tokens_in": 5,
            "tokens_out": 5,
            "error_category": None,
            "attempts": 1,
            "tokens_estimated": True,
        }
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        return path

    def test_resume_open_with_old_schema_version_raises(self, tmp_path):
        run_dir = tmp_path / "runs" / "rid"
        self._seed_jsonl(run_dir, 0)
        with pytest.raises(SchemaVersionError, match="schemaVersion=0"):
            RunPersistence(run_dir, resume=True)

    def test_resume_open_with_future_schema_version_raises(self, tmp_path):
        run_dir = tmp_path / "runs" / "rid"
        self._seed_jsonl(run_dir, 99)
        with pytest.raises(SchemaVersionError, match="schemaVersion=99"):
            RunPersistence(run_dir, resume=True)

    def test_iter_records_rejects_incompatible_schema_version(self, tmp_path):
        run_dir = tmp_path / "runs" / "rid"
        # Seed at correct version so the constructor accepts the resume.
        self._seed_jsonl(run_dir, SCHEMA_VERSION)
        persistence = RunPersistence(run_dir, resume=True)
        # Now mutate the file to an incompatible version and exercise the
        # downstream parser.
        (run_dir / "runs.jsonl").write_text(
            json.dumps({**json.loads((run_dir / "runs.jsonl").read_text()),
                        "schemaVersion": 99}) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(SchemaVersionError, match="schemaVersion=99"):
            list(persistence.iter_records())


class TestPerFixtureHaltThreshold:
    """REQ-004 AC-3: error rate >10% halts per FIXTURE, not per record (PR 1873).
    Distinguishing case: 1 error out of 30 records spread across 5 fixtures.
    Per-record = 3.3% (would not halt under the old rule); per-fixture = 20%
    (correctly halts under the spec)."""

    def _setup(self, tmp_path, monkeypatch):
        agents_dir = tmp_path / "templates" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "security.shared.md").write_text(
            "agent prompt", encoding="utf-8"
        )
        monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")

    def test_one_error_in_one_of_five_fixtures_halts_per_fixture(
        self, tmp_path, monkeypatch, capsys
    ):
        self._setup(tmp_path, monkeypatch)
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        for i in range(1, 6):
            fid = f"F{i:03d}"
            payload = _valid_fixture_payload(
                id=fid,
                assertions=[{"kind": "verdict", "expected_value": "IDENTIFY"}],
            )
            _write_fixture(fixtures_dir, f"{fid}.json", payload)

        # Iteration order: fixture × variant × run. First call (F001-agent-0)
        # errors; the remaining 29 succeed.
        results = [
            APICallResult(
                outcome="error",
                raw_response=None,
                tokens_in=0,
                tokens_out=0,
                latency_ms=5.0,
                error_category=ERR_SERVER_ERROR,
                attempts=3,
            )
        ] + [
            APICallResult(
                outcome="success",
                raw_response="IDENTIFY: ok",
                tokens_in=10,
                tokens_out=10,
                latency_ms=5.0,
                error_category=None,
                attempts=1,
            )
            for _ in range(29)
        ]
        adapter = _StubAdapter(results)
        monkeypatch.setattr(cli_mod, "AnthropicAPIAdapter", lambda: adapter)
        rc = cli_main([
            "--agent", "security",
            "--fixtures", str(fixtures_dir),
            "--n-runs", "3",
        ])
        assert rc == 1
        captured = capsys.readouterr()
        assert "fixture-level error rate exceeds 10%" in captured.err
        # Per-fixture metrics in the structured log:
        assert '"fixtures_with_errors": 1' in captured.err
        assert '"executed_fixtures": 5' in captured.err
        # Per-record values are also logged so operators can correlate; the
        # per-record fraction here is well below 10%, proving the halt
        # fired on the per-fixture rule, not the per-record one.
        assert '"error_count": 1' in captured.err
        assert '"executed_records": 30' in captured.err


class TestReportWriterRecommendationPassThrough:
    """`ReportWriter.write` accepts a verdict that flows into both
    report.json and the Markdown narrative (PR 1873)."""

    def _agg(self) -> "AggregateResult":
        return AggregateResult(
            agent_recall=0.78,
            baseline_recall=0.40,
            recall_delta=0.38,
            bootstrap_ci_95=(0.20, 0.55),
            recall_with_errors=0.78,
            recall_excluding_errors=0.78,
            per_fixture_pass_rates={"F001": {"agent": [1.0], "baseline": [0.0]}},
            flakiness=False,
            flaky_fixtures_detected=[],
            flaky_fixtures_excluded=[],
            halt_due_to_flakiness=False,
            total_tokens_in=100,
            total_tokens_out=50,
            cost_estimate_usd=0.01,
            tokens_estimated=True,
            error_count=0,
            pricing_rate_as_of="2026-05-03",
        )

    def test_default_recommendation_renders_pending(self, tmp_path):
        writer = ReportWriter(tmp_path / "reports")
        json_path, md_path = writer.write(
            aggregate=self._agg(),
            run_id="rid",
            model_id="claude-sonnet-4-6",
            agent_prompt_sha="a" * 64,
            baseline_prompt_sha="b" * 64,
            fixture_set_sha="c" * 64,
            wall_clock_seconds=12.3,
        )
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["recommendation"] is None
        md = md_path.read_text(encoding="utf-8")
        assert "Pending" in md
        assert "Verdict" not in md.split("## Recommendation", 1)[1].split("##", 1)[0]

    def test_explicit_recommendation_round_trips(self, tmp_path):
        writer = ReportWriter(tmp_path / "reports")
        json_path, md_path = writer.write(
            aggregate=self._agg(),
            run_id="rid",
            model_id="claude-sonnet-4-6",
            agent_prompt_sha="a" * 64,
            baseline_prompt_sha="b" * 64,
            fixture_set_sha="c" * 64,
            wall_clock_seconds=12.3,
            recommendation="halt-due-to-flakiness",
        )
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["recommendation"] == "halt-due-to-flakiness"
        md = md_path.read_text(encoding="utf-8")
        assert "halt-due-to-flakiness" in md
        assert "Pending" not in md.split("## Recommendation", 1)[1].split("##", 1)[0]

    def _agg_halted(self) -> "AggregateResult":
        # Variant of _agg() with the flakiness gate tripped: AC-10 halt
        # implies flakiness, so both flags are set.
        return AggregateResult(
            agent_recall=0.78,
            baseline_recall=0.40,
            recall_delta=0.38,
            bootstrap_ci_95=(0.11, 0.64),
            recall_with_errors=0.78,
            recall_excluding_errors=0.78,
            per_fixture_pass_rates={"F001": {"agent": [1.0], "baseline": [0.0]}},
            flakiness=True,
            flaky_fixtures_detected=["F001", "F002", "F003", "F005"],
            flaky_fixtures_excluded=["F001", "F002", "F003", "F005"],
            halt_due_to_flakiness=True,
            total_tokens_in=100,
            total_tokens_out=50,
            cost_estimate_usd=0.01,
            tokens_estimated=True,
            error_count=0,
            pricing_rate_as_of="2026-05-03",
        )

    def test_ci_section_marks_halt_run(self, tmp_path):
        # When the run is halt-due-to-flakiness, the CI section MUST
        # carry a caveat so a CI that excludes zero is not misread as
        # blessing the halted verdict.
        writer = ReportWriter(tmp_path / "reports")
        _, md_path = writer.write(
            aggregate=self._agg_halted(),
            run_id="rid",
            model_id="claude-sonnet-4-6",
            agent_prompt_sha="a" * 64,
            baseline_prompt_sha="b" * 64,
            fixture_set_sha="c" * 64,
            wall_clock_seconds=12.3,
            recommendation="halt-due-to-flakiness",
        )
        ci_section = (
            md_path.read_text(encoding="utf-8")
            .split("## Confidence Interval", 1)[1]
            .split("##", 1)[0]
        )
        assert "halted at AC-10" in ci_section
        assert "does not unblock the verdict" in ci_section

    def test_ci_section_marks_flaky_no_halt_run(self, tmp_path):
        # Flaky-but-not-halted (variance present, but threshold not
        # crossed): note that flaky fixtures are excluded from the
        # delta, without claiming the verdict is blocked.
        agg = AggregateResult(
            agent_recall=0.78,
            baseline_recall=0.40,
            recall_delta=0.38,
            bootstrap_ci_95=(0.20, 0.55),
            recall_with_errors=0.78,
            recall_excluding_errors=0.78,
            per_fixture_pass_rates={"F001": {"agent": [1.0], "baseline": [0.0]}},
            flakiness=True,
            flaky_fixtures_detected=["F001"],
            flaky_fixtures_excluded=["F001"],
            halt_due_to_flakiness=False,
            total_tokens_in=100,
            total_tokens_out=50,
            cost_estimate_usd=0.01,
            tokens_estimated=True,
            error_count=0,
            pricing_rate_as_of="2026-05-03",
        )
        writer = ReportWriter(tmp_path / "reports")
        _, md_path = writer.write(
            aggregate=agg,
            run_id="rid",
            model_id="claude-sonnet-4-6",
            agent_prompt_sha="a" * 64,
            baseline_prompt_sha="b" * 64,
            fixture_set_sha="c" * 64,
            wall_clock_seconds=12.3,
        )
        ci_section = (
            md_path.read_text(encoding="utf-8")
            .split("## Confidence Interval", 1)[1]
            .split("##", 1)[0]
        )
        assert "flaky fixtures are excluded" in ci_section
        assert "halted at AC-10" not in ci_section

    def test_ci_section_no_caveat_on_clean_run(self, tmp_path):
        writer = ReportWriter(tmp_path / "reports")
        _, md_path = writer.write(
            aggregate=self._agg(),
            run_id="rid",
            model_id="claude-sonnet-4-6",
            agent_prompt_sha="a" * 64,
            baseline_prompt_sha="b" * 64,
            fixture_set_sha="c" * 64,
            wall_clock_seconds=12.3,
        )
        ci_section = (
            md_path.read_text(encoding="utf-8")
            .split("## Confidence Interval", 1)[1]
            .split("##", 1)[0]
        )
        assert "halted at AC-10" not in ci_section
        assert "flaky fixtures are excluded" not in ci_section


class TestCliInputValidators:
    """Allow-list validators on `--agent`, `--run-id`, and `--resume`
    prevent CWE-22 path traversal (PR 1873)."""

    def test_agent_name_validator_accepts_canonical_names(self):
        for name in ("security", "qa", "architect", "agent_x", "agent-x"):
            assert cli_mod._agent_name_arg(name) == name

    @pytest.mark.parametrize(
        "bad",
        [
            "../../etc/passwd",
            "Security",  # uppercase
            "security/x",
            "security.shared",
            "1security",
            "",
            "a" * 32,  # too long
        ],
    )
    def test_agent_name_validator_rejects_traversal_and_invalid(self, bad):
        import argparse as _argparse
        with pytest.raises(_argparse.ArgumentTypeError):
            cli_mod._agent_name_arg(bad)

    def test_run_id_validator_accepts_iso_uuid_shape(self):
        # Same shape `_generate_run_id` produces.
        assert cli_mod._run_id_arg("20260503T182553Z-eaa08f8d")

    @pytest.mark.parametrize("bad", ["..", "/etc/passwd", "rid/../x", "a" * 65])
    def test_run_id_validator_rejects_traversal(self, bad):
        import argparse as _argparse
        with pytest.raises(_argparse.ArgumentTypeError):
            cli_mod._run_id_arg(bad)

    def test_assert_under_repo_root_rejects_outside(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
        with pytest.raises(FileNotFoundError, match="outside REPO_ROOT"):
            cli_mod._assert_under_repo_root(tmp_path.parent / "escape")

    def test_assert_under_repo_root_accepts_inside(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_mod, "REPO_ROOT", tmp_path)
        inside = tmp_path / "evals" / "security-spike"
        # Does not require existence.
        resolved = cli_mod._assert_under_repo_root(inside)
        assert resolved.is_relative_to(tmp_path.resolve())
