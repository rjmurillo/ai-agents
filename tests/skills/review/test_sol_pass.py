"""Tests for the cross-family Sol pass that runs after the fresh critic.

The reviewer call is injected, so no test reaches a model. Covers ordering
after the critic, the 2-round cap, dropping findings without a file, line, or
repro, the Sol-only log, the unavailable WARN path with no fallback, the model
allowlist, the off switch, and conformance with the review model policy.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/review/scripts/sol_pass.py", module_name="sol_pass_under_test"
)

CRITIC_TEXT = (
    "## Critical Findings\n1. `src/app/a.py:10` drops the error.\n\nVerdict: NEEDS_REVISION\n"
)


class FakeRunner:
    """Records every reviewer call and returns a canned result."""

    def __init__(self, result):
        self.result = result
        self.calls: list[dict] = []

    def __call__(self, model, prompt, schema_path, cwd, timeout):
        self.calls.append(
            {"model": model, "prompt": prompt, "schema": json.loads(schema_path.read_text())}
        )
        return self.result


def _ok(findings):
    return mod.RunResult(ok=True, text=json.dumps({"findings": findings}))


def _finding(**overrides):
    base = {
        "file": "src/app/b.py",
        "line": 5,
        "repro": "pytest tests/test_b.py::test_empty fails with KeyError",
        "summary": "KeyError on empty input",
        "severity": "high",
        "category": "correctness",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("AI_AGENTS_ARTIFACT_ROOT", "AI_AGENTS_SOL_PASS", "AI_AGENTS_SOL_MODEL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def critic_file(tmp_path):
    path = tmp_path / "critic.md"
    path.write_text(CRITIC_TEXT, encoding="utf-8")
    return path


def _run(tmp_path, runner, *extra):
    argv = ["run", "--repo", str(tmp_path), "--log-base", str(tmp_path), *extra]
    return mod.main(argv, runner=runner)


def _logs(tmp_path):
    log_dir = tmp_path / ".project-toolkit" / "metrics" / "sol-pass"
    return [json.loads(p.read_text()) for p in sorted(log_dir.glob("*.json"))]


# Ordering after the critic


def test_refuses_to_run_without_critic_output(tmp_path, capsys):
    runner = FakeRunner(_ok([]))

    code = _run(tmp_path, runner, "--critic-findings", str(tmp_path / "missing.md"))

    assert code == mod.EXIT_CONFIG
    assert runner.calls == []
    assert "after the fresh critic" in capsys.readouterr().err


def test_refuses_to_run_with_empty_critic_output(tmp_path):
    empty = tmp_path / "critic.md"
    empty.write_text("  \n", encoding="utf-8")
    runner = FakeRunner(_ok([]))

    code = _run(tmp_path, runner, "--critic-findings", str(empty))

    assert code == mod.EXIT_CONFIG
    assert runner.calls == []


def test_critic_findings_flag_is_required():
    with pytest.raises(SystemExit) as exc:
        mod.build_parser().parse_args(["run"])
    assert exc.value.code == 2


def test_sol_never_sees_the_critic_findings(tmp_path, critic_file):
    runner = FakeRunner(_ok([]))

    _run(tmp_path, runner, "--critic-findings", str(critic_file))

    assert "src/app/a.py:10" not in runner.calls[0]["prompt"]


def test_orchestrator_routes_sol_pass_after_readiness_critic():
    for rendered in (
        "src/claude/agents/orchestrator.md",
        "src/copilot-cli/agents/orchestrator.agent.md",
    ):
        text = (PROJECT_ROOT / rendered).read_text(encoding="utf-8")
        line = next(ln for ln in text.splitlines() if "critic (readiness)" in ln)
        assert line.index("critic (readiness)") < line.index("sol pass"), rendered


# Two-round cap


def test_round_three_escalates_without_a_model_call(tmp_path, critic_file, capsys):
    runner = FakeRunner(_ok([_finding()]))

    code = _run(tmp_path, runner, "--critic-findings", str(critic_file), "--round", "3")

    assert code == mod.EXIT_ESCALATE
    assert runner.calls == []
    assert json.loads(capsys.readouterr().out)["verdict"] == "ESCALATE"
    assert _logs(tmp_path)[0]["status"] == "escalated"


def test_round_two_runs_with_frozen_contract(tmp_path, critic_file):
    runner = FakeRunner(_ok([]))

    code = _run(tmp_path, runner, "--critic-findings", str(critic_file), "--round", "2")

    assert code == mod.EXIT_OK
    assert "This is round 2" in runner.calls[0]["prompt"]


def test_round_one_has_no_frozen_contract(tmp_path, critic_file):
    runner = FakeRunner(_ok([]))

    _run(tmp_path, runner, "--critic-findings", str(critic_file))

    assert "This is round 2" not in runner.calls[0]["prompt"]


def test_round_zero_is_a_config_error(tmp_path, critic_file):
    runner = FakeRunner(_ok([]))

    assert (
        _run(tmp_path, runner, "--critic-findings", str(critic_file), "--round", "0")
        == mod.EXIT_CONFIG
    )
    assert runner.calls == []


def test_max_rounds_is_two():
    assert mod.MAX_ROUNDS == 2


# Findings need file, line, and repro; style nits dropped


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"file": ""}, "missing-file"),
        ({"file": None}, "missing-file"),
        ({"line": None}, "missing-line"),
        ({"line": 0}, "missing-line"),
        ({"line": "12"}, "missing-line"),
        ({"line": True}, "missing-line"),
        ({"repro": ""}, "missing-repro"),
        ({"repro": "   "}, "missing-repro"),
        ({"category": "Style"}, "style-nit"),
        ({"category": "naming"}, "style-nit"),
    ],
)
def test_drops_incomplete_or_style_findings(override, reason):
    kept, dropped = mod.filter_findings([_finding(**override)])

    assert kept == []
    assert dropped[0]["reason"] == reason


def test_drops_non_object_findings():
    kept, dropped = mod.filter_findings(["src/a.py:1 bad"])

    assert kept == []
    assert dropped[0]["reason"] == "not-an-object"


def test_keeps_complete_finding():
    kept, dropped = mod.filter_findings([_finding()])

    assert dropped == []
    assert kept[0]["file"] == "src/app/b.py"


def test_dropped_findings_are_logged_not_reported(tmp_path, critic_file, capsys):
    runner = FakeRunner(_ok([_finding(repro=""), _finding()]))

    _run(tmp_path, runner, "--critic-findings", str(critic_file))

    out = json.loads(capsys.readouterr().out)
    log = _logs(tmp_path)[0]
    assert len(out["findings"]) == 1
    assert log["counts"] == {"raw": 2, "kept": 1, "dropped": 1, "sol_only": 1, "overlap": 0}
    assert log["dropped"][0]["reason"] == "missing-repro"


# Sol-only logging


def test_logs_sol_only_and_overlap(tmp_path, critic_file, capsys):
    overlap = _finding(file="src/app/a.py", line=12)
    sol_only = _finding(file="src/app/b.py", line=5)
    runner = FakeRunner(_ok([overlap, sol_only]))

    code = _run(tmp_path, runner, "--critic-findings", str(critic_file), "--pr", "123")

    assert code == mod.EXIT_OK
    assert json.loads(capsys.readouterr().out)["verdict"] == "WARN"
    logs = _logs(tmp_path)
    assert len(logs) == 1
    log = logs[0]
    assert log["status"] == "ok"
    assert log["pr"] == "123"
    assert log["model"] == mod.DEFAULT_SOL_MODEL
    assert log["counts"]["sol_only"] == 1
    assert log["counts"]["overlap"] == 1
    by_file = {f["file"]: f["sol_only"] for f in log["findings"]}
    assert by_file == {"src/app/a.py": False, "src/app/b.py": True}
    assert len(log["critic_sha256"]) == 64


def test_overlap_window_boundary():
    findings = [_finding(file="src/app/a.py", line=13), _finding(file="src/app/a.py", line=14)]

    marked = mod.mark_sol_only(findings, CRITIC_TEXT)

    assert [f["sol_only"] for f in marked] == [False, True]


def test_overlap_matches_path_suffix():
    marked = mod.mark_sol_only([_finding(file="a.py", line=10)], "see app/a.py:10")

    assert marked[0]["sol_only"] is False


def test_empty_result_passes_and_still_logs(tmp_path, critic_file, capsys):
    runner = FakeRunner(_ok([]))

    _run(tmp_path, runner, "--critic-findings", str(critic_file))

    assert json.loads(capsys.readouterr().out)["verdict"] == "PASS"
    assert _logs(tmp_path)[0]["counts"]["kept"] == 0


def test_each_run_gets_its_own_log_file(tmp_path, critic_file):
    runner = FakeRunner(_ok([]))

    _run(tmp_path, runner, "--critic-findings", str(critic_file))
    _run(tmp_path, runner, "--critic-findings", str(critic_file))

    assert len(_logs(tmp_path)) == 2


def test_artifact_root_override_redirects_log(tmp_path, critic_file, monkeypatch):
    durable = tmp_path / "durable"
    monkeypatch.setenv("AI_AGENTS_ARTIFACT_ROOT", str(durable))

    mod.main(
        ["run", "--repo", str(tmp_path), "--critic-findings", str(critic_file)],
        runner=FakeRunner(_ok([])),
    )

    assert len(list((durable / "metrics" / "sol-pass").glob("*.json"))) == 1


def test_summarize_totals_runs(tmp_path, critic_file, capsys):
    _run(
        tmp_path,
        FakeRunner(_ok([_finding(), _finding(file="src/app/a.py", line=10)])),
        "--critic-findings",
        str(critic_file),
    )
    _run(
        tmp_path,
        FakeRunner(mod.RunResult(ok=False, failure_class="timeout")),
        "--critic-findings",
        str(critic_file),
    )
    (tmp_path / ".project-toolkit" / "metrics" / "sol-pass" / "broken.json").write_text(
        "{", encoding="utf-8"
    )
    capsys.readouterr()

    code = mod.main(["summarize", "--repo", str(tmp_path), "--log-base", str(tmp_path)])

    totals = json.loads(capsys.readouterr().out)
    assert code == mod.EXIT_OK
    assert totals["runs"] == 2
    assert totals["ok"] == 1
    assert totals["unavailable"] == 1
    assert totals["sol_only"] == 1
    assert totals["overlap"] == 1
    assert totals["unreadable"] == 1


# Unavailable path: WARN, no same-family fallback


@pytest.mark.parametrize(
    "failure", ["timeout", "rate-limit", "quota", "5xx", "not-installed", "model-unsupported"]
)
def test_unavailable_warns_and_makes_one_call(tmp_path, critic_file, capsys, failure):
    runner = FakeRunner(mod.RunResult(ok=False, failure_class=failure, detail="boom"))

    code = _run(tmp_path, runner, "--critic-findings", str(critic_file))

    out = json.loads(capsys.readouterr().out)
    assert code == mod.EXIT_UNAVAILABLE
    assert out["verdict"] == "WARN"
    assert out["reason"] == "review-model-unavailable"
    assert out["message"].startswith("Review model unavailable, deferring to human.")
    assert f"Failure: {failure}" in out["message"]
    assert len(runner.calls) == 1
    assert runner.calls[0]["model"] == mod.DEFAULT_SOL_MODEL
    log = _logs(tmp_path)[0]
    assert log["status"] == "unavailable"
    assert log["failure_class"] == failure
    assert log["findings"] == []


@pytest.mark.parametrize("text", ["not json", '{"findings": "x"}', "[]"])
def test_malformed_output_is_unavailable(tmp_path, critic_file, capsys, text):
    runner = FakeRunner(mod.RunResult(ok=True, text=text))

    code = _run(tmp_path, runner, "--critic-findings", str(critic_file))

    assert code == mod.EXIT_UNAVAILABLE
    assert json.loads(capsys.readouterr().out)["reason"] == "review-model-unavailable"
    assert _logs(tmp_path)[0]["failure_class"] == "invalid-output"


def test_codex_runner_reports_not_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.shutil, "which", lambda _name: None)

    result = mod.codex_runner("gpt-6.1-sol", "p", tmp_path / "s.json", tmp_path, 5)

    assert result.ok is False
    assert result.failure_class == "not-installed"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("The 'x' model is not supported when using Codex", "model-unsupported"),
        ("rate limit exceeded", "rate-limit"),
        ("HTTP 429", "rate-limit"),
        ("You hit your usage limit", "quota"),
        ("upstream connect error", "5xx"),
    ],
)
def test_failure_classification(message, expected):
    assert mod._classify_failure(message) == expected


def test_failure_message_reads_turn_failed_event():
    events = '{"type":"thread.started"}\n{"type":"turn.failed","error":{"message":"model gone"}}\n'

    assert mod._failure_message(events, "stderr noise") == "model gone"


# Model allowlist: Sol only


@pytest.mark.parametrize(
    "model",
    [
        "gemini-4-argon",
        "gemini-4-carbon",
        "grok-4.7",
        "xai/grok-4.7",
        "claude-opus-5-5",
        "claude-sonnet-5-5",
        "opus",
        "gpt-6-astra",
        "gpt-6.1-sol-mini",
        "gpt-6.1-sol; echo injected",
    ],
)
def test_rejects_non_sol_models_before_any_call(tmp_path, critic_file, model):
    runner = FakeRunner(_ok([]))

    code = _run(tmp_path, runner, "--critic-findings", str(critic_file), "--model", model)

    assert code == mod.EXIT_CONFIG
    assert runner.calls == []


def test_blank_model_id_is_refused():
    assert mod.validate_model("") is not None


@pytest.mark.parametrize("model", ["gpt-6.1-sol", "gpt-6-sol", "gpt-5.6-sol", "gpt-7-sol"])
def test_accepts_sol_models(model):
    assert mod.validate_model(model) is None


def test_env_model_override_is_also_guarded(tmp_path, critic_file, monkeypatch):
    monkeypatch.setenv("AI_AGENTS_SOL_MODEL", "gemini-4-argon")
    runner = FakeRunner(_ok([]))

    assert _run(tmp_path, runner, "--critic-findings", str(critic_file)) == mod.EXIT_CONFIG
    assert runner.calls == []


# Off switch


@pytest.mark.parametrize("value", ["off", "0", "false", "OFF"])
def test_env_off_switch_skips_and_logs(tmp_path, critic_file, monkeypatch, capsys, value):
    monkeypatch.setenv("AI_AGENTS_SOL_PASS", value)
    runner = FakeRunner(_ok([_finding()]))

    code = _run(tmp_path, runner, "--critic-findings", str(critic_file))

    assert code == mod.EXIT_OK
    assert runner.calls == []
    assert json.loads(capsys.readouterr().out)["verdict"] == "SKIPPED"
    assert _logs(tmp_path)[0]["status"] == "skipped"


def test_disable_flag_skips(tmp_path, critic_file):
    runner = FakeRunner(_ok([_finding()]))

    assert _run(tmp_path, runner, "--critic-findings", str(critic_file), "--disable") == mod.EXIT_OK
    assert runner.calls == []


# Conformance with the review model policy


def test_policy_reason_message_and_classes_match():
    policy = (PROJECT_ROOT / ".agents/governance/AI-REVIEW-MODEL-POLICY.md").read_text(
        encoding="utf-8"
    )

    assert f"`{mod.UNAVAILABLE_REASON}`" in policy
    assert "Review model unavailable, deferring to human." in policy
    for failure_class in ("timeout", "5xx", "rate-limit", "invalid-output", "quota"):
        assert f"`{failure_class}`" in policy


def test_schema_requires_file_line_repro():
    required = mod.FINDINGS_SCHEMA["properties"]["findings"]["items"]["required"]

    assert {"file", "line", "repro"} <= set(required)
