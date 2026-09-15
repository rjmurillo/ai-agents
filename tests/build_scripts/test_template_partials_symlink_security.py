"""CWE-22/CWE-59 defense: a symlinked ``partials/`` directory shared by every
template-compile module (``agent_templates.py``, ``rule_templates.py``,
``skill_templates.py``).

Split out on its own rather than appended to ``test_skill_template_grammar.py``,
which sits at the taste-lint 500-line file-size ceiling, the same
seam-splitting precedent ``test_skill_templates_symlink_security.py`` already
used for the SKILL.md-file case.

CodeRabbit review (ADR-109 B2, rules containment round): every compile
module calls ``skill_template_grammar.render(tmpl_path, partials_dir)``,
which loads ``partials_dir`` unconditionally through
``_load_protected_partials`` regardless of whether the template names any
partial. A symlinked ``partials_dir`` therefore reads whatever real
directory the link points at, files it never validated, with no error
before this guard: ``partials_dir.is_dir()`` alone follows the symlink and
returns True, so the pre-existing per-partial-file symlink check (which
only inspects the final path component) never saw it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import skill_template_grammar  # noqa: E402


def test_render_symlinked_partials_dir_is_refused_even_naming_no_partial(
    tmp_path: Path,
) -> None:
    """A symlinked partials dir is refused before the unconditional glob runs."""
    real_partials = tmp_path / "real-partials"
    real_partials.mkdir()
    partials = tmp_path / "partials"
    try:
        partials.symlink_to(real_partials)
    except OSError:
        pytest.skip("cannot create symlink on this platform")
    tmpl = tmp_path / "t.md"
    tmpl.write_text("plain text, no partial reference\n", encoding="utf-8")

    with pytest.raises(skill_template_grammar.MissingPartialError):
        skill_template_grammar.render(tmpl, partials)
