"""Pure logic for the bounded longitudinal pilot (issue #6993).

Two conditions run the same frozen task sequence, each task in a fresh session:
`vendor_only` (the baseline, always reported) and `local_context` (validated
local facts plus approved corrections retained from earlier tasks). Nothing here
spawns a model. `eval_longitudinal_pilot.py` owns the runners and the CLI.

Rules this module enforces:
- A spend ceiling is mandatory. `Ledger` refuses to exist without a positive,
  finite ceiling, and refuses a call that could cross it.
- Human effort is `None` unless a timed row exists. Unknown is never 0.
- A local fact whose probe fails against the checkout is withheld and reported
  as stale. It is never passed to the model.
- Published records carry hashes, counts, and scores. They never carry the model
  transcript or the answer text.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONDITIONS = ("vendor_only", "local_context")
BASELINE = "vendor_only"
PHASES = ("pre", "post")
ROLES = ("seed", "correction_source", "related", "stale_trap", "held_out")
ACCEPT_F1 = 1.0
CHARS_PER_TOKEN = 4
COST_COMPONENTS = (
    "bootstrap_usd",
    "execution_usd",
    "retrieval_usd",
    "maintenance_usd",
    "rework_usd",
)
LIMITATIONS = (
    "Fixture tasks on one repository; results do not generalize to customer outcomes.",
    "Clarification requests are counted as prose lines ending in a question mark.",
    "Retrieval cost is not separable inside one print-mode call; only tokens are estimated.",
    "No production verifier or named review owner is attached; no production-value claim.",
)


class PilotError(ValueError):
    """The pilot file, ceiling, or inputs are invalid."""


def _fail(message: str) -> PilotError:
    return PilotError(message)


def _need_str(obj: dict[str, Any], key: str, where: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _fail(f"{where}: '{key}' must be a non-empty string")
    return value


def _validate_task(task: object, seen: dict[str, dict[str, Any]], corrections: set[str]) -> None:
    if not isinstance(task, dict):
        raise _fail("every task must be an object")
    tid = _need_str(task, "id", "task")
    where = f"task {tid!r}"
    if tid in seen:
        raise _fail(f"{where}: duplicate id")
    _validate_task_fields(task, where)
    _validate_task_links(task, where, seen, corrections)
    seen[tid] = task


def _validate_gold(task: dict[str, Any], where: str) -> None:
    gold = task.get("gold")
    if not isinstance(gold, list) or not gold or not all(isinstance(g, str) for g in gold):
        raise _fail(f"{where}: gold must be a non-empty list of strings")
    probe = task.get("gold_probe")
    if not isinstance(probe, dict) or not probe.get("dir") or not probe.get("pattern"):
        raise _fail(f"{where}: gold_probe needs 'dir' and 'pattern'")


def _validate_task_fields(task: dict[str, Any], where: str) -> None:
    if task.get("phase") not in PHASES or task.get("role") not in ROLES:
        raise _fail(f"{where}: phase must be one of {PHASES} and role one of {ROLES}")
    for key in ("prompt", "answer_key"):
        _need_str(task, key, where)
    if task.get("grader") != "set_f1":
        raise _fail(f"{where}: grader must be 'set_f1'")
    _validate_gold(task, where)
    points = task.get("decision_points")
    if not isinstance(points, int) or isinstance(points, bool) or points < 0:
        raise _fail(f"{where}: decision_points must be an int >= 0")


def _validate_task_links(
    task: dict[str, Any], where: str, seen: dict[str, dict[str, Any]], corrections: set[str]
) -> None:
    if seen and PHASES.index(task["phase"]) < PHASES.index(list(seen.values())[-1]["phase"]):
        raise _fail(f"{where}: a 'pre' task cannot follow a 'post' task")
    if task.get("followup_of") is not None and task["followup_of"] not in seen:
        raise _fail(f"{where}: followup_of must name an earlier task")
    if task.get("uses_correction") is not None and task["uses_correction"] not in corrections:
        raise _fail(f"{where}: uses_correction must name an earlier approved correction")
    corr = task.get("correction")
    if corr is not None:
        if not isinstance(corr, dict) or not corr.get("id") or not corr.get("text"):
            raise _fail(f"{where}: correction needs 'id' and 'text'")
        if corr.get("approved") is True:
            corrections.add(corr["id"])


def _validate_facts(data: dict[str, Any]) -> list[dict[str, Any]]:
    rename = (data.get("repo_change") or {}).get("rename")
    if not (
        isinstance(rename, list) and len(rename) == 2 and all(isinstance(r, str) for r in rename)
    ):
        raise _fail("repo_change.rename must be [old, new]")
    ctx = data.get("local_context") or {}
    _need_str(ctx, "revision", "local_context")
    facts = ctx.get("facts")
    if not isinstance(facts, list) or not facts:
        raise _fail("local_context.facts must be a non-empty list")
    for fact in facts:
        if not (isinstance(fact, dict) and fact.get("id") and fact.get("text")):
            raise _fail("every fact needs 'id' and 'text'")
        if not isinstance(fact.get("probe"), dict) or not set(fact.get("valid_in", [])) <= set(
            PHASES
        ):
            raise _fail(f"fact {fact.get('id')!r}: needs a probe and valid_in within {PHASES}")
    return facts


def load_pilot(path: Path) -> dict[str, Any]:
    """Read and validate the frozen pilot file, or raise `PilotError`."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _fail(f"cannot read pilot file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise _fail(f"{path}: top level must be an object")
    for key in ("revision", "frozen", "outcome", "verifier", "preamble"):
        _need_str(data, key, str(path))
    facts = _validate_facts(data)
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise _fail("'tasks' must be a non-empty list")
    seen: dict[str, dict[str, Any]] = {}
    corrections: set[str] = set()
    for task in tasks:
        _validate_task(task, seen, corrections)
    fact_ids = {f["id"] for f in facts}
    for task in tasks:
        if task.get("uses_fact") is not None and task["uses_fact"] not in fact_ids:
            raise _fail(f"task {task['id']!r}: uses_fact names an unknown fact")
    return data


@dataclass
class Ledger:
    """Hard spend ceiling. A call is refused when it could cross the ceiling."""

    ceiling_usd: float
    reserve_usd: float
    max_calls: int | None = None
    spent_usd: float = 0.0
    calls: int = 0
    stopped_reason: str | None = field(default=None)
    overrun_usd: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (("ceiling_usd", self.ceiling_usd), ("reserve_usd", self.reserve_usd)):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise _fail(f"{name} is required and must be a number")
            if not math.isfinite(value) or value <= 0:
                raise _fail(f"{name} must be a positive finite number, got {value!r}")
        if self.reserve_usd > self.ceiling_usd:
            raise _fail("per-call reserve exceeds the ceiling: no call could ever start")
        if self.max_calls is not None and self.max_calls < 1:
            raise _fail("max_calls must be >= 1 when given")

    def allow(self) -> bool:
        """True when one more call fits under the ceiling; records why not otherwise."""
        if self.stopped_reason is not None:
            return False
        if self.max_calls is not None and self.calls >= self.max_calls:
            self.stopped_reason = f"max_calls {self.max_calls} reached"
        elif self.spent_usd + self.reserve_usd > self.ceiling_usd:
            self.stopped_reason = (
                f"ceiling ${self.ceiling_usd:.4f} would be crossed "
                f"(spent ${self.spent_usd:.4f} + reserve ${self.reserve_usd:.4f})"
            )
        return self.stopped_reason is None

    def charge(self, cost_usd: float | None) -> None:
        """Book one finished call. An unreported cost is booked at the reserve."""
        self.calls += 1
        self.spent_usd += self.reserve_usd if cost_usd is None else float(cost_usd)
        if self.spent_usd > self.ceiling_usd:
            # A call can cost more than the reserve; the ceiling is checked before a call,
            # not enforced inside it. Record the breach and stop the run.
            self.overrun_usd = round(self.spent_usd - self.ceiling_usd, 6)
            self.stopped_reason = (
                f"ceiling ${self.ceiling_usd:.4f} exceeded by ${self.overrun_usd:.4f}: "
                "a call cost more than the per-call reserve"
            )


def _norm(path: str) -> str:
    return re.split(r"::|:\d", str(path).strip().strip("`"), maxsplit=1)[0].rstrip("/")


def normalize_answer(task: dict[str, Any], answer: dict[str, Any] | None) -> set[str] | None:
    """The predicted path set for a task, minus excluded files, or None when absent."""
    values = (answer or {}).get(task["answer_key"])
    if not isinstance(values, list):
        return None
    excluded = set(task["gold_probe"].get("exclude") or [])
    return {_norm(v) for v in values if isinstance(v, str) and Path(_norm(v)).name not in excluded}


def grade_task(task: dict[str, Any], answer: dict[str, Any] | None) -> dict[str, Any]:
    """F1, acceptance, and residual defects (missing plus extra) against gold."""
    gold = {_norm(g) for g in task["gold"]}
    predicted = normalize_answer(task, answer)
    if predicted is None:
        return {"f1": 0.0, "accepted": False, "missing": len(gold), "extra": 0, "answered": False}
    hits = len(predicted & gold)
    precision = hits / len(predicted) if predicted else 0.0
    recall = hits / len(gold)
    f1 = 2 * precision * recall / (precision + recall) if hits else 0.0
    return {
        "f1": round(f1, 4),
        "accepted": f1 >= ACCEPT_F1,
        "missing": len(gold - predicted),
        "extra": len(predicted - gold),
        "answered": True,
    }


def count_clarifications(text: str) -> int:
    """Prose lines ending in '?' outside fenced blocks: questions put to the human."""
    prose = re.sub(r"```.*?(```|\Z)", "", text or "", flags=re.DOTALL)
    return sum(1 for line in prose.splitlines() if line.rstrip().endswith("?"))


def probe_ok(probe: dict[str, Any], root: Path, removed: frozenset[str]) -> bool:
    """True when the fact's probe still holds. `removed` are paths the repo change deleted."""
    target = probe.get("path_exists")
    if not isinstance(target, str):
        raise _fail(f"unsupported probe {probe!r}: only 'path_exists' is defined")
    return target not in removed and (root / target).exists()


@dataclass
class PilotState:
    """What one condition has retained across sessions. Empty for the baseline."""

    corrections: dict[str, str] = field(default_factory=dict)

    def retain(self, task: dict[str, Any]) -> None:
        corr = task.get("correction")
        if corr and corr.get("approved") is True:
            self.corrections[corr["id"]] = corr["text"]


@dataclass
class ContextResult:
    text: str
    fact_ids: list[str]
    stale_fact_ids: list[str]
    correction_ids: list[str]
    tokens_est: int


def build_context(
    pilot: dict[str, Any], condition: str, task: dict[str, Any], state: PilotState, root: Path
) -> ContextResult:
    """The local context for one fresh session. The baseline gets none."""
    if condition == BASELINE:
        return ContextResult("", [], [], [], 0)
    removed = (
        frozenset(pilot["repo_change"]["rename"][:1]) if task["phase"] == "post" else frozenset()
    )
    kept: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    for fact in pilot["local_context"]["facts"]:
        (kept if probe_ok(fact["probe"], root, removed) else stale).append(fact)
    lines = ["Validated local context:"]
    lines += [f"- {f['id']}: {f['text']}" for f in kept]
    lines += [f"- {cid} (approved correction): {text}" for cid, text in state.corrections.items()]
    if stale:
        ids = ", ".join(f["id"] for f in stale)
        lines.append(
            f"Withheld as stale (freshness probe failed): {ids}. Verify against the repository."
        )
    text = "\n".join(lines)
    return ContextResult(
        text,
        [f["id"] for f in kept],
        [f["id"] for f in stale],
        list(state.corrections),
        len(text) // CHARS_PER_TOKEN,
    )


def stale_truth(pilot: dict[str, Any], phase: str) -> set[str]:
    """Fact ids that are wrong in `phase`, from the fixture's own ground truth."""
    return {f["id"] for f in pilot["local_context"]["facts"] if phase not in f.get("valid_in", [])}


def context_revision(pilot: dict[str, Any]) -> str:
    blob = json.dumps(pilot["local_context"], sort_keys=True, separators=(",", ":"))
    return f"{pilot['local_context']['revision']}+{hashlib.sha256(blob.encode()).hexdigest()[:12]}"


def build_prompt(pilot: dict[str, Any], task: dict[str, Any], ctx: ContextResult) -> str:
    parts = [pilot["preamble"]]
    if ctx.text:
        parts.append(ctx.text)
    parts.append(task["prompt"])
    return "\n\n".join(parts)


def derive_gold(task: dict[str, Any], root: Path) -> list[str]:
    """Re-derive a task's gold from a checkout with its gold_probe (no model)."""
    probe = task["gold_probe"]
    pattern = re.compile(probe["pattern"], re.MULTILINE)
    skip = set(probe.get("exclude") or [])
    found: list[str] = []
    for path in sorted((root / probe["dir"]).glob("*.py")):
        if path.name in skip:
            continue
        if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
            found.append(f"{probe['dir']}/{path.name}")
    return found
