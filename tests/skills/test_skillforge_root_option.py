"""Tests for the opt-in --root option on the SkillForge validators (issue #6655).

quick_validate.py and validate-skill.py confine the target skill to the current
working directory (CWE-22). Validating a skill in another checkout needed a cd
or a copy. ``--root DIR`` moves the trusted root for one call. The default stays
the current directory, and every containment check still runs against the root.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FORGE = Path("skills") / "skillforge" / "scripts"
_SCRIPT_NAMES = ("quick_validate.py", "validate-skill.py")
_TREES = (".claude", "src/copilot-cli")
_SCRIPTS = [_REPO_ROOT / tree / _FORGE / name for tree in _TREES for name in _SCRIPT_NAMES]

_TRAVERSAL_MARKER = "Path traversal detected"
_SKILL_MD = """---
name: sample
description: Sample skill for the root option. Use when you say `run sample`.
license: MIT
---

# Sample

## Triggers

| Phrase | Action |
|--------|--------|
| `run sample` | Run the sample |

## Process

1. Phase 1: read the input.
2. Phase 2: write the output.

## Verification

- [ ] Output exists
- [ ] Output is valid

## Anti-Patterns

| Avoid | Why |
|-------|-----|
| Skipping input | Output is empty |

## Extension Points

- Add a phase.
"""


def _script_id(script: Path) -> str:
    return f"{script.parts[-5]}-{script.name}"


def _make_skill(dir_path: Path) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")


def _run(script: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


@pytest.fixture
def layout(tmp_path: Path) -> dict[str, Path]:
    """A work dir (the cwd) and a separate repo that holds the skill."""
    work = tmp_path / "work"
    work.mkdir()
    repo = tmp_path / "other-repo"
    skill = repo / "skills" / "sample"
    _make_skill(skill)
    return {"work": work, "repo": repo, "skill": skill}


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_absolute_path_inside_root_passes(script: Path, layout: dict[str, Path]) -> None:
    result = _run(script, layout["work"], str(layout["skill"]), "--root", str(layout["repo"]))
    combined = result.stdout + result.stderr
    assert _TRAVERSAL_MARKER not in combined, combined
    assert "Traceback" not in combined, combined
    assert result.returncode == 0, combined


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_root_equals_form_is_accepted(script: Path, layout: dict[str, Path]) -> None:
    result = _run(script, layout["work"], str(layout["skill"]), f"--root={layout['repo']}")
    combined = result.stdout + result.stderr
    assert _TRAVERSAL_MARKER not in combined, combined
    assert result.returncode == 0, combined


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_root_before_path_is_accepted(script: Path, layout: dict[str, Path]) -> None:
    result = _run(script, layout["work"], "--root", str(layout["repo"]), str(layout["skill"]))
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_path_outside_root_is_rejected(script: Path, layout: dict[str, Path]) -> None:
    # The skill sits in other-repo, the root is work: the guard still fires.
    result = _run(script, layout["work"], str(layout["skill"]), "--root", str(layout["work"]))
    combined = result.stdout + result.stderr
    assert _TRAVERSAL_MARKER in combined, combined
    assert result.returncode == 1


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_dotdot_escape_from_root_is_rejected(script: Path, layout: dict[str, Path]) -> None:
    escape = str(layout["repo"] / "skills" / ".." / ".." / "work")
    result = _run(script, layout["work"], escape, "--root", str(layout["repo"]))
    combined = result.stdout + result.stderr
    assert _TRAVERSAL_MARKER in combined, combined
    assert result.returncode == 1


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_sibling_prefix_directory_is_rejected(script: Path, tmp_path: Path) -> None:
    # /x/repo-evil shares the string prefix of /x/repo but is not inside it.
    repo = tmp_path / "repo"
    repo.mkdir()
    evil = tmp_path / "repo-evil" / "sample"
    _make_skill(evil)
    result = _run(script, tmp_path, str(evil), "--root", str(repo))
    combined = result.stdout + result.stderr
    assert _TRAVERSAL_MARKER in combined, combined
    assert result.returncode == 1


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_no_root_keeps_absolute_path_rejection(script: Path, layout: dict[str, Path]) -> None:
    # Default behavior is unchanged: without --root the cwd is the root.
    result = _run(script, layout["work"], str(layout["skill"]))
    combined = result.stdout + result.stderr
    assert _TRAVERSAL_MARKER in combined, combined
    assert result.returncode == 1


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_missing_root_directory_exits_nonzero(script: Path, layout: dict[str, Path]) -> None:
    missing = layout["work"] / "does-not-exist"
    result = _run(script, layout["work"], str(layout["skill"]), "--root", str(missing))
    combined = result.stdout + result.stderr
    assert "--root is not a directory" in combined, combined
    assert "Traceback" not in combined, combined
    assert result.returncode == 1


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_root_that_is_a_file_exits_nonzero(script: Path, layout: dict[str, Path]) -> None:
    not_a_dir = layout["work"] / "file.txt"
    not_a_dir.write_text("x", encoding="utf-8")
    result = _run(script, layout["work"], str(layout["skill"]), "--root", str(not_a_dir))
    assert "--root is not a directory" in result.stdout + result.stderr
    assert result.returncode == 1


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
@pytest.mark.parametrize(
    "bad_args",
    [
        ["--root"],
        ["--root="],
        ["--bogus", "skills/sample"],
        [],
    ],
    ids=["root-without-value", "empty-root", "unknown-flag", "no-args"],
)
def test_usage_errors_exit_one_with_usage(
    script: Path, tmp_path: Path, bad_args: list[str]
) -> None:
    result = _run(script, tmp_path, *bad_args)
    combined = result.stdout + result.stderr
    assert "Usage:" in combined, combined
    assert result.returncode == 1


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_duplicate_root_and_extra_positional_exit_one(
    script: Path, layout: dict[str, Path]
) -> None:
    repo = str(layout["repo"])
    dup = _run(script, layout["work"], str(layout["skill"]), "--root", repo, "--root", repo)
    extra = _run(script, layout["work"], str(layout["skill"]), "second", "--root", repo)
    for result in (dup, extra):
        assert "Usage:" in result.stdout + result.stderr
        assert result.returncode == 1


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_symlink_skill_md_escaping_root_is_rejected(script: Path, tmp_path: Path) -> None:
    # CWE-22: under --root, a SKILL.md symlink that points outside the root must
    # not be read.
    root = tmp_path / "root"
    contained = root / "evil"
    contained.mkdir(parents=True)
    secret = tmp_path / "secret.md"
    secret.write_text(_SKILL_MD, encoding="utf-8")
    try:
        (contained / "SKILL.md").symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    result = _run(script, tmp_path, str(contained), "--root", str(root))
    combined = result.stdout + result.stderr
    assert "Skill is valid" not in combined, combined
    assert "All checks passed" not in combined, combined
    assert result.returncode == 1, combined
