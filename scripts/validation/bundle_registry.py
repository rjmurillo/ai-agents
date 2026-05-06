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
# an adjacent ``BUNDLE: <command-base> -> <skill>`` text fragment.
SKILL_INVOCATION_TEMPLATE = 'Skill(skill="{skill}")'


def expected_skill_invocation(skill: str) -> str:
    """Return the literal ``Skill(...)`` string the parser searches for."""
    return SKILL_INVOCATION_TEMPLATE.format(skill=skill)


def expected_bundle_marker(command_file: str, skill: str) -> str:
    """Return the literal ``BUNDLE:`` marker the parser searches for.

    ``command_file`` is the basename (e.g. ``spec.md``); the marker uses
    the slash-command base (no extension), e.g. ``spec``.
    """
    base = command_file.rsplit(".md", 1)[0]
    return f"BUNDLE: {base} -> {skill}"
