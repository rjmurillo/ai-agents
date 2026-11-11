"""Synthetic inventories and score rows shared by the audit_batches tests."""

from __future__ import annotations

from typing import Any

import audit_scores
from session_sampling import TIMELINE_SUPPLEMENT

Row = dict[str, Any]
TABLES = audit_scores.load_label_tables()


def _session(name: str, stratum: str | None = None, sampled: bool = True) -> Row:
    row: Row = {"harness": "copilot", "meta": {"id": name}, "sampled": sampled}
    if stratum:
        row["stratum"] = stratum
    return row


def _inventory(n: int = 5, extra: int = 0) -> Row:
    sessions = [_session(f"s{i}") for i in range(n)]
    sessions += [_session(f"t{i}", TIMELINE_SUPPLEMENT) for i in range(extra)]
    sessions.append(_session("unsampled", sampled=False))
    return {
        "generated_at": "2026-11-10T00:00:00+00:00",
        "stats": {"sessions_considered": 40},
        "sampling": {"rule": "R", "within_harness": "W", "max_sessions": 12},
        "sessions": sessions,
    }


def _score(scorer: str, label: str) -> Row:
    return {"label": label, "score": TABLES[scorer][label], "reason": "synthetic reason"}


def _row(assignment: Row, sid: str, **extra: Any) -> Row:
    row: Row = {
        "session_id": sid,
        "batch_id": assignment["batch_id"],
        "source_digest": assignment["source_digest"],
        "harness": "copilot",
        "skills_detected": True,
        "scores": {
            "efficiency": _score("efficiency", "highly_efficient"),
            "code_quality": {**_score("code_quality", "approve")},
            "procedure_compliance": _score("procedure_compliance", "fully_compliant"),
            "verbosity": _score("verbosity", "proportionate"),
        },
    }
    row.update(extra)
    return row


def _rows(assignment: Row) -> list[Row]:
    return [_row(assignment, sid) for sid in assignment["session_ids"]]
