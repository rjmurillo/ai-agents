"""Runtime test: run_completion_gate imports from an installed-plugin path.

Issue #2572: the installed Copilot plugin copy of run_completion_gate.py failed
with ``ModuleNotFoundError: No module named 'scripts'`` because the repo's
top-level scripts/ package is not bundled with the skill and the project-root
walk started from the script location (inside installed-plugins/) instead of
the user's working directory. This test copies the script to a directory with
no scripts/ tree above it and runs it from a separate working directory,
asserting the module loads (``--help`` reaches argparse).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "github"
    / "scripts"
    / "pr"
    / "run_completion_gate.py"
)


def test_runs_from_installed_path_without_scripts_tree(tmp_path: Path) -> None:
    # Simulate the installed plugin: script under .../skills/github/scripts/pr/
    # with no scripts/ package above it.
    installed = tmp_path / "installed-plugins" / "skills" / "github" / "scripts" / "pr"
    installed.mkdir(parents=True)
    shutil.copy2(_SCRIPT, installed / "run_completion_gate.py")

    # Separate working directory standing in for the user's repo (no scripts/).
    user_repo = tmp_path / "user_repo"
    (user_repo / ".git").mkdir(parents=True)

    result = subprocess.run(
        [sys.executable, str(installed / "run_completion_gate.py"), "--help"],
        cwd=user_repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert "ModuleNotFoundError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert "run_completion_gate.py" in result.stdout
