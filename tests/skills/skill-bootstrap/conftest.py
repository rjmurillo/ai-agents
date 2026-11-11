"""Shared path setup and git fixtures for the skill-bootstrap tests."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "skill-bootstrap"
_IMPORT_PATHS = (str(SKILL_DIR / "scripts"), str(Path(__file__).parent))
sys.path[:0] = _IMPORT_PATHS
try:
    # Cached in sys.modules so the test modules' top-level imports resolve
    # after the paths are removed again.
    import bootstrap_boundary  # noqa: F401
    import bootstrap_helpers  # noqa: F401
    import bootstrap_sweep  # noqa: F401
    import sweep_helpers
finally:
    for _path in _IMPORT_PATHS:
        sys.path.remove(_path)


def _run_git(repo: Path, *args: str) -> str:
    """Run git in `repo` and return stdout, failing the test on a non-zero exit."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return proc.stdout


def init_repo(path: Path) -> Path:
    """Create a git repository at `path` with one commit and one committed skill."""
    path.mkdir(parents=True)
    _run_git(path, "init", "-q")
    _run_git(path, "config", "user.name", "Test User")
    _run_git(path, "config", "user.email", "test@example.com")
    _run_git(path, "config", "commit.gpgsign", "false")
    (path / "README.md").write_text("# fixture\n", encoding="utf-8")
    skill = path / ".claude" / "skills" / "existing-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: existing-skill\n---\n", encoding="utf-8")
    _run_git(path, "add", "-A")
    _run_git(path, "commit", "-q", "-m", "chore: initial commit")
    return path.resolve()


@pytest.fixture
def make_repo() -> Callable[[Path], Path]:
    """Factory that creates a committed git repository at the given path."""
    return init_repo


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repository with HEAD and a committed `existing-skill`."""
    return init_repo(tmp_path / "repo")


@pytest.fixture
def snap_path(tmp_path: Path) -> Path:
    """A snapshot file location outside the fixture repository."""
    return tmp_path / "snaps" / "snapshot.json"


@pytest.fixture
def skill_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A skill directory with two judge rubrics; bootstrap_sweep reads judges from here."""
    return sweep_helpers.make_skill_dir(tmp_path, monkeypatch)


@pytest.fixture
def sweep(
    tmp_path: Path,
    repo: Path,
    skill_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> sweep_helpers.Run:
    """A sweep Run whose run directory sits beside, not inside, the fixture repo."""
    return sweep_helpers.make_run(tmp_path, repo, capsys)
