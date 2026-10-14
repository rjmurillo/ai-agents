"""Fixture helpers for the skillify tests: paths and skill writers."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = REPO_ROOT / ".claude" / "skills" / "skillify"

GOOD_SKILL = """---
name: {name}
description: {description}
---

# Title

Framing paragraph.

## Triggers

- "{trigger}"

## Contract

The note exists.

## Procedure

1. Read the input.
2. Write the note. Ask for approval before publishing it.

## Anti-patterns

- Guessing the destination.
- Publishing without approval.

## Pitfalls

| Gotcha | Fix |
|--------|-----|
| Path with spaces | Quote it |
| CRLF line endings | Read as text |

## Verification

- [ ] The note exists.
"""


def make_skill(
    root: Path,
    name: str,
    description: str = "Ingest a meeting transcript into notes.",
    trigger: str = "ingest a meeting transcript",
    body: str | None = None,
) -> Path:
    """Write `<root>/<name>/SKILL.md` and return the file path."""
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    text = (
        body
        if body is not None
        else GOOD_SKILL.format(name=name, description=description, trigger=trigger)
    )
    skill_file = directory / "SKILL.md"
    skill_file.write_text(text, encoding="utf-8", newline="")
    return skill_file
