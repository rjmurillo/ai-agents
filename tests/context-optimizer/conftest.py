"""
conftest.py for context-optimizer tests.

Skips all tests in this directory when tiktoken's BPE data cannot be loaded
(e.g., in network-restricted environments where openaipublic.blob.core.windows.net
is unreachable). Tests that call compress_markdown_content.py require tiktoken
for token count metrics, making the entire test module network-dependent.
"""

from __future__ import annotations

import pytest


def _tiktoken_available() -> bool:
    """Return True if tiktoken can load the cl100k_base BPE encoding."""
    try:
        import tiktoken  # noqa: PLC0415
        tiktoken.get_encoding("cl100k_base")
        return True
    except Exception:  # noqa: BLE001
        return False


_TIKTOKEN_AVAILABLE = _tiktoken_available()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip context-optimizer tests when tiktoken BPE data is unavailable."""
    if _TIKTOKEN_AVAILABLE:
        return

    skip = pytest.mark.skip(
        reason="tiktoken BPE data unavailable (requires network access to download)",
    )
    for item in items:
        if "context-optimizer" in str(item.fspath):
            item.add_marker(skip)
