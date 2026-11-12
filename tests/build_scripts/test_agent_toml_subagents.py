"""``agent_toml.forbids_subagents``: which sources get the ``Subagents`` section."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import agent_toml  # noqa: E402


@pytest.mark.parametrize(
    "loaded",
    [
        {"disallowedTools": "Agent"},
        {"disallowedTools": "Agent, Bash"},
        {"disallowedTools": "Bash,Agent"},
        {"disallowedTools": " Agent "},
        {"disallowedTools": ["Agent"]},
        {"disallowedTools": ["Bash", "Agent"]},
    ],
    ids=["string", "string-with-space", "string-no-space", "padded", "list", "list-with-other"],
)
def test_agent_among_the_disallowed_tools_forbids_subagents(loaded) -> None:
    assert agent_toml.forbids_subagents(loaded) is True


@pytest.mark.parametrize(
    "loaded",
    [
        {},
        {"disallowedTools": None},
        {"disallowedTools": ""},
        {"disallowedTools": "Bash"},
        {"disallowedTools": ["Bash", "Write"]},
        {"disallowedTools": "Agents"},
    ],
    ids=["absent", "none", "empty", "other-tool", "other-list", "near-miss"],
)
def test_other_values_do_not_forbid_subagents(loaded) -> None:
    """Negative control: only the exact name ``Agent`` triggers the section."""
    assert agent_toml.forbids_subagents(loaded) is False


def test_the_section_text_is_a_plain_instruction() -> None:
    assert agent_toml.NO_SUBAGENTS.startswith("\n\n## Subagents\n\n")
    assert "Do not start subagents" in agent_toml.NO_SUBAGENTS
