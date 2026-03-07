"""
conftest.py for context-optimizer tests.

Skips tests in test_compress_markdown_content.py when tiktoken's BPE data cannot
be loaded (e.g., in network-restricted environments where
openaipublic.blob.core.windows.net is unreachable). Only tests that call
compress_markdown_content.py require tiktoken for token count metrics.

Other test modules (test_analyze_skill_placement.py, test_skill_passive_compliance_test.py)
do not depend on tiktoken and should run regardless of network availability.
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
    """Skip tiktoken-dependent tests when tiktoken BPE data is unavailable."""
    if _TIKTOKEN_AVAILABLE:
        return

    skip = pytest.mark.skip(
        reason="tiktoken BPE data unavailable (requires network access to download)",
    )
    for item in items:
        if "test_compress_markdown_content.py" in str(item.fspath):
            item.add_marker(skip)
