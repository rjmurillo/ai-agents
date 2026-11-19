"""Each guarded-import allowance's fallback holds with its module blocked (ADR-121 decision 13).

`GUARDED_IMPORT_ALLOWANCES` lets rule 2 pass a target that reaches a third-party
module, because the import is guarded. The validator checks that the guard
exists. These tests check what the guard does: each listed target runs with its
module blocked (`sys.modules[name] = None`, so `import name` raises ImportError)
under `python -I`, as a consumer's bare interpreter would, and must give the
fallback the entry names.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation import plugin_root_guarded_imports as guarded

REPO_ROOT = Path(__file__).resolve().parents[2]

# Runs a script as `__main__` with one module blocked, from the script's own folder
# on sys.path, the way `python3 <script>` would put it there.
BLOCKING_RUNNER = """\
import os, runpy, sys
module, target = sys.argv[1], sys.argv[2]
sys.modules[module] = None
sys.argv = [target, *sys.argv[3:]]
sys.path.insert(0, os.path.dirname(target))
runpy.run_path(target, run_name="__main__")
"""

SKILL_MD = "---\nname: my-skill\ndescription: Demo skill. Use when testing.\n---\n\n# My Skill\n"


def _run_blocked(
    target: str, module: str, *args: str, cwd: Path, home: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, "-I", "-c", BLOCKING_RUNNER, module, str(REPO_ROOT / target), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


def _skill(root: Path, frontmatter_extra: str = "") -> Path:
    skill = root / "skills" / "my-skill"
    skill.mkdir(parents=True)
    text = SKILL_MD.replace("---\n\n", f"{frontmatter_extra}---\n\n", 1)
    (skill / "SKILL.md").write_text(text, encoding="utf-8")
    return skill


def test_every_committed_entry_has_a_fallback_test() -> None:
    covered = {
        (".claude/skills/autoplan/scripts/resolve_route.py", "yaml"),
        (".claude/skills/memory/scripts/count_memory_tokens.py", "tiktoken"),
        (".claude/skills/skillforge/scripts/quick_validate.py", "yaml"),
        (".claude/skills/skillforge/scripts/package_skill.py", "yaml"),
    }
    assert set(guarded.GUARDED_IMPORT_ALLOWANCES) == covered


def test_resolve_route_without_yaml_exits_2_and_names_pyyaml(tmp_path: Path) -> None:
    result = _run_blocked(
        ".claude/skills/autoplan/scripts/resolve_route.py",
        "yaml",
        "--request",
        "audit our CLI",
        cwd=tmp_path,
    )
    assert result.returncode == 2, result.stderr
    assert "PyYAML" in result.stderr
    assert result.stdout == ""


def test_count_memory_tokens_without_tiktoken_exits_1_and_names_it(tmp_path: Path) -> None:
    (tmp_path / "memory.md").write_text("# A memory\n\nSome text.\n", encoding="utf-8")
    result = _run_blocked(
        ".claude/skills/memory/scripts/count_memory_tokens.py",
        "tiktoken",
        "memory.md",
        cwd=tmp_path,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "tiktoken" in result.stderr


def test_quick_validate_without_yaml_still_passes_a_valid_skill(tmp_path: Path) -> None:
    _skill(tmp_path)
    result = _run_blocked(
        ".claude/skills/skillforge/scripts/quick_validate.py",
        "yaml",
        "skills/my-skill/",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "valid" in result.stdout


def test_quick_validate_without_yaml_still_rejects_a_bad_frontmatter_key(tmp_path: Path) -> None:
    """Negative control: the stdlib reader parses, so a bad key is still caught."""
    _skill(tmp_path, frontmatter_extra="not-a-field: x\n")
    result = _run_blocked(
        ".claude/skills/skillforge/scripts/quick_validate.py",
        "yaml",
        "skills/my-skill/",
        cwd=tmp_path,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "not-a-field" in result.stdout + result.stderr


@pytest.mark.skipif(os.name != "posix", reason="HOME override")
def test_package_skill_without_yaml_still_packages(tmp_path: Path) -> None:
    home = tmp_path / "home"
    skill = _skill(home / ".claude")
    out = tmp_path / "dist"
    result = _run_blocked(
        ".claude/skills/skillforge/scripts/package_skill.py",
        "yaml",
        str(skill),
        str(out),
        cwd=tmp_path,
        home=home,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (out / "my-skill.skill").is_file()


def test_blocking_an_unrelated_module_leaves_resolve_route_working(tmp_path: Path) -> None:
    """Control: the fallback above comes from blocking yaml, not from the runner."""
    result = _run_blocked(
        ".claude/skills/autoplan/scripts/resolve_route.py",
        "no_such_module_7281",
        "--request",
        "audit our CLI",
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "PyYAML" not in result.stderr
