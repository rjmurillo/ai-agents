#!/usr/bin/env python3
"""Export an aggregate-only summary of a skill-doctor report.

Allowlist based: the export is built from named fields, each coerced to a plain
number or a short controlled string. Nothing is copied by walking the report,
so a new private field in report.json cannot leak by default. As a second
check, a deny set is derived from every private-looking value in the report
(paths, session ids, reasons, evidence, prompts, hashes, handles) and the
export is refused when any of them appears in it.

Exit codes: 0 written, 1 canary check failed or report invalid, 2 bad
arguments or unreadable input.

Python 3.10+, stdlib only.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import report_audit
import report_evaluation
from audit_scores import write_atomic
from render_report import GRADES, grade_for

NON_PROBABILITY_NOTE = (
    "Non-probability sample. Results are descriptive for the conversations scored "
    "and are not population estimates or evidence that skills caused outcomes."
)
MIN_SUBSTRING_LENGTH = 6
KNOWN_GRADES = frozenset(letter for _, letter in GRADES) | {"F"}

# Keys whose values (strings, or strings nested in lists and objects) are private.
PRIVATE_KEYS = frozenset(
    {
        "path",
        "paths",
        "aliases",
        "alias",
        "session_id",
        "session_ids",
        "excluded_session_ids",
        "reason",
        "reasons",
        "evidence",
        "evidence_ref",
        "excerpt",
        "diff",
        "proposed_path",
        "mechanism",
        "change",
        "reproduction",
        "handle",
        "url",
        "prompt",
        "payload",
        "sha256",
        "target",
        "baseline",
        "candidate",
        "expected_improvement",
        "acceptance_checks",
        "risks",
        "unresolved_because",
    }
)


class CanaryError(ValueError):
    """The export carries a value that the report marks private."""


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def _private_values(node: Any) -> Iterator[str]:
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key in PRIVATE_KEYS:
                yield from _strings(value)
            else:
                yield from _private_values(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _private_values(item)


def deny_set(report: Mapping[str, Any]) -> set[str]:
    """Every private value in the report, plus the handoff prompts built from it."""
    deny = {value for value in _private_values(report) if value.strip()}
    for suggestion in report.get("suggestions") or []:
        if isinstance(suggestion, dict):
            deny.add(report_evaluation.skillopt_prompt(suggestion))
            deny.add(report_evaluation.skillforge_prompt(suggestion))
    return deny


def find_canaries(export: Any, deny: set[str]) -> list[str]:
    """Deny values that appear in the export, as an exact value or a substring."""
    leaves = list(_strings(export)) + [k for k in _keys(export)]
    hits = []
    for secret in sorted(deny):
        long_enough = len(secret) >= MIN_SUBSTRING_LENGTH
        if any(leaf == secret or (long_enough and secret in leaf) for leaf in leaves):
            hits.append(secret)
    return hits


def _keys(node: Any) -> Iterator[str]:
    if isinstance(node, Mapping):
        for key, value in node.items():
            yield str(key)
            yield from _keys(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _keys(item)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    # NaN and Infinity are not JSON; a shared summary must parse anywhere.
    return number if math.isfinite(number) else None


def _count(value: Any) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _scores(report: Mapping[str, Any]) -> dict[str, float]:
    raw = report.get("scores") if isinstance(report.get("scores"), dict) else {}
    keys = [key for key, _ in report_audit.DIMENSIONS] + ["overall"]
    return {k: n for k in keys if (n := _number(raw.get(k))) is not None}


def _shortfalls(audit: Mapping[str, Any]) -> dict[str, Any]:
    artifact = audit.get("scores")
    if not isinstance(artifact, dict):
        return {}
    dims = artifact.get("dimensions") if isinstance(artifact.get("dimensions"), dict) else {}
    per_dim = {
        key: n
        for key, _ in report_audit.DIMENSIONS
        if (n := _number((dims.get(key) or {}).get("weighted_shortfall"))) is not None
    }
    out: dict[str, Any] = {"by_dimension": per_dim}
    total = _number(artifact.get("total_shortfall"))
    if total is not None:
        out["total"] = total
    return out


def _suggestion_counts(report: Mapping[str, Any]) -> dict[str, int]:
    counts = {status: 0 for status in report_evaluation.SUGGESTION_STATUSES}
    suggestions = report.get("suggestions")
    for suggestion in suggestions if isinstance(suggestions, list) else []:
        if not isinstance(suggestion, dict):
            continue
        status = report_evaluation.suggestion_status(suggestion)
        if status in counts:
            counts[status] += 1
    return counts


def _public_grade(report: Mapping[str, Any], overall: float) -> str:
    """A letter from the fixed grade scale. Any other text is refused, never exported."""
    grade = report.get("grade")
    if not isinstance(grade, str):
        return grade_for(overall)
    if grade not in KNOWN_GRADES:
        raise CanaryError("grade is not a letter on the grade scale; refusing to export its text")
    return str(grade)


def _public_evaluation_status(report: Mapping[str, Any]) -> str:
    """The status line from fixed vocabularies. Unrecognized evaluation text is refused."""
    evaluation = report_evaluation.evaluation_of(dict(report))
    if evaluation["diagnosis"] != "static" or (
        evaluation["optimization"] not in report_evaluation.OPTIMIZATION_STAGES
    ):
        raise CanaryError(
            "evaluation.diagnosis or evaluation.optimization is outside its fixed vocabulary; "
            "refusing to export its text"
        )
    suggestions = report.get("suggestions")
    safe = {
        "evaluation": {
            "diagnosis": evaluation["diagnosis"],
            "optimization": evaluation["optimization"],
        },
        "suggestions": [
            {"status": report_evaluation.suggestion_status(s)}
            for s in (suggestions if isinstance(suggestions, list) else [])
            if isinstance(s, dict)
        ],
    }
    return report_evaluation.evaluation_summary(safe)


def export_public(report: Mapping[str, Any]) -> dict[str, Any]:
    """Aggregate summary built only from allowlisted fields.

    Raises CanaryError when any value the report marks private appears in it.
    """
    stats = report.get("stats") if isinstance(report.get("stats"), dict) else {}
    audit = report_audit.audit_of(report)
    scores = _scores(report)
    export: dict[str, Any] = {
        "grade": _public_grade(report, scores.get("overall", 0.0)),
        "overall": scores.get("overall"),
        "scores": {k: v for k, v in scores.items() if k != "overall"},
        "weighted_shortfall": _shortfalls(audit),
        "counts": {
            "sessions_scored": _count(stats.get("sessions_analyzed")),
            "skills_found": _count(stats.get("skills_found")),
            "skills_used": _count(stats.get("skills_used")),
        },
        "evaluation_status": _public_evaluation_status(report),
        "suggestion_status_counts": _suggestion_counts(report),
        "sampling_note": NON_PROBABILITY_NOTE,
    }
    catalog = report_audit.catalog_counts(audit)
    if catalog is not None:
        export["counts"]["catalog"] = catalog
    hits = find_canaries(export, deny_set(report))
    if hits:
        raise CanaryError(f"export carries {len(hits)} private value(s); refusing to write")
    return export


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="Path to report.json")
    parser.add_argument("--out", required=True, help="Path of the public summary JSON to write")
    return parser


def _load(path: Path) -> Mapping[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        print(f"error: {path} is not a JSON object", file=sys.stderr)
        return None
    return data


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = _load(Path(args.report).expanduser())
    if report is None:
        return 2
    try:
        export = export_public(report)
    except CanaryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        out = Path(args.out).expanduser()
        if not out.parent.is_dir():
            raise OSError(f"directory does not exist: {out.parent}")
        write_atomic(out, export)
    except OSError as exc:
        print(f"error: cannot write {args.out}: {exc}", file=sys.stderr)
        return 2
    print(f"public summary: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
