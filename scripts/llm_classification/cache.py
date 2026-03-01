"""In-memory cache for LLM classification results."""

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.llm_classification.classifier import LLMClassificationResult


@dataclass
class CacheEntry:
    """A cached classification result with hit tracking."""

    result: LLMClassificationResult
    hit_count: int = 0


class ClassificationCache:
    """LRU cache for LLM classification results.

    Uses normalized fingerprints for fuzzy matching of similar comments.
    """

    def __init__(self, max_entries: int = 100) -> None:
        """Initialize cache with maximum entry limit."""
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_entries = max_entries

    def _normalize(self, text: str) -> str:
        """Normalize text for fingerprint generation.

        Removes variable content like commit hashes, line numbers, and
        normalizes whitespace.
        """
        normalized = text.lower()
        normalized = re.sub(r"[a-f0-9]{7,40}", "<hash>", normalized)
        normalized = re.sub(r"line\s*\d+", "line <N>", normalized)
        normalized = re.sub(r"#\d+", "#<N>", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _fingerprint(self, comment_body: str) -> str:
        """Generate a fingerprint for cache lookup."""
        normalized = self._normalize(comment_body)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def get(self, comment_body: str) -> LLMClassificationResult | None:
        """Look up a cached result. Returns None if not found."""
        key = self._fingerprint(comment_body)
        if key not in self._cache:
            return None

        entry = self._cache[key]
        entry.hit_count += 1
        self._cache.move_to_end(key)
        return entry.result

    def put(
        self, comment_body: str, result: LLMClassificationResult
    ) -> None:
        """Store a classification result in cache."""
        key = self._fingerprint(comment_body)

        if key in self._cache:
            self._cache[key].result = result
            self._cache.move_to_end(key)
            return

        if len(self._cache) >= self._max_entries:
            self._cache.popitem(last=False)

        self._cache[key] = CacheEntry(result=result)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def __len__(self) -> int:
        """Return number of cached entries."""
        return len(self._cache)
