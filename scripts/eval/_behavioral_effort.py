"""Behavioral effort evidence for the Claude harness (issue #5426, Amendment 4).

Claude Code names no reasoning effort in its stream, so no backend value can confirm a
requested effort. Owner decision D12 (2026-10-23) accepts a weaker proof for Claude only.
A model's effort control counts as verified when its thinking tokens strictly increase
across `low`, `medium`, and `high`. Each count comes from the same fixed prompt, one
separate `claude -p` call per level, on the pinned CLI version.

Weaker than the Codex rule: Codex effort is named by the backend and must equal the
request. A rising thinking-token count shows the flag changes behavior, never which value
was served. Every Claude report labels its effort evidence `behavioral`.

Pure data and checks. No I/O, no process. `_harness_capability` owns the record, the
evidence kind, and the arm eligibility that reads this.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

LEVELS: tuple[str, ...] = ("low", "medium", "high")
#: The only harness whose effort may rest on behavioral evidence.
BEHAVIORAL_HARNESS = "claude"


class BehavioralEffortError(ValueError):
    """The behavioral effort block is malformed."""


@dataclass(frozen=True, slots=True)
class BehavioralEffort:
    """Thinking tokens per model and effort level, measured on one CLI version.

    `thinking_tokens[model][level]` is the `thinking_tokens` the result event reported
    for one call. A missing level or model is simply absent, and fails the check.
    """

    cli_version: str
    prompt: str
    thinking_tokens: Mapping[str, Mapping[str, int]]


def strictly_increasing(counts: Mapping[str, int | None]) -> bool:
    """True when low < medium < high, all three present. A tie or inversion is False."""
    values = [counts.get(level) for level in LEVELS]
    if any(not isinstance(v, int) or isinstance(v, bool) for v in values):
        return False
    ints = [v for v in values if v is not None]
    return all(first < second for first, second in zip(ints, ints[1:], strict=False))


def verified_models(evidence: BehavioralEffort | None, pinned_version: str) -> frozenset[str]:
    """Models whose effort control is verified on `pinned_version`. Empty on a mismatch."""
    if evidence is None or not pinned_version or evidence.cli_version != pinned_version:
        return frozenset()
    return frozenset(
        model for model, counts in evidence.thinking_tokens.items() if strictly_increasing(counts)
    )


def models_verified(
    evidence: BehavioralEffort | None, pinned_version: str, models: Sequence[str]
) -> bool:
    """True when `models` is non-empty and every one of them is verified."""
    verified = verified_models(evidence, pinned_version)
    return bool(models) and all(model in verified for model in models)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BehavioralEffortError(f"{field} must be a non-empty string")
    return value


def _counts(value: object, field: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise BehavioralEffortError(f"{field} must be an object")
    counts: dict[str, int] = {}
    for level, count in value.items():
        if level not in LEVELS:
            raise BehavioralEffortError(f"{field} has unknown level {level!r}; use {LEVELS}")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise BehavioralEffortError(f"{field}.{level} must be a non-negative integer")
        counts[level] = count
    return counts


def parse_behavioral_effort(value: object, field: str) -> BehavioralEffort | None:
    """Parse the optional record block. `None` means the record has none."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise BehavioralEffortError(f"{field} must be an object")
    models = value.get("thinking_tokens")
    if not isinstance(models, dict) or not models:
        raise BehavioralEffortError(f"{field}.thinking_tokens must be a non-empty object")
    return BehavioralEffort(
        cli_version=_text(value.get("cli_version"), f"{field}.cli_version"),
        prompt=_text(value.get("prompt"), f"{field}.prompt"),
        thinking_tokens={
            str(model): _counts(counts, f"{field}.thinking_tokens.{model}")
            for model, counts in models.items()
        },
    )


def behavioral_effort_dict(evidence: BehavioralEffort) -> dict[str, object]:
    return {
        "cli_version": evidence.cli_version,
        "prompt": evidence.prompt,
        "thinking_tokens": {m: dict(c) for m, c in evidence.thinking_tokens.items()},
    }
