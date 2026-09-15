"""Tests for the Claude plugin-tree skill support-file mirror.

ADR-109 B3 rendered only ``SKILL.md`` into ``src/claude/skills/<name>/``,
leaving 84 skills' ``scripts/``, ``references/``, ``tests/``, and other
support files unmirrored: a plugin install's ``src/claude/skills/`` tree
told the agent to run a script that was never shipped there (see the B3
follow-up handoff). ``.claude/skills/<name>/`` stays the canonical,
hand-maintained source for everything except ``SKILL.md``;
``generate_skills.sync_claude_plugin_skill_support`` copies it into
``src/claude/skills/<name>/`` the same way ``_copy_skill_tree`` already
mirrors it into ``src/copilot-cli/skills/<name>/`` for the Copilot target,
except merge-resolver is never excluded (it ships in the Claude plugin,
just not the Copilot toolkit).
"""

from __future__ import annotations

import sys
from pathlib import Path

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import generate_skills  # noqa: E402
from _skill_template_helpers import minimal_platform_config  # noqa: E402

# Helpers ----------------------------------------------------------------


def _write_skill(
    repo: Path, name: str, *, skill_md: str = "# skill\n", files: dict[str, str] | None = None
) -> Path:
    """Seed ``.claude/skills/<name>/`` with SKILL.md plus optional support files."""
    skill_dir = repo / ".claude" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    for rel, body in (files or {}).items():
        path = skill_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return skill_dir


def _target(repo: Path, name: str, rel: str) -> Path:
    return repo / "src" / "claude" / "skills" / name / rel


# Copy -------------------------------------------------------------------


def test_copies_support_files_into_plugin_tree(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "alpha",
        files={"scripts/run.py": "print('hi')\n", "references/notes.md": "notes\n"},
    )

    written, removed, skipped, errors = generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert errors == []
    assert written == 2
    assert removed == 0
    assert skipped == 0
    assert _target(tmp_path, "alpha", "scripts/run.py").read_text() == "print('hi')\n"
    assert _target(tmp_path, "alpha", "references/notes.md").read_text() == "notes\n"


def test_clean_second_run_writes_nothing(tmp_path: Path) -> None:
    """A no-op run must report 0 written, not recount every unchanged file.

    Regression for the live-repo finding: the mirror recopied every file on
    every invocation regardless of whether the destination already matched,
    so ``build_all.py --check`` printed "526 written" on an already-clean
    tree and mtimes churned on every run.
    """
    _write_skill(
        tmp_path,
        "alpha",
        files={"scripts/run.py": "print('hi')\n", "references/notes.md": "notes\n"},
    )
    first_written, _, _, first_errors = generate_skills.sync_claude_plugin_skill_support(tmp_path)
    assert first_errors == []
    assert first_written == 2

    second_written, second_removed, second_skipped, second_errors = (
        generate_skills.sync_claude_plugin_skill_support(tmp_path)
    )

    assert second_errors == []
    assert second_written == 0
    assert second_removed == 0
    assert second_skipped == 0


def test_mode_only_divergence_is_still_a_write(tmp_path: Path) -> None:
    """Matching bytes with a different permission mode is still corrected."""
    skill_dir = _write_skill(tmp_path, "alpha", files={"scripts/run.py": "print('hi')\n"})
    (skill_dir / "scripts" / "run.py").chmod(0o755)
    generate_skills.sync_claude_plugin_skill_support(tmp_path)
    target = _target(tmp_path, "alpha", "scripts/run.py")
    target.chmod(0o644)

    written, _, _, errors = generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert errors == []
    assert written == 1
    assert target.stat().st_mode & 0o777 == 0o755


def test_skill_md_is_never_written_by_the_mirror(tmp_path: Path) -> None:
    """SKILL.md is skill_templates.compile_all's target, not this mirror's."""
    _write_skill(tmp_path, "alpha", files={"scripts/run.py": "print('hi')\n"})
    plugin_skill_md = _target(tmp_path, "alpha", "SKILL.md")
    plugin_skill_md.parent.mkdir(parents=True, exist_ok=True)
    plugin_skill_md.write_text("rendered by the template compiler\n", encoding="utf-8")

    generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert plugin_skill_md.read_text() == "rendered by the template compiler\n"


# Drift: modified, missing, extra ----------------------------------------


def test_modified_support_file_is_corrected(tmp_path: Path) -> None:
    _write_skill(tmp_path, "alpha", files={"scripts/run.py": "correct\n"})
    stale = _target(tmp_path, "alpha", "scripts/run.py")
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("hand-edited drift\n", encoding="utf-8")

    written, removed, _, errors = generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert errors == []
    assert written == 1
    assert stale.read_text() == "correct\n"


def test_missing_support_file_is_copied_in(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "alpha",
        files={"scripts/a.py": "a\n", "scripts/b.py": "b\n"},
    )
    _target(tmp_path, "alpha", "scripts/a.py").parent.mkdir(parents=True, exist_ok=True)
    _target(tmp_path, "alpha", "scripts/a.py").write_text("a\n", encoding="utf-8")
    # scripts/b.py has no counterpart yet under src/claude/skills.

    written, _, _, errors = generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert errors == []
    # _copy_skill_tree compares bytes and mode before writing; a.py already
    # matches its source and is not recounted, only b.py is a real write.
    assert written == 1
    assert _target(tmp_path, "alpha", "scripts/b.py").read_text() == "b\n"


def test_stale_extra_file_is_removed(tmp_path: Path) -> None:
    _write_skill(tmp_path, "alpha", files={"scripts/keep.py": "keep\n"})
    stale_extra = _target(tmp_path, "alpha", "scripts/gone.py")
    stale_extra.parent.mkdir(parents=True, exist_ok=True)
    stale_extra.write_text("removed source, stale copy\n", encoding="utf-8")

    _, removed, _, errors = generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert errors == []
    assert removed == 1
    assert not stale_extra.exists()
    assert _target(tmp_path, "alpha", "scripts/keep.py").is_file()


def test_stale_extra_directory_is_pruned_once_empty(tmp_path: Path) -> None:
    _write_skill(tmp_path, "alpha", files={"SKILL.md": "# alpha\n"})
    stale_dir = _target(tmp_path, "alpha", "references")
    stale_dir.mkdir(parents=True, exist_ok=True)
    (stale_dir / "gone.md").write_text("stale\n", encoding="utf-8")

    generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert not stale_dir.exists()


# Exclusions ---------------------------------------------------------------


def test_pycache_and_bytecode_excluded(tmp_path: Path) -> None:
    skill_dir = _write_skill(tmp_path, "alpha", files={"scripts/run.py": "ok\n"})
    cache = skill_dir / "scripts" / "__pycache__"
    cache.mkdir()
    (cache / "run.cpython-314.pyc").write_bytes(b"")

    generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert not _target(tmp_path, "alpha", "scripts/__pycache__").exists()


def test_top_level_agents_and_claude_md_are_not_skills(tmp_path: Path) -> None:
    skills_root = tmp_path / ".claude" / "skills"
    skills_root.mkdir(parents=True)
    (skills_root / "AGENTS.md").write_text("# header\n", encoding="utf-8")
    (skills_root / "CLAUDE.md").write_text("# header\n", encoding="utf-8")
    _write_skill(tmp_path, "real", files={"scripts/run.py": "ok\n"})

    written, _, _, errors = generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert errors == []
    assert written == 1
    assert not (tmp_path / "src" / "claude" / "skills" / "AGENTS.md").exists()


def test_merge_resolver_is_not_excluded_unlike_the_copilot_mirror(tmp_path: Path) -> None:
    """The Copilot mirror excludes merge-resolver (copilot-cli.yaml); this one must not."""
    _write_skill(tmp_path, "merge-resolver", files={"scripts/resolve.py": "resolve\n"})

    written, _, _, errors = generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert errors == []
    assert written == 1
    assert _target(tmp_path, "merge-resolver", "scripts/resolve.py").read_text() == "resolve\n"


# check mode: direct comparison, never writes -------------------------------
#
# Regression for the coordinator's live-probe finding on bf4d0117f: appending
# a line to a tracked mirror file, or adding an untracked extra file, under
# src/claude/skills/merge-resolver/scripts/ made `build_all.py --check` exit
# 0 and silently erase the change. That happened because the old sync call
# had no way to run "compare only": it always wrote for real, which either
# overwrote a hand edit back to canonical content (masking it from the
# later git-diff staleness check) or deleted an untracked extra outright,
# both before the diff ever got a chance to see them. These tests seed the
# repo the way the live tree is laid out -- a support file already mirrored
# and untouched, one hand-edited in place, one extra with no source -- and
# assert `check=True` reports every mismatch without ever touching disk.


def test_check_mode_reports_a_hand_edit_without_correcting_it(tmp_path: Path) -> None:
    """A support file hand-edited directly under the mirror is drift, not a fix target.

    Without the fix, `check=True` didn't exist and the sync always wrote
    for real, silently overwriting this hand edit back to the canonical
    content before any staleness check could see it: this test fails
    against that code (`written == 0`, mirror already "corrected") and
    passes once `check=True` only compares.
    """
    _write_skill(tmp_path, "alpha", files={"scripts/run.py": "correct\n"})
    generate_skills.sync_claude_plugin_skill_support(tmp_path)
    mirror = _target(tmp_path, "alpha", "scripts/run.py")
    mirror.write_text("hand-edited, never committed\n", encoding="utf-8")

    written, removed, _, errors = generate_skills.sync_claude_plugin_skill_support(
        tmp_path, check=True
    )

    assert errors == []
    assert written == 1
    assert removed == 0
    assert mirror.read_text() == "hand-edited, never committed\n", (
        "check=True must never write; the caller decides what to do with the report"
    )


def test_check_mode_reports_an_extra_file_without_deleting_it(tmp_path: Path) -> None:
    """An extra mirror file with no canonical source is drift, not a delete target.

    Without the fix, the sync always pruned real stale extras during
    generation, before the git-diff staleness check ran, so an untracked
    extra was removed and the run reported clean. This fails against that
    code (`removed == 0`, file already gone) and passes once `check=True`
    only reports.
    """
    _write_skill(tmp_path, "alpha", files={"scripts/keep.py": "keep\n"})
    generate_skills.sync_claude_plugin_skill_support(tmp_path)
    extra = _target(tmp_path, "alpha", "scripts/probe_extra.py")
    extra.write_text("# probe\n", encoding="utf-8")

    written, removed, _, errors = generate_skills.sync_claude_plugin_skill_support(
        tmp_path, check=True
    )

    assert errors == []
    assert written == 0
    assert removed == 1
    assert extra.is_file(), "check=True must never delete; the caller decides"


def test_check_mode_on_a_clean_tree_reports_nothing(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "alpha",
        files={"scripts/run.py": "print('hi')\n", "references/notes.md": "notes\n"},
    )
    generate_skills.sync_claude_plugin_skill_support(tmp_path)

    written, removed, skipped, errors = generate_skills.sync_claude_plugin_skill_support(
        tmp_path, check=True
    )

    assert (written, removed, skipped, errors) == (0, 0, 0, [])


def test_check_mode_wins_when_what_if_is_also_set(tmp_path: Path) -> None:
    """``check`` and ``what_if`` are mutually exclusive; ``check`` wins (docstring contract)."""
    _write_skill(tmp_path, "alpha", files={"scripts/run.py": "correct\n"})
    generate_skills.sync_claude_plugin_skill_support(tmp_path)
    mirror = _target(tmp_path, "alpha", "scripts/run.py")
    mirror.write_text("drifted\n", encoding="utf-8")

    written, _, _, errors = generate_skills.sync_claude_plugin_skill_support(
        tmp_path, what_if=True, check=True
    )

    assert errors == []
    assert written == 1  # what_if alone reports 0 (see test_what_if_does_not_write_or_remove)
    assert mirror.read_text() == "drifted\n"


# Symlink refusal ------------------------------------------------------------


def test_symlinked_file_inside_a_skill_directory_is_refused(tmp_path: Path) -> None:
    skill_dir = _write_skill(tmp_path, "alpha", files={"scripts/run.py": "ok\n"})
    outside = tmp_path / "outside.txt"
    outside.write_text("do not follow me\n", encoding="utf-8")
    (skill_dir / "scripts" / "linked.py").symlink_to(outside)

    written, removed, _, errors = generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert len(errors) == 1
    assert "alpha" in errors[0] and "symlink" in errors[0]
    # A refused skill mirrors nothing at all, rather than a partial copy.
    assert written == 0
    assert removed == 0
    assert not _target(tmp_path, "alpha", "scripts/run.py").exists()


def test_symlinked_directory_inside_a_skill_is_refused(tmp_path: Path) -> None:
    skill_dir = _write_skill(tmp_path, "alpha")
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "leaked.py").write_text("leaked\n", encoding="utf-8")
    (skill_dir / "scripts").symlink_to(outside_dir)

    _, _, _, errors = generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert len(errors) == 1
    assert "symlink" in errors[0]
    assert not _target(tmp_path, "alpha", "scripts/leaked.py").exists()


def test_one_bad_skill_does_not_block_the_others(tmp_path: Path) -> None:
    skill_dir = _write_skill(tmp_path, "bad")
    (skill_dir / "linked.py").symlink_to(tmp_path / "nowhere")
    _write_skill(tmp_path, "good", files={"scripts/run.py": "ok\n"})

    written, _, _, errors = generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert len(errors) == 1
    assert written == 1
    assert _target(tmp_path, "good", "scripts/run.py").is_file()


# NO-REGEN sentinel -----------------------------------------------------------


def test_no_regen_protected_target_is_not_overwritten(tmp_path: Path) -> None:
    _write_skill(tmp_path, "alpha", files={"scripts/run.py": "fresh\n"})
    protected = _target(tmp_path, "alpha", "scripts/run.py")
    protected.parent.mkdir(parents=True, exist_ok=True)
    protected.write_text("hand-edited; do not overwrite\n", encoding="utf-8")
    protected.with_suffix(".py.noregen").write_text("", encoding="utf-8")

    written, _, skipped, errors = generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert errors == []
    assert written == 0
    assert skipped == 1
    assert protected.read_text() == "hand-edited; do not overwrite\n"


def test_no_regen_protected_stale_extra_is_kept(tmp_path: Path) -> None:
    _write_skill(tmp_path, "alpha")
    protected_extra = _target(tmp_path, "alpha", "scripts/gone.py")
    protected_extra.parent.mkdir(parents=True, exist_ok=True)
    protected_extra.write_text("hand-edited; do not delete\n", encoding="utf-8")
    protected_extra.with_suffix(".py.noregen").write_text("", encoding="utf-8")

    _, removed, _, errors = generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert errors == []
    assert removed == 0
    assert protected_extra.is_file()


# what_if / absent source -----------------------------------------------------


def test_what_if_does_not_write_or_remove(tmp_path: Path) -> None:
    _write_skill(tmp_path, "alpha", files={"scripts/run.py": "ok\n"})

    written, removed, _, errors = generate_skills.sync_claude_plugin_skill_support(
        tmp_path, what_if=True
    )

    assert errors == []
    assert written == 0  # _copy_skill_tree's what_if branch never counts
    assert removed == 0
    assert not _target(tmp_path, "alpha", "scripts/run.py").exists()


def test_absent_source_tree_is_a_silent_noop(tmp_path: Path) -> None:
    """A synthetic fixture whose skills live elsewhere leaves this mirror inert.

    Mirrors ``skill_templates.compile_all``'s own contract: both read the
    real, repo-global ``.claude/skills/`` tree unconditionally, never a
    caller-supplied ``sourceDir``.
    """
    (tmp_path / "skills_elsewhere" / "alpha").mkdir(parents=True)
    (tmp_path / "skills_elsewhere" / "alpha" / "SKILL.md").write_text("# alpha\n", encoding="utf-8")

    written, removed, skipped, errors = generate_skills.sync_claude_plugin_skill_support(tmp_path)

    assert (written, removed, skipped, errors) == (0, 0, 0, [])


# End-to-end wiring through generate_skills() --------------------------------


def test_generate_skills_wires_the_mirror_into_the_copy_loop(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "alpha",
        files={"scripts/run.py": "print('hi')\n", "references/notes.md": "notes\n"},
    )
    config = minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path)

    assert rc == 0
    assert _target(tmp_path, "alpha", "scripts/run.py").read_text() == "print('hi')\n"
    # The Copilot copy loop (this fixture's configured outputDir) still runs
    # independently, unaffected by the new mirror.
    assert (tmp_path / "out" / "skills" / "alpha" / "scripts" / "run.py").is_file()
    # The canonical source is read-only to this whole run.
    assert (tmp_path / ".claude" / "skills" / "alpha" / "scripts" / "run.py").read_text() == (
        "print('hi')\n"
    )


def test_generate_skills_returns_1_and_skips_the_copy_loop_on_a_mirror_error(
    tmp_path: Path,
) -> None:
    skill_dir = _write_skill(tmp_path, "alpha", files={"scripts/run.py": "ok\n"})
    (skill_dir / "scripts" / "linked.py").symlink_to(tmp_path / "nowhere")
    config = minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path)

    assert rc == 1
    # Sync errors return before the Copilot copy loop ever runs.
    assert not (tmp_path / "out" / "skills").exists()
