"""Pin the .gitignore rules for OS metadata files and local IDE state.

OS and editor droppings must stay out of git, while the shared VS Code
workspace config and the .env.example template must stay trackable.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_git_available = (
    shutil.which("git") is not None
    and subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    ).returncode
    == 0
)

pytestmark = pytest.mark.skipif(
    not _git_available,
    reason="git unavailable or not inside a work tree",
)

TRACKED_VSCODE_FILES = (
    ".vscode/extensions.json",
    ".vscode/mcp.json",
    ".vscode/settings.json",
    ".vscode/tasks.json",
    ".vscode/toolsets.jsonc",
)


def _check_ignore(relpath: str) -> bool:
    """Return True iff the .gitignore patterns match `relpath`.

    --no-index matters: without it git reports every tracked path as not
    ignored, so a broken re-include for a tracked file would still pass.
    """
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", relpath],
        cwd=REPO_ROOT,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise RuntimeError(f"git check-ignore failed (exit {result.returncode}) on {relpath}")


@pytest.mark.parametrize(
    "relpath",
    [
        ".DS_Store",
        "docs/.DS_Store",
        "docs/._notes.md",
        "Thumbs.db",
        "docs/ehthumbs.db",
        "desktop.ini",
        "scripts/module.py.swp",
        "README.md~",
    ],
)
def test_os_and_editor_files_are_ignored(relpath: str) -> None:
    assert _check_ignore(relpath), f"{relpath} should be gitignored"


@pytest.mark.parametrize("relpath", [".vscode/launch.json", ".vscode/settings.local.json"])
def test_local_vscode_state_is_ignored(relpath: str) -> None:
    assert _check_ignore(relpath), f"{relpath} is local IDE state and should be gitignored"


@pytest.mark.parametrize("relpath", TRACKED_VSCODE_FILES)
def test_shared_vscode_config_is_not_ignored(relpath: str) -> None:
    assert (REPO_ROOT / relpath).is_file(), f"{relpath} is expected to be tracked"
    assert not _check_ignore(relpath), f"{relpath} is shared config and must stay trackable"


def test_env_example_is_not_ignored() -> None:
    assert not _check_ignore(".env.example")


def test_local_env_files_stay_ignored() -> None:
    assert _check_ignore(".env")
    assert _check_ignore(".env.local")
