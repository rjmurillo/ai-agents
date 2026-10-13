"""Tests for build/scripts/agent_capabilities.py (issue #5688, ADR-107 invariant 6)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "build" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import agent_capabilities as caps  # noqa: E402

TOOLSETS = {
    "editor": {"tools_vscode": ["vscode", "read", "edit"], "tools_copilot": ["read", "edit"]},
    "research": {"tools": ["web", "context7/*"]},
}


class TestClassify:
    @pytest.mark.parametrize(
        "claude,other,family,item",
        [
            ("Read", "read", "builtin", "read"),
            ("Glob", "search", "builtin", "search"),
            ("Grep", "search", "builtin", "search"),
            ("Write", "edit", "builtin", "write"),
            ("Edit", "edit", "builtin", "write"),
            ("Bash", "shell", "builtin", "execute"),
            ("Bash", "execute", "builtin", "execute"),
            ("WebFetch", "web", "builtin", "network"),
            ("WebSearch", "web", "builtin", "network"),
            ("Task", "agent", "builtin", "delegate"),
            ("TodoWrite", "todo", "builtin", "track"),
        ],
    )
    def test_harness_spellings_share_one_capability(
        self, claude: str, other: str, family: str, item: str
    ) -> None:
        assert caps.classify(claude) == (family, item)
        assert caps.classify(other) == (family, item)

    def test_mcp_spellings_match(self) -> None:
        assert caps.classify("mcp__github__issue_read") == caps.classify("github/issue_read")

    def test_server_alias_and_tool_separator(self) -> None:
        assert caps.classify("cognitionai/deepwiki/*") == ("mcp:deepwiki", "*")
        assert caps.classify("mcp__context7__resolve_library_id") == caps.classify(
            "context7/resolve-library-id"
        )

    def test_wildcard_is_not_an_explicit_tool(self) -> None:
        assert caps.classify("serena/*") != caps.classify("serena/find_symbol")

    def test_unknown_name_stays_literal(self) -> None:
        assert caps.classify("Teleport") == ("unmapped", "Teleport")

    def test_vscode_host_tool_is_its_own_capability(self) -> None:
        assert caps.classify("vscode") == ("builtin", "host:vscode")


class TestExpand:
    def test_platform_variant_wins(self) -> None:
        names = caps.expand_names(["$toolset:editor"], "tools_vscode", TOOLSETS)
        assert names == ["vscode", "read", "edit"]

    def test_copilot_variant(self) -> None:
        names = caps.expand_names(["$toolset:editor"], "tools_copilot", TOOLSETS)
        assert names == ["read", "edit"]

    def test_shared_tools_fallback(self) -> None:
        names = caps.expand_names(["read", "$toolset:research"], "tools_copilot", TOOLSETS)
        assert names == ["read", "web", "context7/*"]

    def test_unknown_toolset_is_an_error(self) -> None:
        with pytest.raises(caps.CapabilityError, match="unknown toolset 'nope'"):
            caps.expand_names(["$toolset:nope"], "tools_vscode", TOOLSETS)

    def test_toolset_without_tools_for_platform_is_an_error(self) -> None:
        toolsets = {"empty": {"description": "x"}}
        with pytest.raises(caps.CapabilityError, match="no tools for 'tools_copilot'"):
            caps.expand_names(["$toolset:empty"], "tools_copilot", toolsets)


class TestCapabilityUnits:
    def test_absent_key_declares_unrestricted(self) -> None:
        units = caps.capability_units({}, "tools", "capability", {})
        assert units == {"capability:declaration": "unrestricted"}

    def test_comma_string_and_list_agree(self) -> None:
        as_text = caps.capability_units({"tools": "Read, Grep"}, "tools", "capability", {})
        as_list = caps.capability_units({"tools": ["read", "search"]}, "tools", "capability", {})
        assert as_text == as_list
        assert as_text["capability:declaration"] == "restricted"
        assert as_text["capability:builtin"] == "read\nsearch"

    def test_duplicates_and_order_do_not_matter(self) -> None:
        one = caps.capability_units({"tools": ["Grep", "Read", "Glob"]}, "tools", "c", {})
        two = caps.capability_units({"tools": ["Read", "Grep"]}, "tools", "c", {})
        assert one == two

    def test_each_server_gets_its_own_unit(self) -> None:
        units = caps.capability_units(
            {"tools": ["mcp__github__issue_read", "serena/find_symbol", "Teleport"]},
            "tools",
            "c",
            {},
        )
        assert units["c:mcp:github"] == "issue_read"
        assert units["c:mcp:serena"] == "find_symbol"
        assert units["c:unmapped"] == "Teleport"

    def test_empty_list_is_restricted_to_nothing(self) -> None:
        units = caps.capability_units({"tools": []}, "tools", "c", {})
        assert units == {"c:declaration": "restricted"}

    def test_non_list_value_is_an_error(self) -> None:
        with pytest.raises(caps.CapabilityError, match="tools_vscode must be a list"):
            caps.capability_units({"tools_vscode": {"a": 1}}, "tools_vscode", "c", {})

    def test_non_string_item_is_an_error(self) -> None:
        with pytest.raises(caps.CapabilityError, match="non-string tool"):
            caps.capability_units({"tools": ["read", 3]}, "tools", "c", {})


class TestDropFamiliesOnMismatch:
    def test_mismatched_declaration_drops_families(self) -> None:
        left = {"c:declaration": "unrestricted"}
        right = {"c:declaration": "restricted", "c:builtin": "read"}
        caps.drop_families_on_declaration_mismatch(left, right)
        assert right == {"c:declaration": "restricted"}

    def test_matching_declaration_keeps_families(self) -> None:
        left = {"c:declaration": "restricted", "c:builtin": "read"}
        right = {"c:declaration": "restricted", "c:builtin": "write"}
        caps.drop_families_on_declaration_mismatch(left, right)
        assert left["c:builtin"] == "read"
        assert right["c:builtin"] == "write"

    def test_other_units_are_untouched(self) -> None:
        left = {"c:declaration": "unrestricted", "preamble": "x"}
        right = {"c:declaration": "restricted", "c:builtin": "read", "preamble": "y"}
        caps.drop_families_on_declaration_mismatch(left, right)
        assert right == {"c:declaration": "restricted", "preamble": "y"}


class TestLoadToolsets:
    def test_missing_file_is_empty(self, tmp_path: Path) -> None:
        assert caps.load_toolsets(tmp_path) == {}

    def test_reads_the_repo_file(self, tmp_path: Path) -> None:
        (tmp_path / "templates").mkdir()
        (tmp_path / "templates" / "toolsets.yaml").write_text(
            "editor:\n  tools:\n    - read\n", encoding="utf-8"
        )
        assert caps.load_toolsets(tmp_path) == {"editor": {"tools": ["read"]}}

    def test_invalid_yaml_is_an_error(self, tmp_path: Path) -> None:
        (tmp_path / "templates").mkdir()
        (tmp_path / "templates" / "toolsets.yaml").write_text("a: [", encoding="utf-8")
        with pytest.raises(caps.CapabilityError, match="not valid YAML"):
            caps.load_toolsets(tmp_path)

    def test_non_mapping_is_an_error(self, tmp_path: Path) -> None:
        (tmp_path / "templates").mkdir()
        (tmp_path / "templates" / "toolsets.yaml").write_text("- a\n", encoding="utf-8")
        with pytest.raises(caps.CapabilityError, match="must be a mapping"):
            caps.load_toolsets(tmp_path)

    def test_unreadable_file_is_an_error(self, tmp_path: Path) -> None:
        (tmp_path / "templates").mkdir()
        (tmp_path / "templates" / "toolsets.yaml").write_bytes(b"\xff\xfe\x00bad")
        with pytest.raises(caps.CapabilityError, match="cannot read"):
            caps.load_toolsets(tmp_path)
