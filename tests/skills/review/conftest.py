"""Put the /review scripts and the github skill's code-scanning helpers on sys.path."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TESTS_DIR = Path(__file__).resolve().parent
for _path in (
    _TESTS_DIR,
    _PROJECT_ROOT / ".claude" / "lib",
    _PROJECT_ROOT / ".claude" / "skills" / "review" / "scripts",
    _PROJECT_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr",
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
