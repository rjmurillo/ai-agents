"""Rules for an agent's declared success criterion (ADR-065 Decision 2, issue #7639).

Every agent declares, in a top-level ``success_criterion`` frontmatter key,
the one signal that says its work succeeded. The router, not the agent, reads
it. ``check_agent_success_criterion.py`` applies these rules to every rendered
agent.

Shape:

- ``kind``: one of ``KINDS``.
- ``value``: required for every kind except ``human-judgment``, and forbidden
  for that kind. ``exit-code`` takes an integer from 0 to 255. ``regex`` takes
  a pattern that compiles. ``schema`` and ``test`` take a non-empty string
  naming the schema or the test.
- ``rationale``: one sentence on what the signal proves and what it does not.
  ADR-065 requires it for ``human-judgment``. This gate requires it for every
  kind, because a format check such as a verdict-line regex proves the reply
  is well formed, not that the work is right, and the reader needs to know
  which one they are getting.

The ``human-judgment`` escape hatch is the one ADR-065 says will be abused if
the rationale is not enforced. So a rationale must clear a length floor, must
not be placeholder text, and must not be copied from another agent: one
sentence pasted into every file says nothing about any of them. The copy
check folds case and whitespace only, so it catches a pasted sentence, not a
paraphrase; judging a paraphrase stays a review duty.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

CRITERION_KEY = "success_criterion"

HUMAN_JUDGMENT = "human-judgment"
KINDS = frozenset({"exit-code", "schema", "regex", "test", HUMAN_JUDGMENT})
FIELDS = frozenset({"kind", "value", "rationale"})

MIN_RATIONALE_CHARS = 40
MIN_RATIONALE_WORDS = 6
MAX_EXIT_CODE = 255

# Text that fills the field without saying anything. Matched as whole words,
# case-insensitively, anywhere in the rationale.
_PLACEHOLDER = re.compile(r"\b(tbd|todo|fixme|n/a|placeholder|lorem|xxx)\b", re.IGNORECASE)


def normalize_rationale(text: str) -> str:
    """Return the rationale with case and whitespace folded, for duplicate checks."""
    return " ".join(text.lower().split())


def _check_value(kind: str, criterion: Mapping[str, object]) -> list[str]:
    has_value = "value" in criterion
    value = criterion.get("value")
    if kind == HUMAN_JUDGMENT:
        if has_value:
            return ["kind 'human-judgment' takes no 'value' (put the reason in 'rationale')"]
        return []
    if not has_value:
        return [f"kind '{kind}' requires a 'value'"]
    if kind == "exit-code":
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= MAX_EXIT_CODE:
            return [f"kind 'exit-code' needs an integer from 0 to {MAX_EXIT_CODE}, got {value!r}"]
        return []
    if not isinstance(value, str) or not value.strip():
        return [f"kind '{kind}' needs a non-empty string value, got {value!r}"]
    if kind == "regex":
        try:
            re.compile(value)
        except re.error as exc:
            return [f"kind 'regex' value does not compile: {exc}"]
    return []


def _check_rationale(criterion: Mapping[str, object]) -> list[str]:
    rationale = criterion.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        return ["'rationale' must be a non-empty string"]
    text = rationale.strip()
    findings: list[str] = []
    if len(text) < MIN_RATIONALE_CHARS or len(text.split()) < MIN_RATIONALE_WORDS:
        findings.append(
            f"'rationale' is too short to explain anything (needs at least "
            f"{MIN_RATIONALE_CHARS} characters and {MIN_RATIONALE_WORDS} words)"
        )
    match = _PLACEHOLDER.search(text)
    if match:
        findings.append(f"'rationale' contains placeholder text '{match.group(0)}'")
    return findings


def check_criterion(criterion: object) -> list[str]:
    """Return findings for one declared criterion; empty when it is valid.

    ``criterion`` is the raw value of the ``success_criterion`` key, or
    ``None`` when the agent declares none.
    """
    if criterion is None:
        return [
            f"no top-level {CRITERION_KEY} declared (add kind, rationale, and value "
            "unless kind is human-judgment; ADR-065 Decision 2)"
        ]
    if not isinstance(criterion, Mapping):
        return [f"{CRITERION_KEY} must be a mapping, got {type(criterion).__name__}"]
    findings = [
        f"unknown field '{key}' (allowed: {', '.join(sorted(FIELDS))})"
        for key in sorted(str(k) for k in criterion if k not in FIELDS)
    ]
    kind = criterion.get("kind")
    if not isinstance(kind, str) or kind not in KINDS:
        findings.append(f"'kind' must be one of {', '.join(sorted(KINDS))}, got {kind!r}")
    else:
        findings.extend(_check_value(kind, criterion))
    findings.extend(_check_rationale(criterion))
    return findings


def duplicate_rationales(rationales: Mapping[str, str]) -> dict[str, list[str]]:
    """Map each agent to the other agents that share its rationale text.

    ``rationales`` maps agent name to rationale. Only agents that share text
    appear in the result.
    """
    by_text: dict[str, list[str]] = {}
    for name, text in rationales.items():
        by_text.setdefault(normalize_rationale(text), []).append(name)
    shared: dict[str, list[str]] = {}
    for names in by_text.values():
        if len(names) < 2:
            continue
        for name in names:
            shared[name] = sorted(other for other in names if other != name)
    return shared
