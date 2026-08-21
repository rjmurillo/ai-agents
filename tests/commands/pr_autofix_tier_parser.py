"""Tier-set extractors behind `test_pr_autofix_tier_contract.py`.

Refs #5094. The `/pr-autofix` tier guard has to agree with the producer about
two separate things, and collapsing them is what put `SKIP` on the acting path:

- **Recognition**: every value `classify_tier` can return must be named in some
  arm of the guard, or a healthy classification reads as a producer failure.
- **Dispatch**: only the actionable ones may fall through to the gates. The
  command's tier table defines `SKIP` as "Draft, merged, or closed", "No
  action", so it is recognized and must still terminate.

Split from `pr_autofix_field_parser.py` so each module stays under the 500-line
taste rule, following the `step0_parser.py` precedent in this directory. This
module holds no assertions; it is the parser the tests drive.

Public symbols:

- `recognized_tiers(text)`: every tier the guard names, in any arm
- `dispatched_tiers(text)`: tiers whose arm is a no-op, so the loop keeps going
- `declared_tiers(script)`: the producer's own `_TIER_ORDER`, read with `ast`
"""

from __future__ import annotations

import ast
import re

from tests.commands.pr_autofix_field_parser import PRODUCER_DIR

_TIER_PASSTHROUGH = re.compile(
    r"^\s*((?:[A-Z][A-Z0-9]*\|)*[A-Z][A-Z0-9]*)\)\s*;;\s*$", re.MULTILINE
)


def _tier_case_block(text: str) -> str | None:
    """The `case "$TIER" in ... esac` block, or None when the guard is absent."""
    match = re.search(r'case "\$TIER" in\n(.*?)\nesac', text, re.DOTALL)
    return match.group(1) if match else None


def recognized_tiers(text: str) -> frozenset[str] | None:
    """Every tier the guard names in any arm, terminating or pass-through.

    Recognition is the property that must equal the producer's declared set. It
    is deliberately separate from dispatch: a tier can be recognized and still
    terminate, which is what `SKIP` does.
    """
    block = _tier_case_block(text)
    if block is None:
        return None
    tiers: set[str] = set()
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.endswith(")") and not stripped.endswith(") ;;"):
            continue
        label = stripped.removesuffix(";;").strip().removesuffix(")")
        if not label or label == "*":
            continue
        if all(part.isupper() or part.isdigit() for part in label.replace("|", "")):
            tiers.update(label.split("|"))
    return frozenset(tiers) if tiers else None


def dispatched_tiers(text: str) -> frozenset[str] | None:
    """Tiers whose arm is a no-op, so the loop keeps acting on them.

    The pass-through arm is the one written `T1|T2|...) ;;` with no body. A tier
    outside it either terminates or is unrecognized.

    Every such arm is unioned, not just the first. `search` stopped at the first
    match, which made this function blind to exactly the defect it exists to
    catch: a second empty arm, `SKIP) ;;`, put `SKIP` back on the acting path
    and both assertions in `test_skip_is_recognized_but_never_dispatched` still
    passed, because `SKIP` was absent from the returned set and the set still
    equalled `declared - {"SKIP"}`. A guard that reports green on its own
    subject is the failure this suite is named for; CodeRabbit found this one.
    """
    block = _tier_case_block(text)
    if block is None:
        return None
    tiers: set[str] = set()
    for match in _TIER_PASSTHROUGH.finditer(block):
        tiers.update(match.group(1).split("|"))
    return frozenset(tiers)


def declared_tiers(script: str = "test_pr_merge_ready") -> tuple[str, ...] | None:
    """The producer's own `_TIER_ORDER`, read from its source with `ast`.

    `classify_tier`'s docstring names this tuple as the range of its return
    value, so it is the canonical set a consumer may see. Reading it here rather
    than restating it is what stops the command's guard from being written
    against a remembered contract, which is how the guard first shipped
    rejecting BEHIND, BLOCKED, DIRTY, and SKIP.
    """
    tree = ast.parse((PRODUCER_DIR / f"{script}.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id == "_TIER_ORDER"):
                continue
            if not isinstance(node.value, ast.Tuple):
                return None
            values = [
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
            return tuple(values) if len(values) == len(node.value.elts) else None
    return None
