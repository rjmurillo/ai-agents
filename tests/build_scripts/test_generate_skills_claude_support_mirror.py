"""Tests for the Claude plugin-tree stale-copy reconciliation (ADR-119).

ADR-109 B3 mirrored ``.claude/skills/<name>/`` support files into
``src/claude/skills/<name>/``. ADR-119 retired that mirror: a shipped skill's
``.claude/skills/<name>`` is a relative symlink to ``src/claude/skills/<name>``,
so the plugin tree holds the only copy and is edited in place.
``generate_skills.prune_stale_claude_skill_support`` now only removes the stale
``src/claude/skills/<name>/`` left behind when a skill becomes
``metadata.distribution: repo-local``, and refuses while that skill's
``.claude/skills/<name>`` is still a symlink into the plugin tree.
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
from _skill_template_helpers import minimal_platform_config  # noqa: E402

LOCAL_SKILL_MD = "---\nname: {name}\nmetadata:\n  distribution: repo-local\n---\n\nbody\n"
SHIPPED_SKILL_MD = "---\nname: {name}\n---\n\nbody\n"

needs_symlinks = pytest.mark.skipif(
    sys.platform == "win32", reason="creating symlinks needs elevated rights on Windows"
)

# Helpers ----------------------------------------------------------------


def _write_install_skill(repo: Path, name: str, *, local: bool) -> Path:
    """Seed a real ``.claude/skills/<name>/SKILL.md`` with the given distribution."""
    skill_dir = repo / ".claude" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    body = (LOCAL_SKILL_MD if local else SHIPPED_SKILL_MD).format(name=name)
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    return skill_dir


def _write_plugin_copy(repo: Path, name: str, files: dict[str, str]) -> Path:
    """Seed ``src/claude/skills/<name>/`` with the given files."""
    skill_dir = repo / "src" / "claude" / "skills" / name
    for rel, body in files.items():
        path = skill_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return skill_dir


def _plugin(repo: Path, name: str, rel: str) -> Path:
    return repo / "src" / "claude" / "skills" / name / rel


# Shipped skills are never touched ----------------------------------------


def test_shipped_skill_plugin_copy_is_left_alone(tmp_path: Path) -> None:
    """A shipped skill needs no mirror: nothing written, nothing removed."""
    _write_plugin_copy(tmp_path, "alpha", {"SKILL.md": "# a\n", "scripts/run.py": "x\n"})

    result = generate_skills.prune_stale_claude_skill_support(tmp_path)

    assert result == (0, 0, 0, [])
    assert _plugin(tmp_path, "alpha", "scripts/run.py").read_text() == "x\n"
    assert _plugin(tmp_path, "alpha", "SKILL.md").is_file()


def test_shipped_skill_with_install_dir_does_not_gain_plugin_files(tmp_path: Path) -> None:
    """The retired .claude->src copy must not run: a real install dir stays unmirrored."""
    skill_dir = _write_install_skill(tmp_path, "alpha", local=False)
    (skill_dir / "scripts").mkdir()
    (skill_dir / "scripts" / "run.py").write_text("x\n", encoding="utf-8")

    result = generate_skills.prune_stale_claude_skill_support(tmp_path)

    assert result == (0, 0, 0, [])
    assert not (tmp_path / "src" / "claude" / "skills" / "alpha").exists()


def test_top_level_agents_and_claude_md_are_not_skills(tmp_path: Path) -> None:
    root = tmp_path / "src" / "claude" / "skills"
    root.mkdir(parents=True)
    (root / "AGENTS.md").write_text("guide\n", encoding="utf-8")
    (root / "CLAUDE.md").write_text("guide\n", encoding="utf-8")

    result = generate_skills.prune_stale_claude_skill_support(tmp_path)

    assert result == (0, 0, 0, [])
    assert (root / "AGENTS.md").is_file()
    assert (root / "CLAUDE.md").is_file()


def test_absent_trees_are_a_silent_noop(tmp_path: Path) -> None:
    (tmp_path / "skills_elsewhere" / "alpha").mkdir(parents=True)
    (tmp_path / "skills_elsewhere" / "alpha" / "SKILL.md").write_text("# a\n", encoding="utf-8")

    assert generate_skills.prune_stale_claude_skill_support(tmp_path) == (0, 0, 0, [])


# Repo-local skills: stale plugin copy is pruned ---------------------------


def test_stale_plugin_copy_of_repo_local_skill_is_removed(tmp_path: Path) -> None:
    _write_install_skill(tmp_path, "alpha", local=True)
    _write_plugin_copy(
        tmp_path, "alpha", {"SKILL.md": "# a\n", "scripts/run.py": "x\n", "references/n.md": "n\n"}
    )

    written, removed, skipped, errors = generate_skills.prune_stale_claude_skill_support(tmp_path)

    assert errors == []
    assert (written, skipped) == (0, 0)
    assert removed == 3
    assert not (tmp_path / "src" / "claude" / "skills" / "alpha").exists()
    # The real install directory is the repo-local skill's canonical home.
    assert (tmp_path / ".claude" / "skills" / "alpha" / "SKILL.md").is_file()


def test_clean_second_run_removes_nothing(tmp_path: Path) -> None:
    _write_install_skill(tmp_path, "alpha", local=True)
    _write_plugin_copy(tmp_path, "alpha", {"scripts/run.py": "x\n"})
    generate_skills.prune_stale_claude_skill_support(tmp_path)

    assert generate_skills.prune_stale_claude_skill_support(tmp_path) == (0, 0, 0, [])


def test_pruning_one_repo_local_skill_keeps_a_shipped_neighbour(tmp_path: Path) -> None:
    _write_install_skill(tmp_path, "local-one", local=True)
    _write_plugin_copy(tmp_path, "local-one", {"scripts/run.py": "x\n"})
    _write_plugin_copy(tmp_path, "shipped-one", {"scripts/run.py": "y\n"})

    _, removed, _, errors = generate_skills.prune_stale_claude_skill_support(tmp_path)

    assert errors == []
    assert removed == 1
    assert not (tmp_path / "src" / "claude" / "skills" / "local-one").exists()
    assert _plugin(tmp_path, "shipped-one", "scripts/run.py").read_text() == "y\n"


def test_nested_directories_are_pruned_once_empty(tmp_path: Path) -> None:
    _write_install_skill(tmp_path, "alpha", local=True)
    _write_plugin_copy(tmp_path, "alpha", {"scripts/deep/nested/run.py": "x\n"})

    generate_skills.prune_stale_claude_skill_support(tmp_path)

    assert not (tmp_path / "src" / "claude" / "skills" / "alpha").exists()


# check / what_if: report, never delete -----------------------------------


def test_check_mode_reports_a_stale_copy_without_deleting_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_install_skill(tmp_path, "alpha", local=True)
    _write_plugin_copy(tmp_path, "alpha", {"scripts/run.py": "x\n"})

    _, removed, _, errors = generate_skills.prune_stale_claude_skill_support(tmp_path, check=True)

    assert errors == []
    assert removed == 1
    assert "DRIFT" in capsys.readouterr().out
    assert _plugin(tmp_path, "alpha", "scripts/run.py").read_text() == "x\n"


def test_check_mode_on_a_clean_tree_reports_nothing(tmp_path: Path) -> None:
    _write_install_skill(tmp_path, "alpha", local=True)
    _write_plugin_copy(tmp_path, "beta", {"scripts/run.py": "x\n"})

    assert generate_skills.prune_stale_claude_skill_support(tmp_path, check=True) == (0, 0, 0, [])


def test_check_mode_wins_when_what_if_is_also_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_install_skill(tmp_path, "alpha", local=True)
    _write_plugin_copy(tmp_path, "alpha", {"scripts/run.py": "x\n"})

    _, removed, _, _ = generate_skills.prune_stale_claude_skill_support(
        tmp_path, check=True, what_if=True
    )

    out = capsys.readouterr().out
    assert removed == 1
    assert "DRIFT" in out
    assert "Would remove" not in out
    assert _plugin(tmp_path, "alpha", "scripts/run.py").is_file()


def test_what_if_does_not_remove(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_install_skill(tmp_path, "alpha", local=True)
    _write_plugin_copy(tmp_path, "alpha", {"scripts/run.py": "x\n"})

    _, removed, _, errors = generate_skills.prune_stale_claude_skill_support(tmp_path, what_if=True)

    assert errors == []
    assert removed == 1
    assert "Would remove" in capsys.readouterr().out
    assert _plugin(tmp_path, "alpha", "scripts/run.py").is_file()


# Refusals ------------------------------------------------------------------


@needs_symlinks
def test_repo_local_skill_still_linked_into_plugin_tree_is_refused(tmp_path: Path) -> None:
    """Removing the plugin copy while .claude/skills/<name> links to it would lose the skill."""
    plugin_dir = _write_plugin_copy(
        tmp_path,
        "alpha",
        {"SKILL.md": LOCAL_SKILL_MD.format(name="alpha"), "scripts/run.py": "x\n"},
    )
    install = tmp_path / ".claude" / "skills" / "alpha"
    install.parent.mkdir(parents=True)
    install.symlink_to(Path("..") / ".." / "src" / "claude" / "skills" / "alpha")

    written, removed, skipped, errors = generate_skills.prune_stale_claude_skill_support(tmp_path)

    assert (written, removed, skipped) == (0, 0, 0)
    assert len(errors) == 1
    assert "still a symlink" in errors[0]
    assert (plugin_dir / "scripts" / "run.py").read_text() == "x\n"


@needs_symlinks
def test_symlinked_file_inside_a_stale_copy_is_refused(tmp_path: Path) -> None:
    _write_install_skill(tmp_path, "alpha", local=True)
    plugin_dir = _write_plugin_copy(tmp_path, "alpha", {"scripts/run.py": "x\n"})
    (plugin_dir / "scripts" / "linked.py").symlink_to(tmp_path / "nowhere")

    _, removed, _, errors = generate_skills.prune_stale_claude_skill_support(tmp_path)

    assert removed == 0
    assert len(errors) == 1
    assert "symlink inside a skill directory refused" in errors[0]
    assert (plugin_dir / "scripts" / "run.py").is_file()


@needs_symlinks
def test_symlinked_directory_inside_a_stale_copy_is_refused(tmp_path: Path) -> None:
    _write_install_skill(tmp_path, "alpha", local=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("keep\n", encoding="utf-8")
    plugin_dir = _write_plugin_copy(tmp_path, "alpha", {"SKILL.md": "# a\n"})
    (plugin_dir / "scripts").symlink_to(outside, target_is_directory=True)

    _, removed, _, errors = generate_skills.prune_stale_claude_skill_support(tmp_path)

    assert removed == 0
    assert len(errors) == 1
    assert (outside / "secret.txt").read_text() == "keep\n"


@needs_symlinks
def test_symlinked_plugin_skill_directory_is_refused(tmp_path: Path) -> None:
    _write_install_skill(tmp_path, "alpha", local=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("keep\n", encoding="utf-8")
    root = tmp_path / "src" / "claude" / "skills"
    root.mkdir(parents=True)
    (root / "alpha").symlink_to(outside, target_is_directory=True)

    _, removed, _, errors = generate_skills.prune_stale_claude_skill_support(tmp_path)

    assert removed == 0
    assert len(errors) == 1
    assert "symlinked skill directory refused" in errors[0]
    assert (outside / "secret.txt").is_file()


@needs_symlinks
def test_one_bad_skill_does_not_block_the_others(tmp_path: Path) -> None:
    _write_install_skill(tmp_path, "aaa-bad", local=True)
    bad = _write_plugin_copy(tmp_path, "aaa-bad", {"scripts/run.py": "x\n"})
    (bad / "scripts" / "linked.py").symlink_to(tmp_path / "nowhere")
    _write_install_skill(tmp_path, "zzz-good", local=True)
    _write_plugin_copy(tmp_path, "zzz-good", {"scripts/run.py": "y\n"})

    _, removed, _, errors = generate_skills.prune_stale_claude_skill_support(tmp_path)

    assert len(errors) == 1
    assert removed == 1
    assert not (tmp_path / "src" / "claude" / "skills" / "zzz-good").exists()
    assert (bad / "scripts" / "run.py").is_file()


def test_malformed_distribution_field_is_an_error_not_a_crash(tmp_path: Path) -> None:
    skill_dir = tmp_path / ".claude" / "skills" / "alpha"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: alpha\nmetadata:\n  distribution: repo_local\n---\n", encoding="utf-8"
    )

    written, removed, skipped, errors = generate_skills.prune_stale_claude_skill_support(tmp_path)

    assert (written, removed, skipped) == (0, 0, 0)
    assert len(errors) == 1
    assert "distribution" in errors[0]


# End-to-end wiring through generate_skills() --------------------------------


def test_generate_skills_prunes_the_stale_copy_before_the_copy_loop(tmp_path: Path) -> None:
    skill_dir = _write_install_skill(tmp_path, "alpha", local=True)
    (skill_dir / "run.py").write_text("print('hi')\n", encoding="utf-8")
    _write_plugin_copy(tmp_path, "alpha", {"scripts/run.py": "stale\n"})
    # A shipped skill gives the Copilot copy loop something to mirror.
    _write_install_skill(tmp_path, "beta", local=False)
    config = minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path)

    assert rc == 0
    assert (tmp_path / "out" / "skills" / "beta" / "SKILL.md").is_file()
    assert not (tmp_path / "src" / "claude" / "skills" / "alpha").exists()
    assert (tmp_path / ".claude" / "skills" / "alpha" / "run.py").read_text() == "print('hi')\n"


@needs_symlinks
def test_generate_skills_returns_1_and_skips_the_copy_loop_on_a_sync_error(
    tmp_path: Path,
) -> None:
    _write_install_skill(tmp_path, "alpha", local=True)
    plugin_dir = _write_plugin_copy(tmp_path, "alpha", {"scripts/run.py": "x\n"})
    (plugin_dir / "scripts" / "linked.py").symlink_to(tmp_path / "nowhere")
    config = minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path)

    assert rc == 1
    # Sync errors return before the Copilot copy loop ever runs.
    assert not (tmp_path / "out" / "skills").exists()
