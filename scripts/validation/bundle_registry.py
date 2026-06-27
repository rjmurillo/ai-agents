"""Single source of truth for SPEC-005 BundleRegistry.

The registry enumerates which dedicated skills are bundled into which
lifecycle command markdown files. It is consumed by:

- ``tests/test_command_bundles.py`` (static-parser test, parametrized)
- ``scripts/validation/pre_pr.py`` (advisory WARN check, gated behind
  ``BUNDLE_CHECK_ENFORCED`` env var; default ``0``)

Both consumers MUST import from this module to avoid copy-paste drift
(per SPEC-005 plan adversarial review C5 and pre-mortem F5).

The registry has 15 entries across 13 unique skills (some skills
appear in more than one command). See:

- ``.agents/specs/requirements/REQ-005-command-skill-bundling.md``
- ``.agents/specs/design/DESIGN-005-command-skill-bundling.md``
- ``.agents/specs/tasks/TASK-005-command-skill-bundling.md``
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "BUNDLE_REGISTRY",
    "SKILL_INVOCATION_TEMPLATE",
    "BUNDLE_ADJACENCY_WINDOW",
    "expected_skill_invocation",
    "expected_bundle_marker",
    "bundle_marker_present",
    "bundle_marker_adjacent",
]

# Each tuple: (command file basename under .claude/commands/, skill name)
# A skill name is the directory under .claude/skills/.
BUNDLE_REGISTRY: list[tuple[str, str]] = [
    ("spec.md", "session-init"),
    ("ship.md", "session-end"),
    ("ship.md", "reflect"),
    ("plan.md", "pre-mortem"),
    ("plan.md", "decision-critic"),
    ("build.md", "context-gather"),
    ("build.md", "steering-matcher"),
    ("build.md", "chestertons-fence"),
    ("test.md", "threat-modeling"),
    ("test.md", "slo-designer"),
    ("test.md", "observability"),
    ("review.md", "doc-accuracy"),
    ("review.md", "chestertons-fence"),
    ("pr-review.md", "merge-resolver"),
    ("research.md", "context-gather"),
]

# Per SPEC-005 DESIGN-005 §"BUNDLE Marker Format":
# the static parser looks for both the ``Skill(skill="...")`` call and
# an adjacent ``BUNDLE: <command-base> -> <skill> (<status>)`` text
# fragment. ``<status>`` is one of ``invoked``, ``skipped:<reason>``,
# or ``failed:<reason>`` per DESIGN-005 §"BUNDLE Marker Format".
SKILL_INVOCATION_TEMPLATE = 'Skill(skill="{skill}")'

# Maximum line distance between a ``Skill(...)`` call and its matching
# ``BUNDLE:`` marker for them to count as adjacent. Sourced from
# DESIGN-005; updates require a paired spec edit.
BUNDLE_ADJACENCY_WINDOW = 5


def _command_base(command_file: str) -> str:
    """Return the slash-command base for a command file basename.

    ``Path.stem`` strips the ``.md`` extension (``spec.md`` -> ``spec``,
    ``pr-review.md`` -> ``pr-review``) and is the single source of truth
    for marker base derivation across this module.
    """
    return Path(command_file).stem


def expected_skill_invocation(skill: str) -> str:
    """Return the literal ``Skill(...)`` string the parser searches for.

    Uses ``str.replace`` rather than ``str.format`` so a future skill
    name containing ``{`` or ``}`` cannot trigger a format error or an
    accidental field substitution.
    """
    return SKILL_INVOCATION_TEMPLATE.replace("{skill}", skill)


def expected_bundle_marker(command_file: str, skill: str) -> str:
    """Return the literal ``BUNDLE:`` marker prefix (including the
    opening ``(`` of the status suffix).

    ``command_file`` is the basename (e.g. ``spec.md``); the marker uses
    the slash-command base (no extension), e.g. ``spec``. The trailing
    ``(`` forces a status suffix per DESIGN-005 §"BUNDLE Marker Format"
    so non-conformant markers without a status do not silently pass.
    Use :func:`bundle_marker_present` for full validation of the status
    set, and :func:`bundle_marker_adjacent` for adjacency to the
    matching ``Skill(...)`` call.
    """
    base = _command_base(command_file)
    return f"BUNDLE: {base} -> {skill} ("


def bundle_marker_present(text: str, command_file: str, skill: str) -> bool:
    """Return ``True`` if a well-formed BUNDLE marker for the pair exists.

    A well-formed marker matches ``BUNDLE: <base> -> <skill> (<status>)``
    where ``<status>`` is one of ``invoked``, ``skipped:<reason>``, or
    ``failed:<reason>`` per DESIGN-005.
    """
    import re

    base = _command_base(command_file)
    pattern = re.compile(
        rf"BUNDLE:\s+{re.escape(base)}\s+->\s+{re.escape(skill)}\s+"
        rf"\((invoked|skipped:[^)]+|failed:[^)]+)\)"
    )
    return bool(pattern.search(text))


def bundle_marker_adjacent(
    text: str,
    command_file: str,
    skill: str,
    *,
    window: int = BUNDLE_ADJACENCY_WINDOW,
) -> bool:
    """Return ``True`` if a well-formed BUNDLE marker is within ``window``
    lines of the matching ``Skill(skill="...")`` call.

    Per DESIGN-005 §"BUNDLE Marker Format", the convention is to emit the
    marker before invoking the skill. This check is order-agnostic: it
    accepts the marker on either side of the invocation as long as the
    line distance is within ``window``. The intent is to keep the marker
    and the invocation visibly co-located; strict ordering is not
    enforced here because reviewers and downstream parsers already see
    the pairing as a block. Returns ``False`` if either side is absent.
    """
    import re

    base = _command_base(command_file)
    invocation = expected_skill_invocation(skill)
    marker_re = re.compile(
        rf"BUNDLE:\s+{re.escape(base)}\s+->\s+{re.escape(skill)}\s+"
        rf"\((invoked|skipped:[^)]+|failed:[^)]+)\)"
    )

    lines = text.splitlines()
    invocation_lines = [i for i, line in enumerate(lines) if invocation in line]
    marker_lines = [i for i, line in enumerate(lines) if marker_re.search(line)]

    if not invocation_lines or not marker_lines:
        return False

    for inv in invocation_lines:
        for mk in marker_lines:
            if abs(inv - mk) <= window:
                return True
    return False
