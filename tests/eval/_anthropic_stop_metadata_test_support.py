"""Shared fixtures for the REQ-037 stop-metadata test files.

Loaded once here and imported by `test_anthropic_stop_metadata_*.py`, so the
sys.path dance for the hyphenated eval scripts and the urllib mock double
are not duplicated across those files. Mirrors the loader convention in
`_harness_capability_test_support.py`: do the sys.path mutation once at
import time, then hand back bound module objects.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"

_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    import _anthropic_api
    import _anthropic_response
    import _eval_api_adapter
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))


def load_hyphenated_module(name: str, filename: str) -> Any:
    """Load a hyphenated eval script as an importable module.

    The script imports sibling modules with plain `from X import Y`, so
    `EVAL_DIR` must be on `sys.path` while it loads.
    """
    path_added = str(EVAL_DIR) not in sys.path
    if path_added:
        sys.path.insert(0, str(EVAL_DIR))
    try:
        spec = importlib.util.spec_from_file_location(name, EVAL_DIR / filename)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if path_added and str(EVAL_DIR) in sys.path:
            sys.path.remove(str(EVAL_DIR))


rule_activation_mod = load_hyphenated_module("eval_rule_activation_stop", "eval-rule-activation.py")
prompt_change_mod = load_hyphenated_module("eval_prompt_change_stop", "eval-prompt-change.py")


class FakeUrlopenResponse(io.BytesIO):
    """Stand-in for `urllib.request.urlopen`'s context-managed return value."""

    def __enter__(self) -> FakeUrlopenResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def payload_response(payload: dict[str, Any]) -> FakeUrlopenResponse:
    return FakeUrlopenResponse(json.dumps(payload).encode())


class FakeTransport:
    """Injectable transport seam. Mirrors the shape production transports set."""

    def __init__(self, termination: str | None) -> None:
        self.calls = 0
        self.termination: str | None = termination
        self.system_fingerprint: str | None = None

    def __call__(self, prompt: str, model_id: str, system: str) -> str:
        self.calls += 1
        return "response text"


__all__ = [
    "EVAL_DIR",
    "REPO_ROOT",
    "FakeTransport",
    "FakeUrlopenResponse",
    "_anthropic_api",
    "_anthropic_response",
    "_eval_api_adapter",
    "load_hyphenated_module",
    "payload_response",
    "prompt_change_mod",
    "rule_activation_mod",
]
