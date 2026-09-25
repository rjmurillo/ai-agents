"""Anthropic Messages API response-envelope parsing (REQ-037).

Classifies a response's `stop_reason` into a `Termination` category and
parses the response body into a `MessageResponse`, independent of how the
call was made. `_anthropic_api.py` is the only caller that builds a
`MessageResponse` from a live HTTP call; this module owns none of the
transport, only the envelope shape.

Stdlib only, no sibling imports, so it carries no cycle risk for callers
that need only classification (the adapter, the two evaluators) and do not
need the HTTP/retry machinery in `_anthropic_api.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# REQ-037 termination map. A Messages API `stop_reason` classifies into one
# of five buckets; new provider stop reasons degrade to `incomplete` rather
# than being scored as a completed answer (REQ-037 Q6/Failure Modes).
Termination = Literal["completed", "refusal", "token_limit", "incomplete", "unknown"]

_COMPLETED_STOP_REASONS: frozenset[str] = frozenset({"end_turn", "stop_sequence"})
_REFUSAL_STOP_REASON = "refusal"
_TOKEN_LIMIT_STOP_REASONS: frozenset[str] = frozenset(
    {"max_tokens", "model_context_window_exceeded"}
)

# REQ-037 Failure Modes: a refusal, a token-limit cutoff, and an unrecognized
# stop reason (`incomplete`) must never be scored as an answer. The single
# source of truth for that gate; every caller (the adapter and the two
# evaluators) checks membership here instead of repeating the tuple.
NON_SCOREABLE_TERMINATIONS: frozenset[str] = frozenset({"refusal", "token_limit", "incomplete"})


def classify_termination(stop_reason: object) -> Termination:
    """Map a raw `stop_reason` value to a `Termination` category.

    REQ-037 termination map (DESIGN-035):

    | `stop_reason`                                   | Termination   |
    |--------------------------------------------------|---------------|
    | `end_turn`, `stop_sequence`                       | `completed`   |
    | `refusal`                                         | `refusal`     |
    | `max_tokens`, `model_context_window_exceeded`     | `token_limit` |
    | any other string                                  | `incomplete`  |
    | missing or not a string                           | `unknown`     |
    """
    if not isinstance(stop_reason, str):
        return "unknown"
    if stop_reason in _COMPLETED_STOP_REASONS:
        return "completed"
    if stop_reason == _REFUSAL_STOP_REASON:
        return "refusal"
    if stop_reason in _TOKEN_LIMIT_STOP_REASONS:
        return "token_limit"
    return "incomplete"


@dataclass(frozen=True, slots=True)
class MessageResponse:
    """Structured result of one Messages API call (REQ-037 Data Model).

    Created once per call by `parse_message_response` and never mutated.
    `block_types` preserves content-block order as returned by the API;
    `text` joins only the `text` blocks with `\\n`, matching the historical
    `call_api` return value byte-for-byte.
    """

    text: str
    stop_reason: str | None
    termination: Termination
    block_types: tuple[str, ...]
    refusal_category: str | None = None
    refusal_explanation: str | None = None

    @property
    def blocks_scoring(self) -> bool:
        """True when this response must not be scored as an answer.

        REQ-037 AC-9/Failure Modes: a refusal, a token-limit cutoff, or an
        unrecognized stop reason is recorded, never scored as a right or
        wrong verdict.
        """
        return self.termination in NON_SCOREABLE_TERMINATIONS


def parse_message_response(payload: dict[str, Any]) -> MessageResponse:
    """Parse a Messages API response body into a `MessageResponse`.

    Reads the response dict once. Non-dict content blocks and blocks with a
    missing or non-string `type` are skipped when building `block_types`
    (defensive; the live API always sends dict blocks with a string `type`).
    Refusal `category`/`explanation` are read from `stop_details` only when
    `stop_reason == "refusal"` and `stop_details` is itself a dict; a
    non-string category or explanation is dropped rather than propagated.
    """
    content = payload.get("content", [])
    block_types: list[str] = []
    text_parts: list[str] = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if not isinstance(block_type, str):
                continue
            block_types.append(block_type)
            text = block.get("text")
            if block_type == "text" and isinstance(text, str):
                text_parts.append(text)

    stop_reason_raw = payload.get("stop_reason")
    stop_reason = stop_reason_raw if isinstance(stop_reason_raw, str) else None
    termination = classify_termination(stop_reason_raw)

    refusal_category: str | None = None
    refusal_explanation: str | None = None
    if stop_reason == _REFUSAL_STOP_REASON:
        stop_details = payload.get("stop_details")
        if isinstance(stop_details, dict):
            category = stop_details.get("category")
            if isinstance(category, str):
                refusal_category = category
            explanation = stop_details.get("explanation")
            if isinstance(explanation, str):
                refusal_explanation = explanation

    return MessageResponse(
        text="\n".join(text_parts),
        stop_reason=stop_reason,
        termination=termination,
        block_types=tuple(block_types),
        refusal_category=refusal_category,
        refusal_explanation=refusal_explanation,
    )
