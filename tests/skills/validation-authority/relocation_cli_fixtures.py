"""CLI runners shared by the relocation tests for validation-authority (issue #6506).

Kept apart from ``validation_record_fixtures``, which builds records in memory,
because these helpers start real subprocesses and write modules to disk.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKILLS_ROOT = PROJECT_ROOT / ".claude" / "skills"
RECORD_SCRIPT = SKILLS_ROOT / "validation-authority" / "scripts" / "validation_record.py"
TRIGGER_SCRIPT = SKILLS_ROOT / "build" / "scripts" / "validation_trigger.py"
SUBPROCESS_TIMEOUT_S = 60


def run_script(script: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``script`` with this interpreter in ``cwd`` and capture its output."""
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=SUBPROCESS_TIMEOUT_S,
        check=False,
    )


def trigger_output(cwd: Path, path: str, *effects: str) -> dict[str, Any]:
    """Run the real validation trigger on one changed path and return its JSON."""
    args = ["--repo-root", str(PROJECT_ROOT), "--changed-path", path]
    for effect in effects:
        args += ["--effect", effect]
    result = run_script(TRIGGER_SCRIPT, cwd, *args)
    assert result.returncode == 0, result.stderr
    output: dict[str, Any] = json.loads(result.stdout)
    return output


def write_moved_modules(root: Path, *, drop_param: bool = False) -> None:
    """Write the two destination modules that make_relocation_target() describes."""
    tests = root / "tests" / "validation"
    tests.mkdir(parents=True)
    (tests / "test_slow_part1.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    params = '"y"' if drop_param else '"x"'
    (tests / "test_slow_part2.py").write_text(
        "import pytest\n\n\nclass TestB:\n"
        f"    @pytest.mark.parametrize('v', [{params}])\n"
        "    def test_b(self, v):\n        pass\n",
        encoding="utf-8",
    )
