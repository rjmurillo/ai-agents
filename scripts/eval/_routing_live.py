"""Gated live backend for the routing benchmark (issue #5424).

The live path is wired and stays closed unless two things hold:

1. the caller passed the explicit `--live` flag (the CLI decides, not this
   module), and
2. every harness in the plan has a credential in the environment.

`require_live_authorization` raises `LiveGateError` on any miss, before a
backend exists or a process starts. It never falls back to a dry run or to a
different harness. Credential names come from
`_runtime_harness.HARNESS_AUTH_ENV`, the same allowlist the runtime isolation
uses, minus the provider settings that are not secrets.

`LiveBackend` runs one harness CLI process per invocation, in a scratch copy
of the scenario. Each process is a new session, so a fresh-context boundary is
a runner fact, not a harness claim. The model and effort flags come from
`_capability_probes.TRUSTED_REQUEST_TEMPLATES`, the flag shapes the #5423 live
probes pinned. Sandbox and permission flags mirror what the repo already runs:
`-s workspace-write` for codex (`_harness_capability` matrix) and
`--allow-all-tools` for copilot (`eval_runtime_parity.build_argv`).

Codex invocations read backend evidence. With `RUST_LOG=tungstenite::protocol=trace`
the backend's own response frames name the model and reasoning effort it served,
and `_durable_codex.parse_codex_run` reads them with the token counts. A Codex
invocation is `EvidenceKind.BACKEND` when frames were read and `NONE` when none
were, so a request is never recorded as honored on its own say. Copilot reads no
frames: its observations stay `None` and `UNVERIFIED`, and Copilot is dropped
from eval support. The backend runs invocations one at a time, so a live run
proves no concurrency behavior and fan-out workers never overlap.

`real_home` (the CLI's `--real-home`) runs Codex on the operator's own
`CODEX_HOME` and login. Nothing is linked, copied, or read. `~/.codex/AGENTS.md`
and skills then load in every invocation, a confound the results record.

Plan handoff: after a planning invocation the backend hashes the plan file in the
scratch copy, and before the implementation invocation it hashes the file again.
That records the artifact present when the fresh process started. It is not proof
the implementer read it. The plan file is excluded from the scope diff.

The CLI builds a new backend for every planned row, so each arm starts from the
scenario's initial state.

A shared `InvocationBudget` caps paid invocations across rows. An invocation
past the cap raises `BudgetExhaustedError` before any process starts.
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any

from _capability_probes import TRUSTED_REQUEST_TEMPLATES
from _durable_codex import codex_env, parse_codex_run
from _harness_capability import EvidenceKind
from _routing_backend import IMPLEMENT_INVOCATION_ID, PLAN_INVOCATION_ID
from _routing_config import HANDOFF_ARTIFACT
from _routing_grader import GradeResult, grade, materialize
from _routing_result import SESSION_MARKER_FRESH, FailureKind, InvocationRequest, Observation
from _routing_scenario import Scenario
from _runtime_harness import HARNESS_AUTH_ENV, runtime_env

DEFAULT_TIMEOUT_SECONDS = 900.0
_NON_CREDENTIAL_ENV = frozenset(
    {
        "COPILOT_PROVIDER_TYPE",
        "COPILOT_PROVIDER_BASE_URL",
        "COPILOT_PROVIDER_MODEL_ID",
        "COPILOT_PROVIDER_WIRE_MODEL",
    }
)
_SANDBOX_LABEL = {"codex": "codex:-s workspace-write", "copilot": "copilot:--allow-all-tools"}

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class LiveGateError(RuntimeError):
    """A live run was requested without the credentials it needs."""


class BudgetExhaustedError(RuntimeError):
    """The shared invocation budget has no invocation left to spend."""


class InvocationBudget:
    """A hard cap on paid invocations, shared by every backend in one run."""

    def __init__(self, limit: int) -> None:
        if isinstance(limit, bool) or limit < 1:
            raise ValueError("invocation budget must be at least 1")
        self.limit = limit
        self.used = 0

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def take(self) -> None:
        if self.remaining < 1:
            raise BudgetExhaustedError(f"invocation budget of {self.limit} is spent")
        self.used += 1


def credential_names(harness: str) -> tuple[str, ...]:
    """Environment variables that count as a credential for `harness`."""
    if harness not in _SANDBOX_LABEL:
        raise LiveGateError(f"no live backend exists for harness {harness!r}")
    return tuple(sorted(HARNESS_AUTH_ENV[harness] - _NON_CREDENTIAL_ENV))


def require_live_authorization(
    harnesses: Sequence[str], env: Mapping[str, str], *, real_home: bool = False
) -> None:
    """Raise `LiveGateError` unless each harness may spend.

    A harness may spend with a non-empty credential in `env`, or, for Codex only,
    when the operator passed `--real-home` and so accepts the CLI's own login.
    """
    missing: list[str] = []
    for harness in harnesses:
        names = credential_names(harness)
        if real_home and harness == "codex":
            continue
        if not any(env.get(name, "").strip() for name in names):
            missing.append(f"{harness} (set one of {', '.join(names)})")
    if missing:
        raise LiveGateError("live run refused, no credential for: " + "; ".join(missing))


def change_surface(scenario: Scenario) -> str:
    """The legal change surface as prompt text, identical for every arm.

    Raises `ValueError` when the scenario declares no allowed path: a prompt
    that names no surface is the defect behind the RB-01 shared scope violation,
    so rendering one is refused instead of defaulting.
    """
    if not scenario.allowed_paths:
        raise ValueError(f"{scenario.scenario_id}: no allowed paths, cannot state a change surface")
    lines = [
        "Change surface: edit only these paths, and no other file, including tests "
        "and fixtures not listed:",
        *(f"- {path}" for path in scenario.allowed_paths),
    ]
    if scenario.forbidden_paths:
        lines.append("Never edit these paths:")
        lines.extend(f"- {path}" for path in scenario.forbidden_paths)
    return "\n".join(lines)


def role_prompt(request: InvocationRequest, scenario: Scenario) -> str:
    """The minimal role prompt. Prompt design for a comparison belongs to #5426.

    Worker prompts end with `change_surface`. The plan and review prompts write
    or edit no source file, so they carry no surface.
    """
    task = scenario.requirement
    if request.role == "reviewer":
        return (
            f"Review the working tree against this requirement and report defects only.\n\n{task}"
        )
    if request.phase_id == "plan":
        return f"Write implementation-plan.md for this requirement. Edit no source file.\n\n{task}"
    return f"Complete this requirement in the working tree.\n\n{task}\n\n{change_surface(scenario)}"


def live_argv(harness: str, model: str, effort: str, prompt: str) -> list[str]:
    """Shell-free argv for one live invocation."""
    model_flag = TRUSTED_REQUEST_TEMPLATES[(harness, "model_override")]
    effort_flag = TRUSTED_REQUEST_TEMPLATES[(harness, "effort_override")]
    request = [
        model_flag.flag,
        model_flag.render(model),
        effort_flag.flag,
        effort_flag.render(effort),
    ]
    if harness == "codex":
        head = [
            "codex",
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "-s",
            "workspace-write",
        ]
        return [*head, *request, "--", prompt]
    head = ["copilot", "--no-auto-update", "--no-custom-instructions", "--allow-all-tools"]
    return [*head, "--output-format", "json", *request, "-p", prompt]


@dataclass(frozen=True, slots=True)
class _BackendEvidence:
    model: str | None = None
    effort: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    failure: str = ""


class LiveBackend:
    """One scratch scenario copy per scenario id. Use as a context manager."""

    def __init__(
        self,
        harness: str,
        *,
        runner: Runner = subprocess.run,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        real_home: bool = False,
        budget: InvocationBudget | None = None,
    ) -> None:
        credential_names(harness)
        self._real_home = real_home and harness == "codex"
        self._budget = budget
        self._harness = harness
        self._runner = runner
        self._timeout = timeout
        self._scratch = tempfile.TemporaryDirectory(prefix="routing-live-")
        self._started = time.monotonic()
        self._workdirs: dict[str, Path] = {}

    def __enter__(self) -> LiveBackend:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._scratch.cleanup()

    def _workdir(self, scenario: Scenario) -> Path:
        if scenario.scenario_id not in self._workdirs:
            path = Path(self._scratch.name) / scenario.scenario_id / "work"
            materialize(scenario, path)
            self._workdirs[scenario.scenario_id] = path
        return self._workdirs[scenario.scenario_id]

    def _profile(self) -> Path:
        profile = Path(self._scratch.name) / "profile"
        profile.mkdir(exist_ok=True)
        return profile

    def _env(self) -> dict[str, str]:
        env: dict[str, str] = (
            codex_env() if self._real_home else runtime_env(self._profile(), self._harness)
        )
        return env

    def _run(self, argv: list[str], workdir: Path) -> tuple[int | None, str, str, str]:
        """Returns (exit code or None, failure detail, stdout, stderr)."""
        try:
            completed: Any = self._runner(
                argv,
                cwd=workdir,
                env=self._env(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return None, f"{argv[0]} is not on PATH", "", ""
        except subprocess.TimeoutExpired:
            return None, f"timed out after {self._timeout}s", "", ""
        except (OSError, subprocess.SubprocessError) as exc:
            return None, f"process did not complete: {type(exc).__name__}", "", ""
        code = int(completed.returncode)
        detail = "" if code == 0 else f"exit code {code}"
        return code, detail, str(completed.stdout or ""), str(completed.stderr or "")

    def _plan_sha(self, workdir: Path) -> str | None:
        """SHA-256 of the plan artifact on disk now, or `None` when there is none."""
        path = workdir / HANDOFF_ARTIFACT
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

    def invoke(self, request: InvocationRequest, scenario: Scenario) -> Observation:
        if self._budget is not None:
            self._budget.take()
        argv = live_argv(
            self._harness, request.model, request.effort, role_prompt(request, scenario)
        )
        workdir = self._workdir(scenario)
        consumed = (
            self._plan_sha(workdir) if request.invocation_id == IMPLEMENT_INVOCATION_ID else None
        )
        start = time.monotonic()
        code, detail, stdout, stderr = self._run(argv, workdir)
        produced = self._plan_sha(workdir) if request.invocation_id == PLAN_INVOCATION_ID else None
        evidence = self._backend_evidence(stdout, stderr)
        failure = detail or evidence.failure
        return Observation(
            session_id=request.session_id,
            start_offset_seconds=start - self._started,
            elapsed_seconds=time.monotonic() - start,
            observed_model=evidence.model,
            observed_effort=evidence.effort,
            evidence=EvidenceKind.BACKEND if evidence.model else EvidenceKind.NONE,
            input_tokens=evidence.input_tokens,
            output_tokens=evidence.output_tokens,
            tool_sandbox=_SANDBOX_LABEL[self._harness],
            context_markers=(SESSION_MARKER_FRESH,) if request.fresh_context else (),
            failure=FailureKind.HARNESS if failure else None,
            failure_detail=failure,
            artifact_sha=produced,
            consumed_artifact_sha=consumed,
        )

    def _backend_evidence(self, stdout: str, stderr: str) -> _BackendEvidence:
        """What the backend said it served. Codex only: other harnesses read none."""
        if self._harness != "codex" or not stdout:
            return _BackendEvidence()
        facts = parse_codex_run(stdout, stderr)
        return _BackendEvidence(
            model="+".join(facts.models) or None,
            effort="+".join(facts.efforts) or None,
            input_tokens=facts.input_tokens if facts.completed else None,
            output_tokens=facts.output_tokens if facts.completed else None,
            failure=facts.failure,
        )

    def grade(self, scenario: Scenario, round_index: int) -> GradeResult:
        return grade(scenario, self._workdir(scenario), ignore=frozenset({HANDOFF_ARTIFACT}))
