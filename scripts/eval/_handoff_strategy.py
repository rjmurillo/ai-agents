"""Strategy comparison for a stalled investigation (issue #7350).

Extends the #6814 historical harness (`_control_ablation_history`, `_grade`,
`_claude`) with what it lacks: tasks with different base commits, a visible
reproduction written for the worker, a held-out check derived from the fix's own
tests by exact-once text edits, a role-prompted read-only investigator launch,
and a correction budget above zero. Two arms start from the same stalled state
with the same facts and differ only in the investigator's role text and its
framing instruction: continued analyst investigation, or a bounded handoff to
the independent-thinker.

Nothing here reads the shipped fix or the held-out file into a prompt. The brief
holds only worker-visible material.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import _control_ablation_history as history
from _control_ablation_tasks import ControlAblationConfigError, Task

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.hook_utilities.frontmatter_block import split_frontmatter  # noqa: E402

SCHEMA_VERSION = 3
ARM_CONTINUE = "continue_analyst"
ARM_HANDOFF = "handoff_independent_thinker"
ARMS = (ARM_CONTINUE, ARM_HANDOFF)
#: Correction budget, identical in both arms: repair rounds after the first attempt.
REPAIR_ROUNDS = 2
#: Read-only investigator: no Edit or Write, Bash limited to checks and history reads.
INVESTIGATOR_TOOLS = "Read,Glob,Grep,Bash"
INVESTIGATOR_ALLOWED = (
    "Bash(python3 -m pytest:*),Bash(git log:*),Bash(git diff:*),"
    "Bash(git show:*),Bash(ls:*),Bash(cat:*)"
)
ROLE_FILES = {
    ARM_CONTINUE: "src/claude/agents/analyst.md",
    ARM_HANDOFF: "src/claude/agents/independent-thinker.md",
}
FEEDBACK_CHARS = 3000
#: A provider rate limit or overload is retried, not counted as a repair turn (protocol v2).
TRANSIENT_RETRIES = 3
CITATION_NOTE = (
    "citation-freshness: ignore -- file:line citations in this report are quoted from the "
    "issue text and from agent replies about the pre-fix commit, not about HEAD"
)
TRANSIENT_WAITS = (60.0, 120.0, 240.0)

_BRIEF_KEYS = frozenset({"symptom", "rejected_hypotheses", "non_goals"})
_EXTRA_KEYS = frozenset({"visible_files", "withheld_edits", "brief", "stall"})

INSTRUCTION_CONTINUE = (
    "You are continuing an investigation of this defect. Read the code and run the "
    "reproduction. Find where the symptom is produced and why it is still red. "
    "You cannot edit files. Reply with the root cause, your evidence (file:line and "
    "command output), and the smallest change you recommend."
)
INSTRUCTION_HANDOFF = (
    "An investigation of this defect has stalled and is handed to you. Do not continue "
    "the existing line by default. List the premises behind the issue's suggested fix "
    "and the earlier attempt, test each against the code and the reproduction output, "
    "and state what evidence would falsify your own alternative. You cannot edit files. "
    "Reply with the root cause you can support, your evidence (file:line and command "
    "output), the premises you rejected, and the smallest change you recommend."
)
INSTRUCTIONS = {ARM_CONTINUE: INSTRUCTION_CONTINUE, ARM_HANDOFF: INSTRUCTION_HANDOFF}
PRODUCER_TAIL = (
    "Implement the smallest fix now. Edit only the allowed paths. Run the reproduction "
    "before you finish; it must exit 0. Report what you changed and what you ran."
)


@dataclass(frozen=True, slots=True)
class Brief:
    """Worker-visible handoff facts. Identical bytes in both arms."""

    symptom: str
    rejected_hypotheses: str
    non_goals: str


@dataclass(frozen=True, slots=True)
class HandoffCorpus:
    tasks: list[Task]
    sources: Mapping[str, history.TaskSource]
    briefs: Mapping[str, Brief]
    stall: Mapping[str, bool]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text_map(value: object, path: str) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise ControlAblationConfigError(f"{path}: expected an object of strings")
    return dict(value)


def apply_text_edits(files: Mapping[str, str], edits: object, path: str) -> dict[str, str]:
    """Apply `{path, old, new}` edits; each `old` must occur exactly once."""
    if not isinstance(edits, list):
        raise ControlAblationConfigError(f"{path}: expected an array")
    out = dict(files)
    for index, edit in enumerate(edits):
        where = f"{path}[{index}]"
        if not isinstance(edit, dict) or set(edit) != {"path", "old", "new"}:
            raise ControlAblationConfigError(f"{where}: expected {{path, old, new}}")
        target, old, new = edit["path"], edit["old"], edit["new"]
        if target not in out:
            raise ControlAblationConfigError(f"{where}.path {target!r} is not a withheld file")
        count = out[target].count(old)
        if count != 1:
            raise ControlAblationConfigError(f"{where}.old occurs {count} times in {target}")
        out[target] = out[target].replace(old, new)
    return out


def _load_brief(value: object, path: str) -> Brief:
    raw = _text_map(value, path)
    if set(raw) != _BRIEF_KEYS or not all(raw.values()):
        raise ControlAblationConfigError(f"{path}: needs non-empty {sorted(_BRIEF_KEYS)}")
    return Brief(raw["symptom"], raw["rejected_hypotheses"], raw["non_goals"])


def load_tasks(payload: Mapping[str, Any], repo_root: Path, python: str) -> HandoffCorpus:
    """Resolve a schema_version 3 document. Each task names its own base commit."""
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ControlAblationConfigError(f"schema_version must be {SCHEMA_VERSION}")
    raw_tasks = payload.get("tasks")
    if payload.keys() - {"schema_version", "tasks"} or not isinstance(raw_tasks, list):
        raise ControlAblationConfigError("document needs schema_version and a tasks array")
    tasks: list[Task] = []
    sources: dict[str, history.TaskSource] = {}
    briefs: dict[str, Brief] = {}
    stall: dict[str, bool] = {}
    for index, raw in enumerate(raw_tasks):
        path = f"tasks[{index}]"
        if not isinstance(raw, dict) or _EXTRA_KEYS - raw.keys():
            raise ControlAblationConfigError(f"{path}: needs keys {sorted(_EXTRA_KEYS)}")
        base = {k: v for k, v in raw.items() if k not in _EXTRA_KEYS}
        base["case"] = history.CASE
        task, source = history._load_one(base, index, repo_root, python)
        if task.id in sources:
            raise ControlAblationConfigError(f"duplicate task id: {task.id!r}")
        visible = _text_map(raw["visible_files"], f"{path}.visible_files")
        followup = apply_text_edits(
            task.followup_files, raw["withheld_edits"], f"{path}.withheld_edits"
        )
        if not isinstance(raw["stall"], bool):
            raise ControlAblationConfigError(f"{path}.stall must be a boolean")
        tasks.append(
            replace(task, setup_files={**task.setup_files, **visible}, followup_files=followup)
        )
        sources[task.id] = source
        briefs[task.id] = _load_brief(raw["brief"], f"{path}.brief")
        stall[task.id] = raw["stall"]
    return HandoffCorpus(tasks, sources, briefs, stall)


# ---------------------------------------------------------------------------
# Roles and prompts
# ---------------------------------------------------------------------------


def role_text(repo_root: Path, arm: str) -> str:
    """The existing role definition body, frontmatter stripped, injected verbatim."""
    text = (repo_root / ROLE_FILES[arm]).read_text(encoding="utf-8")
    block = split_frontmatter(text)
    if not block.found:
        return text
    # block.body drops blank lines after the closing fence; keep them, this text is hashed.
    return text[block.fence_end :]


def command_text(task: Task) -> str:
    """The acceptance command as the agent types it: its `python3` is the runner's."""
    return " ".join("python3" if i == 0 else part for i, part in enumerate(task.acceptance))


def facts_block(task: Task, brief: Brief, base_output: str) -> str:
    """Handoff contract fields: reproduction, evidence, rejected hypotheses, acceptance, scope."""
    allowed = ", ".join(task.allowed_paths)
    return (
        f"ISSUE (verbatim):\n{task.prompt}\n\n"
        f"RESIDUAL SYMPTOM:\n{brief.symptom}\n\n"
        f"REPRODUCTION (exits nonzero now): {command_text(task)}\n"
        f"OBSERVED OUTPUT:\n{base_output[:FEEDBACK_CHARS]}\n\n"
        f"EARLIER ATTEMPTS AND REJECTED HYPOTHESES:\n{brief.rejected_hypotheses}\n\n"
        f"ACCEPTANCE: the reproduction exits 0 and no path outside [{allowed}] changes.\n"
        f"NON-GOALS: {brief.non_goals}\n"
    )


def investigator_prompt(arm: str, facts: str, prior: str, feedback: str) -> str:
    parts = [INSTRUCTIONS[arm], facts]
    if prior:
        parts.append(f"YOUR PRIOR FINDINGS:\n{prior}")
    if feedback:
        parts.append(f"RESULT OF THE LAST CHANGE (reproduction still red):\n{feedback}")
    return "\n\n".join(parts)


def producer_prompt(facts: str, findings: str, feedback: str) -> str:
    parts = [facts, f"INVESTIGATION FINDINGS:\n{findings}"]
    if feedback:
        parts.append(
            "Your earlier change is still in the working tree. The reproduction is still "
            f"red:\n{feedback}"
        )
    parts.append(PRODUCER_TAIL)
    return "\n\n".join(parts)


def prompt_template_hashes() -> dict[str, str]:
    return {
        "instruction_continue": sha256_text(INSTRUCTION_CONTINUE),
        "instruction_handoff": sha256_text(INSTRUCTION_HANDOFF),
        "producer_tail": sha256_text(PRODUCER_TAIL),
        "investigator_tools": sha256_text(INVESTIGATOR_TOOLS + INVESTIGATOR_ALLOWED),
    }


# ---------------------------------------------------------------------------
# Decision rule (frozen in PROTOCOL.md before any live run)
# ---------------------------------------------------------------------------


def wilson(passes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 1.0)
    p = passes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (round(max(0.0, centre - margin), 2), round(min(1.0, centre + margin), 2))


def _sum(rows: Sequence[Mapping[str, Any]], key: str) -> float:
    return float(sum(row[key] for row in rows))


def _arm_rows(
    entries: Sequence[Mapping[str, Any]], arm: str, tasks: set[str]
) -> list[Mapping[str, Any]]:
    return [e for e in entries if e["arm"] == arm and e["task_id"] in tasks]


def decide(
    entries: Sequence[Mapping[str, Any]],
    stall_tasks: set[str],
    control_tasks: set[str],
    expected_cells: int,
    expected_keys: Collection[tuple[str, str, int]] | None = None,
) -> dict[str, Any]:
    """Apply the frozen rule. The default is to retain the incumbent routing.

    With `expected_keys` (the task file's `(task, arm, repeat)` grid) the cells must be
    exactly that set. A count alone lets an unexpected cell stand in for a missing one.
    """
    base = {"routing": "retain incumbent", "reasons": []}
    reasons: list[str] = []
    if len(entries) != expected_cells or not all(e["valid"] for e in entries):
        reasons.append("missing or invalid cells")
    if expected_keys is not None:
        keys = {(e["task_id"], e["arm"], e["repeat"]) for e in entries}
        missing, unexpected = set(expected_keys) - keys, keys - set(expected_keys)
        if missing or unexpected:
            reasons.append(
                f"cells differ from the task grid: missing {len(missing)}, "
                f"unexpected {len(unexpected)}"
            )
    if reasons:
        return {**base, "outcome": "INCONCLUSIVE", "reasons": reasons}

    def tally(tasks: set[str]) -> dict[str, dict[str, float]]:
        out = {}
        for arm in ARMS:
            rows = _arm_rows(entries, arm, tasks)
            out[arm] = {
                "cells": len(rows),
                "passes": sum(1 for r in rows if r["accepted"]),
                "regressions": sum(1 for r in rows if r["regression"]),
                "scope_violations": _sum(rows, "scope_violations"),
                "wall_seconds": _sum(rows, "wall_seconds"),
            }
        return out

    stall, control = tally(stall_tasks), tally(control_tasks)
    treat, cont = ARM_HANDOFF, ARM_CONTINUE
    summary = {"stall": stall, "negative_control": control}
    if control_tasks and (
        control[treat]["passes"] < control[cont]["passes"]
        or control[treat]["scope_violations"] > 0
        or control[treat]["regressions"] > control[cont]["regressions"]
    ):
        reasons = ["negative control: treatment did worse than the incumbent"]
        return {**base, "outcome": "REJECT", "reasons": reasons, **summary}
    if (
        stall[treat]["regressions"] > stall[cont]["regressions"]
        or stall[treat]["scope_violations"] > stall[cont]["scope_violations"]
    ):
        reasons = ["stalled tasks: treatment missed a regression or grew scope"]
        return {**base, "outcome": "REJECT", "reasons": reasons, **summary}
    if len(stall_tasks) < 2:
        reasons = [f"{len(stall_tasks)} stalled task(s); the rule needs at least 2"]
        return {**base, "outcome": "INCONCLUSIVE", "reasons": reasons, **summary}
    gain = stall[treat]["passes"] - stall[cont]["passes"]
    slower = stall[treat]["wall_seconds"] > 1.5 * stall[cont]["wall_seconds"]
    if gain >= 2 and not slower:
        return {
            "outcome": "SUPPORTED_NARROW",
            "routing": "bounded handoff to independent-thinker after a repeated repair failure",
            "reasons": [f"treatment accepted {gain} more stalled cells, within 1.5x time"],
            **summary,
        }
    return {**base, "outcome": "INCONCLUSIVE", "reasons": [f"gain {gain} (needs 2)"], **summary}


def combine(
    report_dirs: Sequence[Path], payload: Mapping[str, Any], repeats: int = 3
) -> dict[str, Any]:
    """Apply the frozen rule to the cells of several batches of one protocol.

    A later batch fills cells an earlier batch lost to a provider failure. A cell
    present twice is refused: a cell is scored once, never replaced by a rerun.
    """
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()
    reference: dict[str, Any] = {}
    for report_dir in report_dirs:
        report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
        provenance = report.get("provenance") or {}
        facts = {
            "tasks_file_sha256": provenance.get("tasks_file_sha256"),
            "model_requested": provenance.get("model_requested"),
            "effort": report.get("effort"),
        }
        for name, value in facts.items():
            if not value:
                raise ControlAblationConfigError(f"{report_dir}: report lacks {name}")
            if reference.setdefault(name, value) != value:
                raise ControlAblationConfigError(f"batches disagree on {name}")
        for entry in report["entries"]:
            key = (entry["task_id"], entry["arm"], entry["repeat"])
            if key in seen:
                raise ControlAblationConfigError(f"cell {key} appears in more than one batch")
            seen.add(key)
            entries.append(entry)
    tasks = payload["tasks"]
    expected = {(t["id"], arm, r) for t in tasks for arm in ARMS for r in range(repeats)}
    if seen - expected:
        raise ControlAblationConfigError(
            f"unexpected cells not in the task grid: {sorted(seen - expected)}"
        )
    stall = {t["id"] for t in tasks if t["stall"]}
    control = {t["id"] for t in tasks if not t["stall"]}
    return {
        "batches": [str(d) for d in report_dirs],
        "tasks_file_sha256": reference["tasks_file_sha256"],
        "cells": len(entries),
        "expected_cells": len(expected),
        "missing_cells": [list(c) for c in sorted(expected - seen)],
        "decision": decide(entries, stall, control, len(expected), expected_keys=expected),
    }


def combine_files(
    report_dirs: Sequence[Path], tasks_file: Path, output_dir: Path | None
) -> dict[str, Any]:
    """`combine` over a task file, writing `decision.json` into `output_dir` when given."""
    raw = tasks_file.read_bytes()
    result = combine(report_dirs, json.loads(raw.decode("utf-8")))
    if result["tasks_file_sha256"] != hashlib.sha256(raw).hexdigest():
        raise ControlAblationConfigError("the task file on disk is not the one the reports ran")
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "decision.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
