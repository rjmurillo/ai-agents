"""Independent reviewer arm contract for the durable-outcome drivers (issue #5768).

Pure, stdlib only: no subprocess, no file I/O, no model calls. The two
drivers (`_durable_live.py`, `eval_control_ablation.py`) launch the reviewer
process themselves and hand its reply text to `parse_review`.

Why a reviewer arm exists. `review_findings` was written as a literal `0`
because no driver ran a reviewer. That is an unmeasured value, not a measured
absence of defects. A record now carries one of three states:

* the reviewer ran and replied in the required shape: the finding count;
* the reviewer did not run, failed, or replied in another shape: `None`, which
  `_durable_outcome.classify` turns into `UNVERIFIED`;
* a run that was never accepted: `None` as well, because no accepted change
  reached the reviewer. Those runs classify `REJECTED` before the null check.

Independence. The reviewer is a separate process in a fresh directory. It
sees the requirement and the accepted change, never the producer's messages,
the hidden checks, or either control's instruction files. Every control gets
the same reviewer text, model, and effort, so `RunConfig.reviewer` matches
across controls and `compare` accepts the pair.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

#: `RunConfig.reviewer` value for a run with no reviewer arm.
NO_REVIEWER = "none"

#: `RunConfig.reviewer` value for `--dry-run` rows, whose reviewer reply is a canned fixture.
DRY_RUN_REVIEWER = "dry-run-fixture"

#: Suffix the live driver adds to a control name for the reviewer's launches in `invocations.jsonl`.
REVIEWER_CONTROL_SUFFIX = ":reviewer"

#: The reviewer must end its reply with one line that starts with this marker.
REVIEW_MARKER = "REVIEW_RESULT:"

#: Read-only tool names the reviewer may use. It never edits or runs code.
REVIEW_TOOLS: tuple[str, ...] = ("Read", "Glob", "Grep")

#: Identical for every control. The live driver appends it as a system prompt file.
#: The ablation driver puts it at the start of the reviewer's user prompt.
REVIEWER_INSTRUCTIONS = (
    "You are an independent code reviewer. You did not write this change and you have "
    "no access to the author's reasoning. Read the changed files and judge them against "
    "the stated requirement. Report only concrete defects: behavior that violates the "
    "requirement, a plausible but wrong approach, a missed edge case, or a change outside "
    "the requirement. Do not report style, naming, or taste. Do not edit files.\n"
    f"End your reply with exactly one line: {REVIEW_MARKER} "
    '{"findings": ["<one defect per string>"]}. '
    'Use {"findings": []} when you found no defect.'
)


@dataclass(frozen=True, slots=True)
class ReviewerSpec:
    """Which harness, model, and effort run the reviewer arm."""

    harness: str
    model: str
    effort: str

    def __post_init__(self) -> None:
        for name in ("harness", "model", "effort"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or ":" in value:
                raise ValueError(f"reviewer {name} must be a non-empty string without ':'")

    @property
    def identity(self) -> str:
        """`RunConfig.reviewer` text: harness, requested model, effort.

        The requested model, not the observed one: a run that never launched
        the reviewer has no observed model, and one file must hold one string.
        The observed model is in `invocations.jsonl`.
        """
        return f"{self.harness}:{self.model}:{self.effort}"


def reviewer_identity(spec: ReviewerSpec | None) -> str:
    """`RunConfig.reviewer` for `spec`, or `none` when no reviewer arm is configured."""
    return NO_REVIEWER if spec is None else spec.identity


def review_prompt(requirement: str, changed: Sequence[str]) -> str:
    """The reviewer's task text: the requirement and the paths the accepted change touched."""
    paths = "\n".join(f"- {path}" for path in changed) or "- (no changed paths)"
    return (
        "Review the accepted change in the working directory.\n\n"
        f"Requirement:\n{requirement}\n\n"
        f"Changed paths:\n{paths}\n\n"
        "Read those files and any file they depend on. "
        f"Finish with the {REVIEW_MARKER} line."
    )


def parse_review(text: str) -> int | None:
    """Return the reviewer's finding count, or `None` when the reply is not in the required shape.

    Only the last `REVIEW_MARKER` line counts, so a quoted earlier example
    cannot set the result. The payload must be a JSON object with exactly one
    key, `findings`, holding a list of non-empty strings. Anything else is
    `None`: a malformed reply is missing evidence, never zero findings.
    """
    marked = [line.strip() for line in text.splitlines() if line.strip().startswith(REVIEW_MARKER)]
    if not marked:
        return None
    try:
        payload = json.loads(marked[-1][len(REVIEW_MARKER) :])
    except ValueError:
        return None
    if not isinstance(payload, dict) or set(payload) != {"findings"}:
        return None
    findings = payload["findings"]
    if not isinstance(findings, list):
        return None
    if not all(isinstance(item, str) and item.strip() for item in findings):
        return None
    return len(findings)
