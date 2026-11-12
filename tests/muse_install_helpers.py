"""Shared helpers for the Muse install replay tests (issue #7278, issue #7226).

``src/muse/README.md`` holds the documented bash blocks. The tests replay them in
a scratch HOME so the install layout is checked, not assumed.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "src" / "muse" / "README.md"
LIB_MISSING_MESSAGE = "Plugin lib directory not found"
PERSONAL_HEADING = "## Install into the Muse personal agent"
CODE_HEADING = "## Install into Muse Code"
_LIB_RESOLUTION_ENV = frozenset({"COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "GITHUB_WORKSPACE"})


def section_blocks(heading: str) -> list[str]:
    """Return the bash blocks of the README section that starts at ``heading``.

    The section ends at the next ``## `` heading, so blocks of a later section
    are never replayed as part of this one.
    """
    text = README.read_text(encoding="utf-8")
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    return re.findall(r"```bash\n(.*?)```", section, flags=re.DOTALL)


def scratch_env(home: Path) -> dict[str, str]:
    # GITHUB_WORKSPACE is always set in CI. The skill script then reads
    # $GITHUB_WORKSPACE/.claude/lib and never looks at ~/workspace/lib, which
    # would hide the install layout this test exists to check.
    env = {k: v for k, v in os.environ.items() if k not in _LIB_RESOLUTION_ENV}
    env["HOME"] = str(home)
    return env


def run_bash(
    script: str, home: Path, *, xdg: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = scratch_env(home)
    env.pop("XDG_CONFIG_HOME", None)
    if xdg is not None:
        env["XDG_CONFIG_HOME"] = str(xdg)
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
