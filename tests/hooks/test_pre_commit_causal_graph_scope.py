#!/usr/bin/env python3
"""Regression tests for the pre-commit causal-graph scoping fix (#3034).

Before the fix, staging any episode file made the pre-commit hook regenerate the
causal graph from the ENTIRE episodes directory
(``update_causal_graph.py --episode-path <dir>``) and stage the result. When the
committed graph was stale, that dragged a large, unrelated cross-session diff
into whatever commit happened to touch one episode.

The fix scopes the regeneration to the STAGED episode files, one at a time. The
generator builds nodes/edges/chains/patterns per episode (no cross-episode
relationships) and merges additively with dedupe by node id, so a per-episode
run produces a graph delta proportional to the change.

These tests assert (1) structurally that the hook no longer runs the whole-tree
regeneration and does loop over the staged files, and (2) behaviorally that the
generator, run on a single episode, adds only that episode's nodes and is
idempotent on a second run.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PRE_COMMIT = REPO_ROOT / ".githooks" / "pre-commit"
SCRIPT = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "memory"
    / "scripts"
    / "update_causal_graph.py"
)


def _hook_text() -> str:
    return PRE_COMMIT.read_text(encoding="utf-8")


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("update_causal_graph", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- structural guards -----------------------------------------------------


def test_hook_does_not_regen_whole_episode_directory() -> None:
    text = _hook_text()
    assert '--episode-path "$REPO_ROOT/.agents/memory/episodes"' not in text, (
        "pre-commit reintroduced the whole-directory causal-graph regen (#3034); "
        "scope it to the staged episode files instead"
    )


def test_hook_loops_over_staged_episode_files() -> None:
    text = _hook_text()
    assert 'while IFS= read -r _episode' in text, (
        "pre-commit should iterate the staged episodes"
    )
    assert '--episode-path "$REPO_ROOT/$_episode"' in text, (
        "pre-commit should pass each staged episode path to the generator"
    )
    assert 'done <<< "$STAGED_EPISODE_FILES"' in text, (
        "the loop should read the staged episode set"
    )


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
