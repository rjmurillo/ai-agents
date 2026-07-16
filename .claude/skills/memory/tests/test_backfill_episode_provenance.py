#!/usr/bin/env python3
"""Tests for backfill_episode_provenance.py.

Uses synthetic episode + graph fixtures (never the live corpus) so the tests do
not rot when real episodes change. The fixture edge key and pattern name are
derived through update_causal_graph's own public functions, so the fixtures stay
byte-identical to what the generator would produce.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..scripts.backfill_episode_provenance import (
    backfill_graph,
    derive_attribution,
    main,
)
from ..scripts.update_causal_graph import (
    build_causal_chains,
    generate_node_id,
    get_decision_patterns,
)

# An episode that yields exactly one error -> recovery chain (one edge) and one
# success decision pattern.
_EPISODE_A: dict[str, Any] = {
    "id": "episode-fixture-a",
    "timestamp": "2026-01-01T00:00:00+00:00",
    "task": "demo task",
    "outcome": "success",
    "decisions": [
        {
            "type": "design",
            "chosen": "adopt guard clause",
            "outcome": "success",
            "context": "when validating input",
        },
    ],
    "events": [
        {"type": "error", "content": "database timeout"},
        {"type": "milestone", "content": "resolve the timeout"},
    ],
}


def _edge_key(episode: dict[str, Any]) -> tuple[str, str]:
    chains = build_causal_chains(episode)
    assert len(chains) == 1, "fixture episode must yield exactly one chain"
    chain = chains[0]
    return (
        generate_node_id(chain["from_type"], chain["from_label"]),
        generate_node_id(chain["to_type"], chain["to_label"]),
    )


def _pattern_name(episode: dict[str, Any]) -> str:
    patterns = get_decision_patterns(episode)
    assert len(patterns) == 1, "fixture episode must yield exactly one pattern"
    return patterns[0]["name"]


def _write_episode(episodes_dir: Path, episode: dict[str, Any]) -> None:
    episodes_dir.mkdir(parents=True, exist_ok=True)
    (episodes_dir / f"{episode['id']}.json").write_text(
        json.dumps(episode), encoding="utf-8",
    )


def _legacy_graph(episode: dict[str, Any]) -> dict[str, Any]:
    """Graph with one legacy edge, one legacy pattern, one unattributable row."""
    source, target = _edge_key(episode)
    return {
        "nodes": [],
        "edges": [
            {
                "source": source,
                "target": target,
                "type": "causes",
                "weight": 0.8,
                "evidence_count": 42,
                "created": "2026-06-02T04:20:23.788737+00:00",
                "episodes": [],
            },
        ],
        "patterns": [
            {
                "name": _pattern_name(episode),
                "description": "",
                "trigger": "T",
                "action": "A",
                "success_rate": 1.0,
                "occurrences": 1,
                "created": "2026-06-02T04:20:23.788737+00:00",
            },
            {
                "id": "p999",
                "name": "Orphan seed pattern",
                "success_rate": 0.5,
                "occurrences": 3,
                "trigger": "T",
                "action": "A",
                "description": "",
                "episodes": [],
            },
        ],
    }


def _run(graph_path: Path, episodes_dir: Path, *extra: str) -> int:
    return main(
        ["--graph-path", str(graph_path), "--episode-path", str(episodes_dir), *extra],
    )


class TestDeriveAttribution:
    """Re-derivation maps items back to the episodes that reproduce them."""

    def test_edge_and_pattern_attributed(self, tmp_path: Path) -> None:
        episodes_dir = tmp_path / "episodes"
        _write_episode(episodes_dir, _EPISODE_A)

        edge_attr, pattern_attr = derive_attribution(
            sorted(episodes_dir.glob("episode-*.json")),
        )

        assert edge_attr[_edge_key(_EPISODE_A)] == {"episode-fixture-a"}
        assert pattern_attr[_pattern_name(_EPISODE_A)] == {"episode-fixture-a"}


class TestBackfillCli:
    """End-to-end backfill through the CLI entry point."""

    def test_legacy_edge_is_empty_before_backfill(self, tmp_path: Path) -> None:
        # Fails-before: the legacy edge has no provenance, indistinguishable
        # from an orphan the prune path could safely remove.
        graph = _legacy_graph(_EPISODE_A)
        assert graph["edges"][0]["episodes"] == []

    def test_legacy_edge_and_pattern_backfilled(self, tmp_path: Path) -> None:
        episodes_dir = tmp_path / "episodes"
        graph_path = tmp_path / "graph.json"
        _write_episode(episodes_dir, _EPISODE_A)
        graph_path.write_text(json.dumps(_legacy_graph(_EPISODE_A)), encoding="utf-8")

        assert _run(graph_path, episodes_dir) == 0

        result = json.loads(graph_path.read_text(encoding="utf-8"))
        assert result["edges"][0]["episodes"] == ["episode-fixture-a"]
        design = next(p for p in result["patterns"] if p["name"] == "design pattern")
        assert design["episodes"] == ["episode-fixture-a"]

    def test_unattributable_row_untouched(self, tmp_path: Path) -> None:
        episodes_dir = tmp_path / "episodes"
        graph_path = tmp_path / "graph.json"
        _write_episode(episodes_dir, _EPISODE_A)
        graph_path.write_text(json.dumps(_legacy_graph(_EPISODE_A)), encoding="utf-8")

        assert _run(graph_path, episodes_dir) == 0

        result = json.loads(graph_path.read_text(encoding="utf-8"))
        orphan = next(p for p in result["patterns"] if p["name"] == "Orphan seed pattern")
        assert orphan["episodes"] == []

    def test_only_episodes_field_changes(self, tmp_path: Path) -> None:
        episodes_dir = tmp_path / "episodes"
        graph_path = tmp_path / "graph.json"
        _write_episode(episodes_dir, _EPISODE_A)
        before = _legacy_graph(_EPISODE_A)
        graph_path.write_text(json.dumps(before), encoding="utf-8")

        assert _run(graph_path, episodes_dir) == 0

        after = json.loads(graph_path.read_text(encoding="utf-8"))
        edge_before, edge_after = before["edges"][0], after["edges"][0]
        for field in ("source", "target", "type", "weight", "evidence_count", "created"):
            assert edge_after[field] == edge_before[field]

    def test_partially_attributed_item_gains_surviving_supporter(
        self, tmp_path: Path,
    ) -> None:
        # An item that already records one episode but has an unrecorded
        # surviving supporter (a real case: implementation pattern in the live
        # graph had 1 recorded episode and 7 supporters). Union completes the
        # provenance without dropping the recorded id; retraction of the stale
        # id is the #3039 path's job, not the backfill's.
        episodes_dir = tmp_path / "episodes"
        graph_path = tmp_path / "graph.json"
        _write_episode(episodes_dir, _EPISODE_A)
        graph = _legacy_graph(_EPISODE_A)
        design = next(p for p in graph["patterns"] if p["name"] == "design pattern")
        design["episodes"] = ["episode-old-supporter"]
        graph_path.write_text(json.dumps(graph), encoding="utf-8")

        assert _run(graph_path, episodes_dir) == 0

        result = json.loads(graph_path.read_text(encoding="utf-8"))
        design_after = next(p for p in result["patterns"] if p["name"] == "design pattern")
        assert design_after["episodes"] == ["episode-fixture-a", "episode-old-supporter"]

    def test_idempotent_second_run_writes_nothing(self, tmp_path: Path) -> None:
        episodes_dir = tmp_path / "episodes"
        graph_path = tmp_path / "graph.json"
        _write_episode(episodes_dir, _EPISODE_A)
        graph_path.write_text(json.dumps(_legacy_graph(_EPISODE_A)), encoding="utf-8")

        assert _run(graph_path, episodes_dir) == 0
        first = graph_path.read_bytes()
        assert _run(graph_path, episodes_dir) == 0
        assert graph_path.read_bytes() == first

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        episodes_dir = tmp_path / "episodes"
        graph_path = tmp_path / "graph.json"
        _write_episode(episodes_dir, _EPISODE_A)
        original = json.dumps(_legacy_graph(_EPISODE_A))
        graph_path.write_text(original, encoding="utf-8")

        assert _run(graph_path, episodes_dir, "--dry-run") == 0
        assert graph_path.read_text(encoding="utf-8") == original

    def test_path_traversal_rejected(self, tmp_path: Path) -> None:
        assert main(
            ["--graph-path", "../evil.json", "--episode-path", str(tmp_path)],
        ) == 2


class TestSortedUnion:
    """Multiple attributing episodes yield a sorted, de-duplicated list."""

    def test_two_episodes_sorted(self, tmp_path: Path) -> None:
        episodes_dir = tmp_path / "episodes"
        graph_path = tmp_path / "graph.json"
        # Two episodes whose content reproduces the SAME edge and pattern; ids
        # chosen so insertion order differs from sorted order.
        ep_z = {**_EPISODE_A, "id": "episode-zzz"}
        ep_a = {**_EPISODE_A, "id": "episode-aaa"}
        _write_episode(episodes_dir, ep_z)
        _write_episode(episodes_dir, ep_a)
        graph_path.write_text(json.dumps(_legacy_graph(_EPISODE_A)), encoding="utf-8")

        assert _run(graph_path, episodes_dir) == 0

        result = json.loads(graph_path.read_text(encoding="utf-8"))
        assert result["edges"][0]["episodes"] == ["episode-aaa", "episode-zzz"]

    def test_backfill_graph_idempotent_in_memory(self, tmp_path: Path) -> None:
        episodes_dir = tmp_path / "episodes"
        _write_episode(episodes_dir, _EPISODE_A)
        edge_attr, pattern_attr = derive_attribution(
            sorted(episodes_dir.glob("episode-*.json")),
        )
        graph = _legacy_graph(_EPISODE_A)

        first = backfill_graph(graph, edge_attr, pattern_attr)
        second = backfill_graph(graph, edge_attr, pattern_attr)

        assert first == {"edges_backfilled": 1, "patterns_backfilled": 1}
        assert second == {"edges_backfilled": 0, "patterns_backfilled": 0}
        assert graph["edges"][0]["episodes"] == ["episode-fixture-a"]
