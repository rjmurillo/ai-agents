"""Tests for the stray system temp ``.git`` guard (issue #6889)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from scripts.testing import system_temp_git_guard as guard

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _config(*, worker: bool) -> Any:
    namespace = SimpleNamespace()
    if worker:
        namespace.workerinput = {"workerid": "gw0"}
    return namespace


class TestDescribeStrayGit:
    def test_returns_none_when_the_entry_is_absent(self, tmp_path: Path) -> None:
        assert guard.describe_stray_git(tmp_path / ".git") is None

    def test_names_the_path_and_an_empty_directory(self, tmp_path: Path) -> None:
        stray = tmp_path / ".git"
        stray.mkdir()

        message = guard.describe_stray_git(stray)

        assert message is not None
        assert str(stray) in message
        assert "holding: nothing" in message
        assert "#6889" in message

    def test_lists_the_entries_it_holds(self, tmp_path: Path) -> None:
        stray = tmp_path / ".git"
        stray.mkdir()
        (stray / "config.worktree").write_text("", encoding="utf-8")

        message = guard.describe_stray_git(stray)

        assert message is not None
        assert "config.worktree" in message

    def test_truncates_a_long_listing(self, tmp_path: Path) -> None:
        stray = tmp_path / ".git"
        stray.mkdir()
        for index in range(guard._ENTRY_LIMIT + 3):
            (stray / f"entry-{index:02d}").write_text("", encoding="utf-8")

        message = guard.describe_stray_git(stray)

        assert message is not None
        assert "and 3 more" in message
        assert f"entry-{guard._ENTRY_LIMIT + 2:02d}" not in message

    def test_flags_a_plain_file(self, tmp_path: Path) -> None:
        stray = tmp_path / ".git"
        stray.write_text("gitdir: /elsewhere\n", encoding="utf-8")

        message = guard.describe_stray_git(stray)

        assert message is not None
        assert "not a plain directory" in message

    def test_flags_a_dangling_symlink(self, tmp_path: Path) -> None:
        stray = tmp_path / ".git"
        stray.symlink_to(tmp_path / "missing-target")

        message = guard.describe_stray_git(stray)

        assert message is not None
        assert str(stray) in message

    @pytest.mark.skipif(
        os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
        reason="needs POSIX permissions and a non-root user",
    )
    def test_reports_a_directory_it_cannot_list(self, tmp_path: Path) -> None:
        stray = tmp_path / ".git"
        stray.mkdir()
        stray.chmod(0)
        try:
            message = guard.describe_stray_git(stray)
        finally:
            stray.chmod(0o700)

        assert message is not None
        assert "cannot be listed" in message


class TestSystemTempGitPath:
    def test_follows_the_current_system_temp_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

        assert guard.system_temp_git_path() == tmp_path / ".git"


class TestHooksSkipWorkers:
    def test_a_worker_ignores_a_stray_at_start(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(guard, "describe_stray_git", lambda _path: "stray")
        session = SimpleNamespace(config=_config(worker=True))

        guard.pytest_sessionstart(cast("pytest.Session", session))

    def test_a_worker_leaves_the_exit_status_alone_at_finish(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(guard, "describe_stray_git", lambda _path: "stray")
        session = SimpleNamespace(config=_config(worker=True), exitstatus=0)

        guard.pytest_sessionfinish(cast("pytest.Session", session), 0)

        assert session.exitstatus == 0

    def test_the_controller_exits_at_start_on_a_stray(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(guard, "describe_stray_git", lambda _path: "stray")
        session = SimpleNamespace(config=_config(worker=False))

        with pytest.raises(pytest.exit.Exception) as raised:
            guard.pytest_sessionstart(cast("pytest.Session", session))

        assert raised.value.returncode == 4
        assert "stray" in str(raised.value)

    def test_the_controller_passes_at_start_without_a_stray(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(guard, "describe_stray_git", lambda _path: None)
        session = SimpleNamespace(config=_config(worker=False))

        guard.pytest_sessionstart(cast("pytest.Session", session))


def _run_pytest(
    project: Path, fake_tmp: Path, *args: str, plugin: bool = True
) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env["TMPDIR"] = str(fake_tmp)
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTEST_ADDOPTS", None)
    command = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-o", "addopts="]
    if plugin:
        command += ["-p", "scripts.testing.system_temp_git_guard"]
    command += list(args)
    return subprocess.run(
        command,
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "test_sample.py").write_text("def test_runs():\n    assert True\n", encoding="utf-8")
    return root


@pytest.fixture
def fake_tmp(tmp_path: Path) -> Path:
    path = tmp_path / "system-tmp"
    path.mkdir()
    return path


class TestRunBehavior:
    def test_a_clean_temp_directory_passes(self, project: Path, fake_tmp: Path) -> None:
        result = _run_pytest(project, fake_tmp)

        assert result.returncode == 0, result.stdout + result.stderr

    def test_a_stray_at_start_stops_the_run_before_any_test(
        self, project: Path, fake_tmp: Path
    ) -> None:
        (fake_tmp / ".git").mkdir()
        (fake_tmp / ".git" / "config.worktree").write_text("", encoding="utf-8")

        result = _run_pytest(project, fake_tmp)

        output = result.stdout + result.stderr
        assert result.returncode == 4, output
        assert "Stray system temp .git before the run" in output
        assert str(fake_tmp / ".git") in output
        assert "config.worktree" in output
        assert "test_runs" not in output

    def test_without_the_plugin_the_same_stray_goes_unnoticed(
        self, project: Path, fake_tmp: Path
    ) -> None:
        (fake_tmp / ".git").mkdir()

        result = _run_pytest(project, fake_tmp, plugin=False)

        assert result.returncode == 0, result.stdout + result.stderr

    def test_a_stray_created_during_the_run_fails_the_run(
        self, project: Path, fake_tmp: Path
    ) -> None:
        (project / "test_creates_stray.py").write_text(
            textwrap.dedent(
                """
                import tempfile
                from pathlib import Path


                def test_creates_the_stray():
                    (Path(tempfile.gettempdir()) / ".git").mkdir()
                """
            ),
            encoding="utf-8",
        )

        result = _run_pytest(project, fake_tmp)

        output = result.stdout + result.stderr
        assert result.returncode == 1, output
        assert "appeared during the run" in output
        assert "2 passed" in output

    def test_a_failed_run_keeps_its_own_exit_status(self, project: Path, fake_tmp: Path) -> None:
        (project / "test_fails_and_creates.py").write_text(
            textwrap.dedent(
                """
                import tempfile
                from pathlib import Path


                def test_fails_after_creating():
                    (Path(tempfile.gettempdir()) / ".git").mkdir()
                    raise AssertionError("boom")
                """
            ),
            encoding="utf-8",
        )

        result = _run_pytest(project, fake_tmp)

        assert result.returncode == 1, result.stdout + result.stderr
        assert "appeared during the run" in result.stdout + result.stderr

    def test_xdist_reports_the_stray_once_from_the_controller(
        self, project: Path, fake_tmp: Path
    ) -> None:
        (fake_tmp / ".git").mkdir()

        serial = _run_pytest(project, fake_tmp)
        parallel = _run_pytest(project, fake_tmp, "-n", "2")

        marker = "Stray system temp .git before the run"
        serial_output = serial.stdout + serial.stderr
        parallel_output = parallel.stdout + parallel.stderr
        assert parallel.returncode == 4, parallel_output
        assert parallel_output.count(marker) == serial_output.count(marker) > 0

    def test_xdist_reports_a_stray_a_worker_created_once_at_the_end(
        self, project: Path, fake_tmp: Path
    ) -> None:
        (project / "test_worker_creates_stray.py").write_text(
            textwrap.dedent(
                """
                import tempfile
                from pathlib import Path


                def test_worker_creates_the_stray():
                    (Path(tempfile.gettempdir()) / ".git").mkdir()
                """
            ),
            encoding="utf-8",
        )

        result = _run_pytest(project, fake_tmp, "-n", "2")

        output = result.stdout + result.stderr
        assert result.returncode == 1, output
        assert output.count("appeared during the run") == 1
        assert "2 passed" in output

    def test_the_repository_conftest_registers_the_guard(self, fake_tmp: Path) -> None:
        (fake_tmp / ".git").mkdir()

        result = _run_pytest(
            PROJECT_ROOT,
            fake_tmp,
            "--collect-only",
            "-q",
            "tests/test_system_temp_git_guard.py",
            plugin=False,
        )

        output = result.stdout + result.stderr
        assert result.returncode == 4, output
        assert "Stray system temp .git before the run" in output
