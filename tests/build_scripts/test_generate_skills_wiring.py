"""Tests for generate_skills.py's compile-then-copy wiring and CLI.

Split out of test_generate_skills_template_compile.py (taste-lint 500-line
file-size ceiling; ADR-109 B3 pushed that file over it) rather than grown in
place: discover/owned_targets/compile_all stay there, generate_skills()'s
copy-loop wiring and the --validate CLI entry point move here. Fixture
helpers live in the shared ``_skill_template_helpers.py``.
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
from _skill_template_helpers import (  # noqa: E402
    install_target,
    minimal_platform_config,
    run_cli,
    seed_target_dir,
    target,
    write_partial,
    write_template,
)


def test_generate_skills_runs_compile_before_copy_and_writes_rendered_target(
    tmp_path: Path,
) -> None:
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "# sync\n{{> greet}}\n")
    skill_dir = tmp_path / ".claude" / "skills" / "sync"
    skill_dir.mkdir(parents=True)
    # ADR-109 B3: the install-tree SKILL.md is what a prior binplace run
    # would have left in place; _iter_skill_sources needs it present to
    # discover "sync" as a skill to copy, but generate_skills' copy loop
    # must read the just-rendered PLUGIN-tree content, not this stale one.
    (skill_dir / "SKILL.md").write_text("stale install copy\n", encoding="utf-8")
    config = minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path)

    assert rc == 0
    dst = target(tmp_path, "sync")
    assert dst.read_text(encoding="utf-8") == "# sync\nhi\n"
    # Copy loop still ran, and read the fresh plugin-tree render, not the
    # stale install-tree copy still sitting in .claude/skills/.
    mirror = tmp_path / "out" / "skills" / "sync" / "SKILL.md"
    assert mirror.is_file()
    assert mirror.read_text(encoding="utf-8") == "# sync\nhi\n"


def test_generate_skills_nonzero_compile_returns_before_copy(tmp_path: Path) -> None:
    write_template(tmp_path, "sync", "{{var}}\n")
    skill_dir = tmp_path / ".claude" / "skills" / "sync"
    skill_dir.mkdir(parents=True)
    skill_dir_md = skill_dir / "SKILL.md"
    skill_dir_md.write_text("# sync\n", encoding="utf-8")
    config = minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path)

    assert rc == 2
    assert not (tmp_path / "out" / "skills" / "sync").exists()


def test_generate_skills_validate_true_compares_without_writing_then_still_copies(
    tmp_path: Path,
) -> None:
    """build_all.py --check shape: validate=True skips the write but still copies."""
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    dst.write_text("hi\n", encoding="utf-8")
    # validate=True never writes, so the install-tree copy _iter_skill_sources
    # needs must already be on disk, the same way a prior binplace run
    # would have left it (ADR-109 B3).
    install_target(tmp_path, "sync").write_text("hi\n", encoding="utf-8")
    config = minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path, validate=True)

    assert rc == 0
    assert (tmp_path / "out" / "skills" / "sync" / "SKILL.md").is_file()


def test_generate_skills_validate_true_with_drift_returns_one_and_skips_copy(
    tmp_path: Path,
) -> None:
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    dst.write_text("hand edited\n", encoding="utf-8")
    config = minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path, validate=True)

    assert rc == 1
    assert dst.read_text(encoding="utf-8") == "hand edited\n"
    assert not (tmp_path / "out" / "skills" / "sync").exists()


def test_cli_validate_exit_0_on_clean_tree(tmp_path: Path) -> None:
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    dst.write_text("hi\n", encoding="utf-8")

    result = run_cli("--repo-root", str(tmp_path), "--validate")

    assert result.returncode == 0, result.stderr


def test_cli_validate_exit_1_on_drift(tmp_path: Path) -> None:
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    dst.write_text("hand edited\n", encoding="utf-8")

    result = run_cli("--repo-root", str(tmp_path), "--validate")

    assert result.returncode == 1
    assert "DRIFTED" in result.stdout
    assert dst.read_text(encoding="utf-8") == "hand edited\n"


def test_cli_validate_exit_2_on_disallowed_tag(tmp_path: Path) -> None:
    write_template(tmp_path, "sync", "{{var}}\n")
    seed_target_dir(tmp_path, "sync")

    result = run_cli("--repo-root", str(tmp_path), "--validate")

    assert result.returncode == 2
    assert "{{var}}" in result.stderr


def test_cli_validate_needs_no_platform_config(tmp_path: Path) -> None:
    """--validate never resolves a platform config (main()'s own contract)."""
    result = run_cli("--repo-root", str(tmp_path), "--validate")

    assert result.returncode == 0
