"""Ledger builders shared by the audit-mode tests."""

from __future__ import annotations

from typing import Any

from audit_check import CATEGORIES


def anchor(section: str, quote: str) -> dict[str, str]:
    return {"section": section, "quote": quote}


def option(oid: str, label: str, consequence: str | None = None) -> dict[str, str]:
    return {"id": oid, "label": label, "consequence": consequence or f"{label} becomes the rule."}


def ask(cid: str, category: str, anchors: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    """An ask candidate with two materially distinct options and no recommendation."""

    base: dict[str, Any] = {
        "id": cid,
        "category": category,
        "disposition": "ask",
        "anchors": anchors,
        "statement": f"Decide {cid}.",
        "why_now": "The spec cannot be built until this is fixed.",
        "options": [option("a", "Option A"), option("b", "Option B")],
    }
    base.update(extra)
    return base


def ledger(candidates: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "coverage_reviewed": sorted(CATEGORIES),
        "candidates": candidates,
    }
    data.update(extra)
    return data
