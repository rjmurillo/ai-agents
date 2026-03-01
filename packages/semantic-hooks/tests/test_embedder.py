"""Tests for embedder module."""

import pytest

from semantic_hooks.embedder import (
    cosine_similarity,
    semantic_tension,
    compute_trajectory_embedding,
)


class TestCosineSimilarity:
    """Tests for cosine similarity calculation."""

    def test_identical_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [-1.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector(self):
        a = [1.0, 2.0, 3.0]
        b = [0.0, 0.0, 0.0]
        assert cosine_similarity(a, b) == 0.0


class TestSemanticTension:
    """Tests for semantic tension (ΔS) calculation."""

    def test_identical_embeddings(self):
        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        # ΔS = 1 - cos_sim = 1 - 1 = 0
        assert semantic_tension(a, b) == pytest.approx(0.0)

    def test_orthogonal_embeddings(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        # ΔS = 1 - cos_sim = 1 - 0 = 1
        assert semantic_tension(a, b) == pytest.approx(1.0)

    def test_opposite_embeddings(self):
        a = [1.0, 0.0, 0.0]
        b = [-1.0, 0.0, 0.0]
        # ΔS = 1 - cos_sim = 1 - (-1) = 2
        assert semantic_tension(a, b) == pytest.approx(2.0)

    def test_partial_similarity(self):
        a = [1.0, 1.0, 0.0]
        b = [1.0, 0.0, 0.0]
        # cos_sim = 1/sqrt(2) ≈ 0.707
        # ΔS ≈ 0.293
        assert 0.2 < semantic_tension(a, b) < 0.4


class TestTrajectoryEmbedding:
    """Tests for trajectory embedding computation."""

    def test_single_embedding(self):
        embeddings = [[1.0, 2.0, 3.0]]
        result = compute_trajectory_embedding(embeddings)
        assert result == pytest.approx([1.0, 2.0, 3.0])

    def test_uniform_embeddings(self):
        embeddings = [
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
        ]
        result = compute_trajectory_embedding(embeddings)
        assert result == pytest.approx([1.0, 0.0, 0.0])

    def test_recency_weighting(self):
        # Most recent (last) should have highest weight
        embeddings = [
            [1.0, 0.0, 0.0],  # oldest
            [0.0, 1.0, 0.0],  # newest
        ]
        result = compute_trajectory_embedding(embeddings)
        # With decay=0.7, weights are [0.7, 1.0] normalized
        # Result should be biased toward [0, 1, 0]
        assert result[1] > result[0]

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            compute_trajectory_embedding([])

    def test_custom_weights(self):
        embeddings = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ]
        weights = [0.25, 0.75]
        result = compute_trajectory_embedding(embeddings, weights=weights)
        assert result == pytest.approx([0.25, 0.75, 0.0])
