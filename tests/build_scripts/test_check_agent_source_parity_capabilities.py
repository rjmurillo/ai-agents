"""Invariant 6 tests for build/scripts/check_agent_source_parity.py (issue #5688).

ADR-107 section 5 lets a normalized predicate drop platform tool spellings but
not the abstract capability set. These tests widen, narrow, and respell tool
lists in each member and expect the gate to tell those cases apart.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.build_scripts.test_check_agent_source_parity import (
    CLAUDE,
    COPILOT,
    SHARED,
    build_repo,
    gate,
    mutate,
    run_gate,
)


def divergence_units(root: Path) -> list[tuple[str, str]]:
    found, _ = gate.collect_divergence(root)
    return sorted((pair, unit) for _, pair, unit in found)


class TestClaudeToolList:
    def test_added_write_edit_bash_fails(self, tmp_path: Path) -> None:
        """The repro from the review: widen a Claude agent with write and shell tools."""
        claude = mutate(CLAUDE, "tools: Read, Grep", "tools: Read, Grep, Write, Edit, Bash")
        build_repo(tmp_path, claude=claude)
        assert run_gate(tmp_path) == gate.EXIT_DIVERGED
        assert divergence_units(tmp_path) == [(gate.PAIR_CLAUDE, "capability:builtin")]

    def test_removed_tool_fails(self, tmp_path: Path) -> None:
        build_repo(tmp_path, claude=mutate(CLAUDE, "tools: Read, Grep", "tools: Read"))
        assert divergence_units(tmp_path) == [(gate.PAIR_CLAUDE, "capability:builtin")]

    def test_respelled_tools_pass(self, tmp_path: Path) -> None:
        shared = SHARED.replace("[read, search]", "[read, search, github/issue_read]")
        claude = mutate(
            CLAUDE, "tools: Read, Grep", "tools: [Grep, Glob, Read, mcp__github__issue_read]"
        )
        build_repo(tmp_path, shared=shared, claude=claude, copilot=shared)
        assert run_gate(tmp_path) == gate.EXIT_OK

    def test_added_mcp_tool_names_its_server(self, tmp_path: Path) -> None:
        claude = mutate(CLAUDE, "tools: Read, Grep", "tools: Read, Grep, mcp__serena__write_memory")
        build_repo(tmp_path, claude=claude)
        assert divergence_units(tmp_path) == [(gate.PAIR_CLAUDE, "capability:mcp:serena")]

    def test_wildcard_is_not_an_explicit_list(self, tmp_path: Path) -> None:
        shared = mutate(
            SHARED, "tools_copilot: [read, search]", "tools_copilot: [read, search, serena/*]"
        )
        claude = mutate(CLAUDE, "tools: Read, Grep", "tools: Read, Grep, mcp__serena__find_symbol")
        build_repo(tmp_path, shared=shared, claude=claude, copilot=shared)
        assert divergence_units(tmp_path) == [(gate.PAIR_CLAUDE, "capability:mcp:serena")]

    def test_unknown_tool_name_cannot_hide(self, tmp_path: Path) -> None:
        claude = mutate(CLAUDE, "tools: Read, Grep", "tools: Read, Grep, Teleport")
        build_repo(tmp_path, claude=claude)
        assert divergence_units(tmp_path) == [(gate.PAIR_CLAUDE, "capability:unmapped")]

    def test_dropping_the_list_widens_to_unrestricted(self, tmp_path: Path) -> None:
        claude = mutate(CLAUDE, "tools: Read, Grep\n", "")
        build_repo(tmp_path, claude=claude)
        assert divergence_units(tmp_path) == [(gate.PAIR_CLAUDE, "capability:declaration")]

    def test_unrestricted_claude_pin_is_one_entry_per_agent(self, tmp_path: Path) -> None:
        build_repo(tmp_path, claude=mutate(CLAUDE, "tools: Read, Grep\n", ""))
        assert run_gate(tmp_path, "--write-baseline") == gate.EXIT_OK
        assert run_gate(tmp_path) == gate.EXIT_OK
        assert len(gate.load_baseline(tmp_path)) == 1

    def test_declaring_a_list_retires_the_declaration_pin(self, tmp_path: Path) -> None:
        build_repo(tmp_path, claude=mutate(CLAUDE, "tools: Read, Grep\n", ""))
        run_gate(tmp_path, "--write-baseline")
        claude_path = tmp_path / "templates" / "agents" / "widget.claude.md.tmpl"
        claude_path.write_text(CLAUDE, encoding="utf-8")
        found, _ = gate.collect_divergence(tmp_path)
        assert found == {}
        assert run_gate(tmp_path) == gate.EXIT_DIVERGED


class TestCopilotToolLists:
    @pytest.mark.parametrize("key", ["tools_copilot", "tools_vscode"])
    def test_widened_list_fails(self, tmp_path: Path, key: str) -> None:
        old = f"{key}: [read, search]"
        copilot = mutate(COPILOT, old, f"{key}: [read, search, shell, edit]")
        build_repo(tmp_path, copilot=copilot)
        found = divergence_units(tmp_path)
        assert found
        assert {pair for pair, _ in found} == {gate.PAIR_COPILOT}

    def test_vscode_list_has_its_own_unit(self, tmp_path: Path) -> None:
        copilot = mutate(COPILOT, "tools_vscode: [read, search]", "tools_vscode: [read]")
        build_repo(tmp_path, copilot=copilot)
        assert divergence_units(tmp_path) == [(gate.PAIR_COPILOT, "capability-vscode:builtin")]

    def test_shared_source_widened_fails_both_pairs_it_feeds(self, tmp_path: Path) -> None:
        shared = mutate(
            SHARED, "tools_copilot: [read, search]", "tools_copilot: [read, search, shell]"
        )
        build_repo(tmp_path, shared=shared)
        assert {pair for pair, _ in divergence_units(tmp_path)} == {
            gate.PAIR_CLAUDE,
            gate.PAIR_COPILOT,
        }

    def test_shared_source_without_a_copilot_list_fails(self, tmp_path: Path) -> None:
        shared = mutate(SHARED, "tools_copilot: [read, search]\n", "")
        build_repo(tmp_path, shared=shared)
        assert (gate.PAIR_CLAUDE, "capability:declaration") in divergence_units(tmp_path)

    def test_toolset_reference_expands_before_comparison(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        (tmp_path / "templates" / "toolsets.yaml").write_text(
            "reading:\n  tools_copilot:\n    - read\n    - search\n", encoding="utf-8"
        )
        shared = mutate(
            SHARED, "tools_copilot: [read, search]", "tools_copilot: ['$toolset:reading']"
        )
        agents = tmp_path / "templates" / "agents"
        (agents / "widget.shared.md").write_text(shared, encoding="utf-8")
        (agents / "widget.copilot.md.tmpl").write_text(shared, encoding="utf-8")
        assert run_gate(tmp_path) == gate.EXIT_OK

    def test_unknown_toolset_is_a_config_error(self, tmp_path: Path) -> None:
        shared = mutate(SHARED, "tools_copilot: [read, search]", "tools_copilot: ['$toolset:nope']")
        build_repo(tmp_path, shared=shared, copilot=shared)
        assert run_gate(tmp_path) == gate.EXIT_CONFIG

    def test_invalid_toolsets_file_is_a_config_error(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        (tmp_path / "templates" / "toolsets.yaml").write_text("a: [", encoding="utf-8")
        assert run_gate(tmp_path) == gate.EXIT_CONFIG

    def test_malformed_tool_list_is_a_config_error(self, tmp_path: Path) -> None:
        claude = mutate(CLAUDE, "tools: Read, Grep", "tools:\n  nested: map")
        build_repo(tmp_path, claude=claude)
        assert run_gate(tmp_path) == gate.EXIT_CONFIG


class TestBaselineFormat:
    def test_one_entry_per_line_round_trips(self, tmp_path: Path) -> None:
        found = {("a", gate.PAIR_CLAUDE, "u1"): "d1", ("b", gate.PAIR_COPILOT, "u2"): "d2"}
        text = gate.render_baseline(found)
        assert sum(1 for line in text.splitlines() if '"digest"' in line) == 2
        path = tmp_path / gate.BASELINE_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        assert gate.load_baseline(tmp_path) == found

    def test_empty_baseline_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / gate.BASELINE_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        path.write_text(gate.render_baseline({}), encoding="utf-8")
        assert gate.load_baseline(tmp_path) == {}
