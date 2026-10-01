"""Guards for the skill-tree layout gate (issue #5503).

A loose Markdown file directly under ``.claude/skills/`` registers with the
Claude Code plugin loader as a selectable skill. ``.claude/skills/CLAUDE.md``
did, as a skill named ``CLAUDE``.

Coverage:

- positive: a tree of skill directories passes, and the real tree passes.
- negative: a loose ``CLAUDE.md``, a loose non-Markdown file, and a directory
  without ``SKILL.md`` each fail.
- edge: a missing or empty tree is a config error, not a pass. The gate carries
  no allowlist. A nested ``CLAUDE.md`` inside a skill directory is not scanned.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_skill_tree_layout as gate


def _tree(tmp_path: Path) -> Path:
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    return tmp_path


def _skill(repo: Path, name: str) -> Path:
    path = repo / ".claude" / "skills" / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    return path


def test_tree_of_skill_directories_passes(tmp_path):
    repo = _tree(tmp_path)
    _skill(repo, "alpha")
    _skill(repo, "beta")

    assert gate.find_non_skill_entries(repo) == []
    assert gate.validate_skill_tree_layout(repo) is True
    assert gate.main([str(repo)]) == 0


def test_real_repository_tree_passes():
    assert gate.find_non_skill_entries(REPO_ROOT) == []


def test_loose_claude_md_fails(tmp_path, capsys):
    repo = _tree(tmp_path)
    _skill(repo, "alpha")
    (repo / ".claude" / "skills" / "CLAUDE.md").write_text("# Conventions\n", encoding="utf-8")

    assert gate.validate_skill_tree_layout(repo) is False
    err = capsys.readouterr().err
    assert ".claude/skills/CLAUDE.md" in err
    assert "#5503" in err
    assert gate.main([str(repo)]) == 1


def test_loose_non_markdown_file_fails(tmp_path):
    repo = _tree(tmp_path)
    _skill(repo, "alpha")
    (repo / ".claude" / "skills" / "notes.txt").write_text("x", encoding="utf-8")

    findings = gate.find_non_skill_entries(repo)

    assert [rel.as_posix() for rel, _ in findings] == [".claude/skills/notes.txt"]


def test_directory_without_manifest_fails(tmp_path):
    repo = _tree(tmp_path)
    _skill(repo, "alpha")
    (repo / ".claude" / "skills" / "empty").mkdir()

    findings = gate.find_non_skill_entries(repo)

    assert [(rel.as_posix(), reason) for rel, reason in findings] == [
        (".claude/skills/empty", "directory without SKILL.md")
    ]


def test_nested_claude_md_inside_skill_is_not_scanned(tmp_path):
    repo = _tree(tmp_path)
    skill = _skill(repo, "alpha")
    (skill / "CLAUDE.md").write_text("# Skill notes\n", encoding="utf-8")

    assert gate.find_non_skill_entries(repo) == []


def test_missing_tree_is_config_error(tmp_path, capsys):
    assert gate.validate_skill_tree_layout(tmp_path) is False
    assert "skill tree not found" in capsys.readouterr().err
    assert gate.main([str(tmp_path)]) == 2


def test_empty_tree_fails_instead_of_passing(tmp_path, capsys):
    repo = _tree(tmp_path)

    assert gate.validate_skill_tree_layout(repo) is False
    assert "skill tree is empty" in capsys.readouterr().err
    assert gate.main([str(repo)]) == 2


def test_invalid_root_is_config_error(tmp_path):
    assert gate.main([str(tmp_path / "does-not-exist")]) == 2


def test_gate_has_no_allowlist():
    source = (_VALIDATION_DIR / "check_skill_tree_layout.py").read_text(encoding="utf-8")
    for token in ("ALLOW", "EXEMPT", "_SKIP_FILES", "frozenset("):
        assert token not in source, f"gate grew an exemption mechanism: {token}"
