"""Guard tests for the cross-family Sol pass.

Only a GPT Sol model is accepted, the pass can be switched off, the bootstrap
survives a foreign plugin root, and the WARN path matches the review model
policy.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/review/scripts/sol_pass.py", module_name="sol_pass_guards_under_test"
)


class FakeRunner:
    """Records every reviewer call and returns a canned result."""

    def __init__(self, result):
        self.result = result
        self.calls: list[str] = []

    def __call__(self, model, prompt, schema_path, cwd, timeout):
        self.calls.append(model)
        return self.result


def _ok(findings):
    return mod.RunResult(ok=True, text=json.dumps({"findings": findings}))


def _finding():
    return {
        "file": "src/app/b.py",
        "line": 5,
        "repro": "pytest t.py fails",
        "summary": "s",
        "severity": "high",
        "category": "correctness",
    }


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("AI_AGENTS_ARTIFACT_ROOT", "AI_AGENTS_SOL_PASS", "AI_AGENTS_SOL_MODEL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def critic_file(tmp_path):
    path = tmp_path / "critic.md"
    path.write_text("1. `src/app/a.py:10` drops the error.\n", encoding="utf-8")
    return path


def _run(tmp_path, runner, *extra):
    return mod.main(
        ["run", "--repo", str(tmp_path), "--log-base", str(tmp_path), *extra], runner=runner
    )


def _logs(tmp_path):
    log_dir = tmp_path / ".project-toolkit" / "metrics" / "sol-pass"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(log_dir.glob("*.json"))]


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


def test_bootstrap_ignores_plugin_root_without_paths_module(tmp_path):
    script = PROJECT_ROOT / "src/claude/skills/review/scripts/sol_pass.py"
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(tmp_path), "COPILOT_PLUGIN_ROOT": str(tmp_path)}

    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert proc.returncode == 0, proc.stderr


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
