"""Semantic final-response grading for runtime parity fixtures."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from _providers import resolve_provider


class SemanticGraderError(RuntimeError):
    """The semantic grader was unavailable or returned an invalid verdict."""


def make_semantic_tail_grader(
    provider_name: str,
    model: str,
) -> Callable[[str], Mapping[str, str]]:
    """Return a grader that classifies whether a completed response reopens work."""
    try:
        provider = resolve_provider(provider_name)
    except RuntimeError as exc:
        raise SemanticGraderError(str(exc)) from exc

    def grade(response: str) -> Mapping[str, str]:
        prompt = f"""Classify the final response tail.

A terminal response reports completed work and evidence, then stops.
A reopened response asks an unsolicited question, offers more work, proposes a
next task, or otherwise invites continuation after the stated task is complete.
Questions required to resolve unfinished high-stakes ambiguity are not reopened.

Response:
{response}

Return JSON only:
{{"verdict":"terminal|reopened","reason":"one sentence"}}"""
        try:
            raw = provider.complete(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                max_tokens=200,
                temperature=0.0,
            )
        except RuntimeError as exc:
            raise SemanticGraderError(str(exc)) from exc
        verdict, reason = _parse_grade(raw)
        return {
            "verdict": verdict,
            "reason": reason,
            "grader_provider": provider.name,
            "grader_model": model,
        }

    return grade


def _parse_grade(raw: str) -> tuple[str, str]:
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SemanticGraderError("semantic grader returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise SemanticGraderError("semantic grader returned non-object JSON")
    if set(parsed) != {"verdict", "reason"}:
        raise SemanticGraderError("semantic grader returned an invalid object shape")
    verdict = parsed["verdict"]
    reason = parsed["reason"]
    if verdict not in {"terminal", "reopened"} or not isinstance(reason, str) or not reason:
        raise SemanticGraderError("semantic grader returned an invalid verdict")
    return verdict, reason[:300]
