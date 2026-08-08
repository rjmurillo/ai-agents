"""Behavioral tests for the tmp_path git isolation fixture (issue #4287).

``GIT_CEILING_DIRECTORIES`` stops upward discovery but is inert when ``GIT_DIR``
is set, because an explicit ``GIT_DIR`` bypasses discovery entirely. The fix in
``tests/conftest.py`` unsets every pointer variable before setting the ceiling.

Test approach: directly test the fixture function with a synthetic MonkeyPatch
so the behavior is observable regardless of the host environment.
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import os
import subprocess
import types
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock


def _load_tests_conftest() -> types.ModuleType:
    path = Path(__file__).resolve().parent / "conftest.py"
    spec = importlib.util.spec_from_file_location("tests_conftest_under_test", path)
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, importlib.abc.Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _get_fixture_fn(module: types.ModuleType) -> Callable[..., None]:
    """Return the unwrapped function behind the isolation fixture."""
    fixture = module._isolate_tmp_path_from_parent_git_repo
    unwrapped = getattr(fixture, "__wrapped__", fixture)
    return cast("Callable[..., None]", unwrapped)


class TestHostileGitDirIsUnsetByFixture:
    """The isolation fixture must unset GIT_DIR (and siblings) before ceiling."""

    def test_git_dir_is_deleted_when_present(self, tmp_path: Path) -> None:
        """Fixture calls monkeypatch.delenv for GIT_DIR.

        Load the tests/conftest module and call the fixture directly with a
        synthetic MonkeyPatch that records delenv calls. Verify GIT_DIR is
        among them.
        """
        module = _load_tests_conftest()
        fixture_fn = _get_fixture_fn(module)

        deleted: list[str] = []
        setenvs: dict[str, str] = {}

        mp = MagicMock()
        mp.delenv.side_effect = lambda name, raising=True: deleted.append(name)
        mp.setenv.side_effect = lambda name, value: setenvs.update({name: value})

        request = SimpleNamespace(
            fixturenames=["tmp_path"],
            getfixturevalue=lambda _: tmp_path,
        )

        fixture_fn(request, mp)

        assert "GIT_DIR" in deleted, (
            "GIT_DIR was not passed to monkeypatch.delenv. "
            "A hostile caller that exported GIT_DIR would bypass the ceiling."
        )
        assert "GIT_WORK_TREE" in deleted
        assert "GIT_COMMON_DIR" in deleted
        assert "GIT_INDEX_FILE" in deleted
        assert "GIT_OBJECT_DIRECTORY" in deleted
        assert "GIT_ALTERNATE_OBJECT_DIRECTORIES" in deleted
        assert "GIT_CEILING_DIRECTORIES" in setenvs, "ceiling must still be set"

    def test_ceiling_contains_tmp_path_parent(self, tmp_path: Path) -> None:
        """The ceiling is set to tmp_path.parent so siblings are also isolated."""
        module = _load_tests_conftest()
        fixture_fn = _get_fixture_fn(module)

        setenvs: dict[str, str] = {}
        mp = MagicMock()
        mp.delenv.return_value = None
        mp.setenv.side_effect = lambda name, value: setenvs.update({name: value})

        request = SimpleNamespace(
            fixturenames=["tmp_path"],
            getfixturevalue=lambda _: tmp_path,
        )

        fixture_fn(request, mp)

        ceiling = setenvs.get("GIT_CEILING_DIRECTORIES", "")
        assert str(tmp_path.parent) in ceiling

    def test_no_ceiling_without_tmp_path_but_still_sanitized(
        self, tmp_path: Path
    ) -> None:
        """No ceiling without tmp_path, but the environment is still sanitized.

        The ceiling needs a path, so it stays conditional. Unsetting an
        inherited pointer does not, and gating it on tmp_path left every module
        that builds its sandbox with tempfile unprotected. Refs #4717.
        """
        module = _load_tests_conftest()
        fixture_fn = _get_fixture_fn(module)

        deleted: list[str] = []
        setenvs: dict[str, str] = {}
        mp = MagicMock()
        mp.delenv.side_effect = lambda name, raising=True: deleted.append(name)
        mp.setenv.side_effect = lambda name, value: setenvs.update({name: value})

        request = SimpleNamespace(
            fixturenames=[],
            getfixturevalue=lambda _: tmp_path,
        )

        fixture_fn(request, mp)

        assert "GIT_DIR" in deleted, (
            "pointer vars must be unset even when the test has no tmp_path"
        )
        assert "GIT_CONFIG_PARAMETERS" in deleted, (
            "inherited config injection must be unset even without tmp_path"
        )
        assert "GIT_CEILING_DIRECTORIES" not in setenvs, (
            "GIT_CEILING_DIRECTORIES must not be set when tmp_path is absent"
        )


class TestNegativeControl:
    """Without the fix a hostile GIT_DIR redirects git operations away from tmp_path.

    This class proves the underlying failure mode is real, by directly calling
    a git subprocess with GIT_DIR in the environment. When the isolation is in
    place (the fixture cleared GIT_DIR), the subprocesses here work normally
    because the test body does not re-inject it.
    """

    def test_git_init_creates_dot_git_in_tmp_path(self, tmp_path: Path) -> None:
        """With isolation active, git init creates .git in tmp_path.

        The fixture already ran and cleared GIT_DIR (if any) by the time this
        test body executes. This test confirms the positive case holds.
        """
        result = subprocess.run(
            ["git", "init", "-q", "-b", "main", str(tmp_path)],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0
        assert (tmp_path / ".git").is_dir(), (
            "git init did not create .git in tmp_path. "
            "GIT_DIR or GIT_WORK_TREE may be leaking into the subprocess environment."
        )

    def test_hostile_git_dir_without_isolation_redirects_operations(
        self, tmp_path: Path
    ) -> None:
        """Prove the failure mode: GIT_DIR in env redirects git init away from cwd.

        This test does NOT rely on the fixture to clear GIT_DIR; it manually
        passes a hostile env to the subprocess to demonstrate the original bug.
        The test is labeled as the negative control: without isolation, git
        init creates nothing at the cwd.
        """
        real_repo = tmp_path / "real"
        real_repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=real_repo, check=True)

        work = tmp_path / "work"
        work.mkdir()

        hostile_env = {**os.environ, "GIT_DIR": str(real_repo / ".git")}
        subprocess.run(
            ["git", "init", "-q", "-b", "main"],
            cwd=work,
            env=hostile_env,
            check=False,
        )

        # Confirm the failure: work has no .git because GIT_DIR hijacked the init.
        assert not (work / ".git").is_dir(), (
            "Expected git init to be redirected by GIT_DIR (this is the failure mode "
            "the fixture fixes). If .git was created, git's behavior changed."
        )
