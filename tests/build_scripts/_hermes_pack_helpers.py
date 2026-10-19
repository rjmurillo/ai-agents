"""Shared fixtures for the Hermes pack tests (ADR-115 Decision 6).

``make_repo`` builds a tiny repository with four skills and a minimal lib source.
``make_stanza`` and ``make_config`` build a valid ``hermes-packs`` stanza that
matches those skills, and tests override single keys to break one rule at a time.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "build" / "scripts"))

import hermes_pack_config as cfg  # noqa: E402

EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)
HERMES_YAML = _REPO_ROOT / "templates" / "platforms" / "hermes.yaml"

COMMIT = "63d0b94120027d487c9a5235b9ec64b696af1b26"


def make_stanza(**overrides: object) -> dict[str, object]:
    stanza: dict[str, object] = {
        "mode": "hermes-packs",
        "sourceDir": "src/claude/skills",
        "outputDir": "src/hermes",
        "packMaxFiles": 380,
        "hermesCommit": COMMIT,
        "frontmatterDrop": ["metadata"],
        "packs": {
            "one": {"description": "First pack.", "skills": ["alpha", "beta"]},
            "two": {"description": "Second pack.", "skills": ["gamma"]},
        },
        "excluded": {"delta": "plugin_guard returns dangerous."},
    }
    stanza.update(overrides)
    return stanza


def make_config(**overrides: object) -> cfg.HermesConfig:
    return cfg.parse_stanza(make_stanza(**overrides))


def write_skill(root: Path, name: str, extra: dict[str, str] | None = None) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(f"---\nname: {name}\n---\nBody\n", encoding="utf-8")
    for rel, text in (extra or {}).items():
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


NESTED_FRONTMATTER = (
    "---\nname: alpha\ndescription: d\nmodel: haiku\nmetadata:\n  domains:\n    - x\n---\nBody\n"
)


def make_repo(tmp_path: Path) -> Path:
    """A repository with skills alpha, beta, gamma, delta and a minimal lib source."""
    skills = tmp_path / "src" / "claude" / "skills"
    write_skill(skills, "alpha", {"scripts/run.py": "print('a')\n", "references/r.md": "r\n"})
    (skills / "alpha" / "SKILL.md").write_text(NESTED_FRONTMATTER, encoding="utf-8")
    write_skill(skills, "beta")
    write_skill(skills, "gamma")
    write_skill(skills, "delta")
    pkg = tmp_path / "scripts" / "hook_utilities"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        "from scripts.hook_utilities.util import x\n", encoding="utf-8"
    )
    (pkg / "util.py").write_text("x = 1\n", encoding="utf-8")
    (pkg / "bootstrap.py").write_text("B = 1\n", encoding="utf-8")
    # lib_render.PLUGIN_LIB_FILES: hand-maintained in the Claude plugin lib (ADR-119).
    (tmp_path / "src" / "claude" / "lib").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "claude" / "lib" / "paths.py").write_text("P = 1\n", encoding="utf-8")
    for name in ("github_core", "ai_review_common"):
        (tmp_path / "scripts" / name).mkdir()
        (tmp_path / "scripts" / name / "__init__.py").write_text("", encoding="utf-8")
    return tmp_path


def write_config(repo: Path, stanza: dict[str, object]) -> Path:
    path = repo / "hermes.yaml"
    path.write_text(
        yaml.safe_dump(
            {"schemaVersion": "1.0", "provider": "hermes", "artifacts": {"skills": stanza}}
        ),
        encoding="utf-8",
    )
    return path
