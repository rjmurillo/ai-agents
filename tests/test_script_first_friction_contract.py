"""Check that the shipped prompts carry the script and workaround guidance."""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (_ROOT / relative).read_text(encoding="utf-8")


def _line_starting(text: str, prefix: str) -> str:
    lines = [line for line in text.splitlines() if line.startswith(prefix)]
    assert len(lines) == 1, f"expected one line starting {prefix!r}, found {len(lines)}"
    return lines[0]


@pytest.mark.parametrize("root", ["src/claude/rules", "src/copilot-cli/instructions"])
def test_shipped_rules_keep_the_three_parts(root: str) -> None:
    suffix = ".instructions.md" if root.endswith("instructions") else ".md"
    scripts = _line_starting(_read(f"{root}/universal{suffix}"), "3. **Script before model**.")
    assert "deterministic work and reserve model calls for judgment" in scripts
    assert "recurring scripts in the host's script location, not scratch" in scripts
    report = _line_starting(_read(f"{root}/voice{suffix}"), "- **Report every workaround.**")
    for part in (
        "what you hit",
        "what you did instead",
        "the permanent fix",
        "no fix outside the task",
    ):
        assert part in report


@pytest.mark.parametrize(
    "relative",
    [
        "src/claude/agents/orchestrator.md",
        "src/copilot-cli/agents/orchestrator.agent.md",
    ],
)
def test_shipped_orchestrator_uses_existing_return_field(relative: str) -> None:
    line = _line_starting(_read(relative), "Agents return a completion record")
    assert "Include actual workarounds under residual risks." in line
    assert "Leave out sensitive details." in line
