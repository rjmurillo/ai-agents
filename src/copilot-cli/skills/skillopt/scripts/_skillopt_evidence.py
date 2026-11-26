"""Evidence-driven edits: weakness patterns, manifesto entries, read-only pins, proposer tier.

Four checks that make each proposed edit a falsifiable claim tied to evidence,
after Weng, "Harness Engineering for Self-Improvement" (Lil'Log, 2026):

  - weakness-check  : failing train tasks clustered into verifier-grounded
                      patterns before any edit is proposed (Self-Harness,
                      Zhang et al., arXiv:2606.09498)
  - manifesto-check : one entry per patch naming the failure evidence, the
                      inferred root cause, the targeted fix, and a predicted
                      impact with expected fixes and at-risk regressions
                      (AHE, Lin et al., arXiv:2604.25850)
  - manifesto-verify: next-round check of those predictions on train results
  - pin / pin-check : sha256 of the read-only files (eval set, verifier,
                      tracer, any model or budget config file) taken at
                      baseline; the model name is recorded, not hashed
  - proposer tier   : warn on a lightweight-tier proposer (STOP, Zelikman et
                      al., COLM 2024)

Every check reads train evidence only. A sel task id in a task list or a
free-text field of a weakness pattern or a manifesto entry exits 2, because
the candidate author must not see sel tasks (SKILL.md Precondition 4). Patch
text is not scanned.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from _skillopt_bundle import path_sha256
from _skillopt_gates import _split_task_ids
from _skillopt_patching import SkillOptError

WEAKNESS_SCHEMA = "skillopt-weakness/1"
MANIFESTO_SCHEMA = "skillopt-manifesto/1"
PINS_SCHEMA = "skillopt-pins/1"

# AHE's seven editable harness components (Lin et al., arXiv:2604.25850).
COMPONENTS = (
    "system-prompt",
    "tool-description",
    "tool-implementation",
    "middleware",
    "skill",
    "sub-agent-configuration",
    "long-term-memory",
)

PATTERN_TEXT_FIELDS = ("verifier_cause", "agent_behavior", "mechanism")
ENTRY_TEXT_FIELDS = ("root_cause", "fix")

# Proposer tiers. STOP improved with GPT-4 and degraded with GPT-3.5 and
# Mixtral, so a lightweight proposer can make the target worse.
_LIGHTWEIGHT = re.compile(
    r"((?<![a-z])(haiku|mini|nano|lite|tiny|small)(?![a-z])|gpt-3\.5|mixtral|\b[1-9]b\b)",
    re.IGNORECASE,
)
_CAPABLE = re.compile(r"(opus|sonnet|fable|gpt-4|gpt-5|\bo3\b|-pro\b|ultra)", re.IGNORECASE)
TIER_HINT = (
    "STOP (Zelikman et al., COLM 2024) improved with GPT-4 and degraded with "
    "GPT-3.5 and Mixtral: a weak proposer can make the target worse. Use a "
    "sonnet-tier or stronger proposer, or record why this one is acceptable."
)


def proposer_tier(model: str) -> str:
    """Classify a proposer model name as lightweight, capable, or unknown."""
    if not isinstance(model, str) or not model.strip():
        raise SkillOptError("proposer model must be a nonempty string")
    if _LIGHTWEIGHT.search(model):
        return "lightweight"
    if _CAPABLE.search(model):
        return "capable"
    return "unknown"


def _require_schema(doc: Any, schema: str, label: str) -> dict[str, Any]:
    if not isinstance(doc, dict):
        raise SkillOptError(f"{label} must be a JSON object")
    if doc.get("schema") != schema:
        raise SkillOptError(f"{label} 'schema' must be {schema!r}")
    return doc


def _text(entry: dict[str, Any], field: str, where: str, sel: set[str] | None = None) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SkillOptError(f"{where}: '{field}' must be a nonempty string")
    for tid in sorted(sel or ()):
        if re.search(rf"(?<![\w-]){re.escape(tid)}(?![\w-])", value):
            raise SkillOptError(
                f"{where}: '{field}' names sel task {tid!r}; "
                "the candidate author must use train evidence only"
            )
    return value


def _train_ids(
    value: Any, field: str, where: str, train: set[str], sel: set[str], *, allow_empty: bool
) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(t, str) and t for t in value):
        raise SkillOptError(f"{where}: '{field}' must be a list of task ids")
    if not value and not allow_empty:
        raise SkillOptError(f"{where}: '{field}' must name at least one task")
    leaked = [t for t in value if t in sel]
    if leaked:
        raise SkillOptError(
            f"{where}: '{field}' names sel task(s) {', '.join(leaked)}; "
            "the candidate author must use train evidence only"
        )
    unknown = [t for t in value if t not in train]
    if unknown:
        raise SkillOptError(f"{where}: '{field}' names non-train task(s) {', '.join(unknown)}")
    return value


def _splits(eval_set: dict[str, Any]) -> tuple[list[str], set[str]]:
    train = _split_task_ids(eval_set, "train")
    splits = eval_set["splits"]
    sel = set(_split_task_ids(eval_set, "sel")) if "sel" in splits else set()
    return train, sel


# --------------------------------------------------------------------------- #
# Weakness mining
# --------------------------------------------------------------------------- #
def check_weakness(
    eval_set: dict[str, Any], incumbent_results: dict[str, Any], weakness: Any
) -> dict[str, Any]:
    """Validate a weakness file and report recurrence and unclustered failures.

    Each pattern clusters failing train tasks under one verifier-grounded cause:
    the terminal verifier cause, the causal agent behavior, and the mechanism
    the trace exposed. A task belongs to at most one pattern.
    """
    doc = _require_schema(weakness, WEAKNESS_SCHEMA, "weakness file")
    train, sel = _splits(eval_set)
    train_set = set(train)
    patterns = doc.get("patterns")
    if not isinstance(patterns, list) or not patterns:
        raise SkillOptError("weakness file 'patterns' must be a nonempty list")
    seen_ids: set[str] = set()
    owner: dict[str, str] = {}
    out: list[dict[str, Any]] = []
    for index, pattern in enumerate(patterns):
        where = f"pattern {index}"
        if not isinstance(pattern, dict):
            raise SkillOptError(f"{where} must be an object")
        pid = _text(pattern, "id", where)
        if pid in seen_ids:
            raise SkillOptError(f"duplicate pattern id {pid!r}")
        seen_ids.add(pid)
        for field in PATTERN_TEXT_FIELDS:
            _text(pattern, field, f"pattern {pid!r}", sel)
        if not isinstance(pattern.get("addressable"), bool):
            raise SkillOptError(f"pattern {pid!r}: 'addressable' must be true or false")
        tasks = _train_ids(
            pattern.get("tasks"), "tasks", f"pattern {pid!r}", train_set, sel, allow_empty=False
        )
        for tid in tasks:
            if incumbent_results.get(tid) is True:
                raise SkillOptError(
                    f"pattern {pid!r}: task {tid!r} passed at baseline; cluster failures only"
                )
            if tid in owner:
                raise SkillOptError(f"task {tid!r} is in patterns {owner[tid]!r} and {pid!r}")
            owner[tid] = pid
        out.append(
            {
                "id": pid,
                "tasks": tasks,
                "recurrent": len(tasks) >= 2,
                "addressable": pattern["addressable"],
            }
        )
    failing = [t for t in train if incumbent_results.get(t) is not True]
    return {
        "patterns": out,
        "recurrent_addressable": [p["id"] for p in out if p["recurrent"] and p["addressable"]],
        "unclustered_failures": [t for t in failing if t not in owner],
    }


# --------------------------------------------------------------------------- #
# Manifesto: one falsifiable prediction per patch
# --------------------------------------------------------------------------- #
def _check_predictions(
    entry: dict[str, Any],
    where: str,
    train_set: set[str],
    sel: set[str],
    incumbent_results: dict[str, Any],
) -> None:
    """Predicted fixes must fail at baseline; at-risk tasks must pass at baseline."""
    fixes = _train_ids(
        entry.get("predicted_fixes"), "predicted_fixes", where, train_set, sel, allow_empty=False
    )
    passing = [t for t in fixes if incumbent_results.get(t) is True]
    if passing:
        raise SkillOptError(
            f"{where}: predicted_fixes {', '.join(passing)} already pass at baseline"
        )
    risks = _train_ids(entry.get("at_risk"), "at_risk", where, train_set, sel, allow_empty=True)
    failing = [t for t in risks if incumbent_results.get(t) is not True]
    if failing:
        raise SkillOptError(
            f"{where}: at_risk {', '.join(failing)} do not pass at baseline; "
            "list only tasks that pass now"
        )


def check_manifesto(
    eval_set: dict[str, Any],
    incumbent_results: dict[str, Any],
    weakness: Any,
    manifesto: Any,
    patches: Any,
) -> dict[str, Any]:
    """Validate one manifesto entry per patch against the weakness patterns."""
    mined = check_weakness(eval_set, incumbent_results, weakness)
    patterns = {p["id"]: p for p in mined["patterns"]}
    doc = _require_schema(manifesto, MANIFESTO_SCHEMA, "manifesto")
    if not isinstance(patches, list) or not patches:
        raise SkillOptError("patches must be a nonempty list")
    tier = proposer_tier(_text(doc, "proposer_model", "manifesto"))
    train, sel = _splits(eval_set)
    train_set = set(train)
    entries = doc.get("entries")
    if not isinstance(entries, list) or not entries:
        raise SkillOptError("manifesto 'entries' must be a nonempty list")
    covered: dict[int, int] = {}
    targeted: list[str] = []
    for index, entry in enumerate(entries):
        where = f"manifesto entry {index}"
        if not isinstance(entry, dict):
            raise SkillOptError(f"{where} must be an object")
        patch = entry.get("patch")
        if isinstance(patch, bool) or not isinstance(patch, int) or not 0 <= patch < len(patches):
            raise SkillOptError(
                f"{where}: 'patch' must be a patch index from 0 to {len(patches) - 1}"
            )
        if patch in covered:
            raise SkillOptError(f"patch {patch} has manifesto entries {covered[patch]} and {index}")
        covered[patch] = index
        pid = _text(entry, "pattern", where)
        if pid not in patterns:
            raise SkillOptError(f"{where}: unknown pattern {pid!r}")
        if not patterns[pid]["addressable"]:
            raise SkillOptError(f"{where}: pattern {pid!r} is not addressable; do not patch it")
        targeted.append(pid)
        for field in ENTRY_TEXT_FIELDS:
            _text(entry, field, where, sel)
        if entry.get("component") not in COMPONENTS:
            raise SkillOptError(f"{where}: 'component' must be one of {', '.join(COMPONENTS)}")
        evidence = _train_ids(
            entry.get("evidence"), "evidence", where, train_set, sel, allow_empty=False
        )
        stray = [t for t in evidence if t not in patterns[pid]["tasks"]]
        if stray:
            raise SkillOptError(f"{where}: evidence {', '.join(stray)} is not in pattern {pid!r}")
        _check_predictions(entry, where, train_set, sel, incumbent_results)
    missing = [i for i in range(len(patches)) if i not in covered]
    if missing:
        raise SkillOptError(f"patch(es) {', '.join(map(str, missing))} have no manifesto entry")
    warnings: list[str] = []
    if tier != "capable":
        warnings.append(f"proposer tier {tier}: {TIER_HINT}")
    skipped = [p for p in mined["recurrent_addressable"] if p not in targeted]
    single = sorted({p for p in targeted if not patterns[p]["recurrent"]})
    if single and skipped:
        warnings.append(
            f"targets single-task pattern(s) {', '.join(single)} while recurrent "
            f"pattern(s) {', '.join(skipped)} go untargeted; prefer recurrent patterns"
        )
    return {
        "entries": len(entries),
        "patterns_targeted": sorted(set(targeted)),
        "proposer_tier": tier,
        "warnings": warnings,
    }


def _outcome(results: dict[str, Any], tid: str) -> bool | None:
    value = results.get(tid)
    return value if isinstance(value, bool) else None


def verify_manifesto(
    eval_set: dict[str, Any],
    manifesto: Any,
    incumbent_results: dict[str, Any],
    candidate_results: dict[str, Any],
) -> dict[str, Any]:
    """Score each prediction against train results from the next round.

    Verdict precedence: PREDICTION_UNVERIFIED (a named or train task has no
    boolean result), then PREDICTION_FALSIFIED (a predicted fix did not flip
    to pass, or a train regression no entry listed as at risk), then
    PREDICTIONS_HELD. A listed at-risk regression is reported, not falsified.
    """
    doc = _require_schema(manifesto, MANIFESTO_SCHEMA, "manifesto")
    train, sel = _splits(eval_set)
    train_set = set(train)
    entries = doc.get("entries")
    if not isinstance(entries, list) or not entries:
        raise SkillOptError("manifesto 'entries' must be a nonempty list")
    unverified = sorted(
        t
        for t in train
        if _outcome(incumbent_results, t) is None or _outcome(candidate_results, t) is None
    )
    at_risk_all: set[str] = set()
    report_entries: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        where = f"manifesto entry {index}"
        if not isinstance(entry, dict):
            raise SkillOptError(f"{where} must be an object")
        fixes = _train_ids(
            entry.get("predicted_fixes"),
            "predicted_fixes",
            where,
            train_set,
            sel,
            allow_empty=False,
        )
        risks = _train_ids(entry.get("at_risk"), "at_risk", where, train_set, sel, allow_empty=True)
        at_risk_all.update(risks)
        report_entries.append(
            {
                "patch": entry.get("patch"),
                "confirmed_fixes": [
                    t
                    for t in fixes
                    if incumbent_results.get(t) is not True and candidate_results.get(t) is True
                ],
                "missed_fixes": [
                    t
                    for t in fixes
                    if incumbent_results.get(t) is True or candidate_results.get(t) is not True
                ],
                "at_risk_regressed": [
                    t
                    for t in risks
                    if incumbent_results.get(t) is True and candidate_results.get(t) is not True
                ],
            }
        )
    regressions = [
        t
        for t in train
        if incumbent_results.get(t) is True and candidate_results.get(t) is not True
    ]
    unpredicted = [t for t in regressions if t not in at_risk_all]
    if unverified:
        verdict = "PREDICTION_UNVERIFIED"
    elif unpredicted or any(e["missed_fixes"] for e in report_entries):
        verdict = "PREDICTION_FALSIFIED"
    else:
        verdict = "PREDICTIONS_HELD"
    return {
        "verdict": verdict,
        "entries": report_entries,
        "unpredicted_regressions": unpredicted,
        "unverified": unverified,
    }


# --------------------------------------------------------------------------- #
# Read-only pins: eval set, verifier, tracer, and model configuration
# --------------------------------------------------------------------------- #
def make_pins(surfaces: dict[str, Path], model: str) -> dict[str, Any]:
    """Record sha256 digests of the read-only surfaces and the model in use."""
    if "eval" not in surfaces:
        raise SkillOptError("pin needs an 'eval' surface (the eval.json manifest)")
    if not isinstance(model, str) or not model.strip():
        raise SkillOptError("pin needs --model, the model configuration the run uses")
    pinned: dict[str, Any] = {}
    for name, path in sorted(surfaces.items()):
        if not path.exists():
            raise SkillOptError(f"read-only surface {name!r} does not exist: {path}")
        pinned[name] = {"path": str(path.resolve()), "sha256": path_sha256(path)}
    return {"schema": PINS_SCHEMA, "model": model.strip(), "surfaces": pinned}


def check_pins(pins: Any, model: str | None = None) -> dict[str, Any]:
    """Recompute each pinned digest. Any change, or a different model, is a mismatch."""
    doc = _require_schema(pins, PINS_SCHEMA, "pins file")
    surfaces = doc.get("surfaces")
    if not isinstance(surfaces, dict) or "eval" not in surfaces:
        raise SkillOptError("pins file 'surfaces' must be an object with an 'eval' entry")
    changed: list[str] = []
    for name, entry in sorted(surfaces.items()):
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise SkillOptError(f"pins surface {name!r} must have a 'path' string")
        path = Path(entry["path"])
        if not path.exists() or path_sha256(path) != entry.get("sha256"):
            changed.append(name)
    model_changed = model is not None and model.strip() != doc.get("model")
    return {
        "verdict": "MISMATCH" if changed or model_changed else "MATCH",
        "changed_surfaces": changed,
        "model_changed": model_changed,
        "pinned_model": doc.get("model"),
    }


def assert_declared_pins(eval_path: Path, eval_set: dict[str, Any]) -> None:
    """When eval.json names a pins file, refuse to gate unless every pin still matches."""
    declared = eval_set.get("pins")
    if declared is None:
        return
    if not isinstance(declared, str) or not declared.strip():
        raise SkillOptError("eval set 'pins' must be a path string to a pins file")
    pins_path = (eval_path.parent / declared).resolve()
    if not pins_path.is_file():
        raise SkillOptError(f"eval set names pins file {declared!r}, which does not exist")
    pins = json.loads(pins_path.read_bytes().decode("utf-8"))
    report = check_pins(pins)
    pinned_eval = Path(pins["surfaces"]["eval"]["path"]).resolve()
    if pinned_eval != eval_path.resolve():
        raise SkillOptError(
            f"pins file pins eval set {pinned_eval}, not the one being gated "
            f"({eval_path.resolve()}); pin this run's files again"
        )
    if report["verdict"] != "MATCH":
        raise SkillOptError(
            "read-only surface changed since baseline: "
            f"{', '.join(report['changed_surfaces'])}; gains would not be attributable to the edit"
        )
