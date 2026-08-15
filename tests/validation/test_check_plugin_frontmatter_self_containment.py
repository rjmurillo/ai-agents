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
import json
import sys
from pathlib import Path
from unittest import mock

import pytest
import yaml

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


def _write_marketplace_manifests(root: Path, sources: tuple[str, ...] = gate.PLUGIN_ROOTS) -> None:
    github_plugins = [
        {"name": f"plugin-{index}", "source": f"./{source}"}
        for index, source in enumerate(sources)
    ]
    claude_plugins = [
        {"name": f"plugin-{index}", "source": f"./{source}"}
        for index, source in enumerate(sources)
    ]
    (root / ".github" / "plugin").mkdir(parents=True)
    (root / ".claude-plugin").mkdir()
    (root / ".github" / "plugin" / "marketplace.json").write_text(
        json.dumps({"plugins": github_plugins}), encoding="utf-8"
    )
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"plugins": claude_plugins}), encoding="utf-8"
    )


class TestOutwardDetection:
    """Positive cases: a file under an upstream-only directory must be caught."""

    @pytest.mark.parametrize(
        "value",
        [
            "Reads ../../docs/a.md for the list.",
            "Reads ../../../docs/agent-catalog.md for the list.",
        ],
    )
    def test_repeated_traversal_is_still_a_path(self, value: str) -> None:
        """One traversal segment is not the only shape a relative path takes.

        Matching a single optional segment leaves the slash of the segment
        before it as the character in front of the directory name, so the
        boundary rejects the whole match and every deeper traversal walks past
        the gate. The count of segments has nothing to do with whether the
        target ships.
        """
        assert gate.scan_file(Path("x.md"), _frontmatter(value)) != []

    @pytest.mark.parametrize(
        "value",
        [
            "Reads `docs/a.md` for the roster.",
            "Reads **docs/a.md** for the roster.",
            "Reads *docs/a.md* for the roster.",
            "'| step | `docs/a.md` | notes |'",
            "See [the roster](docs/a.md).",
            "Reads (docs/a.md) for the roster.",
        ],
    )
    def test_a_markdown_delimiter_does_not_hide_a_path(self, value: str) -> None:
        """The boundary must be a negated class, not an enumerated one.

        A path in a description is most often written inside backticks, bold
        markers, or a table cell. Listing the punctuation seen in prose looks
        equivalent and silently drops every delimiter left off the list, which
        is most of them. Measured on this repository, the enumerated form found
        1,902 body references against 3,770 for the negated one.
        """
        assert gate.scan_file(Path("x.md"), _frontmatter(value)) != []

    @pytest.mark.parametrize(
        "value",
        [
            "Reads docs/a.md,docs/b.md now.",
            "Reads `docs/a.md``docs/b.md` now.",
            "Reads docs/a.md docs/b.md now.",
            "Reads (docs/a.md)(docs/b.md) now.",
        ],
    )
    def test_two_references_sharing_one_separator_are_both_found(self, value: str) -> None:
        """The boundary is consumed, so the closing guard must not be.

        A scan does not revisit a character an earlier match consumed. With
        two references separated by exactly one character, that character is
        the second match's opening boundary, so consuming it at the end of the
        first match loses the second reference entirely. The trailing guard is
        a zero-width lookahead for that reason.
        """
        refs = [ref for _, _, ref in gate.scan_file(Path("x.md"), _frontmatter(value))]
        assert refs == ["docs/a.md", "docs/b.md"]

    def test_an_absolute_path_is_still_a_path(self) -> None:
        """A leading slash does not make the target ship.

        The old boundary rejected the slash, so spelling the same unshipped
        file as ``/docs/a.md`` walked past the gate.
        """
        assert gate.scan_file(Path("x.md"), _frontmatter("Reads /docs/a.md.")) != []

    def test_a_directory_that_merely_contains_a_watched_name_is_not_a_path(self) -> None:
        """Pins the cost of admitting a leading slash.

        ``docs`` is watched as a top-level directory. Allowing a slash in front
        of the whole path must not also allow one in front of the directory
        name, or every nested ``src/docs/...`` becomes a false positive.
        """
        assert gate.scan_file(Path("x.md"), _frontmatter("Reads src/docs/a.md.")) == []

    @pytest.mark.parametrize("ext", ["md", "markdown", "py", "ps1", "yaml"])
    def test_a_longer_extension_is_still_an_extension(self, ext: str) -> None:
        """The extension cap was four characters, and ``markdown`` is eight.

        The cap is a heuristic for telling a file from a directory, not a claim
        about which file types matter, so a real extension must not fall off
        the end of it.
        """
        assert gate.scan_file(Path("x.md"), _frontmatter(f"Reads docs/a.{ext}.")) != []

    @pytest.mark.parametrize(
        "reference",
        ["docs/c++/notes.md", "docs/a+b.md", ".github/c++/x.md"],
    )
    def test_a_plus_inside_a_path_does_not_end_the_path(self, reference: str) -> None:
        """A character missing from the interior class drops the whole path.

        Matching stops at the unknown character, and because the pattern still
        has to close on an extension the partial match fails outright. There is
        no other candidate start inside these strings, so the reference does not
        get truncated at the plus, it disappears. Both shapes here returned no
        match before ``+`` joined the interior class.
        """
        assert gate.scan_file(Path("x.md"), _frontmatter(f"Reads {reference}.")) != []

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

    def test_flags_a_path_with_spaces(self) -> None:
        found = gate.scan_file(Path("x.md"), _frontmatter("Read docs/My Guide.md first."))
        assert [ref for _, _, ref in found] == ["docs/My Guide.md"]

    def test_normalizes_windows_separators(self) -> None:
        text = "---\ndescription: 'Read docs\\secret.md first.'\n---\n"
        found = gate.scan_file(Path("x.md"), text)
        assert [ref for _, _, ref in found] == ["docs/secret.md"]

    @pytest.mark.parametrize(
        "value",
        [
            '"Read docs/My Guide.md first."',
            "'Read docs/My Guide.md first.'",
            "'`Read docs/My Guide.md first.`'",
            "'[guide](docs/My Guide.md)'",
        ],
    )
    def test_extracts_paths_from_markdown_containers(self, value: str) -> None:
        found = gate.scan_file(Path("x.md"), _frontmatter(value))
        assert [ref for _, _, ref in found] == ["docs/My Guide.md"]

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

    @pytest.mark.parametrize(
        "phrase",
        ["Use C++ and docs", "C++/CLI is a thing", "a+b.md alone", "scores are 1+2"],
    )
    def test_a_plus_alone_does_not_make_a_path(self, phrase: str) -> None:
        """Pins the cost of admitting ``+`` to the interior class.

        ``+`` only appears between a watched directory and an extension, so it
        can never open a match by itself. Without that anchoring the widening
        would read ordinary C++ prose as a reference, which is the trade that
        kept it out of the extension alphabet.
        """
        assert gate.scan_file(Path("x.md"), _frontmatter(f"{phrase}.")) == []

    def test_ignores_bundled_templates_directory(self) -> None:
        """A skill may ship its own templates/. Only agents/ and platforms/ are upstream."""
        text = _frontmatter("Uses templates/threat-model-template.md from this skill.")
        assert gate.scan_file(Path("x.md"), text) == []

    @pytest.mark.parametrize(
        "reference",
        [".claude/skills/foo/SKILL.md", "src/copilot-cli/lib/paths.py"],
    )
    def test_detects_a_root_prefixed_path(self, reference: str) -> None:
        """The rule forbids this spelling twice over, so the gate must see it.

        MUST-2 bans a bare in-root path because it "resolves only when the
        consumer's working directory happens to match", and MUST-3 bans
        reaching across roots because the roots install separately. An earlier
        draft asserted the opposite, on the reasoning that a plugin root ships
        and therefore anything under it resolves. The root ships; the
        repo-relative spelling of it does not travel with it.
        """
        assert gate.scan_file(Path("x.md"), _frontmatter(f"Reads {reference}.")) != []

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

    def test_the_leading_dot_of_a_root_is_a_literal(self) -> None:
        """Kills the mutant that drops ``re.escape`` from the root prefixes.

        Unescaped, ``.claude`` is a wildcard followed by ``claude``, so a
        directory named ``xclaude/`` matches and a consumer-workspace path gets
        hard-blocked by a gate with no baseline.
        """
        assert gate.scan_file(Path("x.md"), _frontmatter("Reads xclaude/a.md.")) == []
        assert gate.scan_file(Path("x.md"), _frontmatter("Reads .claude/a.md.")) != []


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
    def test_an_indented_opening_marker_is_not_frontmatter(self) -> None:
        """A block that does not open at column zero is not frontmatter.

        No loader reads it as frontmatter, so neither does the gate. Trimming
        the left of the opening line instead of the right invents a block the
        consumer never sees and reports references out of ordinary body text.
        """
        text = "  ---\ndescription: Reads docs/a.md.\n---\n# body\n"
        assert gate.frontmatter_lines(text) == []
        assert gate.scan_file(Path("x.md"), text) == []

    def test_an_indented_marker_does_not_close_the_block(self) -> None:
        """A YAML fence lives at column zero, so an indented one is content.

        Inside a block scalar the three dashes are text. Treating them as the
        closing fence truncates the block, and every reference after that line
        disappears while the loader that actually reads the file still sees it.
        """
        text = (
            "---\n"
            "description: |\n"
            "  Intro line.\n"
            "  ---\n"
            "  Reads docs/agent-catalog.md for the roster.\n"
            "---\n"
            "# body\n"
        )
        assert gate.scan_file(Path("x.md"), text) != []

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
    def test_derives_plugin_sources_from_both_marketplace_manifests(self, tmp_path: Path) -> None:
        _write_marketplace_manifests(tmp_path, (".claude", "new-plugin"))
        (tmp_path / ".claude").mkdir()
        (tmp_path / "new-plugin").mkdir()
        roots = gate.plugin_roots(tmp_path)
        assert roots == (".claude", "new-plugin")

    def test_main_scans_manifest_source_not_named_in_the_old_constant(
        self, tmp_path: Path, capsys
    ) -> None:
        _write_marketplace_manifests(tmp_path, ("new-plugin",))
        skill = tmp_path / "new-plugin" / "skills" / "manifest-source"
        skill.mkdir(parents=True)
        (skill / "bad.md").write_text(_frontmatter("Per docs/a.md."), encoding="utf-8")
        assert gate.main(["--repo-root", str(tmp_path)]) == 1
        assert "new-plugin/skills/manifest-source/bad.md:2" in capsys.readouterr().err

    def test_scans_a_legitimate_worktrees_directory(self, tmp_path: Path) -> None:
        """A directory name alone must not remove shipped plugin files."""
        _write_marketplace_manifests(tmp_path, (".claude",))
        (tmp_path / ".claude" / "skills" / "worktrees").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "worktrees" / "SKILL.md").write_text(
            _frontmatter("Per docs/a.md."), encoding="utf-8"
        )
        (tmp_path / ".claude" / "skills" / "real.md").write_text(
            "---\nname: r\n---\n", encoding="utf-8"
        )
        found = [p.name for p in gate.iter_markdown(tmp_path)]
        assert found == ["real.md", "SKILL.md"]

    def test_scans_every_plugin_root(self, tmp_path: Path) -> None:
        _write_marketplace_manifests(tmp_path)
        for root in gate.PLUGIN_ROOTS:
            target = tmp_path / root / "skills"
            target.mkdir(parents=True)
            (target / "a.md").write_text("---\nname: a\n---\n", encoding="utf-8")
        assert len(gate.iter_markdown(tmp_path)) == len(gate.PLUGIN_ROOTS)

    def test_missing_root_is_a_config_error(self, tmp_path: Path) -> None:
        _write_marketplace_manifests(tmp_path)
        (tmp_path / ".claude").mkdir()
        with pytest.raises(gate.ConfigError):
            gate.iter_markdown(tmp_path)

    def test_main_returns_config_error_when_manifest_source_is_missing(
        self, tmp_path: Path, capsys
    ) -> None:
        _write_marketplace_manifests(tmp_path, (".claude", "missing-root"))
        (tmp_path / ".claude").mkdir()
        assert gate.main(["--repo-root", str(tmp_path)]) == 2
        assert "Plugin source directory does not exist: missing-root" in capsys.readouterr().err

    def test_a_checkout_path_named_worktrees_does_not_hide_files(self, tmp_path: Path) -> None:
        repo = tmp_path / "worktrees" / "ai-agents"
        _write_marketplace_manifests(repo, (".claude",))
        (repo / ".claude" / "skills").mkdir(parents=True)
        (repo / ".claude" / "skills" / "real.md").write_text(
            "---\nname: r\n---\n", encoding="utf-8"
        )
        assert [p.name for p in gate.iter_markdown(repo)] == ["real.md"]


class TestCli:
    """Exit codes are pinned to literals: CI reads the number, not the constant."""

    def test_clean_tree_exits_zero(self, tmp_path: Path, capsys) -> None:
        _write_marketplace_manifests(tmp_path, (".claude",))
        skills = tmp_path / ".claude" / "skills"
        skills.mkdir(parents=True)
        (skills / "a.md").write_text(_frontmatter("Self-contained."), encoding="utf-8")
        assert gate.main(["--repo-root", str(tmp_path)]) == 0
        assert "No outward frontmatter references" in capsys.readouterr().out

    def test_violation_exits_one_and_names_the_file(self, tmp_path: Path, capsys) -> None:
        _write_marketplace_manifests(tmp_path, (".claude",))
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
        assert "Marketplace manifest not found" in capsys.readouterr().err

    def test_utf16_frontmatter_is_a_config_error(self, tmp_path: Path, capsys) -> None:
        _write_marketplace_manifests(tmp_path, (".claude",))
        skill = tmp_path / ".claude" / "skills"
        skill.mkdir(parents=True)
        (skill / "bad.md").write_bytes(_frontmatter("Read docs/secret.md").encode("utf-16"))
        assert gate.main(["--repo-root", str(tmp_path)]) == 2
        assert "Could not read" in capsys.readouterr().err

    def test_unparseable_frontmatter_is_a_config_error(self, tmp_path: Path, capsys) -> None:
        _write_marketplace_manifests(tmp_path, (".claude",))
        skill = tmp_path / ".claude" / "skills"
        skill.mkdir(parents=True)
        (skill / "bad.md").write_text(
            '---\n{"description": "Read docs/secret.md", broken\n---\n',
            encoding="utf-8",
        )
        assert gate.main(["--repo-root", str(tmp_path)]) == 2
        assert "Unparseable frontmatter" in capsys.readouterr().err

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
        ships = gate.reference_shipper(root, "src/copilot-cli", root / "src/copilot-cli/skills/x")
        assert gate.scan_file(Path("x.md"), text, ships) == []

    def test_the_same_reference_under_a_root_without_it_is_flagged(self) -> None:
        root = Path(__file__).resolve().parents[2]
        text = _frontmatter("Per docs/copilot-instructions.md.")
        ships = gate.reference_shipper(root, ".claude", root / ".claude/skills/x")
        assert [ref for _, _, ref in gate.scan_file(Path("x.md"), text, ships)] == [
            "docs/copilot-instructions.md"
        ]

    def test_a_traversal_never_counts_as_shipped(self, tmp_path: Path) -> None:
        """`root/../docs/a.md` exists on disk but is outside the plugin root."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "a.md").write_text("x", encoding="utf-8")
        (tmp_path / ".claude").mkdir()
        ships = gate.reference_shipper(tmp_path, ".claude", tmp_path / ".claude")
        assert ships("../docs/a.md") is False

    def test_a_traversal_in_the_middle_never_counts_as_shipped(self, tmp_path: Path) -> None:
        """A traversal need not lead the path to escape the root.

        Kills the mutant that tests `candidate.startswith("../")`. The escaping
        form resolves on disk, so a leading-prefix test suppresses a real
        outward reference.
        """
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "a.md").write_text("x", encoding="utf-8")
        (tmp_path / ".claude" / "docs").mkdir(parents=True)
        ships = gate.reference_shipper(tmp_path, ".claude", tmp_path / ".claude")
        escaping = "docs/../../docs/a.md"
        assert (tmp_path / ".claude" / escaping).exists()
        assert ships(escaping) is False

    def test_consecutive_dots_in_a_filename_are_not_a_traversal(self, tmp_path: Path) -> None:
        """Kills the mutant that tests `".." in candidate` as a substring.

        A filename may contain two dots without escaping anything, and the
        substring form would refuse to resolve a file the consumer really has.
        """
        (tmp_path / ".claude" / "docs").mkdir(parents=True)
        (tmp_path / ".claude" / "docs" / "a..b.md").write_text("x", encoding="utf-8")
        ships = gate.reference_shipper(tmp_path, ".claude", tmp_path / ".claude")
        assert ships("docs/a..b.md") is True

    def test_a_skill_that_bundles_its_own_directory_is_clean(self, tmp_path: Path) -> None:
        """The skill-bundle convention: 90 skills here ship their own scripts/.

        Resolving only against the plugin root would look for
        `.claude/scripts/collect.py` and flag a file the consumer actually
        installed one directory down.
        """
        skill = tmp_path / ".claude" / "skills" / "demo"
        (skill / "scripts").mkdir(parents=True)
        (skill / "scripts" / "collect.py").write_text("x", encoding="utf-8")
        ships = gate.reference_shipper(tmp_path, ".claude", skill)
        assert ships("scripts/collect.py") is True

    def test_a_sibling_skills_bundle_does_not_launder_a_reference(self, tmp_path: Path) -> None:
        """File-relative resolution is relative to *this* file, not any skill."""
        other = tmp_path / ".claude" / "skills" / "other"
        (other / "scripts").mkdir(parents=True)
        (other / "scripts" / "collect.py").write_text("x", encoding="utf-8")
        mine = tmp_path / ".claude" / "skills" / "mine"
        mine.mkdir(parents=True)
        ships = gate.reference_shipper(tmp_path, ".claude", mine)
        assert ships("scripts/collect.py") is False

    def test_a_dot_slash_prefix_still_resolves(self, tmp_path: Path) -> None:
        (tmp_path / ".claude" / "docs").mkdir(parents=True)
        (tmp_path / ".claude" / "docs" / "a.md").write_text("x", encoding="utf-8")
        ships = gate.reference_shipper(tmp_path, ".claude", tmp_path / ".claude")
        assert ships("./docs/a.md") is True
        assert ships("docs/b.md") is False

    def test_owning_root_maps_each_root_and_rejects_outsiders(self) -> None:
        root = Path("/repo")
        for name in gate.PLUGIN_ROOTS:
            assert gate.owning_root(root / name / "skills" / "x" / "SKILL.md", root) == name
        assert gate.owning_root(root / "templates" / "agents" / "x.md", root) is None

    def test_plugin_roots_are_pinned(self) -> None:
        """Losing a manifest source silently shrinks the gate."""
        root = Path(__file__).resolve().parents[2]
        assert gate.PLUGIN_ROOTS == gate.plugin_roots(root)

    def test_root_prefixed_detection_tracks_the_pinned_roots(self) -> None:
        """Adding a root must extend detection, not just the scan.

        Asserted through the matcher rather than against the constant, so a
        hand-maintained list that drifts from ``PLUGIN_ROOTS`` fails here.
        """
        for name in gate.PLUGIN_ROOTS:
            reference = f"{name}/skills/x/SKILL.md"
            assert gate.OUTWARD_FILE.findall(reference) == [reference], name

    def test_resolution_does_not_launder_a_root_prefixed_path(self, tmp_path: Path) -> None:
        """The discriminating case for the two-base resolution.

        The target really exists in the root that ships the file naming it, so
        a resolver that stripped the root prefix, or that resolved against the
        repository instead of the plugin, would call this clean. It is not:
        the consumer receives the root's contents at whatever path their
        harness installs to, so the repo-relative spelling has nowhere to land.
        The relative spelling of the same file, asserted alongside, still
        resolves, which is what keeps this from being a blanket ban.
        """
        (tmp_path / ".claude" / "rules").mkdir(parents=True)
        (tmp_path / ".claude" / "rules" / "y.md").write_text("x", encoding="utf-8")
        ships = gate.reference_shipper(tmp_path, ".claude", tmp_path / ".claude")
        assert ships("rules/y.md") is True
        assert ships(".claude/rules/y.md") is False

    def test_a_cross_root_reference_is_flagged_even_when_the_target_exists(self) -> None:
        """MUST-3. The roots install separately, so neither may reach the other."""
        root = Path(__file__).resolve().parents[2]
        text = _frontmatter("Mirrors .claude/rules/plugin-self-containment.md.")
        assert (root / ".claude/rules/plugin-self-containment.md").is_file()
        ships = gate.reference_shipper(root, "src/copilot-cli", root / "src/copilot-cli/skills/x")
        assert [ref for _, _, ref in gate.scan_file(Path("x.md"), text, ships)] == [
            ".claude/rules/plugin-self-containment.md"
        ]


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
    """Frontmatter is YAML, so every valid spelling must be read.

    A line-oriented reader matches ``description:`` at line start and walks
    past a quoted key, a flow mapping, or an escape that encodes the path
    separator. All three are valid YAML that a consumer's loader resolves to
    the same string, so all three must be caught. The line scan survives only
    as the fallback for frontmatter a real loader rejects.
    """

    @pytest.mark.parametrize(
        "block",
        [
            pytest.param('"description": "Per docs/a.md."', id="quoted-key"),
            pytest.param('{"description": "Per docs/a.md"}', id="flow-mapping"),
            pytest.param('description: "Per docs\\u002fa.md."', id="escaped-separator"),
            pytest.param("description: >-\n  Per docs/a.md.", id="folded-scalar"),
            pytest.param("'description': Per docs/a.md.", id="single-quoted-key"),
        ],
    )
    def test_every_valid_yaml_spelling_is_caught(self, block: str) -> None:
        text = f"---\n{block}\n---\n"
        found = [ref for _, _, ref in gate.scan_file(Path("x.md"), text)]
        assert found == ["docs/a.md"], f"bypassed by {block!r}"

    def test_invalid_yaml_is_a_config_error(self) -> None:
        """A value the validator cannot parse is not a clean value."""
        text = "---\nname: {{PLACEHOLDER}\ndescription: Per docs/a.md.\n---\n"
        with pytest.raises(yaml.YAMLError):
            yaml.safe_load(text.split("---")[1])
        with pytest.raises(gate.FrontmatterParseError):
            gate.scan_file(Path("x.md"), text)

    def test_valid_yaml_that_is_not_a_mapping_degrades_instead_of_crashing(self) -> None:
        """Kills the mutant that tests ``not data`` instead of the type.

        A sequence is valid YAML and parses to a truthy list, so a falsiness
        test lets it through to ``data.get`` and the gate dies with an
        ``AttributeError`` on a file it was asked to check, taking the whole
        run down with it. The type test sends it to the line scan instead,
        which finds nothing here because a sequence has no key at line start.
        Finding nothing is the right answer: a sequence is not frontmatter any
        loader accepts, so there is no description for a consumer to misread.
        Not dying is the property under test.
        """
        text = "---\n- description: Per docs/a.md.\n---\n"
        assert isinstance(yaml.safe_load(text.split("---")[1]), list)
        assert gate.scan_file(Path("x.md"), text) == []

    def test_a_commented_key_does_not_claim_the_real_key_line(self) -> None:
        """The report has to point at the line the author must edit.

        ``_key_line`` searches rather than anchors, so that a key inside a flow
        mapping still reports its own line. That same looseness let a
        commented-out key one line above claim the number.
        """
        text = "---\n# description: some note\ndescription: Per docs/a.md.\n---\n"
        assert gate.scan_file(Path("x.md"), text) == [(3, "description", "docs/a.md")]

    def test_placeholder_templates_still_read_continuation_lines(self) -> None:
        """The only YAML fallback is the shipped placeholder template shape."""
        text = (
            "---\n"
            "name: {{PLACEHOLDER}}\n"
            "description: A description long enough to wrap\n"
            "  onto a second line that carries docs/a.md with it.\n"
            "---\n"
        )
        with pytest.raises(yaml.YAMLError):
            yaml.safe_load(text.split("---")[1])
        assert [ref for _, _, ref in gate.scan_file(Path("x.md"), text)] == ["docs/a.md"]

    def test_the_rejected_templates_still_exist_and_still_scan(self) -> None:
        """Pins the premise for the fallback. If these parse, simplify this."""
        root = Path(__file__).resolve().parents[2]
        template = root / ".claude/skills/skillforge/assets/templates/skill-md-template.md"
        assert template.is_file()
        text = template.read_text(encoding="utf-8", errors="replace")
        lines = gate.frontmatter_lines(text)
        with pytest.raises(yaml.YAMLError):
            yaml.safe_load("\n".join(line for _, line in lines))
        gate.checked_values(text)

    def test_main_resolves_references_against_the_owning_root(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """End to end, so the CLI cannot quietly stop passing the shipper.

        Unit tests hand ``scan_file`` a shipper directly, which leaves the
        wiring in ``main`` untested. Dropping that one line reintroduces the
        false positive this class exists to prevent, and every unit test stays
        green. This is the test that goes red.
        """
        _write_marketplace_manifests(tmp_path, ("src/copilot-cli", ".claude"))
        (tmp_path / ".claude").mkdir()
        shipped = tmp_path / "src/copilot-cli"
        (shipped / "docs").mkdir(parents=True)
        (shipped / "docs" / "guide.md").write_text("x", encoding="utf-8")
        (shipped / "skills").mkdir()
        (shipped / "skills" / "a.md").write_text(
            _frontmatter("Per docs/guide.md."), encoding="utf-8"
        )
        assert gate.main(["--repo-root", str(tmp_path)]) == 0

        (tmp_path / ".claude" / "b.md").write_text(
            _frontmatter("Per docs/guide.md."), encoding="utf-8"
        )
        assert gate.main(["--repo-root", str(tmp_path)]) == 1
        assert "docs/guide.md" in capsys.readouterr().err

    def test_main_resolves_references_against_the_files_own_directory(
        self, tmp_path: Path
    ) -> None:
        """End to end, so the CLI cannot quietly stop passing the file's directory.

        Every unit test builds the shipper itself, which leaves ``main`` free to
        pass the plugin root instead of the directory holding the file. That
        swap reintroduces the false positive against the skill-bundle
        convention while the whole unit suite stays green.
        """
        _write_marketplace_manifests(tmp_path, (".claude",))
        skill = tmp_path / ".claude" / "skills" / "demo"
        (skill / "scripts").mkdir(parents=True)
        (skill / "scripts" / "collect.py").write_text("x", encoding="utf-8")
        (skill / "SKILL.md").write_text(
            _frontmatter("Run scripts/collect.py to gather the data."), encoding="utf-8"
        )
        assert not (tmp_path / ".claude" / "scripts").exists()
        assert gate.main(["--repo-root", str(tmp_path)]) == 0

    def test_main_does_not_launder_a_root_prefixed_path(self, tmp_path: Path) -> None:
        """End to end, so the CLI cannot quietly strip the root before resolving.

        The existing root-prefix tests call ``reference_shipper`` directly, so
        ``main`` is free to hand it ``reference.removeprefix(".claude/")``. That
        makes every same-root spelling resolve and the whole unit suite stays
        green, because no unit test ever runs the path the CLI runs. The
        spelling is the violation: the target ships, but the repo-relative name
        for it does not travel with the root a consumer installs.
        """
        _write_marketplace_manifests(tmp_path, (".claude",))
        root = tmp_path / ".claude"
        (root / "rules").mkdir(parents=True)
        (root / "rules" / "y.md").write_text("x", encoding="utf-8")
        (root / "skills").mkdir()
        (root / "skills" / "a.md").write_text(
            _frontmatter("Per rules/y.md."), encoding="utf-8"
        )
        assert gate.main(["--repo-root", str(tmp_path)]) == 0

        (root / "skills" / "a.md").write_text(
            _frontmatter("Per .claude/rules/y.md."), encoding="utf-8"
        )
        assert gate.main(["--repo-root", str(tmp_path)]) == 1


class TestUriHandling:
    """A path inside a URI belongs to the scheme, not to the filesystem.

    Whether that makes it exempt depends on whether the reader can resolve it.
    A remote URI resolves for anyone, so its tail is not a reference. A
    ``file:`` URI resolves only on the author's machine, so it is the least
    portable reference this gate can see.
    """

    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/rjmurillo/ai-agents/wiki?page=docs/setup.md",
            "https://example.com/wiki#docs/setup.md",
            "https://example.com/a?x=1&y=docs/setup.md",
            "https://github.com/rjmurillo/ai-agents/blob/main/docs/setup.md",
        ],
    )
    def test_a_path_inside_a_remote_uri_is_not_a_reference(self, url: str) -> None:
        assert gate.scan_file(Path("x.md"), _frontmatter(f"Read more at {url}")) == []

    def test_a_reference_after_an_equals_sign_is_still_a_reference(self) -> None:
        """Pins why the URI is removed rather than the path boundary widened.

        Adding the equals sign to the boundary would pass every case above and
        silently lose this one, which is a real reference shape.
        """
        text = _frontmatter("Run with --config=docs/a.md now.")
        assert [ref for _, _, ref in gate.scan_file(Path("x.md"), text)] == ["docs/a.md"]

    @pytest.mark.parametrize(
        "value",
        [
            "See http://example.com,docs/a.md for both.",
            "See <http://example.com>docs/a.md for both.",
            "See http://example.com;docs/a.md for both.",
        ],
    )
    def test_a_reference_touching_a_uri_survives_the_strip(self, value: str) -> None:
        """A greedy tail turns a precision fix into a silent miss.

        Matching to the next whitespace swallows the reference that follows a
        URI with only punctuation between them, so the strip stops at the
        characters that enclose a URI in prose instead.
        """
        assert [ref for _, _, ref in gate.scan_file(Path("x.md"), _frontmatter(value))] == [
            "docs/a.md"
        ]

    def test_a_local_file_uri_is_a_violation(self) -> None:
        """It names the author's disk, so nothing about it survives shipping.

        It is reported whole because the part a consumer cannot use is the
        scheme, not the tail.
        """
        text = _frontmatter("Read file:///home/rich/src/ai-agents/docs/a.md now.")
        refs = [ref for _, _, ref in gate.scan_file(Path("x.md"), text)]
        assert refs == ["file:///home/rich/src/ai-agents/docs/a.md"]

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Mail mailto:a@b.example?subject=docs/a.md now.", []),
            ("Dial tel:+15551234567 for docs/a.md", ["docs/a.md"]),
            ("See urn:isbn:0451450523 and docs/a.md", ["docs/a.md"]),
        ],
    )
    def test_an_opaque_uri_tail_is_not_a_reference(
        self, value: str, expected: list[str]
    ) -> None:
        """Its tail is an address or a payload, not a path.

        The expectation is exact per case rather than "either shape". A range
        assertion here passes whether or not the strip runs, which is the same
        as not testing it.
        """
        refs = [ref for _, _, ref in gate.scan_file(Path("x.md"), _frontmatter(value))]
        assert refs == expected

    def test_the_opaque_scheme_list_is_explicit_not_a_pattern(self) -> None:
        """A general ``scheme:`` pattern also matches ordinary prose.

        ``Note:docs/a.md`` has the shape of an opaque URI, so a general pattern
        exempts it and the reference disappears.
        """
        text = _frontmatter("Note:docs/a.md is the file.")
        assert [ref for _, _, ref in gate.scan_file(Path("x.md"), text)] == ["docs/a.md"]


    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Read file:///docs/a.md.", "file:///docs/a.md"),
            ("See file:///docs/a.md!", "file:///docs/a.md"),
            ("Which file:///docs/a.md?", "file:///docs/a.md"),
            ("Bare file:///docs/a.md", "file:///docs/a.md"),
        ],
    )
    def test_a_local_uri_does_not_absorb_sentence_punctuation(
        self, value: str, expected: str
    ) -> None:
        """A period ending the sentence is not part of the URI.

        This is not cosmetic. The opt-out compares the reported string against
        the declared one, so a trailing period on one side and not the other
        silently defeats a correct declaration.
        """
        refs = [ref for _, _, ref in gate.scan_file(Path("x.md"), _frontmatter(value))]
        assert refs == [expected]

    def test_a_local_uri_can_be_declared(self) -> None:
        """The opt-out the failure message advertises has to be reachable.

        ``declared_paths`` read markers with ``OUTWARD_FILE`` alone, which
        cannot produce a ``file:/`` string, so ``declared`` was always empty for
        a local URI and the documented escape hatch could never be taken.
        """
        text = (
            _frontmatter("Read file:///docs/a.md.")
            + "\n<!-- vendor-portability: file:///docs/a.md -->\n"
        )
        assert gate.scan_file(Path("x.md"), text) == []

    def test_an_undeclared_local_uri_is_still_a_violation(self) -> None:
        """Making the opt-out reachable must not make it automatic."""
        text = (
            _frontmatter("Read file:///docs/a.md.") + "\n<!-- vendor-portability: docs/b.md -->\n"
        )
        refs = [ref for _, _, ref in gate.scan_file(Path("x.md"), text)]
        assert refs == ["file:///docs/a.md"]

    def test_a_file_uri_inside_a_remote_url_is_not_a_local_reference(self) -> None:
        """A query string is part of the remote address, not a local path."""
        value = "See <https://example.test/?redirect=file:///docs/a.md>"
        assert gate.scan_file(Path("x.md"), _frontmatter(value)) == []

    def test_a_standalone_file_uri_survives_the_remote_strip(self) -> None:
        """The converse of the test above, and the reason for the ``file:`` guard.

        ``REMOTE_URI`` matches any ``scheme://``, which includes ``file://``.
        Since the local scan now reads the stripped value, dropping the guard
        erases every local URI here and the check passes on a real violation.
        """
        refs = [
            ref
            for _, _, ref in gate.scan_file(Path("x.md"), _frontmatter("Read file:///docs/a.md."))
        ]
        assert refs == ["file:///docs/a.md"]

    def test_a_data_payload_is_not_a_reference(self) -> None:
        """``data:`` carries its payload after a comma, where the shared tail stops."""
        assert gate.scan_file(Path("x.md"), _frontmatter("See data:text/plain,docs/a.md")) == []

    def test_a_url_in_a_marker_does_not_declare_a_path(self) -> None:
        """An opt-out a URL can trigger is not an opt-out.

        The marker names a remote address whose query happens to contain a
        path-shaped value. Reading it without stripping URIs waived a real
        violation elsewhere in the same file.
        """
        text = (
            _frontmatter("Per docs/a.md.")
            + "\n<!-- vendor-portability: https://example.test/?path=docs/a.md -->\n"
        )
        refs = [ref for _, _, ref in gate.scan_file(Path("x.md"), text)]
        assert refs == ["docs/a.md"]

    def test_a_marker_naming_the_path_plainly_still_waives(self) -> None:
        """Closing the laundering path must not close the escape hatch."""
        text = _frontmatter("Per docs/a.md.") + "\n<!-- vendor-portability: docs/a.md -->\n"
        assert gate.scan_file(Path("x.md"), text) == []

    def test_an_absolute_reference_is_never_shipped(self, tmp_path: Path) -> None:
        """``base / "/docs/a.md"`` discards the base, so the test leaks to the host.

        Without the guard the existence question is asked of the build machine
        rather than of shipped content. ``/build`` and ``/scripts`` are ordinary
        directories in a container image and both spell a watched directory, so
        an absolute reference would be laundered into "shipped" by the image.
        """
        (tmp_path / ".claude").mkdir()
        ships = gate.reference_shipper(tmp_path, ".claude", tmp_path / ".claude")
        assert ships("/docs/a.md") is False

    def test_an_absolute_reference_asks_nothing_of_the_host(self, tmp_path: Path) -> None:
        """The guard must short-circuit, not merely produce the right answer.

        A version that resolved first and rejected after would still stat a host
        path, which is the behaviour that made the laundering possible.
        """
        (tmp_path / ".claude").mkdir()
        ships = gate.reference_shipper(tmp_path, ".claude", tmp_path / ".claude")
        seen: list[str] = []

        def fake_exists(candidate: Path) -> bool:
            seen.append(str(candidate))
            return True

        with mock.patch.object(Path, "exists", fake_exists):
            result = ships("/docs/a.md")
        assert result is False
        assert seen == []
