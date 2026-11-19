"""Shared fixtures for the skill mirror orphan-prune tests (not a test module)."""

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

SKILL_MD = "---\nname: {name}\ndescription: fixture\n---\n# {name}\n"
# The four mirror shapes in templates/platforms: copilot-cli translates
# SKILL.md, codex drops frontmatter keys, cursor and muse keep an allow-list.
SHAPES = {
    "copilot-cli": "provider: copilot-cli\n",
    "codex": "provider: codex\n    frontmatterDrop: [model, model-rationale]\n",
    "cursor": "provider: cursor\n    frontmatterKeep: [name, description]\n",
    "muse": "provider: muse\n    frontmatterKeep: [name, description]\n",
}


def config(repo: Path, shape: str = "copilot-cli") -> Path:
    provider, _, extra = SHAPES[shape].partition("\n    ")
    config = repo / "platform.yaml"
    config.write_text(
        'schemaVersion: "1.0"\n'
        f"{provider}\n"
        "artifacts:\n"
        "  skills:\n"
        "    mode: directory-copy\n"
        "    sourceDir: src/claude/skills\n"
        "    outputDir: out/skills\n" + (f"    {extra}" if extra else ""),
        encoding="utf-8",
    )
    return config


def seed(repo: Path, name: str = "alpha") -> Path:
    """Seed ``src/claude/skills/<name>`` with a SKILL.md and two reference files."""
    source = repo / "src" / "claude" / "skills" / name
    (source / "references").mkdir(parents=True)
    (source / "scripts").mkdir()
    (source / "SKILL.md").write_text(SKILL_MD.format(name=name), encoding="utf-8")
    (source / "references" / "keep.md").write_text("keep\n", encoding="utf-8")
    (source / "references" / "old.md").write_text("old\n", encoding="utf-8")
    (source / "scripts" / "run.py").write_text("print('run')\n", encoding="utf-8")
    return source


def mirror(repo: Path, name: str = "alpha") -> Path:
    return repo / "out" / "skills" / name


def build(repo: Path, shape: str = "copilot-cli", *, check: bool = False) -> int:
    return generate_skills.generate_skills(config(repo, shape), repo, validate=check)


def built_repo(repo: Path, shape: str = "copilot-cli", name: str = "alpha") -> Path:
    """Seed a skill, run one clean build, and return the source directory."""
    source = seed(repo, name)
    assert build(repo, shape) == 0
    assert (mirror(repo, name) / "references" / "old.md").is_file()
    return source


def make_symlink(link: Path, target: Path, *, directory: bool = False) -> None:
    """Create ``link`` pointing at ``target``; skip the test when symlinks are unavailable."""
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError:
        pytest.skip("symlinks unavailable")
