"""Shared helpers for the lint_skill_frontmatter.py tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.skills.skillforge.conformance_support import load

_REPO_ROOT = Path(__file__).resolve().parents[3]
lint = load("skillforge_frontmatter_lint_under_test", "lint_skill_frontmatter.py")

_DESCRIPTION = "Demo skill. Do NOT use for other work (use other-skill)."
_SKILLS_TREE = _REPO_ROOT / "src" / "claude" / "skills"

RULE_IDS = (
    "fm.subset-parse",
    "fm.size.bytes",
    "fm.size.headroom",
    "fm.artifacts.shape",
    "fm.capability.shape",
    "fm.routing.intents-role",
    "fm.routing.phrases-routable",
    "fm.handoff.shape",
    "fm.description.redirect",
)


def _skill_text(
    metadata: str = "",
    body: str = "Body.\n",
    description: str = _DESCRIPTION,
    top_level: str = "",
) -> str:
    meta_block = f"metadata:\n{metadata}" if metadata else ""
    return f"---\nname: demo\ndescription: {description}\n{top_level}{meta_block}---\n\n{body}"


def _write_skill(tmp_path: Path, text: str) -> Path:
    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    return skill_dir


def _lint(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    text: str,
    *flags: str,
) -> tuple[int, dict[str, dict[str, object]]]:
    skill_dir = _write_skill(tmp_path, text)
    code = lint.main([str(skill_dir), "--root", str(tmp_path), "--format", "json", *flags])
    payload = json.loads(capsys.readouterr().out)
    assert payload["exit_code"] == code
    (skill,) = payload["skills"]
    return code, {row["id"]: row for row in skill["results"]}


def _messages(row: dict[str, object]) -> str:
    messages = row["messages"]
    assert isinstance(messages, list)
    return " ".join(messages)
