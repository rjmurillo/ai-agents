"""Recompute an ADR-127 eval results file and check the decision 7 floors.

This module is pure: it reads parsed JSON and returns findings. It does not
call git or a model. ``check_skill_rewrite_evidence.py`` loads the inputs from
the repository and calls :func:`verify_results`.

The verdict is recomputed from the per-run labels in ``detail``, never read
from ``gate.verdict``. Each run passes when it was scored and its ``verdict``
equals the scenario's ``expected_verdict`` in the committed scenario file.

Shared with the runner (``scripts/eval/eval-prompt-change.py``, loaded by
path): ``acceptance_gate``, ``is_base_unstable``, ``required_passes``, and
``_is_suspected_regression``. Rebuilt here, because the runner computes them
inside its model loop: the per-scenario aggregate of ``run_scenario_multi``
(:func:`_aggregate`), the pooling of ``_resample_base`` (:func:`_pool`), and
the stable-pair scores of ``run_comparison`` (in :func:`verify_results`).
``tests/validation/test_skill_rewrite_evidence.py::TestRunnerConformance``
feeds the same runs through both and fails when they differ.

Limit, stated as ADR-127 decision 9 states it: this proves the file is
consistent with itself and with the repository. It cannot prove a model
produced the labels. A hand-built file with matching hashes passes. That
residual stays with the reviewer.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

_EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"
_RUNNER_PATH = _EVAL_DIR / "eval-prompt-change.py"

MIN_SCENARIOS = 8
MIN_CARRIED = 6

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
IDENTITY_KEYS = ("prompt_surface_sha256", "scenarios_sha256", "base_commit", "model")


def load_runner() -> ModuleType:
    """Import the eval runner by path; its siblings resolve from its directory."""
    added = str(_EVAL_DIR) not in sys.path
    if added:
        sys.path.insert(0, str(_EVAL_DIR))
    try:
        spec = importlib.util.spec_from_file_location("eval_prompt_change", _RUNNER_PATH)
        if spec is None or spec.loader is None:  # pragma: no cover - the path is a constant
            raise ImportError(f"cannot load {_RUNNER_PATH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if added and str(_EVAL_DIR) in sys.path:
            sys.path.remove(str(_EVAL_DIR))


@dataclass(frozen=True)
class Expected:
    """What the repository says a results file must match."""

    prompt_path: str
    prompt_surface_sha256: str
    scenarios_path: str
    scenarios_sha256: str
    scenarios: tuple[dict[str, Any], ...]


def identity_findings(results: dict[str, Any]) -> list[str]:
    """Findings for a missing or malformed identity block (a missing signal)."""
    identity = results.get("identity")
    if not isinstance(identity, dict):
        return ["identity block is missing; re-run the eval with the current runner"]
    problems = []
    for key in IDENTITY_KEYS:
        value = identity.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"identity.{key} is missing or empty")
            continue
        if key.endswith("sha256") and not _SHA256.match(value):
            problems.append(f"identity.{key} is not a 64-hex sha256: {value!r}")
        if key == "base_commit" and not _SHA1.match(value):
            problems.append(f"identity.base_commit is not a 40-hex commit: {value!r}")
    if identity.get("model") != results.get("model"):
        problems.append("identity.model differs from the top-level model")
    return problems


def _match_findings(identity: dict[str, Any], expected: Expected) -> list[str]:
    problems = []
    pairs = (
        ("prompt_path", expected.prompt_path),
        ("prompt_surface_sha256", expected.prompt_surface_sha256),
        ("scenarios_path", expected.scenarios_path),
        ("scenarios_sha256", expected.scenarios_sha256),
    )
    for key, want in pairs:
        got = identity.get(key)
        if got != want:
            problems.append(f"identity.{key} is {got!r}; the repository has {want!r}")
    return problems


def _run_passed(run: object, expected_verdict: str) -> bool | None:
    """Recomputed pass for one run, or None when the run is malformed."""
    verdict = run.get("verdict") if isinstance(run, dict) else None
    if not isinstance(run, dict) or not isinstance(verdict, str):
        return None
    if run.get("not_scored"):
        return False
    return verdict.strip().upper() == expected_verdict


def _aggregate(runner: ModuleType, sid: str, runs: list[Any], expected: str) -> dict[str, Any]:
    """The `run_scenario_multi` aggregate, rebuilt from recorded runs."""
    scored = [r for r in runs if not r.get("not_scored")]
    passes = sum(1 for r in scored if _run_passed(r, expected))
    count = len(scored)
    return {
        "scenario_id": sid,
        "passes": passes,
        "runs": count,
        "requested_runs": len(runs),
        "not_scored_runs": len(runs) - count,
        "pass_rate": passes / count if count else 0.0,
        "passed": count > 0 and passes >= runner.required_passes(count),
        "flaky": 0 < passes < count,
        "reason_mismatch_runs": 0,
        "per_run": runs,
    }


def _pool(runner: ModuleType, first: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """The `_resample_base` pooling, rebuilt from recorded runs."""
    passes = first["passes"] + extra["passes"]
    count = first["runs"] + extra["runs"]
    pooled = dict(first)
    pooled.update(
        {
            "passes": passes,
            "runs": count,
            "requested_runs": first["requested_runs"] + extra["requested_runs"],
            "not_scored_runs": first["not_scored_runs"] + extra["not_scored_runs"],
            "pass_rate": passes / count if count else 0.0,
            "passed": count > 0 and passes >= runner.required_passes(count),
            "flaky": 0 < passes < count,
            "per_run": [*first["per_run"], *extra["per_run"]],
            "resample_contradicted": (
                extra["passes"] < extra["runs"] or extra["runs"] < extra["requested_runs"]
            ),
        }
    )
    return pooled


def _side(results: dict[str, Any], side: str) -> dict[str, list[Any]] | None:
    detail = results.get("detail")
    rows = detail.get(side) if isinstance(detail, dict) else None
    if not isinstance(rows, list):
        return None
    out: dict[str, list[Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("per_run"), list):
            return None
        sid = row.get("scenario_id")
        if not isinstance(sid, (str, int)) or str(sid) in out:
            return None
        sid = str(sid)
        out[sid] = row["per_run"]
    return out


@dataclass
class _Recomputed:
    before: list[dict[str, Any]]
    after: list[dict[str, Any]]
    findings: list[str]


def _recompute_sides(
    runner: ModuleType, results: dict[str, Any], expected: Expected, runs: int
) -> _Recomputed:
    out = _Recomputed([], [], [])
    before_runs, after_runs = _side(results, "before"), _side(results, "after")
    if before_runs is None or after_runs is None:
        out.findings.append("detail.before or detail.after is missing or malformed")
        return out
    ids = [str(s["id"]) for s in expected.scenarios]
    for label, side in (("before", before_runs), ("after", after_runs)):
        missing = [i for i in ids if i not in side]
        extra = sorted(set(side) - set(ids))
        if missing:
            out.findings.append(f"detail.{label} drops scenarios {missing}")
        if extra:
            out.findings.append(f"detail.{label} has scenarios not in the file {extra}")
    if out.findings:
        return out
    for scenario in expected.scenarios:
        sid = str(scenario["id"])
        want = str(scenario["expected_verdict"]).strip().upper()
        b_runs, a_runs = before_runs[sid], after_runs[sid]
        if any(_run_passed(r, want) is None for r in [*b_runs, *a_runs]):
            out.findings.append(f"{sid}: a run has no string verdict")
            continue
        if len(a_runs) != runs or len(b_runs) < runs:
            out.findings.append(
                f"{sid}: {len(b_runs)} base and {len(a_runs)} after runs; "
                f"runs_per_scenario is {runs}"
            )
            continue
        before = _aggregate(runner, sid, b_runs[:runs], want)
        after = _aggregate(runner, sid, a_runs, want)
        if len(b_runs) > runs:
            if not runner._is_suspected_regression(before, after):
                out.findings.append(f"{sid}: extra base runs without a suspected regression")
                continue
            before = _pool(runner, before, _aggregate(runner, sid, b_runs[runs:], want))
        out.before.append(before)
        out.after.append(after)
    return out


def _floor_findings(runner: ModuleType, rec: _Recomputed, required: int, total: int) -> list[str]:
    """ADR-127 decision 7 items 4 and 7, which the runner does not compute."""
    problems = []
    if total < MIN_SCENARIOS:
        problems.append(f"scenario floor: {total} scenarios, at least {MIN_SCENARIOS} required")
    carried = 0
    for before, after in zip(rec.before, rec.after, strict=True):
        unstable = runner.is_base_unstable(before, required)
        if not unstable and before["runs"] >= required and before["passes"] == before["runs"]:
            carried += 1
        if (unstable or not before["passed"]) and not (
            after["runs"] >= required and after["passes"] == after["runs"]
        ):
            problems.append(
                f"{before['scenario_id']}: fails or is unstable on base, so it must pass "
                f"every scored after run; it passed {after['passes']} of {after['runs']}"
            )
    if carried < MIN_CARRIED:
        problems.append(
            f"carried floor: {carried} scenarios pass every base run, "
            f"at least {MIN_CARRIED} required"
        )
    return problems


def _recompute_gate(
    runner: ModuleType, rec: _Recomputed, required: int, security: bool
) -> dict[str, Any]:
    """The runner's `acceptance_gate` over the rebuilt rows, with `run_comparison`'s scores."""
    stable = [
        (b, a)
        for b, a in zip(rec.before, rec.after, strict=True)
        if not runner.is_base_unstable(b, required)
    ]
    before_score = sum(1 for b, _ in stable if b["passed"]) / max(1, len(stable))
    after_score = sum(1 for _, a in stable if a["passed"]) / max(1, len(stable))
    gate: dict[str, Any] = runner.acceptance_gate(
        {
            "before_score": round(before_score, 4),
            "after_score": round(after_score, 4),
            "delta": round(after_score - before_score, 4),
            "scenario_count": len(rec.before),
            "scored_scenario_count": len(stable),
            "before_results": rec.before,
            "after_results": rec.after,
        },
        security_critical=security,
    )
    return gate


def _verdict_findings(results: dict[str, Any], gate: dict[str, Any]) -> list[str]:
    """The recorded verdict must equal the recomputed one, and that must be PASS."""
    block = results.get("gate")
    recorded = block.get("verdict") if isinstance(block, dict) else None
    problems = []
    if recorded != gate["verdict"]:
        problems.append(
            f"gate.verdict says {recorded!r} but the recorded runs recompute to {gate['verdict']!r}"
        )
    if gate["verdict"] != "PASS":
        problems.append(f"recomputed gate is {gate['verdict']}: regressions {gate['regressions']}")
    return problems


def verify_results(runner: ModuleType, results: object, expected: Expected) -> list[str]:
    """Every finding for one results file. Empty means the file holds."""
    if not isinstance(results, dict):
        return ["results file is not a JSON object"]
    problems = identity_findings(results)
    if problems:
        return problems
    problems = _match_findings(results["identity"], expected)
    security = results.get("security_critical")
    runs = results.get("runs_per_scenario")
    required = runner.SECURITY_RUNS if security else runner.DEFAULT_RUNS
    if not isinstance(security, bool):
        return [*problems, f"security_critical is {security!r}; it must be true or false"]
    if not isinstance(runs, int) or runs < required:
        return [*problems, f"runs_per_scenario {runs!r} is below the required {required}"]
    rec = _recompute_sides(runner, results, expected, runs)
    if rec.findings:
        return [*problems, *rec.findings]
    model = results["model"]
    rows = [*rec.before, *rec.after]
    if any(r.get("model_used", model) != model for row in rows for r in row["per_run"]):
        problems.append("a recorded run names a model other than identity.model")
    problems += _verdict_findings(results, _recompute_gate(runner, rec, required, security))
    problems.extend(_floor_findings(runner, rec, required, len(rec.before)))
    return problems
