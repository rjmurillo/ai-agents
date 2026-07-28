"""CI must install the resolution ``uv.lock`` pins.

``uv pip install -e ".[dev]"`` re-resolves from ``pyproject.toml`` and ignores
the lock entirely. Measured against this repo's lock on 2026-07-28, 30 packages
drifted, including ``mypy`` 2.1.0 to 2.3.0, ``pytest`` 9.0.3 to 9.1.1 and
``ruff`` 0.15.16 to 0.15.22. Every PR was graded by different tools than the
lock pins, and a compromised release of any dependency reached the runner
without a lockfile change to review (issue #3603).

``pytest.yml`` already carries a comment describing the ``ruff`` half of this
drift and works around it per-command with ``uv run --frozen``. That workaround
only covers the commands somebody remembered to wrap; the install itself is the
single place that fixes all of them.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION = REPO_ROOT / ".github/actions/setup-code-env/action.yml"


def _install_step() -> str:
    action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    for step in action["runs"]["steps"]:
        if step.get("name") == "Install Python dependencies":
            return step["run"]
    raise AssertionError("setup-code-env has no 'Install Python dependencies' step")


def test_the_install_reads_the_lock_file():
    body = _install_step()
    assert "uv export --frozen" in body
    assert "--no-emit-project" in body


def test_the_locked_export_is_what_gets_installed():
    """An export nobody installs from pins nothing."""
    body = _install_step()
    assert "uv pip install --system -r" in body


def test_the_project_is_installed_without_re_resolving():
    """A plain ``-e .`` after the pinned install would resolve dependencies
    again and undo the pinning."""
    body = _install_step()
    assert "uv pip install --system --no-deps -e ." in body


def test_no_unpinned_extra_install_survives_on_the_locked_path():
    """The pre-fix command may remain only on the no-lock fallback branch."""
    body = _install_step()
    unpinned = [
        line
        for line in body.splitlines()
        if 'uv pip install --system -e ".[dev]"' in line
    ]
    assert len(unpinned) <= 1
    if unpinned:
        assert "uv.lock" in body, "the fallback must be guarded by a lock check"


def test_the_lock_file_the_action_depends_on_exists():
    assert (REPO_ROOT / "uv.lock").is_file()
