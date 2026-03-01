"""Embedding abstraction for semantic similarity calculations."""

from abc import ABC, abstractmethod
from collections import OrderedDict
import numpy as np
from numpy.typing import NDArray


class Embedder(ABC):
    """Abstract base class for text embedding providers."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        pass

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        pass

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the dimensionality of embeddings."""
        pass


class OpenAIEmbedder(Embedder):
    """OpenAI text-embedding-3-small embedder."""

    DEFAULT_MODEL = "text-embedding-3-small"
    DIMENSIONS = 1536

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        cache_size: int = 1000,
    ):
        """Initialize OpenAI embedder.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Model name (default: text-embedding-3-small)
            cache_size: LRU cache size for embeddings
        """
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)
        self.model = model
        self._cache_size = cache_size
        # Manual cache dict to allow checking membership without API calls
        self._cache: OrderedDict[str, tuple[float, ...]] = OrderedDict()

    def _embed_impl(self, text: str) -> tuple[float, ...]:
        """Internal embedding implementation (returns tuple for caching)."""
        response = self.client.embeddings.create(
            model=self.model,
            input=text,
        )
        return tuple(response.data[0].embedding)

    def _add_to_cache(self, key: str, value: tuple[float, ...]) -> None:
        """Add entry to cache, evicting oldest if at capacity."""
        if key in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return
        if len(self._cache) >= self._cache_size:
            # Remove oldest entry
            self._cache.popitem(last=False)
        self._cache[key] = value

    def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        if text in self._cache:
            # Update LRU position on cache hit
            self._cache.move_to_end(text)
            return list(self._cache[text])
        result = self._embed_impl(text)
        self._add_to_cache(text, result)
        return list(result)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        results: list[list[float]] = [[] for _ in texts]
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(texts):
            if text in self._cache:
                # Cache hit - update LRU position and use cached result
                self._cache.move_to_end(text)
                results[i] = list(self._cache[text])
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        # Batch fetch uncached texts with single API call
        if uncached_texts:
            response = self.client.embeddings.create(
                model=self.model,
                input=uncached_texts,
            )
            for embedding_data in response.data:
                # Use the index field to map back to the correct input position
                batch_idx = embedding_data.index
                original_idx = uncached_indices[batch_idx]
                embedding = tuple(embedding_data.embedding)
                results[original_idx] = list(embedding)
                # Add to cache using the original text
                self._add_to_cache(texts[original_idx], embedding)

        return results

    @property
    def dimensions(self) -> int:
        """Return the dimensionality of embeddings."""
        return self.DIMENSIONS


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors.

    Args:
        a: First embedding vector
        b: Second embedding vector

    Returns:
        Cosine similarity in range [-1, 1]
    """
    a_np: NDArray[np.float64] = np.array(a, dtype=np.float64)
    b_np: NDArray[np.float64] = np.array(b, dtype=np.float64)

    dot_product = np.dot(a_np, b_np)
    norm_a = np.linalg.norm(a_np)
    norm_b = np.linalg.norm(b_np)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot_product / (norm_a * norm_b))


def semantic_tension(current: list[float], expected: list[float]) -> float:
    """Calculate semantic tension (ΔS) between current and expected embeddings.

    ΔS = 1 - cosine_similarity(current, expected)

    Args:
        current: Current context embedding
        expected: Expected trajectory embedding

    Returns:
        Semantic tension in range [0, 2], where:
        - 0 = identical direction
        - 1 = orthogonal
        - 2 = opposite direction
    """
    return 1.0 - cosine_similarity(current, expected)


def compute_trajectory_embedding(
    embeddings: list[list[float]],
    weights: list[float] | None = None,
) -> list[float]:
    """Compute expected trajectory from recent embeddings.

    Uses exponential decay weighting by default (recent = higher weight).

    Args:
        embeddings: List of recent embedding vectors (oldest first)
        weights: Optional custom weights (relative, not required to sum to 1)

    Returns:
        Weighted average embedding representing expected trajectory
    """
    if not embeddings:
        raise ValueError("At least one embedding required")

    n = len(embeddings)

    if weights is None:
        # Exponential decay: more recent = higher weight
        decay = 0.7
        raw_weights = [decay ** (n - 1 - i) for i in range(n)]
        total = sum(raw_weights)
        weights = [w / total for w in raw_weights]

    if len(weights) != n:
        raise ValueError(f"Weights length {len(weights)} != embeddings length {n}")

    embeddings_np: NDArray[np.float64] = np.array(embeddings, dtype=np.float64)
    weights_np: NDArray[np.float64] = np.array(weights, dtype=np.float64).reshape(-1, 1)

    weighted_sum: NDArray[np.float64] = np.sum(embeddings_np * weights_np, axis=0)

    return weighted_sum.tolist()
