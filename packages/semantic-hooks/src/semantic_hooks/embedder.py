"""Embedding abstraction for semantic similarity calculations."""

from abc import ABC, abstractmethod
from functools import lru_cache
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
        # Create cached version of _embed
        self._cached_embed = lru_cache(maxsize=cache_size)(self._embed_impl)

    def _embed_impl(self, text: str) -> tuple[float, ...]:
        """Internal embedding implementation (returns tuple for caching)."""
        response = self.client.embeddings.create(
            model=self.model,
            input=text,
        )
        return tuple(response.data[0].embedding)

    def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        return list(self._cached_embed(text))

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        # Check cache first
        results: list[list[float]] = []
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(texts):
            try:
                # Try to get from cache without calling API
                cached = self._cached_embed.__wrapped__(text)
                results.append(list(cached))
            except KeyError:
                uncached_indices.append(i)
                uncached_texts.append(text)
                results.append([])  # Placeholder

        # Batch fetch uncached
        if uncached_texts:
            response = self.client.embeddings.create(
                model=self.model,
                input=uncached_texts,
            )
            for idx, embedding_data in zip(uncached_indices, response.data):
                embedding = list(embedding_data.embedding)
                results[idx] = embedding
                # Manually cache
                self._cached_embed(texts[idx])

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
        weights: Optional custom weights (must sum to 1)

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
