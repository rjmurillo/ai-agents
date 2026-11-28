"""Render the observe-mode PR comment body. Rendering only; nothing posts it."""

from __future__ import annotations

from scripts.pr_approval.engine import Decision

MARKER_PREFIX = "<!-- pr-approval-policy:v1 head="

_LABELS = {"WOULD_APPROVE": "WOULD APPROVE", "HOLD": "HOLD", "OFF": "OFF"}


def marker(head_sha: str | None) -> str:
    """Deduplication marker. One comment per head SHA."""
    return f"{MARKER_PREFIX}{head_sha or 'unknown'} -->"


def render_comment(decision: Decision) -> str:
    """Return a Markdown body built only from stable fields and reason codes."""
    label = _LABELS.get(decision.verdict, "HOLD")
    digest = (decision.policy_digest or "unknown")[:12]
    reasons = ", ".join(f"`{code}`" for code in decision.reasons) or "`NONE`"
    return "\n".join(
        [
            marker(decision.head_sha),
            f"**PR approval policy (observe): {label}**",
            "",
            f"- Head: `{decision.head_sha or 'unknown'}`",
            f"- Rule: `{decision.rule_id or 'none'}`",
            f"- Reasons: {reasons}",
            f"- Policy: `{decision.policy_commit or 'unknown'}` digest `{digest}`",
            "",
            "Observe mode records a decision only. It grants no approval and merges nothing.",
        ]
    )
