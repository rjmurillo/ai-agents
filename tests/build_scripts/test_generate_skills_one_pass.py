"""A new templated skill reaches every mirror in one generate_skills run.

A skill author adds ``templates/skills/<name>.SKILL.md.tmpl`` plus support
files under ``src/claude/skills/<name>/`` (scripts, references), the one
hand-maintained copy (ADR-119). The install path ``.claude/skills/<name>`` is
a symlink binplace places after every generator, so it does not exist yet.
Skill discovery used to require an install-tree ``SKILL.md``, so the first run
rendered only the plugin-tree ``SKILL.md`` and a second run mirrored the
support files (issue #6537). These tests keep the one-pass guarantee: the
first run renders ``SKILL.md`` into the plugin tree, leaves the support files
alone, and gives the Copilot tree both.
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

import generate_skills  # noqa: E402
import skill_support_mirror  # noqa: E402
from _skill_template_helpers import minimal_platform_config, write_template  # noqa: E402

_BODY = "---\nname: alpha\ndescription: fixture\n---\n# alpha\n"


def _config(repo: Path) -> Path:
    """Platform config whose Copilot source is the plugin tree, as in the repo."""
    return minimal_platform_config(repo, "src/claude/skills")


def _seed_new_skill(repo: Path, name: str = "alpha") -> None:
    """Seed a template and plugin-tree support files, with no rendered SKILL.md."""
    write_template(repo, name, _BODY.replace("alpha", name))
    skill_dir = repo / "src" / "claude" / "skills" / name
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "scripts").mkdir()
    (skill_dir / "references" / "notes.md").write_text("notes\n", encoding="utf-8")
    (skill_dir / "scripts" / "run.py").write_text("print('hi')\n", encoding="utf-8")


def _snapshot(repo: Path) -> dict[str, bytes]:
    """Return every file under src/ and out/ keyed by relative path."""
    snap: dict[str, bytes] = {}
    for root in ("src", "out"):
        for path in sorted((repo / root).rglob("*")):
            if path.is_file():
                snap[path.relative_to(repo).as_posix()] = path.read_bytes()
    return snap


def test_first_run_renders_skill_md_and_keeps_support_files_in_claude_plugin_tree(
    tmp_path: Path,
) -> None:
    _seed_new_skill(tmp_path)
    config = _config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path)

    base = tmp_path / "src" / "claude" / "skills" / "alpha"
    assert rc == 0
    assert (base / "SKILL.md").is_file()
    assert (base / "references" / "notes.md").read_text(encoding="utf-8") == "notes\n"
    assert (base / "scripts" / "run.py").read_text(encoding="utf-8") == "print('hi')\n"


def test_first_run_mirrors_skill_and_support_files_into_copilot_tree(tmp_path: Path) -> None:
    _seed_new_skill(tmp_path)
    config = _config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path)

    base = tmp_path / "out" / "skills" / "alpha"
    assert rc == 0
    assert "# alpha" in (base / "SKILL.md").read_text(encoding="utf-8")
    assert (base / "references" / "notes.md").read_text(encoding="utf-8") == "notes\n"
    assert (base / "scripts" / "run.py").read_text(encoding="utf-8") == "print('hi')\n"


def test_second_run_is_a_fixed_point(tmp_path: Path) -> None:
    _seed_new_skill(tmp_path)
    config = _config(tmp_path)
    generate_skills.generate_skills(config, tmp_path)
    after_first = _snapshot(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path)

    assert rc == 0
    assert _snapshot(tmp_path) == after_first


@pytest.mark.skipif(sys.platform == "win32", reason="symlink creation needs Developer Mode")
def test_second_run_after_binplace_link_is_a_fixed_point(tmp_path: Path) -> None:
    """Once binplace links the install path, nothing changes again."""
    _seed_new_skill(tmp_path)
    config = _config(tmp_path)
    generate_skills.generate_skills(config, tmp_path)
    after_first = _snapshot(tmp_path)
    install = tmp_path / ".claude" / "skills" / "alpha"
    install.parent.mkdir(parents=True)
    install.symlink_to(Path("..") / ".." / "src" / "claude" / "skills" / "alpha")

    rc = generate_skills.generate_skills(config, tmp_path)

    assert rc == 0
    assert _snapshot(tmp_path) == after_first


def test_support_sync_alone_leaves_a_templated_skill_untouched(tmp_path: Path) -> None:
    """The stanza-less platform path calls the support sync directly.

    The retired mirror copied ``.claude`` support files into the plugin tree
    (2 written). Now a shipped skill's plugin copy is the only copy, so the sync
    writes and removes nothing.
    """
    _seed_new_skill(tmp_path)
    before = _snapshot(tmp_path)

    result = skill_support_mirror.prune_stale_claude_skill_support(tmp_path)

    assert result == (0, 0, 0, [])
    assert _snapshot(tmp_path) == before


def test_directory_without_template_or_skill_md_is_still_ignored(tmp_path: Path) -> None:
    """Negative control: a bare directory is not a skill."""
    _seed_new_skill(tmp_path)
    stray = tmp_path / "src" / "claude" / "skills" / "stray" / "references"
    stray.mkdir(parents=True)
    (stray / "x.md").write_text("x\n", encoding="utf-8")
    config = _config(tmp_path)

    generate_skills.generate_skills(config, tmp_path)

    assert not (tmp_path / "src" / "claude" / "skills" / "stray" / "SKILL.md").exists()
    assert not (tmp_path / "out" / "skills" / "stray").exists()


def test_templated_skill_with_no_rendered_skill_md_does_not_break_other_skills(
    tmp_path: Path,
) -> None:
    """Edge: an existing skill with its rendered SKILL.md still mirrors."""
    _seed_new_skill(tmp_path)
    old = tmp_path / "src" / "claude" / "skills" / "beta"
    old.mkdir(parents=True)
    (old / "SKILL.md").write_text(_BODY.replace("alpha", "beta"), encoding="utf-8")
    (old / "scripts").mkdir()
    (old / "scripts" / "b.py").write_text("b\n", encoding="utf-8")
    config = _config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path)

    assert rc == 0
    assert (tmp_path / "out" / "skills" / "beta" / "scripts" / "b.py").is_file()
    assert (tmp_path / "out" / "skills" / "alpha" / "scripts" / "run.py").is_file()
