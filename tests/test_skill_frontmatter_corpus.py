"""Every SKILL.md in every shipped skill tree passes the frontmatter gate.

CI runs the pytest legs on every PR, so this holds GP-003 (name, description,
top-level SemVer version, license) on the real corpus even when nobody runs
``pre_pr.py``. The temporary-tree tests prove the entry point can fail.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.skill_frontmatter import validate_skill_frontmatter

REPO_ROOT = Path(__file__).resolve().parents[1]
_GOOD = "---\nname: alpha\ndescription: d\nversion: 1.0.0\nlicense: MIT\n---\n"


def _skill(root: Path, prefix: str, body: str) -> None:
    target = root / prefix / "alpha" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text(body, encoding="utf-8")


def test_real_corpus_passes(capsys: pytest.CaptureFixture[str]) -> None:
    ok = validate_skill_frontmatter(REPO_ROOT)

    assert ok, capsys.readouterr().out


def test_a_good_tree_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _skill(tmp_path, ".claude/skills", _GOOD)

    assert validate_skill_frontmatter(tmp_path) is True
    assert "1 of 1 SKILL.md passed" in capsys.readouterr().out


def test_a_copy_missing_version_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _skill(tmp_path, ".claude/skills", _GOOD)
    _skill(tmp_path, "src/hermes/pack/skills", _GOOD.replace("version: 1.0.0\n", ""))

    assert validate_skill_frontmatter(tmp_path) is False
    out = capsys.readouterr().out
    assert "[FAIL] src/hermes/pack/skills/alpha/SKILL.md" in out
    assert "Missing required field: version" in out
    assert "1 of 2 SKILL.md passed" in out


def test_no_skill_files_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert validate_skill_frontmatter(tmp_path) is False
    assert "No SKILL.md found" in capsys.readouterr().out
