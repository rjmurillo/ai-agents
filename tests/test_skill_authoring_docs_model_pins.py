"""Regression guards for the skill-authoring docs that teach model pins (issue #4940).

Five documents carry copyable YAML frontmatter examples. Before this guard they
told authors to write a versioned Claude id (``model: claude-opus-4-6``), which
ADR-080 rule 1 forbids on a skill or command and
``scripts/validation/check_model_pins.py`` rejects, so a copy-paste from any of
them produced a gate failure.

Canonical contract, quoted verbatim from
``scripts/validation/check_model_pins.py``:

- ``_VERSIONED_RE = re.compile(r"^claude-(?:opus|sonnet|haiku)-[0-9]")``
- skill/command failure message: ``f"{unit.kind} carries versioned id
  '{model}'; skills and commands may not pin a version (ADR-080 rule 1)"``
- ``ROLLING_ALIASES = ("sonnet", "opus", "haiku")`` and a bare alias must both
  carry ``model-rationale`` and price below ``DEFAULT_MODEL =
  "claude-sonnet-4-6"``.

Stricter/looser/different than canonical: this guard is *narrower* than
``check_model_pins.py`` in scope and *different* in target. The gate scans unit
frontmatter under ``_UNIT_GLOBS`` (``.claude/skills``, ``.claude/agents``,
``templates/agents``, ``.claude/commands``) and by design ignores documentation,
because a fenced example is not frontmatter. This guard scans only the five
documents listed in ``TRACKED_DOCS`` and only inside fenced ``yaml`` blocks. It
deliberately allows a versioned id that is labelled as a counter-example
(``MARKER_WORDS`` / ``PROSE_LABELS``), because showing the rejected shape next
to the correct one is how the docs teach the rule. It says nothing about
``subagent_model``: the gate collects nested pins with ``if key == "model"``
(``_collect_nested_pins``), so that key is outside both contracts.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# The documents issue #4940 names. Each is a place an author copies from.
TRACKED_DOCS = (
    "docs/SKILL-AUTHORING.md",
    ".agents/steering/claude-skills.md",
    ".agents/architecture/ADR-040-skill-frontmatter-standardization.md",
    ".agents/architecture/SKILL-STANDARDS-RECONCILED.md",
    ".agents/architecture/DESIGN-REVIEW-context-optimizer-refactoring.md",
)

# Same shape as check_model_pins._VERSIONED_RE, applied to one frontmatter line
# rather than to a parsed value. Dotted and hyphenated spellings both match,
# because check_model_pins._normalize_id collapses dots to hyphens before its
# own match.
_PIN_LINE_RE = re.compile(
    r"^\s*model\s*:\s*['\"]?(claude-(?:opus|sonnet|haiku)[-.][0-9][^\s'\"#]*)"
)

_YAML_FENCE_RE = re.compile(r"^```ya?ml\s*$(.*?)^```\s*$", re.MULTILINE | re.DOTALL)

# A fenced block may show a rejected pin when the pin itself is labelled. The
# label must sit within LABEL_LOOKBACK_LINES above the pin (an in-block comment)
# or be the "**Before**" prose heading that introduces a migration example.
# Matching the whole block instead would let a "# Correct" line hide behind a
# "# Wrong" line in the same fence, which is exactly the shape the old docs
# used. The prose label is read from the LAST nonblank line before the fence,
# not from a character window: in a migration section the "**Before**" heading
# sits within a few hundred characters of the "**After**" fence that follows it,
# so a window would exempt the corrected example too (PR #5003 review).
MARKER_WORDS = ("wrong", "before", "never", "rejected", "superseded", "banned")
PROSE_LABELS = ("**Before**",)
LABEL_LOOKBACK_LINES = 3


def _read(rel_path: str) -> str:
    path = REPO_ROOT / rel_path
    assert path.is_file(), f"tracked doc missing: {rel_path}"
    return path.read_text(encoding="utf-8")


def _yaml_blocks(text: str) -> list[re.Match[str]]:
    """Every fenced ``yaml`` block, as matches so callers keep the offsets."""
    return list(_YAML_FENCE_RE.finditer(text))


def _has_prose_label(text: str, block_start: int) -> bool:
    """True when the last line before the fence introduces a 'Before' example.

    Only the introducing line counts. A migration section writes "**Before**",
    one short fence, then "**After**" and the corrected fence; anything wider
    than the introducing line exempts the corrected fence as well.
    """
    preceding = text[:block_start].splitlines()
    introducing = next((line for line in reversed(preceding) if line.strip()), "")
    return any(label in introducing for label in PROSE_LABELS)


def _is_labelled(lines: list[str], index: int) -> bool:
    """True when a marker comment sits on, or just above, the pin line."""
    window = lines[max(0, index - LABEL_LOOKBACK_LINES) : index + 1]
    for line in window:
        stripped = line.strip()
        comment = stripped[stripped.index("#") :].lower() if "#" in stripped else ""
        if comment and any(word in comment for word in MARKER_WORDS):
            return True
    return False


def _versioned_pins_taught(text: str) -> list[str]:
    """Versioned ids that a fenced example offers as the correct shape."""
    found: list[str] = []
    for block in _yaml_blocks(text):
        if _has_prose_label(text, block.start()):
            continue
        lines = block.group(1).splitlines()
        for index, line in enumerate(lines):
            match = _PIN_LINE_RE.match(line)
            if match and not _is_labelled(lines, index):
                found.append(match.group(1))
    return found


@pytest.mark.parametrize("rel_path", TRACKED_DOCS)
def test_yaml_examples_teach_no_versioned_model_pin(rel_path: str) -> None:
    """No fenced YAML example offers a versioned pin as the correct shape."""
    offenders = _versioned_pins_taught(_read(rel_path))

    assert not offenders, (
        f"{rel_path} shows versioned model pin(s) {offenders} in a YAML example that is not "
        "labelled as a counter-example. ADR-080 rule 1: skills and commands may not pin a "
        "version. Omit model: to inherit, or use the bare 'haiku' alias with model-rationale."
    )


@pytest.mark.parametrize("rel_path", TRACKED_DOCS)
def test_doc_points_at_adr_080(rel_path: str) -> None:
    """Each tracked doc names ADR-080 so the next reader learns the rule."""
    assert "ADR-080" in _read(rel_path), (
        f"{rel_path} teaches skill frontmatter but does not point at ADR-080"
    )


def test_authoring_guide_shows_both_conformant_states() -> None:
    """The public guide shows inherit-by-omission and the cost alias."""
    text = _read("docs/SKILL-AUTHORING.md")

    assert "model: haiku" in text, "the cost-alias state is missing"
    assert "model-rationale:" in text, "the cost alias must be shown with its rationale"
    assert "Omit `model:`" in text, "the inherit-by-omission default is missing"
    assert "check_model_pins.py" in text, "the enforcing gate is not named"


def test_counter_example_detection_catches_an_unlabelled_pin() -> None:
    """Negative control: the matcher fires on an unlabelled pin.

    Without this, a broken regex would make every assertion above pass
    vacuously.
    """
    doc = "```yaml\n---\nname: my-skill\nmodel: claude-opus-4-6\n---\n```\n"
    assert len(_yaml_blocks(doc)) == 1
    assert _versioned_pins_taught(doc) == ["claude-opus-4-6"]


def test_labelled_counter_example_is_allowed() -> None:
    """A pin directly under a '# Wrong' comment is teaching, not regressing."""
    doc = "```yaml\n# Wrong: versioned id in a skill\nmodel: claude-opus-4-6\n```\n"

    assert _versioned_pins_taught(doc) == []


def test_correct_line_in_a_wrong_block_is_still_flagged() -> None:
    """Edge: a '# Wrong' line earlier in the fence does not excuse a later pin.

    This is the shape the pre-fix troubleshooting section used, so the guard
    must see past it.
    """
    doc = "```yaml\n# Wrong\nmodel: sonnet-4.6\n\n# Correct\nmodel: claude-sonnet-4-6\n```\n"

    assert _versioned_pins_taught(doc) == ["claude-sonnet-4-6"]


def test_before_prose_label_exempts_a_migration_example() -> None:
    """A '**Before**' migration fence may show the id being migrated away."""
    doc = "**Before** (versioned id):\n\n```yaml\nmodel: claude-opus-4-6-20251015\n```\n"

    assert _versioned_pins_taught(doc) == []


def test_before_label_does_not_exempt_the_after_fence() -> None:
    """Edge: the corrected fence of a migration pair is still checked.

    The label is read from the line that introduces each fence. A window wide
    enough to reach back over the 'Before' fence would let a regression hide in
    the 'After' example, which is the one authors copy (PR #5003 review).
    """
    doc = (
        "**Before** (versioned id):\n\n"
        "```yaml\nmodel: claude-opus-4-6-20251015\n```\n\n"
        "**After** (corrected):\n\n"
        "```yaml\nmodel: claude-opus-4-6\n```\n"
    )

    assert _versioned_pins_taught(doc) == ["claude-opus-4-6"]


def test_bare_alias_is_not_flagged() -> None:
    """Edge: a conformant bare alias must not read as a versioned pin."""
    doc = "```yaml\nmodel: haiku\nmodel-rationale: cost. ...\n```\n"

    assert _versioned_pins_taught(doc) == []


def test_dotted_spelling_is_flagged() -> None:
    """Edge: check_model_pins normalises dots to hyphens; so must this guard."""
    doc = "```yaml\nmodel: claude-opus-4.6\n```\n"

    assert _versioned_pins_taught(doc) == ["claude-opus-4.6"]
