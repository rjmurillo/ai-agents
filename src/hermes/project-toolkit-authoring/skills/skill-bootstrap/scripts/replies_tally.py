"""The `tally` subcommand: validate labels against the private run, then weight them.

Labels file: {"schema": "reply-friction/labels/v1", "labels": [ ... ]}, one entry
per evidence row:

    {"id": "e0001", "label": "friction", "category": "offer_tail",
     "quote_source": "reply", "quote": "<verbatim text from that field>"}

`label` is friction, none, or unclear. A friction entry needs `category`,
`quote_source` (reply or next_human), and a `quote` that is a verbatim
substring of that one field of that one row. none and unclear entries carry no
category and no quote. Every evidence row needs exactly one label.

Output names problem codes and row ids only. Quotes and transcript text never
leave this module.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from replies_corpus import ConfigError
from replies_sample import EVIDENCE_NAME, MANIFEST_NAME, RUN_SCHEMA

LABELS_SCHEMA = "reply-friction/labels/v1"
TALLY_SCHEMA = "reply-friction/tally/v1"
LABELS = ("friction", "none", "unclear")
CATEGORIES = (
    "offer_tail",
    "bare_ids",
    "decision_buried",
    "self_chore",
    "long_no_lead",
    "wrong_claim",
    "ownjob",
    "confusion",
    "other",
)
QUOTE_SOURCES = ("reply", "next_human")
ALLOWED_FIELDS = frozenset({"id", "label", "category", "quote_source", "quote"})
MIN_QUOTE = 3
MAX_QUOTE = 400
MAX_LABEL_BYTES = 5 * 1024 * 1024
MAX_PROBLEMS = 50
Z95 = 1.96


class ValidationError(Exception):
    """Labels or run files failed validation. `problems` holds codes and ids only."""

    def __init__(self, problems: list[dict[str, str | None]]) -> None:
        super().__init__("invalid")
        self.problems = problems


def load_run(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read the manifest and evidence rows, checking the evidence hash."""
    try:
        manifest = json.loads((run_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
        blob = (run_dir / EVIDENCE_NAME).read_bytes()
    except (OSError, ValueError) as exc:
        raise ConfigError("run_dir_unreadable") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != RUN_SCHEMA:
        raise ConfigError("run_manifest_schema")
    if hashlib.sha256(blob).hexdigest() != manifest.get("evidence_sha256"):
        raise ValidationError([{"id": None, "code": "evidence_modified"}])
    try:
        rows = [json.loads(line) for line in blob.decode("utf-8").splitlines() if line.strip()]
    except (ValueError, RecursionError) as exc:
        raise ConfigError("run_dir_unreadable") from exc
    return manifest, rows


def read_labels(path: Path) -> list[Any]:
    try:
        if path.stat().st_size > MAX_LABEL_BYTES:
            raise ConfigError("labels_too_large")
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError("labels_unreadable") from exc
    except ValueError as exc:
        raise ConfigError("labels_not_json") from exc
    if not isinstance(doc, dict) or doc.get("schema") != LABELS_SCHEMA:
        raise ConfigError("labels_schema")
    if not isinstance(doc.get("labels"), list):
        raise ConfigError("labels_schema")
    return doc["labels"]


def _quote_problem(entry: dict[str, Any], row: dict[str, Any]) -> str | None:
    source, quote = entry.get("quote_source"), entry.get("quote")
    if source not in QUOTE_SOURCES:
        return "bad_quote_source"
    if not isinstance(quote, str) or len(quote.strip()) < MIN_QUOTE:
        return "bad_quote"
    if len(quote) > MAX_QUOTE:
        return "quote_too_long"
    field_text = row.get(source)
    if not isinstance(field_text, str):
        return "quote_source_empty"
    return None if quote in field_text else "quote_not_in_source"


def _entry_problem(entry: dict[str, Any], row: dict[str, Any]) -> str | None:
    if set(entry) - ALLOWED_FIELDS:
        return "unknown_field"
    label = entry.get("label")
    if label not in LABELS:
        return "bad_label"
    if label != "friction":
        extras = ("category", "quote_source", "quote")
        return (
            "unexpected_field_for_label" if any(entry.get(k) is not None for k in extras) else None
        )
    if entry.get("category") not in CATEGORIES:
        return "bad_category"
    return _quote_problem(entry, row)


def validate(entries: list[Any], rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return labels keyed by row id, or raise ValidationError listing every problem."""
    by_id = {row["id"]: row for row in rows}
    problems: list[dict[str, str | None]] = []
    labels: dict[str, dict[str, Any]] = {}
    for entry in entries:
        rid = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(entry, dict) or not isinstance(rid, str):
            problems.append({"id": None, "code": "bad_entry"})
        elif rid not in by_id:
            problems.append({"id": None, "code": "unknown_id"})
        elif rid in labels:
            problems.append({"id": rid, "code": "duplicate_id"})
        else:
            labels[rid] = entry
            code = _entry_problem(entry, by_id[rid])
            if code:
                problems.append({"id": rid, "code": code})
    problems += [{"id": rid, "code": "missing_label"} for rid in by_id if rid not in labels]
    if problems:
        raise ValidationError(problems)
    return labels


def _stratum_stats(
    manifest: dict[str, Any], rows: list[dict[str, Any]], labels: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    cells: dict[tuple[str, bool], Counter[str]] = defaultdict(Counter)
    for row in rows:
        entry = labels[row["id"]]
        cell = cells[(row["kind"], row["flagged"])]
        cell["n"] += 1
        cell[entry["label"]] += 1
        if entry["label"] == "friction":
            cell["cat:" + entry["category"]] += 1
        if row.get("next_class") == "human" and entry["label"] != "unclear":
            cell["typed_n"] += 1
            cell["typed_friction"] += int(entry["label"] == "friction")
    out = []
    for stratum in manifest["strata"]:
        cell = cells.get((stratum["kind"], stratum["flagged"]), Counter())
        if cell["n"] != stratum["sampled"]:
            raise ValidationError([{"id": None, "code": "manifest_sample_mismatch"}])
        out.append({**stratum, "cell": cell})
    return out


def _estimate(strata: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(s["population"] for s in strata)
    resolved = [s for s in strata if s["cell"]["n"] - s["cell"]["unclear"] > 0]
    pop = sum(s["population"] for s in resolved)
    if pop == 0:
        return {"population": total, "rate": None, "ci95": None, "coverage": 0.0}
    est = sum(s["population"] * s["cell"]["friction"] / _m(s) for s in resolved)
    rate = est / pop
    cats = defaultdict(float)
    for s in resolved:
        for key, count in s["cell"].items():
            if key.startswith("cat:"):
                cats[key[4:]] += s["population"] * count / _m(s)
    return {
        "population": total,
        "rate": round(rate, 4),
        "ci95": _interval(resolved, rate, pop),
        "coverage": round(pop / total, 4),
        "estimated_friction": round(est, 2),
        "estimated_by_category": {k: round(v, 2) for k, v in sorted(cats.items())},
    }


def _m(stratum: dict[str, Any]) -> int:
    return stratum["cell"]["n"] - stratum["cell"]["unclear"]


def _interval(resolved: list[dict[str, Any]], rate: float, pop: int) -> list[float] | None:
    """Approximate 95% interval from a stratified Wald variance.

    A stratum with all friction or all none would give zero variance, so only the
    variance term uses the adjusted proportion (x + 0.5) / (m + 1) there. The point
    estimate is unchanged.
    """
    if any(_m(s) < 2 for s in resolved):
        return None
    var = 0.0
    for s in resolved:
        m, big_n, x = _m(s), s["population"], s["cell"]["friction"]
        p = (x + 0.5) / (m + 1) if x in (0, m) else x / m
        var += big_n**2 * (1 - min(1.0, m / big_n)) * p * (1 - p) / (m - 1)
    half = Z95 * math.sqrt(var) / pop
    return [round(max(0.0, rate - half), 4), round(min(1.0, rate + half), 4)]


def _typed_domain(strata: list[dict[str, Any]]) -> dict[str, Any]:
    """Friction rate among replies a person answered. A ratio estimate, so it has no interval."""
    num = den = 0.0
    sampled = 0
    for s in strata:
        if _m(s) <= 0:
            continue
        weight = s["population"] / _m(s)
        num += weight * s["cell"]["typed_friction"]
        den += weight * s["cell"]["typed_n"]
        sampled += s["cell"]["typed_n"]
    rate = round(num / den, 4) if den else None
    return {"sampled": sampled, "estimated_replies": round(den, 2), "rate": rate}


def _check_controls(controls: set[str], labels: dict[str, dict[str, Any]]) -> None:
    missed = [rid for rid in sorted(controls) if labels[rid]["label"] != "friction"]
    if missed:
        raise ValidationError([{"id": rid, "code": "control_not_flagged"} for rid in missed])


def run_tally(run_dir: Path, labels_path: Path) -> dict[str, Any]:
    manifest, rows = load_run(run_dir)
    labels = validate(read_labels(labels_path), rows)
    ids = manifest.get("control_ids")
    if not isinstance(ids, list) or any(
        not isinstance(rid, str) or rid not in labels for rid in ids
    ):
        raise ConfigError("run_manifest_controls")
    controls = set(ids)
    _check_controls(controls, labels)
    strata = _stratum_stats(manifest, [r for r in rows if r["id"] not in controls], labels)
    kinds = sorted({s["kind"] for s in strata})
    return {
        "command": "tally",
        "schema": TALLY_SCHEMA,
        "labeled": len(labels),
        "label_counts": dict(Counter(e["label"] for e in labels.values())),
        "control": {"rows": len(controls), "friction": len(controls)},
        "overall": _estimate(strata),
        "followed_by_typed_turn": _typed_domain(strata),
        "by_kind": {k: _estimate([s for s in strata if s["kind"] == k]) for k in kinds},
        "strata": [
            {
                "kind": s["kind"],
                "flagged": s["flagged"],
                "population": s["population"],
                "sampled": s["sampled"],
                "friction": s["cell"]["friction"],
                "unclear": s["cell"]["unclear"],
            }
            for s in strata
        ],
    }
