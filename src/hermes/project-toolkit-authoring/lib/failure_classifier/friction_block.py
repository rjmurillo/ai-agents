"""Structural check of a finished friction block. Stdlib only."""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Friction block check
# ---------------------------------------------------------------------------

HIT = "Hit"
DID_INSTEAD = "Did instead"
PERMANENT_FIX = "Permanent fix"

_LABEL_LINE = re.compile(
    r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?(?:\*\*)?(Hit|Did instead|Permanent fix):(?:\*\*)?[ \t]*(.*?)\s*$"
)
_PLACEHOLDER = re.compile(r"<[^<>]*>")

# Items walk three stages: Hit seen, Did instead seen, Permanent fix seen.
_STAGE_NONE = 0
_STAGE_HIT = 1
_STAGE_DID = 2
_STAGE_DONE = 3


@dataclass
class _Field:
    label: str
    value: str
    line: int


def _fields(text: str) -> list[_Field]:
    """Label lines with their values. Indented lines after a label continue it."""
    lines = text.splitlines()
    fields: list[_Field] = []
    for number, line in enumerate(lines):
        match = _LABEL_LINE.match(line)
        if match is None:
            continue
        parts = [match.group(2)]
        for follow in lines[number + 1 :]:
            if not follow.strip() or _LABEL_LINE.match(follow) or not follow[0].isspace():
                break
            parts.append(follow.strip())
        fields.append(_Field(match.group(1), " ".join(p for p in parts if p).strip(), number + 1))
    return fields


def _value_problems(field: _Field) -> list[str]:
    if not field.value:
        return [f'line {field.line}: "{field.label}:" value is empty']
    if _PLACEHOLDER.fullmatch(field.value):
        return [f'line {field.line}: "{field.label}:" value is still a placeholder: {field.value}']
    return []


def _missing(stage: int) -> str:
    if stage == _STAGE_HIT:
        return f'"{DID_INSTEAD}:" and "{PERMANENT_FIX}:"'
    return f'"{PERMANENT_FIX}:"'


def validate_friction_block(text: str) -> list[str]:
    """Problems in a friction report, one string each; empty when valid.

    Each ``Hit:`` line needs a ``Did instead:`` line and then a
    ``Permanent fix:`` line before the next ``Hit:``. Every value must be
    non-empty and not an angle-bracket placeholder such as ``<...>``. A
    ``Did instead:`` or ``Permanent fix:`` with no ``Hit:`` before it is a
    problem. Text with no friction lines is valid: zero items.
    """
    problems: list[str] = []
    stage = _STAGE_NONE
    hit_line = 0
    for field in _fields(text):
        problems.extend(_value_problems(field))
        if field.label == HIT:
            if stage in (_STAGE_HIT, _STAGE_DID):
                problems.append(f'line {hit_line}: "{HIT}:" is not followed by {_missing(stage)}')
            stage, hit_line = _STAGE_HIT, field.line
        elif stage in (_STAGE_NONE, _STAGE_DONE):
            problems.append(f'line {field.line}: "{field.label}:" has no preceding "{HIT}:"')
        elif field.label == DID_INSTEAD:
            if stage == _STAGE_DID:
                problems.append(f'line {field.line}: duplicate "{DID_INSTEAD}:"')
            stage = _STAGE_DID
        else:
            if stage == _STAGE_HIT:
                problems.append(
                    f'line {field.line}: "{PERMANENT_FIX}:" comes before "{DID_INSTEAD}:"'
                )
            stage = _STAGE_DONE
    if stage in (_STAGE_HIT, _STAGE_DID):
        problems.append(f'line {hit_line}: "{HIT}:" is not followed by {_missing(stage)}')
    return problems
