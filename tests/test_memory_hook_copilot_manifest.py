"""`.github/hooks/memory-recall.json` registers Copilot recall correctly.

Issue #4727: Copilot CLI drops output from config-file userPromptSubmitted
hooks. The registration must use Copilot's native schema, the documented
userPromptTransformed event, and run the recall invoker from the repo root.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads(
    (REPO_ROOT / ".github" / "hooks" / "memory-recall.json").read_text(encoding="utf-8")
)
INVOKER = ".claude/hooks/UserPromptSubmit/invoke_memory_recall.py"


def _entries(event: str) -> list[dict]:
    return MANIFEST["hooks"].get(event, [])


@pytest.mark.unit
def test_registers_one_user_prompt_transformed_entry():
    assert MANIFEST["version"] == 1
    assert list(MANIFEST["hooks"]) == ["userPromptTransformed"]
    assert len(_entries("userPromptTransformed")) == 1


@pytest.mark.unit
@pytest.mark.parametrize("shell", ["bash", "powershell"])
def test_entry_runs_the_recall_invoker_from_repo_root(shell):
    (entry,) = _entries("userPromptTransformed")

    assert entry["type"] == "command"
    assert entry["cwd"] == "."
    assert shlex.split(entry[shell])[-2:] == [INVOKER, "--copilot-transformed"]
    assert (REPO_ROOT / INVOKER).is_file()


@pytest.mark.unit
def test_timeout_matches_the_claude_registration():
    (entry,) = _entries("userPromptTransformed")

    assert entry["timeoutSec"] == 10


@pytest.mark.unit
@pytest.mark.parametrize("event", ["userPromptSubmitted", "UserPromptSubmit"])
def test_no_registration_on_the_dropped_output_event(event):
    assert _entries(event) == []
