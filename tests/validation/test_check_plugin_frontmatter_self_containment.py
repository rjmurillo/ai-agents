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
    def test_declaration_suppresses_the_file(self) -> None:
        text = "<!-- vendor-portability: contributor-facing -->\n" + _frontmatter(
            "Per docs/a.md."
        )
        assert gate.scan_file(Path("x.md"), text) == []

    def test_declaration_is_case_insensitive(self) -> None:
        text = "<!-- Vendor-Portability: x -->\n" + _frontmatter("Per docs/a.md.")
        assert gate.scan_file(Path("x.md"), text) == []

    def test_declaration_below_the_frontmatter_still_counts(self) -> None:
        text = _frontmatter("Per docs/a.md.") + "\n<!-- vendor-portability: real -->\n"
        assert gate.scan_file(Path("x.md"), text) == []


class TestFrontmatterParsing:
    def test_no_frontmatter_means_nothing_scanned(self) -> None:
        assert gate.frontmatter_lines("# Title\n\ndescription: docs/a.md\n") == []

    def test_unterminated_frontmatter_is_not_frontmatter(self) -> None:
        """Otherwise the whole body would be scanned as frontmatter."""
        assert gate.frontmatter_lines("---\ndescription: docs/a.md\n\n# Body\n") == []

    def test_empty_file(self) -> None:
        assert gate.frontmatter_lines("") == []

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
