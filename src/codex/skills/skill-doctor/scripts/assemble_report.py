"""Assemble report.json from a report draft, scores.json, and an optional audit manifest.

Replaces the hand copy in Step 3. The score artifact is recomputed from the scored
records, so every number in the report traces back to one accepted score per
session. A supplied ``--artifact`` must equal that recomputation.

Writes:
  - ``scores``: curved dimension scores and ``overall`` from the artifact
  - ``stats.sessions_analyzed``: the number of scored sessions
  - ``sampling.per_harness.<harness>.overall``: each harness scored on its own records
  - ``audit``: ``scores`` (the artifact), ``records`` (the scored sessions), and
    ``catalog`` from the audit manifest when one is given

``grade`` is dropped so the renderer derives it from the new ``overall``.

Exit codes: 0 written, 1 invalid or inconsistent input (nothing written),
2 bad arguments or an unreadable file. Python 3.10+, stdlib only.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import audit_scores
import report_audit
import report_evaluation

DIMENSIONS = tuple(audit_scores.WEIGHTS)


class AssemblyError(ValueError):
    """Raised when inputs cannot produce a consistent report. ``errors`` lists every reason."""

    def __init__(self, errors: Sequence[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = list(errors)


def _sessions_of(scores: Any) -> Any:
    return scores.get("sessions") if isinstance(scores, dict) else scores


def recompute_artifact(scores: Any) -> dict[str, Any]:
    """Validate scored sessions and build their artifact. Raises AssemblyError when invalid."""
    sessions = _sessions_of(scores)
    errors = audit_scores.validate_sessions(sessions, audit_scores.load_label_tables())
    if errors:
        raise AssemblyError(errors)
    return audit_scores.build_artifact(sessions)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _catalog_of(manifest: Any) -> list[Any]:
    catalog = manifest.get("catalog") if isinstance(manifest, dict) else None
    if not isinstance(catalog, list):
        raise AssemblyError(["audit manifest has no catalog list"])
    return catalog


def _set_harness_overall(report: dict[str, Any], artifact: Mapping[str, Any]) -> None:
    sampling = report.setdefault("sampling", {})
    per_harness = sampling.setdefault("per_harness", {})
    for harness, summary in artifact["per_harness"].items():
        per_harness.setdefault(harness, {})["overall"] = summary["overall"]


def assemble(
    draft: Mapping[str, Any],
    scores: Any,
    artifact: Mapping[str, Any] | None = None,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the assembled report. Raises AssemblyError before returning anything invalid."""
    if not isinstance(draft, dict):
        raise AssemblyError(["report draft must be a JSON object"])
    rebuilt = recompute_artifact(scores)
    if artifact is not None and _canonical(artifact) != _canonical(rebuilt):
        raise AssemblyError(["score artifact does not recompute from the scored records"])
    report = copy.deepcopy(dict(draft))
    report.pop("grade", None)
    report["scores"] = {key: rebuilt["dimensions"][key]["score"] for key in DIMENSIONS}
    report["scores"]["overall"] = rebuilt["overall"]
    report.setdefault("stats", {})["sessions_analyzed"] = rebuilt["sessions_scored"]
    _set_harness_overall(report, rebuilt)
    audit: dict[str, Any] = {"scores": rebuilt, "records": list(_sessions_of(scores))}
    if manifest is not None:
        audit["catalog"] = _catalog_of(manifest)
    report["audit"] = audit
    errors = report_evaluation.validate_report(report) + report_audit.validate_audit(report)
    if errors:
        raise AssemblyError(errors)
    return report


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Assemble report.json from scored records.")
    p.add_argument("draft", type=Path, help="report draft JSON (findings, suggestions, stats)")
    p.add_argument("--scores", type=Path, required=True, help="scores.json with scored sessions")
    p.add_argument("--artifact", type=Path, default=None, help="score_artifact.json to verify")
    p.add_argument("--manifest", type=Path, default=None, help="audit_manifest.json for catalog")
    p.add_argument("--out", type=Path, required=True, help="report.json to write")
    return p


def _read(path: Path | None) -> Any:
    return None if path is None else json.loads(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry. Exit 0 ok, 1 invalid input (nothing written), 2 bad arguments or I/O."""
    try:
        args = _parser().parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        return 2 if exc.code not in (0, None) else 0
    try:
        inputs = [_read(p) for p in (args.draft, args.scores, args.artifact, args.manifest)]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"error: cannot read input: {exc}", file=sys.stderr)
        return 2
    try:
        report = assemble(*inputs)
    except AssemblyError as exc:
        for error in exc.errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    except audit_scores.ScoreInputError as exc:
        print(f"error: cannot read rubrics: {exc}", file=sys.stderr)
        return 2
    try:
        audit_scores.write_atomic(args.out, report)
    except OSError as exc:
        print(f"error: cannot write output: {exc}", file=sys.stderr)
        return 2
    print(f"report: {args.out}")
    print(
        f"overall: {report['scores']['overall']:.4f} from {report['stats']['sessions_analyzed']} sessions"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
