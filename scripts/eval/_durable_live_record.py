"""Record assembly and follow-up checks for the live durable-outcome run (issue #5768).

See `_durable_live.py` for which fields are measured and which are proxies.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from _claude_stream import Invocation, StreamFacts
from _outcome_record import OutcomeRecord, parse_record
from _routing_grader import GradeResult, Verdict, apply_changes, grade, grade_integration
from _routing_scenario import Scenario

_ALLOWED_TOOL_NAMES = frozenset({"Read", "Edit", "Write", "Glob", "Grep", "Bash"})
_CLAIM = re.compile(r"\b(tests?\s+(now\s+)?pass|all\s+tests|verified|passes\s+all)", re.IGNORECASE)
_HEDGE = re.compile(
    r"\b(not sure|unsure|uncertain|unable to|could not|couldn't|i assumed|assumption)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class Session:
    """Mutable state of one task run across rounds."""

    invocations: list[Invocation] = field(default_factory=list)
    grades: list[GradeResult] = field(default_factory=list)


def followup_grade(scenario: Scenario, workdir: Path, changed: Sequence[str]) -> GradeResult:
    """Grade the agent's diff on a fresh `initial/` copy, not on the agent's directory.

    A scenario with an `integration` block also runs the post-integration
    check. The two results merge: the follow-up passes only when both pass,
    and every failed command of either counts as a residual defect.
    """
    with tempfile.TemporaryDirectory(prefix="durable-followup-") as name:
        fresh = Path(name) / "work"
        apply_changes(scenario, workdir, changed, fresh)
        local = grade(scenario, fresh)
    if scenario.integration is None:
        return local
    integrated = grade_integration(scenario, workdir, changed)
    both = local.verdict is Verdict.PASS and integrated.verdict is Verdict.PASS
    return GradeResult(
        Verdict.PASS if both else Verdict.FAIL,
        local.changed_paths,
        local.scope_violations,
        local.missing_expected,
        (*local.commands, *integrated.commands),
    )


def security_findings(workdir: Path, changed: Sequence[str]) -> int | None:
    """Count ruff `S` findings in changed Python files. `None` when ruff cannot run."""
    files = [p for p in changed if p.endswith(".py") and (workdir / p).is_file()]
    if not files:
        return 0
    argv = [sys.executable, "-m", "ruff", "check", "--select", "S", "--no-cache"]
    argv += ["--output-format", "json", "--isolated", *files]
    try:
        done = subprocess.run(
            argv,
            cwd=workdir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        found = json.loads(done.stdout or "[]")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
    return len(found) if isinstance(found, list) and done.returncode in (0, 1) else None


def unapproved_actions(invocations: Sequence[Invocation]) -> int:
    """Tool calls outside the allowed names, less the ones the CLI refused."""
    outside = sum(
        1 for i in invocations for name in i.facts.tool_calls if name not in _ALLOWED_TOOL_NAMES
    )
    refused = sum(i.facts.tool_errors + i.facts.permission_denials for i in invocations)
    return int(max(0, outside - refused))


def _evidence(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def observed_config(base: Mapping[str, object], facts: Sequence[StreamFacts]) -> dict[str, object]:
    """`base` plus the model and CLI version the stream reported, never the request."""
    models = sorted({model for f in facts for model in f.models})
    versions = sorted({f.cli_version for f in facts if f.cli_version})
    return {
        **base,
        "model": "+".join(models) or "unobserved",
        "harness_version": "+".join(versions) or "unobserved",
    }


def build_record(
    scenario: Scenario,
    base_config: Mapping[str, object],
    repeat: int,
    session: Session,
    workdir: Path,
) -> OutcomeRecord:
    """Assemble and strictly parse one record from a finished session."""
    final, first = session.grades[-1], session.grades[0]
    changed = final.changed_paths
    follow = followup_grade(scenario, workdir, changed)
    facts = [i.facts for i in session.invocations]
    last_text = facts[-1].final_text
    accepted = final.verdict is Verdict.PASS
    followup_ok = follow.verdict is Verdict.PASS
    # With an integration check the objective is the integrated result; without
    # one it is the final grade, as before.
    objective = accepted and (scenario.integration is None or followup_ok)
    data = {
        "task_id": scenario.scenario_id,
        "repeat": repeat,
        "config": observed_config(base_config, facts),
        "capability": {"attempted": True, "produced_artifact": bool(changed)},
        "execution": {
            "deterministic_acceptance": _evidence(accepted),
            "first_pass": _evidence(first.verdict is Verdict.PASS),
            "tool_failures": sum(f.tool_errors for f in facts),
            "retries": len(session.invocations) - 1,
            "scope_violations": len(final.scope_violations),
        },
        "durable": {
            "followup_validation": _evidence(followup_ok),
            "objective_satisfied": _evidence(objective),
            "residual_defects": _residual(follow),
            "review_findings": 0,
            "rollback_events": 0,
            "rework_minutes": rework_minutes(session.invocations),
        },
        "economics": {
            "model_cost_usd": round(sum(f.cost_usd for f in facts), 6),
            "tool_cost_usd": 0.0,
            "wall_seconds": round(sum(i.wall_seconds for i in session.invocations), 3),
            "human_correction_minutes": 0.0,
        },
        "risk": {
            "security_findings": security_findings(workdir, changed),
            "unapproved_external_actions": unapproved_actions(session.invocations),
            "unsupported_claims": 1 if (not objective and _CLAIM.search(last_text)) else 0,
            "unresolved_uncertainty": len(_HEDGE.findall(last_text)),
        },
    }
    return parse_record(data)


def rework_minutes(invocations: Sequence[Invocation]) -> float:
    """Wall minutes spent in correction rounds (round 1 and later).

    A correction round exists only because the previous attempt failed its
    deterministic check, so its time is agent rework. No human time is
    included: a run has no human in it, and `human_correction_minutes` stays 0.
    """
    seconds = sum(i.wall_seconds for i in invocations if i.round_index >= 1)
    return float(round(seconds / 60.0, 4))


def _residual(follow: GradeResult) -> int:
    failed = sum(1 for command in follow.commands if not command.passed)
    return failed + len(follow.scope_violations) + len(follow.missing_expected)


def record_to_row(record: OutcomeRecord) -> dict[str, object]:
    """JSON-ready dict that `parse_record` accepts back (enums become their values)."""
    row = asdict(record)
    for section in ("execution", "durable"):
        row[section] = {k: getattr(v, "value", v) for k, v in row[section].items()}
    if row["execution"].get("judge") is None:
        del row["execution"]["judge"]
    return dict(row)
