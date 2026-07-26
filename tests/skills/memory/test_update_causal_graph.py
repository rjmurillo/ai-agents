"""Tests for update_causal_graph.py."""

import importlib.util
import json
import re
import shlex
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import update_causal_graph


class TestLoadCausalGraph:
    """Tests for load_causal_graph function."""

    def test_empty_graph_structure(self, tmp_path):
        # load_causal_graph returns empty graph when file doesn't exist
        graph = update_causal_graph.load_causal_graph(tmp_path / "nonexistent.json")
        assert "nodes" in graph
        assert "edges" in graph
        assert "patterns" in graph
        assert graph["nodes"] == []


class TestAddCausalNode:
    """Tests for add_causal_node function."""

    def test_adds_new_node(self):
        graph = {"nodes": [], "edges": [], "patterns": []}
        node = update_causal_graph.add_causal_node(graph, "decision", "Use Python", "ep-1")
        assert node is not None
        assert node["type"] == "decision"
        assert node["label"] == "Use Python"
        assert len(graph["nodes"]) == 1

    def test_updates_existing_node(self):
        graph = {"nodes": [], "edges": [], "patterns": []}
        update_causal_graph.add_causal_node(graph, "decision", "Use Python", "ep-1")
        node = update_causal_graph.add_causal_node(graph, "decision", "Use Python", "ep-2")
        assert len(graph["nodes"]) == 1
        assert "ep-2" in node["episodes"]


class TestAddCausalEdge:
    """Tests for add_causal_edge function."""

    def test_adds_new_edge(self):
        graph = {"nodes": [], "edges": [], "patterns": []}
        edge = update_causal_graph.add_causal_edge(graph, "n001", "n002", "causes", 0.8, "ep-1")
        assert edge is not None
        assert edge["source"] == "n001"
        assert edge["weight"] == 0.8
        assert edge["evidence_count"] == 1
        assert edge["episodes"] == ["ep-1"]
        assert "count" not in edge
        assert len(graph["edges"]) == 1

    def test_updates_existing_edge(self):
        graph = {"nodes": [], "edges": [], "patterns": []}
        update_causal_graph.add_causal_edge(graph, "n001", "n002", "causes", 0.8, "ep-1")
        edge = update_causal_graph.add_causal_edge(graph, "n001", "n002", "causes", 0.6, "ep-2")
        assert len(graph["edges"]) == 1
        assert edge["evidence_count"] == 2
        assert edge["weight"] == 0.7
        assert edge["episodes"] == ["ep-1", "ep-2"]
        assert "count" not in edge

    def test_same_episode_reprocess_is_noop(self):
        # An episode contributes to an edge at most once; reprocessing the
        # same episode must not manufacture evidence (#3034 follow-up).
        graph = {"nodes": [], "edges": [], "patterns": []}
        update_causal_graph.add_causal_edge(graph, "n001", "n002", "causes", 0.8, "ep-1")
        result = update_causal_graph.add_causal_edge(graph, "n001", "n002", "causes", 0.8, "ep-1")
        assert result is None
        assert len(graph["edges"]) == 1
        assert graph["edges"][0]["evidence_count"] == 1
        assert graph["edges"][0]["weight"] == 0.8
        assert graph["edges"][0]["episodes"] == ["ep-1"]

    def test_migrates_legacy_count_key(self):
        graph = {
            "nodes": [],
            "edges": [
                {
                    "source": "n001",
                    "target": "n002",
                    "type": "causes",
                    "weight": 0.8,
                    "count": 9,
                }
            ],
            "patterns": [],
        }
        edge = update_causal_graph.add_causal_edge(graph, "n001", "n002", "causes", 0.6, "ep-1")

        assert edge["evidence_count"] == 10
        assert edge["weight"] == 0.78
        assert "count" not in edge
        assert edge["episodes"] == ["ep-1"]


class TestAddPattern:
    """Tests for add_pattern function."""

    def test_adds_new_pattern(self):
        graph = {"nodes": [], "edges": [], "patterns": []}
        pattern = update_causal_graph.add_pattern(
            graph, "test-pattern", "desc", "trigger", "action", 1.0, "ep-1"
        )
        assert pattern is not None
        assert pattern["name"] == "test-pattern"
        assert pattern["episodes"] == ["ep-1"]
        assert len(graph["patterns"]) == 1

    def test_updates_existing_pattern(self):
        graph = {"nodes": [], "edges": [], "patterns": []}
        update_causal_graph.add_pattern(
            graph, "test-pattern", "desc", "trigger", "action", 1.0, "ep-1"
        )
        pattern = update_causal_graph.add_pattern(
            graph, "test-pattern", "desc", "trigger", "action", 0.0, "ep-2"
        )
        assert len(graph["patterns"]) == 1
        assert pattern["occurrences"] == 2
        assert pattern["success_rate"] == 0.5
        assert pattern["episodes"] == ["ep-1", "ep-2"]

    def test_same_episode_reprocess_is_noop(self):
        # Reprocessing the same episode must not inflate occurrences or drift
        # success_rate (#3034 follow-up).
        graph = {"nodes": [], "edges": [], "patterns": []}
        update_causal_graph.add_pattern(
            graph, "test-pattern", "desc", "trigger", "action", 1.0, "ep-1"
        )
        result = update_causal_graph.add_pattern(
            graph, "test-pattern", "desc", "trigger", "action", 1.0, "ep-1"
        )
        assert result is None
        assert len(graph["patterns"]) == 1
        assert graph["patterns"][0]["occurrences"] == 1
        assert graph["patterns"][0]["success_rate"] == 1.0
        assert graph["patterns"][0]["episodes"] == ["ep-1"]

    def test_running_average_is_occurrence_weighted(self):
        # An occurrence-weighted average of 1.0, 1.0, 0.0 is 0.67; the old
        # two-point (old + new) / 2 form produced 0.50 (#3034 review).
        graph = {"nodes": [], "edges": [], "patterns": []}
        update_causal_graph.add_pattern(
            graph, "test-pattern", "desc", "trigger", "action", 1.0, "ep-1"
        )
        update_causal_graph.add_pattern(
            graph, "test-pattern", "desc", "trigger", "action", 1.0, "ep-2"
        )
        update_causal_graph.add_pattern(
            graph, "test-pattern", "desc", "trigger", "action", 0.0, "ep-3"
        )
        pattern = graph["patterns"][0]
        assert pattern["occurrences"] == 3
        assert pattern["success_rate"] == 0.67
        assert pattern["episodes"] == ["ep-1", "ep-2", "ep-3"]


class TestGetDecisionPatterns:
    """Tests for get_decision_patterns function."""

    def test_success_pattern(self):
        episode = {
            "id": "ep-1",
            "decisions": [
                {
                    "type": "design",
                    "chosen": "Use factory pattern",
                    "outcome": "success",
                    "context": "Need flexible creation",
                }
            ],
        }
        patterns = update_causal_graph.get_decision_patterns(episode)
        assert len(patterns) == 1
        assert patterns[0]["success"] is True
        assert "design pattern" in patterns[0]["name"]

    def test_failure_antipattern(self):
        episode = {
            "id": "ep-1",
            "decisions": [
                {
                    "type": "test",
                    "chosen": "Skip tests",
                    "outcome": "failure",
                    "context": "",
                }
            ],
        }
        patterns = update_causal_graph.get_decision_patterns(episode)
        assert len(patterns) == 1
        assert patterns[0]["success"] is False
        assert "anti-pattern" in patterns[0]["name"]
        assert "AVOID" in patterns[0]["action"]


class TestBuildCausalChains:
    """Tests for build_causal_chains function."""

    def test_error_recovery_chain(self):
        episode = {
            "decisions": [],
            "events": [
                {"type": "error", "content": "Build failed"},
                {"type": "milestone", "content": "Applied fix and recovered"},
            ],
        }
        chains = update_causal_graph.build_causal_chains(episode)
        assert len(chains) >= 1
        assert chains[0]["from_type"] == "error"
        assert chains[0]["edge_type"] == "causes"

    def test_decision_event_chain(self):
        episode = {
            "decisions": [{"chosen": "Use Python scripts", "type": "design"}],
            "events": [
                {"type": "commit", "content": "Converted to Python scripts"},
            ],
        }
        chains = update_causal_graph.build_causal_chains(episode)
        assert len(chains) >= 1

    def test_no_chains(self):
        episode = {"decisions": [], "events": []}
        chains = update_causal_graph.build_causal_chains(episode)
        assert chains == []


class TestGetEpisodeFiles:
    """Tests for get_episode_files function."""

    def test_single_file(self, tmp_path):
        ep = tmp_path / "episode-test.json"
        ep.write_text('{"id": "ep-1"}')
        files = update_causal_graph.get_episode_files(ep, None)
        assert len(files) == 1

    def test_directory(self, tmp_path):
        (tmp_path / "episode-1.json").write_text('{"id": "ep-1"}')
        (tmp_path / "episode-2.json").write_text('{"id": "ep-2"}')
        (tmp_path / "not-an-episode.json").write_text("{}")
        files = update_causal_graph.get_episode_files(tmp_path, None)
        assert len(files) == 2

    def test_missing_path(self, tmp_path):
        files = update_causal_graph.get_episode_files(tmp_path / "missing", None)
        assert files == []

    def test_since_filter(self, tmp_path):
        (tmp_path / "episode-old.json").write_text(json.dumps({"timestamp": "2025-01-01T00:00:00"}))
        (tmp_path / "episode-new.json").write_text(json.dumps({"timestamp": "2026-06-01T00:00:00"}))
        # Source expects since as ISO string, not datetime
        files = update_causal_graph.get_episode_files(tmp_path, "2026-01-01")
        assert len(files) == 1


class TestRemoveEpisodeContributions:
    """Issue #3039: retract a specific episode's nodes/edges/patterns."""

    def _graph_with_two_episodes(self):
        graph = {"nodes": [], "edges": [], "patterns": []}
        # Shared edge contributed by both episodes; node shared; pattern per ep.
        update_causal_graph.add_causal_node(graph, "decision", "d", "ep-1")
        update_causal_graph.add_causal_node(graph, "decision", "d", "ep-2")
        update_causal_graph.add_causal_edge(graph, "a", "b", "causes", 1.0, "ep-1")
        update_causal_graph.add_causal_edge(graph, "a", "b", "causes", 0.0, "ep-2")
        update_causal_graph.add_pattern(graph, "p", "d", "t", "x", 1.0, "ep-1")
        return graph

    def test_removes_sole_supporter_edge_and_pattern(self):
        graph = self._graph_with_two_episodes()
        removed = update_causal_graph.remove_episode_contributions(graph, "ep-1")
        # The pattern only ep-1 supported is gone; the shared edge survives.
        assert removed["patterns"] == 1
        assert graph["patterns"] == []
        assert len(graph["edges"]) == 1

    def test_shared_edge_weight_recomputed_exactly(self):
        graph = self._graph_with_two_episodes()
        # Shared edge mean of {1.0, 0.0} = 0.5 before removal.
        assert graph["edges"][0]["weight"] == 0.5
        update_causal_graph.remove_episode_contributions(graph, "ep-2")
        # ep-2's 0.0 removed -> mean of {1.0} = 1.0, exact (running average
        # could not have recovered this).
        assert graph["edges"][0]["weight"] == 1.0
        assert graph["edges"][0]["evidence_count"] == 1
        assert graph["edges"][0]["episodes"] == ["ep-1"]

    def test_shared_node_survives_partial_removal(self):
        graph = self._graph_with_two_episodes()
        update_causal_graph.remove_episode_contributions(graph, "ep-1")
        # Node "d" was contributed by ep-1 and ep-2; still supported by ep-2.
        assert len(graph["nodes"]) == 1
        assert graph["nodes"][0]["episodes"] == ["ep-2"]

    def test_removing_absent_episode_is_noop(self):
        graph = self._graph_with_two_episodes()
        before = json.dumps(graph, sort_keys=True)
        update_causal_graph.remove_episode_contributions(graph, "ep-404")
        assert json.dumps(graph, sort_keys=True) == before

    def test_legacy_anonymous_evidence_survives_prune(self):
        # A bare-count legacy edge plus one real episode; pruning the episode
        # keeps the anonymous legacy evidence.
        graph = {
            "nodes": [],
            "edges": [
                {"source": "a", "target": "b", "type": "causes", "weight": 0.8, "count": 3},
            ],
            "patterns": [],
        }
        update_causal_graph.add_causal_edge(graph, "a", "b", "causes", 0.4, "ep-1")
        # mean of {0.8,0.8,0.8,0.4} = 0.7
        assert graph["edges"][0]["weight"] == 0.7
        update_causal_graph.remove_episode_contributions(graph, "ep-1")
        assert len(graph["edges"]) == 1  # legacy evidence keeps the edge
        assert graph["edges"][0]["weight"] == 0.8
        assert graph["edges"][0]["evidence_count"] == 3
        assert graph["edges"][0]["episodes"] == []

    def test_orphan_node_survives_unrelated_prune(self):
        # Data-loss regression (#3039): a node the pruned episode never
        # referenced, whose provenance is empty or absent, must survive the
        # prune and must not be counted as removed. Pre-fix, the node loop
        # filtered every node and deleted any that ended up empty, vacuuming
        # unrelated orphans on any prune.
        graph = {
            "nodes": [
                {"id": "n001", "type": "decision", "label": "orphan-empty", "episodes": []},
                {"id": "n002", "type": "decision", "label": "orphan-absent"},
                {"id": "n003", "type": "decision", "label": "other-ep", "episodes": ["ep-keep"]},
            ],
            "edges": [],
            "patterns": [],
        }
        removed = update_causal_graph.remove_episode_contributions(graph, "ep-does-not-exist")
        surviving = {n["id"] for n in graph["nodes"]}
        assert surviving == {"n001", "n002", "n003"}
        assert removed["nodes"] == 0

    def test_node_solely_supported_by_pruned_episode_is_removed(self):
        # Positive control: the fix must not disable the correct deletion. A
        # node supported only by the pruned episode is dropped; a node that
        # also has another supporter keeps that supporter.
        graph = {
            "nodes": [
                {"id": "n001", "type": "decision", "label": "sole", "episodes": ["ep-gone"]},
                {
                    "id": "n002",
                    "type": "decision",
                    "label": "shared",
                    "episodes": ["ep-gone", "ep-keep"],
                },
            ],
            "edges": [],
            "patterns": [],
        }
        removed = update_causal_graph.remove_episode_contributions(graph, "ep-gone")
        surviving = {n["id"] for n in graph["nodes"]}
        assert surviving == {"n002"}
        assert graph["nodes"][0]["episodes"] == ["ep-keep"]
        assert removed["nodes"] == 1


class TestReplaceSemanticsOnEdit:
    """Issue #3039: editing an episode to shrink it retracts stale content."""

    def _episode(self, tmp_path, name, events):
        ep = {"id": name, "task": "t", "outcome": "success", "events": events, "decisions": []}
        path = tmp_path / f"episode-{name}.json"
        path.write_text(json.dumps(ep), encoding="utf-8")
        return path

    def _run(self, tmp_path, graph_path, episode_path):
        return update_causal_graph.main(
            [
                "--episode-path",
                str(episode_path),
                "--graph-path",
                str(graph_path),
            ]
        )

    def test_edit_shrink_removes_stale_edge(self, tmp_path):
        graph_path = tmp_path / "graph.json"
        # First: an error->recovery chain produces one edge.
        events = [
            {"type": "error", "content": "boom happened"},
            {"type": "milestone", "content": "fix applied to boom"},
        ]
        ep = self._episode(tmp_path, "1", events)
        assert self._run(tmp_path, graph_path, ep) == 0
        graph = json.loads(graph_path.read_text())
        assert len(graph["edges"]) == 1

        # Edit the episode to drop the recovery milestone -> chain gone.
        ep.write_text(
            json.dumps(
                {
                    "id": "1",
                    "task": "t",
                    "outcome": "success",
                    "events": [{"type": "error", "content": "boom happened"}],
                    "decisions": [],
                }
            ),
            encoding="utf-8",
        )
        assert self._run(tmp_path, graph_path, ep) == 0
        graph = json.loads(graph_path.read_text())
        # The stale edge must be gone (pre-#3039 it stayed frozen).
        assert graph["edges"] == []


class TestPruneCli:
    """Issue #3039: --prune-episode-ids removes a deleted episode's content."""

    def test_prune_removes_deleted_episode(self, tmp_path):
        graph_path = tmp_path / "graph.json"
        graph = {"nodes": [], "edges": [], "patterns": []}
        update_causal_graph.add_causal_edge(graph, "a", "b", "causes", 1.0, "gone")
        update_causal_graph.add_causal_node(graph, "decision", "d", "gone")
        graph_path.write_text(json.dumps(graph), encoding="utf-8")

        rc = update_causal_graph.main(
            [
                "--episode-path",
                str(tmp_path / "no-such-dir"),
                "--graph-path",
                str(graph_path),
                "--prune-episode-ids",
                "gone",
            ]
        )
        assert rc == 0
        result = json.loads(graph_path.read_text())
        assert result["edges"] == []
        assert result["nodes"] == []

    def test_prune_dry_run_makes_no_change(self, tmp_path):
        graph_path = tmp_path / "graph.json"
        graph = {
            "nodes": [],
            "edges": [
                {
                    "source": "a",
                    "target": "b",
                    "type": "causes",
                    "weight": 1.0,
                    "evidence_count": 1,
                    "episodes": ["gone"],
                    "contributions": {"gone": 1.0},
                },
            ],
            "patterns": [],
        }
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        rc = update_causal_graph.main(
            [
                "--episode-path",
                str(tmp_path / "no-such-dir"),
                "--graph-path",
                str(graph_path),
                "--prune-episode-ids",
                "gone",
                "--dry-run",
            ]
        )
        assert rc == 0
        assert len(json.loads(graph_path.read_text())["edges"]) == 1


class TestChangedLabelRetraction:
    """Issue #3143: a failed commit's retry that corrects a milestone label
    must not leave the stale node.

    #3143 was filed 2026-07-17 01:13Z, about 18 hours before the #3039
    reconcile fix (commit 3601bb1b, 2026-07-17 19:45Z) landed. The reported
    symptom was two nodes for one episode after a pre-commit block, a milestone
    correction, and a retry. The #3039 edit-shrink retraction covers this case:
    the corrected label hashes to a new node id, so the prior node is present
    in the episode's old membership but is not re-touched on reprocess, and so
    it is retracted. These tests lock that behavior for the exact changed-label
    scenario (acceptance criterion 4) and the unchanged reprocess (criterion 2).
    """

    def _write_episode(self, path: Path, milestone: str) -> None:
        # Schema-complete mock: episode.schema.json also requires session,
        # timestamp, and metrics. Populating them keeps the fixture valid if a
        # future --since run parses timestamp (missing-key files are silently
        # skipped by get_episode_files).
        path.write_text(
            json.dumps(
                {
                    "id": "episode-2026-07-16-session-3056",
                    "session": "session-3056",
                    "timestamp": "2026-07-16T00:00:00Z",
                    "task": "close 3097",
                    "outcome": "success",
                    "decisions": [],
                    "events": [{"type": "milestone", "content": milestone}],
                    "metrics": {},
                }
            ),
            encoding="utf-8",
        )

    def _run(self, graph_path: Path, episode_path: Path) -> int:
        return update_causal_graph.main(
            [
                "--episode-path",
                str(episode_path),
                "--graph-path",
                str(graph_path),
            ]
        )

    def _milestone_nodes(self, graph_path: Path) -> list[dict]:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        return [n for n in graph["nodes"] if n["type"] == "milestone"]

    def test_corrected_label_leaves_only_final_node(self, tmp_path):
        graph_path = tmp_path / "graph.json"
        episode_path = tmp_path / "episode-3056.json"

        # First commit attempt: milestone ends in #3141. The graph is written
        # and staged before a later gate blocks the commit.
        self._write_episode(
            episode_path,
            "filed #3137, #3138, #3139, #3140, and #3141",
        )
        assert self._run(graph_path, episode_path) == 0
        first = self._milestone_nodes(graph_path)
        assert len(first) == 1
        assert "#3141" in first[0]["label"]

        # Retry after correcting the milestone to include newly filed #3142.
        # The corrected content hashes to a new node id.
        self._write_episode(
            episode_path,
            "filed #3137, #3138, #3139, #3140, #3141, and #3142",
        )
        assert self._run(graph_path, episode_path) == 0
        final = self._milestone_nodes(graph_path)

        # Exactly one milestone node survives, and it is the corrected version.
        # Pre-#3039 the stale #3141 node lingered, giving two nodes for one
        # episode.
        assert len(final) == 1, final
        # The surviving node is the corrected label: it carries the newly filed
        # #3142 and still lists #3141. Assert the ids individually rather than
        # the exact join punctuation, which is incidental to the behavior.
        label = final[0]["label"]
        assert "#3141" in label and "#3142" in label
        assert first[0]["id"] != final[0]["id"]

    def test_unchanged_reprocess_is_byte_idempotent(self, tmp_path):
        graph_path = tmp_path / "graph.json"
        episode_path = tmp_path / "episode-3056.json"
        self._write_episode(
            episode_path,
            "filed #3137, #3138, #3139, #3140, and #3141",
        )
        assert self._run(graph_path, episode_path) == 0
        first_bytes = graph_path.read_text(encoding="utf-8")

        # Reprocessing the identical episode must not add a node or churn the
        # `created` timestamps: the committed graph stays byte-stable.
        assert self._run(graph_path, episode_path) == 0
        assert graph_path.read_text(encoding="utf-8") == first_bytes


class TestGraphMetadataSurvivesAFreshWrite:
    """The graph's own schema requires version and updated (issue #3351).

    The committed graph carried both for months without any live writer
    touching them: they survived only because every write happened to load a
    file that already had them. A graph written from nothing dropped them, and
    the loss was invisible because that path never ran in production.
    """

    def test_a_graph_loaded_from_nothing_carries_version_and_updated(self, tmp_path):
        graph = update_causal_graph.load_causal_graph(tmp_path / "absent.json")

        assert graph["version"] == update_causal_graph.GRAPH_VERSION
        assert graph["updated"]

    def test_a_graph_loaded_from_corruption_fails_closed(self, tmp_path):
        corrupt = tmp_path / "corrupt.json"
        corrupt.write_text("{ not json", encoding="utf-8")

        with pytest.raises(ValueError, match="invalid JSON"):
            update_causal_graph.load_causal_graph(corrupt)

    @pytest.mark.parametrize(
        "content",
        ["[]", '[{"id": "abc"}]', '"text"', "42", "null", "true"],
        ids=["array", "populated_array", "string", "number", "null", "boolean"],
    )
    def test_well_formed_json_that_is_not_an_object_raises(self, tmp_path, content):
        """Parsing cleanly is not the same as being a graph.

        Every one of these used to survive the loader and crash later at the
        first ``graph["nodes"]`` with a TypeError naming a list or a NoneType
        and nothing about the graph. Raising here is deliberate rather than
        falling back to an empty graph: git_hook_policy.update_causal_graph
        snapshots the file, and only a non-zero exit makes it restore that
        snapshot. Returning an empty graph would let the hook stage the empty
        one over whatever the file held.
        """
        graph_file = tmp_path / "graph.json"
        graph_file.write_text(content, encoding="utf-8")

        with pytest.raises(ValueError, match="not an object"):
            update_causal_graph.load_causal_graph(graph_file)

    def test_bytes_that_are_not_utf8_raise_rather_than_escaping_raw(self, tmp_path):
        """UnicodeDecodeError is a ValueError, not an OSError.

        It therefore slipped past both existing handlers and propagated with a
        message about a byte position and no mention of the causal graph. The
        outcome was already correct, since git_hook_policy restores its
        snapshot on any non-zero exit, but the operator saw a raw traceback
        where every other corruption produces a sentence naming the file.
        """
        graph_file = tmp_path / "graph.json"
        graph_file.write_bytes(b'{"nodes": [], "edges": [\xff\xfe], "patterns": []}')

        with pytest.raises(ValueError, match="not valid UTF-8"):
            update_causal_graph.load_causal_graph(graph_file)

    def test_a_save_over_undecodable_bytes_replaces_them(self, tmp_path):
        """The comparison read is an optimization, so failing it means write.

        save_causal_graph short-circuits when the rendered content already
        matches the file. That read used to guard only OSError, so undecodable
        bytes on disk aborted the save with a UnicodeDecodeError instead of
        overwriting them. A graph that cannot be read is exactly the graph that
        most needs replacing.
        """
        path = tmp_path / "g.json"
        path.write_bytes(b"\xff\xfe not utf-8 at all")

        update_causal_graph.save_causal_graph(path, {"nodes": [], "edges": [], "patterns": []})

        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk["nodes"] == []
        assert on_disk["version"] == update_causal_graph.GRAPH_VERSION

    def test_a_save_over_an_unreadable_path_still_writes(self, tmp_path, monkeypatch):
        """The OSError half of the same contract, pinned alongside it.

        Without this the pair could regress to catching only UnicodeDecodeError
        and the suite would stay green.
        """
        path = tmp_path / "g.json"
        path.write_text("stale", encoding="utf-8")
        real_read = Path.read_text

        def refuse(self, *args, **kwargs):
            if self == path:
                raise OSError("read refused")
            return real_read(self, *args, **kwargs)

        with monkeypatch.context() as patched:
            patched.setattr(Path, "read_text", refuse)
            update_causal_graph.save_causal_graph(path, {"nodes": [], "edges": [], "patterns": []})

        assert json.loads(path.read_text(encoding="utf-8"))["nodes"] == []

    def test_a_fresh_write_lands_version_and_updated_on_disk(self, tmp_path):
        path = tmp_path / "g.json"

        update_causal_graph.save_causal_graph(path, {"nodes": [], "edges": [], "patterns": []})

        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk["version"] == update_causal_graph.GRAPH_VERSION
        assert on_disk["updated"]

    def test_each_write_restamps_updated(self, tmp_path):
        path = tmp_path / "g.json"
        graph = {
            "version": "1.0",
            "updated": "2026-02-10T17:55:46+00:00",
            "nodes": [],
            "edges": [],
            "patterns": [],
        }
        update_causal_graph.save_causal_graph(path, graph)
        first = json.loads(path.read_text(encoding="utf-8"))["updated"]

        graph["nodes"].append({"id": "abc", "type": "decision", "label": "x"})
        update_causal_graph.save_causal_graph(path, graph)

        assert json.loads(path.read_text(encoding="utf-8"))["updated"] != first

    def test_a_write_that_changes_nothing_leaves_the_file_untouched(self, tmp_path):
        # This runs on every commit. An unconditional stamp would dirty the
        # graph each time and manufacture conflicts in the repo's worst
        # conflict source.
        path = tmp_path / "g.json"
        graph = {"version": "1.0", "nodes": [], "edges": [], "patterns": []}
        update_causal_graph.save_causal_graph(path, graph)
        first_bytes = path.read_text(encoding="utf-8")

        update_causal_graph.save_causal_graph(path, dict(graph))

        assert path.read_text(encoding="utf-8") == first_bytes

    def test_a_graph_that_already_declares_a_version_keeps_it(self, tmp_path):
        path = tmp_path / "g.json"

        update_causal_graph.save_causal_graph(
            path,
            {"version": "2.0", "nodes": [], "edges": [], "patterns": []},
        )

        assert json.loads(path.read_text(encoding="utf-8"))["version"] == "2.0"


class TestPatternIdentityIsStableAndMergeSafe:
    """Patterns are written with a content-derived id (issue #3353)."""

    def test_a_new_pattern_carries_an_id(self):
        graph = {"nodes": [], "edges": [], "patterns": []}

        pattern = update_causal_graph.add_pattern(
            graph,
            "routing pattern",
            "d",
            "t",
            "a",
            1.0,
            "ep-1",
        )

        assert pattern is not None
        assert pattern["id"] == update_causal_graph.generate_pattern_id("routing pattern")

    def test_the_id_is_a_function_of_the_name_alone(self):
        # Two branches processing the same pattern from different episodes,
        # with different success rates, must agree on the id. A sequential
        # allocator would give the same number to two different patterns.
        first = {"nodes": [], "edges": [], "patterns": []}
        second = {"nodes": [], "edges": [], "patterns": []}

        update_causal_graph.add_pattern(first, "shared", "d", "t", "a", 1.0, "ep-1")
        update_causal_graph.add_pattern(second, "shared", "other", "t2", "a2", 0.5, "ep-2")

        assert first["patterns"][0]["id"] == second["patterns"][0]["id"]

    def test_different_names_get_different_ids(self):
        graph = {"nodes": [], "edges": [], "patterns": []}

        update_causal_graph.add_pattern(graph, "one", "d", "t", "a", 1.0, "ep-1")
        update_causal_graph.add_pattern(graph, "two", "d", "t", "a", 1.0, "ep-1")

        assert graph["patterns"][0]["id"] != graph["patterns"][1]["id"]

    def test_a_pattern_written_before_this_fix_gains_an_id_when_touched(self):
        graph = {
            "nodes": [],
            "edges": [],
            "patterns": [
                {
                    "name": "legacy",
                    "description": "d",
                    "trigger": "t",
                    "action": "a",
                    "success_rate": 1.0,
                    "occurrences": 1,
                }
            ],
        }

        update_causal_graph.add_pattern(graph, "legacy", "d", "t", "a", 1.0, "ep-9")

        assert graph["patterns"][0]["id"] == update_causal_graph.generate_pattern_id("legacy")

    def test_reprocessing_an_episode_does_not_change_the_id(self):
        graph = {"nodes": [], "edges": [], "patterns": []}
        update_causal_graph.add_pattern(graph, "stable", "d", "t", "a", 1.0, "ep-1")
        original = graph["patterns"][0]["id"]

        update_causal_graph.add_pattern(graph, "stable", "d", "t", "a", 1.0, "ep-1")

        assert graph["patterns"][0]["id"] == original


# The shape generate_node_id and generate_pattern_id both produce: a
# 12-character lowercase sha256 prefix. Sequential fixture ids (n001, p001)
# fail it on the letter, which is not a hex digit.
_GENERATED_ID = re.compile(r"[0-9a-f]{12}")


class TestTheCommittedGraphCarriesNoTestFixtures:
    """The production graph held test seed rows for months (issue #3352).

    Node ``n001`` and patterns ``p001`` through ``p004`` were written by the
    retired ``reflexion_memory`` writer during a test run on 2026-02-10. They
    carry sequential ids the live generator never emits, empty descriptions,
    and no episodes. No episode reproduces them, so nothing regenerates them.
    """

    GRAPH = (
        Path(__file__).resolve().parents[3]
        / ".agents"
        / "memory"
        / "causality"
        / "causal-graph.json"
    )

    def _graph(self) -> dict:
        return json.loads(self.GRAPH.read_text(encoding="utf-8"))

    def test_every_node_id_has_the_shape_the_generator_produces(self):
        """ "Does not start with n" was the wrong test for "is not n001".

        generate_node_id returns a 12-character sha256 prefix, so the shape is
        the contract and anything else is hand-seeded. The old guard read
        startswith("n"), which is both too broad, it would reject a future
        scheme that happened to begin with that letter, and too narrow, it
        passes any other fixture shape. Asserting the real shape is neither.
        """
        wrong_shape = [
            n["id"] for n in self._graph()["nodes"] if not _GENERATED_ID.fullmatch(n["id"])
        ]

        assert wrong_shape == []

    def test_every_pattern_id_has_the_shape_the_generator_produces(self):
        wrong_shape = [
            p.get("id")
            for p in self._graph()["patterns"]
            if not _GENERATED_ID.fullmatch(p.get("id") or "")
        ]

        assert wrong_shape == []

    def test_every_pattern_carries_an_id_derived_from_its_name(self):
        mismatched = [
            p["name"]
            for p in self._graph()["patterns"]
            if p.get("id") != update_causal_graph.generate_pattern_id(p["name"])
        ]

        assert mismatched == []

    def test_every_pattern_describes_a_real_episode(self):
        # The fixtures were identifiable by an empty description; real
        # patterns name the episode they came from.
        undescribed = [p["name"] for p in self._graph()["patterns"] if not p.get("description")]

        assert undescribed == []

    def test_the_committed_graph_declares_its_version_and_updated(self):
        graph = self._graph()

        assert graph["version"]
        assert graph["updated"]


def _episode_file(directory: Path, episode_id: str, chosen: str) -> Path:
    """Write an episode that yields at least one node and edge."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"episode-{episode_id}.json"
    path.write_text(
        json.dumps(
            {
                "id": episode_id,
                "timestamp": "2026-07-26T00:00:00+00:00",
                "decisions": [{"chosen": chosen, "rationale": "because"}],
                "events": [{"type": "milestone", "content": f"{chosen} shipped"}],
            }
        ),
        encoding="utf-8",
    )
    return path


class TestResetGraphIsTheDocumentedRepairPath:
    """Issue #3370: a corrupt graph is preserved rather than overwritten, so the
    failure has to carry its own repair path. Without one the pre-commit hook
    restores the same corrupt bytes and warns generically on every commit,
    forever, with nothing the user can act on.
    """

    def test_a_corrupt_graph_is_preserved_and_the_run_exits_two(self, tmp_path):
        graph_path = tmp_path / "graph.json"
        graph_path.write_text('{"nodes":[', encoding="utf-8")
        _episode_file(tmp_path / "ep", "ep-1", "Use Python")

        rc = update_causal_graph.main(
            ["--episode-path", str(tmp_path / "ep"), "--graph-path", str(graph_path)]
        )

        assert rc == 2
        assert graph_path.read_text(encoding="utf-8") == '{"nodes":['

    def test_the_failure_names_the_repair_command(self, tmp_path, capsys):
        graph_path = tmp_path / "graph.json"
        graph_path.write_text("not json at all", encoding="utf-8")
        _episode_file(tmp_path / "ep", "ep-1", "Use Python")

        update_causal_graph.main(
            ["--episode-path", str(tmp_path / "ep"), "--graph-path", str(graph_path)]
        )

        err = capsys.readouterr().err
        assert "--reset-graph" in err
        assert "update_causal_graph.py" in err

    def test_reset_rebuilds_a_corrupt_graph(self, tmp_path):
        graph_path = tmp_path / "graph.json"
        graph_path.write_text('{"nodes":[', encoding="utf-8")
        _episode_file(tmp_path / "ep", "ep-1", "Use Python")

        rc = update_causal_graph.main(
            [
                "--episode-path", str(tmp_path / "ep"),
                "--graph-path", str(graph_path),
                "--reset-graph",
            ]
        )

        assert rc == 0
        rebuilt = json.loads(graph_path.read_text(encoding="utf-8"))
        assert rebuilt["nodes"], "reset must rebuild content from the episodes on disk"

    def test_reset_drops_state_no_episode_on_disk_supports(self, tmp_path):
        """The proof that reset rebuilds rather than merges: a node whose only
        supporting episode is gone from disk must not survive the repair.
        """
        graph_path = tmp_path / "graph.json"
        stale = update_causal_graph._empty_graph()
        update_causal_graph.add_causal_node(stale, "decision", "Deleted", "ep-gone")
        graph_path.write_text(json.dumps(stale), encoding="utf-8")
        _episode_file(tmp_path / "ep", "ep-1", "Use Python")

        rc = update_causal_graph.main(
            [
                "--episode-path", str(tmp_path / "ep"),
                "--graph-path", str(graph_path),
                "--reset-graph",
            ]
        )

        assert rc == 0
        rebuilt = json.loads(graph_path.read_text(encoding="utf-8"))
        assert all("ep-gone" not in n.get("episodes", []) for n in rebuilt["nodes"])

    def test_reset_on_a_missing_graph_file_writes_one(self, tmp_path):
        graph_path = tmp_path / "absent" / "graph.json"
        _episode_file(tmp_path / "ep", "ep-1", "Use Python")

        rc = update_causal_graph.main(
            [
                "--episode-path", str(tmp_path / "ep"),
                "--graph-path", str(graph_path),
                "--reset-graph",
            ]
        )

        assert rc == 0
        assert graph_path.exists()

    def test_reset_with_no_episodes_still_writes_an_empty_graph(self, tmp_path):
        """The no-episodes early return would otherwise leave the corrupt file
        in place and report success, which is the failure this flag exists to
        prevent.
        """
        graph_path = tmp_path / "graph.json"
        graph_path.write_text('{"nodes":[', encoding="utf-8")

        rc = update_causal_graph.main(
            [
                "--episode-path", str(tmp_path / "no-such-dir"),
                "--graph-path", str(graph_path),
                "--reset-graph",
            ]
        )

        assert rc == 0
        rebuilt = json.loads(graph_path.read_text(encoding="utf-8"))
        assert rebuilt["nodes"] == []

    def test_a_valid_graph_is_untouched_by_the_new_error_path(self, tmp_path):
        """Negative control on the try/except: a healthy run must still load and
        extend the existing graph rather than fall into the repair branch.
        """
        graph_path = tmp_path / "graph.json"
        seeded = update_causal_graph._empty_graph()
        update_causal_graph.add_causal_node(seeded, "decision", "Kept", "ep-0")
        graph_path.write_text(json.dumps(seeded), encoding="utf-8")
        _episode_file(tmp_path / "ep", "ep-1", "Use Python")

        rc = update_causal_graph.main(
            ["--episode-path", str(tmp_path / "ep"), "--graph-path", str(graph_path)]
        )

        assert rc == 0
        rebuilt = json.loads(graph_path.read_text(encoding="utf-8"))
        assert any("ep-0" in n.get("episodes", []) for n in rebuilt["nodes"])


def _hook_repair_command(graph_path, repo_root):
    """Import the wrapper's helper without putting the whole module on sys.path."""
    validation = Path(__file__).resolve().parents[3] / "scripts" / "validation"
    spec = importlib.util.spec_from_file_location(
        "_ghp_for_repair_tests", validation / "git_hook_policy.py"
    )
    module = importlib.util.module_from_spec(spec)
    # Registered before exec because the module defines slotted dataclasses,
    # which resolve their own module out of sys.modules during class creation.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        return module._causal_repair_command(graph_path, repo_root)
    finally:
        sys.modules.pop(spec.name, None)


class TestTheHookWarningNamesTheRepair:
    """The wrapper restores the file as found, so a corrupt graph stays corrupt.
    Its warning has to name the same repair command the script prints.
    """

    def test_the_restore_warning_cites_the_reset_flag(self):
        source = (
            Path(__file__).resolve().parents[3]
            / "scripts" / "validation" / "git_hook_policy.py"
        ).read_text(encoding="utf-8")
        marker = "causal graph update failed; original graph restored"
        assert marker in source
        tail = source.split(marker, 1)[1][:600]
        assert "_causal_repair_command(" in tail

    def test_the_wrapper_command_carries_the_reset_flag(self):
        command = _hook_repair_command(Path("/repo/g.json"), Path("/repo"))
        assert "--reset-graph" in shlex.split(command)

    def test_the_wrapper_command_names_the_on_disk_episode_directory(self):
        argv = shlex.split(_hook_repair_command(Path("/repo/g.json"), Path("/repo")))
        assert argv[argv.index("--episode-path") + 1] == ".agents/memory/episodes"

    def test_the_wrapper_command_names_the_graph_it_just_restored(self):
        graph = Path("/repo/.agents/memory/causality/causal-graph.json")
        argv = shlex.split(_hook_repair_command(graph, Path("/repo")))
        assert argv[argv.index("--graph-path") + 1] == (
            ".agents/memory/causality/causal-graph.json"
        )

    def test_a_graph_outside_the_repo_keeps_its_absolute_path(self):
        argv = shlex.split(_hook_repair_command(Path("/other place/g.json"), Path("/repo")))
        assert argv[argv.index("--graph-path") + 1] == "/other place/g.json"

    def test_the_wrapper_runs_the_script_its_advice_names(self):
        """One home for the path: the subprocess and the advice cannot drift."""
        source = (
            Path(__file__).resolve().parents[3]
            / "scripts" / "validation" / "git_hook_policy.py"
        ).read_text(encoding="utf-8")
        assert ".claude/skills/memory/scripts/update_causal_graph.py" not in (
            source.split("_CAUSAL_UPDATER = ", 1)[1].split("\n", 1)[1]
        )


def _repair_argv(tmp_path, capsys, graph_path=None):
    """Run a load failure and return the printed repair command, shell-split.

    ``shlex.split`` rather than ``str.split`` so a quoted path with spaces
    stays one argument, which is the whole point of quoting it.
    """
    graph = graph_path if graph_path is not None else tmp_path / "graph.json"
    graph.write_text("{", encoding="utf-8")
    _episode_file(tmp_path / "ep", "ep-1", "Use Python")

    assert update_causal_graph.main(
        ["--episode-path", str(tmp_path / "ep"), "--graph-path", str(graph)]
    ) == 2

    err = capsys.readouterr().err
    printed = [ln for ln in err.splitlines() if "--reset-graph" in ln]
    assert printed, "the failure must print the repair command"
    return shlex.split(printed[0])


class TestTheRepairPathIsDerivedNotHardCoded:
    """This file is mirrored into the Copilot CLI plugin, where an upstream
    ``.claude/...`` literal names a path that does not exist. The vendor
    portability ratchet (issue #2050) rejects the literal, so the repair
    command has to name the script's own location.
    """

    def test_the_repair_path_resolves_to_this_script(self):
        resolved = (Path.cwd() / update_causal_graph._repair_invocation()).resolve()
        assert resolved == Path(update_causal_graph.__file__).resolve()

    def test_the_path_is_relative_when_the_script_sits_under_the_cwd(self, monkeypatch):
        monkeypatch.chdir(Path(update_causal_graph.__file__).resolve().parents[4])
        assert not Path(update_causal_graph._repair_invocation()).is_absolute()

    def test_the_path_is_absolute_when_the_script_sits_outside_the_cwd(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        invocation = update_causal_graph._repair_invocation()
        assert Path(invocation).is_absolute()
        assert Path(invocation).exists()

    def test_the_printed_script_path_exists_on_disk(self, tmp_path, capsys):
        """A repair command naming a script the reader does not have is not advice."""
        argv = _repair_argv(tmp_path, capsys)
        assert Path(argv[1]).exists()


class TestTheRepairCommandNamesThePathsInPlay:
    """A bare ``--reset-graph`` rebuilds paths derived from the script's own
    location, which differ between the canonical tree and the Copilot CLI
    mirror, and ignore any ``--graph-path`` the caller passed. Copy-pasting it
    could rebuild somewhere other than the file that just failed to load.
    """

    def test_the_command_repeats_the_callers_graph_path(self, tmp_path, capsys):
        argv = _repair_argv(tmp_path, capsys)
        assert argv[argv.index("--graph-path") + 1] == str(tmp_path / "graph.json")

    def test_the_command_repeats_the_callers_episode_path(self, tmp_path, capsys):
        argv = _repair_argv(tmp_path, capsys)
        assert argv[argv.index("--episode-path") + 1] == str(tmp_path / "ep")

    def test_a_path_with_spaces_survives_a_shell_round_trip(self, tmp_path, capsys):
        target = tmp_path / "two words"
        target.mkdir()
        argv = _repair_argv(tmp_path, capsys, graph_path=target / "graph.json")
        assert argv[argv.index("--graph-path") + 1] == str(target / "graph.json")

    def test_the_pasted_command_actually_rebuilds_the_corrupt_file(
        self, tmp_path, capsys
    ):
        argv = _repair_argv(tmp_path, capsys)
        graph = tmp_path / "graph.json"
        assert update_causal_graph.main(argv[2:]) == 0
        assert json.loads(graph.read_text(encoding="utf-8"))["nodes"]
