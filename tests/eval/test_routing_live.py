"""Tests for the gated live backend (issue #5424). No real harness is started.

The backend receives a fake process runner, so these tests prove the gate, the
argv shape, the environment allowlist, and failure classification. They do not
prove that a real codex or copilot process behaves this way.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.eval._routing_runner_test_support import (
    BOUNDED,
    backend_mod,
    config_dict,
    dag_mod,
    live_mod,
    matched_records,
    parse,
    plan_mod,
    result_mod,
    run_mod,
    scenarios,
)

ALL_CREDENTIALS = (
    "CODEX_API_KEY",
    "CODEX_ACCESS_TOKEN",
    "COPILOT_GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "COPILOT_PROVIDER_API_KEY",
    "COPILOT_PROVIDER_BEARER_TOKEN",
)


@pytest.fixture(autouse=True)
def _no_ambient_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ALL_CREDENTIALS:
        monkeypatch.delenv(name, raising=False)


def _scenario() -> Any:
    return next(s for s in scenarios() if s.scenario_id == BOUNDED)


FRAME = "2026-10-04T00:00:00.000000Z TRACE tungstenite::protocol: Received message "


def _argv_value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def _codex_streams(argv: list[str], *, frames: bool, completed: bool) -> tuple[str, str]:
    """Realistic codex stdout and stderr for one run: the model and effort come from argv."""
    model = _argv_value(argv, "--model")
    effort = [a for a in argv if a.startswith("model_reasoning_effort=")][0].split("=")[1]
    events: list[dict[str, Any]] = [{"type": "thread.started"}, {"type": "turn.started"}]
    if completed:
        usage = {"input_tokens": 1000, "cached_input_tokens": 400, "output_tokens": 50}
        events.append({"type": "turn.completed", "usage": usage})
    stdout = "".join(json.dumps(event) + "\n" for event in events)
    body: dict[str, Any] = {"id": "r1", "model": model, "reasoning": {"effort": effort}}
    stderr = "".join(
        FRAME + json.dumps({"type": kind, "response": body}) + "\n"
        for kind in ("response.created", "response.completed")
    )
    return stdout, stderr if frames else ""


class FakeRunner:
    """Records each call and optionally leaves the known-good solution in `cwd`."""

    def __init__(
        self,
        returncode: int = 0,
        *,
        apply_solution: bool = False,
        error: Exception | None = None,
        frames: bool = True,
        completed: bool = True,
    ) -> None:
        self.returncode = returncode
        self.apply_solution = apply_solution
        self.error = error
        self.frames = frames
        self.completed = completed
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append({"argv": argv, **kwargs, "cwd_exists": Path(kwargs["cwd"]).is_dir()})
        if self.error:
            raise self.error
        if self.apply_solution:
            source = _scenario().fixture_dir("known_good")
            for path in source.rglob("*.fixture"):
                target = Path(kwargs["cwd"]) / path.relative_to(source).as_posix().removesuffix(
                    ".fixture"
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        stdout, stderr = _codex_streams(argv, frames=self.frames, completed=self.completed)
        return subprocess.CompletedProcess(argv, self.returncode, stdout, stderr)


def test_credential_names_exclude_provider_settings_that_are_not_secrets() -> None:
    assert live_mod.credential_names("codex") == ("CODEX_ACCESS_TOKEN", "CODEX_API_KEY")
    copilot = live_mod.credential_names("copilot")
    assert "GH_TOKEN" in copilot and "COPILOT_PROVIDER_API_KEY" in copilot
    assert "COPILOT_PROVIDER_TYPE" not in copilot and "COPILOT_PROVIDER_BASE_URL" not in copilot


def test_a_harness_with_no_live_backend_is_refused() -> None:
    with pytest.raises(live_mod.LiveGateError, match="no live backend"):
        live_mod.credential_names("claude")
    with pytest.raises(live_mod.LiveGateError):
        live_mod.LiveBackend("gemini")


def test_live_is_refused_without_a_credential_for_every_harness() -> None:
    with pytest.raises(live_mod.LiveGateError, match="codex.*CODEX_API_KEY") as excinfo:
        live_mod.require_live_authorization(["codex", "copilot"], {"GH_TOKEN": "t"})

    assert "copilot" not in str(excinfo.value)


@pytest.mark.parametrize("value", ["", "   "])
def test_an_empty_credential_does_not_count(value: str) -> None:
    with pytest.raises(live_mod.LiveGateError):
        live_mod.require_live_authorization(["codex"], {"CODEX_API_KEY": value})


def test_a_provider_setting_is_not_a_credential() -> None:
    env = {"COPILOT_PROVIDER_TYPE": "openai", "COPILOT_PROVIDER_BASE_URL": "https://x"}

    with pytest.raises(live_mod.LiveGateError, match="copilot"):
        live_mod.require_live_authorization(["copilot"], env)


def test_one_credential_per_harness_opens_the_gate() -> None:
    env = {"CODEX_ACCESS_TOKEN": "a", "COPILOT_GITHUB_TOKEN": "b"}

    live_mod.require_live_authorization(["codex", "copilot"], env)


def test_live_argv_carries_model_and_effort_with_the_pinned_flag_shapes() -> None:
    codex = live_mod.live_argv("codex", "gpt-5.6-luna", "high", "PROMPT")
    copilot = live_mod.live_argv("copilot", "gpt-5.6-luna", "high", "PROMPT")

    assert codex[:2] == ["codex", "exec"] and codex[-2:] == ["--", "PROMPT"]
    assert ["--model", "gpt-5.6-luna", "-c", "model_reasoning_effort=high"] == codex[-6:-2]
    assert "--ignore-user-config" in codex and "--ignore-rules" in codex
    assert ["-s", "workspace-write"] == codex[codex.index("-s") : codex.index("-s") + 2]
    assert copilot[0] == "copilot" and copilot[-2:] == ["-p", "PROMPT"]
    assert copilot[copilot.index("--model") : copilot.index("--model") + 4] == [
        "--model", "gpt-5.6-luna", "--reasoning-effort", "high",
    ]  # fmt: skip


def test_role_prompts_differ_by_role_and_carry_the_same_requirement() -> None:
    scenario = _scenario()
    config = parse(config_dict())
    requests = {
        r.invocation_id: r
        for r in dag_mod.build_requests(config.strategy_for("B", "codex"), scenario)
    }
    prompts = {role: live_mod.role_prompt(req, scenario) for role, req in requests.items()}

    assert len(set(prompts.values())) == 3
    assert all(scenario.requirement in prompt for prompt in prompts.values())
    assert "implementation-plan.md" in prompts["orchestrator-plan"]
    assert "report defects only" in prompts["reviewer-review"]


def test_backend_runs_in_a_scratch_copy_with_an_allowlisted_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "credential")
    monkeypatch.setenv("UNRELATED_SECRET", "must-not-pass")
    runner = FakeRunner()
    request = dag_mod.build_requests(parse(config_dict()).strategy_for("E", "codex"), _scenario())[
        0
    ]

    with live_mod.LiveBackend("codex", runner=runner, timeout=7.0) as backend:
        observation = backend.invoke(request, _scenario())

    call = runner.calls[0]
    assert call["cwd_exists"] and call["timeout"] == 7.0 and call["check"] is False
    assert call["stdin"] == subprocess.DEVNULL and call["encoding"] == "utf-8"
    assert call["env"]["CODEX_API_KEY"] == "credential"
    assert "UNRELATED_SECRET" not in call["env"]
    assert "shell" not in call
    assert observation.observed_model == request.model
    assert observation.observed_effort == request.effort
    assert observation.evidence is result_mod.EvidenceKind.BACKEND
    assert (observation.input_tokens, observation.output_tokens) == (600, 50)
    assert observation.failure is None


def test_the_scratch_workspace_is_created_fresh_and_removed_on_exit() -> None:
    runner = FakeRunner()
    scenario = _scenario()
    request = dag_mod.build_requests(parse(config_dict()).strategy_for("E", "codex"), scenario)[0]

    with live_mod.LiveBackend("codex", runner=runner) as backend:
        backend.invoke(request, scenario)
        workdir = Path(runner.calls[0]["cwd"])
        assert (workdir / "slugger" / "core.py").is_file()
        assert not list(workdir.rglob("check_hidden_*"))
    assert not workdir.exists()


@pytest.mark.parametrize(
    ("runner", "detail"),
    [
        (FakeRunner(returncode=2), "exit code 2"),
        (FakeRunner(error=FileNotFoundError("codex")), "not on PATH"),
        (FakeRunner(error=subprocess.TimeoutExpired("codex", 1)), "timed out"),
        (FakeRunner(error=PermissionError("denied")), "PermissionError"),
    ],
)
def test_a_process_failure_is_a_harness_failure(runner: FakeRunner, detail: str) -> None:
    scenario = _scenario()
    request = dag_mod.build_requests(parse(config_dict()).strategy_for("E", "codex"), scenario)[0]

    with live_mod.LiveBackend("codex", runner=runner) as backend:
        observation = backend.invoke(request, scenario)

    assert observation.failure is result_mod.FailureKind.HARNESS
    assert detail in observation.failure_detail


def test_grading_reads_the_repository_state_the_process_left() -> None:
    scenario = _scenario()
    request = dag_mod.build_requests(parse(config_dict()).strategy_for("E", "codex"), scenario)[0]

    with live_mod.LiveBackend("codex", runner=FakeRunner(apply_solution=True)) as solved:
        solved.invoke(request, scenario)
        good = solved.grade(scenario, 0)
    with live_mod.LiveBackend("codex", runner=FakeRunner()) as untouched:
        untouched.invoke(request, scenario)
        bad = untouched.grade(scenario, 0)

    assert good.verdict.value == "PASS" and bad.verdict.value == "FAIL"


def test_a_live_run_records_no_backend_evidence_when_no_frames_arrive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "credential")
    config = parse(config_dict())
    plan = plan_mod.build_plan(config, matched_records(), scenarios())
    row = next(r for r in plan.rows if (r.arm, r.harness, r.scenario_id) == ("E", "codex", BOUNDED))

    runner = FakeRunner(apply_solution=True, frames=False)
    with live_mod.LiveBackend("codex", runner=runner) as backend:
        result = run_mod.run_planned(row, config.strategy_for("E", "codex"), _scenario(), backend)

    assert result.status is result_mod.RunStatus.ACCEPTED
    assert "unverified_model:agent-implement" in result.notes
    assert result.total_input_tokens == 600 and result.total_cost_usd is None
    assert result.tool_sandbox == ("codex:-s workspace-write",)


def test_live_backend_is_not_the_scripted_fake() -> None:
    assert not issubclass(live_mod.LiveBackend, backend_mod.ScriptedBackend)


def _requests(arm: str) -> dict[str, Any]:
    strategy = parse(config_dict()).strategy_for(arm, "codex")
    return {r.invocation_id: r for r in dag_mod.build_requests(strategy, _scenario())}


class PlanWriter(FakeRunner):
    """Writes a plan file when it runs the planning prompt."""

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "implementation-plan.md" in argv[-1]:
            (Path(kwargs["cwd"]) / "implementation-plan.md").write_text("the plan", "utf-8")
        return super().__call__(argv, **kwargs)


def test_the_plan_file_is_hashed_and_does_not_count_as_a_scope_violation() -> None:
    scenario = _scenario()
    requests = _requests("F")

    with live_mod.LiveBackend("codex", runner=PlanWriter(apply_solution=True)) as backend:
        plan = backend.invoke(requests["planner-plan"], scenario)
        implement = backend.invoke(requests["implementer-implement"], scenario)
        graded = backend.grade(scenario, 0)

    assert plan.artifact_sha and plan.artifact_sha == implement.consumed_artifact_sha
    assert graded.verdict.value == "PASS" and "implementation-plan.md" not in graded.changed_paths


def test_a_live_plan_handoff_passes_and_a_missing_plan_is_reported() -> None:
    config = parse(config_dict())
    plan = plan_mod.build_plan(config, matched_records(), scenarios())
    row = next(r for r in plan.rows if (r.arm, r.harness, r.scenario_id) == ("F", "codex", BOUNDED))
    strategy = config.strategy_for("F", "codex")

    with live_mod.LiveBackend("codex", runner=PlanWriter(apply_solution=True)) as backend:
        written = run_mod.run_planned(row, strategy, _scenario(), backend)
    with live_mod.LiveBackend("codex", runner=FakeRunner(apply_solution=True)) as backend:
        absent = run_mod.run_planned(row, strategy, _scenario(), backend)

    assert written.violations == ()
    assert absent.violations == ("handoff_missing:planner-plan",)


def test_a_file_that_is_not_the_plan_still_counts_as_a_change() -> None:
    scenario = _scenario()
    request = _requests("E")["agent-implement"]

    with live_mod.LiveBackend("codex", runner=FakeRunner(apply_solution=True)) as backend:
        backend.invoke(request, scenario)
        (Path(backend._workdirs[scenario.scenario_id]) / "notes.md").write_text("x", "utf-8")
        graded = backend.grade(scenario, 0)

    assert "notes.md" in graded.scope_violations


# --- Backend evidence, budget, and real home (issue #5424 live) -------------------


def test_a_run_with_no_completed_turn_is_a_harness_failure_with_no_tokens() -> None:
    scenario = _scenario()
    request = _requests("E")["agent-implement"]

    with live_mod.LiveBackend("codex", runner=FakeRunner(completed=False)) as backend:
        observation = backend.invoke(request, scenario)

    assert observation.failure is result_mod.FailureKind.HARNESS
    assert observation.input_tokens is None and observation.output_tokens is None


def test_a_served_model_that_differs_from_the_request_is_recorded_as_served() -> None:
    scenario = _scenario()
    request = _requests("E")["agent-implement"]

    class Wrong(FakeRunner):
        def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            swapped = [a.replace(request.model, "gpt-6-luna") for a in argv]
            return super().__call__(swapped, **kwargs)

    with live_mod.LiveBackend("codex", runner=Wrong()) as backend:
        observation = backend.invoke(request, scenario)

    assert observation.observed_model == "gpt-6-luna" != request.model


def test_the_budget_stops_the_invocation_before_any_process_starts() -> None:
    scenario = _scenario()
    request = _requests("E")["agent-implement"]
    runner = FakeRunner()
    budget = live_mod.InvocationBudget(1)

    with live_mod.LiveBackend("codex", runner=runner, budget=budget) as backend:
        backend.invoke(request, scenario)
        with pytest.raises(live_mod.BudgetExhaustedError):
            backend.invoke(request, scenario)

    assert len(runner.calls) == 1 and budget.used == 1 and budget.remaining == 0


@pytest.mark.parametrize("limit", [0, -3, True])
def test_a_budget_below_one_is_refused(limit: int) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        live_mod.InvocationBudget(limit)


def test_real_home_opens_the_gate_for_codex_only() -> None:
    live_mod.require_live_authorization(["codex"], {}, real_home=True)
    with pytest.raises(live_mod.LiveGateError, match="copilot"):
        live_mod.require_live_authorization(["codex", "copilot"], {}, real_home=True)
    with pytest.raises(live_mod.LiveGateError, match="codex"):
        live_mod.require_live_authorization(["codex"], {}, real_home=False)


def test_real_home_passes_codex_home_and_blocks_metered_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_HOME", "/operator/codex-home")
    monkeypatch.setenv("OPENAI_API_KEY", "metered")
    runner = FakeRunner()
    request = _requests("E")["agent-implement"]

    with live_mod.LiveBackend("codex", runner=runner, real_home=True) as backend:
        backend.invoke(request, _scenario())

    env = runner.calls[0]["env"]
    assert env["CODEX_HOME"] == "/operator/codex-home"
    assert "OPENAI_API_KEY" not in env
    assert env["RUST_LOG"].startswith("tungstenite::protocol")


def test_real_home_makes_no_credential_link_in_the_scratch_tree() -> None:
    runner = FakeRunner()
    request = _requests("E")["agent-implement"]

    with live_mod.LiveBackend("codex", runner=runner, real_home=True) as backend:
        backend.invoke(request, _scenario())
        root = Path(runner.calls[0]["cwd"]).parent.parent
        assert [p for p in root.rglob("*") if p.is_symlink()] == []
