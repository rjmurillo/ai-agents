"""Tests for the causal graph merge driver and its registration.

Issue #3345: every merge of the default branch conflicted on the generated
causal graph, and the documented workaround silently deleted graph state. These
cover the union semantics, the loud-failure contract, and the wiring that keeps
a `.gitattributes` entry from becoming a no-op.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.merge_causal_graph import (
    GraphMergeError,
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

    def test_edges_key_on_the_triple_they_connect(self) -> None:
        edge = {"source": "a", "target": "b", "type": "causes", "evidence_count": 1}
        other = {"source": "a", "target": "b", "type": "enables", "evidence_count": 1}
        merged = merge_graphs(_graph(), _graph(edges=[edge]), _graph(edges=[other]))
        assert len(merged["edges"]) == 2

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
