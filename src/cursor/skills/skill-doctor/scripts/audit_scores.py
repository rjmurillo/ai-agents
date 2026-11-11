"""Validate scored sessions and aggregate them into a recomputable score artifact.

Executes SKILL.md Step 3 over a scores file. Label tables are parsed at runtime
from ``scorers/*.md`` so the numeric values cannot drift from the rubrics.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCORERS_DIR = SKILL_ROOT / "scorers"
SCHEMA_VERSION = 1

# scorer key in the scores file -> rubric file stem
SCORER_FILES: dict[str, str] = {
    "efficiency": "efficiency",
    "code_quality": "code-quality",
    "procedure_compliance": "procedure-compliance",
    "verbosity": "verbosity",
}
INSUFFICIENT = "insufficient_evidence"
WEIGHTS: dict[str, float] = {
    "efficiency": 0.25,
    "code_quality": 0.25,
    "procedure_compliance": 0.2,
    "verbosity": 0.15,
    "skill_coverage": 0.15,
}
QUALITY_FALLBACK_RAW = 0.5
FAIL_THRESHOLD = 0.5
SCORE_TOLERANCE = 1e-9
QUALITY_LIMIT_NOTE = (
    "No applicable code-quality evidence; raw 0.5 is a neutral fallback, not a measured result."
)

_VALUE_RE = re.compile(r'^\s*-\s*value:\s*"?([A-Za-z0-9_]+)"?\s*$')
_SCORE_RE = re.compile(r"^\s*score:\s*([0-9]*\.?[0-9]+)\s*$")


class ScoreInputError(ValueError):
    """Raised for unusable rubric files."""


def load_label_table(rubric_path: Path) -> dict[str, float]:
    """Parse ``labels:`` value/score pairs from a scorer markdown frontmatter."""
    lines = rubric_path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ScoreInputError(f"{rubric_path.name}: missing frontmatter")
    table: dict[str, float] = {}
    current: str | None = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        value = _VALUE_RE.match(line)
        if value:
            current = value.group(1)
            continue
        score = _SCORE_RE.match(line)
        if score and current is not None:
            table[current] = float(score.group(1))
            current = None
    if not table:
        raise ScoreInputError(f"{rubric_path.name}: no label table found")
    return table


def load_label_tables(scorers_dir: Path = SCORERS_DIR) -> dict[str, dict[str, float]]:
    """Return ``{scorer: {label: value}}`` for all four rubrics."""
    return {key: load_label_table(scorers_dir / f"{stem}.md") for key, stem in SCORER_FILES.items()}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _applicability_errors(where: str, result: Mapping[str, Any], label: Any) -> list[str]:
    applicable = result.get("applicable", label != INSUFFICIENT)
    if not isinstance(applicable, bool):
        return [f"{where}: applicable must be a boolean"]
    if label == INSUFFICIENT and applicable:
        return [f"{where}: insufficient_evidence must have applicable=false"]
    if label != INSUFFICIENT and not applicable and label is not None:
        return [f"{where}: label {label!r} is a judged result and must have applicable=true"]
    return []


def _validate_result(sid: str, scorer: str, result: Any, table: Mapping[str, float]) -> list[str]:
    where = f"session {sid!r} scorer {scorer}"
    if not isinstance(result, dict):
        return [f"{where}: result must be an object"]
    errors: list[str] = []
    label = result.get("label")
    if label not in table:
        errors.append(f"{where}: unknown label {label!r} (known: {sorted(table)})")
    elif not _is_number(result.get("score")):
        errors.append(f"{where}: score must be a number")
    elif not math.isclose(result["score"], table[label], abs_tol=SCORE_TOLERANCE):
        errors.append(
            f"{where}: label {label!r} requires score {table[label]}, got {result['score']}"
        )
    reason = result.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        errors.append(f"{where}: reason must be a non-empty string")
    ref = result.get("evidence_ref")
    if ref is not None and not isinstance(ref, str):
        errors.append(f"{where}: evidence_ref must be a string when present")
    errors.extend(_applicability_errors(where, result, label))
    pre = result.get("pre_cutoff")
    if pre is not None and not isinstance(pre, bool):
        errors.append(f"{where}: pre_cutoff must be a boolean when present")
    return errors


def _validate_header(sid: str, session: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(session.get("harness"), str) or not session["harness"].strip():
        errors.append(f"session {sid!r}: harness must be a non-empty string")
    stratum = session.get("stratum")
    if stratum is not None and not isinstance(stratum, str):
        errors.append(f"session {sid!r}: stratum must be a string when present")
    if not isinstance(session.get("skills_detected"), bool):
        errors.append(f"session {sid!r}: skills_detected must be a boolean")
    term = session.get("terminated_by")
    if term is not None and not isinstance(term, str):
        errors.append(f"session {sid!r}: terminated_by must be a string when present")
    lims = session.get("limitations", [])
    if not isinstance(lims, list) or not all(isinstance(x, str) for x in lims):
        errors.append(f"session {sid!r}: limitations must be a list of strings")
    return errors


def validate_session(
    session: Any, tables: Mapping[str, Mapping[str, float]], index: int
) -> list[str]:
    """Return validation errors for one session record."""
    if not isinstance(session, dict):
        return [f"sessions[{index}]: must be an object"]
    sid = session.get("session_id")
    if not isinstance(sid, str) or not sid.strip():
        return [f"sessions[{index}]: session_id must be a non-empty string"]
    errors = _validate_header(sid, session)
    scores = session.get("scores")
    if not isinstance(scores, dict):
        return errors + [f"session {sid!r}: scores must be an object"]
    for scorer, table in tables.items():
        if scorer not in scores:
            errors.append(f"session {sid!r}: missing scorer {scorer}")
        else:
            errors.extend(_validate_result(sid, scorer, scores[scorer], table))
    for extra in sorted(set(scores) - set(tables)):
        errors.append(f"session {sid!r}: unknown scorer {extra}")
    return errors


def validate_sessions(
    sessions: Any, tables: Mapping[str, Mapping[str, float]] | None = None
) -> list[str]:
    """Validate every session record and report duplicate ids. Empty list means valid."""
    tables = tables or load_label_tables()
    if not isinstance(sessions, list) or not sessions:
        return ["sessions must be a non-empty list"]
    errors: list[str] = []
    seen: set[str] = set()
    for i, session in enumerate(sessions):
        errors.extend(validate_session(session, tables, i))
        sid = session.get("session_id") if isinstance(session, dict) else None
        if isinstance(sid, str):
            if sid in seen:
                errors.append(f"duplicate session_id {sid!r}")
            seen.add(sid)
    return errors


def _is_applicable(result: Mapping[str, Any]) -> bool:
    return bool(result.get("applicable", result["label"] != INSUFFICIENT))


def curve(raw: float) -> float:
    """SKILL.md Step 3 curve."""
    return 0.5 + 0.5 * raw


def _dimension(sessions: Sequence[Mapping[str, Any]], scorer: str) -> dict[str, Any]:
    scores = [
        float(s["scores"][scorer]["score"]) for s in sessions if _is_applicable(s["scores"][scorer])
    ]
    numerator = math.fsum(scores)
    denominator = len(scores)
    fallback = denominator == 0
    raw = QUALITY_FALLBACK_RAW if fallback else numerator / denominator
    score = curve(raw)
    dim: dict[str, Any] = {
        "numerator": numerator,
        "denominator": denominator,
        "inapplicable": len(sessions) - denominator,
        "raw": raw,
        "score": score,
        "weight": WEIGHTS[scorer],
        "weighted_shortfall": 100 * WEIGHTS[scorer] * (1 - score),
        "fallback_used": fallback,
    }
    if fallback:
        dim["evidence_limit"] = QUALITY_LIMIT_NOTE
    return dim


def _coverage(sessions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    detected = sum(1 for s in sessions if s["skills_detected"])
    total = len(sessions)
    score = detected / total if total else 0.0
    return {
        "numerator": detected,
        "denominator": total,
        "inapplicable": 0,
        "raw": score,
        "score": score,
        "weight": WEIGHTS["skill_coverage"],
        "weighted_shortfall": 100 * WEIGHTS["skill_coverage"] * (1 - score),
        "fallback_used": False,
    }


def _low_scorers(session: Mapping[str, Any]) -> list[str]:
    """Scorers with an applicable raw score below the failure threshold."""
    return [
        k
        for k in SCORER_FILES
        if _is_applicable(session["scores"][k])
        and float(session["scores"][k]["score"]) < FAIL_THRESHOLD
    ]


def _counts_as_failure(session: Mapping[str, Any], scorer: str) -> bool:
    """A low result counts unless the session was cut off and it lacks pre_cutoff evidence.

    ``pre_cutoff`` defaults to true when ``terminated_by`` is unset and to
    false when it is set.
    """
    if not session.get("terminated_by"):
        return True
    return session["scores"][scorer].get("pre_cutoff", False) is True


def failed_conversations(sessions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Apply the Step 3 failure filter and count termination-only exclusions."""
    failed: list[str] = []
    excluded: list[str] = []
    for s in sessions:
        low = _low_scorers(s)
        if not low:
            continue
        if any(_counts_as_failure(s, k) for k in low):
            failed.append(s["session_id"])
        else:
            excluded.append(s["session_id"])
    return {
        "count": len(failed),
        "session_ids": failed,
        "excluded_count": len(excluded),
        "excluded_session_ids": excluded,
    }


def aggregate(sessions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate validated sessions into Step 3 scores, shortfalls, and failures."""
    dims = {k: _dimension(sessions, k) for k in SCORER_FILES}
    dims["skill_coverage"] = _coverage(sessions)
    overall = math.fsum(WEIGHTS[k] * d["score"] for k, d in dims.items())
    fallbacks = [k for k, d in dims.items() if d["fallback_used"]]
    return {
        "sessions_scored": len(sessions),
        "dimensions": dims,
        "overall": overall,
        "total_shortfall": 100 * (1 - overall),
        "failed_conversations": failed_conversations(sessions),
        "fallback_used": bool(fallbacks),
        "evidence_limits": [dims[k]["evidence_limit"] for k in fallbacks],
    }


def pool_strata(strata: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """Recompute the combined score from pooled session records.

    Refuses pre-computed stratum grades: strata have unequal applicability, so
    a combined score must come from pooled applicable results.
    """
    pooled: list[Mapping[str, Any]] = []
    for name, records in strata.items():
        is_seq = isinstance(records, Sequence) and not isinstance(records, (str, bytes))
        if not is_seq or any(not isinstance(r, Mapping) or "scores" not in r for r in records):
            raise TypeError(
                f"stratum {name!r}: pool_strata needs session records, not pre-computed grades"
            )
        pooled.extend(records)
    return aggregate(pooled)


def _group(sessions: Sequence[Mapping[str, Any]], key: str) -> dict[str, list[Mapping[str, Any]]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for s in sessions:
        value = s.get(key)
        if value is not None:
            groups.setdefault(value, []).append(s)
    return groups


def _subset_summary(subset: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    full = aggregate(subset)
    return {
        "sessions_scored": full["sessions_scored"],
        "overall": full["overall"],
        "total_shortfall": full["total_shortfall"],
        "dimensions": full["dimensions"],
        "fallback_used": full["fallback_used"],
    }


def build_artifact(sessions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build the score artifact. Strata and harnesses come from their own subsets."""
    artifact: dict[str, Any] = {"schema_version": SCHEMA_VERSION, **aggregate(sessions)}
    strata = _group(sessions, "stratum")
    harnesses = _group(sessions, "harness")
    artifact["strata"] = {k: _subset_summary(v) for k, v in sorted(strata.items())}
    artifact["per_harness"] = {k: _subset_summary(v) for k, v in sorted(harnesses.items())}
    artifact["combined_source"] = "pooled_records"
    artifact["limitations"] = sorted({lim for s in sessions for lim in s.get("limitations", [])})
    return artifact


def write_atomic(path: Path, data: Mapping[str, Any]) -> None:
    """Write JSON via a temp file in the target directory and ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".audit_scores.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate and aggregate skill-doctor scores.")
    p.add_argument("scores", type=Path, help="scores JSON file")
    p.add_argument("--out", type=Path, default=None, help="write artifact JSON here")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry. Exit 0 ok, 1 validation failure, 2 bad arguments or unreadable file."""
    try:
        args = _parser().parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        return 2 if exc.code not in (0, None) else 0
    try:
        payload = json.loads(args.scores.read_text(encoding="utf-8"))
        tables = load_label_tables()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ScoreInputError) as exc:
        print(f"error: cannot read input: {exc}", file=sys.stderr)
        return 2
    sessions = payload.get("sessions") if isinstance(payload, dict) else payload
    errors = validate_sessions(sessions, tables)
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        return 1
    artifact = build_artifact(sessions)
    try:
        if args.out is not None:
            write_atomic(args.out, artifact)
        else:
            json.dump(artifact, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
    except OSError as exc:
        print(f"error: cannot write output: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
