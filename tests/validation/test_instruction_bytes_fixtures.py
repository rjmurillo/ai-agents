"""Per-fixture activation from capability frontmatter (issue #5400)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.instruction_bytes_corpus import CorpusError
from scripts.validation.instruction_bytes_fixtures import (
    FIXTURES,
    Fixture,
    FixtureResult,
    load_always_on,
    load_graph,
    measure_fixture,
)
from tests.validation._instruction_bytes_helpers import (
    FIXTURE,
    add_agent,
    add_rule,
    add_skill,
    build_repo,
    capability,
    write,
)


def _measure(root: Path, fixture: Fixture = FIXTURE) -> FixtureResult:
    always, _ = load_always_on(root)
    return measure_fixture(root, fixture, load_graph(root), always["claude_code"]["files"])


def _by_source(result: FixtureResult, source: str) -> list[str]:
    return sorted(f.path for f in result.files if f.source == source)


class TestDependencyClosure:
    def test_follows_depends_on_transitively_to_canonical_owners(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        result = _measure(tmp_path)
        assert _by_source(result, "entrypoint") == [
            ".claude/agents/scout.md",
            ".claude/skills/alpha/SKILL.md",
        ]
        assert _by_source(result, "dependency") == [
            ".claude/skills/beta/SKILL.md",
            ".claude/skills/gamma/SKILL.md",
        ]
        assert result.findings == ()

    def test_activated_bytes_are_the_exact_sum_of_loaded_files(self, tmp_path: Path) -> None:
        sizes = build_repo(tmp_path)
        result = _measure(tmp_path)
        loaded = sizes["alpha"] + sizes["beta"] + sizes["gamma"] + sizes["scout"]
        conditional = sum(f.size_bytes for f in result.files if f.source != "always-on")
        assert conditional == loaded + sizes["py-rule"]

    def test_an_unreferenced_skill_is_not_loaded(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        paths = [f.path for f in _measure(tmp_path).files]
        assert ".claude/skills/plain/SKILL.md" not in paths

    def test_a_dependency_cycle_terminates_and_counts_each_owner_once(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        add_skill(tmp_path, "gamma", capability(["gamma-cap"], ["alpha-cap"]))
        result = _measure(tmp_path)
        dependencies = _by_source(result, "dependency")
        assert dependencies == [
            ".claude/skills/beta/SKILL.md",
            ".claude/skills/gamma/SKILL.md",
        ]

    def test_an_owner_that_is_a_rule_loads_its_rules_copy(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        add_rule(tmp_path, "sec-rule", ["nothing/**"], capability(["sec-cap"]))
        add_skill(tmp_path, "alpha", capability(["alpha-cap"], ["sec-cap"]))
        result = _measure(tmp_path)
        assert _by_source(result, "dependency") == [".claude/rules/sec-rule.md"]

    def test_an_owner_that_is_an_agent_loads_its_agents_copy(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        add_agent(tmp_path, "owner-agent", capability(["agent-cap"]))
        add_skill(tmp_path, "alpha", capability(["alpha-cap"], ["agent-cap"]))
        result = _measure(tmp_path)
        assert ".claude/agents/owner-agent.md" in _by_source(result, "dependency")

    def test_an_unowned_dependency_is_a_finding_not_a_crash(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        add_skill(tmp_path, "alpha", capability(["alpha-cap"], ["ghost-cap"]))
        result = _measure(tmp_path)
        assert any("`ghost-cap` has no canonical owner" in f for f in result.findings)

    def test_an_owner_outside_the_three_template_shapes_has_no_loaded_copy(
        self, tmp_path: Path
    ) -> None:
        build_repo(tmp_path)
        write(
            tmp_path,
            "templates/agents/notes.md",
            "---\nname: notes\n" + capability(["notes-cap"]) + "---\nx\n",
        )
        add_skill(tmp_path, "alpha", capability(["alpha-cap"], ["notes-cap"]))
        result = _measure(tmp_path)
        assert "templates/agents/notes.md: no loaded copy to measure" in result.findings

    def test_an_owner_without_a_loaded_copy_is_a_finding(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        (tmp_path / ".claude/skills/beta/SKILL.md").unlink()
        result = _measure(tmp_path)
        assert any("no loaded copy to measure" in f for f in result.findings)
        assert ".claude/skills/beta/SKILL.md" not in [f.path for f in result.files]


class TestMissingFrontmatter:
    def test_an_entrypoint_without_a_capability_block_counts_as_itself(
        self, tmp_path: Path
    ) -> None:
        sizes = build_repo(tmp_path)
        fixture = Fixture("T2", "plain", None, ("plain",), ())
        result = _measure(tmp_path, fixture)
        assert _by_source(result, "entrypoint") == [".claude/skills/plain/SKILL.md"]
        assert _by_source(result, "dependency") == []
        assert result.findings == ("skill `plain` has no capability block; counted as itself only",)
        loaded = [f.size_bytes for f in result.files if f.source == "entrypoint"]
        assert loaded == [sizes["plain"]]

    def test_an_agent_without_frontmatter_at_all_is_still_measured(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        write(tmp_path, "templates/agents/bare.shared.md", "no frontmatter\n")
        write(tmp_path, ".claude/agents/bare.md", "no frontmatter\n")
        result = _measure(tmp_path, Fixture("T3", "bare", None, (), ("bare",)))
        assert _by_source(result, "entrypoint") == [".claude/agents/bare.md"]
        assert "agent `bare` has no capability block; counted as itself only" in result.findings


class TestEntrypointValidation:
    def test_a_missing_loaded_skill_fails_closed(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        with pytest.raises(CorpusError, match="skill `ghost` has no .claude/skills/ghost/SKILL.md"):
            _measure(tmp_path, Fixture("T4", "x", None, ("ghost",), ()))

    def test_a_missing_loaded_agent_fails_closed(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        with pytest.raises(CorpusError, match="agent `ghost` has no .claude/agents/ghost.md"):
            _measure(tmp_path, Fixture("T5", "x", None, (), ("ghost",)))

    @pytest.mark.parametrize("name", ["../etc/passwd", "Up", "a b", "", "x/y"])
    def test_an_unsafe_artifact_name_is_refused_before_any_read(
        self, tmp_path: Path, name: str
    ) -> None:
        build_repo(tmp_path)
        with pytest.raises(CorpusError, match="invalid artifact name"):
            _measure(tmp_path, Fixture("T6", "x", None, (name,), ()))


class TestPathScopedRules:
    def test_a_rule_loads_when_its_paths_match_the_edited_file(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        assert _by_source(_measure(tmp_path), "path-scoped-rule") == [".claude/rules/py-rule.md"]

    def test_a_rule_scoped_elsewhere_stays_out(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        paths = [f.path for f in _measure(tmp_path).files]
        assert ".claude/rules/doc-rule.md" not in paths

    def test_a_different_edited_path_selects_a_different_rule(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        fixture = Fixture("T7", "docs", "docs/guide.md", (), ())
        assert _by_source(_measure(tmp_path, fixture), "path-scoped-rule") == [
            ".claude/rules/doc-rule.md"
        ]

    def test_no_edited_path_selects_no_scoped_rules(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        fixture = Fixture("T8", "none", None, (), ())
        assert _by_source(_measure(tmp_path, fixture), "path-scoped-rule") == []

    def test_a_universal_rule_is_always_on_and_never_double_counted(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        result = _measure(tmp_path)
        assert ".claude/rules/always.md" in _by_source(result, "always-on")
        assert ".claude/rules/always.md" not in _by_source(result, "path-scoped-rule")
        paths = [f.path for f in result.files]
        assert len(paths) == len(set(paths))

    def test_a_rule_with_no_paths_key_is_never_scoped_to_a_file(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        add_rule(tmp_path, "nopaths", None)
        assert ".claude/rules/nopaths.md" not in _by_source(_measure(tmp_path), "path-scoped-rule")

    def test_a_string_paths_value_is_read(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        write(tmp_path, ".claude/rules/one.md", '---\npaths: "**/*.py"\n---\nx\n')
        assert ".claude/rules/one.md" in _by_source(_measure(tmp_path), "path-scoped-rule")

    def test_malformed_rule_frontmatter_fails_closed(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        write(tmp_path, ".claude/rules/bad.md", "---\npaths: [unclosed\n---\nx\n")
        with pytest.raises(CorpusError, match="frontmatter cannot be parsed"):
            _measure(tmp_path)

    def test_an_unsupported_glob_fails_closed_when_matching_a_fixture(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        write(tmp_path, ".claude/rules/klass.md", '---\npaths:\n  - "*.[ch]"\n---\nx\n')
        with pytest.raises(CorpusError, match="klass.md: .*character class"):
            measure_fixture(tmp_path, FIXTURE, load_graph(tmp_path), [])

    def test_an_unsupported_glob_fails_closed_in_the_always_on_measurement(
        self, tmp_path: Path
    ) -> None:
        build_repo(tmp_path)
        write(tmp_path, ".claude/rules/klass.md", '---\npaths:\n  - "*.[ch]"\n---\nx\n')
        with pytest.raises(CorpusError, match="always-on measurement failed"):
            load_always_on(tmp_path)

    def test_a_duplicate_paths_key_fails_closed(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        write(tmp_path, ".claude/rules/dup.md", '---\npaths: ["a"]\npaths: ["b"]\n---\nx\n')
        with pytest.raises(CorpusError, match="frontmatter cannot be parsed"):
            _measure(tmp_path)


class TestGraphLoading:
    def test_a_tree_without_templates_fails_closed(self, tmp_path: Path) -> None:
        with pytest.raises(CorpusError, match="capability graph unreadable"):
            load_graph(tmp_path)

    def test_shape_defects_are_carried_not_swallowed(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        add_skill(tmp_path, "alpha", "metadata:\n  type: legacy\n")
        graph = load_graph(tmp_path)
        assert any("retired `metadata.type`" in d for d in graph.defects)

    def test_owners_are_indexed_by_capability_name(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        graph = load_graph(tmp_path)
        assert graph.owners["beta-cap"].path == "templates/skills/beta.SKILL.md.tmpl"


class TestAlwaysOn:
    def test_missing_workspace_files_surface_as_findings(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        _, findings = load_always_on(tmp_path)
        assert any(".claude/CLAUDE.md" in f for f in findings)

    def test_always_on_files_come_from_the_existing_counter(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        loaded, _ = load_always_on(tmp_path)
        assert "AGENTS.md" in loaded["claude_code"]["files"]
        assert ".claude/rules/py-rule.md" not in loaded["claude_code"]["files"]


class TestShippedFixtureDefinitions:
    def test_f1_to_f6_are_defined_once_each_in_order(self) -> None:
        assert [f.fixture_id for f in FIXTURES] == ["F1", "F2", "F3", "F4", "F5", "F6"]

    def test_every_fixture_measures_against_the_live_tree(self) -> None:
        root = Path(__file__).resolve().parents[2]
        always, _ = load_always_on(root)
        graph = load_graph(root)
        for fixture in FIXTURES:
            result = measure_fixture(root, fixture, graph, always["claude_code"]["files"])
            assert result.files, fixture.fixture_id
            entrypoints = [f for f in result.files if f.source == "entrypoint"]
            assert len(entrypoints) == len(fixture.skills) + len(fixture.agents)
