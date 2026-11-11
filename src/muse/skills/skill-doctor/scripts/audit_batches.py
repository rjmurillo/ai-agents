"""Immutable review assignments and all-or-nothing score imports.

``assign`` turns a collector inventory into batches of sampled session identifiers,
each bound to a source digest. ``import`` checks one batch of score rows against its
assignment, then replaces the accepted-scores file atomically. Any rejected batch
leaves the last accepted file byte-for-byte unchanged.

Python 3.10+, stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import audit_scores

ASSIGNMENT_VERSION = 1
MANIFEST_FILENAME = "assignment.json"
DEFAULT_STRATUM = "skill_first"
NON_PROBABILITY_NOTE = (
    "Not a probability sample. Selected sessions are not representative of the population."
)
_STRATUM_ORDER = (DEFAULT_STRATUM, "timeline_supplement")


class ImportRejectedError(ValueError):
    """Raised when incoming rows or inputs fail validation. ``errors`` lists every reason."""

    def __init__(self, errors: Sequence[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = list(errors)


def _digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def session_key(session: Mapping[str, Any]) -> str:
    """Identifier used by the sampler: ``<harness>:<meta.id>``."""
    return f"{session['harness']}:{session['meta']['id']}"


def _sampled_by_stratum(inventory: Mapping[str, Any]) -> dict[str, list[str]]:
    sessions = inventory.get("sessions")
    if not isinstance(sessions, list):
        raise ImportRejectedError(["inventory has no sessions list"])
    strata: dict[str, list[str]] = {}
    for session in sessions:
        if session.get("sampled"):
            strata.setdefault(session.get("stratum") or DEFAULT_STRATUM, []).append(
                session_key(session)
            )
    return {name: sorted(keys) for name, keys in strata.items()}


def _ordered_strata(names: Sequence[str]) -> list[str]:
    known = [name for name in _STRATUM_ORDER if name in names]
    return known + sorted(set(names) - set(known))


def source_digest(
    inventory: Mapping[str, Any], audit_manifest: Mapping[str, Any] | None = None
) -> str:
    """Digest of sampled identifiers by stratum and the sampling block.

    Excludes ``generated_at``. When an audit manifest is supplied its M1 fingerprint is
    included, so a changed scope or catalog also changes the digest.
    """
    fingerprint = audit_manifest.get("fingerprint") if audit_manifest else None
    return _digest(
        {
            "strata": _sampled_by_stratum(inventory),
            "sampling": inventory.get("sampling", {}),
            "manifest_fingerprint": fingerprint,
        }
    )


def _stratum_details(inventory: Mapping[str, Any], stratum: str) -> dict[str, Any]:
    sampling = inventory.get("sampling", {})
    declared = sampling.get("strata", {}).get(stratum)
    if declared:
        cap = sampling.get("timeline_supplement", {}).get("requested")
        return {
            "candidate_count": declared["candidates"],
            "cap": cap if stratum == "timeline_supplement" else sampling.get("max_sessions"),
            "selection_rule": declared["rule"],
        }
    rule = f"{sampling.get('rule', '')} {sampling.get('within_harness', '')}".strip()
    return {
        "candidate_count": inventory.get("stats", {}).get("sessions_considered"),
        "cap": sampling.get("max_sessions"),
        "selection_rule": rule,
    }


def _batch_id(digest: str, stratum: str, ids: Sequence[str], number: int) -> str:
    return f"batch-{number:03d}-{_digest([digest, stratum, list(ids)])[:12]}"


def build_assignment(
    inventory: Mapping[str, Any],
    batch_size: int,
    audit_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Split the sampled sessions into immutable batches. Same inputs give the same output."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    digest = source_digest(inventory, audit_manifest)
    strata = _sampled_by_stratum(inventory)
    batches: list[dict[str, Any]] = []
    for stratum in _ordered_strata(list(strata)):
        ids = strata[stratum]
        for start in range(0, len(ids), batch_size):
            chunk = ids[start : start + batch_size]
            batches.append(
                {
                    "assignment_version": ASSIGNMENT_VERSION,
                    "batch_id": _batch_id(digest, stratum, chunk, len(batches) + 1),
                    "source_digest": digest,
                    "stratum": stratum,
                    **_stratum_details(inventory, stratum),
                    "representative": False,
                    "non_probability_note": NON_PROBABILITY_NOTE,
                    "session_ids": chunk,
                }
            )
    return {
        "assignment_version": ASSIGNMENT_VERSION,
        "source_digest": digest,
        "batch_size": batch_size,
        "total_sessions": sum(len(ids) for ids in strata.values()),
        "batches": batches,
    }


def _dump(data: Mapping[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def write_assignment_dir(assignment: Mapping[str, Any], out: Path) -> list[Path]:
    """Write the manifest and one file per batch. Refuses to overwrite different content."""
    files = {MANIFEST_FILENAME: _dump(assignment)}
    for batch in assignment["batches"]:
        files[f"{batch['batch_id']}.json"] = _dump(batch)
    for name, text in files.items():
        existing = out / name
        if existing.exists() and existing.read_text(encoding="utf-8") != text:
            raise ImportRejectedError(
                [f"{existing} exists with different content; assignments are immutable"]
            )
    written = []
    for name, text in files.items():
        audit_scores.write_atomic(out / name, json.loads(text))
        written.append(out / name)
    return written


def _is_count(value: Any) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 0)


def _sampling_metadata_errors(assignment: Mapping[str, Any]) -> list[str]:
    """A batch must say how it was selected and that it is not a probability sample."""
    errors = []
    if assignment.get("representative") is not False:
        errors.append("assignment must declare representative: false (non-probability sample)")
    note = assignment.get("non_probability_note")
    if not isinstance(note, str) or not note.strip():
        errors.append("assignment is missing its non_probability_note")
    rule = assignment.get("selection_rule")
    if not isinstance(rule, str) or not rule.strip():
        errors.append("assignment is missing its selection_rule")
    for key in ("candidate_count", "cap"):
        if key not in assignment or not _is_count(assignment[key]):
            errors.append(f"assignment {key} must be present as a non-negative integer or null")
    return errors


def _check_assignment(assignment: Any) -> list[str]:
    required = ("batch_id", "source_digest", "stratum", "session_ids")
    if not isinstance(assignment, dict) or any(key not in assignment for key in required):
        return [f"assignment must be an object with {', '.join(required)}"]
    ids = assignment["session_ids"]
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        return ["assignment session_ids must be a list of strings"]
    number = _number_from(assignment["batch_id"])
    expected = _batch_id(assignment["source_digest"], assignment["stratum"], ids, number)
    if number < 1 or assignment["batch_id"] != expected:
        return ["assignment batch_id does not match its contents; the assignment was altered"]
    return _sampling_metadata_errors(assignment)


def _number_from(batch_id: Any) -> int:
    parts = str(batch_id).split("-")
    return int(parts[1]) if len(parts) == 3 and parts[1].isdigit() else 0


def _identity_errors(
    assignment: Mapping[str, Any], index: int, row: Mapping[str, Any]
) -> list[str]:
    where = f"rows[{index}] {row.get('session_id')!r}"
    errors = []
    if row.get("batch_id") != assignment["batch_id"]:
        errors.append(f"{where}: foreign assignment, batch_id {row.get('batch_id')!r}")
    if row.get("source_digest") != assignment["source_digest"]:
        errors.append(f"{where}: foreign assignment, source_digest does not match")
    if row.get("stratum", assignment["stratum"]) != assignment["stratum"]:
        errors.append(f"{where}: foreign assignment, stratum {row.get('stratum')!r}")
    return errors


def _membership_errors(assigned: Sequence[str], rows: Sequence[Any]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        sid = row.get("session_id") if isinstance(row, dict) else None
        if not isinstance(sid, str) or not sid.strip():
            errors.append(f"rows[{index}]: malformed, session_id must be a non-empty string")
        elif sid in seen:
            errors.append(f"duplicate session_id {sid!r}")
        elif sid not in assigned:
            errors.append(f"extra session_id {sid!r} is not in this batch")
        if isinstance(sid, str):
            seen.add(sid)
    errors.extend(f"missing session_id {sid!r}" for sid in assigned if sid not in seen)
    return errors


def validate_rows(
    assignment: Mapping[str, Any],
    rows: Any,
    tables: Mapping[str, Mapping[str, float]] | None = None,
) -> list[str]:
    """Every reason the rows cannot be accepted for this batch. Empty list means valid."""
    errors = _check_assignment(assignment)
    if errors:
        return errors
    if not isinstance(rows, list):
        return ["rows must be a list of score objects"]
    tables = tables or audit_scores.load_label_tables()
    errors = _membership_errors(assignment["session_ids"], rows)
    for index, row in enumerate(rows):
        if isinstance(row, dict):
            errors.extend(_identity_errors(assignment, index, row))
        errors.extend(audit_scores.validate_session(row, tables, index))
    return errors


def load_accepted(path: Path, digest: str) -> list[dict[str, Any]]:
    """Rows already accepted for this digest. Raises ImportRejectedError on stale or corrupt files."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportRejectedError([f"accepted file {path} is unreadable: {exc}"]) from exc
    if not isinstance(data, dict) or not isinstance(data.get("sessions"), list):
        raise ImportRejectedError([f"accepted file {path} is not an accepted-scores object"])
    if data.get("source_digest") != digest:
        raise ImportRejectedError(
            [
                f"stale assignment: accepted file digest {data.get('source_digest')!r} differs "
                f"from assignment digest {digest!r}; create a new assignment and a new accepted file"
            ]
        )
    return [dict(row) for row in data["sessions"]]


def import_scores(
    assignment: Mapping[str, Any],
    accepted_path: Path,
    incoming_rows: Any,
    tables: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, Any]:
    """Validate one batch, then atomically replace the accepted file.

    Raises ImportRejectedError before any write when validation fails. A failed replace
    raises OSError and leaves the previous accepted file in place. Re-importing a
    batch replaces that batch's rows, so no record is counted twice. Provider
    termination (``terminated_by``) is stored as given.
    """
    errors = validate_rows(assignment, incoming_rows, tables)
    if errors:
        raise ImportRejectedError(errors)
    assigned = set(assignment["session_ids"])
    kept = [
        row
        for row in load_accepted(accepted_path, assignment["source_digest"])
        if row.get("session_id") not in assigned
    ]
    merged = sorted(kept + list(incoming_rows), key=lambda row: row["session_id"])
    audit_scores.write_atomic(
        accepted_path, {"source_digest": assignment["source_digest"], "sessions": merged}
    )
    return {
        "batch_id": assignment["batch_id"],
        "accepted": len(incoming_rows),
        "total": len(merged),
    }


def unscored_ids(manifest: Mapping[str, Any], accepted_path: Path) -> list[str]:
    """Assigned identifiers that have no accepted score yet."""
    accepted = {
        row["session_id"] for row in load_accepted(accepted_path, manifest["source_digest"])
    }
    return [
        sid for batch in manifest["batches"] for sid in batch["session_ids"] if sid not in accepted
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build review assignments and import scores.")
    sub = parser.add_subparsers(dest="command", required=True)
    assign = sub.add_parser("assign", help="write assignment manifests from an inventory")
    assign.add_argument("inventory", type=Path)
    assign.add_argument("--batch-size", type=int, required=True)
    assign.add_argument("--out", type=Path, required=True)
    assign.add_argument("--audit-manifest", type=Path, default=None)
    imp = sub.add_parser("import", help="validate and accept one batch of score rows")
    imp.add_argument("assignment", type=Path)
    imp.add_argument("rows", type=Path)
    imp.add_argument("--accepted", type=Path, required=True)
    return parser


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_assign(args: argparse.Namespace) -> int:
    if args.batch_size < 1:
        print("error: --batch-size must be at least 1", file=sys.stderr)
        return 2
    inventory = _read_json(args.inventory)
    manifest = _read_json(args.audit_manifest) if args.audit_manifest else None
    assignment = build_assignment(inventory, args.batch_size, manifest)
    write_assignment_dir(assignment, args.out)
    print(f"{len(assignment['batches'])} batches, {assignment['total_sessions']} sessions")
    return 0


def _run_import(args: argparse.Namespace) -> int:
    assignment = _read_json(args.assignment)
    payload = _read_json(args.rows)
    rows = payload.get("sessions") if isinstance(payload, dict) else payload
    summary = import_scores(assignment, args.accepted, rows)
    print(
        f"accepted {summary['accepted']} rows for {summary['batch_id']}; total {summary['total']}"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry. Exit 0 ok, 1 validation failure (nothing written), 2 bad arguments or I/O."""
    try:
        args = _parser().parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        return 2 if exc.code not in (0, None) else 0
    try:
        return _run_assign(args) if args.command == "assign" else _run_import(args)
    except ImportRejectedError as exc:
        for error in exc.errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, audit_scores.ScoreInputError) as exc:
        print(f"error: cannot read or write files: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
