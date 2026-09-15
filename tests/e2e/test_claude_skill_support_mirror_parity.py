"""Regression guard: every .claude/skills/ support file ships in src/claude/skills/.

ADR-109 B3 (PR #5785) rendered only ``SKILL.md`` into
``src/claude/skills/<name>/``; the 84 skills that also carry ``scripts/``,
``references/``, ``tests/``, or other support files under
``.claude/skills/<name>/`` had nothing mirroring those into the Claude
plugin tree, so an installed plugin's SKILL.md could point at a script that
was never shipped. ``build/scripts/generate_skills.py``'s
``sync_claude_plugin_skill_support`` closes that gap (the B3 follow-up).

This is the always-on, non-CLI regression test for the gap: no CLI, no
``RUN_CLI_E2E`` gate, just a byte-for-byte parity check over the two
committed trees. It complements (does not replace)
``tests/build_scripts/test_generate_skills_claude_support_mirror.py``,
which exercises the mirror function itself against synthetic fixtures.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_SOURCE = REPO_ROOT / ".claude" / "skills"
_SKILLS_TARGET = REPO_ROOT / "src" / "claude" / "skills"
_SKILL_MD = Path("SKILL.md")
_TOP_LEVEL_EXCLUDES = frozenset({"AGENTS.md", "CLAUDE.md"})


def _support_relpaths(skill_dir: Path) -> set[Path]:
    """Every file under ``skill_dir`` except SKILL.md and bytecode caches."""
    rels: set[Path] = set()
    for path in skill_dir.rglob("*"):
        if path.is_dir():
            continue
        if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
            continue
        rel = path.relative_to(skill_dir)
        if rel == _SKILL_MD:
            continue
        rels.add(rel)
    return rels


def _skill_dirs(root: Path) -> list[Path]:
    return sorted(
        child
        for child in root.iterdir()
        if child.is_dir()
        and child.name not in _TOP_LEVEL_EXCLUDES
        and (child / "SKILL.md").is_file()
    )


def test_every_skill_support_file_has_a_twin_in_the_claude_plugin_tree() -> None:
    """Every .claude/skills/<name>/ support file ships, byte-identical, under
    src/claude/skills/<name>/. A missing, extra, or content-mismatched file
    here means a skill's plugin install will reference a script, reference
    doc, or test that is not actually shipped (or ships stale).
    """
    missing: list[str] = []
    mismatched: list[str] = []

    for skill_dir in _skill_dirs(_SKILLS_SOURCE):
        name = skill_dir.name
        target_dir = _SKILLS_TARGET / name
        for rel in sorted(_support_relpaths(skill_dir)):
            source_file = skill_dir / rel
            target_file = target_dir / rel
            label = f"{name}/{rel.as_posix()}"
            if not target_file.is_file():
                missing.append(label)
                continue
            if source_file.read_bytes() != target_file.read_bytes():
                mismatched.append(label)

    assert not missing, "support files missing from src/claude/skills/:\n" + "\n".join(missing)
    assert not mismatched, (
        "support files diverged from .claude/skills/ (run "
        "`uv run python build/scripts/generate_skills.py`):\n" + "\n".join(mismatched)
    )


def test_no_extra_support_files_in_the_claude_plugin_tree() -> None:
    """Every non-SKILL.md file under src/claude/skills/<name>/ has a source
    counterpart under .claude/skills/<name>/; a stale mirror left behind by
    a deleted source file is exactly what
    ``generate_skills._prune_stale_support_files`` exists to catch.
    """
    extra: list[str] = []

    for skill_dir in _skill_dirs(_SKILLS_SOURCE):
        name = skill_dir.name
        target_dir = _SKILLS_TARGET / name
        if not target_dir.is_dir():
            continue
        wanted = _support_relpaths(skill_dir)
        for rel in sorted(_support_relpaths(target_dir)):
            if rel not in wanted:
                extra.append(f"{name}/{rel.as_posix()}")

    assert not extra, "stale support files under src/claude/skills/ with no source:\n" + "\n".join(
        extra
    )


def test_merge_resolver_ships_in_the_claude_plugin_tree() -> None:
    """merge-resolver is excluded from the Copilot mirror (issue #2026,
    templates/platforms/copilot-cli.yaml's excludeFilenames) but MUST ship
    in the Claude plugin: this repo's own toolkit depends on it.
    """
    source_dir = _SKILLS_SOURCE / "merge-resolver"
    target_dir = _SKILLS_TARGET / "merge-resolver"

    assert source_dir.is_dir(), "fixture assumption broken: .claude/skills/merge-resolver/ is gone"
    assert (target_dir / "SKILL.md").is_file()
    for rel in sorted(_support_relpaths(source_dir)):
        assert (target_dir / rel).is_file(), f"missing merge-resolver/{rel.as_posix()}"
