"""Tests for scripts/validation/skill_corpus.py (issue #7658)."""

from __future__ import annotations

from pathlib import Path

from scripts.validation.skill_corpus import corpus_files, corpus_summary


def _skill(root: Path, rel: str) -> Path:
    path = root / rel / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nname: x\n---\n", encoding="utf-8")
    return path


def test_corpus_files_collects_every_tree_sorted(tmp_path: Path) -> None:
    b = _skill(tmp_path, "src/skills/b")
    a = _skill(tmp_path, ".claude/skills/a")
    nested = _skill(tmp_path, "src/skills/b/inner")
    (tmp_path / "src/skills/b/README.md").write_text("x", encoding="utf-8")
    assert corpus_files(tmp_path, ["src/skills", ".claude/skills"]) == sorted([a, b, nested])


def test_corpus_files_skips_absent_tree(tmp_path: Path) -> None:
    a = _skill(tmp_path, ".claude/skills/a")
    assert corpus_files(tmp_path, [".claude/skills", "missing/skills"]) == [a]


def test_corpus_files_empty_when_nothing_present(tmp_path: Path) -> None:
    assert corpus_files(tmp_path, ["missing"]) == []
    assert corpus_files(tmp_path, []) == []


def test_corpus_files_ignores_a_file_named_like_a_tree(tmp_path: Path) -> None:
    (tmp_path / "skills").write_text("not a dir", encoding="utf-8")
    assert corpus_files(tmp_path, ["skills"]) == []


def test_summary_names_present_and_absent_trees(tmp_path: Path) -> None:
    _skill(tmp_path, ".claude/skills/a")
    line = corpus_summary(tmp_path, [".claude/skills", "src/skills"])
    assert line == "Scanning skill trees: .claude/skills; absent, not scanned: src/skills"


def test_summary_all_present_has_no_absent_clause(tmp_path: Path) -> None:
    _skill(tmp_path, "one/a")
    _skill(tmp_path, "two/b")
    assert corpus_summary(tmp_path, ["one", "two"]) == "Scanning skill trees: one, two"


def test_summary_none_present(tmp_path: Path) -> None:
    line = corpus_summary(tmp_path, ["one"])
    assert line == "Scanning skill trees: (none present); absent, not scanned: one"
