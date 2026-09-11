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
       as literal text rather than an include).
    3. Neither file contains the literal substring ``{{``: an unresolved
       mustache tag would mean the render left a partial or a disallowed
       construct unexpanded.
    """
    template_path = REPO_ROOT / "templates" / "skills" / f"{name}.SKILL.md.tmpl"
    partials_dir = REPO_ROOT / "templates" / "skills" / "partials"
    rendered_path = REPO_ROOT / ".claude" / "skills" / name / "SKILL.md"
    mirror_path = REPO_ROOT / "src" / "copilot-cli" / "skills" / name / "SKILL.md"

    assert template_path.is_file(), f"no template for {name!r}: {template_path}"
    assert rendered_path.is_file(), f"no rendered SKILL.md for {name!r}: {rendered_path}"
    assert mirror_path.is_file(), f"no Copilot mirror for {name!r}: {mirror_path}"

    fresh_render = skill_templates.render(template_path, partials_dir)
    committed = rendered_path.read_text(encoding="utf-8", newline="")
    assert committed == fresh_render, (
        f"{rendered_path} has drifted from templates/skills/{name}.SKILL.md.tmpl; "
        "rerun build/scripts/build_all.py"
    )

    for path in (rendered_path, mirror_path):
        text = path.read_text(encoding="utf-8", newline="")
        assert not _CLAUDE_MD_LINE_RE.search(text), f"{path}: still carries an @CLAUDE.md line"
        assert "{{" not in text, f"{path}: unresolved '{{{{' left in rendered output"
