"""Enforcement messages must not tell their reader to apply a human-only label.

Issue #4782: a gate's own enforcement message instructed whoever tripped it to
grant themselves a permission they do not hold, which is what makes an agent
read a bypass label as sanctioned remediation. One did: an agent working PR
#4735 applied the `commit-limit-bypass` label to that PR on 2026-08-08 after
hitting the gate that used to enforce it.

ADR-099 removed the `commit-limit-bypass` gate entirely (the commit-count
block and its human-only label): the local verification step could not always
reach GitHub to confirm the label, and the only mitigation this file used to
pin (state the sanctioned action, name the authority, forbid self-application,
never phrase it as an instruction) does not apply to a mechanism that no
longer exists. What remains with the same shape is
`description-validation-bypass` (`scripts/validation/pr_description.py`),
untouched by ADR-099, and this file now tests only that one.

Canonical authority: ``CONTRIBUTING.md``, quoted verbatim:

  1. A human maintainer MUST add the `description-validation-bypass` label (case-insensitive match)

It sits under ``#### Bypassing Description Validation``, the section the
enforcement message cites by name. ``test_contributing_declares_the_label_
human_only`` pins both the declaration and the heading, so a rename in
``CONTRIBUTING.md`` fails here rather than leaving a dangling citation.

Stricter than canonical: ``CONTRIBUTING.md`` states who may add the label.
The enforcement message additionally states who may NOT, because the
load-bearing half for an autonomous reader is the prohibition, not the
permission.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from scripts.validation.pr_description import DEFAULT_BYPASS_LABEL, validate_pr_description

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"

# An instruction to the reader: an imperative verb followed, inside the same
# sentence, by the label name. `[^.]` cannot cross a sentence boundary, so a
# message that names the label in a fresh sentence ("... . The 'X' label lifts
# the ceiling, but ...") does not match, while the pre-#4782 wording did:
#   "For unrecoverable cases, apply the 'description-validation-bypass' label"
_SELF_SERVICE_INSTRUCTION = re.compile(
    r"(?i)\b(?:use|add|apply|set)\b[^.]{0,30}?" r"(?:description-validation-bypass)"
)


def _assert_defers_to_a_maintainer(message: str, label: str, sanctioned_action: str) -> None:
    """Assert one enforcement message states the constraint, not the bypass.

    Four properties, all of which the pre-#4782 wording failed on at least one
    surface: the message names a sanctioned action the reader may take, names
    the label's authority, forbids self-application in words, and never reads as
    an instruction to apply the label.
    """
    assert sanctioned_action.lower() in message.lower(), f"no sanctioned action offered: {message}"
    assert "human maintainer" in message, f"authority not named: {message}"
    assert "do not apply it yourself" in message, f"prohibition missing: {message}"
    assert label in message, f"label not named at all: {message}"
    match = _SELF_SERVICE_INSTRUCTION.search(message)
    assert match is None, f"reads as an instruction to apply the label: {match} in {message}"


_LABEL_HEADING = "#### Bypassing Description Validation"


def _section_body(lines: Sequence[str], heading: str) -> str:
    """Return the lines under `heading`, up to the next heading of any level.

    A markdown heading line starts with one or more `#` characters. Slicing
    to the next such line (or EOF) bounds the section so a caller can assert
    a declaration is *inside* the cited section, not merely present somewhere
    in the whole document.
    """
    start = lines.index(heading) + 1
    for offset, line in enumerate(lines[start:]):
        if line.startswith("#"):
            return "\n".join(lines[start : start + offset])
    return "\n".join(lines[start:])


def test_contributing_declares_the_label_human_only() -> None:
    """The cited authority still says what the enforcement message claims it says.

    Scoped to the section named by the message: a declaration existing
    anywhere in the file is not enough, because the runtime message cites a
    specific section by name. If the declaration moved to a different
    section while the old heading survived elsewhere in the file, an
    unscoped `in text` check would still pass and the message's citation
    would go stale silently.
    """
    lines = CONTRIBUTING.read_text(encoding="utf-8").splitlines()
    assert _LABEL_HEADING in lines, (
        f"message cites a section that no longer exists: {_LABEL_HEADING}"
    )
    section = _section_body(lines, _LABEL_HEADING)
    assert f"A human maintainer MUST add the `{DEFAULT_BYPASS_LABEL}` label" in section, (
        f"CONTRIBUTING.md's {_LABEL_HEADING!r} section no longer declares "
        f"{DEFAULT_BYPASS_LABEL} human-only; the enforcement message citing "
        "that section is now wrong"
    )


def test_contributing_never_instructs_without_naming_the_authority() -> None:
    """Prose an agent reads before acting carries the same obligation.

    Weaker than the runtime-message rule above, and deliberately so: a
    contributor guide may tell the reader to obtain the label, provided the same
    line says who grants it. What it may not do is pair an imperative with the
    label name and leave the authority to another paragraph, which is how
    CONTRIBUTING.md read before this change ("apply the
    `description-validation-bypass` label").

    Scope is reported with the finding count per `.claude/rules/testing.md`
    MUST 10: every line of the file is examined, not a subset.
    """
    lines = CONTRIBUTING.read_text(encoding="utf-8").splitlines()
    offenders = [
        (number, line)
        for number, line in enumerate(lines, start=1)
        if _SELF_SERVICE_INSTRUCTION.search(line) and "human maintainer" not in line
    ]
    assert not offenders, (
        f"{len(offenders)} of {len(lines)} CONTRIBUTING.md lines name a "
        f"human-only label as an action without naming who may take it: {offenders}"
    )


def test_description_validator_defers_its_bypass_label_to_a_maintainer() -> None:
    """Same shape as the retired commit-limit-bypass guidance (CONTRIBUTING.md:909)."""
    issues = validate_pr_description(
        pr_files=["scripts/validation/pr_description.py"],
        mentioned_files=["docs/not-in-this-diff.md"],
    )

    criticals = [issue for issue in issues if issue.severity == "CRITICAL"]
    assert len(criticals) == 1, f"expected 1 CRITICAL in {len(issues)} issues: {issues}"
    _assert_defers_to_a_maintainer(criticals[0].message, DEFAULT_BYPASS_LABEL, "Move the path")


def test_description_validator_names_no_bypass_when_every_mention_is_in_the_diff() -> None:
    """No over-fire: the passing path never mentions the label."""
    issues = validate_pr_description(
        pr_files=["scripts/validation/pr_description.py"],
        mentioned_files=["scripts/validation/pr_description.py"],
    )

    assert not [issue for issue in issues if DEFAULT_BYPASS_LABEL in issue.message], issues
