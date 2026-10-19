"""Fixtures that pin the body-file containment rule's roots (issue #6667).

``tests/conftest.py`` re-exports these so every test module can request them.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _github_core_modules(submodule: str) -> list:
    """Return every loaded copy of ``github_core.<submodule>``.

    The suite can hold two copies of the package at once: the plugin copy that
    skill scripts load from ``.claude/lib`` as ``github_core``, and the
    canonical ``scripts.github_core``. Which one a script's containment check
    runs depends on import order, and the canonical copy resolves its git probe
    through ``scripts.github_core.repo``. A stub on one copy is invisible to the
    other, so patch all of them (issue #6667).
    """
    import importlib

    for prefix in ("github_core", "scripts.github_core"):
        try:
            importlib.import_module(f"{prefix}.{submodule}")
        except ImportError:
            continue
    return [
        module
        for name, module in list(sys.modules.items())
        if name in (f"github_core.{submodule}", f"scripts.github_core.{submodule}")
    ]


@pytest.fixture
def stub_git_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer the body-file containment git probes without a subprocess.

    ``github_core.validation.is_allowed_body_file_path`` asks git for the repo
    root and the git dir. Script tests that patch ``subprocess.run`` with an
    ordered ``side_effect`` list would see those probes as extra calls. This
    fake answers both from the checkout, so the containment rule runs for
    real and the ordered ``gh`` call lists stay exact (issue #6667).
    """
    from scripts.github_core.repo import REPO_ROOT_OK

    for repo_module in _github_core_modules("repo"):
        monkeypatch.setattr(
            repo_module,
            "resolve_repo_root",
            lambda **_kwargs: (PROJECT_ROOT, REPO_ROOT_OK),
        )
    for validation_module in _github_core_modules("validation"):
        monkeypatch.setattr(validation_module, "_candidate_git_dir_roots", lambda: [])


@pytest.fixture
def stub_temp_roots(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Pin the temp roots the body-file containment rule approves.

    ``github_core.validation._candidate_temp_roots`` also approves the system
    temp dir and ``/tmp``, so a test that expects "outside every root" would
    pass or fail on where the checkout and scratch space happen to live. Call
    the returned function with no argument for no temp roots, or with the
    directories that should count as temp roots (issue #6667).
    """

    def _set(*roots: Path) -> None:
        resolved = [str(Path(root).resolve()) for root in roots]
        for validation_module in _github_core_modules("validation"):
            monkeypatch.setattr(validation_module, "_candidate_temp_roots", lambda: list(resolved))

    return _set


@pytest.fixture
def tmp_path_is_temp_root(tmp_path: Path, stub_temp_roots: Callable[..., None]) -> Path:
    """Make ``tmp_path`` an approved temp root wherever the runner puts it.

    CI points ``--basetemp`` at the runner temp dir, which is not ``/tmp`` and
    not ``TMPDIR``, so a body file written under ``tmp_path`` fails the
    containment rule there while it passes on a developer machine.
    """
    stub_temp_roots(tmp_path)
    return tmp_path
