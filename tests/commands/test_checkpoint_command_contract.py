"""Contract tests for the /checkpoint command.

The command is LLM-executed prose, so these tests pin the contract fragments
that protect issue #1907 AC-4: a checkpoint file must be linked from the active
JSON session log when such a log exists, and failures must be reported instead
of silently claimed as done.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_PATH = REPO_ROOT / ".claude" / "commands" / "checkpoint.md"
COPILOT_PATH = REPO_ROOT / "src" / "copilot-cli" / "skills" / "checkpoint" / "SKILL.md"


@pytest.fixture(params=[COMMAND_PATH, COPILOT_PATH], ids=["claude", "copilot"])
def checkpoint_text(request: pytest.FixtureRequest) -> str:
    return Path(request.param).read_text(encoding="utf-8")


def test_checkpoint_can_read_and_edit_session_log(checkpoint_text: str) -> None:
    assert "Glob" in checkpoint_text
    assert "Read" in checkpoint_text
    assert "Edit" in checkpoint_text
    assert "Write" in checkpoint_text
    assert "Bash(git branch:*)" in checkpoint_text
    assert "Bash(python3 -m json.tool:*)" in checkpoint_text
    assert "Bash(python3 scripts/redact_secrets.py:*)" in checkpoint_text
    assert "## Triggers" in checkpoint_text
    assert "## Process" in checkpoint_text
    assert "## Verification" in checkpoint_text


def test_checkpoint_links_created_file_from_active_session_log(checkpoint_text: str) -> None:
    assert "Link the checkpoint from the active session log" in checkpoint_text
    assert "session.branch" in checkpoint_text
    assert "equals the current branch" in checkpoint_text
    assert "sort by filename descending" in checkpoint_text
    assert "That file is the active session" in checkpoint_text
    assert "top-level `checkpoints` array" in checkpoint_text
    assert "Append an object with `path`, `created`, `label`," in checkpoint_text


def test_checkpoint_derives_default_slug_and_handles_collisions(checkpoint_text: str) -> None:
    assert "If `$ARGUMENTS` is empty after trimming" in checkpoint_text
    assert "derive the label from the active" in checkpoint_text
    assert "session.objective" in checkpoint_text
    assert "CHECKPOINT-YYYYMMDD-HHMMSS-<slug>.md" in checkpoint_text
    assert "Use this collision loop before writing" in checkpoint_text
    assert "then `-3`" in checkpoint_text


def test_checkpoint_redacts_before_writing_durable_text(checkpoint_text: str) -> None:
    assert "Redact secrets before writing" in checkpoint_text
    assert "python3 scripts/redact_secrets.py" in checkpoint_text
    assert "instead of writing unredacted durable text" in checkpoint_text


def test_checkpoint_fails_closed_when_session_log_update_is_unsafe(
    checkpoint_text: str,
) -> None:
    assert "If no active session log was found" in checkpoint_text
    assert "Do not invent or modify a log" in checkpoint_text
    assert re.search(r"If JSON\s+validation fails", checkpoint_text)
    assert re.search(r"do not claim the checkpoint was\s+linked", checkpoint_text)
