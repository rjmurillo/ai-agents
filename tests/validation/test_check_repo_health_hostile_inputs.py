"""The gate's answer must come from the repository it was pointed at.

Split from ``test_check_repo_health.py``, which pins detection, to keep both
files under the 500-line taste ceiling. Two inputs the gate does not control
reach it before any config does.

The environment. git resolves a repository's location from ``GIT_DIR``,
``GIT_WORK_TREE``, and ``GIT_COMMON_DIR`` before it reads any config file, so a
value inherited from whatever invoked the hook redirects every answer the gate
collects. Measured on git 2.43.0 against a corrupted checkout with ``GIT_DIR``
naming an unrelated bare repository: ``rev-parse --git-common-dir`` and
``worktree list --porcelain`` both answered for that other repository, so live
corruption reported as a verified pass. ``GIT_CONFIG_KEY_n`` and its siblings
are deliberately left in place, because a command-scoped ``core.bare`` arrives
that way and the gate exists to report it.

The ``.git`` marker file. ``_marker_git_dir`` reads it while walking ancestors,
and an ancestor is any directory above the checkout, including directories the
gate's caller does not own. An unbounded read of a ``.git`` symlinked at a
character device such as ``/dev/zero`` never returns, which hangs the commit or
push the gate runs inside.

Coverage:

- positive: a healthy checkout still exits 0 with each override set, so the
  stripping does not turn every run into a failure.
- negative: a corrupted checkout still exits 1 with ``GIT_DIR`` or
  ``GIT_COMMON_DIR`` pointing at a genuine bare repository; ``_git`` passes none
  of the three location variables to the child while keeping ``GIT_CONFIG_KEY_0``.
- edge: an oversized marker, a marker that is a character device, and a marker
  that is a directory each resolve to nothing; a normal marker still resolves.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the way production imports (issue #2223): prepend ``scripts/validation``
# to ``sys.path`` and import by bare name.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_repo_health

# git 2.43.0 answers for the override rather than the working directory for
# these two, so each is a discriminating input rather than a defensive guess.
# GIT_WORK_TREE is stripped alongside them and is pinned structurally below.
_REDIRECTING_OVERRIDES = ["GIT_DIR", "GIT_COMMON_DIR"]

_CHARACTER_DEVICE = Path("/dev/zero")


def _git_test_env() -> dict[str, str]:
    """Return a host-independent environment for scratch Git repositories."""
    return {
        "PATH": os.environ.get("PATH", ""),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=_git_test_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result


@pytest.fixture(autouse=True)
def _use_scratch_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the gate's own git calls off the host's global and system config."""
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)


def _make_repo(root: Path, name: str = "repo") -> Path:
    """Create a scratch checkout with one commit."""
    repo = root / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    (repo / "tracked.txt").write_text("content\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _make_decoy_bare(tmp_path: Path) -> Path:
    """Create a genuine bare repository for an override to point at."""
    seed = _make_repo(tmp_path, "seed")
    decoy = tmp_path / "decoy.git"
    _git(tmp_path, "clone", "-q", "--bare", str(seed), str(decoy))
    return decoy


class TestAnInheritedLocationOverrideCannotChangeTheVerdict:
    """Negative: the answer must describe the repository named on the CLI."""

    def test_the_override_really_does_redirect_plain_git(self, tmp_path: Path) -> None:
        """The control. Without it the cases below prove nothing."""
        repo = _make_repo(tmp_path)
        decoy = _make_decoy_bare(tmp_path)

        redirected = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=str(repo),
            env={**_git_test_env(), "GIT_DIR": str(decoy)},
            capture_output=True,
            text=True,
            check=True,
        )

        assert Path(redirected.stdout.strip()) == decoy

    @pytest.mark.parametrize("override", _REDIRECTING_OVERRIDES)
    def test_a_corrupted_checkout_is_still_reported(
        self,
        override: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        repo = _make_repo(tmp_path)
        decoy = _make_decoy_bare(tmp_path)
        _git(repo, "config", "core.bare", "true")
        monkeypatch.setenv(override, str(decoy))

        code = check_repo_health.main([str(repo)])

        assert code == 1
        err = capsys.readouterr().err
        assert str(repo) in err
        assert str(decoy) not in err

    @pytest.mark.parametrize("override", _REDIRECTING_OVERRIDES)
    def test_a_healthy_checkout_still_passes(
        self, override: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Stripping must not convert every run into a failure."""
        repo = _make_repo(tmp_path)
        decoy = _make_decoy_bare(tmp_path)
        monkeypatch.setenv(override, str(decoy))

        assert check_repo_health.main([str(repo)]) == 0

    def test_no_location_variable_reaches_the_child_process(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pins the contract for all three, GIT_WORK_TREE included.

        Read at the boundary rather than through a verdict, because
        ``GIT_WORK_TREE`` is ignored by a bare-flagged repository and so cannot
        move any verdict this gate produces.
        """
        repo = _make_repo(tmp_path)
        for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR"):
            monkeypatch.setenv(name, str(tmp_path))
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.bare")
        seen: dict[str, str] = {}
        real_run = subprocess.run

        def _capture(*args: Any, **kwargs: Any) -> Any:
            seen.update(kwargs["env"])
            return real_run(*args, **kwargs)

        monkeypatch.setattr(check_repo_health.subprocess, "run", _capture)

        check_repo_health.main([str(repo)])

        assert seen, "the gate ran no git command, so nothing was measured"
        assert "GIT_DIR" not in seen
        assert "GIT_WORK_TREE" not in seen
        assert "GIT_COMMON_DIR" not in seen
        assert seen["GIT_CONFIG_KEY_0"] == "core.bare"


class TestAHostileGitMarkerIsRefusedRatherThanRead:
    """Edge: an ancestor's ``.git`` marker is input the gate does not own."""

    def test_a_normal_marker_still_resolves(self, tmp_path: Path) -> None:
        """The control for every refusal below."""
        target = tmp_path / "elsewhere"
        target.mkdir()
        marker = tmp_path / ".git"
        marker.write_text("gitdir: elsewhere\n", encoding="utf-8")

        assert check_repo_health._marker_git_dir(marker) == target.resolve()

    def test_an_oversized_marker_resolves_to_nothing(self, tmp_path: Path) -> None:
        """A real marker holds one short line, so size alone disqualifies this."""
        marker = tmp_path / ".git"
        padding = "x" * (check_repo_health._MAX_MARKER_BYTES + 1)
        marker.write_text(f"gitdir: elsewhere\n{padding}", encoding="utf-8")

        assert marker.stat().st_size > check_repo_health._MAX_MARKER_BYTES
        assert check_repo_health._marker_git_dir(marker) is None

    def test_a_marker_at_the_size_cap_is_still_read(self, tmp_path: Path) -> None:
        """The boundary: the cap refuses larger, not equal."""
        target = tmp_path / "elsewhere"
        target.mkdir()
        marker = tmp_path / ".git"
        line = "gitdir: elsewhere\n"
        marker.write_text(
            line + "\n" * (check_repo_health._MAX_MARKER_BYTES - len(line)),
            encoding="utf-8",
        )

        assert marker.stat().st_size == check_repo_health._MAX_MARKER_BYTES
        assert check_repo_health._marker_git_dir(marker) == target.resolve()

    @pytest.mark.skipif(
        not _CHARACTER_DEVICE.exists(), reason="no /dev/zero on this platform"
    )
    def test_a_marker_symlinked_at_a_character_device_resolves_to_nothing(
        self, tmp_path: Path
    ) -> None:
        """An unbounded read here never returns and hangs the commit."""
        marker = tmp_path / ".git"
        marker.symlink_to(_CHARACTER_DEVICE)

        assert check_repo_health._marker_git_dir(marker) is None

    @pytest.mark.skipif(
        not _CHARACTER_DEVICE.exists(), reason="no /dev/zero on this platform"
    )
    def test_the_ancestor_walk_survives_a_character_device_marker(
        self, tmp_path: Path
    ) -> None:
        """The walk is where a real invocation meets an ancestor it does not own."""
        holder = tmp_path / "holder"
        holder.mkdir()
        (holder / ".git").symlink_to(_CHARACTER_DEVICE)

        assert check_repo_health._work_tree_root(holder, tmp_path / "somewhere") is None

    def test_a_marker_that_is_a_directory_resolves_to_nothing(
        self, tmp_path: Path
    ) -> None:
        """``_work_tree_root`` resolves a directory itself and never reads it."""
        marker = tmp_path / ".git"
        marker.mkdir()

        assert check_repo_health._marker_git_dir(marker) is None
