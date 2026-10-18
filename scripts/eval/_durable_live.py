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
  rework only.
* `human_correction_minutes`: `None` unless `--human-minutes FILE` supplies a
  timed row for the run's (control, task_id, repeat) cell (`_human_minutes.py`).
  An unattended run has no human, so the value is missing evidence and the
  record classifies `UNVERIFIED` until a human times a correction pass. The
  owner decision to keep or drop that clause is open on #5768.
* `review_findings`: measured when `RunSettings.reviewer` is set. A separate
  reviewer process reads an accepted change in a fresh copy and replies with a
  finding count (`_durable_review.py`). `None` when the arm is off, the run was
  not accepted, or the reply is not in the required shape. Never 0 by default.
* `rollback_events`: measured. A change that passed acceptance but fails the
  fresh-copy follow-up or the post-integration check is reverted to `initial/`
  and the revert is verified (`_durable_live_record.rollback_events`). Counted
  as 1. A revert that cannot be verified is `None`. A run needing no revert is 0.
  In this driver the value is derived from the follow-up result: it is 1 exactly
  when the run was accepted and the follow-up failed. The revert targets the
  run's temp workdir, which is deleted after the record is built, so no later
  step reads the reverted tree. It adds no evidence beyond `followup_validation`.
  The reviewer arm is read-only on both harnesses: `--tools Read,Glob,Grep` for
  claude and `-s read-only` for codex.

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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from _claude_stream import Invocation, StreamFacts, parse_stream
from _durable_codex import codex_argv, codex_env, parse_codex_run
from _durable_live_record import Session, build_record
from _durable_process import (  # noqa: F401  (re-exported for callers and tests)
    ALLOWED_TOOLS,
    DEFAULT_MAX_BUDGET_USD,
    DEFAULT_MAX_TURNS,
    DEFAULT_TIMEOUT_SECONDS,
    HARNESSES,
    Runner,
    RunSettings,
    claude_argv,
    claude_env,
    run_claude,
    run_process,
)
from _durable_review import (
    REVIEW_TOOLS,
    REVIEWER_CONTROL_SUFFIX,
    REVIEWER_INSTRUCTIONS,
    review_prompt,
    reviewer_identity,
)
from _human_minutes import HumanMinutes
from _human_minutes import lookup as human_lookup
from _outcome_record import OutcomeRecord
from _routing_grader import GradeResult, Verdict, apply_changes, grade, materialize
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
    read_only: bool = False,
) -> Invocation:
    """One launch. `read_only` is the reviewer arm: no edit or shell tool on either harness."""
    budget.spend()
    start = time.monotonic()
    if settings.harness == "codex":
        code, facts, detail = _run_codex(
            prompt, workdir, control_file, settings, runner, read_only=read_only
        )
    else:
        argv = (
            claude_argv(settings, control_file, prompt, REVIEW_TOOLS, restrict_tools=True)
            if read_only
            else claude_argv(settings, control_file, prompt)
        )
        code, stdout, detail = run_claude(argv, workdir, runner=runner, timeout=settings.timeout)
        facts = parse_stream(stdout)
    wall = time.monotonic() - start
    # `claude -p` exits 1 when the agent hits its turn or budget limit and still emits a
    # valid `result` event (observed 2026-09-30). Trust that event; any other nonzero exit,
    # timeout, or missing binary is a harness failure.
    if detail and not facts.limit_hit:
        facts = _with_failure(facts, detail)
    return Invocation(control, scenario.scenario_id, round_index, code, wall, facts)


def _run_codex(
    prompt: str,
    workdir: Path,
    control_file: Path,
    settings: RunSettings,
    runner: Runner,
    *,
    read_only: bool = False,
) -> tuple[int | None, StreamFacts, str]:
    """One `codex exec` run. `read_only` selects the read-only sandbox for the reviewer."""
    text = control_file.read_text(encoding="utf-8")
    sandbox = "read-only" if read_only else "workspace-write"
    argv = codex_argv(settings.model, settings.effort, text, prompt, sandbox)
    code, stdout, stderr, detail = run_process(
        argv, workdir, codex_env(), runner=runner, timeout=settings.timeout
    )
    return code, parse_codex_run(stdout, stderr, settings.cli_version), detail


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


def _run_review(
    scenario: Scenario,
    control: str,
    session: Session,
    workdir: Path,
    settings: RunSettings,
    budget: InvocationBudget,
    runner: Runner,
) -> Invocation:
    """Launch the independent reviewer on a fresh copy of the accepted change.

    The copy holds `initial/` plus the agent's changed files and nothing else:
    no control instruction file, no hidden check output, no producer message.
    The reviewer gets read-only tools and the same text for every control.
    """
    spec = settings.reviewer
    if spec is None:  # pragma: no cover - guarded by the caller
        raise LiveRunError("reviewer arm requested without a reviewer")
    reviewer_settings = replace(
        settings,
        harness=spec.harness,
        model=spec.model,
        effort=spec.effort,
        retry_budget=0,
    )
    with tempfile.TemporaryDirectory(prefix="durable-review-") as name:
        scratch = Path(name)
        copy = scratch / "work"
        apply_changes(scenario, workdir, session.grades[-1].changed_paths, copy)
        instructions = scratch / "reviewer.md"
        instructions.write_text(REVIEWER_INSTRUCTIONS, encoding="utf-8")
        return _invoke(
            scenario,
            f"{control}{REVIEWER_CONTROL_SUFFIX}",
            len(session.invocations),
            review_prompt(scenario.requirement, session.grades[-1].changed_paths),
            workdir=copy,
            control_file=instructions,
            settings=reviewer_settings,
            budget=budget,
            runner=runner,
            read_only=True,
        )


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
    human_minutes: HumanMinutes | None = None,
    runner: Runner = subprocess.run,
) -> TaskRun:
    """Run one scenario under one control, with up to `retry_budget` correction rounds.

    A run whose process failed or never produced a `result` event returns
    `record=None`. It is a harness failure, not a task failure, and it is
    not counted against the control. `human_minutes` supplies a timed human
    correction pass for this cell; without a row the value stays `None`.
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
        if settings.reviewer is not None and session.grades[-1].verdict is Verdict.PASS:
            session.review = _run_review(
                scenario, control, session, workdir, settings, budget, runner
            )
        record = build_record(
            scenario,
            base_config,
            repeat,
            session,
            workdir,
            reviewer=settings.reviewer,
            human_correction_minutes=human_lookup(
                human_minutes, control, scenario.scenario_id, repeat
            ),
        )
    launches = (*session.invocations, *((session.review,) if session.review else ()))
    return TaskRun(record, launches)


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    """Records per control, every invocation summary, and tasks that hit a harness failure."""

    records: Mapping[str, tuple[OutcomeRecord, ...]]
    invocations: tuple[Invocation, ...]
    harness_failures: tuple[tuple[str, str, str], ...]


def max_invocations(
    tasks: int, controls: int, repeats: int, retry_budget: int, *, reviewer: bool = False
) -> int:
    """Upper bound on process launches for a run. The reviewer arm adds one per task run."""
    return tasks * controls * repeats * (retry_budget + 1 + int(reviewer))


def run_experiment(
    scenarios: Sequence[Scenario],
    controls: Mapping[str, str],
    settings: RunSettings,
    budget: InvocationBudget,
    *,
    repeats: int = 1,
    first_repeat: int = 0,
    human_minutes: HumanMinutes | None = None,
    runner: Runner = subprocess.run,
) -> ExperimentResult:
    """Run every scenario under every control, `repeats` times. `controls` maps name to text.

    Repeat indices are `first_repeat` to `first_repeat + repeats - 1`, so a
    later chunk or a re-run of one failed cell keeps unique `task_id`/`repeat` pairs.
    """
    if settings.harness not in HARNESSES:
        raise LiveRunError(f"unknown harness {settings.harness!r}; expected one of {HARNESSES}")
    if settings.reviewer is not None and settings.reviewer.harness != settings.harness:
        raise LiveRunError(
            f"reviewer harness {settings.reviewer.harness!r} must match run harness "
            f"{settings.harness!r}; a cross-harness reviewer is not supported"
        )
    records: dict[str, list[OutcomeRecord]] = {name: [] for name in controls}
    invocations: list[Invocation] = []
    failures: list[tuple[str, str, str]] = []
    with tempfile.TemporaryDirectory(prefix="durable-controls-") as name:
        for control, text in controls.items():
            control_file = Path(name) / f"{control}.md"
            control_file.write_text(text, encoding="utf-8")
            base = {
                "harness": settings.harness,
                "context_bytes": 0,
                "retry_budget": settings.retry_budget,
                "reviewer": reviewer_identity(settings.reviewer),
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
                        human_minutes=human_minutes,
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
