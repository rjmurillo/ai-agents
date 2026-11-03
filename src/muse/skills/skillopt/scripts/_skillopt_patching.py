"""Bounded patch applier, edit budget, and the protected slow-section."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

SLOW_START = "<!-- SLOW_UPDATE_START -->"
SLOW_END = "<!-- SLOW_UPDATE_END -->"

# Marker names a patch body may never contain: a patch cannot open, close, or
# forge a slow-section fence.
_MARKER_NAMES = ("SLOW_UPDATE_START", "SLOW_UPDATE_END")

VALID_OPS = ("append", "insert_after", "replace", "delete")


class SkillOptError(Exception):
    """A bounded-edit rule was violated. Carries a human-readable reason."""


# --------------------------------------------------------------------------- #
# Edit budget: the learning rate (cosine annealing, explore -> fine-tune)
# --------------------------------------------------------------------------- #
def edit_budget(step: int, total_steps: int, l_max: int = 5, l_min: int = 1) -> int:
    """Max atomic edits allowed at `step` of `total_steps`, cosine-annealed.

    Starts at l_max (exploration) and decays to l_min (fine-tuning), matching
    SkillOpt's cosine-decayed textual edit budget L_t. step is 0-indexed.
    """
    if total_steps < 1:
        raise SkillOptError("total_steps must be >= 1")
    if not 0 <= step < total_steps:
        raise SkillOptError(f"step {step} out of range [0, {total_steps})")
    if l_min < 1:
        raise SkillOptError("l_min must be >= 1")
    if l_max < l_min:
        raise SkillOptError("l_max must be >= l_min")
    if total_steps == 1:
        return l_max
    progress = step / (total_steps - 1)  # 0.0 .. 1.0
    cosine = 0.5 * (1.0 + math.cos(math.pi * progress))  # 1.0 .. 0.0
    value = l_min + (l_max - l_min) * cosine
    return max(l_min, min(l_max, round(value)))


# --------------------------------------------------------------------------- #
# Protected slow-section: longitudinal guidance step edits cannot overwrite
# --------------------------------------------------------------------------- #
def protected_ranges(lines: list[str]) -> list[tuple[int, int]]:
    """Return [(start_idx, end_idx)] inclusive line ranges of every slow-section.

    A malformed fence (START without matching END, or crossed markers) is an
    error: silent acceptance would let an edit slip into protected content.
    """
    ranges: list[tuple[int, int]] = []
    open_idx: int | None = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped == SLOW_START:
            if open_idx is not None:
                raise SkillOptError(f"nested {SLOW_START} at line {idx + 1}")
            open_idx = idx
        elif stripped == SLOW_END:
            if open_idx is None:
                raise SkillOptError(f"{SLOW_END} without {SLOW_START} at line {idx + 1}")
            ranges.append((open_idx, idx))
            open_idx = None
    if open_idx is not None:
        raise SkillOptError(f"unterminated {SLOW_START} at line {open_idx + 1}")
    return ranges


def _is_protected(idx: int, ranges: Iterable[tuple[int, int]], *, allow_after_end: bool) -> bool:
    """True if mutating line `idx` would touch protected content.

    allow_after_end lets insert_after anchor on the END marker (the insertion
    lands outside the fence) while still blocking inserts on the START marker
    and any line strictly inside the fence.
    """
    for start, end in ranges:
        upper = end - 1 if allow_after_end else end
        if start <= idx <= upper:
            return True
    return False


def _find_anchor(lines: list[str], anchor: str) -> int:
    """Index of the unique line equal to `anchor`. Ambiguity or absence rejects.

    Ambiguous anchors are rejected rather than guessed: a wrong guess silently
    mutates the wrong line, the exact instability SkillOpt's bounded edits exist
    to prevent.
    """
    matches = [i for i, line in enumerate(lines) if line == anchor]
    if not matches:
        raise SkillOptError(f"anchor not found: {anchor!r}")
    if len(matches) > 1:
        raise SkillOptError(f"anchor ambiguous ({len(matches)} matches): {anchor!r}")
    return matches[0]


def _patch_text_lines(patch: dict[str, Any], n: int) -> list[str]:
    """The patch `text` as LF-split lines; CRLF in the text is normalized."""
    text = patch.get("text", "")
    if not isinstance(text, str):
        raise SkillOptError(f"patch {n}: 'text' must be a string")
    if any(marker in text for marker in _MARKER_NAMES):
        raise SkillOptError(f"patch {n}: text must not contain slow-section marker text")
    return text.replace("\r\n", "\n").split("\n")


def _apply_one(lines: list[str], patch: dict[str, Any], n: int) -> None:
    """Apply one validated-shape patch to `lines` in place."""
    op = patch.get("op")
    if op not in VALID_OPS:
        raise SkillOptError(f"patch {n}: invalid op {op!r}; expected one of {VALID_OPS}")

    ranges = protected_ranges(lines)  # recompute: line indices shift between patches

    if op == "append":
        lines.extend(_patch_text_lines(patch, n))
        return

    anchor = patch.get("anchor")
    if not isinstance(anchor, str):
        raise SkillOptError(f"patch {n}: {op} requires a string 'anchor'")
    idx = _find_anchor(lines, anchor)
    if _is_protected(idx, ranges, allow_after_end=(op == "insert_after")):
        raise SkillOptError(f"patch {n}: {op} would touch the protected slow-section")

    if op == "insert_after":
        lines[idx + 1 : idx + 1] = _patch_text_lines(patch, n)
    elif op == "replace":
        lines[idx : idx + 1] = _patch_text_lines(patch, n)
    else:
        del lines[idx]


def apply_patches(doc: str, patches: list[dict[str, Any]], budget: int) -> str:
    """Apply at most `budget` atomic patches to `doc`, return the new document.

    Each patch: {"op": append|insert_after|replace|delete, "anchor": str, "text": str}.
    append ignores anchor and adds text as trailing lines. Raises SkillOptError
    on budget overflow, bad op, ambiguous anchor, or any attempt to mutate the
    protected slow-section. All-or-nothing: a single bad patch rejects the batch.

    Line endings: a document containing CRLF is processed as LF and restored to
    CRLF on output, so a Windows file round-trips without translation. A
    document that mixes endings is normalized to CRLF.
    """
    if not isinstance(patches, list) or not all(isinstance(p, dict) for p in patches):
        raise SkillOptError("patches must be a JSON list of objects")
    if budget < 0:
        raise SkillOptError("budget must be >= 0")
    if len(patches) > budget:
        raise SkillOptError(f"edit budget exceeded: {len(patches)} patches > budget {budget}")

    crlf = "\r\n" in doc
    lines = doc.replace("\r\n", "\n").split("\n")
    for n, patch in enumerate(patches):
        _apply_one(lines, patch, n)
    protected_ranges(lines)  # final check: the fence structure is still well formed
    result = "\n".join(lines)
    return result.replace("\n", "\r\n") if crlf else result
