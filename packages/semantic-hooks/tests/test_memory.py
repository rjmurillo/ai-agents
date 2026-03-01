"""Tests for semantic memory storage and retrieval."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from semantic_hooks.core import ReasoningDirection, SemanticNode
from semantic_hooks.memory import SemanticMemory


@pytest.fixture
def temp_db():
    """Create a temporary database path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_memory.db"


class TestSemanticMemoryRoundtrip:
    """Tests for SQLite serialization roundtrip correctness."""

    def test_node_without_embedding_roundtrips(self, temp_db):
        """Node without embedding should store and retrieve correctly."""
        memory = SemanticMemory(db_path=temp_db)
        node = SemanticNode(
            topic="test topic",
            delta_s=0.5,
            lambda_observe=ReasoningDirection.CONVERGENT,
            module_used="bash",
            insight="test insight",
            timestamp=datetime(2026, 1, 15, 12, 0, 0),
            session_id="sess-001",
        )
        memory.add_node(node)

        retrieved = memory.get_recent(n=1, include_embeddings=False)
        assert len(retrieved) == 1
        assert retrieved[0].topic == "test topic"
        assert retrieved[0].delta_s == 0.5
        assert retrieved[0].lambda_observe == ReasoningDirection.CONVERGENT
        assert retrieved[0].session_id == "sess-001"

    def test_node_with_embedding_roundtrips(self, temp_db):
        """Node with embedding should store and retrieve embedding correctly."""
        memory = SemanticMemory(db_path=temp_db)
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        node = SemanticNode(
            topic="embedding test",
            delta_s=0.3,
            lambda_observe=ReasoningDirection.DIVERGENT,
            module_used="read",
            insight="has embedding",
            embedding=embedding,
        )
        memory.add_node(node)

        retrieved = memory.get_recent(n=1, include_embeddings=True)
        assert len(retrieved) == 1
        assert retrieved[0].embedding is not None
        assert retrieved[0].embedding == pytest.approx(embedding)

    def test_node_with_metadata_roundtrips(self, temp_db):
        """Node with metadata dict should serialize and deserialize."""
        memory = SemanticMemory(db_path=temp_db)
        metadata = {"exit_code": 0, "working_directory": "/home/user"}
        node = SemanticNode(
            topic="metadata test",
            delta_s=0.1,
            lambda_observe=ReasoningDirection.RECURSIVE,
            module_used="grep",
            insight="has metadata",
            metadata=metadata,
        )
        memory.add_node(node)

        retrieved = memory.get_recent(n=1, include_embeddings=False)
        assert len(retrieved) == 1
        assert retrieved[0].metadata == metadata

    def test_find_similar_with_stored_embeddings(self, temp_db):
        """find_similar should work with stored embeddings."""
        memory = SemanticMemory(db_path=temp_db)

        # Store two nodes with different embeddings
        node_a = SemanticNode(
            topic="topic A",
            delta_s=0.2,
            lambda_observe=ReasoningDirection.CONVERGENT,
            module_used="test",
            insight="insight A",
            embedding=[1.0, 0.0, 0.0],
        )
        node_b = SemanticNode(
            topic="topic B",
            delta_s=0.3,
            lambda_observe=ReasoningDirection.CONVERGENT,
            module_used="test",
            insight="insight B",
            embedding=[0.0, 1.0, 0.0],
        )
        memory.add_node(node_a)
        memory.add_node(node_b)

        # Query similar to node_a's embedding
        results = memory.find_similar([1.0, 0.0, 0.0], top_k=2, min_similarity=0.0)
        assert len(results) == 2
        # First result should be most similar to query
        assert results[0][0].topic == "topic A"
        assert results[0][1] == pytest.approx(1.0)

    def test_get_recent_respects_session_filter(self, temp_db):
        """get_recent should filter by session_id when provided."""
        memory = SemanticMemory(db_path=temp_db)

        for i, sess in enumerate(["sess-1", "sess-1", "sess-2"]):
            node = SemanticNode(
                topic=f"topic {i}",
                delta_s=0.1 * i,
                lambda_observe=ReasoningDirection.CONVERGENT,
                module_used="test",
                insight=f"insight {i}",
                session_id=sess,
            )
            memory.add_node(node)

        sess1_nodes = memory.get_recent(n=10, session_id="sess-1")
        assert len(sess1_nodes) == 2

        sess2_nodes = memory.get_recent(n=10, session_id="sess-2")
        assert len(sess2_nodes) == 1

    def test_legacy_bytes_embedding_still_loads(self, temp_db):
        """Data stored as bytes (legacy format) should load with decode fallback."""
        import sqlite3

        memory = SemanticMemory(db_path=temp_db)

        # Simulate legacy storage: embedding stored as bytes via .encode()
        embedding = [0.1, 0.2, 0.3]
        embedding_blob = json.dumps(embedding).encode("utf-8")

        with sqlite3.connect(temp_db) as conn:
            conn.execute(
                """
                INSERT INTO semantic_nodes
                (id, topic, delta_s, lambda_observe, module_used, insight,
                 timestamp, session_id, project_id, parent_id, embedding, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-node-1",
                    "legacy topic",
                    0.4,
                    "->",
                    "test",
                    "legacy insight",
                    "2026-01-01T00:00:00",
                    "sess-legacy",
                    "",
                    None,
                    embedding_blob,
                    None,
                ),
            )
            conn.commit()

        # Verify the legacy bytes data can be read back
        retrieved = memory.get_recent(
            n=1, session_id="sess-legacy", include_embeddings=True
        )
        assert len(retrieved) == 1
        assert retrieved[0].embedding == pytest.approx(embedding)
