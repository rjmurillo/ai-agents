"""Tests for the causal graph id repair (issue #3367).

Thirteen committed nodes carried an id that ``generate_node_id`` does not
reproduce from their own type and label. These cover both repairs (rename and
fold), the edge moves that have to follow a rename, idempotence, and the CLI
contract, plus the guards against the repair itself losing evidence.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.maintenance import repair_causal_graph_ids as repair_mod

_GENERATOR = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "memory" / "scripts"
if str(_GENERATOR) not in sys.path:
    sys.path.insert(0, str(_GENERATOR))

from update_causal_graph import generate_node_id  # noqa: E402  (path set above)


def _node(node_type: str, label: str, node_id: str | None = None, **extra: Any) -> dict[str, Any]:
    node = {
        "id": node_id if node_id is not None else generate_node_id(node_type, label),
        "type": node_type,
        "label": label,
        "episodes": ["episode-1"],
        "created": "2026-01-01T00:00:00+00:00",
    }
    node.update(extra)
    return node


def _graph(**overrides: Any) -> dict[str, Any]:
    graph: dict[str, Any] = {
        "version": "3",
        "updated": "2026-01-01T00:00:00+00:00",
        "nodes": [],
        "patterns": [],
        "edges": [],
    }
    graph.update(overrides)
    return graph


class TestAnIdThatIsFreeIsJustRenamed:
    def test_the_node_takes_the_id_its_content_derives(self) -> None:
        stale = _node("decision", "chose uv", node_id="deadbeefcafe")
        repaired = repair_mod.repair(_graph(nodes=[stale]))
        assert [n["id"] for n in repaired["nodes"]] == [generate_node_id("decision", "chose uv")]

    def test_nothing_but_the_id_changes(self) -> None:
        stale = _node("decision", "chose uv", node_id="deadbeefcafe", episodes=["a", "b"])
        repaired = repair_mod.repair(_graph(nodes=[stale]))["nodes"][0]
        assert repaired["episodes"] == ["a", "b"]
        assert repaired["created"] == "2026-01-01T00:00:00+00:00"
        assert repaired["label"] == "chose uv"

    def test_a_node_already_correct_is_left_alone(self) -> None:
        good = _node("decision", "chose uv")
        assert repair_mod.repair(_graph(nodes=[good]))["nodes"] == [good]


class TestAnIdAlreadyTakenIsFolded:
    def _pair(self) -> dict[str, Any]:
        canonical = _node("test", "pytest", episodes=["a"], created="2026-01-01T00:00:00+00:00")
        stale = _node(
            "test",
            "pytest",
            node_id="deadbeefcafe",
            episodes=["b"],
            created="2025-06-01T00:00:00+00:00",
        )
        return _graph(nodes=[canonical, stale])

    def test_the_duplicate_pair_becomes_one_node(self) -> None:
        assert len(repair_mod.repair(self._pair())["nodes"]) == 1

    def test_episodes_from_both_survive(self) -> None:
        assert repair_mod.repair(self._pair())["nodes"][0]["episodes"] == ["a", "b"]

    def test_the_earlier_created_wins(self) -> None:
        """The fold keeps when the thing was first seen, not when it was split."""
        assert repair_mod.repair(self._pair())["nodes"][0]["created"] == "2025-06-01T00:00:00+00:00"

    def test_folding_is_independent_of_which_copy_comes_first(self) -> None:
        graph = self._pair()
        reversed_graph = _graph(nodes=list(reversed(graph["nodes"])))
        forward = repair_mod.repair(graph)["nodes"][0]
        backward = repair_mod.repair(reversed_graph)["nodes"][0]
        assert forward["id"] == backward["id"]
        assert forward["episodes"] == backward["episodes"]
        assert forward["created"] == backward["created"]


class TestEdgesFollowTheirEndpoints:
    def test_an_edge_onto_a_renamed_node_is_moved(self) -> None:
        stale = _node("decision", "chose uv", node_id="deadbeefcafe")
        other = _node("test", "pytest")
        edge = {"source": "deadbeefcafe", "target": other["id"], "weight": 1.0}
        repaired = repair_mod.repair(_graph(nodes=[stale, other], edges=[edge]))
        assert repaired["edges"][0]["source"] == generate_node_id("decision", "chose uv")

    def test_no_edge_is_left_pointing_at_a_missing_node(self) -> None:
        stale = _node("decision", "chose uv", node_id="deadbeefcafe")
        other = _node("test", "pytest")
        edges = [
            {"source": "deadbeefcafe", "target": other["id"], "weight": 1.0},
            {"source": other["id"], "target": "deadbeefcafe", "weight": 1.0},
        ]
        repaired = repair_mod.repair(_graph(nodes=[stale, other], edges=edges))
        ids = {n["id"] for n in repaired["nodes"]}
        assert all(e["source"] in ids and e["target"] in ids for e in repaired["edges"])
        assert len(repaired["edges"]) == 2

    def test_two_edges_that_collapse_onto_one_pair_are_folded(self) -> None:
        """A fold can make two edges name the same pair; the generator allows one."""
        canonical = _node("test", "pytest")
        stale = _node("test", "pytest", node_id="deadbeefcafe")
        other = _node("decision", "chose uv")
        edges = [
            {
                "source": other["id"],
                "target": canonical["id"],
                "weight": 1.0,
                "evidence_count": 1,
                "contributions": {"a": 1.0},
            },
            {
                "source": other["id"],
                "target": "deadbeefcafe",
                "weight": 0.5,
                "evidence_count": 1,
                "contributions": {"b": 0.5},
            },
        ]
        repaired = repair_mod.repair(_graph(nodes=[canonical, stale, other], edges=edges))
        assert len(repaired["edges"]) == 1
        folded = repaired["edges"][0]
        assert folded["contributions"] == {"a": 1.0, "b": 0.5}
        assert folded["evidence_count"] == 2
        assert folded["weight"] == 0.75

    def test_an_edge_between_untouched_nodes_is_unchanged(self) -> None:
        a, b = _node("test", "pytest"), _node("decision", "chose uv")
        edge = {"source": a["id"], "target": b["id"], "weight": 1.0}
        assert repair_mod.repair(_graph(nodes=[a, b], edges=[edge]))["edges"] == [edge]


class TestRerunningChangesNothing:
    def test_a_repaired_graph_is_a_fixed_point(self) -> None:
        graph = _graph(
            nodes=[
                _node("test", "pytest", node_id="deadbeefcafe", episodes=["b"]),
                _node("test", "pytest", episodes=["a"]),
                _node("decision", "chose uv", node_id="0123456789ab"),
            ],
            edges=[{"source": "deadbeefcafe", "target": "0123456789ab", "weight": 1.0}],
        )
        once = repair_mod.repair(graph)
        assert repair_mod.repair(once) == once

    def test_a_clean_graph_reports_nothing_to_do(self) -> None:
        assert repair_mod.unreproducible(_graph(nodes=[_node("test", "pytest")])) == []


class TestTheCli:
    def _write(self, tmp_path: Path, graph: dict[str, Any]) -> Path:
        path = tmp_path / "causal-graph.json"
        path.write_text(json.dumps(graph), encoding="utf-8")
        return path

    def test_check_exits_nonzero_when_an_id_does_not_reproduce(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = self._write(tmp_path, _graph(nodes=[_node("test", "pytest", node_id="dead")]))
        assert repair_mod.main([str(path), "--check"]) == 1
        assert "dead ->" in capsys.readouterr().out

    def test_check_exits_zero_on_a_clean_graph(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, _graph(nodes=[_node("test", "pytest")]))
        assert repair_mod.main([str(path), "--check"]) == 0

    def test_check_does_not_write(self, tmp_path: Path) -> None:
        graph = _graph(nodes=[_node("test", "pytest", node_id="dead")])
        path = self._write(tmp_path, graph)
        before = path.read_text(encoding="utf-8")
        repair_mod.main([str(path), "--check"])
        assert path.read_text(encoding="utf-8") == before

    def test_the_default_run_writes_the_repair(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, _graph(nodes=[_node("test", "pytest", node_id="dead")]))
        assert repair_mod.main([str(path)]) == 0
        written = json.loads(path.read_text(encoding="utf-8"))
        assert written["nodes"][0]["id"] == generate_node_id("test", "pytest")

    def test_a_clean_graph_is_left_byte_stable(self, tmp_path: Path) -> None:
        """Writing an unchanged graph would churn the diff for no reason."""
        path = self._write(tmp_path, _graph(nodes=[_node("test", "pytest")]))
        before = path.read_text(encoding="utf-8")
        assert repair_mod.main([str(path)]) == 0
        assert path.read_text(encoding="utf-8") == before

    def test_it_defaults_to_the_committed_graph(self) -> None:
        assert repair_mod.DEFAULT_GRAPH.name == "causal-graph.json"
        assert repair_mod.DEFAULT_GRAPH.exists()


class TestTheRepairDoesNotLoseEvidence:
    """Guards against the fix being worse than the bug it repairs."""

    def test_no_type_label_pair_disappears(self) -> None:
        graph = _graph(
            nodes=[
                _node("test", "pytest", node_id="dead"),
                _node("decision", "chose uv", node_id="beef"),
                _node("commit", "abc123"),
            ]
        )
        repaired = repair_mod.repair(graph)
        assert {(n["type"], n["label"]) for n in repaired["nodes"]} == {
            (n["type"], n["label"]) for n in graph["nodes"]
        }

    def test_no_episode_is_dropped(self) -> None:
        graph = _graph(
            nodes=[
                _node("test", "pytest", node_id="dead", episodes=["a"]),
                _node("test", "pytest", episodes=["b", "c"]),
            ]
        )
        repaired = repair_mod.repair(graph)
        assert set(repaired["nodes"][0]["episodes"]) == {"a", "b", "c"}

    def test_patterns_are_not_touched(self) -> None:
        patterns = [{"name": "recovery", "id": "abc", "occurrences": 2}]
        graph = _graph(nodes=[_node("test", "pytest", node_id="dead")], patterns=patterns)
        assert repair_mod.repair(graph)["patterns"] == patterns

    def test_unknown_top_level_keys_survive(self) -> None:
        graph = _graph(nodes=[_node("test", "pytest", node_id="dead")], cohorts=[1])
        assert repair_mod.repair(graph)["cohorts"] == [1]
