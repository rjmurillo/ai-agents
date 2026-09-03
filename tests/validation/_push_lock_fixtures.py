"""Scaffolding shared by the push-lock gate suites (issues #4366, #4635).

The gate reads two units, a fenced block and a run of unfenced prose, so its
tests split across two modules along the same seam. The builders and the
staged-repository helper live here rather than in either module, so the two
suites cannot drift into disagreeing about what a recipe looks like.

Only the helpers live here. Following
``tests/validation/_adr_debate_repo.py``, this module holds no tests and no
fixtures: a fixture has to be discoverable by pytest, and these do not.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

CANONICAL_LINE = 'flock "$HOME/src/scratch/locks/push-lock-$SLUG.lock" git push origin "$BR"'


def _fence(*lines: str) -> str:
    """Return the lines wrapped in a bash fence, with the trailing blank line."""
    return "\n".join(["```bash", *lines, "```", ""])


def _prose(*lines: str) -> str:
    """Return the lines as one unfenced paragraph, which is one scan unit."""
    return "\n".join(lines) + "\n"


def _init_repo(repo: Path, files: dict[str, str]) -> None:
    """Create a git repository holding ``files``, committed."""
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    for relative, content in files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)
