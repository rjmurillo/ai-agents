"""Behavioral tests for caching ``_local_env_vars()`` (issue #5379).

``_local_env_vars()`` shells out to ``git rev-parse --local-env-vars`` to
discover the variable names git honors. That result depends only on the
installed git version, not on per-test state, so a successful discovery is
memoized in a module-level cache. This module proves four things the cache
must not break:

1. The subprocess runs once across many simulated pytest items, not once per
   item.
2. Environment sanitization (which reads the cached names but the *current*
   ``os.environ`` values) still runs on every item, driven by the discovered
   names and not just the hardcoded pointer-var tuple.
3. All three fallback triggers (git missing, git erroring, git succeeding
   with empty stdout) still return the hand-written pointer-var tuple, and
   the documented ``cache_clear()`` seam lets a test force rediscovery of a
   memoized successful result.
4. A failed discovery is never memoized, so a transient subprocess failure
   does not permanently pin the fallback for the rest of the worker process.

Test approach mirrors ``tests/test_conftest_git_isolation.py``: load
``tests/conftest.py`` as a standalone module per test so each test starts
with a fresh, empty cache instead of sharing state with the real pytest
session's ``tests/conftest.py`` import.
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import subprocess
import types
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

import pytest


def _load_tests_conftest() -> types.ModuleType:
    path = Path(__file__).resolve().parent / "conftest.py"
    spec = importlib.util.spec_from_file_location(
        "tests_conftest_local_env_vars_cache_under_test", path
    )
    assert spec is not None
    loader = spec.loader
    assert isinstance(loader, importlib.abc.Loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _get_autouse_fixture_fn(module: types.ModuleType) -> Callable[..., None]:
    """Return the unwrapped function behind the tmp_path isolation fixture.

    Mirrors ``tests/test_conftest_git_isolation.py``'s helper of the same
    shape. Calling the real fixture function (instead of the bare
    ``_sanitize_git_environment`` helper it wraps) is what proves a
    regression reachable only through the fixture, not just through the
    helper in isolation, still fails these tests.
    """
    fixture = module._isolate_tmp_path_from_parent_git_repo
    unwrapped = getattr(fixture, "__wrapped__", fixture)
    return cast("Callable[..., None]", unwrapped)


class TestLocalEnvVarsCachedAcrossItems:
    """The git subprocess must run once, not once per pytest item."""

    def test_subprocess_runs_once_across_multiple_calls(self) -> None:
        """Simulate several test items calling ``_local_env_vars()``.

        A call counter on the mocked ``subprocess.run`` proves the real
        ``git rev-parse`` process is invoked once no matter how many pytest
        items (simulated here as repeated calls) ask for the variable names.
        """
        module = _load_tests_conftest()
        call_count = 0

        def fake_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
            nonlocal call_count
            call_count += 1
            return SimpleNamespace(stdout="GIT_DIR\nGIT_WORK_TREE\n")

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            # Simulate three separate pytest items each triggering discovery.
            first_item = module._local_env_vars()
            second_item = module._local_env_vars()
            third_item = module._local_env_vars()

        assert call_count == 1, (
            f"git rev-parse ran {call_count} times across three simulated "
            "test items; caching should limit it to one subprocess per "
            "worker process."
        )
        assert first_item == second_item == third_item == (
            "GIT_DIR",
            "GIT_WORK_TREE",
        )

    def test_result_is_cached_object_identity(self) -> None:
        """Repeated calls return the cached tuple, not a freshly built one.

        ``lru_cache`` returns the exact same object on a cache hit. Asserting
        identity (not just equality) confirms the cache path is taken rather
        than a coincidentally-equal recomputation.
        """
        module = _load_tests_conftest()
        with patch.object(
            module.subprocess,
            "run",
            return_value=SimpleNamespace(stdout="GIT_DIR\n"),
        ):
            first = module._local_env_vars()
            second = module._local_env_vars()

        assert first is second


class TestSanitizationRunsEveryItem:
    """Caching the variable *names* must not skip per-item value clearing."""

    def test_delenv_called_on_every_simulated_item(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The discovered (not hardcoded) names are cleared on every item.

        The stubbed discovery includes ``GIT_CONFIG``, a name that is absent
        from the hardcoded ``_GIT_POINTER_VARS`` tuple. Asserting on it
        (instead of ``GIT_DIR``/``GIT_WORK_TREE``, both already in that
        hardcoded tuple) proves the *cached discovery result* drives
        sanitization, not just the hardcoded fallback: a regression that
        iterates only ``_GIT_POINTER_VARS`` would leave ``GIT_CONFIG``
        untouched and this test would fail.

        Two simulated pytest items go through the real autouse fixture
        function (not the bare ``_sanitize_git_environment`` helper), each
        setting a different hostile value for ``GIT_CONFIG``. Both items must
        still see their value cleared, proving the cache only short-circuits
        name discovery, not per-test sanitization. The outer ``monkeypatch``
        fixture (distinct from the per-item mocks passed into the fixture
        under test) guarantees the hostile values are restored even if an
        assertion fails.
        """
        module = _load_tests_conftest()
        fixture_fn = _get_autouse_fixture_fn(module)
        with patch.object(
            module.subprocess,
            "run",
            return_value=SimpleNamespace(
                stdout="GIT_DIR\nGIT_WORK_TREE\nGIT_CONFIG\n"
            ),
        ):
            # First simulated pytest item, no tmp_path fixture requested.
            deleted_first: list[str] = []
            mp_first = MagicMock()
            mp_first.delenv.side_effect = lambda name, raising=True: (
                deleted_first.append(name)
            )
            monkeypatch.setenv("GIT_CONFIG", "/hostile/first")
            request_first = SimpleNamespace(fixturenames=[], getfixturevalue=lambda _: None)
            fixture_fn(request_first, mp_first)
            assert "GIT_CONFIG" in deleted_first
            monkeypatch.delenv("GIT_CONFIG", raising=False)

            # Second simulated pytest item, a different hostile value for the
            # same discovered-only name. The cache (populated by the first
            # item) is reused; sanitization must still run.
            deleted_second: list[str] = []
            mp_second = MagicMock()
            mp_second.delenv.side_effect = lambda name, raising=True: (
                deleted_second.append(name)
            )
            monkeypatch.setenv("GIT_CONFIG", "/hostile/second")
            request_second = SimpleNamespace(fixturenames=[], getfixturevalue=lambda _: None)
            fixture_fn(request_second, mp_second)
            assert "GIT_CONFIG" in deleted_second
            monkeypatch.delenv("GIT_CONFIG", raising=False)


class TestGitUnavailableFallback:
    """The fallback to the hand-written pointer-var tuple must still work."""

    def test_falls_back_when_git_missing(self) -> None:
        """``OSError`` from ``subprocess.run`` (git not on PATH) falls back."""
        module = _load_tests_conftest()
        with patch.object(
            module.subprocess, "run", side_effect=OSError("git not found")
        ):
            result = module._local_env_vars()

        assert result == module._GIT_POINTER_VARS

    def test_falls_back_when_git_errors(self) -> None:
        """A non-zero git exit (``CalledProcessError``) falls back too."""
        module = _load_tests_conftest()
        with patch.object(
            module.subprocess,
            "run",
            side_effect=subprocess.CalledProcessError(1, ["git"]),
        ):
            result = module._local_env_vars()

        assert result == module._GIT_POINTER_VARS

    def test_falls_back_on_empty_stdout(self) -> None:
        """A git that exits 0 with empty stdout falls back too.

        ``git rev-parse --local-env-vars`` succeeding with no output is a
        third trigger for the fallback, distinct from ``OSError`` (git
        missing) and ``CalledProcessError`` (git erroring). Mutating
        ``return names or _GIT_POINTER_VARS`` to ``return names`` would
        return an empty tuple here instead of falling back, and this test
        would fail.
        """
        module = _load_tests_conftest()
        with patch.object(
            module.subprocess, "run", return_value=SimpleNamespace(stdout="")
        ):
            result = module._local_env_vars()

        assert result == module._GIT_POINTER_VARS

    def test_transient_failure_is_not_cached(self) -> None:
        """A failed call does not pin the fallback for the next call.

        Caching a transient subprocess failure (a fork failure under load, a
        timeout) would degrade the git-isolation guard for the rest of the
        worker process even after git starts answering again. Proven here
        without touching ``cache_clear()``: a failing call followed directly
        by a succeeding call must return the discovered names, not the
        fallback pinned by the first call.
        """
        module = _load_tests_conftest()

        with patch.object(module.subprocess, "run", side_effect=OSError("no git")):
            fallback_result = module._local_env_vars()
        assert fallback_result == module._GIT_POINTER_VARS

        with patch.object(
            module.subprocess,
            "run",
            return_value=SimpleNamespace(stdout="GIT_DIR\n"),
        ):
            recovered_result = module._local_env_vars()
        assert recovered_result == ("GIT_DIR",)

    def test_cache_clear_seam_forces_rediscovery(self) -> None:
        """``cache_clear()`` is the documented seam to force rediscovery.

        A successful discovery is memoized. After ``cache_clear()`` a second
        call must re-invoke the (now mocked-different) subprocess, proving
        the cache does not permanently pin a stale successful result.
        """
        module = _load_tests_conftest()

        with patch.object(
            module.subprocess,
            "run",
            return_value=SimpleNamespace(stdout="GIT_DIR\n"),
        ):
            first_result = module._local_env_vars()
        assert first_result == ("GIT_DIR",)

        module._local_env_vars.cache_clear()

        with patch.object(
            module.subprocess,
            "run",
            return_value=SimpleNamespace(stdout="GIT_WORK_TREE\n"),
        ):
            rediscovered_result = module._local_env_vars()
        assert rediscovered_result == ("GIT_WORK_TREE",)
