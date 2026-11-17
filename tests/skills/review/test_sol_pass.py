"""Tests for the cross-family Sol pass that runs after the fresh critic.

The reviewer call is injected, so no test reaches a model. Covers ordering
after the critic (including a stale critic file), the 2-round cap counted from
the run log, dropped findings in the log, the Sol-only log, the unavailable
WARN path with no fallback, and exit codes on bad input. The finding rules are
in ``test_sol_findings.py``; the model allowlist, off switch, bootstrap, and
policy conformance are in ``test_sol_pass_guards.py``.
"""

from __future__ import annotations

import json
import os
import shutil
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
    ".claude/skills/review/scripts/sol_pass.py", module_name="sol_pass_under_test"
)

CRITIC_TEXT = (
    "## Critical Findings\n1. `src/app/a.py:10` drops the error.\n\nVerdict: NEEDS_REVISION\n"
)
_needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git CLI not installed")


class FakeRunner:
    """Records every reviewer call and returns a canned result."""

    def __init__(self, result):
        self.result = result
        self.calls: list[dict] = []

    def __call__(self, model, prompt, schema_path, cwd, timeout):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.calls.append({"model": model, "prompt": prompt, "schema": schema, "cwd": cwd})
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


def _log_dir(tmp_path):
    return tmp_path / ".project-toolkit" / "metrics" / "sol-pass"


def _logs(tmp_path):
    return [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(_log_dir(tmp_path).glob("*.json"))
    ]


# Ordering after the critic


def test_refuses_to_run_without_critic_output(tmp_path, capsys):
    runner = FakeRunner(_ok([]))

    code = _run(tmp_path, runner, "--critic-findings", str(tmp_path / "missing.md"))

    assert code == mod.EXIT_CONFIG
    assert runner.calls == []
    assert "cannot read critic output" in capsys.readouterr().err
    assert not _log_dir(tmp_path).exists()


def test_refuses_to_run_with_empty_critic_output(tmp_path):
    empty = tmp_path / "critic.md"
    empty.write_text("  \n", encoding="utf-8")
    runner = FakeRunner(_ok([]))

    assert _run(tmp_path, runner, "--critic-findings", str(empty)) == mod.EXIT_CONFIG
    assert runner.calls == []


def test_non_utf8_critic_output_is_a_config_error_not_a_crash(tmp_path):
    binary = tmp_path / "critic.md"
    binary.write_bytes(b"\xff\xfe\x00bad")
    runner = FakeRunner(_ok([]))

    assert _run(tmp_path, runner, "--critic-findings", str(binary)) == mod.EXIT_CONFIG
    assert runner.calls == []


def test_critic_findings_flag_is_required():
    with pytest.raises(SystemExit) as exc:
        mod.build_parser().parse_args(["run"])
    assert exc.value.code == 2


def _git_repo(path: Path) -> None:
    path.mkdir()
    for args in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "init"]):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)


@_needs_git
def test_refuses_critic_output_older_than_head(tmp_path, critic_file, capsys):
    repo = tmp_path / "repo"
    _git_repo(repo)
    os.utime(critic_file, (1_000_000, 1_000_000))
    runner = FakeRunner(_ok([]))

    code = mod.main(
        [
            "run",
            "--repo",
            str(repo),
            "--log-base",
            str(tmp_path),
            "--critic-findings",
            str(critic_file),
        ],
        runner=runner,
    )

    assert code == mod.EXIT_CONFIG
    assert runner.calls == []
    assert "older than HEAD" in capsys.readouterr().err


@_needs_git
def test_accepts_critic_output_newer_than_head(tmp_path, critic_file):
    repo = tmp_path / "repo"
    _git_repo(repo)
    runner = FakeRunner(_ok([]))

    code = mod.main(
        [
            "run",
            "--repo",
            str(repo),
            "--log-base",
            str(tmp_path),
            "--critic-findings",
            str(critic_file),
        ],
        runner=runner,
    )

    assert code == mod.EXIT_OK
    assert len(runner.calls) == 1
    assert runner.calls[0]["cwd"] == repo.resolve()


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
        assert "resources/cross-family-pass.md" in line, rendered
    assert (PROJECT_ROOT / "src/claude/skills/review/resources/cross-family-pass.md").is_file()


# Two-round cap, counted from the run log


def test_third_run_for_same_pr_escalates_without_a_model_call(tmp_path, critic_file, capsys):
    runner = FakeRunner(_ok([]))
    first = _run(tmp_path, runner, "--critic-findings", str(critic_file), "--pr", "7")
    second = _run(tmp_path, runner, "--critic-findings", str(critic_file), "--pr", "7")
    capsys.readouterr()

    third = _run(tmp_path, runner, "--critic-findings", str(critic_file), "--pr", "7")

    assert (first, second, third) == (mod.EXIT_OK, mod.EXIT_OK, mod.EXIT_ESCALATE)
    assert len(runner.calls) == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "ESCALATE"
    assert [log["status"] for log in _logs(tmp_path)].count("escalated") == 1


def test_round_two_uses_frozen_contract_and_round_one_does_not(tmp_path, critic_file):
    runner = FakeRunner(_ok([]))

    _run(tmp_path, runner, "--critic-findings", str(critic_file), "--pr", "7")
    _run(tmp_path, runner, "--critic-findings", str(critic_file), "--pr", "7")

    assert "This is round 2" not in runner.calls[0]["prompt"]
    assert "This is round 2" in runner.calls[1]["prompt"]
    assert sorted(log["round"] for log in _logs(tmp_path)) == [1, 2]


def test_round_count_is_per_pr(tmp_path, critic_file):
    runner = FakeRunner(_ok([]))
    for _ in range(2):
        _run(tmp_path, runner, "--critic-findings", str(critic_file), "--pr", "7")

    code = _run(tmp_path, runner, "--critic-findings", str(critic_file), "--pr", "8")

    assert code == mod.EXIT_OK
    assert len(runner.calls) == 3


def test_unavailable_and_skipped_runs_do_not_use_a_round(tmp_path, critic_file, monkeypatch):
    _run(
        tmp_path,
        FakeRunner(mod.RunResult(ok=False, failure_class="timeout")),
        "--critic-findings",
        str(critic_file),
        "--pr",
        "7",
    )
    _run(
        tmp_path,
        FakeRunner(_ok([])),
        "--critic-findings",
        str(critic_file),
        "--pr",
        "7",
        "--disable",
    )
    runner = FakeRunner(_ok([]))

    _run(tmp_path, runner, "--critic-findings", str(critic_file), "--pr", "7")

    assert "This is round 2" not in runner.calls[0]["prompt"]


def test_max_rounds_is_two():
    assert mod.MAX_ROUNDS == 2


# Findings need file, line, and repro; style nits dropped


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
    assert (log["status"], log["pr"], log["key"], log["round"]) == ("ok", "123", "pr-123", 1)
    assert log["model"] == mod.DEFAULT_SOL_MODEL
    assert (log["counts"]["sol_only"], log["counts"]["overlap"]) == (1, 1)
    assert {f["file"]: f["sol_only"] for f in log["findings"]} == {
        "src/app/a.py": False,
        "src/app/b.py": True,
    }
    assert len(log["critic_sha256"]) == 64


def test_empty_result_passes_and_still_logs(tmp_path, critic_file, capsys):
    _run(tmp_path, FakeRunner(_ok([])), "--critic-findings", str(critic_file))

    assert json.loads(capsys.readouterr().out)["verdict"] == "PASS"
    assert _logs(tmp_path)[0]["counts"]["kept"] == 0


def test_each_run_gets_its_own_log_file(tmp_path, critic_file):
    runner = FakeRunner(_ok([]))

    _run(tmp_path, runner, "--critic-findings", str(critic_file), "--pr", "1")
    _run(tmp_path, runner, "--critic-findings", str(critic_file), "--pr", "2")

    assert len(_logs(tmp_path)) == 2


def test_artifact_root_override_redirects_log(tmp_path, critic_file, monkeypatch):
    durable = tmp_path / "durable"
    monkeypatch.setenv("AI_AGENTS_ARTIFACT_ROOT", str(durable))

    mod.main(
        ["run", "--repo", str(tmp_path), "--critic-findings", str(critic_file)],
        runner=FakeRunner(_ok([])),
    )

    assert len(list((durable / "metrics" / "sol-pass").glob("*.json"))) == 1


def test_log_write_failure_exits_2_after_printing_verdict(tmp_path, critic_file, capsys):
    blocker = tmp_path / ".project-toolkit"
    blocker.write_text("not a directory", encoding="utf-8")

    code = _run(tmp_path, FakeRunner(_ok([_finding()])), "--critic-findings", str(critic_file))

    captured = capsys.readouterr()
    assert code == mod.EXIT_CONFIG
    assert json.loads(captured.out)["verdict"] == "WARN"
    assert "run log not written" in captured.err


def test_log_write_failure_still_prints_unavailable_warn(tmp_path, critic_file, capsys):
    (tmp_path / ".project-toolkit").write_text("not a directory", encoding="utf-8")
    runner = FakeRunner(mod.RunResult(ok=False, failure_class="timeout"))

    code = _run(tmp_path, runner, "--critic-findings", str(critic_file))

    out = json.loads(capsys.readouterr().out)
    assert code == mod.EXIT_UNAVAILABLE
    assert out["reason"] == "review-model-unavailable"
    assert out["log"] is None


def test_summarize_totals_runs(tmp_path, critic_file, capsys):
    two = _ok([_finding(), _finding(file="src/app/a.py", line=10)])
    _run(tmp_path, FakeRunner(two), "--critic-findings", str(critic_file))
    _run(
        tmp_path,
        FakeRunner(mod.RunResult(ok=False, failure_class="timeout")),
        "--critic-findings",
        str(critic_file),
    )
    (_log_dir(tmp_path) / "broken.json").write_text("{", encoding="utf-8")
    capsys.readouterr()

    code = mod.main(["summarize", "--repo", str(tmp_path), "--log-base", str(tmp_path)])

    totals = json.loads(capsys.readouterr().out)
    assert code == mod.EXIT_OK
    assert (totals["runs"], totals["ok"], totals["unavailable"]) == (2, 1, 1)
    assert (totals["sol_only"], totals["overlap"], totals["unreadable"]) == (1, 1, 1)


# Unavailable path: WARN, no same-family fallback


@pytest.mark.parametrize(
    "failure",
    [
        "timeout",
        "rate-limit",
        "quota",
        "5xx",
        "auth",
        "unknown",
        "not-installed",
        "model-unsupported",
    ],
)
def test_unavailable_warns_and_makes_one_call(tmp_path, critic_file, capsys, failure):
    runner = FakeRunner(mod.RunResult(ok=False, failure_class=failure, detail="boom"))

    code = _run(tmp_path, runner, "--critic-findings", str(critic_file))

    out = json.loads(capsys.readouterr().out)
    assert code == mod.EXIT_UNAVAILABLE
    assert (out["verdict"], out["reason"]) == ("WARN", "review-model-unavailable")
    assert out["message"].startswith("Review model unavailable, deferring to human.")
    assert f"Failure: {failure}" in out["message"]
    assert [call["model"] for call in runner.calls] == [mod.DEFAULT_SOL_MODEL]
    log = _logs(tmp_path)[0]
    assert (log["status"], log["failure_class"], log["findings"]) == ("unavailable", failure, [])


@pytest.mark.parametrize("text", ["not json", '{"findings": "x"}', "[]"])
def test_malformed_output_is_unavailable(tmp_path, critic_file, capsys, text):
    code = _run(
        tmp_path,
        FakeRunner(mod.RunResult(ok=True, text=text)),
        "--critic-findings",
        str(critic_file),
    )

    assert code == mod.EXIT_UNAVAILABLE
    assert json.loads(capsys.readouterr().out)["reason"] == "review-model-unavailable"
    assert _logs(tmp_path)[0]["failure_class"] == "invalid-output"


def test_codex_runner_reports_not_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.shutil, "which", lambda _name: None)

    result = mod.codex_runner("gpt-6.1-sol", "p", tmp_path / "s.json", tmp_path, 5)

    assert (result.ok, result.failure_class) == (False, "not-installed")
