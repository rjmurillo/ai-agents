"""Put the /review scripts and the github skill's code-scanning helpers on sys.path.

The paths are added when pytest configures and removed when it shuts down, so nothing
outlives the run. The module names added here (``codeql_*``, ``code_scanning_*``) are
unique to this feature and shadow no other module.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TESTS_DIR = Path(__file__).resolve().parent
_PATHS = [
    str(path)
    for path in (
        _TESTS_DIR,
        _PROJECT_ROOT / ".claude" / "lib",
        _PROJECT_ROOT / ".claude" / "skills" / "review" / "scripts",
        _PROJECT_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr",
    )
]
_ADDED: list[str] = []


def pytest_configure() -> None:
    for path in _PATHS:
        if path not in sys.path:
            sys.path.insert(0, path)
            _ADDED.append(path)


def pytest_unconfigure() -> None:
    while _ADDED:
        path = _ADDED.pop()
        if path in sys.path:
            sys.path.remove(path)
