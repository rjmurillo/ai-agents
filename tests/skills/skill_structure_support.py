"""Read a shipped skill's SKILL.md for the sub-skill structure tests.

The memory sub-skill tests pin the same structure: a frontmatter block, the
plugin-run locators the body names, and backtick triggers. They share these
readers and keep their skill-specific assertions in their own files.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_BUILD_SCRIPTS = Path(__file__).resolve().parents[2] / "build" / "scripts"
sys.path.insert(0, str(_BUILD_SCRIPTS))
try:
    import plugin_run_launcher
finally:
    sys.path.remove(str(_BUILD_SCRIPTS))

SKILLS_DIR = Path(__file__).resolve().parents[2] / ".claude" / "skills"
FRONTMATTER = re.compile(r"(?s)\A---\r?\n(.*?)\r?\n---\r?\n")
BACKTICK_TRIGGER = re.compile(r"`[^`]+`")


def locator_targets(body: str) -> set[str]:
    """Return every script path a plugin-run locator in ``body`` names."""
    return {
        match.script_rel
        for line in body.splitlines()
        for match in plugin_run_launcher.find_locators(line)
        if match.script_rel
    }


def frontmatter_block(text: str) -> str:
    """Return the frontmatter between the opening ``---`` fences of ``text``."""
    match = FRONTMATTER.search(text)
    assert match is not None, "SKILL.md must open with a --- frontmatter block"
    return match.group(1)
