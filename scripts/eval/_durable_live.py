"""Live Claude producer of durable-outcome records (issue #5768, REQ-042).

`eval_durable_outcome.py` reads `OutcomeRecord` JSONL. This module produces
that JSONL from real `claude -p` runs over the #5425 routing corpus, so the
reduced-control comparison can run on identical tasks.

Why this is not the #6031 routing runner (`_routing_live.py`): that runner
plans only harnesses the #5423 capability matrix classifies, and the matrix
holds `codex` and `copilot`. Its arms A to F are defined over the Sol, Luna,
and Terra model families. A Claude run cannot be planned there without
forging an eligibility class, which #5424 forbids. This module reuses the
corpus loader, the deterministic grader, and the record parser, and adds no
routing arm, registry, or eligibility claim.

Control configurations. The instruction text a run loads is the variable.
`CONTROLS` names two sets of repo files; their text goes to the CLI through
`--append-system-prompt-file`. `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` turns off
CLAUDE.md auto-discovery, so no other instruction file loads. Level-1
evidence from 2026-09-30, claude 2.1.285: with
`--setting-sources "" --strict-mcp-config --disable-slash-commands`, the
question "do your loaded instructions mention Richard Murillo" answered YES
from `~/.claude/CLAUDE.md`, and answered NO once the variable was set.

What is measured, and what is a proxy:

* `first_pass`, `deterministic_acceptance`, `scope_violations`: the corpus
  grader (`_routing_grader.grade`), which runs the hidden checks. Measured.
* `followup_validation`: the agent's changed files are copied onto a fresh
  `initial/` state and graded again. It catches a result that depended on
  files outside the diff. A `post_integration_regression` scenario (the
  extension corpus, `load_extension_corpus`) adds the `integration` check:
  files that only exist after the change lands run against the agent's
  change. The routing corpus has no such case.
* `objective_satisfied`: equals the final grade, because the hidden checks
  encode the scenario's acceptance criteria. For an extension scenario it is
  the final grade and the integration check together.
* `residual_defects`: failing validation commands plus scope violations in
  the follow-up grade.
* `tool_failures`, cost, tokens, turns, wall time: read from the CLI stream.
* `unapproved_external_actions`: tool calls outside the allowed set that did
  not come back as errors. `Bash(python:*)` runs arbitrary Python, and this
  count neither observes nor blocks a network call made from inside it.
* `security_findings`: ruff `S` rules over the changed Python files.
* `unsupported_claims`: a regex over the final message that looks for a claim
  such as "tests pass", counted when the objective is not satisfied after the
  final grade and, for an extension scenario, the integration check. A proxy.
* `unresolved_uncertainty`: a hedge-phrase regex over the final message. A
  proxy, and the weakest evidence here.
* `rework_minutes`: measured. Wall minutes of correction rounds (round 1 and
  later), which exist only because the prior attempt failed its check. Agent
  rework only; `human_correction_minutes` stays 0.
* `review_findings`, `rollback_events`: 0 by construction. No reviewer ran and
  the driver has no rollback path, so an accepted change is never undone.
  These are not a measured absence of defects.

Observed effort is not exposed by the CLI stream (the init event carries
`per_turn_effort_active` only), so effort is a request, never a verified
value, and the run summary says so.

Stricter than canonical: `eval_routing_benchmark.py` fails closed on missing
credentials. This path has no credential variable to check, because it uses
the operator's stored login. It fails closed on an explicit `--use-stored-login`
flag instead, and never reads or copies the credential file.
"""

from __future__ import annotations

import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from _claude_stream import Invocation, StreamFacts, parse_stream
from _cli_transport import BASE_ENV_ALLOWLIST, minimal_process_env
from _durable_live_record import Session, build_record
from _outcome_record import OutcomeRecord
from _routing_grader import GradeResult, Verdict, grade, materialize
from _routing_scenario import Scenario

#: Instruction files each control loads. `current` is the repo's always-loaded
#: Claude Code surface (CLAUDE.md, AGENTS.md, .claude/CLAUDE.md, the always-on
#: rules). `reduced` keeps AGENTS.md only.
CONTROLS: Mapping[str, tuple[str, ...]] = {
    "current": (
        "CLAUDE.md",
        "AGENTS.md",
        ".claude/CLAUDE.md",
        ".claude/rules/builder-ethos.md",
        ".claude/rules/universal.md",
        ".claude/rules/voice.md",
    ),
    "reduced": ("AGENTS.md",),
}

ALLOWED_TOOLS = ("Read", "Edit", "Write", "Glob", "Grep", "Bash(python:*)", "Bash(python3:*)")
DEFAULT_TIMEOUT_SECONDS = 600.0
DEFAULT_MAX_TURNS = 25
DEFAULT_MAX_BUDGET_USD = 0.75
_BLOCKED_BILLING_ENV = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_FOUNDRY",
        "CLAUDE_CODE_USE_VERTEX",
    }
)

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class LiveRunError(RuntimeError):
    """A live run cannot proceed, or an invocation budget was exceeded."""


@dataclass(slots=True)
class InvocationBudget:
    """A hard cap on process launches. `spend` raises before the launch."""

    limit: int
    used: int = 0

    def spend(self) -> None:
        if self.used >= self.limit:
            raise LiveRunError(f"invocation cap {self.limit} reached; nothing further launched")
        self.used += 1


@dataclass(frozen=True, slots=True)
class TaskRun:
    """Everything one task under one control produced."""

    record: OutcomeRecord | None
    invocations: tuple[Invocation, ...]
    note: str = ""


@dataclass(frozen=True, slots=True)
class RunSettings:
    model: str
    effort: str
    max_turns: int = DEFAULT_MAX_TURNS
    retry_budget: int = 1
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    max_budget_usd: float = DEFAULT_MAX_BUDGET_USD


def control_text(repo_root: Path, control: str) -> str:
    """The concatenated instruction text for `control`. Raises on an unknown name."""
    if control not in CONTROLS:
        raise LiveRunError(f"unknown control {control!r}; expected one of {sorted(CONTROLS)}")
    parts: list[str] = []
    for relative in CONTROLS[control]:
        path = repo_root / relative
        if not path.is_file():
            raise LiveRunError(f"control {control!r} needs {relative}, not found in {repo_root}")
        parts.append(path.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def claude_argv(settings: RunSettings, control_file: Path, prompt: str) -> list[str]:
    """Shell-free argv for one run. Tools are an explicit allowlist."""
    return [
        "claude",
        "-p",
        prompt,
        "--model",
        settings.model,
        "--effort",
        settings.effort,
        "--max-turns",
        str(settings.max_turns),
        "--max-budget-usd",
        str(settings.max_budget_usd),
        "--permission-mode",
        "acceptEdits",
        "--allowedTools",
        *ALLOWED_TOOLS,
        "--setting-sources",
        "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--append-system-prompt-file",
        str(control_file),
        "--output-format",
        "stream-json",
        "--verbose",
    ]


def claude_env() -> dict[str, str]:
    """Allowlisted environment. Billing variables are removed so the stored login bills."""
    env: dict[str, str] = minimal_process_env(
        allow=BASE_ENV_ALLOWLIST,
        blocked=_BLOCKED_BILLING_ENV,
        overrides={"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1"},
    )
    return env


def run_claude(
    argv: Sequence[str],
    workdir: Path,
    *,
    runner: Runner = subprocess.run,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int | None, str, str]:
    """Launch one process. Returns (exit code or None, stdout, failure detail)."""
    try:
        done: Any = runner(
            list(argv),
            cwd=workdir,
            env=claude_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return None, "", "claude is not on PATH"
    except subprocess.TimeoutExpired:
        return None, "", f"timed out after {timeout}s"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "", f"process did not complete: {type(exc).__name__}"
    code = int(done.returncode)
    return code, str(done.stdout or ""), "" if code == 0 else f"exit code {code}"


def _invoke(
    scenario: Scenario,
    control: str,
    round_index: int,
    prompt: str,
    *,
    workdir: Path,
    control_file: Path,
    settings: RunSettings,
    budget: InvocationBudget,
    runner: Runner,
) -> Invocation:
    budget.spend()
    argv = claude_argv(settings, control_file, prompt)
    start = time.monotonic()
    code, stdout, detail = run_claude(argv, workdir, runner=runner, timeout=settings.timeout)
    wall = time.monotonic() - start
    facts = parse_stream(stdout)
    # `claude -p` exits 1 when the agent hits its turn or budget limit and still emits a
    # valid `result` event (observed 2026-09-30). Trust that event; any other nonzero exit,
    # timeout, or missing binary is a harness failure.
    if detail and not facts.limit_hit:
        facts = _with_failure(facts, detail)
    return Invocation(control, scenario.scenario_id, round_index, code, wall, facts)


def _with_failure(facts: StreamFacts, detail: str) -> StreamFacts:
    return replace(facts, failure=detail, completed=False)


def task_prompt(scenario: Scenario) -> str:
    return f"Complete this requirement in the working tree.\n\n{scenario.requirement}"


def correction_prompt(scenario: Scenario, result: GradeResult) -> str:
    """Retry prompt. Names scope problems only, so hidden check output never leaks."""
    lines = [
        "The deterministic acceptance check failed on your last attempt.",
        f"Requirement:\n{scenario.requirement}",
    ]
    if result.scope_violations:
        lines.append("Paths outside the allowed scope: " + ", ".join(result.scope_violations))
    if result.missing_expected:
        lines.append("Expected changes not found in: " + ", ".join(result.missing_expected))
    lines.append("Fix the working tree.")
    return "\n".join(lines)


def _harness_failed(invocation: Invocation) -> bool:
    return not invocation.facts.completed


def run_task(
    scenario: Scenario,
    control: str,
    control_file: Path,
    base_config: Mapping[str, object],
    settings: RunSettings,
    budget: InvocationBudget,
    *,
    repeat: int = 0,
    runner: Runner = subprocess.run,
) -> TaskRun:
    """Run one scenario under one control, with up to `retry_budget` correction rounds.

    A run whose process failed or never produced a `result` event returns
    `record=None`. It is a harness failure, not a task failure, and it is
    not counted against the control.
    """
    session = Session()
    with tempfile.TemporaryDirectory(prefix="durable-live-") as name:
        workdir = Path(name) / "work"
        materialize(scenario, workdir)
        prompt = task_prompt(scenario)
        for round_index in range(settings.retry_budget + 1):
            invocation = _invoke(
                scenario,
                control,
                round_index,
                prompt,
                workdir=workdir,
                control_file=control_file,
                settings=settings,
                budget=budget,
                runner=runner,
            )
            session.invocations.append(invocation)
            if _harness_failed(invocation):
                return TaskRun(None, tuple(session.invocations), invocation.facts.failure)
            session.grades.append(grade(scenario, workdir))
            if session.grades[-1].verdict is Verdict.PASS:
                break
            prompt = correction_prompt(scenario, session.grades[-1])
        record = build_record(scenario, base_config, repeat, session, workdir)
    return TaskRun(record, tuple(session.invocations))


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    """Records per control, every invocation summary, and tasks that hit a harness failure."""

    records: Mapping[str, tuple[OutcomeRecord, ...]]
    invocations: tuple[Invocation, ...]
    harness_failures: tuple[tuple[str, str, str], ...]


def max_invocations(tasks: int, controls: int, repeats: int, retry_budget: int) -> int:
    """Upper bound on process launches for a run."""
    return tasks * controls * repeats * (retry_budget + 1)


def run_experiment(
    scenarios: Sequence[Scenario],
    controls: Mapping[str, str],
    settings: RunSettings,
    budget: InvocationBudget,
    *,
    repeats: int = 1,
    first_repeat: int = 0,
    runner: Runner = subprocess.run,
) -> ExperimentResult:
    """Run every scenario under every control, `repeats` times. `controls` maps name to text.

    Repeat indices are `first_repeat` to `first_repeat + repeats - 1`, so a
    later chunk or a re-run of one failed cell keeps unique `task_id`/`repeat` pairs.
    """
    records: dict[str, list[OutcomeRecord]] = {name: [] for name in controls}
    invocations: list[Invocation] = []
    failures: list[tuple[str, str, str]] = []
    with tempfile.TemporaryDirectory(prefix="durable-controls-") as name:
        for control, text in controls.items():
            control_file = Path(name) / f"{control}.md"
            control_file.write_text(text, encoding="utf-8")
            base = {
                "harness": "claude",
                "context_bytes": 0,
                "retry_budget": settings.retry_budget,
                "reviewer": "none",
                "control": control,
            }
            for scenario in scenarios:
                for repeat in range(first_repeat, first_repeat + repeats):
                    run = run_task(
                        scenario,
                        control,
                        control_file,
                        base,
                        settings,
                        budget,
                        repeat=repeat,
                        runner=runner,
                    )
                    invocations.extend(run.invocations)
                    if run.record is None:
                        failures.append((control, scenario.scenario_id, run.note))
                    else:
                        records[control].append(run.record)
    return ExperimentResult(
        {key: tuple(value) for key, value in records.items()}, tuple(invocations), tuple(failures)
    )
