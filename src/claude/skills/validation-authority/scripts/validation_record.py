#!/usr/bin/env python3
"""Validate the provenance/authority decision record before ``/build`` Phase 3.

`/build` Phase 2b composes `analysis-provenance` then `validation-authority`
whenever `validation_trigger.py` (the sibling `build` skill's script) decides
a change can alter validation semantics. `validation-authority` writes one
JSON decision record naming, for every validation target, who owns it, what
category of code it is, and the single location Phase 3 may edit. This script
checks that record before Phase 3 touches anything, and again whenever `/test`
Gate 4 receives the record path.

The script is a pure function of the record and, optionally, the current
changed-path list, so the same inputs always get the same result. It opens no
network connection and starts no subprocess.

Record shape (REQ-041 data model)::

    {
      "trigger": <the validation_trigger.py output, opaque here>,
      "targets": [
        {
          "target": "<path>",
          "component": "<human label>",
          "provenance": {
            "category": "LOCAL|GENERATED|VENDOR|UPSTREAM|UNKNOWN",
            "owner": "<non-empty>",
            "evidence": "<non-empty>",
            "canonical_source": "<required when category is GENERATED>"
          },
          "authority": {
            "contract": "<non-empty>",
            "diagnosis": "implementation-defect|local-config-defect|
                          stale-generated-output|baseline-update|
                          upstream-defect|unknown",
            "permitted_change_location": "<non-empty>",
            "escalation": "<required when diagnosis is upstream-defect>"
          },
          "baseline_justification": {   // required when diagnosis is baseline-update
            "policy_source": "<path that must exist on disk>",
            "reason": "<non-empty>",
            "added_entries": [{"justification": "<non-empty>", ...}]
          }
        }
      ]
    }

EXIT CODES (ADR-035):
    0 - The record passed. A JSON summary is on stdout.
    1 - The record has defects. The JSON summary lists them.
    2 - Config error: a file is unreadable, the record is not valid JSON, the
        sibling trigger module could not be loaded when a `--changed-path`
        needed it, or the arguments are bad.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

CATEGORIES = ("LOCAL", "GENERATED", "VENDOR", "UPSTREAM", "UNKNOWN")
DIAGNOSES = (
    "implementation-defect",
    "local-config-defect",
    "stale-generated-output",
    "baseline-update",
    "upstream-defect",
    "unknown",
)
TOP_LEVEL_KEYS = ("trigger", "targets")
TARGET_KEYS = ("target", "component", "provenance", "authority")

_UNKNOWN_MESSAGE = "stop semantic edits and request ownership evidence"
_TRIGGER_RELATIVE = Path("build") / "scripts" / "validation_trigger.py"


def _text(value: object) -> bool:
    """Return True when value is a string with non-space content."""
    return isinstance(value, str) and bool(value.strip())


def _path_key(path: object) -> str:
    """Return one spelling for a path: forward slashes, no empty or ``.`` segments.

    Matches ``normalize_path`` in the sibling trigger, so ``./a/b.py`` and
    ``a\\b.py`` name the same target here and there.
    """
    parts = str(path).replace("\\", "/").strip().split("/")
    return "/".join(part for part in parts if part and part != ".")


def load_trigger(path: Path | None = None) -> ModuleType:
    """Load the sibling ``build`` skill's ``validation_trigger`` module.

    Both skills ship in the same ``skills/`` directory of every plugin root,
    so the sibling path resolves in the source tree and in a vendored
    install, mirroring how ``test``'s ``dx_trigger.py`` loads ``review``'s
    ``select_axes.py``.
    """
    target = path or Path(__file__).resolve().parents[2] / _TRIGGER_RELATIVE
    if not target.is_file():
        raise FileNotFoundError(f"validation trigger not found: {target}")
    spec = importlib.util.spec_from_file_location("validation_record_trigger", target)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load validation trigger: {target}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _provenance_defects(where: str, provenance: object) -> list[str]:
    """Check `provenance.category`, `owner`, and `evidence`."""
    if not isinstance(provenance, dict):
        return [f"{where}: `provenance` must be an object"]
    defects: list[str] = []
    category = provenance.get("category")
    if category not in CATEGORIES:
        defects.append(f"{where}: provenance.category must be one of {', '.join(CATEGORIES)}")
    if not _text(provenance.get("owner")):
        defects.append(f"{where}: provenance.owner must be a non-empty string")
    if not _text(provenance.get("evidence")):
        defects.append(f"{where}: provenance.evidence must be a non-empty string")
    if category == "UNKNOWN":
        defects.append(f"{where}: UNKNOWN provenance is blocking; {_UNKNOWN_MESSAGE}")
    return defects


def _authority_defects(where: str, authority: object) -> list[str]:
    """Check `authority.diagnosis`, `contract`, and `permitted_change_location`."""
    if not isinstance(authority, dict):
        return [f"{where}: `authority` must be an object"]
    defects: list[str] = []
    diagnosis = authority.get("diagnosis")
    if diagnosis not in DIAGNOSES:
        defects.append(f"{where}: authority.diagnosis must be one of {', '.join(DIAGNOSES)}")
    if not _text(authority.get("contract")):
        defects.append(f"{where}: authority.contract must be a non-empty string")
    if not _text(authority.get("permitted_change_location")):
        defects.append(f"{where}: authority.permitted_change_location must be a non-empty string")
    if diagnosis == "unknown":
        defects.append(f"{where}: unknown diagnosis is blocking; {_UNKNOWN_MESSAGE}")
    if diagnosis == "upstream-defect" and not _text(authority.get("escalation")):
        defects.append(
            f"{where}: authority.escalation must be a non-empty string for upstream-defect"
        )
    return defects


def _generated_defects(
    where: str, provenance: dict[str, Any], authority: dict[str, Any]
) -> list[str]:
    """Check that a GENERATED target names and points at its canonical source."""
    canonical_source = provenance.get("canonical_source")
    if not _text(canonical_source):
        return [f"{where}: GENERATED provenance needs a non-empty provenance.canonical_source"]
    permitted = authority.get("permitted_change_location")
    if _path_key(permitted) != _path_key(canonical_source):
        return [
            f"{where}: GENERATED authority.permitted_change_location must equal "
            f"provenance.canonical_source ({canonical_source!r}), got {permitted!r}"
        ]
    return []


def _vendor_or_upstream_defects(
    where: str, target_path: str, authority: dict[str, Any]
) -> list[str]:
    """Check that a VENDOR or UPSTREAM target is not itself the edit location."""
    permitted = authority.get("permitted_change_location")
    if _path_key(permitted) == _path_key(target_path):
        return [
            f"{where}: authority.permitted_change_location must not equal the target "
            f"({target_path!r}) for a VENDOR or UPSTREAM target"
        ]
    return []


def _policy_source_defect(where: str, policy_source: object, repo_root: Path | None) -> list[str]:
    if not _text(policy_source):
        return [f"{where}: baseline_justification.policy_source must be a non-empty string"]
    base = (repo_root or Path.cwd()).resolve()
    candidate = (base / str(policy_source)).resolve()
    if Path(str(policy_source)).is_absolute() or not candidate.is_relative_to(base):
        return [
            f"{where}: baseline_justification.policy_source must be a relative path "
            f"inside the repository: {policy_source!r}"
        ]
    if not candidate.exists():
        return [f"{where}: baseline_justification.policy_source does not exist: {policy_source!r}"]
    return []


def _added_entry_defects(where: str, entries: object) -> list[str]:
    if not isinstance(entries, list):
        return [f"{where}: baseline_justification.added_entries must be a list"]
    defects: list[str] = []
    for index, entry in enumerate(entries):
        entry_where = f"{where}.added_entries[{index}]"
        if not isinstance(entry, dict) or not _text(entry.get("justification")):
            defects.append(f"{entry_where}: needs a non-empty `justification`")
    return defects


def _baseline_defects(where: str, target: dict[str, Any], repo_root: Path | None) -> list[str]:
    """Check the `baseline_justification` block required for a baseline-update."""
    justification = target.get("baseline_justification")
    if not isinstance(justification, dict):
        return [f"{where}: baseline-update diagnosis needs a `baseline_justification` object"]
    defects = _policy_source_defect(where, justification.get("policy_source"), repo_root)
    if not _text(justification.get("reason")):
        defects.append(f"{where}: baseline_justification.reason must be a non-empty string")
    defects += _added_entry_defects(where, justification.get("added_entries"))
    return defects


def _target_defects(index: int, target: object, repo_root: Path | None) -> list[str]:
    """Return every defect for one target entry."""
    where = f"targets[{index}]"
    if not isinstance(target, dict):
        return [f"{where}: each target must be an object"]
    missing = [key for key in TARGET_KEYS if key not in target]
    if missing:
        return [f"{where}: missing `{key}`" for key in missing]
    defects: list[str] = []
    if not _text(target.get("target")):
        defects.append(f"{where}: `target` must be a non-empty string")
    if not _text(target.get("component")):
        defects.append(f"{where}: `component` must be a non-empty string")
    provenance = target["provenance"]
    authority = target["authority"]
    defects += _provenance_defects(where, provenance)
    defects += _authority_defects(where, authority)
    if defects or not isinstance(provenance, dict) or not isinstance(authority, dict):
        return defects
    category = provenance.get("category")
    diagnosis = authority.get("diagnosis")
    if category == "GENERATED":
        defects += _generated_defects(where, provenance, authority)
    if category in ("VENDOR", "UPSTREAM"):
        defects += _vendor_or_upstream_defects(where, str(target.get("target")), authority)
    if diagnosis == "baseline-update":
        defects += _baseline_defects(where, target, repo_root)
    return defects


def _flagged_by_trigger(
    changed_paths: Sequence[str], repo_root: Path, trigger_module: ModuleType
) -> list[str]:
    """Return every changed path the trigger's path cues alone would flag."""
    roots = trigger_module.resolve_generated_roots(repo_root)
    return [
        _path_key(path)
        for path in changed_paths
        if trigger_module.is_validation_target(path, repo_root, roots)
    ]


def _coverage_defects(
    valid_targets: list[dict[str, Any]],
    changed_paths: Sequence[str],
    repo_root: Path | None,
    trigger_module: ModuleType | None,
) -> list[str]:
    """Rule 8: reconcile the record's targets against the changed-path list."""
    if not changed_paths:
        return []
    defects: list[str] = []
    by_path = {_path_key(t["target"]): t for t in valid_targets}
    if trigger_module is not None:
        flagged = _flagged_by_trigger(changed_paths, repo_root or Path.cwd(), trigger_module)
        for path in flagged:
            if path not in by_path:
                defects.append(
                    f"changed path {path!r} matches a validation cue but has no record target"
                )
    changed_set = {_path_key(path) for path in changed_paths}
    for target in valid_targets:
        category = target["provenance"].get("category")
        path = _path_key(target["target"])
        if category in ("VENDOR", "UPSTREAM") and path in changed_set:
            defects.append(
                f"targets: {path!r} is VENDOR or UPSTREAM and must not be a changed path"
            )
        if category == "GENERATED" and path in changed_set:
            canonical = target["provenance"].get("canonical_source")
            if _path_key(canonical) not in changed_set:
                defects.append(
                    f"targets: {path!r} is GENERATED and was changed; its canonical source "
                    f"{canonical!r} must be changed too, not edited as a standalone mirror"
                )
    return defects


def _trigger_defects(trigger: object, targets: list[Any]) -> list[str]:
    """An activated trigger needs a record target for each path it named."""
    if not isinstance(trigger, dict):
        return ["`trigger` must be the validation_trigger.py JSON object"]
    decision = trigger.get("decision")
    if decision not in ("activate", "skip"):
        return ["trigger.decision must be `activate` or `skip`"]
    if decision == "skip":
        if trigger.get("effects") or trigger.get("targets"):
            return ["trigger.decision `skip` contradicts its listed effects or targets"]
        return []
    if not targets:
        return ["the trigger activated but the record has no targets; record each target"]
    recorded = {_path_key(t.get("target")) for t in targets if isinstance(t, dict)}
    named = trigger.get("targets")
    named = named if isinstance(named, list) else []
    paths = [_path_key(t["path"]) for t in named if isinstance(t, dict) and _text(t.get("path"))]
    return [
        f"trigger target {path!r} has no record target"
        for path in sorted(set(paths))
        if path not in recorded
    ]


def validate(
    record: Any,
    changed_paths: Sequence[str] = (),
    repo_root: Path | None = None,
    trigger_module: ModuleType | None = None,
) -> list[str]:
    """Return every record defect. An empty list means the record passed."""
    if not isinstance(record, dict):
        return ["record must be a JSON object"]
    missing = [key for key in TOP_LEVEL_KEYS if key not in record]
    if missing:
        return [f"record is missing `{key}`" for key in missing]
    targets = record["targets"]
    if not isinstance(targets, list):
        return ["`targets` must be a list"]
    defects = _trigger_defects(record["trigger"], targets)
    valid_targets: list[dict[str, Any]] = []
    for index, target in enumerate(targets):
        target_defects = _target_defects(index, target, repo_root)
        defects += target_defects
        if not target_defects:
            valid_targets.append(target)
    defects += _coverage_defects(valid_targets, changed_paths, repo_root, trigger_module)
    return defects


def _summary(record: object, defects: list[str], record_path: Path) -> dict[str, Any]:
    """Build the stdout summary for a validated record."""
    data = record if isinstance(record, dict) else {}
    targets = data.get("targets")
    targets = targets if isinstance(targets, list) else []
    categories = Counter(
        str(t["provenance"].get("category"))
        for t in targets
        if isinstance(t, dict) and isinstance(t.get("provenance"), dict)
    )
    return {
        "ok": not defects,
        "record": str(record_path),
        "targets": len(targets),
        "categories": dict(sorted(categories.items())),
        "defects": defects,
    }


def _read(path: Path) -> str:
    """Read a UTF-8 file, raising OSError with the path on failure."""
    return path.read_text(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the record named on the command line and print a summary."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--record", type=Path, required=True, help="decision record JSON")
    parser.add_argument(
        "--changed-path",
        action="append",
        default=[],
        metavar="PATH",
        help="A path from the current changed-path list. Repeatable.",
    )
    parser.add_argument("--repo-root", type=Path, default=None, help="Repository root override.")
    parser.add_argument(
        "--trigger", type=Path, default=None, help="Path to validation_trigger.py override."
    )
    args = parser.parse_args(argv)
    try:
        raw = _read(args.record)
    except OSError as exc:
        print(f"cannot read input: {exc}", file=sys.stderr)
        return 2
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"{args.record}: not valid JSON: {exc}", file=sys.stderr)
        return 2
    trigger_module: ModuleType | None = None
    if args.changed_path:
        try:
            trigger_module = load_trigger(args.trigger)
        except (OSError, ImportError) as exc:
            print(f"validation_record: cannot load sibling trigger: {exc}", file=sys.stderr)
            return 2
    defects = validate(record, args.changed_path, args.repo_root, trigger_module)
    print(json.dumps(_summary(record, defects, args.record), sort_keys=True))
    return 1 if defects else 0


if __name__ == "__main__":
    sys.exit(main())
