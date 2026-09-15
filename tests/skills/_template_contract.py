"""Shared contract for a template-owned pilot skill's ``SKILL.md`` (ADR-108).

DESIGN-024 "Tests"
(``.agents/specs/design/DESIGN-024-skill-guidance-excerpt-sync.md``):

    ``tests/skills/_template_contract.py`` helper plus one
    ``tests/skills/<pilot>/test_skill_md_contract.py`` per pilot: the
    rendered file equals ``render()`` of its template; no
    ``^@CLAUDE\\.md$`` line in rendered or mirror; no ``{{`` in either.

Not itself a test module (no ``test_`` prefix, so pytest's
``python_files = ["test_*.py"]`` does not collect it); the eight
``tests/skills/<pilot>/test_skill_md_contract.py`` files each import this
and call :func:`assert_template_owned_contract` with their own skill name,
which keeps every per-directory file under 15 lines by parametrizing
through here instead of repeating the three assertions eight times.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import skill_templates

_CLAUDE_MD_LINE_RE = re.compile(r"^@CLAUDE\.md$", re.MULTILINE)

# templates/platforms/copilot-cli.yaml artifacts.skills.excludeFilenames:
# skills the Copilot mirror generator permanently omits (hard-wired to this
# repo's own layout). They ship .claude/skills-only, so the mirror-existence
# and mirror-content checks below do not apply. Empty on this branch: none
# of ADR-109 B3 batch 4's sixteen skills are excluded from the mirror.
_NO_COPILOT_MIRROR: frozenset[str] = frozenset()

# Skills whose template escapes a literal "{{" via "\{{" (ADR-108 amended
# 2026-09-14, e.g. a GitHub Actions "${{ }}" example): their rendered
# SKILL.md legitimately contains "{{", so the blanket unresolved-tag scan
# below does not apply to them. skill_templates.render() already proves no
# tag is genuinely unresolved: it raises UnresolvedTagError before
# returning if one exists, so a successful render is the real guarantee.
_LITERAL_BRACE_SKILLS = frozenset({"security-detection"})


def assert_template_owned_contract(name: str) -> None:
    """Assert the ADR-108 contract for one template-owned pilot skill.

    Three checks, matching DESIGN-024's "Tests" table entry verbatim:

    1. The committed ``.claude/skills/<name>/SKILL.md`` equals a fresh
       ``skill_templates.render()`` of ``templates/skills/<name>.SKILL.md.tmpl``.
       This is the ``derived`` predicate ADR-108 section 1 defines: "regenerate,
       then byte-compare."
    2. Neither the rendered file nor its Copilot mirror
       (``src/copilot-cli/skills/<name>/SKILL.md``) contains a line that is
       exactly ``@CLAUDE.md`` (ADR-108 Context: Copilot CLI treats that line
       as literal text rather than an include). Skipped for a skill in
       ``_NO_COPILOT_MIRROR``, which has no mirror file to check.
    3. Neither file contains the literal substring ``{{``: an unresolved
       mustache tag would mean the render left a partial or a disallowed
       construct unexpanded. Skipped for a skill in ``_LITERAL_BRACE_SKILLS``,
       whose rendered output legitimately carries an escaped literal ``{{``.
    """
    template_path = REPO_ROOT / "templates" / "skills" / f"{name}.SKILL.md.tmpl"
    partials_dir = REPO_ROOT / "templates" / "skills" / "partials"
    plugin_path = REPO_ROOT / "src" / "claude" / "skills" / name / "SKILL.md"
    rendered_path = REPO_ROOT / ".claude" / "skills" / name / "SKILL.md"
    mirror_path = REPO_ROOT / "src" / "copilot-cli" / "skills" / name / "SKILL.md"
    has_mirror = name not in _NO_COPILOT_MIRROR

    assert template_path.is_file(), f"no template for {name!r}: {template_path}"
    assert plugin_path.is_file(), f"no rendered plugin-tree SKILL.md for {name!r}: {plugin_path}"
    assert rendered_path.is_file(), f"no binplaced SKILL.md for {name!r}: {rendered_path}"
    if has_mirror:
        assert mirror_path.is_file(), f"no Copilot mirror for {name!r}: {mirror_path}"

    fresh_render = skill_templates.render(template_path, partials_dir)
    plugin_committed = plugin_path.read_text(encoding="utf-8", newline="")
    assert plugin_committed == fresh_render, (
        f"{plugin_path} has drifted from templates/skills/{name}.SKILL.md.tmpl; "
        "rerun build/scripts/build_all.py"
    )

    committed = rendered_path.read_text(encoding="utf-8", newline="")
    assert committed == plugin_committed, (
        f"{rendered_path} is not byte-identical to {plugin_path}; "
        "rerun build/scripts/build_all.py to re-binplace it"
    )

    check_paths = (
        (plugin_path, rendered_path, mirror_path) if has_mirror else (plugin_path, rendered_path)
    )
    for path in check_paths:
        text = path.read_text(encoding="utf-8", newline="")
        assert not _CLAUDE_MD_LINE_RE.search(text), f"{path}: still carries an @CLAUDE.md line"
        if name not in _LITERAL_BRACE_SKILLS:
            assert "{{" not in text, f"{path}: unresolved '{{{{' left in rendered output"
