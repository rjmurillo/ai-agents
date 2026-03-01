"""Semantic memory storage and retrieval."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import sqlite3
from typing import Any, TYPE_CHECKING

from semantic_hooks.core import (
    DEFAULT_ZONE_THRESHOLDS,
    ReasoningDirection,
    SemanticNode,
    SemanticZone,
    ZoneThresholds,
)
from semantic_hooks.embedder import Embedder, cosine_similarity

if TYPE_CHECKING:
    from semantic_hooks.embedder import OpenAIEmbedder


class SemanticMemory:
    """SQLite-backed semantic memory with optional Serena integration.

    Stores semantic nodes with embeddings for similarity search.
    """

    DEFAULT_PATH = Path.home() / ".semantic-hooks" / "memory.db"

    def __init__(
        self,
        db_path: Path | str | None = None,
        embedder: Embedder | None = None,
        serena_path: Path | str | None = None,
    ):
        """Initialize semantic memory.

        Args:
            db_path: Path to SQLite database (default: ~/.semantic-hooks/memory.db)
            embedder: Embedder for generating node embeddings
            serena_path: Optional path to Serena memory file for integration
        """
        self.db_path = Path(db_path) if db_path else self.DEFAULT_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self.serena_path = Path(serena_path) if serena_path else None

        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS semantic_nodes (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    delta_s REAL NOT NULL,
                    lambda_observe TEXT NOT NULL,
                    module_used TEXT NOT NULL,
                    insight TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    session_id TEXT,
                    project_id TEXT,
                    parent_id TEXT,
                    embedding BLOB,
                    metadata TEXT,
                    FOREIGN KEY (parent_id) REFERENCES semantic_nodes(id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session ON semantic_nodes(session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON semantic_nodes(timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_zone ON semantic_nodes(delta_s)
            """)
            conn.commit()

    def add_node(self, node: SemanticNode) -> None:
        """Add a semantic node to memory.

        Args:
            node: SemanticNode to store
        """
        # Generate embedding if embedder available and not already present
        if self.embedder and node.embedding is None:
            text = f"{node.topic}: {node.insight}"
            node.embedding = self.embedder.embed(text)

        embedding_blob = (
            json.dumps(node.embedding) if node.embedding else None
        )
        metadata_json = json.dumps(node.metadata) if node.metadata else None

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO semantic_nodes
                (id, topic, delta_s, lambda_observe, module_used, insight,
                 timestamp, session_id, project_id, parent_id, embedding, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node.id,
                    node.topic,
                    node.delta_s,
                    node.lambda_observe.value,
                    node.module_used,
                    node.insight,
                    node.timestamp.isoformat(),
                    node.session_id,
                    node.project_id,
                    node.parent_id,
                    embedding_blob,
                    metadata_json,
                ),
            )
            conn.commit()

    def get_recent(
        self,
        n: int = 10,
        session_id: str | None = None,
        include_embeddings: bool = True,
    ) -> list[SemanticNode]:
        """Get most recent semantic nodes.

        Args:
            n: Maximum number of nodes to return
            session_id: Filter by session (None = all sessions)
            include_embeddings: Whether to load embedding vectors

        Returns:
            List of SemanticNode ordered by timestamp descending
        """
        query = "SELECT * FROM semantic_nodes"
        params: list[Any] = []

        if session_id:
            query += " WHERE session_id = ?"
            params.append(session_id)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(n)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        return [self._row_to_node(row, include_embeddings) for row in rows]

    def get_by_zone(
        self,
        zone: SemanticZone,
        limit: int = 50,
        thresholds: ZoneThresholds | None = None,
    ) -> list[SemanticNode]:
        """Get nodes by semantic zone.

        Args:
            zone: Target zone
            limit: Maximum nodes to return
            thresholds: Optional custom thresholds (uses defaults if None)

        Returns:
            Nodes within the specified zone
        """
        if thresholds is None:
            thresholds = DEFAULT_ZONE_THRESHOLDS

        zone_ranges = {
            SemanticZone.SAFE: (0.0, thresholds.safe),
            SemanticZone.TRANSITIONAL: (thresholds.safe, thresholds.transitional),
            SemanticZone.RISK: (thresholds.transitional, thresholds.risk),
            SemanticZone.DANGER: (thresholds.risk, 2.0),
        }
        min_ds, max_ds = zone_ranges[zone]

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM semantic_nodes
                WHERE delta_s >= ? AND delta_s < ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (min_ds, max_ds, limit),
            )
            rows = cursor.fetchall()

        return [self._row_to_node(row) for row in rows]

    def find_similar(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        min_similarity: float = 0.5,
    ) -> list[tuple[SemanticNode, float]]:
        """Find nodes similar to query embedding.

        Args:
            query_embedding: Query vector
            top_k: Number of results
            min_similarity: Minimum cosine similarity threshold

        Returns:
            List of (node, similarity) tuples sorted by similarity descending
        """
        # Load all nodes with embeddings (TODO: optimize with vector index)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM semantic_nodes WHERE embedding IS NOT NULL"
            )
            rows = cursor.fetchall()

        results: list[tuple[SemanticNode, float]] = []
        for row in rows:
            node = self._row_to_node(row, include_embeddings=True)
            if node.embedding:
                sim = cosine_similarity(query_embedding, node.embedding)
                if sim >= min_similarity:
                    results.append((node, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def find_bridge(
        self,
        current_topic: str,
        target_topic: str,
        top_k: int = 3,
    ) -> list[SemanticNode]:
        """Find bridge topics connecting current to target.

        Searches for nodes semantically between current and target topics.

        Args:
            current_topic: Current reasoning topic
            target_topic: Target topic to reach
            top_k: Number of bridge candidates

        Returns:
            Nodes that could serve as conceptual bridges
        """
        if not self.embedder:
            return []

        # Get embeddings for current and target
        current_emb = self.embedder.embed(current_topic)
        target_emb = self.embedder.embed(target_topic)

        # Midpoint embedding
        import numpy as np

        midpoint = ((np.array(current_emb) + np.array(target_emb)) / 2).tolist()

        # Find nodes near midpoint
        similar = self.find_similar(midpoint, top_k=top_k * 2, min_similarity=0.3)

        # Filter: must be closer to midpoint than to either endpoint
        bridges: list[SemanticNode] = []
        for node, sim_to_mid in similar:
            if node.embedding:
                sim_to_current = cosine_similarity(node.embedding, current_emb)
                sim_to_target = cosine_similarity(node.embedding, target_emb)
                # Good bridge: similar to midpoint, between current and target
                if sim_to_mid > max(sim_to_current, sim_to_target) * 0.8:
                    bridges.append(node)
                    if len(bridges) >= top_k:
                        break

        return bridges

    def get_session_tree(self, session_id: str) -> list[SemanticNode]:
        """Get all nodes for a session in tree order.

        Args:
            session_id: Session identifier

        Returns:
            Nodes ordered by timestamp
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM semantic_nodes
                WHERE session_id = ?
                ORDER BY timestamp ASC
                """,
                (session_id,),
            )
            rows = cursor.fetchall()

        return [self._row_to_node(row) for row in rows]

    def export_tree(self, session_id: str | None = None) -> dict[str, Any]:
        """Export semantic tree as JSON-serializable dict.

        Args:
            session_id: Optional filter by session

        Returns:
            Tree structure with nodes and metadata, nodes ordered chronologically
        """
        if session_id:
            nodes = self.get_session_tree(session_id)
        else:
            nodes = self.get_recent(n=1000, include_embeddings=False)
            nodes = list(reversed(nodes))

        return {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "session_id": session_id,
            "node_count": len(nodes),
            "nodes": [n.to_dict() for n in nodes],
            "zone_summary": self._compute_zone_summary(nodes),
        }

    def import_from_serena(self) -> int:
        """Import memories from Serena if available.

        Returns:
            Number of nodes imported
        """
        if not self.serena_path or not self.serena_path.exists():
            return 0

        # TODO: Implement Serena memory format parsing
        # This depends on Serena's actual memory structure
        return 0

    def _row_to_node(
        self,
        row: sqlite3.Row,
        include_embeddings: bool = False,
    ) -> SemanticNode:
        """Convert database row to SemanticNode."""
        embedding = None
        if include_embeddings and row["embedding"]:
            raw = row["embedding"]
            # Handle bytes from legacy storage (pre-fix data stored via .encode())
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            embedding = json.loads(raw)

        metadata = {}
        if row["metadata"]:
            raw_meta = row["metadata"]
            if isinstance(raw_meta, bytes):
                raw_meta = raw_meta.decode("utf-8")
            metadata = json.loads(raw_meta)

        return SemanticNode(
            id=row["id"],
            topic=row["topic"],
            delta_s=row["delta_s"],
            lambda_observe=ReasoningDirection(row["lambda_observe"]),
            module_used=row["module_used"],
            insight=row["insight"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            session_id=row["session_id"] or "",
            project_id=row["project_id"] or "",
            parent_id=row["parent_id"],
            embedding=embedding,
            metadata=metadata,
        )

    def _compute_zone_summary(
        self,
        nodes: list[SemanticNode],
    ) -> dict[str, int]:
        """Compute zone distribution summary."""
        summary = {z.value: 0 for z in SemanticZone}
        for node in nodes:
            summary[node.zone.value] += 1
        return summary


def load_config_and_create_memory(
    config_path: str | None = None,
) -> tuple[dict[str, Any], OpenAIEmbedder, SemanticMemory]:
    """Load config file and create embedder and memory instances.

    This is a shared helper for factory functions in guards and recorder modules.

    Args:
        config_path: Path to YAML config (default: ~/.semantic-hooks/config.yaml)

    Returns:
        Tuple of (config_dict, embedder, memory)
    """
    import yaml

    from semantic_hooks.embedder import OpenAIEmbedder

    config_file = Path(config_path) if config_path else (
        Path.home() / ".semantic-hooks" / "config.yaml"
    )

    cfg: dict[str, Any] = {}
    embedder_kwargs: dict[str, Any] = {}

    if config_file.exists():
        with open(config_file) as f:
            cfg = yaml.safe_load(f) or {}

        if "embedding" in cfg:
            e = cfg["embedding"]
            embedder_kwargs["model"] = e.get("model", "text-embedding-3-small")

    embedder = OpenAIEmbedder(**embedder_kwargs)
    memory = SemanticMemory(embedder=embedder)

    return cfg, embedder, memory
