"""Helpers that pin the credential sources of the subscription transports.

The transports are flat sibling modules (`_claude_cli`, `_codex_cli`,
`_copilot_cli`) that tests import under a `sys.path` entry. This module finds
them in `sys.modules` instead of importing a second copy, for the reason the
note in `test_providers.py` gives: a patch on one copy misses the other.
"""

from __future__ import annotations

import dataclasses
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
_ORIGINAL_SYS_PATH = sys.path.copy()
sys.path.insert(0, str(_EVAL_DIR))
try:
    import _cli_credential_sources
    import _cli_credentials
    import _copilot_cli
finally:
    sys.path[:] = _ORIGINAL_SYS_PATH

TRANSPORT_MODULES = ("_claude_cli", "_codex_cli", "_copilot_cli")

__all__ = [
    "_cli_credential_sources",
    "_cli_credentials",
    "_copilot_cli",
    "TRANSPORT_MODULES",
    "install_inert_sources",
    "reset_cache",
    "set_sources",
]


def reset_cache() -> None:
    _cli_credentials.reset_credential_cache()


def set_sources(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    *,
    disk: Callable[[Mapping[str, str]], str | None] | None = None,
    probe: bool = False,
) -> None:
    """Replace one transport's disk reader and login probe, and clear the cache."""
    module = sys.modules[module_name]
    spec = dataclasses.replace(
        module.CREDENTIAL_SPEC,
        read_disk=disk if disk is not None else (lambda environ: None),
        login_probe=lambda executable, environ: probe,
    )
    monkeypatch.setattr(module, "CREDENTIAL_SPEC", spec)
    reset_cache()


def install_inert_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """No dotenv, no disk login, and an existing login, for every transport."""
    monkeypatch.setenv("EVAL_DOTENV_FILES", "/nonexistent/ai-agents-eval.env")
    reset_cache()
    for name in TRANSPORT_MODULES:
        if name in sys.modules:
            set_sources(monkeypatch, name, probe=True)
