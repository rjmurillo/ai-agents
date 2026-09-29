"""Per-fixture activation from capability frontmatter (issue #5400)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.instruction_bytes_corpus import CorpusError
from scripts.validation.instruction_bytes_fixtures import (
    FIXTURES,
    SOURCES,
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

ALWAYS_ON_DESCRIPTION = 'description: "Load at the start of EVERY task."\n'


def _measure(root: Path, fixture: Fixture = FIXTURE) -> FixtureResult:
    return measure_fixture(root, fixture, load_graph(root), load_always_on(root))


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
        by_source = {s: sum(f.size_bytes for f in result.files if f.source == s) for s in SOURCES}
        assert by_source["entrypoint"] + by_source["dependency"] == loaded

    def test_an_unreferenced_skill_is_not_loaded(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        paths = [f.path for f in _measure(tmp_path).files]
        assert ".claude/skills/plain/SKILL.md" not in paths

    def test_a_dependency_cycle_terminates_and_counts_each_owner_once(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        add_skill(tmp_path, "gamma", capability(["gamma-cap"], ["alpha-cap"]))
        result = _measure(tmp_path)
        assert _by_source(result, "dependency") == [
            ".claude/skills/beta/SKILL.md",
            ".claude/skills/gamma/SKILL.md",
        ]

    def test_an_owner_that_is_a_rule_loads_its_rules_copy(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        add_rule(tmp_path, "sec-rule", ["nothing/**"], capability(["sec-cap"]))
        add_skill(tmp_path, "alpha", capability(["alpha-cap"], ["sec-cap"]))
        assert _by_source(_measure(tmp_path), "dependency") == [".claude/rules/sec-rule.md"]

    def test_an_owner_that_is_an_agent_loads_its_agents_copy(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        add_agent(tmp_path, "owner-agent", capability(["agent-cap"]))
        add_skill(tmp_path, "alpha", capability(["alpha-cap"], ["agent-cap"]))
        assert ".claude/agents/owner-agent.md" in _by_source(_measure(tmp_path), "dependency")

    def test_an_unowned_dependency_is_a_finding_not_a_crash(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        add_skill(tmp_path, "alpha", capability(["alpha-cap"], ["ghost-cap"]))
        result = _measure(tmp_path)
        assert any("`ghost-cap` has no canonical owner" in f for f in result.findings)

    def test_an_owner_outside_the_three_template_shapes_fails_closed(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        write(
            tmp_path,
            "templates/agents/notes.md",
            "---\nname: notes\n" + capability(["notes-cap"]) + "---\nx\n",
        )
        add_skill(tmp_path, "alpha", capability(["alpha-cap"], ["notes-cap"]))
        with pytest.raises(CorpusError, match="templates/agents/notes.md has no loaded copy"):
            _measure(tmp_path)

    def test_a_dependency_with_no_loaded_copy_fails_closed_instead_of_lowering_the_total(
        self, tmp_path: Path
    ) -> None:
        build_repo(tmp_path)
        (tmp_path / ".claude/skills/beta/SKILL.md").unlink()
        with pytest.raises(CorpusError, match="beta.SKILL.md.tmpl has no loaded copy"):
            _measure(tmp_path)


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


class TestHarnessContext:
    def test_a_scoped_rule_loads_when_its_paths_match_the_edited_file(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        assert ".claude/rules/py-rule.md" in _by_source(_measure(tmp_path), "scoped-rule")

    def test_a_rule_scoped_elsewhere_stays_out(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        paths = [f.path for f in _measure(tmp_path).files]
        assert ".claude/rules/doc-rule.md" not in paths

    def test_a_different_edited_path_selects_a_different_rule(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        fixture = Fixture("T7", "docs", "docs/guide.md", (), ())
        scoped = _by_source(_measure(tmp_path, fixture), "scoped-rule")
        assert ".claude/rules/doc-rule.md" in scoped
        assert ".claude/rules/py-rule.md" not in scoped

    def test_no_edited_path_resolves_against_the_repository_root(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        fixture = Fixture("T8", "none", None, (), ())
        scoped = _by_source(_measure(tmp_path, fixture), "scoped-rule")
        assert scoped == [".claude/rules/always.md"]

    def test_a_rule_with_no_paths_key_is_always_loaded(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        add_rule(tmp_path, "nopaths", None)
        fixture = Fixture("T9", "none", None, (), ())
        assert ".claude/rules/nopaths.md" in _by_source(_measure(tmp_path, fixture), "scoped-rule")

    def test_a_nested_guide_loads_down_the_edited_directory_chain(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        write(tmp_path, "pkg/CLAUDE.md", "# pkg guide\n")
        write(tmp_path, "other/CLAUDE.md", "# other guide\n")
        nested = _by_source(_measure(tmp_path), "nested")
        assert nested == ["pkg/CLAUDE.md"]

    def test_an_at_import_in_the_root_guide_is_followed(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        write(tmp_path, "CLAUDE.md", "@AGENTS.md\n")
        assert "AGENTS.md" in _by_source(_measure(tmp_path), "root")

    def test_a_broken_at_import_is_a_finding(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        write(tmp_path, "CLAUDE.md", "@missing.md\n")
        result = _measure(tmp_path)
        assert any(f.startswith("@ import missing: @missing.md") for f in result.findings)

    def test_an_edited_path_outside_the_repository_fails_closed(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        fixture = Fixture("T10", "escape", "../outside.py", (), ())
        with pytest.raises(CorpusError, match="cannot resolve Claude Code context"):
            _measure(tmp_path, fixture)

    def test_a_universal_rule_is_counted_once(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        paths = [f.path for f in _measure(tmp_path).files]
        assert len(paths) == len(set(paths))
        assert paths.count(".claude/rules/always.md") == 1


class TestAlwaysOnSkills:
    def test_a_skill_that_declares_always_on_loads_in_every_fixture(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        add_skill(tmp_path, "front", ALWAYS_ON_DESCRIPTION)
        for fixture in (FIXTURE, Fixture("T11", "none", None, (), ())):
            assert _by_source(_measure(tmp_path, fixture), "always-on-skill") == [
                ".claude/skills/front/SKILL.md"
            ]

    def test_an_always_on_skill_that_is_also_an_entrypoint_counts_once(
        self, tmp_path: Path
    ) -> None:
        build_repo(tmp_path)
        add_skill(tmp_path, "front", ALWAYS_ON_DESCRIPTION)
        result = _measure(tmp_path, Fixture("T12", "front", None, ("front",), ()))
        assert [f.source for f in result.files if f.path.endswith("front/SKILL.md")] == [
            "always-on-skill"
        ]

    def test_a_scoped_skill_is_not_always_on(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        add_skill(tmp_path, "scoped", 'description: "Use when you say build this."\n')
        assert _by_source(_measure(tmp_path), "always-on-skill") == []

    def test_the_skill_joins_the_claude_entry_only(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        skill_bytes = add_skill(tmp_path, "front", ALWAYS_ON_DESCRIPTION)
        with_skill = load_always_on(tmp_path)
        (tmp_path / ".claude/skills/front/SKILL.md").unlink()
        without_skill = load_always_on(tmp_path)
        assert with_skill.harnesses["claude_code"]["bytes"] == (
            without_skill.harnesses["claude_code"]["bytes"] + skill_bytes
        )
        assert with_skill.harnesses["copilot"] == without_skill.harnesses["copilot"]

    def test_malformed_skill_frontmatter_fails_closed(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        write(tmp_path, ".claude/skills/broken/SKILL.md", "no frontmatter\n")
        with pytest.raises(CorpusError, match="always-on measurement failed"):
            load_always_on(tmp_path)


class TestGraphLoading:
    def test_a_tree_without_templates_fails_closed(self, tmp_path: Path) -> None:
        with pytest.raises(CorpusError, match="capability graph unreadable"):
            load_graph(tmp_path)

    def test_shape_defects_are_carried_not_swallowed(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        add_skill(tmp_path, "alpha", "metadata:\n  type: legacy\n")
        assert any("retired `metadata.type`" in d for d in load_graph(tmp_path).defects)

    def test_owners_are_indexed_by_capability_name(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        graph = load_graph(tmp_path)
        assert graph.owners["beta-cap"].path == "templates/skills/beta.SKILL.md.tmpl"
        assert graph.nodes["templates/skills/alpha.SKILL.md.tmpl"].depends_on == ("beta-cap",)


class TestAlwaysOn:
    def test_missing_workspace_files_surface_as_findings(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        assert any(".claude/CLAUDE.md" in f for f in load_always_on(tmp_path).findings)

    def test_always_on_files_come_from_the_existing_counter(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        files = load_always_on(tmp_path).harnesses["claude_code"]["files"]
        assert "AGENTS.md" in files
        assert ".claude/rules/py-rule.md" not in files

    def test_an_unsupported_glob_in_a_rule_fails_closed(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        write(tmp_path, ".claude/rules/klass.md", '---\npaths:\n  - "*.[ch]"\n---\nx\n')
        with pytest.raises(CorpusError, match="always-on measurement failed"):
            load_always_on(tmp_path)


class TestShippedFixtureDefinitions:
    def test_f1_to_f6_are_defined_once_each_in_order(self) -> None:
        assert [f.fixture_id for f in FIXTURES] == ["F1", "F2", "F3", "F4", "F5", "F6"]

    def test_every_fixture_measures_against_the_live_tree(self) -> None:
        root = Path(__file__).resolve().parents[2]
        graph, always = load_graph(root), load_always_on(root)
        for fixture in FIXTURES:
            result = measure_fixture(root, fixture, graph, always)
            entrypoints = [f for f in result.files if f.source in {"entrypoint", "always-on-skill"}]
            assert len(entrypoints) >= len(fixture.skills) + len(fixture.agents)
            assert {f.source for f in result.files} <= set(SOURCES)
