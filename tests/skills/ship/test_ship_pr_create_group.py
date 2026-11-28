"""The PR create runs in its own process group off Windows (issue #7807, gap 1).

``ship_pr.py publish`` ran ``new_pr.py`` with no
process group. A timeout killed the direct child only, so the ``gh``
grandchild kept running and could still open a PR after ``STOP: pr-create-failed``.
"""

from __future__ import annotations

import os
import signal
from pathlib import Path

import pytest

from tests.skills.ship.ship_helpers import publish, values
from tests.skills.ship.test_ship_push_lock import _assert_dead, _reap

posix_only = pytest.mark.skipif(os.name == "nt", reason="process groups are POSIX only")

# Prepended to a fake helper. On the create call it starts a grandchild in the
# helper's own process group, which holds none of the helper's pipes. With
# ``wait`` the helper then blocks on it, as new_pr.py blocks on gh.
_GRANDCHILD = """\
import os, subprocess, sys
if {token!r} in sys.argv:
    quiet = subprocess.DEVNULL
    grandchild = subprocess.Popen(["sleep", "60"], stdin=quiet, stdout=quiet, stderr=quiet)
    with open({pid_file!r}, "w", encoding="utf-8") as handle:
        handle.write(str(grandchild.pid))
    if {signum}:
        os.kill(os.getppid(), {signum})
    if {wait}:
        grandchild.wait()
"""


def _grandchild_on_create(
    helper: Path, token: str, pid_file: Path, signum: int = 0, wait: bool = True
) -> None:
    """Make ``helper`` start a grandchild when its argv holds ``token``."""
    shebang, body = helper.read_text(encoding="utf-8").split("\n", 1)
    prefix = _GRANDCHILD.format(token=token, pid_file=str(pid_file), signum=int(signum), wait=wait)
    helper.write_text(f"{shebang}\n{prefix}{body}", encoding="utf-8")


def _github_helper(fakes) -> tuple[Path, str]:
    return fakes.skills / "github" / "scripts" / "pr" / "new_pr.py", "--title"


def _spy_on_create(monkeypatch, common, token: str) -> list[dict]:
    """Record the keyword arguments of the create call; every call still runs for real."""
    real_run = common.run
    seen: list[dict] = []

    def spy(argv, *args, **kwargs):
        if token in argv:
            seen.append(kwargs)
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(common, "run", spy)
    return seen


@posix_only
class TestCreateTimeoutKillsTheGroup:
    def test_a_timeout_kills_the_grandchild(
        self, owner, fakes, scripts, capsys, monkeypatch, tmp_path
    ):
        _repo, body = owner
        path, token = _github_helper(fakes)
        pid_file = tmp_path / "grandchild.pid"
        _grandchild_on_create(path, token, pid_file)
        monkeypatch.setattr(scripts[3], "PR_TIMEOUT_SECONDS", 2)
        try:
            code, lines = publish(scripts, capsys, body)
            assert code == 3, lines
            assert values(lines, "PUSH") == ["pushed"]
            assert lines[-1].startswith("STOP: pr-create-failed "), lines
            assert "timed out after 2s (rerun publish; it detects an existing PR)" in lines[-1]
            _assert_dead(pid_file)
        finally:
            _reap(pid_file)

    @pytest.mark.parametrize(
        ("signum", "raised", "exit_code"),
        [
            pytest.param(signal.SIGINT, KeyboardInterrupt, None, id="SIGINT"),
            pytest.param(signal.SIGTERM, SystemExit, 143, id="SIGTERM"),
        ],
    )
    def test_a_signal_mid_create_kills_the_grandchild_and_propagates(
        self, owner, fakes, scripts, capsys, tmp_path, signum, raised, exit_code
    ):
        """A cancelled create leaves no ``gh`` behind. It prints no terminal line, as before."""
        _repo, body = owner
        path, token = _github_helper(fakes)
        pid_file = tmp_path / "grandchild.pid"
        _grandchild_on_create(path, token, pid_file, signum)
        before = [signal.getsignal(each) for each in (signal.SIGINT, signal.SIGTERM)]
        try:
            with pytest.raises(raised) as caught:
                publish(scripts, capsys, body)
            assert getattr(caught.value, "code", None) == exit_code
            _assert_dead(pid_file)
            assert [signal.getsignal(each) for each in (signal.SIGINT, signal.SIGTERM)] == before
        finally:
            _reap(pid_file)

    def test_a_create_that_ends_in_time_leaves_its_grandchild_alone(
        self, owner, fakes, scripts, capsys, tmp_path
    ):
        """Only a timeout or a signal kills the group; a normal create does not."""
        _repo, body = owner
        path, token = _github_helper(fakes)
        pid_file = tmp_path / "daemon.pid"
        _grandchild_on_create(path, token, pid_file, wait=False)
        try:
            code, lines = publish(scripts, capsys, body)
            assert code == 0, lines
            assert lines[-1] == "NEXT: discharge"
            os.kill(int(pid_file.read_text(encoding="utf-8")), 0)  # raises if it is gone
        finally:
            _reap(pid_file)


class TestCreateGroupFlag:
    """The flag itself, so Windows is covered with no real Windows process."""

    def test_windows_runs_the_create_with_no_group(
        self, owner, fakes, scripts, capsys, monkeypatch
    ):
        _repo, body = owner
        seen = _spy_on_create(monkeypatch, scripts[0], _github_helper(fakes)[1])
        monkeypatch.setattr(scripts[0], "on_windows", lambda: True)
        code, lines = publish(scripts, capsys, body)
        assert code == 0, lines
        assert [call["group"] for call in seen] == [False]

    @posix_only
    def test_posix_runs_the_create_in_a_group(self, owner, fakes, scripts, capsys, monkeypatch):
        _repo, body = owner
        seen = _spy_on_create(monkeypatch, scripts[0], _github_helper(fakes)[1])
        monkeypatch.setattr(scripts[0], "on_windows", lambda: False)
        code, lines = publish(scripts, capsys, body)
        assert code == 0, lines
        assert [call["group"] for call in seen] == [True]

    def test_the_create_keeps_its_timeout_and_work_tree(
        self, owner, fakes, scripts, capsys, monkeypatch
    ):
        repo, body = owner
        seen = _spy_on_create(monkeypatch, scripts[0], _github_helper(fakes)[1])
        assert scripts[3].PR_TIMEOUT_SECONDS == 180
        code, lines = publish(scripts, capsys, body)
        assert code == 0, lines
        assert [(call["timeout"], call["cwd"]) for call in seen] == [(180, repo.resolve())]
