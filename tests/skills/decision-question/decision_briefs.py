"""Brief builders shared by the decision-question tests."""

from __future__ import annotations

from typing import Any


def raw_decision(decision_id: str, option_count: int = 2, **extra: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "id": decision_id,
        "statement": f"Decide {decision_id}.",
        "why_now": "Blocks the next step.",
        "options": [
            {"id": f"o{n}", "label": f"Option {n}", "consequence": f"Cost {n}."}
            for n in range(1, option_count + 1)
        ],
        "recommendation": "o1",
        "recommendation_reason": "Cheapest path that meets the criteria.",
    }
    raw.update(extra)
    return raw


def make_brief(*decisions: dict[str, Any], **context: Any) -> dict[str, Any]:
    ctx: dict[str, Any] = {"material_decision": True}
    ctx.update(context)
    return {"context": ctx, "decisions": list(decisions)}
