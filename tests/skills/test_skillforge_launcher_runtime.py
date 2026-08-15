"""Runtime-contract tests for SkillForge launcher examples."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_MD = REPO_ROOT / ".claude" / "skills" / "skillforge" / "SKILL.md"


def _launcher_block() -> str:
    text = SKILL_MD.read_text(encoding="utf-8")
    match = re.search(
        r"```bash\n(# Validators enforce a path-traversal guard:.*?package_skill\.py.*?\n)```",
        text,
        re.DOTALL,
    )
    assert match, "SkillForge validation launcher block not found"
    return match.group(1)


def _seed_skill(home: Path) -> None:
    skill = home / ".claude" / "skills" / "my-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        """---
name: my-skill
description: Validate JSON schemas for test fixtures. Use when checking fixture schemas.
license: MIT
---

# My Skill

## Triggers

| Phrase | Action |
|---|---|
| `validate fixtures` | Validate schemas |

## Process

1. Read the fixture.
2. Validate its schema.

## Verification

- [ ] The fixture matches its schema.
- [ ] Invalid fixtures return a failure.

## Anti-Patterns

Do not skip invalid fixtures.

## Extension Points

Add validators for new schema formats.
""",
        encoding="utf-8",
    )



def _run_launcher(cwd: Path, home: Path, **roots: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("COPILOT_PLUGIN_ROOT", None)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env.update(roots)
    return subprocess.run(
        ["bash", "-eu", "-o", "pipefail", "-c", _launcher_block()],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_launcher_uses_copilot_plugin_root_from_host_worktree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    host = tmp_path / "host"
    host.mkdir()
    _seed_skill(home)

    result = _run_launcher(
        host,
        home,
        COPILOT_PLUGIN_ROOT=str(REPO_ROOT / "src" / "copilot-cli"),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (home / ".claude" / "skills" / "dist" / "my-skill.skill").is_file()


def test_launcher_uses_project_local_fallback_when_roots_unset(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_skill(home)

    result = _run_launcher(REPO_ROOT, home)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (home / ".claude" / "skills" / "dist" / "my-skill.skill").is_file()


def test_launcher_rejects_missing_plugin_root(tmp_path: Path) -> None:
    home = tmp_path / "home"
    host = tmp_path / "host"
    host.mkdir()
    _seed_skill(home)

    result = _run_launcher(
        host,
        home,
        COPILOT_PLUGIN_ROOT=str(tmp_path / "missing-plugin"),
    )

    assert result.returncode != 0
    assert "missing-plugin" in result.stderr
