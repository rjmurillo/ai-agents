"""Pin the read-batching sentence in the universal rules (issue #5969).

The sentence must appear once in the source template, and every generated
copy that Claude Code or Copilot CLI loads must carry it too.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

SENTENCE = (
    "Batch independent reads into one turn, and stop exploring once the "
    "answer is grounded in evidence."
)

SOURCE = "templates/rules/universal.md"

GENERATED_COPIES = (
    ".claude/rules/universal.md",
    "src/claude/rules/universal.md",
    ".github/instructions/universal.instructions.md",
    "src/copilot-cli/instructions/universal.instructions.md",
)


def _read(relative: str) -> str:
    return (_REPO_ROOT / relative).read_text(encoding="utf-8")


def test_source_carries_sentence_once() -> None:
    assert _read(SOURCE).count(SENTENCE) == 1


def test_sentence_joins_capability_first_item() -> None:
    """The sentence extends an existing SHOULD item instead of adding one."""
    lines = [line for line in _read(SOURCE).splitlines() if SENTENCE in line]
    assert len(lines) == 1
    assert lines[0].startswith("2. **Capability-first**.")


@pytest.mark.parametrize("relative", GENERATED_COPIES)
def test_generated_copy_carries_sentence_once(relative: str) -> None:
    assert _read(relative).count(SENTENCE) == 1
