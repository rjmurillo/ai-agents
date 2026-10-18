"""Tests for the Claude deny-list expansion (ADR-107, "Read-only agents inherit tools").

Covers `agent_capabilities` (load, expand, frontmatter substitution, mutator
coverage), the `agent_templates` compile path, the `check_agent_source_parity`
handling of deny-list members, and the Cursor `readonly` derivation that reads
the same frontmatter.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "build" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import agent_capabilities as caps  # noqa: E402
import agent_templates  # noqa: E402
import agent_tree_copy  # noqa: E402
import check_agent_source_parity as gate  # noqa: E402

LIVE = caps.load_denylists(_REPO_ROOT)

CONFIG = {
    "prefix_variants": [
        "mcp__{server}",
        "mcp__plugin_{server}_{server}",
        "mcp__claude_ai_{claude_ai}",
    ],
    "servers": {"demo": {"claude_ai": ["Demo", "demo"]}},
    "denylists": {
        "demo-write": {"server": "demo", "tools": ["put_thing", "drop_thing"]},
        "mutators": {"tools": ["Bash", "Edit", "Write", "MultiEdit", "NotebookEdit"]},
    },
}

READ_TOOLS = (
    "read_memory",
    "list_memories",
    "find_symbol",
    "find_referencing_symbols",
    "get_symbols_overview",
    "pull_request_read",
    "issue_read",
    "get_file_contents",
    "get_commit",
    "list_commits",
    "search_code",
    "get_job_logs",
)


class TestExpandDeny:
    def test_server_list_emits_every_prefix_variant(self) -> None:
        got = caps.expand_deny("demo-write", CONFIG)

        assert len(got) == 2 * 4
        for prefix in ("mcp__demo", "mcp__plugin_demo_demo", "mcp__claude_ai_Demo"):
            assert f"{prefix}__put_thing" in got
            assert f"{prefix}__drop_thing" in got
        assert "mcp__claude_ai_demo__put_thing" in got

    def test_list_without_server_is_literal(self) -> None:
        assert caps.expand_deny("mutators", CONFIG) == [
            "Bash",
            "Edit",
            "Write",
            "MultiEdit",
            "NotebookEdit",
        ]

    def test_unknown_name_fails_closed(self) -> None:
        with pytest.raises(caps.CapabilityError, match="unknown deny list 'nope'"):
            caps.expand_deny("nope", CONFIG)

    def test_empty_config_fails_closed(self) -> None:
        with pytest.raises(caps.CapabilityError, match="unknown deny list"):
            caps.expand_deny("demo-write", {})

    def test_duplicate_variants_collapse(self) -> None:
        config = {**CONFIG, "prefix_variants": ["mcp__{server}", "mcp__{server}"]}
        assert len(caps.expand_deny("demo-write", config)) == 2

    @pytest.mark.parametrize(
        "patch,message",
        [
            ({"prefix_variants": []}, "prefix_variants must be a non-empty list"),
            ({"prefix_variants": ["bad_{server}"]}, "starting with 'mcp__'"),
            ({"prefix_variants": ["mcp__{nope}"]}, "unknown placeholder"),
            ({"servers": {}}, "no `servers` entry"),
            (
                {"servers": {"demo": {"claude_ai": []}}},
                "servers.demo.claude_ai must be a non-empty list",
            ),
            (
                {"servers": {"demo": {"claude_ai": ["bad name"]}}},
                "not a plain tool name",
            ),
        ],
    )
    def test_malformed_config_is_rejected(self, patch: dict[str, object], message: str) -> None:
        with pytest.raises(caps.CapabilityError, match=message):
            caps.expand_deny("demo-write", {**CONFIG, **patch})

    def test_non_string_server_is_rejected(self) -> None:
        config = {**CONFIG, "denylists": {"x": {"server": 3, "tools": ["a"]}}}
        with pytest.raises(caps.CapabilityError, match="server must be a string"):
            caps.expand_deny("x", config)

    def test_empty_tool_list_is_rejected(self) -> None:
        config = {**CONFIG, "denylists": {"x": {"tools": []}}}
        with pytest.raises(caps.CapabilityError, match="non-empty list"):
            caps.expand_deny("x", config)


class TestLiveTable:
    @pytest.mark.parametrize("name", ["serena-write", "github-write", "builtin-mutators"])
    def test_every_endorsed_list_expands(self, name: str) -> None:
        assert caps.expand_deny(name, LIVE)

    def test_serena_write_covers_all_variants(self) -> None:
        got = set(caps.expand_deny("serena-write", LIVE))

        for prefix in ("mcp__serena", "mcp__plugin_serena_serena", "mcp__claude_ai_Serena"):
            for tool in ("write_memory", "edit_memory", "delete_memory", "rename_symbol"):
                assert f"{prefix}__{tool}" in got

    def test_github_write_covers_all_variants(self) -> None:
        got = set(caps.expand_deny("github-write", LIVE))

        for prefix in ("mcp__github", "mcp__plugin_github_github", "mcp__claude_ai_GitHub"):
            assert f"{prefix}__merge_pull_request" in got
            assert f"{prefix}__issue_write" in got

    def test_builtin_mutators_cover_shell_and_editors(self) -> None:
        assert set(caps.expand_deny("builtin-mutators", LIVE)) == {
            "Bash",
            "Edit",
            "Write",
            "MultiEdit",
            "NotebookEdit",
        }

    @pytest.mark.parametrize("name", ["serena-write", "github-write"])
    def test_read_tools_are_never_denied(self, name: str) -> None:
        denied_tools = {entry.rsplit("__", 1)[1] for entry in caps.expand_deny(name, LIVE)}

        assert denied_tools.isdisjoint(READ_TOOLS)

    def test_every_denied_mcp_entry_is_classified_as_its_server(self) -> None:
        for entry in caps.expand_deny("serena-write", LIVE)[:1]:
            assert caps.classify(entry)[0] == "mcp:serena"


class TestExpandFrontmatter:
    TEXT = (
        "---\nname: x\ndisallowedTools:\n  - Agent\n  - $deny:demo-write\n---\n"
        "Body $deny:demo-write\n"
    )

    def test_item_is_replaced_and_indent_kept(self) -> None:
        out = caps.expand_deny_frontmatter(self.TEXT, CONFIG)

        front = yaml.safe_load(out.split("---\n")[1])
        assert front["disallowedTools"][0] == "Agent"
        assert "mcp__claude_ai_Demo__put_thing" in front["disallowedTools"]
        assert len(front["disallowedTools"]) == 1 + 8

    def test_body_mentions_are_untouched(self) -> None:
        assert caps.expand_deny_frontmatter(self.TEXT, CONFIG).endswith("Body $deny:demo-write\n")

    def test_unknown_name_raises(self) -> None:
        with pytest.raises(caps.CapabilityError, match="unknown deny list"):
            caps.expand_deny_frontmatter(self.TEXT.replace("demo-write", "typo", 1), CONFIG)

    def test_inline_reference_raises(self) -> None:
        text = "---\nname: x\ndisallowedTools: [$deny:demo-write]\n---\nbody\n"
        with pytest.raises(caps.CapabilityError, match="whole list item"):
            caps.expand_deny_frontmatter(text, CONFIG)

    def test_text_without_frontmatter_is_returned_unchanged(self) -> None:
        assert caps.expand_deny_frontmatter("- $deny:x\n", CONFIG) == "- $deny:x\n"

    def test_frontmatter_without_references_is_unchanged(self) -> None:
        text = "---\nname: x\n---\nbody\n"
        assert caps.expand_deny_frontmatter(text, CONFIG) == text


class TestLoadDenylists:
    def test_missing_file_is_empty(self, tmp_path: Path) -> None:
        assert caps.load_denylists(tmp_path) == {}

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        (tmp_path / "templates").mkdir()
        (tmp_path / caps.DENYLISTS_RELATIVE_PATH).write_text("a: [", encoding="utf-8")
        with pytest.raises(caps.CapabilityError, match="not valid YAML"):
            caps.load_denylists(tmp_path)

    def test_non_mapping_raises(self, tmp_path: Path) -> None:
        (tmp_path / "templates").mkdir()
        (tmp_path / caps.DENYLISTS_RELATIVE_PATH).write_text("- a\n", encoding="utf-8")
        with pytest.raises(caps.CapabilityError, match="must be a mapping"):
            caps.load_denylists(tmp_path)

    def test_undecodable_file_raises(self, tmp_path: Path) -> None:
        (tmp_path / "templates").mkdir()
        (tmp_path / caps.DENYLISTS_RELATIVE_PATH).write_bytes(b"\xff\xfe\x00bad")
        with pytest.raises(caps.CapabilityError, match="cannot read"):
            caps.load_denylists(tmp_path)


class TestMutatorCoverage:
    FULL = {"disallowedTools": ["Agent", "Bash", "Edit", "Write", "MultiEdit", "NotebookEdit"]}

    def test_full_list_is_covered(self) -> None:
        assert caps.is_deny_list_member(self.FULL)
        assert caps.uncovered_mutators(self.FULL) == []

    def test_comma_string_form_is_read(self) -> None:
        fm = {"disallowedTools": "Bash, Edit, Write, MultiEdit, NotebookEdit"}
        assert caps.uncovered_mutators(fm) == []

    def test_partial_list_reports_the_gap(self) -> None:
        assert caps.uncovered_mutators({"disallowedTools": ["Bash"]}) == [
            "Edit",
            "MultiEdit",
            "NotebookEdit",
            "Write",
        ]

    def test_agent_only_deny_is_not_a_deny_list_member(self) -> None:
        fm = {"disallowedTools": "Agent"}
        assert not caps.is_deny_list_member(fm)
        assert caps.uncovered_mutators(fm) == []

    def test_a_tools_allowlist_is_never_a_deny_list_member(self) -> None:
        fm = {"tools": ["Read", "Bash"], "disallowedTools": ["Bash"]}
        assert not caps.is_deny_list_member(fm)

    def test_no_keys_is_not_a_member(self) -> None:
        assert not caps.is_deny_list_member({})


def _write_pair(root: Path, claude: str, copilot: str = "---\nname: w\n---\nbody\n") -> None:
    agents = root / "templates" / "agents"
    (agents / "partials").mkdir(parents=True, exist_ok=True)
    (agents / "w.claude.md.tmpl").write_text(claude, encoding="utf-8")
    (agents / "w.copilot.md.tmpl").write_text(copilot, encoding="utf-8")
    (root / "templates" / "agent-denylists.yaml").write_text(
        yaml.safe_dump(CONFIG), encoding="utf-8"
    )


class TestCompile:
    CLAUDE = "---\nname: w\ndisallowedTools:\n  - $deny:mutators\n  - $deny:demo-write\n---\nbody\n"

    def test_render_writes_expanded_entries(self, tmp_path: Path) -> None:
        _write_pair(tmp_path, self.CLAUDE)

        result = agent_templates.compile_all(tmp_path, validate=False)

        assert result.exit_code == 0
        out = (tmp_path / "src" / "claude" / "agents" / "w.md").read_text(encoding="utf-8")
        assert "$deny" not in out
        assert "  - Bash\n" in out
        assert "  - mcp__plugin_demo_demo__drop_thing\n" in out

    def test_unknown_logical_name_fails_the_build(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_pair(tmp_path, self.CLAUDE.replace("demo-write", "typo"))

        result = agent_templates.compile_all(tmp_path, validate=False)

        assert result.exit_code == 2
        assert "unknown deny list 'typo'" in capsys.readouterr().err
        assert not (tmp_path / "src" / "claude" / "agents" / "w.md").exists()

    def test_missing_table_file_fails_the_build(self, tmp_path: Path) -> None:
        _write_pair(tmp_path, self.CLAUDE)
        (tmp_path / "templates" / "agent-denylists.yaml").unlink()

        assert agent_templates.compile_all(tmp_path, validate=False).exit_code == 2

    def test_invalid_table_file_fails_the_build(self, tmp_path: Path) -> None:
        _write_pair(tmp_path, self.CLAUDE)
        (tmp_path / "templates" / "agent-denylists.yaml").write_text("a: [", encoding="utf-8")

        assert agent_templates.compile_all(tmp_path, validate=False).exit_code == 2

    def test_validate_mode_reports_stale_expansion(self, tmp_path: Path) -> None:
        _write_pair(tmp_path, self.CLAUDE)
        agent_templates.compile_all(tmp_path, validate=False)
        config = {**CONFIG, "denylists": {**CONFIG["denylists"]}}
        config["denylists"]["demo-write"] = {"server": "demo", "tools": ["put_thing"]}
        (tmp_path / "templates" / "agent-denylists.yaml").write_text(
            yaml.safe_dump(config), encoding="utf-8"
        )

        result = agent_templates.compile_all(tmp_path, validate=True)

        assert result.exit_code == 1
        assert result.drifted

    def test_copilot_template_is_not_expanded(self, tmp_path: Path) -> None:
        copilot = "---\nname: w\ntools:\n  - $deny:demo-write\n---\nbody\n"
        _write_pair(tmp_path, self.CLAUDE, copilot)

        result = agent_templates.compile_all(tmp_path, validate=False)

        assert result.exit_code == 0
        assert "$deny:demo-write" in result.copilot_rendered["w"]


SHARED = (
    "---\nrole: executor\ndescription: Reads widgets.\nargument-hint: Pick a widget\n"
    "tools_vscode: [read, search]\ntools_copilot: [read, search]\n---\n# W\n\nIntro.\n"
)


def _claude(front: str) -> str:
    return (
        "---\nname: w\ndescription: Reads widgets.\nmetadata:\n  role: executor\n"
        f"argument-hint: Pick a widget\n{front}---\n# W\n\nIntro.\n"
    )


def _parity_repo(root: Path, front: str) -> Path:
    agents = root / "templates" / "agents"
    (agents / "partials").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (agents / "w.shared.md").write_text(SHARED, encoding="utf-8")
    (agents / "w.claude.md.tmpl").write_text(_claude(front), encoding="utf-8")
    (agents / "w.copilot.md.tmpl").write_text(SHARED, encoding="utf-8")
    (root / "templates" / "agent-denylists.yaml").write_text(
        yaml.safe_dump(CONFIG), encoding="utf-8"
    )
    return root


class TestParityHandlesDenyListMembers:
    FULL = "disallowedTools:\n  - Agent\n  - $deny:mutators\n  - $deny:demo-write\n"

    def test_full_deny_list_agrees_with_the_copilot_allowlist(self, tmp_path: Path) -> None:
        _parity_repo(tmp_path, self.FULL)

        found, missing = gate.collect_divergence(tmp_path)

        assert found == {}
        assert missing == []

    def test_deny_list_missing_a_mutator_is_a_divergence(self, tmp_path: Path) -> None:
        _parity_repo(tmp_path, "disallowedTools:\n  - Bash\n")

        found, _ = gate.collect_divergence(tmp_path)

        assert [key[2] for key in found] == ["capability:denylist"]

    def test_template_granting_bash_to_a_read_only_agent_diverges(self, tmp_path: Path) -> None:
        """A `tools` grant of Bash against the read-only Copilot list is flagged."""
        _parity_repo(tmp_path, "tools:\n  - Read\n  - Bash\n")

        found, _ = gate.collect_divergence(tmp_path)

        assert any(key[2].startswith("capability:") for key in found)
        assert gate.main(["--repo-root", str(tmp_path)]) == gate.EXIT_DIVERGED

    def test_agent_only_deny_stays_on_the_ordinary_comparison(self, tmp_path: Path) -> None:
        _parity_repo(tmp_path, "disallowedTools: Agent\n")

        found, _ = gate.collect_divergence(tmp_path)

        assert any(key[2] == "capability:declaration" for key in found)

    def test_unknown_deny_name_is_a_config_error(self, tmp_path: Path) -> None:
        _parity_repo(tmp_path, "disallowedTools:\n  - $deny:typo\n")

        assert gate.main(["--repo-root", str(tmp_path)]) == gate.EXIT_CONFIG

    def test_invalid_denylist_file_is_a_config_error(self, tmp_path: Path) -> None:
        _parity_repo(tmp_path, self.FULL)
        (tmp_path / "templates" / "agent-denylists.yaml").write_text("a: [", encoding="utf-8")

        assert gate.main(["--repo-root", str(tmp_path)]) == gate.EXIT_CONFIG


class TestLiveReadOnlyAgentsAreNotGrantedBash:
    """Owner of the 'no shell for the four read-only agents' rule on the template side."""

    AGENTS = ("analyst", "security", "code-reviewer", "comment-analyzer")

    @pytest.mark.parametrize("stem", AGENTS)
    def test_template_has_no_tools_key_and_denies_the_mutators(self, stem: str) -> None:
        path = _REPO_ROOT / "templates" / "agents" / f"{stem}.claude.md.tmpl"
        # The frontmatter closes inside a partial, so read the template as lines.
        lines = path.read_text(encoding="utf-8").splitlines()

        assert "tools:" not in lines
        assert "disallowedTools:" in lines
        assert "  - $deny:builtin-mutators" in lines

    @pytest.mark.parametrize("stem", AGENTS)
    def test_granting_bash_in_the_live_template_fails_the_gate(
        self, stem: str, tmp_path: Path
    ) -> None:
        shutil.copytree(_REPO_ROOT / "templates" / "agents", tmp_path / "templates" / "agents")
        for name in ("toolsets.yaml", "agent-denylists.yaml"):
            shutil.copy(_REPO_ROOT / "templates" / name, tmp_path / "templates")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        baseline = tmp_path / gate.BASELINE_RELATIVE_PATH
        baseline.parent.mkdir(parents=True)
        shutil.copy(_REPO_ROOT / gate.BASELINE_RELATIVE_PATH, baseline)
        assert gate.main(["--repo-root", str(tmp_path)]) == gate.EXIT_OK

        path = tmp_path / "templates" / "agents" / f"{stem}.claude.md.tmpl"
        text = path.read_text(encoding="utf-8")
        assert "disallowedTools:\n  - Agent\n  - $deny:builtin-mutators\n" in text
        path.write_text(
            text.replace(
                "disallowedTools:\n  - Agent\n  - $deny:builtin-mutators\n",
                "tools:\n  - Read\n  - Bash\n",
            ),
            encoding="utf-8",
        )

        assert gate.main(["--repo-root", str(tmp_path)]) == gate.EXIT_DIVERGED


class TestCursorReadonlyDerivation:
    def test_full_deny_list_earns_readonly(self) -> None:
        fm = {"disallowedTools": ["Agent", "Bash", "Edit", "Write", "MultiEdit", "NotebookEdit"]}
        assert agent_tree_copy.derive_readonly(fm)
        assert not agent_tree_copy.has_inexpressible_restriction(fm)

    def test_partial_deny_list_does_not_earn_readonly(self) -> None:
        assert not agent_tree_copy.derive_readonly({"disallowedTools": ["Bash"]})

    def test_agent_only_deny_does_not_earn_readonly(self) -> None:
        assert not agent_tree_copy.derive_readonly({"disallowedTools": "Agent"})

    def test_allowlist_path_is_unchanged(self) -> None:
        assert agent_tree_copy.derive_readonly({"tools": ["Read", "Grep"]})
        assert not agent_tree_copy.derive_readonly({"tools": ["Read", "Bash"]})
