"""Guard tests for sol-loop.

Only a GPT Sol model id is accepted, the pass can be switched off, the
bootstrap survives a foreign plugin root, the WARN path matches the review
model policy, the orchestrator runs sol-loop after the fresh critic, and no CI
workflow calls it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/sol-loop/scripts/sol_loop.py", module_name="sol_loop_guards_under_test"
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("AI_AGENTS_ARTIFACT_ROOT", "AI_AGENTS_SOL_PASS"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def critic_file(tmp_path):
    path = tmp_path / "critic.md"
    path.write_text("1. `src/app/a.py:10` drops the error.\n", encoding="utf-8")
    return path


def _gate(tmp_path, critic, model="gpt-6.1-sol"):
    argv = ["gate", "--route", "t3", "--repo", str(tmp_path), "--log-base", str(tmp_path)]
    argv += ["--critic-findings", str(critic), "--model", model, "--author-family", "anthropic"]
    return mod.main(argv)


def _logs(tmp_path):
    log_dir = tmp_path / ".project-toolkit" / "metrics" / "sol-loop"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(log_dir.glob("*.json"))]


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
        "gpt-6-1-sol-medium",
        "fusion-gpt-6-1-sol-high-sidekick-swe-2-medium",
        "fusion-gpt-6-sol-high-sidekick-gpt-5-6-luna-high",
        "gpt-6.1-sol; echo injected",
        "",
    ],
)
def test_rejects_non_sol_models_before_anything_runs(tmp_path, critic_file, model):
    code = _gate(tmp_path, critic_file, model=model)

    assert code == mod.EXIT_CONFIG
    assert _logs(tmp_path) == []


@pytest.mark.parametrize("model", ["gpt-6.1-sol", "gpt-6-sol", "gpt-5.6-sol", "gpt-7-sol"])
def test_accepts_sol_models(model):
    assert mod.validate_model(model) is None


@pytest.mark.parametrize("command", ["record", "unavailable"])
def test_record_and_unavailable_also_guard_the_model(tmp_path, critic_file, command):
    extra = ["--reply", str(critic_file)] if command == "record" else ["--failure-class", "timeout"]
    argv = [
        command,
        "--repo",
        str(tmp_path),
        "--log-base",
        str(tmp_path),
        "--critic-findings",
        str(critic_file),
    ]
    argv += ["--model", "claude-opus-5-5", "--author-family", "anthropic", *extra]

    assert mod.main(argv) == mod.EXIT_CONFIG
    assert _logs(tmp_path) == []


# Off switch


@pytest.mark.parametrize("value", ["off", "0", "false", "OFF"])
def test_env_off_switch_skips_and_logs(tmp_path, critic_file, monkeypatch, capsys, value):
    monkeypatch.setenv("AI_AGENTS_SOL_PASS", value)

    code = _gate(tmp_path, critic_file)

    assert code == mod.EXIT_OK
    assert json.loads(capsys.readouterr().out)["verdict"] == "SKIPPED"
    assert _logs(tmp_path)[0]["status"] == "skipped"


# Bootstrap


def test_bootstrap_ignores_plugin_root_without_paths_module(tmp_path):
    script = PROJECT_ROOT / "src/claude/skills/sol-loop/scripts/sol_loop.py"
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


# Conformance with the review model policy


def test_policy_reason_message_and_classes_match():
    policy = (PROJECT_ROOT / ".agents/governance/AI-REVIEW-MODEL-POLICY.md").read_text(
        encoding="utf-8"
    )

    assert f"`{mod.UNAVAILABLE_REASON}`" in policy
    assert "Review model unavailable, deferring to human." in policy
    for failure_class in ("timeout", "5xx", "rate-limit", "invalid-output", "quota"):
        assert f"`{failure_class}`" in policy
        assert failure_class in mod.FAILURE_CLASSES


# Orchestrator route: sol-loop after the fresh critic


@pytest.mark.parametrize(
    "rendered",
    ["src/claude/agents/orchestrator.md", "src/copilot-cli/agents/orchestrator.agent.md"],
)
def test_orchestrator_routes_sol_loop_after_readiness_critic(rendered):
    text = (PROJECT_ROOT / rendered).read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if "critic (readiness)" in ln)

    assert line.index("critic (readiness)") < line.index("sol-loop")
    assert "GPT model wrote the change" in line


# Agent side only


def _workflow_commands(path: Path) -> list[str]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    jobs = doc.get("jobs") or {}
    return [
        str(step.get("run", "")) + " " + json.dumps(step.get("with", {}))
        for job in jobs.values()
        if isinstance(job, dict)
        for step in job.get("steps") or []
        if isinstance(step, dict)
    ]


def test_no_workflow_runs_sol_loop():
    workflows = sorted((PROJECT_ROOT / ".github" / "workflows").glob("*.yml"))

    hits = [
        w.name
        for w in workflows
        for cmd in _workflow_commands(w)
        if "sol_loop" in cmd or "sol-loop" in cmd
    ]

    assert workflows
    assert hits == []
