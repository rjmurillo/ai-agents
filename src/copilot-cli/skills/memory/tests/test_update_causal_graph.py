#!/usr/bin/env python3
"""Tests for update_causal_graph.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ..scripts.update_causal_graph import (
    add_causal_edge,
    add_causal_node,
    add_pattern,
    build_causal_chains,
    generate_node_id,
    get_decision_patterns,
    get_episode_files,
    load_causal_graph,
    main,
    save_causal_graph,
)


class TestGenerateNodeId:
    """Tests for node ID generation."""

    def test_deterministic(self) -> None:
        id1 = generate_node_id("decision", "use Python")
        id2 = generate_node_id("decision", "use Python")
        assert id1 == id2

    def test_different_inputs(self) -> None:
        id1 = generate_node_id("decision", "use Python")
        id2 = generate_node_id("event", "use Python")
        assert id1 != id2

    def test_length(self) -> None:
        node_id = generate_node_id("test", "label")
        assert len(node_id) == 12


class TestLoadCausalGraph:
    """Tests for loading causal graph."""

    def test_missing_file(self, tmp_path: Path) -> None:
        graph = load_causal_graph(tmp_path / "missing.json")
        assert graph == {"nodes": [], "edges": [], "patterns": []}

    def test_valid_file(self, tmp_path: Path) -> None:
        graph_file = tmp_path / "graph.json"
        data = {"nodes": [{"id": "abc"}], "edges": [], "patterns": []}
        graph_file.write_text(json.dumps(data), encoding="utf-8")

        graph = load_causal_graph(graph_file)
        assert len(graph["nodes"]) == 1

    def test_invalid_json(self, tmp_path: Path) -> None:
        graph_file = tmp_path / "graph.json"
        graph_file.write_text("not json", encoding="utf-8")

        graph = load_causal_graph(graph_file)
        assert graph == {"nodes": [], "edges": [], "patterns": []}


class TestSaveCausalGraph:
    """Tests for saving causal graph."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        graph_file = tmp_path / "sub" / "graph.json"
        save_causal_graph(graph_file, {"nodes": [], "edges": [], "patterns": []})
        assert graph_file.is_file()

    def test_content_roundtrip(self, tmp_path: Path) -> None:
        graph_file = tmp_path / "graph.json"
        data = {"nodes": [{"id": "test"}], "edges": [], "patterns": []}
        save_causal_graph(graph_file, data)

        loaded = json.loads(graph_file.read_text(encoding="utf-8"))
        assert loaded["nodes"][0]["id"] == "test"


class TestAddCausalNode:
    """Tests for adding nodes."""

    def test_add_new_node(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        node = add_causal_node(graph, "decision", "test label", "ep-001")
        assert node is not None
        assert node["type"] == "decision"
        assert len(graph["nodes"]) == 1

    def test_duplicate_updates_episodes(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_causal_node(graph, "decision", "test label", "ep-001")
        node = add_causal_node(graph, "decision", "test label", "ep-002")
        assert len(graph["nodes"]) == 1
        assert node is not None
        assert "ep-002" in node["episodes"]


class TestAddCausalEdge:
    """Tests for adding edges."""

    def test_add_new_edge(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        edge = add_causal_edge(graph, "src", "tgt", "causes", 0.8, "ep-001")
        assert edge is not None
        assert edge["weight"] == 0.8
        assert edge["evidence_count"] == 1
        assert edge["episodes"] == ["ep-001"]
        assert len(graph["edges"]) == 1

    def test_duplicate_averages_weight(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_causal_edge(graph, "src", "tgt", "causes", 0.8, "ep-001")
        edge = add_causal_edge(graph, "src", "tgt", "causes", 0.6, "ep-002")
        assert len(graph["edges"]) == 1
        assert edge is not None
        assert edge["weight"] == 0.7
        assert edge["evidence_count"] == 2

    def test_same_episode_reprocess_is_noop(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_causal_edge(graph, "src", "tgt", "causes", 0.8, "ep-001")
        assert add_causal_edge(graph, "src", "tgt", "causes", 0.8, "ep-001") is None
        assert graph["edges"][0]["evidence_count"] == 1


class TestAddPattern:
    """Tests for adding patterns."""

    def test_add_new_pattern(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        pat = add_pattern(graph, "test", "desc", "trigger", "action", 1.0, "ep-001")
        assert pat is not None
        assert pat["occurrences"] == 1
        assert pat["episodes"] == ["ep-001"]

    def test_duplicate_updates_rate(self) -> None:
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_pattern(graph, "test", "desc", "trigger", "action", 1.0, "ep-001")
        pat = add_pattern(graph, "test", "desc", "trigger", "action", 0.0, "ep-002")
        assert len(graph["patterns"]) == 1
        assert pat is not None
        assert pat["success_rate"] == 0.5
        assert pat["occurrences"] == 2

    def test_running_average_is_occurrence_weighted(self) -> None:
        # 1.0, 1.0, 0.0 must average to 0.67, not 0.50 (#3034 review).
        graph: dict[str, Any] = {"nodes": [], "edges": [], "patterns": []}
        add_pattern(graph, "test", "desc", "trigger", "action", 1.0, "ep-001")
        add_pattern(graph, "test", "desc", "trigger", "action", 1.0, "ep-002")
        add_pattern(graph, "test", "desc", "trigger", "action", 0.0, "ep-003")
        pat = graph["patterns"][0]
        assert pat["occurrences"] == 3
        assert pat["success_rate"] == 0.67


class TestGetEpisodeFiles:
    """Tests for episode file discovery."""

    def test_single_file(self, tmp_path: Path) -> None:
        f = tmp_path / "episode-test.json"
        f.write_text(
            json.dumps({"id": "test", "timestamp": "2026-01-01T00:00:00"}),
            encoding="utf-8",
        )
        assert get_episode_files(f) == [f]

    def test_directory(self, tmp_path: Path) -> None:
        (tmp_path / "episode-001.json").write_text("{}", encoding="utf-8")
        (tmp_path / "episode-002.json").write_text("{}", encoding="utf-8")
        (tmp_path / "other.json").write_text("{}", encoding="utf-8")
        files = get_episode_files(tmp_path)
        assert len(files) == 2

    def test_missing_path(self, tmp_path: Path) -> None:
        assert get_episode_files(tmp_path / "missing") == []


class TestGetDecisionPatterns:
    """Tests for decision pattern extraction."""

    def test_success_pattern(self) -> None:
        episode = {
            "id": "ep-001",
            "decisions": [{
                "type": "design",
                "chosen": "Use Python for migration",
                "outcome": "success",
                "context": "Migration planning",
            }],
        }
        patterns = get_decision_patterns(episode)
        assert len(patterns) == 1
        assert patterns[0]["success"] is True
        assert "design" in patterns[0]["name"]

    def test_failure_anti_pattern(self) -> None:
        episode = {
            "id": "ep-001",
            "decisions": [{
                "type": "test",
                "chosen": "Skip unit tests",
                "outcome": "failure",
                "context": "Time pressure",
            }],
        }
        patterns = get_decision_patterns(episode)
        assert len(patterns) == 1
        assert patterns[0]["success"] is False
        assert "AVOID" in patterns[0]["action"]


class TestBuildCausalChains:
    """Tests for causal chain building."""

    def test_error_recovery_chain(self) -> None:
        episode = {
            "events": [
                {"type": "error", "content": "Build failed"},
                {"type": "milestone", "content": "Fixed build configuration"},
            ],
            "decisions": [],
        }
        chains = build_causal_chains(episode)
        assert len(chains) >= 1
        assert chains[0]["edge_type"] == "causes"

    def test_no_chains_without_errors(self) -> None:
        episode = {
            "events": [
                {"type": "milestone", "content": "Completed task"},
            ],
            "decisions": [],
        }
        chains = build_causal_chains(episode)
        assert len(chains) == 0


class TestMainFunction:
    """Tests for the main CLI entry point."""

    def test_no_episodes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()
        graph_file = tmp_path / "graph.json"

        result = main([
            "--episode-path", str(ep_dir),
            "--graph-path", str(graph_file),
        ])
        assert result == 0

    def test_processes_episode(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()
        graph_file = tmp_path / "graph.json"

        episode = {
            "id": "episode-test",
            "timestamp": "2026-01-01T00:00:00",
            "outcome": "success",
            "task": "Test task",
            "decisions": [{
                "type": "design",
                "chosen": "Use Python",
                "outcome": "success",
                "context": "Planning",
            }],
            "events": [],
            "lessons": [],
        }
        (ep_dir / "episode-test.json").write_text(json.dumps(episode), encoding="utf-8")

        result = main([
            "--episode-path", str(ep_dir),
            "--graph-path", str(graph_file),
        ])
        assert result == 0

        captured = capsys.readouterr()
        stats = json.loads(captured.out)
        assert stats["episodes_processed"] == 1
        assert stats["nodes_added"] > 0

        graph = json.loads(graph_file.read_text(encoding="utf-8"))
        assert len(graph["nodes"]) > 0

    def test_dry_run(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()
        graph_file = tmp_path / "graph.json"

        episode = {
            "id": "episode-dry",
            "timestamp": "2026-01-01T00:00:00",
            "outcome": "success",
            "task": "Dry run test",
            "decisions": [{
                "type": "test",
                "chosen": "Write unit tests",
                "outcome": "success",
            }],
            "events": [],
        }
        (ep_dir / "episode-dry.json").write_text(json.dumps(episode), encoding="utf-8")

        result = main([
            "--episode-path", str(ep_dir),
            "--graph-path", str(graph_file),
            "--dry-run",
        ])
        assert result == 0
        assert not graph_file.exists()


class TestEpisodeReconcile:
    """Reprocess-idempotency for an edited episode (regression for #3143).

    #3143: a failed pre-commit retry reprocessed an episode whose milestone
    label had been corrected. The old content-derived node was left behind, so
    the committed graph held two nodes for the same episode. The reconcile path
    (#3058) must retract the stale node while preserving nodes still supported
    by other episodes.
    """

    @staticmethod
    def _milestone_episode(chosen: str) -> dict[str, Any]:
        return {
            "id": "episode-2026-07-16-session-3056-record",
            "timestamp": "2026-07-16T00:00:00",
            "outcome": "success",
            "task": "Milestone record",
            "decisions": [{
                "type": "milestone",
                "chosen": chosen,
                "outcome": "success",
                "context": "record",
            }],
            "events": [],
            "lessons": [],
        }

    def test_reprocess_changed_decision_retracts_stale_node(
        self, tmp_path: Path,
    ) -> None:
        """A corrected milestone leaves exactly one milestone node (AC1, AC4)."""
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()
        graph_file = tmp_path / "graph.json"
        ep_file = ep_dir / "episode-2026-07-16-session-3056-record.json"

        ep_file.write_text(json.dumps(
            self._milestone_episode("filed #3137, #3138, #3139, #3140, and #3141"),
        ), encoding="utf-8")
        assert main([
            "--episode-path", str(ep_file),
            "--graph-path", str(graph_file),
        ]) == 0

        # Correct the milestone (same episode id, new content-derived node id).
        ep_file.write_text(json.dumps(
            self._milestone_episode(
                "filed #3137, #3138, #3139, #3140, #3141, and #3142",
            ),
        ), encoding="utf-8")
        assert main([
            "--episode-path", str(ep_file),
            "--graph-path", str(graph_file),
        ]) == 0

        graph = json.loads(graph_file.read_text(encoding="utf-8"))
        milestone_nodes = [
            n for n in graph["nodes"] if n["label"].startswith("milestone:")
        ]
        assert len(milestone_nodes) == 1
        assert "#3142" in milestone_nodes[0]["label"]
        # The pre-correction node must be gone, not merely deduplicated.
        assert not any(
            n["label"].startswith("milestone:") and "#3142" not in n["label"]
            for n in graph["nodes"]
        )

    def test_reprocess_preserves_node_shared_with_other_episode(
        self, tmp_path: Path,
    ) -> None:
        """Retracting one episode keeps a node another episode still supports (AC6)."""
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()
        graph_file = tmp_path / "graph.json"

        def design_episode(episode_id: str, chosen: list[str]) -> dict[str, Any]:
            return {
                "id": episode_id,
                "timestamp": "2026-07-16T00:00:00",
                "outcome": "success",
                "task": "Design work",
                "decisions": [
                    {"type": "design", "chosen": c, "outcome": "success"}
                    for c in chosen
                ],
                "events": [],
                "lessons": [],
            }

        ep1 = ep_dir / "episode-one.json"
        ep2 = ep_dir / "episode-two.json"
        ep1.write_text(
            json.dumps(design_episode("episode-one", ["SHARED", "ONLY1"])),
            encoding="utf-8",
        )
        ep2.write_text(json.dumps(design_episode("episode-two", ["SHARED"])), encoding="utf-8")
        assert main([
            "--episode-path", str(ep_dir),
            "--graph-path", str(graph_file),
        ]) == 0

        graph = json.loads(graph_file.read_text(encoding="utf-8"))
        shared = next(n for n in graph["nodes"] if n["label"] == "design: SHARED")
        assert set(shared["episodes"]) == {"episode-one", "episode-two"}

        # Reprocess only episode-one, dropping both SHARED and ONLY1.
        ep1.write_text(
            json.dumps(design_episode("episode-one", ["ONLY1-CHANGED"])),
            encoding="utf-8",
        )
        assert main([
            "--episode-path", str(ep1),
            "--graph-path", str(graph_file),
        ]) == 0

        graph = json.loads(graph_file.read_text(encoding="utf-8"))
        labels = {n["label"]: n for n in graph["nodes"]}
        # Shared node survives, now supported only by episode-two.
        assert "design: SHARED" in labels
        assert labels["design: SHARED"]["episodes"] == ["episode-two"]
        # Episode-one's dropped sole-supporter node is retracted.
        assert "design: ONLY1" not in labels
        assert "design: ONLY1-CHANGED" in labels

    def test_unchanged_reprocess_is_byte_idempotent(
        self, tmp_path: Path,
    ) -> None:
        """Reprocessing an unchanged episode changes no bytes (AC2)."""
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()
        graph_file = tmp_path / "graph.json"
        ep_file = ep_dir / "episode-2026-07-16-session-3056-record.json"
        ep_file.write_text(json.dumps(self._milestone_episode("filed #3141")), encoding="utf-8")

        assert main([
            "--episode-path", str(ep_file), "--graph-path", str(graph_file),
        ]) == 0
        first = graph_file.read_text(encoding="utf-8")

        assert main([
            "--episode-path", str(ep_file), "--graph-path", str(graph_file),
        ]) == 0
        assert graph_file.read_text(encoding="utf-8") == first
