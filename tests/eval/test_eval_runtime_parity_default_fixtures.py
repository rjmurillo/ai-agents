"""Pin the default runtime parity fixtures (issue #5973).

Claude's Edit tool refuses to change a file the session has not read. A
fixture that grants `write` for a pre-existing file without `read` cannot pass
on Claude, so its failure would measure the harness, not the agent.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.eval._runtime_parity_test_support import FIXTURES, parity, runtime_parity


def _default_fixtures() -> list[dict[str, Any]]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))["fixtures"]


def test_execute_reversible_tool_grants_read_and_write() -> None:
    fixture = next(f for f in _default_fixtures() if f["id"] == "execute-reversible-tool")
    assert set(fixture["tools"]) == {"read", "write"}


@pytest.mark.parametrize("fixture", _default_fixtures(), ids=lambda f: f["id"])
def test_write_fixture_with_existing_files_also_grants_read(fixture: dict[str, Any]) -> None:
    tools = fixture.get("tools", [])
    if "write" in tools and fixture.get("setup_files"):
        assert "read" in tools


def test_default_fixtures_still_load() -> None:
    assert runtime_parity.load_fixtures(FIXTURES)


def test_claude_command_carries_read_and_edit_for_the_reversible_fixture() -> None:
    fixtures = runtime_parity.load_fixtures(FIXTURES)
    fixture = next(f for f in fixtures if f.fixture_id == "execute-reversible-tool")
    argv = parity.build_argv("claude", "claude", parity.DEFAULT_MODEL, fixture)
    assert set(argv[argv.index("--tools") + 1].split(",")) == {"Read", "Edit"}
