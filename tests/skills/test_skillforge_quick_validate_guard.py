"""Regression tests for the SkillForge quick_validate.py path-traversal guard.

Issue #3224: the CLI guard hardcoded ``~/.claude/skills`` as the only allowed
root, so any skill under the current working directory (a repo checkout, a
Copilot CLI install) was rejected with "Path traversal detected" and could
never be validated. The fix roots the CWE-22 guard at ``os.getcwd()`` to match
the sibling ``validate-skill.py`` and the SKILL.md "current directory" guidance.

These tests exercise the real CLI as the issue's repro does, and run against
both the ``.claude`` copy and the ``src/copilot-cli`` mirror so the two cannot
drift.
"""

from __future__ import annotations

import importlib.util
import ntpath
import posixpath
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

_SCRIPTS = [
    _REPO_ROOT / ".claude" / "skills" / "skillforge" / "scripts" / "quick_validate.py",
    _REPO_ROOT / "src" / "copilot-cli" / "skills" / "skillforge" / "scripts" / "quick_validate.py",
]

_TRAVERSAL_MARKER = "Path traversal detected"
_OUTSIDE_ROOT_MARKER = "outside the permitted root"


def _script_id(script: Path) -> str:
    """Distinguish the .claude copy from the copilot-cli mirror in test IDs."""
    return script.parts[-5]


def _make_skill(dir_path: Path) -> None:
    """Create a minimal skill directory so the guard has a real target."""
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "SKILL.md").write_text(
        "---\nname: sample\ndescription: sample skill\n---\n\n# Sample\n",
        encoding="utf-8",
    )


def _run(script: Path, cwd: Path, arg: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), arg],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_scripts_exist(script: Path) -> None:
    assert script.is_file(), f"missing quick_validate copy: {script}"


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_skill_under_cwd_passes_traversal_guard(script: Path, tmp_path: Path) -> None:
    # A skill under the current working directory must clear the CWE-22 guard.
    # The final validation verdict is irrelevant here; the guard must not fire.
    _make_skill(tmp_path / "my-skill")
    result = _run(script, cwd=tmp_path, arg="my-skill")
    combined = result.stdout + result.stderr
    # The script must reach a clean validation verdict, not crash before the
    # guard: a traceback would also lack the traversal marker (a false pass).
    assert result.returncode == 0, combined
    assert _TRAVERSAL_MARKER not in combined, combined
    assert _OUTSIDE_ROOT_MARKER not in combined, combined


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_dotdot_escape_above_cwd_is_rejected(script: Path, tmp_path: Path) -> None:
    # CWE-22 protection is preserved: a path resolving above cwd is rejected.
    outside = tmp_path / "outside-skill"
    _make_skill(outside)
    workdir = tmp_path / "work"
    workdir.mkdir()
    result = _run(script, cwd=workdir, arg="../outside-skill")
    combined = result.stdout + result.stderr
    assert _TRAVERSAL_MARKER in combined, combined
    assert result.returncode == 1


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_absolute_path_outside_cwd_is_rejected(script: Path, tmp_path: Path) -> None:
    # An absolute path outside the working directory is also an escape.
    outside = tmp_path / "elsewhere"
    _make_skill(outside)
    workdir = tmp_path / "work"
    workdir.mkdir()
    result = _run(script, cwd=workdir, arg=str(outside))
    combined = result.stdout + result.stderr
    assert _TRAVERSAL_MARKER in combined, combined
    assert result.returncode == 1


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_descendant_symlink_skill_md_is_rejected(script: Path, tmp_path: Path) -> None:
    # CWE-22: even when the skill directory is contained under cwd, a SKILL.md
    # symlink whose target is outside cwd must not be read or validated.
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.md"
    secret.write_text(
        "---\nname: leaked\ndescription: out-of-root content\n---\n",
        encoding="utf-8",
    )
    workdir = tmp_path / "work"
    contained = workdir / "evil"
    contained.mkdir(parents=True)
    try:
        (contained / "SKILL.md").symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    result = _run(script, cwd=workdir, arg="evil")
    combined = result.stdout + result.stderr
    assert _OUTSIDE_ROOT_MARKER in combined, combined
    assert result.returncode == 1, combined
    assert "Skill is valid" not in combined, combined


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_symlink_within_cwd_is_allowed(script: Path, tmp_path: Path) -> None:
    # A SKILL.md symlink whose target stays inside cwd resolves within the root,
    # so neither the traversal guard nor the containment check may fire.
    workdir = tmp_path / "work"
    real = workdir / "real"
    real.mkdir(parents=True)
    (real / "SKILL.md").write_text(
        "---\nname: ok\ndescription: in-root content\n---\n",
        encoding="utf-8",
    )
    skill = workdir / "skill"
    skill.mkdir()
    try:
        (skill / "SKILL.md").symlink_to(real / "SKILL.md")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    result = _run(script, cwd=workdir, arg="skill")
    combined = result.stdout + result.stderr
    # A clean exit proves the script validated the in-root target rather than
    # crashing before the guard (a traceback would also lack both markers).
    assert result.returncode == 0, combined
    assert _OUTSIDE_ROOT_MARKER not in combined, combined
    assert _TRAVERSAL_MARKER not in combined, combined


def _load_module(script: Path):
    """Import a quick_validate copy as a module to unit-test its helpers."""
    spec = importlib.util.spec_from_file_location(
        f"quick_validate_{script.parts[-5]}", script
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("script", _SCRIPTS, ids=_script_id)
def test_is_within_handles_filesystem_root(script: Path) -> None:
    # Cross-platform regression for the containment guard. ``_is_within`` runs on
    # the host's ``os.path``, so a host-only assertion (POSIX literals on Linux CI)
    # never exercises Windows drive/UNC root semantics where the CWE-22 sibling-
    # share bypass lived. Inject ``posixpath`` and ``ntpath`` explicitly so both
    # platforms are covered deterministically on any host. Inputs are normcased
    # with the same module to mirror the production caller
    # (``os.path.normcase(os.path.realpath(...))``).
    is_within = _load_module(script)._is_within
    cases = [
        # (pathmod, child, root, expected, label)
        (posixpath, "/foo", "/", True, "posix descendant of root"),
        (posixpath, "/tmp/x", "/tmp", True, "posix normal containment"),
        (posixpath, "/tmp", "/tmp", True, "posix exact root"),
        (posixpath, "/tmpevil", "/tmp", False, "posix sibling prefix"),
        (ntpath, r"c:\repo\skill", r"c:\repo", True, "win normal containment"),
        (ntpath, r"c:\repo", r"c:\repo", True, "win exact root"),
        (ntpath, r"c:\repoevil", r"c:\repo", False, "win sibling prefix"),
        (ntpath, r"c:\evil", "c:\\", True, "win descendant of bare drive root"),
        (ntpath, r"d:\x", "c:\\", False, "win different drive fails closed"),
        (ntpath, r"\\srv\share\repo\skill", r"\\srv\share\repo", True, "win UNC nested child"),
        (ntpath, r"\\srv\share\repo", r"\\srv\share\repo", True, "win UNC exact root"),
        (ntpath, r"\\srv\share\repoevil\x", r"\\srv\share\repo", False, "win UNC sibling prefix"),
        (ntpath, r"\\srv\other\x", r"\\srv\share\repo", False, "win different UNC share"),
        # The CWE-22 bypass the commonpath fix closes: a sibling share whose name
        # string-prefixes the sandbox root. os.path.join(root, "") appends no
        # separator to a bare UNC share, so the old startswith() let this escape.
        (
            ntpath,
            r"\\srv\shareevil\skill",
            r"\\srv\share",
            False,
            "win bare UNC sibling share (CWE-22)",
        ),
        # Regression (adv review of #3226): a legitimate descendant directly
        # under a bare UNC share root must be accepted. ``ntpath.commonpath``
        # raises "Can't mix absolute and relative paths" here because the bare
        # share root's root-relative part is empty; the drive-aware fallback
        # keeps this contained instead of false-rejecting a real SKILL.md read.
        (
            ntpath,
            r"\\srv\share\skill",
            r"\\srv\share",
            True,
            "win bare UNC share root, valid child",
        ),
        (
            ntpath,
            r"\\srv\share",
            r"\\srv\share",
            True,
            "win bare UNC share root, exact equal",
        ),
    ]
    for pathmod, child, root, expected, label in cases:
        got = is_within(pathmod.normcase(child), pathmod.normcase(root), pathmod)
        assert got is expected, f"{label}: is_within({child!r}, {root!r}) = {got}, want {expected}"
