"""Shared builders for the skill collision tests (issue #5763)."""

from __future__ import annotations

import json
from pathlib import Path

SHARED_PREFIX = "Use this skill whenever the user asks for help with the payment ledger. "
ALPHA_TEXT = "Parse YAML configuration files and report schema errors."
BRAVO_NEAR_TEXT = "Render a dashboard of weekly build durations as charts today."


def write_skill(root: Path, directory: str, description: str, name: str | None = None) -> Path:
    skill_dir = root / directory
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_name = directory if name is None else name
    skill_md.write_text(
        f"---\nname: {json.dumps(skill_name)}\n"
        f"description: {json.dumps(description)}\n---\n\n# Body\n",
        encoding="utf-8",
    )
    return skill_md


def make_catalog(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    write_skill(root, "alpha", ALPHA_TEXT)
    write_skill(root, "bravo", "Render a dashboard of weekly build durations as charts.")
    write_skill(root, "charlie", "Rotate expired API credentials in the secrets manager.")
    return root
