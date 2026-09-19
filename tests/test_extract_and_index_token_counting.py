"""Token counting tests for the context extractor."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from extract_and_index import count_tokens


def _has_tiktoken_encoding() -> bool:
    """Return True when cl100k_base can be loaded without network errors."""
    try:
        import tiktoken

        tiktoken.get_encoding("cl100k_base").encode("probe")
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _has_tiktoken_encoding(),
    reason="cl100k_base tokenizer data unavailable in offline environment",
)
class TestTokenCounting:
    def test_count_tokens_nonempty(self):
        tokens = count_tokens("Hello world")
        assert tokens > 0

    def test_count_tokens_empty(self):
        assert count_tokens("") == 0


def test_count_tokens_reports_missing_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "tiktoken", None)

    with pytest.raises(RuntimeError, match="tiktoken library not installed"):
        count_tokens("Hello world")
