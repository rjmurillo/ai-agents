"""Shared test fixtures for the sg_reference_ab_* test modules (#5856).

Not a test module itself (no ``test_`` functions; pytest collects nothing
here), so it is not subject to the taste-lints file-size gate's own
"cohesive seam" pressure the way the test modules that import it are. Holds
the scripted ``urlopen`` fake, response-payload builders, and the stub
plugin-directory builder that ``tests/metrics/test_sg_reference_ab_api.py``,
``test_sg_reference_ab_toolloop.py``, and ``test_sg_reference_ab.py`` all
need, so none of them duplicates it.
"""

from __future__ import annotations

import io
import json
import urllib.error
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from scripts.metrics.sg_reference_ab import DEFAULT_PLUGIN_DIR as _PLUGIN_HOOKS_DIR

__all__ = [
    "SCHEMA",
    "http_error",
    "make_fake_urlopen",
    "plugin_hooks_dir",
    "report_findings_response",
    "text_only_response",
    "tool_use_response",
    "write_stub_plugin",
]

plugin_hooks_dir = _PLUGIN_HOOKS_DIR

SCHEMA = {
    "type": "object",
    "properties": {"findings": {"type": "array"}},
    "required": ["findings"],
}


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def make_fake_urlopen(
    actions: list[dict[str, Any] | Exception],
) -> tuple[Callable[..., _FakeHTTPResponse], list[Any]]:
    """A ``urlopen`` replacement consuming ``actions`` in order.

    Each action is either a response payload (dict) or an exception instance
    to raise. Returns the fake and the list of requests it was called with,
    so a test can assert call count (for retry behavior).
    """
    calls: list[Any] = []

    def _fake_urlopen(request: Any, timeout: float | None = None) -> _FakeHTTPResponse:
        calls.append(request)
        action = actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return _FakeHTTPResponse(action)

    return _fake_urlopen, calls


def http_error(code: int, body: bytes | None = None) -> urllib.error.HTTPError:
    """Build an ``HTTPError`` whose ``.read()`` returns ``body`` (default: no body,
    matching a real ``HTTPError`` built with ``fp=None``, whose ``.read()``
    returns ``b""`` rather than raising).
    """
    fp = io.BytesIO(body) if body is not None else None
    return urllib.error.HTTPError(
        "https://api.anthropic.com/v1/messages", code, "err", cast(Any, {}), cast(Any, fp)
    )


def report_findings_response(
    findings: list[dict[str, Any]], usage: dict[str, int] | None = None
) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "tool_use",
                "id": "tool_1",
                "name": "report_findings",
                "input": {"findings": findings},
            }
        ],
        "usage": usage or {"input_tokens": 100, "output_tokens": 20},
    }


def tool_use_response(
    name: str, tool_input: dict[str, Any], usage: dict[str, int] | None = None
) -> dict[str, Any]:
    return {
        "content": [
            {"type": "tool_use", "id": f"tool_{name}", "name": name, "input": tool_input}
        ],
        "usage": usage or {"input_tokens": 50, "output_tokens": 10},
    }


def text_only_response() -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": "I am done."}],
        "usage": {"input_tokens": 5, "output_tokens": 5},
    }


def write_stub_plugin(root: Path, *, with_version: bool = True, valid: bool = True) -> Path:
    """A minimal fake ``security-guidance`` plugin directory for
    ``load_plugin_contract`` and CLI tests, returning its ``hooks/`` path.
    """
    plugin_root = root / "security-guidance-stub"
    hooks_dir = plugin_root / "hooks"
    hooks_dir.mkdir(parents=True)
    if valid:
        review_api_body = (
            'AGENTIC_INVESTIGATE_SYSTEM = "system prompt for tests"\n'
            'FINDINGS_SCHEMA = {\n'
            '    "type": "object",\n'
            '    "properties": {"findings": {"type": "array"}},\n'
            '    "required": ["findings"],\n'
            "}\n"
        )
    else:
        review_api_body = "# no AGENTIC_INVESTIGATE_SYSTEM or FINDINGS_SCHEMA here\n"
    (hooks_dir / "review_api.py").write_text(review_api_body, encoding="utf-8")
    (hooks_dir / "llm.py").write_text("# stub llm.py\n", encoding="utf-8")
    if with_version:
        plugin_json_dir = plugin_root / ".claude-plugin"
        plugin_json_dir.mkdir(parents=True)
        (plugin_json_dir / "plugin.json").write_text(
            json.dumps({"name": "security-guidance", "version": "9.9.9"}), encoding="utf-8"
        )
    return hooks_dir
