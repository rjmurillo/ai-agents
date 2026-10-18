"""Tests for the Claude MCP server grants (ADR-107).

Covers `agent_capabilities` (load, expand grants and denies, frontmatter substitution,
bare-wildcard rejection, prefix normalization), the `agent_templates` compile path,
and the parity gate on the live templates.
"""

from __future__ import annotations

import json
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
import check_agent_source_parity as gate  # noqa: E402

LIVE = caps.load_mcp_table(_REPO_ROOT)

CONFIG = {
    "prefix_variants": [
        "mcp__{server}",
        "mcp__plugin_{server}_{server}",
        "mcp__claude_ai_{claude_ai}",
    ],
    "servers": {
        "demo": {"claude_ai": ["Demo", "demo"]},
        "solo": {"variants": ["mcp__{server}"]},
        "hosted": {"remote_only": "hosted service, nothing local"},
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


class TestConfigValidation:
    def test_duplicate_variants_collapse(self) -> None:
        config = {**CONFIG, "prefix_variants": ["mcp__{server}", "mcp__{server}"]}
        assert caps.expand_server_grant("solo", config) == ["mcp__solo__*"]
        assert caps.expand_server_grant("demo", config) == ["mcp__demo__*"]

    @pytest.mark.parametrize(
        "patch,message",
        [
            ({"prefix_variants": []}, "prefix_variants must be a non-empty list"),
            ({"prefix_variants": ["bad_{server}"]}, "starting with 'mcp__'"),
            ({"prefix_variants": ["mcp__{nope}"]}, "unknown placeholder"),
            ({"servers": {}}, "unknown MCP server"),
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
            caps.expand_server_grant("demo", {**CONFIG, **patch})


class TestServerGrants:
    def test_wildcard_is_emitted_for_every_prefix_variant(self) -> None:
        assert caps.expand_server_grant("demo", CONFIG) == [
            "mcp__demo__*",
            "mcp__plugin_demo_demo__*",
            "mcp__claude_ai_Demo__*",
            "mcp__claude_ai_demo__*",
        ]

    def test_per_server_variants_override_the_table(self) -> None:
        assert caps.expand_server_grant("solo", CONFIG) == ["mcp__solo__*"]

    def test_unknown_logical_server_fails_closed(self) -> None:
        with pytest.raises(caps.CapabilityError, match="unknown MCP server 'nope'"):
            caps.expand_server_grant("nope", CONFIG)

    def test_empty_table_fails_closed(self) -> None:
        with pytest.raises(caps.CapabilityError, match="unknown MCP server"):
            caps.expand_server_grant("demo", {})

    def test_bad_per_server_variants_are_rejected(self) -> None:
        config = {**CONFIG, "servers": {"s": {"variants": ["bad"]}}}
        with pytest.raises(caps.CapabilityError, match="starting with 'mcp__'"):
            caps.expand_server_grant("s", config)

    @pytest.mark.parametrize(
        "name,family",
        [
            ("mcp__serena__*", "mcp:serena"),
            ("mcp__plugin_serena_serena__*", "mcp:serena"),
            ("mcp__claude_ai_Context7__*", "mcp:context7"),
            ("mcp__claude_ai_Claude_Docs__x", "mcp:claude-docs"),
            ("mcp__github__issue_read", "mcp:github"),
        ],
    )
    def test_prefix_variants_classify_as_one_server(self, name: str, family: str) -> None:
        assert caps.classify(name)[0] == family

    def test_wildcard_compares_equal_to_the_copilot_spelling(self) -> None:
        assert caps.classify("mcp__serena__*") == caps.classify("serena/*")
        assert caps.classify("mcp__plugin_serena_serena__*") == caps.classify("serena/*")

    def test_a_plugin_name_that_is_not_doubled_is_left_alone(self) -> None:
        assert caps.classify("mcp__plugin_a_b__x")[0] == "mcp:plugin_a_b"


class TestWildcardRefusal:
    @pytest.mark.parametrize("key", ["explicit_only", "remote_only"])
    def test_server_marked_not_whole_cannot_be_granted_by_wildcard(self, key: str) -> None:
        config = {**CONFIG, "servers": {**CONFIG["servers"], "locked": {key: "reason"}}}
        with pytest.raises(caps.CapabilityError, match=key):
            caps.expand_server_grant("locked", config)
        assert "locked" not in caps.wildcard_servers(config)

    def test_live_serena_and_deepwiki_cannot_be_granted_by_wildcard(self) -> None:
        for server in ("serena", "deepwiki"):
            with pytest.raises(caps.CapabilityError):
                caps.expand_server_grant(server, LIVE)
        assert caps.wildcard_servers(LIVE) == ["context7"]

    def test_wildcard_grants_are_exactly_the_context7_expansions(self) -> None:
        assert caps.wildcard_grants(LIVE) == frozenset(caps.expand_server_grant("context7", LIVE))


class TestLiveTable:
    def test_only_the_read_only_docs_server_is_granted_by_wildcard(self) -> None:
        wildcard = {
            name
            for name, entry in LIVE["servers"].items()
            if not ({"remote_only", "explicit_only"} & set(entry))
        }

        assert wildcard == {"context7"}

    def test_the_table_carries_no_deny_list(self) -> None:
        assert "denylists" not in LIVE

    def test_context7_grant_covers_every_known_variant(self) -> None:
        assert caps.expand_server_grant("context7", LIVE) == [
            "mcp__context7__*",
            "mcp__plugin_context7_context7__*",
            "mcp__claude_ai_Context7__*",
        ]

    def test_every_mcp_json_server_is_marked_not_wildcard(self) -> None:
        configured = json.loads((_REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
        servers = configured.get("mcpServers", configured)

        for name in servers:
            entry = LIVE["servers"].get(name)
            assert isinstance(entry, dict), f".mcp.json server {name!r} has no `servers` entry"
            reasons = [entry.get(k) for k in ("remote_only", "explicit_only")]
            assert any(isinstance(r, str) and r.strip() for r in reasons), (
                f".mcp.json server {name!r} needs remote_only or explicit_only"
            )

    def test_serena_is_explicit_only(self) -> None:
        assert LIVE["servers"]["serena"].get("explicit_only")


class TestExpandFrontmatter:
    TEXT = "---\nname: x\ntools:\n  - Read\n  - $mcp:demo\n---\nBody $mcp:demo\n"

    def test_body_mentions_are_untouched(self) -> None:
        assert caps.expand_frontmatter(self.TEXT, CONFIG).endswith("Body $mcp:demo\n")

    def test_indent_is_kept(self) -> None:
        text = "---\nname: x\nmetadata:\n  list:\n    - $mcp:solo\n---\nb\n"
        assert "    - mcp__solo__*\n" in caps.expand_frontmatter(text, CONFIG)

    def test_server_reference_expands_to_wildcards(self) -> None:
        text = "---\nname: x\ntools:\n  - Read\n  - $mcp:demo\n---\nbody\n"

        front = yaml.safe_load(caps.expand_frontmatter(text, CONFIG).split("---\n")[1])

        assert front["tools"][0] == "Read"
        assert front["tools"][1:] == caps.expand_server_grant("demo", CONFIG)

    def test_unknown_server_reference_raises(self) -> None:
        text = "---\nname: x\ntools:\n  - $mcp:typo\n---\nbody\n"
        with pytest.raises(caps.CapabilityError, match="unknown MCP server 'typo'"):
            caps.expand_frontmatter(text, CONFIG)

    @pytest.mark.parametrize("entry", ["mcp__*", "mcp__", "'mcp__*'"])
    def test_global_mcp_wildcard_is_rejected(self, entry: str) -> None:
        text = f"---\nname: x\ntools:\n  - Read\n  - {entry}\n---\nbody\n"
        with pytest.raises(caps.CapabilityError, match="grants no tool"):
            caps.expand_frontmatter(text, CONFIG)

    def test_global_wildcard_in_a_flow_list_is_rejected(self) -> None:
        text = "---\nname: x\ntools: [Read, mcp__*]\n---\nbody\n"
        with pytest.raises(caps.CapabilityError, match="grants no tool"):
            caps.expand_frontmatter(text, CONFIG)

    def test_a_server_wildcard_is_not_mistaken_for_the_global_one(self) -> None:
        text = "---\nname: x\ntools:\n  - mcp__serena__*\n---\nbody\n"
        assert caps.expand_frontmatter(text, CONFIG) == text

    def test_global_wildcard_in_the_body_is_ignored(self) -> None:
        text = "---\nname: x\n---\nUse mcp__* here.\n"
        assert caps.expand_frontmatter(text, CONFIG) == text

    def test_inline_reference_raises(self) -> None:
        text = "---\nname: x\ntools: [$mcp:demo]\n---\nbody\n"
        with pytest.raises(caps.CapabilityError, match="whole list item"):
            caps.expand_frontmatter(text, CONFIG)

    def test_text_without_frontmatter_is_returned_unchanged(self) -> None:
        assert caps.expand_frontmatter("- $mcp:x\n", CONFIG) == "- $mcp:x\n"

    def test_frontmatter_without_references_is_unchanged(self) -> None:
        text = "---\nname: x\n---\nbody\n"
        assert caps.expand_frontmatter(text, CONFIG) == text


class TestLoadMcpTable:
    def test_missing_file_is_empty(self, tmp_path: Path) -> None:
        assert caps.load_mcp_table(tmp_path) == {}

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        (tmp_path / "templates").mkdir()
        (tmp_path / caps.MCP_TABLE_RELATIVE_PATH).write_text("a: [", encoding="utf-8")
        with pytest.raises(caps.CapabilityError, match="not valid YAML"):
            caps.load_mcp_table(tmp_path)

    def test_non_mapping_raises(self, tmp_path: Path) -> None:
        (tmp_path / "templates").mkdir()
        (tmp_path / caps.MCP_TABLE_RELATIVE_PATH).write_text("- a\n", encoding="utf-8")
        with pytest.raises(caps.CapabilityError, match="must be a mapping"):
            caps.load_mcp_table(tmp_path)

    def test_undecodable_file_raises(self, tmp_path: Path) -> None:
        (tmp_path / "templates").mkdir()
        (tmp_path / caps.MCP_TABLE_RELATIVE_PATH).write_bytes(b"\xff\xfe\x00bad")
        with pytest.raises(caps.CapabilityError, match="cannot read"):
            caps.load_mcp_table(tmp_path)


def _write_pair(root: Path, claude: str, copilot: str = "---\nname: w\n---\nbody\n") -> None:
    agents = root / "templates" / "agents"
    (agents / "partials").mkdir(parents=True, exist_ok=True)
    (agents / "w.claude.md.tmpl").write_text(claude, encoding="utf-8")
    (agents / "w.copilot.md.tmpl").write_text(copilot, encoding="utf-8")
    (root / "templates" / "agent-mcp-servers.yaml").write_text(
        yaml.safe_dump(CONFIG), encoding="utf-8"
    )


class TestCompile:
    CLAUDE = "---\nname: w\ntools:\n  - Read\n  - $mcp:demo\n---\nbody\n"

    def test_render_writes_expanded_entries(self, tmp_path: Path) -> None:
        _write_pair(tmp_path, self.CLAUDE)

        result = agent_templates.compile_all(tmp_path, validate=False)

        assert result.exit_code == 0
        out = (tmp_path / "src" / "claude" / "agents" / "w.md").read_text(encoding="utf-8")
        assert "$mcp" not in out
        assert "  - Read\n  - mcp__demo__*\n" in out
        assert "  - mcp__claude_ai_demo__*\n" in out
        assert "  - mcp__plugin_demo_demo__*\n" in out

    def test_unknown_logical_server_fails_the_build(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_pair(tmp_path, self.CLAUDE.replace("$mcp:demo", "$mcp:typo"))

        assert agent_templates.compile_all(tmp_path, validate=False).exit_code == 2
        assert "unknown MCP server 'typo'" in capsys.readouterr().err

    def test_global_mcp_wildcard_fails_the_build(self, tmp_path: Path) -> None:
        _write_pair(tmp_path, self.CLAUDE.replace("$mcp:demo", "mcp__*"))

        assert agent_templates.compile_all(tmp_path, validate=False).exit_code == 2

    def test_missing_table_file_fails_the_build(self, tmp_path: Path) -> None:
        _write_pair(tmp_path, self.CLAUDE)
        (tmp_path / "templates" / "agent-mcp-servers.yaml").unlink()

        assert agent_templates.compile_all(tmp_path, validate=False).exit_code == 2

    def test_invalid_table_file_fails_the_build(self, tmp_path: Path) -> None:
        _write_pair(tmp_path, self.CLAUDE)
        (tmp_path / "templates" / "agent-mcp-servers.yaml").write_text("a: [", encoding="utf-8")

        assert agent_templates.compile_all(tmp_path, validate=False).exit_code == 2

    def test_validate_mode_reports_stale_expansion(self, tmp_path: Path) -> None:
        _write_pair(tmp_path, self.CLAUDE)
        agent_templates.compile_all(tmp_path, validate=False)
        config = yaml.safe_load(yaml.safe_dump(CONFIG))
        config["servers"]["demo"]["claude_ai"] = ["Demo"]
        (tmp_path / "templates" / "agent-mcp-servers.yaml").write_text(
            yaml.safe_dump(config), encoding="utf-8"
        )

        result = agent_templates.compile_all(tmp_path, validate=True)

        assert result.exit_code == 1
        assert result.drifted

    def test_copilot_template_is_not_expanded(self, tmp_path: Path) -> None:
        copilot = "---\nname: w\ntools:\n  - $mcp:demo\n---\nbody\n"
        _write_pair(tmp_path, self.CLAUDE, copilot)

        result = agent_templates.compile_all(tmp_path, validate=False)

        assert result.exit_code == 0
        assert "$mcp:demo" in result.copilot_rendered["w"]


class TestLiveAgents:
    """The shipped templates and the parity gate agree with the grant design."""

    AGENTS = ("analyst", "security", "code-reviewer", "comment-analyzer")

    @pytest.mark.parametrize("stem", AGENTS)
    def test_template_declares_tools_and_explicit_serena_reads(self, stem: str) -> None:
        path = _REPO_ROOT / "templates" / "agents" / f"{stem}.claude.md.tmpl"
        # The frontmatter closes inside a partial, so read the template as lines.
        lines = path.read_text(encoding="utf-8").splitlines()

        assert "tools:" in lines
        assert "  - $mcp:serena" not in lines
        assert "disallowedTools:" not in lines
        assert "  - mcp__serena__read_memory" in lines or stem in {
            "code-reviewer",
            "comment-analyzer",
        }

    @pytest.mark.parametrize("stem", AGENTS)
    def test_granting_bash_in_the_live_template_fails_the_gate(
        self, stem: str, tmp_path: Path
    ) -> None:
        shutil.copytree(_REPO_ROOT / "templates" / "agents", tmp_path / "templates" / "agents")
        for name in ("toolsets.yaml", "agent-mcp-servers.yaml"):
            shutil.copy(_REPO_ROOT / "templates" / name, tmp_path / "templates")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        baseline = tmp_path / gate.BASELINE_RELATIVE_PATH
        baseline.parent.mkdir(parents=True)
        shutil.copy(_REPO_ROOT / gate.BASELINE_RELATIVE_PATH, baseline)
        assert gate.main(["--repo-root", str(tmp_path)]) == gate.EXIT_OK

        path = tmp_path / "templates" / "agents" / f"{stem}.claude.md.tmpl"
        text = path.read_text(encoding="utf-8")
        assert "tools:\n  - Read\n" in text
        path.write_text(
            text.replace("tools:\n  - Read\n", "tools:\n  - Read\n  - Bash\n", 1), encoding="utf-8"
        )

        assert gate.main(["--repo-root", str(tmp_path)]) == gate.EXIT_DIVERGED

    def test_unknown_server_in_a_live_template_is_a_config_error(self, tmp_path: Path) -> None:
        shutil.copytree(_REPO_ROOT / "templates" / "agents", tmp_path / "templates" / "agents")
        for name in ("toolsets.yaml", "agent-mcp-servers.yaml"):
            shutil.copy(_REPO_ROOT / "templates" / name, tmp_path / "templates")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        path = tmp_path / "templates" / "agents" / "analyst.claude.md.tmpl"
        path.write_text(
            path.read_text(encoding="utf-8").replace("$mcp:context7", "$mcp:typo"), encoding="utf-8"
        )

        assert gate.main(["--repo-root", str(tmp_path)]) == gate.EXIT_CONFIG
