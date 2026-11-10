"""Optional audit sections for the skill-doctor HTML report.

A report.json may carry an ``audit`` object with up to three parts:

- ``catalog``: ``{"definitions": [...]}`` or a bare list, the ``catalog`` of an
  M1 ``audit_manifest.json`` (name, sha256, path, scope, aliases,
  current_edit_target).
- ``scores``: the M3 score artifact written by ``audit_scores.py``.
- ``records``: the scored session records behind that artifact.

``render_audit`` returns "" when ``audit`` is absent, so older reports render
unchanged. ``validate_audit`` makes the JSON totals and the report scorecard
agree before any HTML is written. Escaping is injected (``esc``) so this module
shares the renderer's single escape function.

Python 3.10+, stdlib only.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

TOLERANCE = 1e-9
DIMENSIONS = (
    ("efficiency", "Efficiency"),
    ("code_quality", "Code Quality"),
    ("procedure_compliance", "Procedure Compliance"),
    ("verbosity", "Verbosity"),
    ("skill_coverage", "Skill Coverage"),
)
SCORER_KEYS = tuple(key for key, _ in DIMENSIONS if key != "skill_coverage")

Escape = Callable[[Any], str]


def audit_of(report: Mapping[str, Any]) -> dict[str, Any]:
    audit = report.get("audit")
    return audit if isinstance(audit, dict) else {}


def catalog_definitions(audit: Mapping[str, Any]) -> list[dict[str, Any]]:
    catalog = audit.get("catalog")
    items = catalog.get("definitions") if isinstance(catalog, dict) else catalog
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def conflict_groups(definitions: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Names that carry more than one distinct content hash."""
    by_name: dict[str, set[str]] = {}
    for definition in definitions:
        by_name.setdefault(str(definition.get("name")), set()).add(str(definition.get("sha256")))
    return {name: sorted(hashes) for name, hashes in sorted(by_name.items()) if len(hashes) > 1}


def catalog_counts(audit: Mapping[str, Any]) -> dict[str, int] | None:
    """Definition, alias and conflicting-name counts, or None without a catalog."""
    if "catalog" not in audit:
        return None
    definitions = catalog_definitions(audit)
    aliases = sum(len(d.get("aliases") or []) for d in definitions)
    return {
        "definitions": len(definitions),
        "aliases": aliases,
        "conflicts": len(conflict_groups(definitions)),
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _score_errors(report: Mapping[str, Any], artifact: Mapping[str, Any]) -> list[str]:
    scores = report.get("scores") if isinstance(report.get("scores"), dict) else {}
    dims = artifact.get("dimensions") if isinstance(artifact.get("dimensions"), dict) else {}
    errors: list[str] = []
    pairs = [(key, dims.get(key, {}).get("score")) for key, _ in DIMENSIONS]
    pairs.append(("overall", artifact.get("overall")))
    for key, expected in pairs:
        actual = scores.get(key)
        if not _is_number(expected) or not _is_number(actual):
            errors.append(f"audit.scores: {key} missing or not numeric in report or artifact")
        elif not math.isclose(actual, expected, abs_tol=TOLERANCE, rel_tol=0.0):
            errors.append(f"audit.scores: report {key} {actual!r} != artifact {expected!r}")
    return errors


def _count_errors(report: Mapping[str, Any], audit: Mapping[str, Any]) -> list[str]:
    artifact = audit["scores"]
    scored = artifact.get("sessions_scored")
    errors: list[str] = []
    records = audit.get("records")
    if isinstance(records, list) and scored != len(records):
        errors.append(f"audit.records has {len(records)} rows but scores.sessions_scored={scored}")
    stats = report.get("stats") if isinstance(report.get("stats"), dict) else {}
    analyzed = stats.get("sessions_analyzed")
    if analyzed is not None and analyzed != scored:
        errors.append(
            f"stats.sessions_analyzed={analyzed} != audit.scores.sessions_scored={scored}"
        )
    return errors


def validate_audit(report: Mapping[str, Any]) -> list[str]:
    """Errors when the report scorecard and the score artifact disagree."""
    audit = audit_of(report)
    artifact = audit.get("scores")
    if not isinstance(artifact, dict):
        return []
    return _score_errors(report, artifact) + _count_errors(report, audit)


def _row(esc: Escape, cells: Sequence[Any]) -> str:
    return "<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in cells) + "</tr>"


def _table(esc: Escape, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join(_row(esc, row) for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _details(esc: Escape, summary: str, body: str, open_: bool = False) -> str:
    flag = " open" if open_ else ""
    return f"<details{flag}><summary>{esc(summary)}</summary>{body}</details>"


def render_catalog(audit: Mapping[str, Any], esc: Escape) -> str:
    counts = catalog_counts(audit)
    if counts is None:
        return ""
    definitions = catalog_definitions(audit)
    rows = [
        [
            d.get("name"),
            d.get("sha256"),
            d.get("scope"),
            d.get("path"),
            "; ".join(str(a) for a in d.get("aliases") or []) or "-",
            "yes" if d.get("current_edit_target") else "no",
        ]
        for d in definitions
    ]
    conflicts = conflict_groups(definitions)
    conflict_rows = [[name, ", ".join(hashes)] for name, hashes in conflicts.items()]
    summary = (
        f'<p id="audit-catalog-counts" data-definitions="{counts["definitions"]}" '
        f'data-aliases="{counts["aliases"]}" data-conflicts="{counts["conflicts"]}">'
        f"{counts['definitions']} definitions, {counts['aliases']} aliases, "
        f"{counts['conflicts']} conflicting-name groups.</p>"
        '<p class="muted">A current content hash does not prove the content that ran '
        "in a past conversation.</p>"
    )
    headers = ["Name", "Content hash", "Scope", "Path", "Aliases", "Current edit target"]
    body = summary + _table(esc, headers, rows)
    if conflict_rows:
        body += "<h3>Conflicting names</h3>" + _table(
            esc, ["Name", "Distinct hashes"], conflict_rows
        )
    return _details(esc, "Skill catalog", body)


def _dimension_rows(artifact: Mapping[str, Any]) -> list[list[Any]]:
    dims = artifact.get("dimensions") or {}
    rows: list[list[Any]] = []
    for key, label in DIMENSIONS:
        d = dims.get(key) or {}
        rows.append(
            [
                label,
                f"{d.get('score', 0):.4f}",
                f"{d.get('numerator', 0):g}",
                d.get("denominator", 0),
                d.get("inapplicable", 0),
                "fallback" if d.get("fallback_used") else "measured",
                f"{d.get('weighted_shortfall', 0):.4f}",
            ]
        )
    return rows


def render_scores(audit: Mapping[str, Any], esc: Escape) -> str:
    artifact = audit.get("scores")
    if not isinstance(artifact, dict):
        return ""
    headers = [
        "Dimension",
        "Score",
        "Numerator",
        "Applicable",
        "Inapplicable",
        "Basis",
        "Weighted shortfall",
    ]
    total = artifact.get("total_shortfall", 0)
    parts = [
        f'<p id="audit-scores-total" data-sessions="{esc(artifact.get("sessions_scored"))}">'
        f"{esc(artifact.get('sessions_scored'))} conversations scored. "
        f"Overall {float(artifact.get('overall', 0)):.4f}; "
        f"total weighted shortfall {float(total):.4f} points.</p>",
        _table(esc, headers, _dimension_rows(artifact)),
    ]
    limits = list(artifact.get("evidence_limits") or []) + list(artifact.get("limitations") or [])
    if limits:
        parts.append("<ul>" + "".join(f"<li>{esc(item)}</li>" for item in limits) + "</ul>")
    failed = artifact.get("failed_conversations") or {}
    if failed:
        parts.append(
            f"<p>Conversations with an applicable score below 0.5: {esc(failed.get('count', 0))}"
            f" (termination-only exclusions: {esc(failed.get('excluded_count', 0))}).</p>"
        )
    return _details(esc, "Score artifact", "".join(parts))


def _record_rows(record: Mapping[str, Any]) -> list[list[Any]]:
    scores = record.get("scores") if isinstance(record.get("scores"), dict) else {}
    rows: list[list[Any]] = []
    for scorer in SCORER_KEYS:
        r = scores.get(scorer) or {}
        applicable = r.get("applicable", r.get("label") != "insufficient_evidence")
        rows.append(
            [
                scorer,
                r.get("label"),
                r.get("score"),
                "applicable" if applicable else "not applicable",
                r.get("reason"),
                r.get("evidence_ref") or "-",
            ]
        )
    return rows


def _render_record(record: Mapping[str, Any], esc: Escape) -> str:
    title = f"{record.get('session_id')} | {record.get('harness')} | {record.get('stratum') or '-'}"
    headers = ["Scorer", "Label", "Score", "Applicability", "Reason", "Evidence"]
    body = _table(esc, headers, _record_rows(record))
    if record.get("terminated_by"):
        body = f"<p>Terminated by: {esc(record['terminated_by'])}</p>" + body
    return _details(esc, title, body)


def render_records(audit: Mapping[str, Any], esc: Escape) -> str:
    records = audit.get("records")
    if not isinstance(records, list):
        return ""
    items = "".join(_render_record(r, esc) for r in records if isinstance(r, dict))
    count = f'<p id="audit-record-count" data-records="{len(records)}">{len(records)} records.</p>'
    return _details(esc, "Per-conversation evidence", count + items)


def render_audit(report: Mapping[str, Any], esc: Escape) -> str:
    """All audit sections, or "" when the report carries none."""
    audit = audit_of(report)
    if not audit:
        return ""
    parts = [
        render_scores(audit, esc),
        render_catalog(audit, esc),
        render_records(audit, esc),
    ]
    body = "".join(part for part in parts if part)
    return f'<h2>Audit evidence</h2><div class="audit">{body}</div>' if body else ""
