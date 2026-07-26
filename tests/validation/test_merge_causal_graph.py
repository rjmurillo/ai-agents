"""Tests for the causal graph merge driver and its registration.

Issue #3345: every merge of the default branch conflicted on the generated
causal graph, and the documented workaround silently deleted graph state. These
cover the union semantics, the loud-failure contract, and the wiring that keeps
a `.gitattributes` entry from becoming a no-op.
"""

from __future__ import annotations

import errno
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, TextIO

import pytest

from scripts.maintenance import install_merge_drivers
from scripts.validation import merge_causal_graph
from scripts.validation.merge_causal_graph import (
    GraphMergeError,
    _atomic_write_text,
    _load,
    main,
    merge_graphs,
)

_ROOT = Path(__file__).resolve().parents[2]
_DRIVER = "scripts/validation/merge_causal_graph.py"


def _node(node_id: str, **overrides: Any) -> dict[str, Any]:
    node = {
        "id": node_id,
        "type": "decision",
        "label": f"node {node_id}",
        "episodes": [f"episode-{node_id}"],
        "created": "2026-01-01T00:00:00+00:00",
    }
    node.update(overrides)
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


# Git invokes merge drivers through sh even on Windows, so a native interpreter
# path like D:\\hostedtoolcache\\python.exe loses its backslashes to shell
# escaping. Render it POSIX-style and quote it, matching how this repository
# feeds interpreter paths to lefthook run strings.
_PYTHON_POSIX = Path(sys.executable).as_posix()
_DRIVER_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "validation" / "merge_causal_graph.py"
).as_posix()
_DRIVER_COMMAND = f'"{_PYTHON_POSIX}" "{_DRIVER_SCRIPT}" "%O" "%A" "%B"'


class TestRecordsWithoutIdentityFieldsAreNotCollapsed:
    """Six of the ten patterns in the committed graph carry no ``id``.

    Keying those on the absent field gave every one of them the same empty key,
    so a union merge kept one and silently dropped five. Caught on real data
    while merging this branch, not in a fixture.
    """

    @staticmethod
    def _pattern(name: str) -> dict[str, object]:
        return {"name": name, "description": f"Pattern from {name}", "occurrences": 1}

    def test_distinct_id_less_records_all_survive(self) -> None:
        shared = self._pattern("shared")
        base = _graph(patterns=[shared])
        ours = _graph(patterns=[shared, self._pattern("ours-a"), self._pattern("ours-b")])
        theirs = _graph(patterns=[shared, self._pattern("theirs-a")])

        merged = merge_graphs(base, ours, theirs)

        names = sorted(p["name"] for p in merged["patterns"])
        assert names == ["ours-a", "ours-b", "shared", "theirs-a"]

    def test_an_identical_id_less_record_is_not_duplicated(self) -> None:
        """Content keying still matches an untouched record across both sides."""
        shared = self._pattern("shared")
        merged = merge_graphs(
            _graph(patterns=[shared]), _graph(patterns=[shared]), _graph(patterns=[shared])
        )

        assert len(merged["patterns"]) == 1

    def test_a_partially_keyed_record_still_uses_its_identity_fields(self) -> None:
        """An edge missing only ``type`` keeps matching on source and target."""
        base = _graph(edges=[{"source": "a", "target": "b", "evidence_count": 1}])
        ours = _graph(edges=[{"source": "a", "target": "b", "evidence_count": 3}])
        theirs = _graph(edges=[{"source": "a", "target": "b", "evidence_count": 4}])

        merged = merge_graphs(base, ours, theirs)

        assert len(merged["edges"]) == 1
        assert merged["edges"][0]["evidence_count"] == 6

    def test_malformed_edges_sharing_one_identity_field_all_survive(self) -> None:
        """PR #3348 review: a partial identity keyed on a half-empty tuple.

        Three edges carrying only ``source`` all keyed to ``("a", "")`` under
        the old any-field rule, so the union kept one and dropped two. That is
        the same collapse the id-less patterns hit, in the one shape the driver
        promises to tolerate: malformed records must not cost good ones.
        """
        malformed = [
            {"source": "a", "evidence_count": 1},
            {"source": "a", "evidence_count": 2},
            {"source": "a", "evidence_count": 3},
        ]

        merged = merge_graphs(_graph(), _graph(edges=malformed), _graph())

        assert sorted(e["evidence_count"] for e in merged["edges"]) == [1, 2, 3]

    def test_a_partial_identity_does_not_match_a_complete_one(self) -> None:
        """An edge missing ``target`` is a different record, not the same one."""
        complete = {"source": "a", "target": "b", "evidence_count": 1}
        partial = {"source": "a", "evidence_count": 9}

        merged = merge_graphs(_graph(), _graph(edges=[complete]), _graph(edges=[partial]))

        assert len(merged["edges"]) == 2

    def test_patterns_key_on_name_and_merge_counters(self) -> None:
        """Patterns are keyed by name, not id, aligning with the generator."""
        base = _graph(patterns=[{"name": "shared", "occurrences": 1}])
        ours = _graph(patterns=[{"name": "shared", "occurrences": 3}])
        theirs = _graph(patterns=[{"name": "shared", "occurrences": 4}])

        merged = merge_graphs(base, ours, theirs)

        assert len(merged["patterns"]) == 1
        assert merged["patterns"][0]["name"] == "shared"
        assert merged["patterns"][0]["occurrences"] == 6


class TestUnionSemantics:
    """Both sides survive. Taking one side is what caused the drift."""

    def test_disjoint_nodes_from_both_sides_survive(self) -> None:
        base = _graph(nodes=[_node("shared")])
        ours = _graph(nodes=[_node("shared"), _node("ours")])
        theirs = _graph(nodes=[_node("shared"), _node("theirs")])
        merged = merge_graphs(base, ours, theirs)
        assert {n["id"] for n in merged["nodes"]} == {"shared", "ours", "theirs"}

    def test_a_record_present_on_both_sides_appears_once(self) -> None:
        graph = _graph(nodes=[_node("shared")])
        merged = merge_graphs(graph, graph, graph)
        assert [n["id"] for n in merged["nodes"]] == ["shared"]

    def test_edges_key_on_the_pair_they_connect(self) -> None:
        """Edges with the same source/target but different types merge as one.

        The generator (update_causal_graph.py) enforces at most one edge per
        (source, target) pair, so the merge driver must do the same. When two
        branches change the type field differently, the merge keeps one record
        rather than emitting two edges for the same pair.
        """
        edge = {"source": "a", "target": "b", "type": "causes", "evidence_count": 1}
        other = {"source": "a", "target": "b", "type": "enables", "evidence_count": 1}
        merged = merge_graphs(_graph(), _graph(edges=[edge]), _graph(edges=[other]))
        assert len(merged["edges"]) == 1
        assert merged["edges"][0]["source"] == "a"
        assert merged["edges"][0]["target"] == "b"

    def test_union_is_independent_of_which_side_git_calls_ours(self) -> None:
        base = _graph(nodes=[_node("shared")])
        a = _graph(nodes=[_node("shared"), _node("a")])
        b = _graph(nodes=[_node("shared"), _node("b")])
        forward = {n["id"] for n in merge_graphs(base, a, b)["nodes"]}
        reverse = {n["id"] for n in merge_graphs(base, b, a)["nodes"]}
        assert forward == reverse

    def test_an_unknown_top_level_key_is_carried_not_dropped(self) -> None:
        """The schema may grow; a merge must not silently truncate it."""
        merged = merge_graphs(_graph(), _graph(cohorts=[1]), _graph())
        assert merged["cohorts"] == [1]


class TestCounterReconciliation:
    """Counters merge three-way. Summing would double-count the shared ancestor."""

    def _counted(self, base: int, ours: int, theirs: int) -> int:
        edge = {"source": "a", "target": "b", "type": "causes"}
        merged = merge_graphs(
            _graph(edges=[{**edge, "evidence_count": base}]),
            _graph(edges=[{**edge, "evidence_count": ours}]),
            _graph(edges=[{**edge, "evidence_count": theirs}]),
        )
        count = merged["edges"][0]["evidence_count"]
        assert isinstance(count, int)
        return count

    def test_both_sides_deltas_apply(self) -> None:
        assert self._counted(68, 71, 73) == 76

    def test_a_counter_neither_side_touched_is_unchanged(self) -> None:
        assert self._counted(68, 68, 68) == 68

    def test_one_sided_change_is_not_doubled(self) -> None:
        assert self._counted(10, 15, 10) == 15

    def test_a_decrease_cannot_drive_the_counter_negative(self) -> None:
        assert self._counted(4, 0, 0) == 0

    def test_new_shared_record_does_not_double_count(self) -> None:
        """Both branches independently adding the same record takes max, not sum.

        Regression test for a bug where a record absent from the ancestor but
        present on both sides with the same counter value would double that
        value (e.g., 5 and 5 became 10) instead of keeping a single copy.
        """
        edge = {"source": "a", "target": "b", "type": "causes", "evidence_count": 5}
        merged = merge_graphs(
            _graph(edges=[]),
            _graph(edges=[edge]),
            _graph(edges=[edge]),
        )
        assert merged["edges"][0]["evidence_count"] == 5

    def test_new_shared_record_with_differing_counts_takes_max(self) -> None:
        """When no ancestor exists, take the higher count, not the sum."""
        edge = {"source": "a", "target": "b", "type": "causes"}
        merged = merge_graphs(
            _graph(edges=[]),
            _graph(edges=[{**edge, "evidence_count": 3}]),
            _graph(edges=[{**edge, "evidence_count": 7}]),
        )
        assert merged["edges"][0]["evidence_count"] == 7


class TestFieldPolicies:
    def test_episode_lists_union_and_deduplicate(self) -> None:
        merged = merge_graphs(
            _graph(nodes=[_node("n", episodes=["a"])]),
            _graph(nodes=[_node("n", episodes=["a", "b"])]),
            _graph(nodes=[_node("n", episodes=["a", "c"])]),
        )
        assert merged["nodes"][0]["episodes"] == ["a", "b", "c"]

    def test_created_takes_the_earliest(self) -> None:
        merged = merge_graphs(
            _graph(),
            _graph(nodes=[_node("n", created="2026-05-01T00:00:00+00:00")]),
            _graph(nodes=[_node("n", created="2026-02-01T00:00:00+00:00")]),
        )
        assert merged["nodes"][0]["created"] == "2026-02-01T00:00:00+00:00"

    def test_last_used_takes_the_latest(self) -> None:
        pattern = {"id": "p", "name": "p"}
        merged = merge_graphs(
            _graph(),
            _graph(patterns=[{**pattern, "last_used": "2026-02-01"}]),
            _graph(patterns=[{**pattern, "last_used": "2026-05-01"}]),
        )
        assert merged["patterns"][0]["last_used"] == "2026-05-01"

    def test_updated_takes_the_latest(self) -> None:
        merged = merge_graphs(
            _graph(),
            _graph(updated="2026-02-01"),
            _graph(updated="2026-05-01"),
        )
        assert merged["updated"] == "2026-05-01"

    def test_a_field_only_one_side_changed_takes_that_side(self) -> None:
        merged = merge_graphs(
            _graph(nodes=[_node("n", label="original")]),
            _graph(nodes=[_node("n", label="original")]),
            _graph(nodes=[_node("n", label="changed")]),
        )
        assert merged["nodes"][0]["label"] == "changed"


class TestMalformedInputIsToleratedNotFatal:
    """A generated file with one bad record should still merge the good ones."""

    def test_a_non_list_collection_is_ignored(self) -> None:
        merged = merge_graphs(_graph(), _graph(nodes="oops"), _graph(nodes=[_node("n")]))
        assert [n["id"] for n in merged["nodes"]] == ["n"]

    def test_a_non_object_record_is_dropped(self) -> None:
        merged = merge_graphs(_graph(), _graph(nodes=["oops", _node("n")]), _graph())
        assert [n["id"] for n in merged["nodes"]] == ["n"]

    def test_an_empty_ancestor_is_an_add_add_not_an_error(self) -> None:
        """Git passes an empty ancestor when both sides created the file."""
        merged = merge_graphs({}, _graph(nodes=[_node("a")]), _graph(nodes=[_node("b")]))
        assert {n["id"] for n in merged["nodes"]} == {"a", "b"}


class TestLoadRefusesWhatItCannotTrust:
    def test_an_empty_ancestor_is_an_empty_graph(self, tmp_path: Path) -> None:
        """Git passes an empty ancestor for an add/add conflict. That is normal."""
        path = tmp_path / "base.json"
        path.write_text("", encoding="utf-8")
        assert _load(path, "ancestor", may_be_empty=True) == {}

    def test_an_empty_side_is_refused(self, tmp_path: Path) -> None:
        """A truncated ours or theirs must not merge cleanly as an empty graph.

        Reading it as {} would delete everything the other side has, which is
        the silent data loss the driver exists to prevent.
        """
        path = tmp_path / "ours.json"
        path.write_text("   \n", encoding="utf-8")
        with pytest.raises(GraphMergeError, match="empty"):
            _load(path, "ours")

    def test_unparseable_file_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "ours.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(GraphMergeError, match="not valid JSON"):
            _load(path, "ours")

    def test_json_that_is_not_an_object_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "ours.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(GraphMergeError, match="expected an object"):
            _load(path, "ours")

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(GraphMergeError, match="cannot read"):
            _load(tmp_path / "absent.json", "theirs")


class TestDriverExitContract:
    """git keys off the exit code: nonzero means leave the conflict alone."""

    def _write(self, tmp_path: Path, name: str, payload: object) -> Path:
        path = tmp_path / name
        path.write_text(
            payload if isinstance(payload, str) else json.dumps(payload),
            encoding="utf-8",
        )
        return path

    def test_successful_merge_exits_zero_and_writes_ours(self, tmp_path: Path) -> None:
        base = self._write(tmp_path, "base.json", _graph())
        ours = self._write(tmp_path, "ours.json", _graph(nodes=[_node("a")]))
        theirs = self._write(tmp_path, "theirs.json", _graph(nodes=[_node("b")]))
        assert main([str(base), str(ours), str(theirs)]) == 0
        written = json.loads(ours.read_text(encoding="utf-8"))
        assert {n["id"] for n in written["nodes"]} == {"a", "b"}

    @pytest.mark.skipif(os.name == "nt", reason="Windows does not expose POSIX mode bits")
    def test_successful_merge_preserves_destination_mode(self, tmp_path: Path) -> None:
        base = self._write(tmp_path, "base.json", _graph())
        ours = self._write(tmp_path, "ours.json", _graph(nodes=[_node("ours")]))
        theirs = self._write(tmp_path, "theirs.json", _graph(nodes=[_node("theirs")]))
        ours.chmod(0o640)

        assert main([str(base), str(ours), str(theirs)]) == 0
        assert stat.S_IMODE(ours.stat().st_mode) == 0o640

    def test_corrupt_side_exits_one_and_leaves_ours_untouched(self, tmp_path: Path) -> None:
        """The behavior that stops a silent side-take from deleting graph state."""
        base = self._write(tmp_path, "base.json", _graph())
        ours = self._write(tmp_path, "ours.json", _graph(nodes=[_node("a")]))
        theirs = self._write(tmp_path, "theirs.json", "{corrupt")
        before = ours.read_text(encoding="utf-8")
        assert main([str(base), str(ours), str(theirs)]) == 1
        assert ours.read_text(encoding="utf-8") == before

    def test_corrupt_ours_exits_one(self, tmp_path: Path) -> None:
        base = self._write(tmp_path, "base.json", _graph())
        ours = self._write(tmp_path, "ours.json", "{corrupt")
        theirs = self._write(tmp_path, "theirs.json", _graph())
        assert main([str(base), str(ours), str(theirs)]) == 1

    def test_missing_input_exits_one(self, tmp_path: Path) -> None:
        ours = self._write(tmp_path, "ours.json", _graph())
        theirs = self._write(tmp_path, "theirs.json", _graph())
        assert main([str(tmp_path / "absent.json"), str(ours), str(theirs)]) == 1

    def test_an_unwritable_destination_exits_three_without_truncating_ours(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed final replace leaves Git's merge-result input untouched."""
        base = self._write(tmp_path, "base.json", _graph())
        ours = self._write(tmp_path, "ours.json", _graph(nodes=[_node("ours")]))
        theirs = self._write(tmp_path, "theirs.json", _graph(nodes=[_node("theirs")]))
        before = ours.read_text(encoding="utf-8")

        def refuse(_source: object, _target: object) -> None:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(merge_causal_graph.os, "replace", refuse)

        assert main([str(base), str(ours), str(theirs)]) == 3
        assert ours.read_text(encoding="utf-8") == before
        assert list(tmp_path.glob("*.tmp")) == []

    def test_a_partial_temporary_write_leaves_ours_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base = self._write(tmp_path, "base.json", _graph())
        ours = self._write(tmp_path, "ours.json", _graph(nodes=[_node("ours")]))
        theirs = self._write(tmp_path, "theirs.json", _graph(nodes=[_node("theirs")]))
        before = ours.read_text(encoding="utf-8")
        original_fdopen = merge_causal_graph.os.fdopen

        class PartialWriter:
            def __init__(self, fd: int) -> None:
                self._handle: TextIO = original_fdopen(fd, "w", encoding="utf-8")

            def write(self, text: str) -> None:
                self._handle.write(text[:1])
                self._handle.flush()
                raise OSError(28, "No space left on device")

            def close(self) -> None:
                self._handle.close()

        def fail_after_partial_write(fd: int, _mode: str, *, encoding: str) -> PartialWriter:
            assert encoding == "utf-8"
            return PartialWriter(fd)

        monkeypatch.setattr(merge_causal_graph.os, "fdopen", fail_after_partial_write)

        assert main([str(base), str(ours), str(theirs)]) == 3
        assert ours.read_text(encoding="utf-8") == before
        assert list(tmp_path.glob("*.tmp")) == []

    def test_fdopen_failure_closes_descriptor_and_leaves_ours_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base = self._write(tmp_path, "base.json", _graph())
        ours = self._write(tmp_path, "ours.json", _graph(nodes=[_node("ours")]))
        theirs = self._write(tmp_path, "theirs.json", _graph(nodes=[_node("theirs")]))
        before = ours.read_text(encoding="utf-8")
        captured_fd: list[int] = []

        def refuse_fdopen(fd: int, _mode: str, *, encoding: str) -> TextIO:
            assert encoding == "utf-8"
            captured_fd.append(fd)
            raise OSError(24, "Too many open files")

        monkeypatch.setattr(merge_causal_graph.os, "fdopen", refuse_fdopen)

        assert main([str(base), str(ours), str(theirs)]) == 3
        assert len(captured_fd) == 1
        with pytest.raises(OSError) as closed:
            os.fstat(captured_fd[0])
        assert closed.value.errno == errno.EBADF
        assert ours.read_text(encoding="utf-8") == before
        assert list(tmp_path.glob("*.tmp")) == []

    def test_close_failure_does_not_mask_a_partial_write_failure(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        base = self._write(tmp_path, "base.json", _graph())
        ours = self._write(tmp_path, "ours.json", _graph(nodes=[_node("ours")]))
        theirs = self._write(tmp_path, "theirs.json", _graph(nodes=[_node("theirs")]))
        before = ours.read_text(encoding="utf-8")
        original_fdopen = merge_causal_graph.os.fdopen

        class WriteAndCloseFailure:
            def __init__(self, fd: int) -> None:
                self._handle: TextIO = original_fdopen(fd, "w", encoding="utf-8")

            def write(self, text: str) -> None:
                self._handle.write(text[:1])
                self._handle.flush()
                raise OSError(28, "No space left on device")

            def close(self) -> None:
                self._handle.close()
                raise OSError(5, "Input/output error")

        def fail_write_and_close(fd: int, _mode: str, *, encoding: str) -> WriteAndCloseFailure:
            assert encoding == "utf-8"
            return WriteAndCloseFailure(fd)

        monkeypatch.setattr(merge_causal_graph.os, "fdopen", fail_write_and_close)

        assert main([str(base), str(ours), str(theirs)]) == 3
        error = capsys.readouterr().err
        assert "No space left on device" in error
        assert "failed to close temporary file" in error
        assert "Input/output error" in error
        assert ours.read_text(encoding="utf-8") == before
        assert list(tmp_path.glob("*.tmp")) == []

    def test_cleanup_failure_reports_primary_and_cleanup_errors(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        base = self._write(tmp_path, "base.json", _graph())
        ours = self._write(tmp_path, "ours.json", _graph(nodes=[_node("ours")]))
        theirs = self._write(tmp_path, "theirs.json", _graph(nodes=[_node("theirs")]))

        def refuse_replace(_source: object, _target: object) -> None:
            raise OSError(28, "No space left on device")

        def refuse_cleanup(_path: Path, missing_ok: bool = False) -> None:
            assert missing_ok
            raise OSError(13, "Permission denied")

        monkeypatch.setattr(merge_causal_graph.os, "replace", refuse_replace)
        monkeypatch.setattr(Path, "unlink", refuse_cleanup)

        assert main([str(base), str(ours), str(theirs)]) == 3
        error = capsys.readouterr().err
        assert "No space left on device" in error
        assert "failed to remove temporary file" in error
        assert "Permission denied" in error


class TestGitActuallyUsesTheDriver:
    """An end-to-end merge, because the unit tests cannot prove git invokes it."""

    def _git(self, repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    @pytest.fixture
    def repo(self, tmp_path: Path) -> Path:
        repo = tmp_path / "repo"
        (repo / ".agents/memory/causality").mkdir(parents=True)
        (repo / "scripts/validation").mkdir(parents=True)
        (repo / "scripts/validation/merge_causal_graph.py").write_text(
            (_ROOT / _DRIVER).read_text(encoding="utf-8"), encoding="utf-8"
        )
        (repo / ".gitattributes").write_text(
            ".agents/memory/causality/causal-graph.json merge=causal-graph\n",
            encoding="utf-8",
        )
        graph = repo / ".agents/memory/causality/causal-graph.json"
        graph.write_text(json.dumps(_graph(nodes=[_node("shared")])), encoding="utf-8")

        self._git(repo, "init", "-q", ".")
        self._git(repo, "config", "user.email", "test@example.com")
        self._git(repo, "config", "user.name", "test")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-qm", "base")
        # `checkout -` is unreliable in a fresh repo; pin the trunk name.
        self._trunk = self._git(repo, "branch", "--show-current").stdout.strip()
        return repo

    def _diverge(self, repo: Path) -> None:
        graph = repo / ".agents/memory/causality/causal-graph.json"
        self._git(repo, "checkout", "-qb", "feature")
        graph.write_text(
            json.dumps(_graph(nodes=[_node("shared"), _node("feature")])), encoding="utf-8"
        )
        self._git(repo, "commit", "-qam", "feature side")
        self._git(repo, "checkout", "-q", self._trunk)
        graph.write_text(
            json.dumps(_graph(nodes=[_node("shared"), _node("trunk")])), encoding="utf-8"
        )
        self._git(repo, "commit", "-qam", "trunk side")

    def test_without_registration_the_merge_conflicts(self, repo: Path) -> None:
        """The negative control: `.gitattributes` alone is a no-op."""
        self._diverge(repo)
        result = self._git(repo, "merge", "feature")
        assert result.returncode != 0
        assert "CONFLICT" in result.stdout + result.stderr

    def test_with_registration_the_merge_succeeds_and_keeps_both_sides(self, repo: Path) -> None:
        self._diverge(repo)
        self._git(repo, "config", "merge.causal-graph.name", "union")
        self._git(
            repo,
            "config",
            "merge.causal-graph.driver",
            _DRIVER_COMMAND,
        )
        result = self._git(repo, "merge", "feature")
        assert result.returncode == 0, result.stdout + result.stderr
        graph = json.loads(
            (repo / ".agents/memory/causality/causal-graph.json").read_text(encoding="utf-8")
        )
        assert {n["id"] for n in graph["nodes"]} == {"shared", "feature", "trunk"}

    def test_the_command_git_is_actually_given_resolves_from_a_subdirectory(
        self, repo: Path
    ) -> None:
        """PR #3348 review: every other e2e test registered an absolute path.

        The command the installer really writes carries a repo-relative script
        path, so those tests passed while proving nothing about the assumption
        the relative form rests on: that git runs a merge driver from the top of
        the working tree even when the merge was invoked from a subdirectory.
        A fresh clone would have been the first place that assumption was tried.

        Registers the exact strings from ``_DRIVERS`` and merges from
        ``.agents/memory/causality`` so a regression to a cwd-relative lookup
        shows up here instead of on somebody's machine.
        """
        driver = install_merge_drivers._DRIVERS["causal-graph"]
        assert "scripts/validation/merge_causal_graph.py" in driver["driver"]
        assert str(_ROOT) not in driver["driver"].split('" ', 1)[-1], (
            "the script path must stay repo-relative for a fresh clone to work"
        )

        self._diverge(repo)
        for setting, value in driver.items():
            self._git(repo, "config", f"merge.causal-graph.{setting}", value)

        subdirectory = repo / ".agents" / "memory" / "causality"
        result = self._git(subdirectory, "merge", "feature")

        assert result.returncode == 0, result.stdout + result.stderr
        graph = json.loads(
            (repo / ".agents/memory/causality/causal-graph.json").read_text(encoding="utf-8")
        )
        assert {n["id"] for n in graph["nodes"]} == {"shared", "feature", "trunk"}

    def test_a_corrupt_side_still_conflicts_rather_than_taking_ours(self, repo: Path) -> None:
        graph = repo / ".agents/memory/causality/causal-graph.json"
        self._git(repo, "checkout", "-qb", "feature")
        graph.write_text("{corrupt", encoding="utf-8")
        self._git(repo, "commit", "-qam", "corrupt side")
        self._git(repo, "checkout", "-q", self._trunk)
        graph.write_text(
            json.dumps(_graph(nodes=[_node("shared"), _node("trunk")])), encoding="utf-8"
        )
        self._git(repo, "commit", "-qam", "trunk side")
        self._git(repo, "config", "merge.causal-graph.name", "union")
        self._git(
            repo,
            "config",
            "merge.causal-graph.driver",
            _DRIVER_COMMAND,
        )
        result = self._git(repo, "merge", "feature")
        assert result.returncode != 0
        assert "CONFLICT" in result.stdout + result.stderr


class TestRegistrationIsWiredAndIdempotent:
    """A driver nobody registers is a driver that never runs."""

    def test_the_docstring_names_the_script_lefthook_actually_runs(self) -> None:
        """PR #3348 review: the docstring credited a script that never runs it.

        A wrong pointer here costs a maintainer the whole debugging session,
        because the file they are told to inspect has nothing to do with the
        driver being missing. Read the runner out of lefthook.yml so the claim
        cannot drift from the wiring again.
        """
        lefthook = (_ROOT / "lefthook.yml").read_text(encoding="utf-8")
        runners = [
            line.split("python", 1)[1].strip()
            for line in lefthook.splitlines()
            if "install_merge_drivers.py" in line and "run:" in line
        ]
        assert runners, "lefthook.yml no longer runs install_merge_drivers.py"

        docstring = merge_causal_graph.__doc__ or ""
        assert runners[0] in docstring, (
            f"module docstring must name {runners[0]}, the script lefthook runs"
        )
        assert "git_hook_policy.py install-merge-drivers" not in docstring

    def test_gitattributes_routes_the_graph_to_the_driver(self) -> None:
        attributes = (_ROOT / ".gitattributes").read_text(encoding="utf-8")
        assert ".agents/memory/causality/causal-graph.json merge=causal-graph" in attributes

    def test_the_installer_runs_from_a_hook(self) -> None:
        """Registration must not depend on a setup step someone can skip."""
        lefthook = (_ROOT / "lefthook.yml").read_text(encoding="utf-8")
        assert "scripts/maintenance/install_merge_drivers.py" in lefthook

    def test_the_registered_command_points_at_the_driver(self) -> None:
        from scripts.maintenance.install_merge_drivers import _DRIVERS

        assert _DRIVER in _DRIVERS["causal-graph"]["driver"]
        assert _DRIVERS["causal-graph"]["driver"].endswith('"%O" "%A" "%B"')

    def test_the_driver_is_stdlib_only(self) -> None:
        """The premise of registering a bare interpreter instead of `uv run`.

        If this driver ever imports a third-party package, the registered
        command stops being sufficient and every clone that has not synced its
        environment falls back to the text merge.
        """
        import ast

        tree = ast.parse((_ROOT / _DRIVER).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])

        assert imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names)

    def test_the_registered_command_does_not_route_through_a_package_manager(self) -> None:
        """A merge must not need uv, a network, or a synced environment.

        Routing the driver through `uv run` fails wherever uv cannot run, and a
        failed merge driver is not a loud error. Git falls back to the text
        merge, which is exactly the conflict issue #3345 exists to remove.
        """
        from scripts.maintenance.install_merge_drivers import _DRIVERS

        command = _DRIVERS["causal-graph"]["driver"]

        assert not command.startswith("uv ")
        assert "uv run" not in command
        assert command.startswith('"')

    def test_the_registered_interpreter_exists_and_runs_the_driver(self, tmp_path: Path) -> None:
        """The baked path must be a working interpreter, not just a string."""
        from scripts.maintenance.install_merge_drivers import _DRIVERS

        interpreter = _DRIVERS["causal-graph"]["driver"].split('"')[1]

        assert Path(interpreter).is_file()

        base = tmp_path / "b.json"
        ours = tmp_path / "o.json"
        theirs = tmp_path / "t.json"
        base.write_text(json.dumps({"nodes": [{"id": "a"}]}), encoding="utf-8")
        ours.write_text(json.dumps({"nodes": [{"id": "a"}, {"id": "b"}]}), encoding="utf-8")
        theirs.write_text(json.dumps({"nodes": [{"id": "a"}, {"id": "c"}]}), encoding="utf-8")

        result = subprocess.run(
            [interpreter, str(_ROOT / _DRIVER), *map(str, (base, ours, theirs))],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert len(json.loads(ours.read_text(encoding="utf-8"))["nodes"]) == 3

    def test_the_interpreter_is_posix_separated_for_sh(self) -> None:
        r"""Git hands the driver string to sh even on Windows, and sh eats
        backslashes, so a native D:\...\python.exe would arrive mangled."""
        from scripts.maintenance.install_merge_drivers import _DRIVERS

        assert "\\" not in _DRIVERS["causal-graph"]["driver"]

    def test_an_interpreter_that_cannot_name_itself_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """sys.executable is documented as possibly empty in embedded hosts."""
        from scripts.maintenance import install_merge_drivers

        monkeypatch.setattr(sys, "executable", "")

        assert install_merge_drivers._interpreter() == "python3"

    def test_a_rejected_config_write_exits_two(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """PR #3348 review: ADR-035 makes 2 the configuration-failure code.

        A rejected `git config` write is a configuration failure, not a logic
        error. This runs from a lefthook hook, where the exit code is the only
        signal a maintainer gets about which half broke.
        """
        from scripts.maintenance import install_merge_drivers

        def reject(args: list[str]) -> subprocess.CompletedProcess[str]:
            if args[:2] == ["config", "--local"] and "--get" not in args:
                return subprocess.CompletedProcess(args, 1, "", "permission denied")
            return subprocess.CompletedProcess(args, 0, "", "")

        monkeypatch.setattr(install_merge_drivers, "_git", reject)

        assert install_merge_drivers.install() == 2
        assert "could not set" in capsys.readouterr().err

    def test_installing_twice_writes_once(self, capsys: pytest.CaptureFixture[str]) -> None:
        from scripts.maintenance import install_merge_drivers

        assert install_merge_drivers.install() == 0
        capsys.readouterr()
        assert install_merge_drivers.install() == 0
        assert capsys.readouterr().out == ""


class TestTopLevelFieldsGoThroughTheSamePolicyTable:
    """PR #3348 review: version and updated were one-off special cases.

    Handling them separately from every other field is how a key only one side
    carried came to be dropped. They now run through the shared field pass.
    """

    def test_a_key_only_theirs_carries_survives(self) -> None:
        merged = merge_graphs({}, {"nodes": []}, {"nodes": [], "schema_note": "added upstream"})
        assert merged["schema_note"] == "added upstream"

    def test_version_survives_when_one_side_omits_it(self) -> None:
        """Issue #3351: the generator drops version on a fresh write.

        That omission is a generator defect, not a deletion, so it must not
        propagate into the merge when the other side still has the value.
        """
        base = {"version": "1.0", "nodes": []}
        merged = merge_graphs(base, {"version": "1.0", "nodes": []}, {"nodes": []})
        assert merged["version"] == "1.0"

    def test_version_survives_when_the_other_side_omits_it(self) -> None:
        base = {"version": "1.0", "nodes": []}
        merged = merge_graphs(base, {"nodes": []}, {"version": "1.0", "nodes": []})
        assert merged["version"] == "1.0"

    def test_version_survives_when_both_sides_omit_it(self) -> None:
        """The case that actually happens once the defect has run twice.

        Two branches that each regenerated the graph both drop version, so
        they agree on the omission and neither side can supply it. Without a
        fallback to the ancestor, merge_graphs strips the field and the value
        is gone for good: the next merge has no ancestor copy left to recover.
        """
        base = {"version": "1.0", "nodes": []}
        merged = merge_graphs(base, {"nodes": []}, {"nodes": []})
        assert merged["version"] == "1.0"

    def test_records_recover_the_same_fields_the_document_does(self) -> None:
        """Recovery is a field policy, so it cannot live at one level only.

        Extending just the top-level key list is how version and updated became
        one-off special cases the first time. A record that both sides
        regenerated has to recover the same way the document does.
        """
        base = {"nodes": [{"id": "n1", "version": "1.0", "label": "a"}]}
        regenerated = {"nodes": [{"id": "n1", "label": "a"}]}
        merged = merge_graphs(base, regenerated, regenerated)

        assert merged["nodes"][0]["version"] == "1.0"

    def test_a_present_side_still_outranks_the_ancestor(self) -> None:
        """The base fallback is a floor, not a preference. A real bump wins."""
        base = {"version": "1.0", "nodes": []}
        bumped = {"version": "2.0", "nodes": []}
        stripped: dict[str, Any] = {"nodes": []}

        assert merge_graphs(base, bumped, stripped)["version"] == "2.0"
        assert merge_graphs(base, stripped, bumped)["version"] == "2.0"

    def test_only_prefer_present_fields_are_recovered_from_the_ancestor(self) -> None:
        """The ancestor reach is deliberately narrow, and this pins the edge.

        Widening it to every ancestor key would resurrect more than version.
        `updated` is a _LATEST field, and _extreme returns the ancestor value
        when neither side has one, so an unrestricted recovery would republish
        a stale timestamp and claim the graph was touched then. Losing the
        field is honest; backdating it is not. If dropping `updated` on a fresh
        write turns out to need recovery too, fix the generator (issue #3351),
        do not backdate here.
        """
        base = {"version": "1.0", "updated": "2026-01-01T00:00:00Z", "nodes": []}
        merged = merge_graphs(base, {"nodes": []}, {"nodes": []})

        assert merged["version"] == "1.0"
        assert "updated" not in merged

    def test_updated_takes_the_later_timestamp(self) -> None:
        merged = merge_graphs(
            {"updated": "2026-01-01T00:00:00Z", "nodes": []},
            {"updated": "2026-02-01T00:00:00Z", "nodes": []},
            {"updated": "2026-03-01T00:00:00Z", "nodes": []},
        )
        assert merged["updated"] == "2026-03-01T00:00:00Z"

    def test_a_field_both_sides_removed_stays_removed(self) -> None:
        """Not every absence is a generator defect. An agreed deletion is a deletion."""
        merged = merge_graphs({"retired": "old", "nodes": []}, {"nodes": []}, {"nodes": []})
        assert "retired" not in merged


class TestCounterKeepsTheSideThatHasANumber:
    """PR #3348 review: a malformed counter on one side discarded a good one."""

    @staticmethod
    def _counted(base: object, ours: object, theirs: object) -> object:
        merged = merge_graphs(
            {"nodes": [{"id": "n1", "frequency": base}]} if base is not None else {"nodes": []},
            {"nodes": [{"id": "n1", "frequency": ours}]},
            {"nodes": [{"id": "n1", "frequency": theirs}]},
        )
        return merged["nodes"][0]["frequency"]

    def test_a_string_on_ours_does_not_discard_a_number_on_theirs(self) -> None:
        assert self._counted(2, "corrupt", 7) == 7

    def test_a_string_on_theirs_does_not_discard_a_number_on_ours(self) -> None:
        assert self._counted(2, 7, "corrupt") == 7

    def test_two_malformed_sides_keep_ours(self) -> None:
        assert self._counted(2, "a", "b") == "a"


class TestTopLevelKeyOrderMatchesTheGeneratedSchema:
    """PR #3348 review: a merge must not reorder unchanged content.

    The generator always writes nodes, then patterns, then edges. If
    ``merge_graphs`` emitted a different order, a merge that changed no
    content would still rewrite the whole file and produce a noisy diff.
    """

    def test_collections_are_emitted_nodes_then_patterns_then_edges(self) -> None:
        merged = merge_graphs(_graph(), _graph(), _graph())
        collection_keys = [key for key in merged if key in {"nodes", "patterns", "edges"}]
        assert collection_keys == ["nodes", "patterns", "edges"]


class _Interrupt(BaseException):
    """Stands in for KeyboardInterrupt without stopping the test runner."""


class TestTheTemporaryNeverOutlivesTheWrite:
    """Refs #3368. The destination surviving is only half the guarantee.

    A merge driver runs inside an interactive `git merge`, so the realistic
    failure is Ctrl-C, not ENOSPC. KeyboardInterrupt is not an OSError, so a
    cleanup path attached to OSError alone never sees it and the sibling
    temporary is left in the graph directory.
    """

    def _destination(self, tmp_path: Path) -> Path:
        path = tmp_path / "causal-graph.json"
        path.write_text('{"nodes": []}\n', encoding="utf-8")
        return path

    def _siblings(self, path: Path) -> list[str]:
        return sorted(p.name for p in path.parent.iterdir() if p != path)

    def test_an_interrupt_mid_write_leaves_only_the_destination(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = self._destination(tmp_path)
        real_fdopen = os.fdopen

        def interrupting_fdopen(fd: int, *args: Any, **kwargs: Any) -> TextIO:
            handle = real_fdopen(fd, *args, **kwargs)
            handle.close()
            raise _Interrupt()

        monkeypatch.setattr(merge_causal_graph.os, "fdopen", interrupting_fdopen)
        with pytest.raises(_Interrupt):
            _atomic_write_text(path, "replacement")

        assert self._siblings(path) == []
        assert path.read_text(encoding="utf-8") == '{"nodes": []}\n'

    def test_an_interrupt_before_the_rename_leaves_only_the_destination(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The window is widest here: the temporary holds a full copy."""
        path = self._destination(tmp_path)

        def interrupting_replace(source: Any, target: Any) -> None:
            raise _Interrupt()

        monkeypatch.setattr(merge_causal_graph.os, "replace", interrupting_replace)
        with pytest.raises(_Interrupt):
            _atomic_write_text(path, "replacement")

        assert self._siblings(path) == []
        assert path.read_text(encoding="utf-8") == '{"nodes": []}\n'

    def test_a_leaked_temporary_would_name_the_file_it_failed_to_replace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """mkstemp's default name points at nothing; a leak must be greppable."""
        path = self._destination(tmp_path)
        seen: list[str] = []
        real_mkstemp = merge_causal_graph.tempfile.mkstemp

        def recording_mkstemp(*args: Any, **kwargs: Any) -> tuple[int, str]:
            fd, name = real_mkstemp(*args, **kwargs)
            seen.append(Path(name).name)
            return fd, name

        monkeypatch.setattr(merge_causal_graph.tempfile, "mkstemp", recording_mkstemp)
        _atomic_write_text(path, "replacement")

        assert len(seen) == 1
        assert path.name in seen[0]


class TestTheContentReachesDiskBeforeTheRename:
    """Refs #3368. os.replace is atomic against processes, not against a crash.

    Renaming over the destination without flushing the temporary can leave the
    destination naming data that never reached disk, which is the partial-file
    outcome the atomic write exists to prevent, moved from the write to the
    rename.
    """

    def test_fsync_runs_before_replace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "causal-graph.json"
        path.write_text("{}\n", encoding="utf-8")
        order: list[str] = []
        real_fsync = os.fsync
        real_replace = os.replace

        def recording_fsync(fd: int) -> None:
            order.append("fsync")
            real_fsync(fd)

        def recording_replace(source: Any, target: Any) -> None:
            order.append("replace")
            real_replace(source, target)

        monkeypatch.setattr(merge_causal_graph.os, "fsync", recording_fsync)
        monkeypatch.setattr(merge_causal_graph.os, "replace", recording_replace)
        _atomic_write_text(path, "replacement")

        assert order == ["fsync", "replace"]
        assert path.read_text(encoding="utf-8") == "replacement"

    def test_a_failed_fsync_exits_three_without_touching_the_destination(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A sync failure is a filesystem failure, not malformed input."""
        base = tmp_path / "base.json"
        ours = tmp_path / "ours.json"
        theirs = tmp_path / "theirs.json"
        base.write_text(json.dumps(_graph()), encoding="utf-8")
        ours.write_text(json.dumps(_graph(nodes=[_node("ours")])), encoding="utf-8")
        theirs.write_text(json.dumps(_graph(nodes=[_node("theirs")])), encoding="utf-8")
        before = ours.read_text(encoding="utf-8")

        def failing_fsync(fd: int) -> None:
            raise OSError(errno.EIO, "sync failed")

        monkeypatch.setattr(merge_causal_graph.os, "fsync", failing_fsync)
        assert main([str(base), str(ours), str(theirs)]) == 3
        assert ours.read_text(encoding="utf-8") == before
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "base.json",
            "ours.json",
            "theirs.json",
        ]
