"""Shared fixtures for eval-harness tests.

The eval mains now run ``verify_model_available()`` before a live run
(issue #2857), which probes ``GET /v1/models``. Keep unit and integration
tests hermetic by skipping that network probe by default. Tests that exercise
the preflight itself delenv ``EVAL_SKIP_MODEL_PREFLIGHT`` explicitly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"


@pytest.fixture(autouse=True)
def _skip_model_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_SKIP_MODEL_PREFLIGHT", "1")


@pytest.fixture(autouse=True)
def _hermetic_credential_sources(monkeypatch: pytest.MonkeyPatch):
    """Keep the subscription transports off the operator's real logins.

    The shared credential order reads dotenv files, the CLIs' on-disk logins,
    and runs `claude auth status`, `codex login status`, and `gh auth token`.
    A unit test must reach none of that. Each transport's spec is replaced
    with one that has no disk credential and reports an existing login, which
    is the state every pre-existing transport test already assumed. A test
    about credential order replaces the spec again with `set_sources`.
    """
    from tests.eval._credential_test_support import install_inert_sources

    install_inert_sources(monkeypatch)
    yield
    from tests.eval._credential_test_support import reset_cache

    reset_cache()


@pytest.fixture(autouse=True)
def _ancestry_scan_stops_at_pytest_base_temp(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Keep the workspace-ancestry guard from reading the operator's home.

    `require_isolated_workspace_root` refuses a root with instruction files in
    any ancestor, including `~/.claude/CLAUDE.md`. A base temp under `$HOME`
    (`--basetemp`, or `TMPDIR` on disk) made every live-run test fail on the
    operator's own files. The scan is cut off at the pytest base temp for roots
    inside it, so a contaminated directory a test builds under `tmp_path` is
    still found. Roots outside the base temp use the real scan.
    """
    if str(EVAL_DIR) not in sys.path:
        sys.path.insert(0, str(EVAL_DIR))
    import _runtime_harness as harness

    real_scan = harness.ancestor_instructions
    base = tmp_path_factory.getbasetemp().resolve()

    def scan_below_base_temp(root: Path) -> list[Path]:
        found = real_scan(root)
        if not root.resolve().is_relative_to(base):
            return found
        return [path for path in found if path.is_relative_to(base)]

    monkeypatch.setattr(harness, "ancestor_instructions", scan_below_base_temp)
