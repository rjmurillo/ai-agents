"""Pins every ``templates/skills/partials/*.mustache`` to the rule it excerpts.

DESIGN-020 "Template grammar"
(``.agents/specs/design/DESIGN-020-skill-guidance-excerpt-sync.md``):

    A partial's first line MAY be ``{{! rule-source: <file>.md }}``. When
    present, the rest of the file MUST be a verbatim contiguous substring of
    ``.claude/rules/<file>.md``, enforced by
    ``tests/build_scripts/test_skill_partials_rule_parity.py``.

ADR-108 section 5 (``.agents/architecture/ADR-108-template-owned-skill-files.md``):

    A partial whose first line is ``{{! rule-source: <file>.md }}`` MUST
    appear verbatim and contiguously in ``.claude/rules/<file>.md``; a test
    under ``tests/build_scripts/`` enforces it. ... A partial with no
    ``rule-source`` line is standalone, which is the shape a partial takes
    once a later issue cuts the rule text.

This file is that test. It walks every real ``.mustache`` file under
``templates/skills/partials/``, parses the optional first-line pin, and
asserts the substring relationship for every partial that carries one.
Positive coverage is the real pilot partials (six as of TASK-027, A2).
Negative and edge coverage use ``tmp_path`` fixtures rather than mutating the
real rule files: a one-byte change proves the substring check is not vacuous,
and a partial with no ``rule-source`` line proves it is skipped rather than
raising on a partial that carries no pin.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PARTIALS_DIR = REPO_ROOT / "templates" / "skills" / "partials"
RULES_DIR = REPO_ROOT / ".claude" / "rules"

_RULE_SOURCE_RE = re.compile(r"^\{\{!\s*rule-source:\s*(\S+\.md)\s*\}\}\n")


def _rule_source(partial_text: str) -> str | None:
    """Return the pinned rule filename, or ``None`` when the partial carries no pin.

    Per DESIGN-020 "Template grammar", the pin is the partial's first line
    only: ``{{! rule-source: <file>.md }}``. A comment tag anywhere else in
    the file is not a pin (there is none in the pilot partials today, but
    the regex anchors to the start of the string so it cannot false-positive
    on one).
    """
    match = _RULE_SOURCE_RE.match(partial_text)
    return match.group(1) if match else None


def _excerpt_body(partial_text: str, rule_source: str) -> str:
    """Return the partial's body: everything after the pinned first line."""
    prefix = f"{{{{! rule-source: {rule_source} }}}}\n"
    assert partial_text.startswith(prefix)
    return partial_text[len(prefix) :]


def _assert_verbatim_substring(
    body: str, rule_text: str, *, partial_name: str, rule_source: str
) -> None:
    """The excerpt, minus its one trailing newline, is a contiguous substring of the rule.

    ``check_grammar``/the partial loader already requires exactly one
    trailing newline on every partial (module docstring of
    ``build/scripts/skill_templates.py``); this strips exactly that one
    newline before comparing, per DESIGN-020's "The rule-source substring
    check strips exactly that one trailing newline before comparing."
    """
    assert body.endswith("\n") and not body.endswith("\n\n"), (
        f"{partial_name}: must end with exactly one trailing newline"
    )
    stripped = body[:-1]
    assert stripped in rule_text, (
        f"{partial_name}: not a verbatim contiguous substring of "
        f".claude/rules/{rule_source}"
    )


def _real_partials() -> list[Path]:
    return sorted(PARTIALS_DIR.glob("*.mustache"))


def test_every_pinned_partial_is_a_verbatim_substring_of_its_rule_file() -> None:
    """Positive: every real pilot partial with a rule-source pin matches its rule.

    Also asserts at least one partial was actually checked, so this test
    cannot pass vacuously because ``templates/skills/partials/`` is empty or
    missing.
    """
    partials = _real_partials()
    assert partials, "expected at least one partial under templates/skills/partials/"

    checked = 0
    for partial_path in partials:
        text = partial_path.read_text(encoding="utf-8", newline="")
        rule_source = _rule_source(text)
        if rule_source is None:
            continue

        rule_path = RULES_DIR / rule_source
        assert rule_path.is_file(), f"{partial_path.name}: no such rule file {rule_path}"
        rule_text = rule_path.read_text(encoding="utf-8", newline="")

        body = _excerpt_body(text, rule_source)
        _assert_verbatim_substring(
            body, rule_text, partial_name=partial_path.name, rule_source=rule_source
        )
        checked += 1

    assert checked >= 6, (
        f"expected at least the six pilot partials to carry a rule-source pin, found {checked}"
    )


def test_pinned_partial_with_a_one_byte_change_fails(tmp_path: Path) -> None:
    """Negative control: a one-byte edit to the excerpt is no longer a substring.

    Proves the positive test is not vacuous: if the substring check always
    passed regardless of content, this would pass too and the positive test
    would give no real assurance.
    """
    real_partial = PARTIALS_DIR / "no-dashes.mustache"
    text = real_partial.read_text(encoding="utf-8", newline="")
    rule_source = _rule_source(text)
    assert rule_source is not None

    rule_path = RULES_DIR / rule_source
    rule_text = rule_path.read_text(encoding="utf-8", newline="")

    body = _excerpt_body(text, rule_source)
    assert body.endswith(".\n")
    # Flip the terminal period to a question mark: one byte, still ends with
    # exactly one trailing newline, no longer present in the rule file.
    corrupted_body = body[:-2] + "?\n"

    # Call the same helper the positive test uses, rather than
    # re-implementing the substring check inline: a drift between this
    # control and the real assertion would otherwise let the control pass
    # for a reason unrelated to what the positive test actually checks.
    with pytest.raises(AssertionError):
        _assert_verbatim_substring(
            corrupted_body, rule_text, partial_name="no-dashes.mustache", rule_source=rule_source
        )


def test_partial_with_no_rule_source_line_is_skipped(tmp_path: Path) -> None:
    """Edge: a partial with no rule-source pin is standalone and never checked.

    ADR-108 section 5: "A partial with no rule-source line is standalone,
    which is the shape a partial takes once a later issue cuts the rule
    text." This test fabricates one (rather than requiring a real one to
    exist yet) and asserts the parser reports no pin, so the substring check
    in the positive test above is never invoked for it.
    """
    standalone = tmp_path / "standalone.mustache"
    standalone.write_text("Freestanding guidance with no rule-source pin.\n", encoding="utf-8")

    text = standalone.read_text(encoding="utf-8", newline="")
    assert _rule_source(text) is None
