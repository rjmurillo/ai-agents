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
        "claude,other,items",
        [
            ("Read", "read", ("read",)),
            ("Bash", "shell", ("execute",)),
            ("Bash", "execute", ("execute",)),
            ("Task", "agent", ("delegate",)),
            ("TodoWrite", "todo", ("track",)),
        ],
    )
    def test_harness_spellings_share_one_capability(
        self, claude: str, other: str, items: tuple[str, ...]
    ) -> None:
        assert caps.classify(claude) == ("builtin", items)
        assert caps.classify(other) == ("builtin", items)

    @pytest.mark.parametrize(
        "claude_names,other",
        [
            (["Glob", "Grep"], "search"),
            (["Write", "Edit"], "edit"),
            (["WebFetch", "WebSearch"], "web"),
        ],
    )
    def test_grouped_vscode_name_equals_its_claude_tools(
        self, claude_names: list[str], other: str
    ) -> None:
        items = {i for n in claude_names for i in caps.classify(n)[1]}
        assert set(caps.classify(other)[1]) == items
        assert len(items) == len(claude_names)

    @pytest.mark.parametrize(
        "name",
        ["Glob", "Grep", "Write", "Edit", "MultiEdit", "NotebookEdit", "WebFetch", "WebSearch"],
    )
    def test_each_claude_grant_is_its_own_item(self, name: str) -> None:
        family, items = caps.classify(name)
        assert family == "builtin"
        assert len(items) == 1
        others = {n for n in ("Glob", "Grep", "Write", "Edit", "MultiEdit", "NotebookEdit")}
        assert all(caps.classify(n)[1] != items for n in others - {name} if n != name)

    def test_mcp_spellings_match(self) -> None:
        assert caps.classify("mcp__github__issue_read") == caps.classify("github/issue_read")

    def test_server_alias_and_tool_separator(self) -> None:
        assert caps.classify("cognitionai/deepwiki/*") == ("mcp:deepwiki", ("*",))
        assert caps.classify("mcp__context7__resolve_library_id") == caps.classify(
            "context7/resolve-library-id"
        )

    def test_wildcard_is_not_an_explicit_tool(self) -> None:
        assert caps.classify("serena/*") != caps.classify("serena/find_symbol")

    def test_unknown_name_stays_literal(self) -> None:
        assert caps.classify("Teleport") == ("unmapped", ("Teleport",))

    def test_vscode_host_tool_is_its_own_capability(self) -> None:
        assert caps.classify("vscode") == ("builtin", ("host:vscode",))


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
        as_text = caps.capability_units({"tools": "Read, Glob, Grep"}, "tools", "capability", {})
        as_list = caps.capability_units({"tools": ["read", "search"]}, "tools", "capability", {})
        assert as_text == as_list
        assert as_text["capability:declaration"] == "restricted"
        assert as_text["capability:builtin"] == "glob\ngrep\nread"

    def test_duplicates_and_order_do_not_matter(self) -> None:
        one = caps.capability_units({"tools": ["Grep", "Read", "Glob"]}, "tools", "c", {})
        two = caps.capability_units({"tools": ["Read", "Grep", "Glob", "Read"]}, "tools", "c", {})
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


class TestGrantsAreCompared:
    def test_dropping_one_grant_in_a_group_shows(self) -> None:
        both = caps.capability_units({"tools": ["Glob", "Grep"]}, "tools", "c", {})
        one = caps.capability_units({"tools": ["Glob"]}, "tools", "c", {})
        assert both != one

    def test_adding_multiedit_to_write_edit_shows(self) -> None:
        base = caps.capability_units({"tools": ["Write", "Edit"]}, "tools", "c", {})
        wider = caps.capability_units({"tools": ["Write", "Edit", "MultiEdit"]}, "tools", "c", {})
        assert base != wider

    def test_websearch_alone_differs_from_web(self) -> None:
        one = caps.capability_units({"tools": ["WebSearch"]}, "tools", "c", {})
        both = caps.capability_units({"tools": ["web"]}, "tools", "c", {})
        assert one != both

    def test_vscode_group_equals_claude_pair(self) -> None:
        claude = caps.capability_units(
            {"tools": ["Glob", "Grep", "Write", "Edit"]}, "tools", "c", {}
        )
        vscode = caps.capability_units({"tools": ["search", "edit"]}, "tools", "c", {})
        assert claude == vscode

    def test_drop_helper_is_gone(self) -> None:
        assert not hasattr(caps, "drop_families_on_declaration_mismatch")

    def test_restricted_list_keeps_its_family_units(self) -> None:
        units = caps.capability_units({"tools": ["Read", "Bash"]}, "tools", "c", {})
        assert units == {"c:declaration": "restricted", "c:builtin": "execute\nread"}


class TestFallbackKey:
    def test_absent_key_falls_back_to_bare_tools(self) -> None:
        fm = {"tools": ["read", "shell"]}
        units = caps.capability_units(fm, "tools_copilot", "c", {}, fallback_key="tools")
        assert units == {"c:declaration": "restricted", "c:builtin": "execute\nread"}

    def test_platform_key_wins_over_fallback(self) -> None:
        fm = {"tools_copilot": ["read"], "tools": ["read", "shell"]}
        units = caps.capability_units(fm, "tools_copilot", "c", {}, fallback_key="tools")
        assert units["c:builtin"] == "read"

    def test_no_fallback_key_keeps_unrestricted(self) -> None:
        fm = {"tools": ["read"]}
        units = caps.capability_units(fm, "tools_copilot", "c", {})
        assert units == {"c:declaration": "unrestricted"}

    def test_neither_key_is_unrestricted(self) -> None:
        units = caps.capability_units({}, "tools_copilot", "c", {}, fallback_key="tools")
        assert units == {"c:declaration": "unrestricted"}

    def test_list_fallback_ignored_when_other_platform_key_present(self) -> None:
        fm = {"tools_vscode": ["read"], "tools": ["read", "shell"]}
        units = caps.capability_units(fm, "tools_copilot", "c", {}, fallback_key="tools")
        assert units == {"c:declaration": "unrestricted"}

    def test_string_fallback_kept_when_other_platform_key_present(self) -> None:
        fm = {"tools_vscode": ["read"], "tools": "read, shell"}
        units = caps.capability_units(fm, "tools_copilot", "c", {}, fallback_key="tools")
        assert units == {"c:declaration": "restricted", "c:builtin": "execute\nread"}

    def test_platform_placeholder_is_ignored_like_the_generator(self) -> None:
        fm = {"tools": "{{PLATFORM_TOOLS}}"}
        units = caps.capability_units(fm, "tools_copilot", "c", {}, fallback_key="tools")
        assert units == {"c:declaration": "unrestricted"}


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
