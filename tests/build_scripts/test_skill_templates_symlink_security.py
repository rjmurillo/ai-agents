"""CWE-22/CWE-59 defense: a symlinked ``SKILL.md`` file inside an otherwise
legitimate ``.claude/skills/<name>/`` directory.

Split out on its own (not appended to ``test_generate_skills_template_compile.py``,
which sits at the taste-lint 500-line file-size ceiling) rather than grown
in place, the same seam-splitting precedent this PR already used for
``skill_templates.py`` / ``skill_template_grammar.py`` and their test files.

CodeRabbit review, PR #5726: ``_name_validation_error`` (``skill_templates.py``)
checks whether ``.claude/skills/<name>/`` itself is a symlink and whether its
resolved path stays inside the resolved ``.claude/skills/`` root, but never
checked the FILE at ``.claude/skills/<name>/SKILL.md``. A real, non-symlinked
directory can still hold a symlinked ``SKILL.md`` pointing anywhere on the
filesystem; ``compile_all``'s ``target.write_text(...)`` follows a symlink
the same way any ``open()`` call does, so a render would silently escape
``.claude/skills/`` through that file even though the directory containment
check passed.
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

import skill_templates  # noqa: E402
from _skill_template_helpers import write_template  # noqa: E402


def test_discover_excludes_a_symlinked_skill_md_inside_a_real_directory(
    tmp_path: Path,
) -> None:
    """A real, non-symlinked skill dir with a symlinked SKILL.md is exit 2,
    never template-owned, and ``compile_all`` never writes through the link.
    """
    write_template(tmp_path, "sync", "hello\n")
    skill_dir = tmp_path / ".claude" / "skills" / "sync"
    skill_dir.mkdir(parents=True)
    outside = tmp_path / "outside-skill-md"
    outside.write_text("do not overwrite me\n", encoding="utf-8")
    link = skill_dir / "SKILL.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("cannot create a symlink on this platform/permission set")

    assert skill_templates.discover(tmp_path) == {}
    errors = skill_templates.discover_errors(tmp_path)
    assert len(errors) == 1
    assert "sync" in errors[0]
    assert "symlink" in errors[0].lower()
    assert skill_templates.owned_targets(tmp_path) == set()

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert link.is_symlink()
    assert outside.read_text(encoding="utf-8") == "do not overwrite me\n"
    assert result.exit_code == 2


def test_discover_excludes_every_skill_when_the_skills_root_is_a_symlink_outside_the_repo(
    tmp_path: Path,
) -> None:
    """An intermediate ``.claude/skills`` symlink to an external tree makes
    every template a config error, and ``compile_all`` never writes there.
    """
    write_template(tmp_path, "sync", "hello\n")
    external = tmp_path.parent / f"{tmp_path.name}-external-skills"
    (external / "sync").mkdir(parents=True)
    target = external / "sync" / "SKILL.md"
    target.write_text("do not overwrite me\n", encoding="utf-8")
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    try:
        (claude_dir / "skills").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create a symlink on this platform/permission set")

    assert skill_templates.discover(tmp_path) == {}
    errors = skill_templates.discover_errors(tmp_path)
    assert len(errors) == 1
    assert "outside the repository root" in errors[0]
    assert skill_templates.owned_targets(tmp_path) == set()

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert target.read_text(encoding="utf-8") == "do not overwrite me\n"
    assert result.exit_code == 2
