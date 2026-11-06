"""Helpers so the PR body allocator can seed without a network clone (#6506)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

_PLACEHOLDER = "<!-- replace with PR body -->\n"


def init_base_repo(root: Path) -> Path:
    """Make ``root`` a git repo with an empty ``origin/main``; no-op when it is one."""
    if (root / ".git").exists():
        return root
    base = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-C", str(root)]
    for args in (
        ["init", "-q", "-b", "main"],
        ["-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "base"],
        ["update-ref", "refs/remotes/origin/main", "HEAD"],
    ):
        subprocess.run([*base, *args], capture_output=True, check=True)
    return root


def prepare_offline(prepare_module: Any, root: Path) -> Path:
    """Allocate a body file without reading git, for tests that script ``subprocess.run``.

    Those tests check body-file containment, not template seeding, and a real git
    call here would consume their ordered subprocess mocks.
    """
    # new_pr re-exports the function, so patch the globals it runs against.
    allocator = prepare_module.prepare_pr_body
    with patch.dict(allocator.__globals__, {"_seed_content": lambda *_a, **_k: _PLACEHOLDER}):
        return allocator(root)
