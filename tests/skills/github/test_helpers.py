"""Shared test helpers for GitHub skill script tests."""

import importlib.util
import subprocess
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
_scripts_dir = _project_root / ".claude" / "skills" / "github" / "scripts"

SKILL_SCRIPT_DIRS = {
    "issue": _scripts_dir / "issue",
    "milestone": _scripts_dir / "milestone",
    "reactions": _scripts_dir / "reactions",
    "utils": _scripts_dir / "utils",
    "root": _scripts_dir,
}


def make_completed_process(
    stdout: str = "", stderr: str = "", returncode: int = 0,
):
    """Create a mock CompletedProcess."""
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


def import_skill_script(name: str, subdir: str = "issue"):
    """Import a skill script by file path to avoid sys.path collisions.

    Uses importlib.util.spec_from_file_location so the correct file is loaded
    even when other test files add conflicting directories to sys.path.
    """
    script_dir = SKILL_SCRIPT_DIRS.get(subdir, _scripts_dir / subdir)
    script_path = script_dir / f"{name}.py"
    alias = f"skill_{name}"
    spec = importlib.util.spec_from_file_location(alias, script_path)
    assert spec is not None, f"Could not load spec for {script_path}"
    assert spec.loader is not None, f"Spec for {script_path} has no loader"
    mod = importlib.util.module_from_spec(spec)
    # Register under both alias and original name so patch() targets work
    sys.modules[alias] = mod
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
