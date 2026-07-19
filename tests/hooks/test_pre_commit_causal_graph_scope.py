#!/usr/bin/env python3
"""Regression tests for scoped, additive causal-graph generation."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "memory"
    / "scripts"
    / "update_causal_graph.py"
)


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("update_causal_graph", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- behavioral guards on the generator ------------------------------------


def _episode(episode_id: str, event_content: str) -> dict:
    return {
        "id": episode_id,
        "session": episode_id,
        "timestamp": "2026-07-12T00:00:00+00:00",
        "task": f"task for {episode_id}",
        "outcome": "success",
        "decisions": [],
        "events": [
            {
                "id": "e001",
                "timestamp": "2026-07-12T00:00:00+00:00",
                "type": "milestone",
                "content": event_content,
                "caused_by": [],
                "leads_to": [],
            }
        ],
        "metrics": {},
        "lessons": [],
    }


def _episode_with_chains(episode_id: str) -> dict:
    """An episode that yields both edges and patterns.

    The decision produces a pattern (via get_decision_patterns) and a
    decision -> event edge to e003: build_causal_chains matches the decision's
    chosen keywords against event content, and to_type is the matched event's
    type (milestone here), not "outcome". The error event followed by a matching
    milestone produces an error -> recovery edge. This exercises the edge/pattern
    idempotency guard that a plain single-event episode does not reach (#3034
    review finding).
    """
    return {
        "id": episode_id,
        "session": episode_id,
        "timestamp": "2026-07-12T00:00:00+00:00",
        "task": f"task for {episode_id}",
        "outcome": "success",
        "decisions": [
            {
                "type": "architecture",
                "chosen": "adopt caching layer",
                "outcome": "success",
                "context": "latency too high",
            }
        ],
        "events": [
            {
                "id": "e001",
                "timestamp": "2026-07-12T00:00:00+00:00",
                "type": "error",
                "content": "cache miss storm",
                "caused_by": [],
                "leads_to": [],
            },
            {
                "id": "e002",
                "timestamp": "2026-07-12T00:01:00+00:00",
                "type": "milestone",
                "content": "fix the cache miss storm",
                "caused_by": [],
                "leads_to": [],
            },
            {
                "id": "e003",
                "timestamp": "2026-07-12T00:02:00+00:00",
                "type": "milestone",
                "content": "adopt caching layer rollout",
                "caused_by": [],
                "leads_to": [],
            },
        ],
        "metrics": {},
        "lessons": [],
    }


def _run(generator: ModuleType, episode_file: Path, graph_file: Path) -> int:
    return generator.main(
        [
            "--episode-path",
            str(episode_file),
            "--graph-path",
            str(graph_file),
        ]
    )


def test_single_episode_adds_only_its_own_nodes(tmp_path: Path) -> None:
    generator = _load_generator()
    graph = tmp_path / "graph.json"
    graph.write_text(
        json.dumps({"nodes": [], "edges": [], "patterns": []}) + "\n",
        encoding="utf-8",
    )
    ep = tmp_path / "episode-a.json"
    ep.write_text(json.dumps(_episode("epA", "did the A thing")), encoding="utf-8")

    rc = _run(generator, ep, graph)

    assert rc == 0
    data = json.loads(graph.read_text(encoding="utf-8"))
    labels = [n["label"] for n in data["nodes"]]
    # Only epA's own event + outcome nodes, nothing from any other episode.
    assert any("did the A thing" in label for label in labels)
    assert all("epA" in n["episodes"] for n in data["nodes"])


def test_reprocessing_same_episode_is_idempotent(tmp_path: Path) -> None:
    generator = _load_generator()
    graph = tmp_path / "graph.json"
    graph.write_text(
        json.dumps({"nodes": [], "edges": [], "patterns": []}) + "\n",
        encoding="utf-8",
    )
    ep = tmp_path / "episode-a.json"
    ep.write_text(json.dumps(_episode("epA", "did the A thing")), encoding="utf-8")

    assert _run(generator, ep, graph) == 0
    first = graph.read_text(encoding="utf-8")
    assert _run(generator, ep, graph) == 0
    second = graph.read_text(encoding="utf-8")

    assert first == second, "reprocessing an unchanged episode must not churn the graph"


def test_reprocessing_episode_with_edges_and_patterns_is_idempotent(
    tmp_path: Path,
) -> None:
    # An episode carrying decisions and an error/recovery chain produces edges
    # and patterns. Reprocessing it (a re-commit or edit) must not manufacture
    # evidence: evidence_count, weight, occurrences, and success_rate must not
    # drift (#3034 review finding on edge/pattern non-idempotency).
    generator = _load_generator()
    graph = tmp_path / "graph.json"
    graph.write_text(
        json.dumps({"nodes": [], "edges": [], "patterns": []}) + "\n",
        encoding="utf-8",
    )
    ep = tmp_path / "episode-chains.json"
    ep.write_text(json.dumps(_episode_with_chains("epC")), encoding="utf-8")

    assert _run(generator, ep, graph) == 0
    first_data = json.loads(graph.read_text(encoding="utf-8"))
    # The fixture must actually exercise edges and patterns, else the guard is
    # not tested.
    assert first_data["edges"], "fixture should produce at least one edge"
    assert first_data["patterns"], "fixture should produce at least one pattern"
    first = graph.read_text(encoding="utf-8")

    assert _run(generator, ep, graph) == 0
    second = graph.read_text(encoding="utf-8")

    assert first == second, (
        "reprocessing an episode with edges/patterns must be byte-identical; "
        "the episodes guard must make add_causal_edge/add_pattern no-ops"
    )


def test_second_episode_does_not_remove_first(tmp_path: Path) -> None:
    generator = _load_generator()
    graph = tmp_path / "graph.json"
    graph.write_text(
        json.dumps({"nodes": [], "edges": [], "patterns": []}) + "\n",
        encoding="utf-8",
    )
    ep_a = tmp_path / "episode-a.json"
    ep_a.write_text(json.dumps(_episode("epA", "the A thing")), encoding="utf-8")
    ep_b = tmp_path / "episode-b.json"
    ep_b.write_text(json.dumps(_episode("epB", "the B thing")), encoding="utf-8")

    assert _run(generator, ep_a, graph) == 0
    assert _run(generator, ep_b, graph) == 0

    labels = [n["label"] for n in json.loads(graph.read_text(encoding="utf-8"))["nodes"]]
    assert any("the A thing" in label for label in labels)
    assert any("the B thing" in label for label in labels)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
