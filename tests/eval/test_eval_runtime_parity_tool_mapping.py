"""Pin the fixture-tool to CLI-tool mapping of the runtime parity evaluator (issue #6710).

Claude Edit and Copilot edit replace text in an existing file. A fixture whose
pass condition is a new file needs Write (Claude) or create (Copilot) as well.
"""

from __future__ import annotations

import dataclasses

import pytest

from tests.eval._runtime_parity_test_support import FIXTURES, parity


def _tools_of(argv: list[str], harness: str) -> list[str]:
    if harness == "claude":
        return argv[argv.index("--tools") + 1].split(",")
    available = next(a for a in argv if a.startswith("--available-tools="))
    return available.split("=", 1)[1].split(",")


def test_write_fixture_gets_a_file_creating_tool_on_both_harnesses() -> None:
    """Issue #6710: Claude Edit and Copilot edit replace text, they cannot create a file."""
    fixture = dataclasses.replace(parity.load_fixtures(FIXTURES)[1], tools=("write",))

    claude = parity.build_argv("claude", "claude", parity.DEFAULT_MODEL, fixture)
    copilot = parity.build_argv("copilot", "copilot", parity.DEFAULT_MODEL, fixture)

    assert _tools_of(claude, "claude") == ["Write", "Edit"]
    assert _tools_of(copilot, "copilot") == ["edit", "create"]
    assert "--allow-tool=create" in copilot
    assert "--allow-tool=edit" in copilot


def test_tool_expansion_keeps_order_and_drops_duplicates() -> None:
    claude = parity._tool_args(("read", "write", "write"), "claude")
    copilot = parity._tool_args(("question", "write", "read"), "copilot")

    assert claude == ["--tools", "Read,Write,Edit"]
    assert copilot == [
        "--available-tools=ask_user,edit,create,view",
        "--allow-tool=ask_user",
        "--allow-tool=edit",
        "--allow-tool=create",
        "--allow-tool=view",
    ]


def test_read_only_fixture_gets_no_file_writing_tool() -> None:
    claude = parity._tool_args(("read",), "claude")
    copilot = parity._tool_args(("read",), "copilot")

    assert claude == ["--tools", "Read"]
    assert copilot == ["--available-tools=view", "--allow-tool=view"]


def test_fixture_without_tools_keeps_the_empty_claude_tool_list() -> None:
    assert parity._tool_args((), "claude") == ["--tools", ""]


def test_unknown_fixture_tool_name_fails_loud() -> None:
    with pytest.raises(KeyError):
        parity._tool_args(("create",), "claude")
