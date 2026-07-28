#!/usr/bin/env python3
"""Held-out-gated artifact optimization primitives (Issue #3422).

Pure functions with no I/O and no API calls, so the accept/reject decision is
unit-testable without eval spend. The CLI in ``optimize-artifact.py`` wires these to
files; the scorers stay where they are.

Why this exists
---------------
The rest of ``scripts/eval/`` measures artifacts. Nothing gates an edit to one.
``eval-prompt-change.py`` scores a prompt before and after an edit on the same
scenarios the author read while making the edit, and ``eval-agent-vs-baseline.py``
scores an agent against every fixture in its spike directory while the author
reads the failures and rewrites the prompt. Both loops fit the test set.

The discipline here is SkillOpt's (Yang et al., Microsoft, arXiv:2605.23904):
treat the artifact as external trainable state, propose bounded edits from
scored rollouts, and land a candidate only if it strictly beats the incumbent on
a split the author never saw. Rejected edits are fingerprinted so the same
failure is not re-proposed.

Two properties here are not in that paper, and both close holes that show up
once a loop runs for more than a few steps:

``TaskSplit.fingerprint``
    Gating N times against one ``sel`` split selects on that split N times. A
    losing edit can be resurrected by adding fixtures and re-rolling. The
    fingerprint covers the seed, the task-id set, and the ratios, and
    :func:`gate` refuses when it moves, so an eval-set change forces a
    re-baseline instead of silently laundering a loss.

``gate(max_consultations=...)``
    Even with a fixed split, repeated selection erodes the gate's meaning. The
    consultation count is carried in the result and can be capped, so the loop
    reports that it has run out of statistical room rather than hiding it.

The seam between this module and any scorer is one mapping, ``{task_id: bool}``.
Agents key it by fixture id, rules and prompts by scenario id, hooks by pytest
node id. That is the whole reason the loop generalizes past skills.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction

__all__ = [
    "AmbiguousAnchorError",
    "AnchorNotFoundError",
    "BudgetExceededError",
    "GateResult",
    "MissingResultError",
    "Patch",
    "PatchShapeError",
    "ProtectedSectionError",
    "SplitTooSmallError",
    "TaskSplit",
    "apply_patches",
    "buffer_contains",
    "edit_budget",
    "gate",
    "guard_refusal",
    "mcnemar_exact",
    "patch_fingerprint",
    "split_fingerprint",
    "score",
    "split_tasks",
]

FENCE_START = "<!-- SLOW_UPDATE_START -->"
FENCE_END = "<!-- SLOW_UPDATE_END -->"

_ANCHORED_OPS = frozenset({"insert_after", "replace", "delete"})
_TEXT_OPS = frozenset({"append", "insert_after", "replace"})
_VALID_OPS = frozenset({"append", "insert_after", "replace", "delete"})
_MAX_RATIO_TEXT_LENGTH = 128
_MAX_RATIO_COEFFICIENT_DIGITS = 64
_MAX_RATIO_EXPONENT_MAGNITUDE = 100
Ratio = float | str


class SplitTooSmallError(ValueError):
    """The requested split yields a held-out set too small to gate on."""


class BudgetExceededError(ValueError):
    """More patches were proposed than this step's edit budget allows."""


class AnchorNotFoundError(ValueError):
    """A patch anchor does not appear in the document."""


class AmbiguousAnchorError(ValueError):
    """A patch anchor appears more than once, so the target is undefined."""


class ProtectedSectionError(ValueError):
    """A patch would mutate the protected slow-update fence."""


class PatchShapeError(ValueError):
    """A patch is missing a field its operation requires."""


class MissingResultError(ValueError):
    """A scored task has no entry in the results mapping."""


@dataclass(frozen=True)
class Patch:
    """One atomic edit.

    ``anchor`` is the unique line a patch attaches to and is required for every
    operation except ``append``. ``text`` is the content to write and is
    required for every operation except ``delete``.
    """

    op: str
    anchor: str | None
    text: str | None


@dataclass(frozen=True)
class TaskSplit:
    """A deterministic partition of an eval set.

    ``opt`` is visible to whoever proposes edits. ``sel`` gates them and must
    never be read during reflection. ``test`` is optional, never gates, and
    exists so a converged loop can report one number that repeated selection
    has not touched.
    """

    opt: tuple[str, ...]
    sel: tuple[str, ...]
    test: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True)
class GateResult:
    """The verdict on one candidate.

    ``compared`` records whether the scores were actually weighed. A refusal on
    a moved fingerprint or an exhausted budget short-circuits before the
    comparison, so it costs the held-out split nothing and the caller must not
    charge a consultation for it.
    """

    decision: str
    reason: str
    candidate: float
    incumbent: float
    sel_consultations: int
    compared: bool = True


def _ratio_fraction(name: str, value: Ratio) -> Fraction:
    ratio_text = str(value)
    display = _ratio_display(ratio_text)
    if len(ratio_text) > _MAX_RATIO_TEXT_LENGTH:
        raise ValueError(
            f"{name} must be a decimal ratio with at most "
            f"{_MAX_RATIO_TEXT_LENGTH} characters, got {display}"
        )
    try:
        decimal = Decimal(ratio_text)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a decimal ratio, got {display}") from exc
    if not decimal.is_finite():
        raise ValueError(f"{name} must be a finite decimal ratio, got {display}")
    if not Decimal("0") <= decimal <= Decimal("1"):
        raise ValueError(f"{name} must be a decimal ratio between 0 and 1, got {display}")
    if decimal and abs(decimal.adjusted()) > _MAX_RATIO_EXPONENT_MAGNITUDE:
        raise ValueError(
            f"{name} must be a decimal ratio with exponent magnitude "
            f"<= {_MAX_RATIO_EXPONENT_MAGNITUDE}, got {display}"
        )
    if len(decimal.as_tuple().digits) > _MAX_RATIO_COEFFICIENT_DIGITS:
        raise ValueError(
            f"{name} must be a decimal ratio with at most "
            f"{_MAX_RATIO_COEFFICIENT_DIGITS} coefficient digits, got {display}"
        )
    return Fraction(decimal)


def _ratio_display(value: str) -> str:
    if len(value) <= 40:
        return value
    return f"{value[:37]}... (length {len(value)})"


def _canonical_ratio(value: Ratio, *, name: str = "ratio") -> str:
    ratio = _ratio_fraction(name, value)
    return f"{ratio.numerator}/{ratio.denominator}"


def _round_half_up(value: Fraction) -> int:
    """Round halves away from zero, avoiding banker's rounding surprises."""
    shifted = value + Fraction(1, 2)
    return shifted.numerator // shifted.denominator


def split_tasks(
    task_ids: Sequence[str],
    *,
    seed: str,
    sel_ratio: Ratio = 0.4,
    test_ratio: Ratio = 0.0,
    min_sel: int = 3,
) -> TaskSplit:
    """Partition ``task_ids`` into optimize, held-out, and reserve groups.

    The partition is derived from ``sha256(seed, task_id)`` rank, so it is
    identical on every machine and independent of input order. Group sizes are
    exact rather than approximate: hash bucketing can hand a ten-task eval set a
    one-task gate, which measures nothing.

    Adding or removing a task changes ``fingerprint``. That is deliberate. A
    different eval set means the incumbent score was measured against something
    else and has to be earned again.

    Raises:
        ValueError: on empty, blank, or duplicate ids, an empty seed, ratios
            outside ``(0, 1)``, or ratios leaving no optimize tasks.
        SplitTooSmallError: when the held-out group is smaller than ``min_sel``.
    """
    if not task_ids:
        raise ValueError("split_tasks requires at least one task id")
    if not seed or not seed.strip():
        raise ValueError("split_tasks requires a non-empty seed")
    sel_display = _ratio_display(str(sel_ratio))
    test_display = _ratio_display(str(test_ratio))
    sel_fraction = _ratio_fraction("sel_ratio", sel_ratio)
    test_fraction = _ratio_fraction("test_ratio", test_ratio)
    if not Fraction(0) < sel_fraction < Fraction(1):
        raise ValueError(f"sel_ratio must be strictly between 0 and 1, got {sel_display}")
    if not Fraction(0) <= test_fraction < Fraction(1):
        raise ValueError(f"test_ratio must be in [0, 1), got {test_display}")
    if min_sel < 0:
        raise ValueError(f"min_sel must be non-negative, got {min_sel}")
    if sel_fraction + test_fraction >= Fraction(1):
        raise ValueError(
            f"sel_ratio + test_ratio must leave at least one opt task, "
            f"got {sel_display} + {test_display}"
        )

    cleaned: list[str] = []
    for raw in task_ids:
        if raw != raw.strip():
            raise ValueError(
                f"task id {raw!r} carries leading or trailing whitespace; "
                f"ids must match the keys the scorer emits exactly"
            )
        if not raw:
            raise ValueError("split_tasks requires non-empty task ids")
        cleaned.append(raw)

    if len(set(cleaned)) != len(cleaned):
        duplicates = sorted({tid for tid in cleaned if cleaned.count(tid) > 1})
        raise ValueError(f"split_tasks received duplicate task ids: {', '.join(duplicates)}")

    total = len(cleaned)
    n_sel = _round_half_up(Fraction(total) * sel_fraction)
    n_test = _round_half_up(Fraction(total) * test_fraction)
    if total - n_sel - n_test < 1:
        raise ValueError(
            f"split of {total} tasks at sel_ratio={sel_display} "
            f"test_ratio={test_display} "
            f"leaves no opt tasks"
        )
    if n_sel < 1:
        raise SplitTooSmallError(
            f"split of {total} tasks at sel_ratio={sel_display} holds out no tasks; "
            f"a gate needs at least one held-out task"
        )
    if n_sel < min_sel:
        raise SplitTooSmallError(
            f"held-out split has {n_sel} task(s), below min_sel={min_sel}; "
            f"widen the eval set or lower min_sel to gate on it"
        )

    ranked = sorted(
        cleaned,
        key=lambda tid: hashlib.sha256(f"{seed}\x00{tid}".encode()).hexdigest(),
    )
    sel = tuple(ranked[:n_sel])
    test = tuple(ranked[n_sel : n_sel + n_test])
    opt = tuple(ranked[n_sel + n_test :])

    fingerprint = split_fingerprint(
        cleaned, seed=seed, sel_ratio=sel_ratio, test_ratio=test_ratio
    )
    return TaskSplit(opt=opt, sel=sel, test=test, fingerprint=fingerprint)


def split_fingerprint(
    task_ids: Iterable[str],
    *,
    seed: str,
    sel_ratio: Ratio,
    test_ratio: Ratio = 0.0,
) -> str:
    """Hash the inputs that determine a split.

    Public rather than private because a reader has to be able to recompute
    this from a split file's own contents. A stored fingerprint that nobody
    can recompute is a claim, not evidence: editing group membership while
    leaving the recorded hash alone would go unnoticed.

    Order-insensitive by design. The task set determines the split; the order
    it arrived in does not.
    """
    payload = json.dumps(
        {
            "seed": seed,
            "tasks": sorted(task_ids),
            "sel_ratio": _canonical_ratio(sel_ratio, name="sel_ratio"),
            "test_ratio": _canonical_ratio(test_ratio, name="test_ratio"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def edit_budget(step: int, total: int, *, max_edits: int = 5, min_edits: int = 1) -> int:
    """Return how many patches step ``step`` of ``total`` may propose.

    Cosine decay: the first step gets ``max_edits`` so early exploration can
    restructure, the last gets ``min_edits`` so late steps can only make small,
    reversible edits. Steps past ``total`` clamp to the floor.

    Raises:
        ValueError: on a negative step, a non-positive total, or bounds where
            ``min_edits`` is below 1 or above ``max_edits``.
    """
    if step < 0:
        raise ValueError(f"step must be non-negative, got {step}")
    if total <= 0:
        raise ValueError(f"total must be positive, got {total}")
    if min_edits < 1:
        raise ValueError(f"min_edits must be at least 1, got {min_edits}")
    if min_edits > max_edits:
        raise ValueError(f"min_edits ({min_edits}) must not exceed max_edits ({max_edits})")

    clamped = min(step, total)
    span = (max_edits - min_edits) * 0.5
    decayed = min_edits + span * (1.0 + math.cos(math.pi * clamped / total))
    return max(min_edits, min(max_edits, round(decayed)))


def _normalize_newlines(text: str) -> str:
    """Collapse CRLF and lone CR to LF.

    One canonical form, used by every place that reasons about lines. When the
    document splitter and the fence-marker check disagreed on whether a lone
    carriage return starts a new line, a patch carrying "START\\rhidden\\rEND"
    read as one harmless line at check time and became a real fence on the next
    read. Sharing this helper is what keeps the two views from drifting apart.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _split_lines(document: str) -> list[str]:
    """Split into lines, dropping exactly one trailing newline."""
    lines = _normalize_newlines(document).split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _join_lines(lines: Sequence[str]) -> str:
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _protected_indices(lines: Sequence[str]) -> frozenset[int]:
    """Return every line index inside a slow-update fence, markers included.

    Raises:
        ProtectedSectionError: on a nested, unclosed, or unbalanced fence. The
            document shape is checked before any patch applies, so a malformed
            fence fails closed rather than leaving rails unprotected.
    """
    protected: set[int] = set()
    open_at: int | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == FENCE_START:
            if open_at is not None:
                raise ProtectedSectionError(
                    f"nested slow-update fence: second start at line {index + 1}"
                )
            open_at = index
        elif stripped == FENCE_END:
            if open_at is None:
                raise ProtectedSectionError(
                    f"unbalanced slow-update fence: end at line {index + 1} with no start"
                )
            protected.update(range(open_at, index + 1))
            open_at = None
    if open_at is not None:
        raise ProtectedSectionError(
            f"unclosed slow-update fence: start at line {open_at + 1} is never closed"
        )
    return frozenset(protected)


def _validate_shape(patch: Patch) -> None:
    if patch.op not in _VALID_OPS:
        raise PatchShapeError(
            f"unknown patch op {patch.op!r}; expected one of {sorted(_VALID_OPS)}"
        )
    if patch.op in _ANCHORED_OPS and (patch.anchor is None or not patch.anchor.strip()):
        raise PatchShapeError(f"patch op {patch.op!r} requires a non-blank anchor")
    if patch.op in _TEXT_OPS and patch.text is None:
        raise PatchShapeError(f"patch op {patch.op!r} requires text")


def _check_patch_fields(patch: Patch) -> None:
    """Refuse a patch whose fields are not the types the ops assume.

    Patches arrive as agent-authored JSON, so a number where a string belongs
    is an ordinary input error, not an internal fault. Checking here turns an
    uncaught AttributeError deep inside the anchor search into a named error
    the CLI can report as a shape problem.
    """
    if not isinstance(patch.op, str):
        raise PatchShapeError(f"patch op must be a string, got {type(patch.op).__name__}")
    if patch.anchor is not None and not isinstance(patch.anchor, str):
        raise PatchShapeError(f"patch anchor must be a string, got {type(patch.anchor).__name__}")
    if patch.text is not None and not isinstance(patch.text, str):
        raise PatchShapeError(f"patch text must be a string, got {type(patch.text).__name__}")


def _reject_smuggled_markers(patch: Patch) -> None:
    """Refuse patch text that would introduce a fence marker.

    Without this a patch could open its own fence and make the next step's edits
    unreachable, or close an existing one and expose the rails inside it.
    """
    if patch.text is None:
        return
    for line in _normalize_newlines(patch.text).split("\n"):
        if line.strip() in (FENCE_START, FENCE_END):
            raise ProtectedSectionError(
                "patch text may not contain a slow-update fence marker; "
                f"found {line.strip()!r}"
            )


def _locate(lines: Sequence[str], anchor: str) -> int:
    needle = anchor.strip()
    matches = [index for index, line in enumerate(lines) if line.strip() == needle]
    if not matches:
        raise AnchorNotFoundError(f"anchor {needle!r} does not appear in the document")
    if len(matches) > 1:
        raise AmbiguousAnchorError(
            f"anchor {needle!r} appears {len(matches)} times; anchors must be unique"
        )
    return matches[0]


def apply_patches(document: str, patches: Sequence[Patch], *, budget: int) -> str:
    """Apply ``patches`` to ``document`` under a hard edit budget.

    Patches apply in order, so a later patch may anchor on a line an earlier one
    wrote. Every anchor must be unique at the moment its patch runs; an
    ambiguous anchor is refused rather than resolved by picking the first match.
    Nothing inside a slow-update fence can be touched.

    A refusal here means the proposed edit was malformed or out of bounds. It is
    not a statement about quality; that is :func:`gate`'s job.

    Raises:
        ValueError: on a negative budget.
        BudgetExceededError: when more patches are proposed than allowed.
        PatchShapeError: when a patch omits a field its op requires.
        AnchorNotFoundError: when an anchor is absent.
        AmbiguousAnchorError: when an anchor is not unique.
        ProtectedSectionError: when a patch targets or introduces fenced content.
    """
    if budget < 0:
        raise ValueError(f"budget must be non-negative, got {budget}")
    if len(patches) > budget:
        raise BudgetExceededError(
            f"{len(patches)} patches exceed this step's edit budget of {budget}"
        )

    lines = _split_lines(document)
    for patch in patches:
        _check_patch_fields(patch)
        _validate_shape(patch)
        _reject_smuggled_markers(patch)
        protected = _protected_indices(lines)

        if patch.op == "append":
            lines = [*lines, *_normalize_newlines(patch.text or "").split("\n")]
            continue

        assert patch.anchor is not None  # guaranteed by _validate_shape
        index = _locate(lines, patch.anchor)
        if index in protected:
            raise ProtectedSectionError(
                f"anchor {patch.anchor.strip()!r} is inside a slow-update fence; "
                f"fenced guidance is edited by hand at epoch boundaries, not by the optimizer"
            )

        if patch.op == "delete":
            lines = [*lines[:index], *lines[index + 1 :]]
        elif patch.op == "replace":
            payload = _normalize_newlines(patch.text or "").split("\n")
            lines = [*lines[:index], *payload, *lines[index + 1 :]]
        else:  # insert_after
            payload = _normalize_newlines(patch.text or "").split("\n")
            lines = [*lines[: index + 1], *payload, *lines[index + 1 :]]

    return _join_lines(lines)


def mcnemar_exact(
    incumbent: Mapping[str, bool],
    candidate: Mapping[str, bool],
    task_ids: Sequence[str],
) -> tuple[int, int, float]:
    """Return ``(b, c, p)`` for a one-sided exact McNemar test.

    The gate reads the same task ids before and after an edit, so the two
    scores are paired. Tasks whose outcome did not move say nothing about the
    edit; only the discordant pairs do. ``b`` counts fail to pass, ``c`` counts
    pass to fail. Under the null that the edit is neutral, ``b`` is
    ``Binomial(b + c, 0.5)``, and the reported ``p`` is ``P(X >= b)``.

    Exact rather than chi-squared, because this repo's eval sets are small
    enough that the asymptotic form does not apply. The number is worth
    reporting precisely because it makes the resolution limit impossible to
    talk around: three discordant tasks cannot produce a ``p`` below 0.125, so
    a three-task held-out group cannot clear a conventional 0.05 floor no
    matter how the edit performs.

    The returned ``p`` is never exactly zero. No finite number of paired
    observations drives the exact probability to zero, so a caller comparing
    against a bar of zero gets a refusal rather than a pass.

    Raises:
        MissingResultError: when a requested task is absent from either side.
    """
    unique = sorted(set(task_ids))
    for label, results in (("incumbent", incumbent), ("candidate", candidate)):
        missing = [task_id for task_id in unique if task_id not in results]
        if missing:
            raise MissingResultError(f"{label} has no result for: {', '.join(missing)}")

    b = sum(1 for t in unique if not incumbent[t] and candidate[t])
    c = sum(1 for t in unique if incumbent[t] and not candidate[t])
    n = b + c
    if n == 0:
        return 0, 0, 1.0

    tail = sum(math.comb(n, k) for k in range(b, n + 1))
    p = tail / (2**n)
    if p == 0.0:
        # The tail always contains the k=b term, so `tail` is at least 1 and
        # the exact probability is strictly positive for every input that
        # reaches here. Past n=1074 the ratio falls below the smallest
        # subnormal and the float conversion reports 0.0 instead. Publishing
        # that zero would make `--max-p 0`, the strictest bar the flag can
        # express, read as satisfied, so the strictest possible bar would be
        # the one that accepts. Report the smallest positive float instead:
        # still far below any usable bar, but honest about being nonzero.
        p = math.nextafter(0.0, 1.0)
    return b, c, p


def score(results: Mapping[str, bool], task_ids: Sequence[str]) -> float:
    """Return the passing fraction of ``task_ids``.

    A task with no entry in ``results`` raises rather than counting as a
    failure. Treating an absent result as a fail lets a truncated or crashed
    rollout quietly change a score, which is the one thing the gate must not
    tolerate.

    Raises:
        ValueError: when ``task_ids`` is empty.
        MissingResultError: when any requested task has no result.
        TypeError: when a result is not a bool.
    """
    if not task_ids:
        raise ValueError("score requires at least one task id")

    unique = sorted(set(task_ids))
    missing = [task_id for task_id in unique if task_id not in results]
    if missing:
        raise MissingResultError(f"no result recorded for: {', '.join(missing)}")

    for task_id in unique:
        value = results[task_id]
        if not isinstance(value, bool):
            raise TypeError(f"result for {task_id!r} must be a bool, got {type(value).__name__}")

    return sum(1 for task_id in unique if results[task_id]) / len(unique)


def guard_refusal(
    *,
    sel_consultations: int = 0,
    max_consultations: int | None = None,
    split_fingerprint: str | None = None,
    incumbent_fingerprint: str | None = None,
) -> str | None:
    """Return why a comparison must not happen, or None when it may.

    Split out of ``gate`` so a caller can ask before it scores anything. Both
    refusals are decidable from bookkeeping alone, and a caller that scores
    first has already read the held-out group: the refusal then costs exactly
    what it was meant to prevent.

    The cap is validated here rather than only in ``gate`` because callers
    reach this function first. A cap below one would otherwise read as a
    permanently exhausted budget, which is indistinguishable from legitimate
    discipline: every gate refuses, and the reason names a limit the operator
    never meant to set.
    """
    if sel_consultations < 0:
        raise ValueError(f"sel_consultations must be non-negative, got {sel_consultations}")
    if max_consultations is not None and max_consultations < 1:
        raise ValueError(f"max_consultations must be positive, got {max_consultations}")

    if (
        split_fingerprint is not None
        and incumbent_fingerprint is not None
        and split_fingerprint != incumbent_fingerprint
    ):
        return (
            "split fingerprint moved since the incumbent was scored; re-baseline "
            "on the current eval set before gating"
        )

    if max_consultations is not None and sel_consultations >= max_consultations:
        return (
            f"held-out split exhausted after {sel_consultations} consultations "
            f"(limit {max_consultations}); re-split to gate against a fresh group"
        )

    return None


def gate(
    candidate: float,
    incumbent: float,
    *,
    sel_consultations: int = 0,
    max_consultations: int | None = None,
    split_fingerprint: str | None = None,
    incumbent_fingerprint: str | None = None,
    discordant_loss: int = 0,
    p_value: float | None = None,
    max_p: float | None = None,
) -> GateResult:
    """Decide whether a candidate replaces the incumbent.

    Strictly greater wins. A tie is a reject: an edit that did not move the
    held-out score is churn, and churn on an artifact costs review attention
    forever.

    Two guards run before the comparison. A moved ``split_fingerprint`` means
    the candidate and the incumbent were measured against different eval sets,
    so the comparison is meaningless. An exhausted consultation budget means the
    held-out split has been selected against too many times to carry the claim.

    ``discordant_loss`` is the number of held-out tasks that passed before the
    edit and fail after it. A net gain can still contain one, and ADR-057
    blocks every pass-to-fail transition rather than netting it against a gain,
    so one broken task rejects the edit however good the aggregate looks.

    There is deliberately no override. ADR-057 states that its gate "has no
    mechanism to accept a justified regression"; a bypass here would be a
    weaker rule wearing the same name, and an agent driving this loop could
    set it without a human ever seeing the broken task.

    ``max_p`` is the largest one-sided exact McNemar tail this gate will
    accept **across the whole consultation budget**, not per comparison. It
    defaults to None because a small held-out group cannot reach a
    conventional floor; enforcing one by default would make the common case
    unpassable rather than informative. Set it when the group is large enough
    that the tail carries information. A live run over 24 rule scenarios
    scored the identical artifact twice and moved the held-out group 6/10 to
    7/10 with no input change, so on a nondeterministic scorer a
    strictly-greater rule alone accepts variance.

    The budget is what makes the correction necessary. A loop permitted five
    consultations that applies 0.05 to each one independently does not deliver
    the 0.05 the operator asked for. Bounding the family without assuming
    anything about dependence gives 5 * 0.05 = 0.25 by the union bound; the
    exact 1 - 0.95**5, about 0.226, holds only if the five comparisons are
    independent, and five looks at one selection group are not. So ``max_p``
    is read as the family bar and spent across ``max_consultations`` by
    Bonferroni: each comparison is held to ``max_p / max_consultations``. That
    correction controls the family bar under arbitrary dependence among the
    p-values, which is why it is used here rather than a sharper
    independence-dependent one. Raising the budget therefore buys more looks
    at a stricter bar, never a cheaper one.

    That guarantee is conditional, and the condition is not free. Bonferroni
    tolerates any dependence between the comparisons, but it still requires
    each per-comparison p-value to be valid on its own: under the null a valid
    p must satisfy P(p <= a) <= a. ``mcnemar_exact`` earns that only if the
    discordant pairs behave as independent fair coin flips under the null, and
    correlated scorer noise breaks it. This is not hypothetical here. A
    rule-path null control in this repo restored the artifact byte for byte
    and reproduced both of the gains the real edit had produced, which is
    direct evidence that outcomes on this harness move together. So the
    honest statement is that the family bar holds under any dependence
    between the comparisons, given per-comparison validity, and that the
    second half is the part this harness does not guarantee.

    Both companions are required rather than optional, because a bar that
    silently does not apply is worse than no bar. ``max_p`` without
    ``p_value`` raises: an unknown tail is not evidence that it clears the
    bar. ``max_p`` without ``max_consultations`` raises: an undeclared family
    size cannot be corrected for. ``p_value`` without ``max_p`` changes
    nothing, since reporting the tail was always allowed.

    Raises:
        ValueError: on scores outside ``[0, 1]``, negative consultations, a
            non-positive consultation cap, a negative discordant count, a
            ``p_value`` or ``max_p`` outside ``[0, 1]``, or ``max_p`` given
            without both ``p_value`` and ``max_consultations``.
    """
    if not 0.0 <= candidate <= 1.0:
        raise ValueError(f"candidate score must be in [0, 1], got {candidate}")
    if not 0.0 <= incumbent <= 1.0:
        raise ValueError(f"incumbent score must be in [0, 1], got {incumbent}")
    if sel_consultations < 0:
        raise ValueError(f"sel_consultations must be non-negative, got {sel_consultations}")
    if max_consultations is not None and max_consultations < 1:
        raise ValueError(f"max_consultations must be positive, got {max_consultations}")
    if discordant_loss < 0:
        raise ValueError(f"discordant_loss must be non-negative, got {discordant_loss}")
    if p_value is not None and not 0.0 <= p_value <= 1.0:
        raise ValueError(f"p_value must be in [0, 1], got {p_value}")
    if max_p is not None and not 0.0 <= max_p <= 1.0:
        raise ValueError(f"max_p must be in [0, 1], got {max_p}")
    if max_p is not None and p_value is None:
        raise ValueError(
            "max_p needs a p_value to judge; an unknown tail is not evidence "
            "that it clears the bar"
        )
    if max_p is not None and max_consultations is None:
        raise ValueError(
            "max_p needs max_consultations; the bar is spent across the "
            "budget, so an undeclared family size cannot be corrected for"
        )

    def _result(decision: str, reason: str, *, compared: bool = True) -> GateResult:
        return GateResult(
            decision=decision,
            reason=reason,
            candidate=candidate,
            incumbent=incumbent,
            sel_consultations=sel_consultations,
            compared=compared,
        )

    refusal = guard_refusal(
        sel_consultations=sel_consultations,
        max_consultations=max_consultations,
        split_fingerprint=split_fingerprint,
        incumbent_fingerprint=incumbent_fingerprint,
    )
    if refusal is not None:
        return _result("REJECT", refusal, compared=False)

    if candidate > incumbent:
        if discordant_loss:
            return _result(
                "REJECT",
                f"candidate {candidate:.4f} beats {incumbent:.4f} overall but "
                f"regressed {discordant_loss} held-out task(s) from pass to fail; "
                f"a net gain does not buy back a broken task",
            )
        # Last, because a broken task is the finding worth naming first even
        # when both refusals apply. The bar is family-wise, so it is spent
        # across the declared budget rather than applied whole to each look.
        if max_p is not None and p_value is not None and max_consultations is not None:
            corrected = max_p / max_consultations
            if p_value > corrected:
                return _result(
                    "REJECT",
                    f"candidate {candidate:.4f} beats {incumbent:.4f} but the "
                    f"one-sided exact McNemar tail is {p_value:g}, above the "
                    f"per-comparison bar of {corrected:g}, which is the "
                    f"{max_p:g} family bar divided across {max_consultations} "
                    f"consultation(s). The gain is not distinguishable from "
                    f"scorer variance at this held-out size",
                )
        return _result("ACCEPT", f"candidate {candidate:.4f} strictly beats {incumbent:.4f}")
    if candidate == incumbent:
        return _result("REJECT", f"tie at {candidate:.4f}; a tie does not earn an edit")
    return _result("REJECT", f"candidate {candidate:.4f} regressed from {incumbent:.4f}")


def patch_fingerprint(patches: Sequence[Patch]) -> str:
    """Return a stable identity for a proposed edit.

    Order-sensitive and text-exact, because both are load-bearing. Patches
    apply sequentially, so appending "one" then "two" builds a different
    document from the reverse; and whitespace is content, since a newline in
    patch text splits one line into two. Only line endings are normalized,
    which is transport rather than content.

    The bias here is deliberate. A fingerprint that treats two different edits
    as the same one lets a single rejection ban an edit that was never tried,
    and the buffer has no expiry. Collapsing too little costs a duplicate
    rollout; collapsing too much costs an edit that can never be proposed
    again.

    Raises:
        ValueError: when ``patches`` is empty, or when a patch field is not
            the type the fingerprint assumes.
    """
    if not patches:
        raise ValueError("patch_fingerprint requires at least one patch")
    for patch in patches:
        # The same guard `apply_patches` runs, for the same reason. Both are
        # public entry points fed agent-authored JSON, and both reach
        # `_normalize_newlines`, so a number where a string belongs raised an
        # AttributeError out of one and a named refusal out of the other. The
        # check sits here rather than in the two buffer commands because every
        # path that can crash routes through this function, including
        # `buffer_contains`, and a caller added later would need it too.
        _check_patch_fields(patch)

    canonical = [
        [
            patch.op,
            _normalize_newlines(patch.anchor) if patch.anchor is not None else "",
            _normalize_newlines(patch.text) if patch.text is not None else "",
        ]
        for patch in patches
    ]
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def buffer_contains(entries: Iterable[Mapping[str, object]], patches: Sequence[Patch]) -> bool:
    """Report whether this edit has already been rejected.

    Entries without a usable ``fingerprint`` are skipped rather than raising, so
    one hand-edited line in the ledger cannot stop the loop.

    Raises:
        ValueError: when ``patches`` is empty.
    """
    target = patch_fingerprint(patches)
    for entry in entries:
        stored = entry.get("fingerprint")
        if isinstance(stored, str) and stored == target:
            return True
    return False
