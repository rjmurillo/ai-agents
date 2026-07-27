"""Tests for the plugin frontmatter self-containment gate (issue #3565).

The check exists because a documentation-only rule failed: the repo shipped
``.claude/rules/plugin-self-containment.md`` in #3443 and violated it two PRs
later. So these tests carry a heavier burden than usual. They must pin the
precision boundary, not just the happy path, because a gate that fires on
consumer-workspace paths or on "build/buy/partner" will be switched off and
the rule will go back to being advisory.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "validation"
    / "check_plugin_frontmatter_self_containment.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("_frontmatter_gate", _MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load()


def _frontmatter(description: str, extra: str = "") -> str:
    return f"---\ndescription: {description}\n{extra}---\n\n# Body\n"


class TestOutwardDetection:
    """Positive cases: a file under an upstream-only directory must be caught."""

    @pytest.mark.parametrize(
        "reference",
        [
            "docs/agent-metrics.md",
            "docs/autonomous-pr-monitor.md",
            ".agents/governance/golden-principles.md",
            ".github/workflows/ci.yml",
            ".serena/memories/foo.md",
            "scripts/validation/pre_pr.py",
            "tests/validation/test_x.py",
            "build/scripts/build_all.py",
            "templates/agents/security.shared.md",
            "templates/platforms/copilot-cli.yaml",
        ],
    )
    def test_flags_upstream_only_file(self, reference: str) -> None:
        found = gate.scan_file(Path("x.md"), _frontmatter(f"Does a thing per {reference}."))
        assert [ref for _, _, ref in found] == [reference]

    def test_flags_the_name_key_too(self) -> None:
        text = "---\nname: docs/thing.md\n---\n"
        assert [key for _, key, _ in gate.scan_file(Path("x.md"), text)] == ["name"]

    def test_reports_every_reference_on_one_line(self) -> None:
        text = _frontmatter("See docs/a.md and .agents/b.md for detail.")
        assert len(gate.scan_file(Path("x.md"), text)) == 2

    def test_reports_the_frontmatter_line_number(self) -> None:
        text = "---\nname: thing\ndescription: per docs/a.md\n---\n"
        assert [n for n, _, _ in gate.scan_file(Path("x.md"), text)] == [3]

    def test_flags_continuation_lines_of_a_folded_scalar(self) -> None:
        text = (
            "---\ndescription: >\n"
            "  A long description that mentions\n  docs/deep/thing.md here.\n---\n"
        )
        found = gate.scan_file(Path("x.md"), text)
        assert [ref for _, _, ref in found] == ["docs/deep/thing.md"]


class TestPrecision:
    """Negative cases. Each one would make the gate unusable if it fired."""

    def test_ignores_consumer_workspace_directories(self) -> None:
        """The rule explicitly permits these. They are the plugin doing its job."""
        text = _frontmatter("Writes its output to .agents/planning/ and docs/adr/.")
        assert gate.scan_file(Path("x.md"), text) == []

    @pytest.mark.parametrize("phrase", ["build/buy/partner", "a build/deploy split"])
    def test_ignores_prose_collisions(self, phrase: str) -> None:
        """The rule names 'build/buy/partner' as a known collision."""
        assert gate.scan_file(Path("x.md"), _frontmatter(f"Covers {phrase} choices.")) == []

    def test_ignores_bundled_templates_directory(self) -> None:
        """A skill may ship its own templates/. Only agents/ and platforms/ are upstream."""
        text = _frontmatter("Uses templates/threat-model-template.md from this skill.")
        assert gate.scan_file(Path("x.md"), text) == []

    @pytest.mark.parametrize(
        "reference",
        [".claude/skills/foo/SKILL.md", "src/copilot-cli/lib/paths.py"],
    )
    def test_ignores_in_root_paths(self, reference: str) -> None:
        """Plugin roots ship. A reference inside one resolves for the consumer."""
        assert gate.scan_file(Path("x.md"), _frontmatter(f"Reads {reference}.")) == []

    def test_ignores_body_prose(self) -> None:
        """Body is the sibling ratchet's surface, deliberately not this one."""
        text = "---\ndescription: Clean.\n---\n\nSee docs/agent-metrics.md for detail.\n"
        assert gate.scan_file(Path("x.md"), text) == []

    def test_ignores_unchecked_frontmatter_keys(self) -> None:
        text = "---\ndescription: Clean.\nallowed-tools: docs/thing.md\n---\n"
        assert gate.scan_file(Path("x.md"), text) == []

    def test_ignores_a_bare_word_after_the_directory(self) -> None:
        assert gate.scan_file(Path("x.md"), _frontmatter("Runs scripts/nightly now.")) == []

    def test_ignores_a_similar_prefix(self) -> None:
        """'mydocs/' and 'subdocs/' are not 'docs/'."""
        assert gate.scan_file(Path("x.md"), _frontmatter("Reads mydocs/a.md.")) == []


class TestDeclaration:
    """The opt-out is scoped to the path it names, not to the whole file.

    The sibling validators treat the marker as a file-wide switch. That is the
    hole this class pins: ``.claude/skills/metrics/SKILL.md`` carries a marker
    written about the consumer's ``.agents/`` artifacts, and a file-wide
    reading let it silence an unrelated ``docs/agent-metrics.md`` sitting in
    its own description.

    Every marker in the real tree sits in the body, below the frontmatter, so
    these fixtures put it there. A marker on line 1 would displace the opening
    ``---`` and leave the file with no frontmatter to check at all, which is a
    different property, pinned in ``TestFrontmatterParsing``.
    """

    @staticmethod
    def _with_marker(description: str, marker: str) -> str:
        return _frontmatter(description) + f"\n<!-- vendor-portability: {marker} -->\n"

    def test_declaration_naming_the_path_suppresses_it(self) -> None:
        text = self._with_marker("Per docs/a.md.", "needs docs/a.md upstream")
        assert gate.scan_file(Path("x.md"), text) == []

    def test_declaration_naming_a_different_path_does_not_suppress(self) -> None:
        """The regression. A marker about one dependency must not cover another."""
        text = self._with_marker("Per docs/agent-metrics.md.", "writes .agents/metrics/out.md")
        assert [ref for _, _, ref in gate.scan_file(Path("x.md"), text)] == [
            "docs/agent-metrics.md"
        ]

    def test_declaration_suppresses_only_the_named_path(self) -> None:
        text = self._with_marker("Per docs/a.md and docs/b.md.", "needs docs/a.md")
        assert [ref for _, _, ref in gate.scan_file(Path("x.md"), text)] == ["docs/b.md"]

    def test_declaration_is_case_insensitive(self) -> None:
        text = _frontmatter("Per docs/a.md.") + "\n<!-- Vendor-Portability: docs/a.md -->\n"
        assert gate.scan_file(Path("x.md"), text) == []

    def test_multi_line_declaration_is_read_whole(self) -> None:
        """Real markers wrap across lines; a line-scoped regex would miss the path."""
        text = _frontmatter("Enforces .agents/governance/golden-principles.md.") + (
            "\n<!-- vendor-portability: declared. This skill enforces the rules\n"
            "     defined in .agents/governance/golden-principles.md upstream. -->\n"
        )
        assert gate.scan_file(Path("x.md"), text) == []

    def test_a_marker_naming_nothing_suppresses_nothing(self) -> None:
        text = self._with_marker("Per docs/a.md.", "contributor-facing")
        assert [ref for _, _, ref in gate.scan_file(Path("x.md"), text)] == ["docs/a.md"]

    def test_declared_paths_collects_across_multiple_markers(self) -> None:
        text = "<!-- vendor-portability: docs/a.md -->\n<!-- vendor-portability: docs/b.md -->\n"
        assert gate.declared_paths(text) == {"docs/a.md", "docs/b.md"}

    def test_the_two_real_declared_files_stay_silent(self) -> None:
        """golden-principles declares the exact path its description names."""
        root = Path(__file__).resolve().parents[2]
        for mirror in (".claude", "src/copilot-cli"):
            path = root / mirror / "skills" / "golden-principles" / "SKILL.md"
            assert gate.scan_file(path, path.read_text(encoding="utf-8")) == []


class TestFrontmatterParsing:
    def test_no_frontmatter_means_nothing_scanned(self) -> None:
        assert gate.frontmatter_lines("# Title\n\ndescription: docs/a.md\n") == []

    def test_unterminated_frontmatter_is_not_frontmatter(self) -> None:
        """Otherwise the whole body would be scanned as frontmatter."""
        assert gate.frontmatter_lines("---\ndescription: docs/a.md\n\n# Body\n") == []

    def test_empty_file(self) -> None:
        assert gate.frontmatter_lines("") == []

    def test_a_leading_comment_displaces_the_frontmatter(self) -> None:
        """A file whose first line is not `---` has no frontmatter to check."""
        text = "<!-- vendor-portability: x -->\n---\ndescription: Per docs/a.md.\n---\n"
        assert gate.frontmatter_lines(text) == []
        assert gate.scan_file(Path("x.md"), text) == []

    def test_second_fence_closes_the_block(self) -> None:
        text = "---\ndescription: a\n---\nbody\n---\ndescription: docs/b.md\n"
        assert gate.scan_file(Path("x.md"), text) == []


class TestFileDiscovery:
    def test_skips_nested_worktrees(self, tmp_path: Path) -> None:
        """.claude/worktrees holds checkouts of this same repo."""
        (tmp_path / ".claude" / "worktrees" / "agent-a" / "skills" / "s").mkdir(parents=True)
        (tmp_path / ".claude" / "worktrees" / "agent-a" / "skills" / "s" / "SKILL.md").write_text(
            _frontmatter("Per docs/a.md."), encoding="utf-8"
        )
        (tmp_path / ".claude" / "skills").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "real.md").write_text(
            "---\nname: r\n---\n", encoding="utf-8"
        )
        found = [p.name for p in gate.iter_markdown(tmp_path)]
        assert found == ["real.md"]

    def test_scans_every_plugin_root(self, tmp_path: Path) -> None:
        for root in gate.PLUGIN_ROOTS:
            target = tmp_path / root / "skills"
            target.mkdir(parents=True)
            (target / "a.md").write_text("---\nname: a\n---\n", encoding="utf-8")
        assert len(gate.iter_markdown(tmp_path)) == len(gate.PLUGIN_ROOTS)

    def test_missing_root_is_not_an_error(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        assert gate.iter_markdown(tmp_path) == []


class TestCli:
    """Exit codes are pinned to literals: CI reads the number, not the constant."""

    def test_clean_tree_exits_zero(self, tmp_path: Path, capsys) -> None:
        skills = tmp_path / ".claude" / "skills"
        skills.mkdir(parents=True)
        (skills / "a.md").write_text(_frontmatter("Self-contained."), encoding="utf-8")
        assert gate.main(["--repo-root", str(tmp_path)]) == 0
        assert "No outward frontmatter references" in capsys.readouterr().out

    def test_violation_exits_one_and_names_the_file(self, tmp_path: Path, capsys) -> None:
        skills = tmp_path / ".claude" / "skills"
        skills.mkdir(parents=True)
        (skills / "bad.md").write_text(_frontmatter("Per docs/a.md."), encoding="utf-8")
        assert gate.main(["--repo-root", str(tmp_path)]) == 1
        err = capsys.readouterr().err
        assert ".claude/skills/bad.md:2" in err
        assert "docs/a.md" in err
        assert "plugin-self-containment.md" in err

    def test_no_plugin_root_is_a_config_error(self, tmp_path: Path, capsys) -> None:
        assert gate.main(["--repo-root", str(tmp_path)]) == 2
        assert "No plugin root found" in capsys.readouterr().err

    def test_real_repository_is_clean(self) -> None:
        """The gate ships at zero. This is the ratchet."""
        root = Path(__file__).resolve().parents[2]
        assert gate.main(["--repo-root", str(root)]) == 0


class TestRootAwareness:
    """A path is outward relative to the root that ships the file naming it.

    ``src/copilot-cli`` ships its own ``docs/`` directory. Treating the
    directory name as upstream-only, rather than resolving it against the
    owning root, would reject a description that resolves perfectly well for
    that plugin's consumer. The gate has no baseline, so a false positive here
    hard-blocks a legitimate change.
    """

    def test_the_copilot_root_really_does_ship_a_docs_directory(self) -> None:
        """Pins the premise. If this file moves, the exemption below is wrong."""
        root = Path(__file__).resolve().parents[2]
        assert (root / "src/copilot-cli/docs/copilot-instructions.md").is_file()

    def test_a_reference_that_ships_in_its_own_root_is_clean(self) -> None:
        root = Path(__file__).resolve().parents[2]
        text = _frontmatter("Per docs/copilot-instructions.md.")
        ships = gate.root_shipper(root, "src/copilot-cli")
        assert gate.scan_file(Path("x.md"), text, ships) == []

    def test_the_same_reference_under_a_root_without_it_is_flagged(self) -> None:
        root = Path(__file__).resolve().parents[2]
        text = _frontmatter("Per docs/copilot-instructions.md.")
        ships = gate.root_shipper(root, ".claude")
        assert [ref for _, _, ref in gate.scan_file(Path("x.md"), text, ships)] == [
            "docs/copilot-instructions.md"
        ]

    def test_a_traversal_never_counts_as_shipped(self, tmp_path: Path) -> None:
        """`root/../docs/a.md` exists on disk but is outside the plugin root."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "a.md").write_text("x", encoding="utf-8")
        (tmp_path / ".claude").mkdir()
        ships = gate.root_shipper(tmp_path, ".claude")
        assert ships("../docs/a.md") is False

    def test_a_dot_slash_prefix_still_resolves(self, tmp_path: Path) -> None:
        (tmp_path / ".claude" / "docs").mkdir(parents=True)
        (tmp_path / ".claude" / "docs" / "a.md").write_text("x", encoding="utf-8")
        ships = gate.root_shipper(tmp_path, ".claude")
        assert ships("./docs/a.md") is True
        assert ships("docs/b.md") is False

    def test_owning_root_maps_each_root_and_rejects_outsiders(self) -> None:
        root = Path("/repo")
        for name in gate.PLUGIN_ROOTS:
            assert gate.owning_root(root / name / "skills" / "x" / "SKILL.md", root) == name
        assert gate.owning_root(root / "templates" / "agents" / "x.md", root) is None

    def test_plugin_roots_are_pinned(self) -> None:
        """Losing a root silently halves the gate; the tuple is the contract."""
        assert gate.PLUGIN_ROOTS == (".claude", "src/claude", "src/copilot-cli")


class TestReferenceShapes:
    """Regex precision cases found by adversarial review."""

    def test_a_version_directory_is_not_a_file(self) -> None:
        assert gate.OUTWARD_FILE.findall("docs/v1.2.3") == []

    def test_a_numeric_suffix_is_not_an_extension(self) -> None:
        assert gate.OUTWARD_FILE.findall("build/artifact.2") == []

    def test_relative_prefixes_are_caught(self) -> None:
        assert gate.OUTWARD_FILE.findall("../docs/a.md") == ["../docs/a.md"]
        assert gate.OUTWARD_FILE.findall("./docs/a.md") == ["./docs/a.md"]

    def test_a_url_path_is_still_ignored(self) -> None:
        assert gate.OUTWARD_FILE.findall("https://example.com/docs/a.md") == []

    def test_a_traversal_in_frontmatter_is_a_violation(self) -> None:
        text = _frontmatter("Read ../docs/a.md first.")
        assert [ref for _, _, ref in gate.scan_file(Path("x.md"), text)] == ["../docs/a.md"]


class TestParserFidelity:
    """The line parser must agree with a real YAML load on the whole corpus.

    The parser is hand-rolled on purpose: two shipped SkillForge templates
    carry placeholder syntax that ``yaml.safe_load`` rejects outright, so a
    strict loader would fail on files the line parser reads fine. The risk of
    hand-rolling is a YAML shape the line parser misreads, such as a quoted key
    or a flow mapping. This test is that guard: it fails the day such a shape
    lands, without importing the loader's fragility into the gate.
    """

    def test_line_parser_agrees_with_yaml_across_the_tree(self) -> None:
        import yaml

        root = Path(__file__).resolve().parents[2]
        disagreements: list[tuple[str, str]] = []
        for path in gate.iter_markdown(root):
            text = path.read_text(encoding="utf-8", errors="replace")
            lines = gate.frontmatter_lines(text)
            if not lines:
                continue
            try:
                loaded = yaml.safe_load("\n".join(line for _, line in lines))
            except yaml.YAMLError:
                continue
            if not isinstance(loaded, dict):
                continue
            mine: dict[str, str] = {}
            for _, key, value in gate.checked_values(text):
                mine[key] = f"{mine.get(key, '')} {value}".strip()
            for key in gate.CHECKED_KEYS:
                real = loaded.get(key)
                if not isinstance(real, str):
                    continue
                if set(gate.OUTWARD_FILE.findall(real)) != set(
                    gate.OUTWARD_FILE.findall(mine.get(key, ""))
                ):
                    disagreements.append((str(path.relative_to(root)), key))
        assert disagreements == []

    def test_main_resolves_references_against_the_owning_root(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """End to end, so the CLI cannot quietly stop passing the shipper.

        Unit tests hand ``scan_file`` a shipper directly, which leaves the
        wiring in ``main`` untested. Dropping that one line reintroduces the
        false positive this class exists to prevent, and every unit test stays
        green. This is the test that goes red.
        """
        shipped = tmp_path / "src/copilot-cli"
        (shipped / "docs").mkdir(parents=True)
        (shipped / "docs" / "guide.md").write_text("x", encoding="utf-8")
        (shipped / "skills").mkdir()
        (shipped / "skills" / "a.md").write_text(
            _frontmatter("Per docs/guide.md."), encoding="utf-8"
        )
        assert gate.main(["--repo-root", str(tmp_path)]) == 0

        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "b.md").write_text(
            _frontmatter("Per docs/guide.md."), encoding="utf-8"
        )
        assert gate.main(["--repo-root", str(tmp_path)]) == 1
        assert "docs/guide.md" in capsys.readouterr().err
