"""Unit tests for scripts/eval/eval-model-sweep.py (Issue #2840).

Covers the orchestrator's pure seams (argv builder, report parser, model-id
parsing, pricing pre-check) and an end-to-end sweep with an injected fake
runner (no API, no subprocess). Also guards DEFAULT_MODEL against drift from
the base evaluator.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"
SWEEP_SCRIPT = EVAL_DIR / "eval-model-sweep.py"
BASE_SCRIPT = EVAL_DIR / "eval-agent-vs-baseline.py"

# eval-model-sweep.py imports sibling modules via plain `from X import Y`, so
# EVAL_DIR must be on sys.path while it loads. Scope the mutation to the load
# and remove it afterward so we do not change import resolution for other
# test modules.
_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    # The script filename has hyphens, so import it by path.
    _spec = importlib.util.spec_from_file_location("eval_model_sweep", SWEEP_SCRIPT)
    assert _spec and _spec.loader
    sweep = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(sweep)
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))

core = sys.modules["_model_sweep_core"]


class _FakeRunner:
    """Injectable runner returning canned ModelResults; records call order."""

    def __init__(self, results_by_model):
        self._by_model = results_by_model
        self.calls = []
        self.last_fixture_sha = "fakesha"

    def run(self, model_id):
        self.calls.append(model_id)
        return self._by_model[model_id]


def _result(model_id, rate, **kw):
    kw.setdefault("fixture_set_sha", "fakesha")
    return core.ModelResult(
        model_id=model_id,
        agent_recall=rate,
        per_fixture_agent_rates={f"f{i}": [rate] for i in range(8)},
        **kw,
    )


def _args(**overrides):
    base = dict(
        agent="security",
        fixtures=EVAL_DIR,  # any existing path
        models="",
        default_model=sweep.DEFAULT_MODEL,
        n_runs=3,
        min_effect=0.05,
        seed=42,
        provider=None,
        output=None,
        dry_run=False,
        child_timeout=sweep.DEFAULT_CHILD_TIMEOUT_S,
    )
    base.update(overrides)
    return type("Args", (), base)()


# --- pure seams -----------------------------------------------------------


def test_parse_models_dedupes_and_adds_default():
    models = sweep.parse_models_arg(
        "claude-opus-4-6, claude-opus-4-6 ,",
        default_model="claude-sonnet-4-6",
    )
    assert models == ["claude-opus-4-6", "claude-sonnet-4-6"]


def test_parse_models_keeps_default_position_if_present():
    models = sweep.parse_models_arg(
        "claude-sonnet-4-6,claude-opus-4-6",
        default_model="claude-sonnet-4-6",
    )
    assert models == ["claude-sonnet-4-6", "claude-opus-4-6"]


def test_parse_models_rejects_bad_id():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        sweep.parse_models_arg("bad id!", default_model="d")


def test_parse_models_rejects_empty():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        sweep.parse_models_arg("  , ", default_model="d")


def test_validate_models_priced_flags_unpriced():
    priced = next(iter(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS))
    unpriced = sweep.validate_models_priced([priced, "made-up-model"])
    assert unpriced == ["made-up-model"]


def test_make_run_id_is_path_safe():
    run_id = sweep.make_run_id("claude-opus-4.6", unique="abcd1234")
    assert re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$", run_id)
    assert run_id == "sweep-claude-opus-4-6-abcd1234"


def test_build_child_argv_includes_run_id_and_provider():
    argv = sweep.build_child_argv(
        agent="security",
        fixtures=Path("tests/evals/x"),
        model_id="claude-sonnet-4-6",
        n_runs=5,
        run_id="sweep-x-1",
        provider="anthropic",
    )
    assert str(BASE_SCRIPT) in argv
    assert argv[argv.index("--model") + 1] == "claude-sonnet-4-6"
    assert argv[argv.index("--n-runs") + 1] == "5"
    assert argv[argv.index("--run-id") + 1] == "sweep-x-1"
    assert argv[argv.index("--provider") + 1] == "anthropic"


def test_build_child_argv_omits_provider_when_absent():
    argv = sweep.build_child_argv(
        agent="security",
        fixtures=Path("tests/evals/x"),
        model_id="claude-sonnet-4-6",
        n_runs=1,
        run_id="sweep-x-1",
        provider=None,
    )
    assert "--provider" not in argv


def test_parse_report_extracts_agent_rates():
    report = {
        "agent_recall": 0.75,
        "fixture_set_sha": "sha-abc",
        "per_fixture_pass_rates": {
            "f1": {"agent": [1.0, 0.5], "baseline": [0.0]},
            "f2": {"agent": [0.5]},
        },
        "total_tokens_in": 100,
        "total_tokens_out": 200,
        "cost_estimate_usd": 0.05,
        "error_count": 2,
    }
    result = sweep.parse_report(report, model_id="m1")
    assert result.model_id == "m1"
    assert result.agent_recall == 0.75
    assert result.per_fixture_agent_rates == {"f1": [1.0, 0.5], "f2": [0.5]}
    assert result.tokens_in == 100
    assert result.tokens_out == 200
    assert result.cost_usd == 0.05
    assert result.error_count == 2


@pytest.mark.parametrize(
    "per_fixture",
    [
        {"f1": {"agent": []}},
        {"f1": {"agent": [True]}},
        {"f1": {"agent": [2.0]}},
        {"f1": {"agent": [float("nan")]}},
        {"f1": {"baseline": [1.0]}},
        {"f1": ["not", "a", "variant", "mapping"]},
    ],
)
def test_parse_report_rejects_missing_or_impossible_rates(per_fixture):
    report = {
        "agent_recall": 1.0,
        "fixture_set_sha": "sha-abc",
        "per_fixture_pass_rates": per_fixture,
        "error_count": 0,
    }

    with pytest.raises(ValueError):
        sweep.parse_report(report, model_id="m1")


@pytest.mark.parametrize("agent_recall", [True, 2.0, float("nan")])
def test_parse_report_rejects_impossible_agent_recall(agent_recall):
    report = {
        "agent_recall": agent_recall,
        "fixture_set_sha": "sha-abc",
        "per_fixture_pass_rates": {"f1": {"agent": [1.0]}},
        "error_count": 0,
    }

    with pytest.raises(ValueError, match="agent_recall"):
        sweep.parse_report(report, model_id="m1")


@pytest.mark.parametrize(
    "bad_report",
    [
        {},  # empty object: missing every required field
        [],  # not a JSON object
        {"agent_recall": 0.5, "per_fixture_pass_rates": {}},  # no sha
        {"agent_recall": 0.5, "fixture_set_sha": "", "per_fixture_pass_rates": {}},
        {"fixture_set_sha": "s", "per_fixture_pass_rates": {}},  # no recall
        {"fixture_set_sha": "s", "agent_recall": 0.5},  # no per_fixture
        {
            "fixture_set_sha": "s",
            "agent_recall": 0.5,
            "per_fixture_pass_rates": [],  # wrong type
        },
        {
            "fixture_set_sha": "s",
            "agent_recall": 0.5,
            "per_fixture_pass_rates": {},
            "flaky_fixtures_excluded": "f1",  # string, not a list of ids
        },
        {
            "fixture_set_sha": "s",
            "agent_recall": 0.5,
            "per_fixture_pass_rates": {},
            "flaky_fixtures_excluded": ["f1", 7],  # non-string element
        },
        {
            "fixture_set_sha": "s",
            "agent_recall": 0.5,
            "per_fixture_pass_rates": {},
            "flaky_fixtures_excluded": [["nested"]],  # unhashable element
        },
        {
            "fixture_set_sha": "s",
            "agent_recall": 0.5,
            "per_fixture_pass_rates": {},
        },
        {
            "fixture_set_sha": "s",
            "agent_recall": 0.5,
            "per_fixture_pass_rates": {},
            "error_count": "0",
        },
        {
            "fixture_set_sha": "s",
            "agent_recall": 0.5,
            "per_fixture_pass_rates": {},
            "error_count": None,
        },
        {
            "fixture_set_sha": "s",
            "agent_recall": 0.5,
            "per_fixture_pass_rates": {},
            "error_count": -1,
        },
    ],
)
def test_parse_report_rejects_schema_invalid(bad_report):
    with pytest.raises((KeyError, ValueError)):
        sweep.parse_report(bad_report, model_id="m1")


def test_parse_report_accepts_list_flaky_exclusions():
    report = {
        "agent_recall": 1.0,
        "fixture_set_sha": "sha-abc",
        "per_fixture_pass_rates": {
            "f1": {"agent": [1.0]},
            "f2": {"agent": [0.5]},
        },
        "flaky_fixtures_excluded": ["f2"],
        "error_count": 0,
    }
    result = sweep.parse_report(report, model_id="m1")
    assert result.per_fixture_agent_rates == {"f1": [1.0]}


def test_parse_models_rejects_bad_default_model():
    import argparse

    with pytest.raises(argparse.ArgumentTypeError, match="default-model"):
        sweep.parse_models_arg("claude-opus-4-6", default_model="bad id!")


def test_run_sweep_preserves_child_logic_exit(capsys):
    priced = list(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS)[0]

    class _LogicBoom:
        def run(self, model_id):
            raise sweep.ChildRunError(model_id, sweep.EXIT_LOGIC, "empty run")

    args = _args(models=priced, default_model=priced)
    rc = sweep.run_sweep(args, runner=_LogicBoom())
    assert rc == sweep.EXIT_LOGIC


def test_run_sweep_preserves_child_auth_exit(capsys):
    priced = list(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS)[0]

    class _AuthBoom:
        def run(self, model_id):
            raise sweep.ChildRunError(model_id, sweep.EXIT_AUTH, "401")

    args = _args(models=priced, default_model=priced)
    rc = sweep.run_sweep(args, runner=_AuthBoom())
    assert rc == sweep.EXIT_AUTH


def test_run_sweep_unknown_child_exit_maps_to_external(capsys):
    priced = list(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS)[0]

    class _WeirdBoom:
        def run(self, model_id):
            raise sweep.ChildRunError(model_id, 99, "who knows")

    args = _args(models=priced, default_model=priced)
    rc = sweep.run_sweep(args, runner=_WeirdBoom())
    assert rc == sweep.EXIT_EXTERNAL


def test_parse_report_excludes_flaky_fixtures():
    report = {
        "agent_recall": 1.0,
        "per_fixture_pass_rates": {
            "stable": {"agent": [1.0]},
            "flaky": {"agent": [0.0, 1.0]},
        },
        "flaky_fixtures_excluded": ["flaky"],
        "fixture_set_sha": "sha1",
        "error_count": 0,
    }
    result = sweep.parse_report(report, model_id="m1")
    assert set(result.per_fixture_agent_rates) == {"stable"}
    assert result.fixture_set_sha == "sha1"


def test_make_run_id_preserves_suffix_for_long_model_id():
    long_id = "z" * 64
    a = sweep.make_run_id(long_id, unique="aaaaaaaa")
    b = sweep.make_run_id(long_id, unique="bbbbbbbb")
    assert a != b
    assert a.endswith("-aaaaaaaa")
    assert b.endswith("-bbbbbbbb")
    assert len(a) <= 64 and len(b) <= 64
    path = sweep.child_report_path("security", "sweep-x-1")
    assert path.name == "report.json"
    assert path.parent.name == "sweep-x-1"
    assert "security-spike" in str(path)


# --- orchestration (fake runner) ------------------------------------------


def test_run_sweep_dry_run_lists_plan_and_exits_ok(capsys):
    priced = list(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS)[:1]
    args = _args(models=",".join(priced), default_model=priced[0], dry_run=True)
    rc = sweep.run_sweep(args, runner=None)
    out = capsys.readouterr().out
    assert rc == sweep.EXIT_OK
    assert "sweep plan" in out
    assert priced[0] in out


def test_run_sweep_live_path_without_runner_is_config_error(capsys, tmp_path):
    # All inputs valid + not dry-run => the live loop is reached; a missing
    # runner must fail cleanly (EXIT_CONFIG), not AttributeError on None.run().
    priced = list(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS)[0]
    args = _args(models=priced, default_model=priced, fixtures=tmp_path)
    rc = sweep.run_sweep(args, runner=None)
    assert rc == sweep.EXIT_CONFIG
    assert "without a runner" in capsys.readouterr().err


def test_run_sweep_unpriced_model_is_config_error(capsys):
    priced = list(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS)[0]
    args = _args(models=f"{priced},totally-made-up", default_model=priced)
    rc = sweep.run_sweep(args, runner=None)
    err = capsys.readouterr().err
    assert rc == sweep.EXIT_CONFIG
    assert "no pricing rate" in err
    assert "totally-made-up" in err


def test_run_sweep_missing_fixtures_is_config_error(capsys):
    priced = list(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS)[0]
    args = _args(
        models=priced,
        default_model=priced,
        fixtures=Path("/nonexistent/path/xyz"),
    )
    rc = sweep.run_sweep(args, runner=None)
    assert rc == sweep.EXIT_CONFIG
    assert "fixtures path not found" in capsys.readouterr().err


def test_run_sweep_keep_pin_end_to_end(tmp_path, capsys):
    priced = list(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS)
    default_id = priced[0]
    # Candidate id must also be priced to pass the pre-check; reuse a second
    # priced id if available, else fabricate results keyed on the same set.
    candidate_id = priced[1] if len(priced) > 1 else None
    if candidate_id is None:
        pytest.skip(
            "needs >=2 priced models to exercise the two-model KEEP path"
        )
    results = {
        default_id: _result(default_id, 0.10),
        candidate_id: _result(candidate_id, 0.90, cost_usd=0.2, error_count=0),
    }
    runner = _FakeRunner(results)
    output = tmp_path / "sweep.json"
    args = _args(
        models=f"{default_id},{candidate_id}",
        default_model=default_id,
        output=output,
    )
    rc = sweep.run_sweep(args, runner=runner)
    out = capsys.readouterr().out
    assert rc == sweep.EXIT_OK
    assert runner.calls == [default_id, candidate_id]
    assert core.DECISION_KEEP in out
    artifact = json.loads(output.read_text(encoding="utf-8"))
    assert artifact["winner"] == candidate_id
    assert artifact["decision"] == core.DECISION_KEEP
    assert artifact["fixtures_sha"] == "fakesha"


def test_run_sweep_artifact_write_failure_maps_to_external(tmp_path, capsys):
    priced = list(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS)
    if len(priced) < 2:
        pytest.skip("needs >=2 priced models to reach the artifact-write step")
    default_id, candidate_id = priced[0], priced[1]
    results = {
        default_id: _result(default_id, 0.10),
        candidate_id: _result(candidate_id, 0.90, cost_usd=0.2, error_count=0),
    }
    # Use a regular file as a directory component so mkdir(parents=True) raises
    # NotADirectoryError (an OSError) on a valid, non-decision path.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    output = blocker / "sub" / "sweep.json"
    args = _args(
        models=f"{default_id},{candidate_id}",
        default_model=default_id,
        output=output,
    )
    rc = sweep.run_sweep(args, runner=_FakeRunner(results))
    captured = capsys.readouterr()
    assert rc == sweep.EXIT_EXTERNAL
    # The verdict is still emitted to stdout before the write is attempted.
    assert core.DECISION_KEEP in captured.out
    assert "could not write artifact" in captured.err


def test_run_sweep_child_failure_is_external_error(capsys):
    priced = list(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS)[0]

    class _Boom:
        def run(self, model_id):
            raise sweep.ChildRunError(model_id, 3, "boom")

    args = _args(models=priced, default_model=priced)
    rc = sweep.run_sweep(args, runner=_Boom())
    assert rc == sweep.EXIT_EXTERNAL
    assert "boom" in capsys.readouterr().err


def test_run_sweep_child_config_failure_maps_to_config(capsys):
    priced = list(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS)[0]

    class _ConfigBoom:
        def run(self, model_id):
            raise sweep.ChildRunError(model_id, sweep.EXIT_CONFIG, "bad fixtures")

    args = _args(models=priced, default_model=priced)
    rc = sweep.run_sweep(args, runner=_ConfigBoom())
    assert rc == sweep.EXIT_CONFIG


def test_run_sweep_child_auth_failure_maps_to_auth(capsys):
    priced = list(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS)[0]

    class _AuthBoom:
        def run(self, model_id):
            raise sweep.ChildRunError(model_id, sweep.EXIT_AUTH, "bad api key")

    args = _args(models=priced, default_model=priced)
    rc = sweep.run_sweep(args, runner=_AuthBoom())
    assert rc == sweep.EXIT_AUTH


def test_runner_unreadable_report_raises_external_child_error(tmp_path, monkeypatch):
    runner = sweep.SubprocessModelEvalRunner(
        agent="security", fixtures=tmp_path, n_runs=1, provider=None, env={}
    )

    class _Completed:
        returncode = sweep.EXIT_OK
        stderr = ""

    monkeypatch.setattr(sweep.subprocess, "run", lambda *a, **k: _Completed())
    # Point at a report path that does not exist -> read_text raises OSError.
    monkeypatch.setattr(
        sweep, "child_report_path", lambda agent, run_id: tmp_path / "missing.json"
    )
    with pytest.raises(sweep.ChildRunError) as excinfo:
        runner.run("claude-sonnet-4")
    assert excinfo.value.returncode == sweep.EXIT_EXTERNAL


def test_runner_honors_explicit_empty_env(tmp_path, monkeypatch):
    runner = sweep.SubprocessModelEvalRunner(
        agent="security", fixtures=tmp_path, n_runs=1, provider=None, env={}
    )
    captured = {}

    class _Completed:
        returncode = sweep.EXIT_OK
        stderr = ""

    def _fake_run(argv, **kwargs):
        captured["env"] = kwargs.get("env")
        return _Completed()

    monkeypatch.setattr(sweep.subprocess, "run", _fake_run)
    monkeypatch.setattr(
        sweep, "child_report_path", lambda agent, run_id: tmp_path / "missing.json"
    )
    with pytest.raises(sweep.ChildRunError):
        runner.run("claude-sonnet-4")
    # An explicit empty env must NOT be replaced by the parent environment.
    assert captured["env"] == {}


def test_runner_timeout_maps_to_external_child_error(tmp_path, monkeypatch):
    runner = sweep.SubprocessModelEvalRunner(
        agent="security",
        fixtures=tmp_path,
        n_runs=1,
        provider=None,
        child_timeout=0.01,
        env={},
    )

    def _raise_timeout(argv, **kwargs):
        # The runner must forward its configured timeout to subprocess.run.
        assert kwargs.get("timeout") == 0.01
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(sweep.subprocess, "run", _raise_timeout)
    with pytest.raises(sweep.ChildRunError) as excinfo:
        runner.run("claude-sonnet-4")
    assert excinfo.value.returncode == sweep.EXIT_EXTERNAL
    assert "timed out" in str(excinfo.value)


@pytest.mark.parametrize(
    "bad_timeout", [0, -1, -0.5, float("nan"), float("inf"), float("-inf")]
)
def test_run_sweep_rejects_nonpositive_or_nonfinite_child_timeout(
    bad_timeout, capsys
):
    priced = list(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS)[0]

    class _NeverRuns:
        def run(self, model_id):  # pragma: no cover - must not be reached
            raise AssertionError("runner invoked despite bad timeout")

    args = _args(models=priced, default_model=priced, child_timeout=bad_timeout)
    rc = sweep.run_sweep(args, runner=_NeverRuns())
    assert rc == sweep.EXIT_CONFIG
    assert "child-timeout" in capsys.readouterr().err


def test_arg_parser_child_timeout_defaults(monkeypatch):
    parser = sweep._build_arg_parser()
    args = parser.parse_args(
        ["--agent", "security", "--fixtures", str(EVAL_DIR), "--models", "x"]
    )
    assert args.child_timeout == sweep.DEFAULT_CHILD_TIMEOUT_S


def test_default_output_path_is_unique_within_same_second():
    a = sweep._default_output_path("security")
    b = sweep._default_output_path("security")
    assert a != b
    assert a.name.startswith("sweep-") and a.name.endswith(".json")


def test_run_sweep_rejects_zero_n_runs(capsys):
    priced = list(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS)[0]
    args = _args(models=priced, default_model=priced, n_runs=0)
    rc = sweep.run_sweep(args, runner=None)
    assert rc == sweep.EXIT_CONFIG
    assert "--n-runs must be >= 1" in capsys.readouterr().err


def test_run_sweep_mismatched_fixture_sha_is_config_error(capsys):
    priced = list(sweep.MODEL_PRICING_RATES_USD_PER_1K_TOKENS)
    if len(priced) < 2:
        pytest.skip("needs >=2 priced models to build a mismatched-sha pair")
    default_id, candidate_id = priced[0], priced[1]
    results = {
        default_id: _result(default_id, 0.5, fixture_set_sha="shaA"),
        candidate_id: _result(candidate_id, 0.9, fixture_set_sha="shaB"),
    }
    args = _args(models=f"{default_id},{candidate_id}", default_model=default_id)
    rc = sweep.run_sweep(args, runner=_FakeRunner(results))
    assert rc == sweep.EXIT_CONFIG
    assert "different fixture sets" in capsys.readouterr().err


# --- drift guard ----------------------------------------------------------


def test_default_model_matches_base_evaluator():
    text = BASE_SCRIPT.read_text(encoding="utf-8")
    match = re.search(r'^DEFAULT_MODEL\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "could not find DEFAULT_MODEL in eval-agent-vs-baseline.py"
    assert match.group(1) == sweep.DEFAULT_MODEL
