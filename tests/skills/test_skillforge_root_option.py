"""Tests for the opt-in --root option on the SkillForge validators (issue #6655).

quick_validate.py and validate-skill.py confine the target skill to the current
working directory (CWE-22). Validating a skill in another checkout needed a cd
or a copy. ``--root DIR`` moves the trusted root for one call. The default stays
the current directory, and every containment check still runs against the root.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FORGE = Path("skills") / "skillforge" / "scripts"
_SCRIPT_NAMES = ("quick_validate.py", "validate-skill.py")
# One entry per real copy. ``.claude/skills/*`` is a symlink into ``src/claude``
# since ADR-119, so listing it would run the same files twice.
_TREES = (
    "src/claude",
    "src/codex",
    "src/copilot-cli",
    "src/cursor",
    "src/hermes/project-toolkit-knowledge",
)
_SCRIPTS = [_REPO_ROOT / tree / _FORGE / name for tree in _TREES for name in _SCRIPT_NAMES]

_TRAVERSAL_MARKER = "Path traversal detected"
_OUTSIDE_ROOT_MARKER = "outside the permitted root"
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


def test_trees_cover_every_real_skillforge_copy() -> None:
    """Every on-disk skillforge validator copy under src/ is exercised here."""
    found = {
        path.relative_to(_REPO_ROOT).as_posix()
        for path in (_REPO_ROOT / "src").glob("**/skills/skillforge/scripts/quick_validate.py")
    }
    covered = {
        (_REPO_ROOT / tree / _FORGE / "quick_validate.py").relative_to(_REPO_ROOT).as_posix()
        for tree in _TREES
    }
    assert found, "no skillforge copies found under src/"
    assert found == covered, (
        f"untested: {sorted(found - covered)}; stale: {sorted(covered - found)}"
    )


def test_trees_do_not_repeat_a_symlinked_copy() -> None:
    """No tree resolves to the same files as another tree (the ADR-119 symlink trap)."""
    resolved = [(_REPO_ROOT / tree / _FORGE).resolve() for tree in _TREES]
    assert len(set(resolved)) == len(resolved), [str(p) for p in resolved]
    assert all(not (_REPO_ROOT / tree).is_symlink() for tree in _TREES)


def _script_id(script: Path) -> str:
    return f"{script.parts[-5]}-{script.name}"


def _make_skill(dir_path: Path) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")


def _make_skill_with_scripts(dir_path: Path) -> None:
    """A skill whose SKILL.md documents ok.py, so a clean scripts/ passes."""
    dir_path.mkdir(parents=True, exist_ok=True)
    scripts_doc = (
        "\n## Scripts\n\n| Script | Purpose |\n|--------|---------|\n"
        "| `ok.py` | Sample script. Exit code 0 on success. |\n"
    )
    (dir_path / "SKILL.md").write_text(_SKILL_MD + scripts_doc, encoding="utf-8")


_OK_SCRIPT = (
    '#!/usr/bin/env python3\n"""Inside."""\nimport sys\n\n'
    "class Result:\n    pass\n\n"
    "try:\n    sys.exit(0)\nexcept SystemExit:\n    raise\n"
)


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
        ["-h"],
        ["-x", "skills/sample"],
        [],
    ],
    ids=[
        "root-without-value",
        "empty-root",
        "unknown-flag",
        "single-dash-help",
        "single-dash-flag",
        "no-args",
    ],
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
    # not be read. The directory is named "sample" to match the frontmatter, so
    # the symlink is the only thing that can fail validation.
    root = tmp_path / "root"
    contained = root / "sample"
    contained.mkdir(parents=True)
    secret = tmp_path / "secret.md"
    secret.write_text(_SKILL_MD, encoding="utf-8")
    try:
        (contained / "SKILL.md").symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    result = _run(script, tmp_path, str(contained), "--root", str(root))
    combined = result.stdout + result.stderr
    assert _OUTSIDE_ROOT_MARKER in combined, combined
    assert "Skill is valid" not in combined, combined
    assert "All checks passed" not in combined, combined
    assert result.returncode == 1, combined


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_symlink_skill_md_inside_root_is_accepted(script: Path, tmp_path: Path) -> None:
    # Control for the rejection test above: the same layout with the symlink
    # target inside the root passes, so the rejection is about containment.
    root = tmp_path / "root"
    contained = root / "sample"
    contained.mkdir(parents=True)
    target = root / "shared.md"
    target.write_text(_SKILL_MD, encoding="utf-8")
    try:
        (contained / "SKILL.md").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    result = _run(script, tmp_path, str(contained), "--root", str(root))
    combined = result.stdout + result.stderr
    assert _OUTSIDE_ROOT_MARKER not in combined, combined
    assert result.returncode == 0, combined


@pytest.mark.parametrize("tree", _TREES)
def test_symlink_script_escaping_root_is_rejected(tree: str, tmp_path: Path) -> None:
    # CWE-22: validate-skill.py reads scripts/*.py to lint them. A symlinked
    # script that points outside the root must not be read.
    script = _REPO_ROOT / tree / _FORGE / "validate-skill.py"
    root = tmp_path / "root"
    contained = root / "sample"
    _make_skill(contained)
    (contained / "scripts").mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text('#!/usr/bin/env python3\n"""Outside."""\n', encoding="utf-8")
    try:
        (contained / "scripts" / "evil.py").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    result = _run(script, tmp_path, str(contained), "--root", str(root))
    combined = result.stdout + result.stderr
    assert "Script evil.py resolves outside the permitted root" in combined, combined
    assert result.returncode == 1, combined


@pytest.mark.parametrize("tree", _TREES)
def test_symlink_script_inside_root_is_not_flagged(tree: str, tmp_path: Path) -> None:
    script = _REPO_ROOT / tree / _FORGE / "validate-skill.py"
    root = tmp_path / "root"
    contained = root / "sample"
    _make_skill_with_scripts(contained)
    (contained / "scripts").mkdir()
    inside = root / "shared.py"
    inside.write_text(_OK_SCRIPT, encoding="utf-8")
    try:
        (contained / "scripts" / "ok.py").symlink_to(inside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    result = _run(script, tmp_path, str(contained), "--root", str(root))
    combined = result.stdout + result.stderr
    assert _OUTSIDE_ROOT_MARKER not in combined, combined
    assert "Traceback" not in combined, combined
    assert result.returncode == 0, combined


@pytest.mark.parametrize("tree", _TREES)
def test_symlinked_scripts_dir_escaping_root_is_rejected_once(tree: str, tmp_path: Path) -> None:
    # CWE-22: a scripts/ directory symlink to an outside directory must not be
    # listed. One error names the directory; no outside filename is reported.
    script = _REPO_ROOT / tree / _FORGE / "validate-skill.py"
    root = tmp_path / "root"
    contained = root / "sample"
    _make_skill(contained)
    outside_dir = tmp_path / "outside-scripts"
    outside_dir.mkdir()
    (outside_dir / "leaky_name.py").write_text('"""Outside."""\n', encoding="utf-8")
    try:
        (contained / "scripts").symlink_to(outside_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    result = _run(script, tmp_path, str(contained), "--root", str(root))
    combined = result.stdout + result.stderr
    assert "scripts/ resolves outside the permitted root" in combined, combined
    assert combined.count("scripts/ resolves outside the permitted root") == 1, combined
    assert "leaky_name" not in combined, combined
    assert "Traceback" not in combined, combined
    assert result.returncode == 1, combined


@pytest.mark.parametrize("tree", _TREES)
def test_symlinked_references_dir_escaping_root_is_rejected(tree: str, tmp_path: Path) -> None:
    script = _REPO_ROOT / tree / _FORGE / "validate-skill.py"
    root = tmp_path / "root"
    contained = root / "sample"
    _make_skill(contained)
    outside_dir = tmp_path / "outside-refs"
    outside_dir.mkdir()
    (outside_dir / "leaky_ref.md").write_text("# Outside\n", encoding="utf-8")
    try:
        (contained / "references").symlink_to(outside_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    result = _run(script, tmp_path, str(contained), "--root", str(root))
    combined = result.stdout + result.stderr
    assert "references/ resolves outside the permitted root" in combined, combined
    assert "leaky_ref" not in combined, combined
    assert "Traceback" not in combined, combined
    assert result.returncode == 1, combined


@pytest.mark.parametrize("tree", _TREES)
def test_symlinked_scripts_dir_inside_root_is_accepted(tree: str, tmp_path: Path) -> None:
    # Control: the same directory symlink with an in-root target is not flagged.
    script = _REPO_ROOT / tree / _FORGE / "validate-skill.py"
    root = tmp_path / "root"
    contained = root / "sample"
    _make_skill_with_scripts(contained)
    shared = root / "shared-scripts"
    shared.mkdir()
    (shared / "ok.py").write_text(_OK_SCRIPT, encoding="utf-8")
    try:
        (contained / "scripts").symlink_to(shared, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    result = _run(script, tmp_path, str(contained), "--root", str(root))
    combined = result.stdout + result.stderr
    assert _OUTSIDE_ROOT_MARKER not in combined, combined
    assert "Traceback" not in combined, combined
    assert result.returncode == 0, combined


def _load_validator(script: Path):
    """Import validate-skill.py as a module; restore sys.path afterwards."""
    # Evict the cached ``_path_guard`` so each tree imports its own sibling copy.
    saved = list(sys.path)
    sys.modules.pop("_path_guard", None)
    try:
        spec = importlib.util.spec_from_file_location(f"validate_skill_{script.parts[-5]}", script)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = saved
        sys.modules.pop("_path_guard", None)


@pytest.mark.parametrize("tree", _TREES)
def test_validate_skill_root_comparison_is_case_normalized(
    tree: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Windows paths differ only by casing (drive letter or component). Simulate a
    # case-insensitive host by pinning normcase to lower(): a root spelled with
    # different casing must still contain the skill, matching quick_validate.py.
    script = _REPO_ROOT / tree / _FORGE / "validate-skill.py"
    module = _load_validator(script)
    # Each tree must run its own _path_guard.py, not a copy cached by an earlier load.
    assert (
        Path(module.is_within.__code__.co_filename).resolve()
        == (script.parent / "_path_guard.py").resolve()
    )
    skill = tmp_path / "Repo" / "sample"
    _make_skill(skill)
    monkeypatch.setattr(module.os.path, "normcase", str.lower)
    other_casing = str(tmp_path / "REPO")
    validator = module.SkillValidator(str(skill), root=other_casing)
    assert validator.load_skill() is True
    with pytest.raises(ValueError, match=_TRAVERSAL_MARKER):
        module.SkillValidator(str(skill), root=str(tmp_path / "REPO-evil"))
