"""Committed-artifact gate for the root ``package.json`` Pi reads (ADR-115 Decision 5, 11).

Pi installs a package from a repository root. The root ``package.json`` holds
only the ``pi`` key, so a stray field or a missing skill directory would change
what Pi loads or what other npm tooling sees. Pi's skill naming rules are quoted
from Pi 1.2.0 ``docs/skills.md``: names use lowercase letters, numbers, and
hyphens, with no leading, trailing, or consecutive hyphens, at most 64
characters; descriptions at most 1024.

The Pi runtime itself is exercised by ``tests/e2e/test_pi_package_smoke.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_JSON = REPO_ROOT / "package.json"
EXPECTED_SKILLS_ENTRY = ["./src/claude/skills"]
EXPECTED_KEYS = {"name", "private", "keywords", "pi"}

NAME_MAX = 64
DESCRIPTION_MAX = 1024
_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def load_manifest(path: Path = PACKAGE_JSON) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_problems(manifest: dict[str, Any], root: Path) -> list[str]:
    """Return one message per way ``manifest`` departs from the Pi package shape."""
    problems: list[str] = []
    if set(manifest) != EXPECTED_KEYS:
        problems.append(f"keys {sorted(manifest)} differ from {sorted(EXPECTED_KEYS)}")
    if manifest.get("private") is not True:
        problems.append("private must be true")
    if manifest.get("keywords") != ["pi-package"]:
        problems.append("keywords must be exactly ['pi-package']")
    pi = manifest.get("pi")
    if not isinstance(pi, dict) or set(pi) != {"skills"}:
        problems.append("pi must hold only the skills key")
        return problems
    if pi["skills"] != EXPECTED_SKILLS_ENTRY:
        problems.append(f"pi.skills must be {EXPECTED_SKILLS_ENTRY}, got {pi['skills']!r}")
        return problems
    for entry in pi["skills"]:
        if not (root / entry).is_dir():
            problems.append(f"pi.skills path {entry} is not a directory")
    return problems


def frontmatter(skill_md: Path) -> dict[str, Any]:
    match = _FRONTMATTER_RE.match(skill_md.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"{skill_md}: no YAML frontmatter")
    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise ValueError(f"{skill_md}: frontmatter is not a mapping")
    return data


def skill_problems(skill_dir: Path) -> list[str]:
    """Return one message per Pi skill-metadata rule that ``skill_dir`` breaks."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{skill_dir.name}: no SKILL.md"]
    try:
        meta = frontmatter(skill_md)
    except (ValueError, yaml.YAMLError) as exc:
        return [f"{skill_dir.name}: {exc}"]
    problems: list[str] = []
    name = meta.get("name")
    if not isinstance(name, str) or len(name) > NAME_MAX or not _NAME_RE.fullmatch(name):
        problems.append(f"{skill_dir.name}: name {name!r} breaks Pi's naming rule")
    description = meta.get("description")
    if not isinstance(description, str) or not description.strip():
        problems.append(f"{skill_dir.name}: description is missing")
    elif len(description) > DESCRIPTION_MAX:
        problems.append(f"{skill_dir.name}: description is {len(description)} chars")
    return problems


def test_root_package_json_has_exactly_the_pi_shape() -> None:
    assert manifest_problems(load_manifest(), REPO_ROOT) == []


def test_every_skill_directory_meets_pis_metadata_rules() -> None:
    skills_root = REPO_ROOT / "src" / "claude" / "skills"
    skill_dirs = sorted(path for path in skills_root.iterdir() if path.is_dir())

    assert skill_dirs, "no skill directories under src/claude/skills"
    problems = [problem for skill_dir in skill_dirs for problem in skill_problems(skill_dir)]
    assert problems == []


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [
        ({"version": "1.0.0"}, "keys"),
        ({"private": False}, "private must be true"),
        ({"keywords": []}, "keywords"),
        ({"keywords": ["pi-package", "extra"]}, "keywords"),
        ({"pi": {"skills": ["./src/claude/skills"], "extensions": []}}, "only the skills key"),
        ({"pi": "skills"}, "only the skills key"),
        ({"pi": {"skills": ["./src/claude/skills", "./missing"]}}, "pi.skills must be"),
        ({"pi": {"skills": ["./src/claude"]}}, "pi.skills must be"),
    ],
)
def test_manifest_problems_flags_a_departure_from_the_shape(
    mutation: dict[str, Any], fragment: str
) -> None:
    manifest = {**load_manifest(), **mutation}

    assert any(fragment in problem for problem in manifest_problems(manifest, REPO_ROOT))


def test_manifest_problems_flags_a_missing_skills_directory(tmp_path: Path) -> None:
    problems = manifest_problems(load_manifest(), tmp_path)

    assert problems == ["pi.skills path ./src/claude/skills is not a directory"]


def _write_skill(tmp_path: Path, directory: str, text: str) -> Path:
    skill_dir = tmp_path / directory
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    return skill_dir


def test_skill_problems_accepts_a_valid_skill(tmp_path: Path) -> None:
    skill = _write_skill(
        tmp_path, "good", "---\nname: good-skill-2\ndescription: Does a thing.\n---\nbody\n"
    )

    assert skill_problems(skill) == []


@pytest.mark.parametrize(
    "name",
    ["Upper", "-lead", "trail-", "dou--ble", "under_score", "sp ace", "a" * 65, "", "1" * 65],
)
def test_skill_problems_rejects_a_name_that_breaks_pis_rule(tmp_path: Path, name: str) -> None:
    skill = _write_skill(tmp_path, "bad", f'---\nname: "{name}"\ndescription: ok\n---\n')

    assert any("naming rule" in problem for problem in skill_problems(skill))


def test_skill_problems_accepts_a_64_character_name(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path, "edge", f"---\nname: {'a' * 64}\ndescription: ok\n---\n")

    assert skill_problems(skill) == []


@pytest.mark.parametrize(
    "front", ["name: ok\n", "name: ok\ndescription: ''\n", "name: ok\ndescription: '  '\n"]
)
def test_skill_problems_requires_a_description(tmp_path: Path, front: str) -> None:
    skill = _write_skill(tmp_path, "nodesc", f"---\n{front}---\n")

    assert any("description is missing" in problem for problem in skill_problems(skill))


def test_skill_problems_rejects_a_description_over_1024_characters(tmp_path: Path) -> None:
    long = "x" * (DESCRIPTION_MAX + 1)
    skill = _write_skill(tmp_path, "long", f"---\nname: ok\ndescription: {long}\n---\n")

    assert any("1025 chars" in problem for problem in skill_problems(skill))


def test_skill_problems_accepts_a_1024_character_description(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path, "max", f"---\nname: ok\ndescription: {'x' * 1024}\n---\n")

    assert skill_problems(skill) == []


def test_skill_problems_reports_a_missing_skill_file(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()

    assert skill_problems(tmp_path / "empty") == ["empty: no SKILL.md"]


@pytest.mark.parametrize(
    "text", ["no frontmatter\n", "---\n- a\n- b\n---\n", "---\nname: [\n---\n"]
)
def test_skill_problems_reports_unparseable_frontmatter(tmp_path: Path, text: str) -> None:
    skill = _write_skill(tmp_path, "broken", text)

    assert skill_problems(skill) != []
