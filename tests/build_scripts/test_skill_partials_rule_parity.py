"""Pins every ``templates/skills/partials/*.mustache`` to the rule it excerpts.

DESIGN-024 "Template grammar"
(``.agents/specs/design/DESIGN-024-skill-guidance-excerpt-sync.md``):

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

# The captured group excludes "/" and "\\": a rule-source pin is a bare
# ``<file>.md`` name, never a path. Without this exclusion a partial could pin
# ``../../../etc/passwd.md`` or an absolute path, and ``RULES_DIR / rule_source``
# would read outside ``.claude/rules`` (CWE-22/CWE-23), reporting the invalid
# pin as verified whenever the escaped target happened to contain the body's
# bytes. A bare filename with no separator cannot escape ``RULES_DIR`` when
# joined with it, which is the primary defense; :func:`_rule_path_under_rules_dir`
# below is the second, independent check (resolve, then contain), so a future
# change to this regex cannot silently reopen the traversal on its own.
_RULE_SOURCE_RE = re.compile(r"^\{\{!\s*rule-source:\s*([^\s/\\]+\.md)\s*\}\}\n")


def _rule_source(partial_text: str) -> str | None:
    """Return the pinned rule filename, or ``None`` when the partial carries no pin.

    Per DESIGN-024 "Template grammar", the pin is the partial's first line
    only: ``{{! rule-source: <file>.md }}``. A comment tag anywhere else in
    the file is not a pin (there is none in the pilot partials today, but
    the regex anchors to the start of the string so it cannot false-positive
    on one). The capture group in :data:`_RULE_SOURCE_RE` already excludes
    path separators, so a value containing ``/`` or ``\\`` (an attempted
    traversal or an absolute path) fails to match here and this function
    returns ``None``, the same as a partial with no pin at all: the value is
    never used to build a filesystem path either way.
    """
    match = _RULE_SOURCE_RE.match(partial_text)
    return match.group(1) if match else None


def _rule_path_under_rules_dir(rule_source: str, *, partial_name: str) -> Path:
    """Resolve ``rule_source`` under :data:`RULES_DIR` and assert containment.

    Second, independent layer of the CWE-22/CWE-23 defense: even though
    :data:`_RULE_SOURCE_RE` already rejects a path separator, this resolves
    the joined path and asserts its parent is exactly ``RULES_DIR`` before any
    read. A bare filename with no separator cannot fail this check today; it
    exists so a later change that loosens the regex (or a new caller of
    :func:`_rule_source` that skips it) still cannot walk this test outside
    ``.claude/rules``.
    """
    resolved_rules_dir = RULES_DIR.resolve()
    rule_path = (RULES_DIR / rule_source).resolve()
    assert rule_path.parent == resolved_rules_dir, (
        f"{partial_name}: rule-source {rule_source!r} resolves outside {RULES_DIR}"
    )
    return rule_path


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
    newline before comparing, per DESIGN-024's "The rule-source substring
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

        rule_path = _rule_path_under_rules_dir(rule_source, partial_name=partial_path.name)
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

    rule_path = _rule_path_under_rules_dir(rule_source, partial_name=real_partial.name)
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


def test_rule_source_path_traversal_is_rejected() -> None:
    """Security: a rule-source pin naming a path outside RULES_DIR is not a valid pin.

    CWE-22/CWE-23: a partial pinning ``{{! rule-source: ../../../etc/passwd.md }}``
    or an absolute path must never reach ``RULES_DIR / rule_source`` unresolved.
    :data:`_RULE_SOURCE_RE`'s capture group excludes "/" and "\\", so both shapes
    fail to match and :func:`_rule_source` reports no pin at all, the same as a
    partial with no rule-source line. This is the negative control on that regex:
    a substring check that still executed for either payload would prove the guard
    absent, not merely unconfirmed.
    """
    traversal = "{{! rule-source: ../../../etc/passwd.md }}\nbody text\n"
    assert _rule_source(traversal) is None

    absolute = "{{! rule-source: /etc/passwd.md }}\nbody text\n"
    assert _rule_source(absolute) is None

    windows_style = "{{! rule-source: ..\\..\\secrets.md }}\nbody text\n"
    assert _rule_source(windows_style) is None


def test_rule_path_under_rules_dir_rejects_escape(tmp_path: Path) -> None:
    """Security: the second, independent containment layer also rejects an escape.

    :func:`_rule_path_under_rules_dir` is the belt-and-suspenders check run
    after :func:`_rule_source` already filtered the value; this proves it
    would catch an escape on its own; if :data:`_RULE_SOURCE_RE` were ever
    loosened back to accept a separator, this function still holds the line.
    """
    with pytest.raises(AssertionError, match="resolves outside"):
        _rule_path_under_rules_dir("../rules_sibling/other.md", partial_name="fake.mustache")
