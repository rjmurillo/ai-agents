"""Every repo-only instruments.py names the valid ids when asked to run an unknown one."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = sorted(
    p for p in (ROOT / ".claude" / "skills").glob("*/scripts/instruments.py") if not p.is_symlink()
)


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), "--repo", str(ROOT), *args],
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=60,
    )


def test_every_repo_only_skill_is_covered() -> None:
    assert len(SCRIPTS) >= 17


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.parents[1].name)
def test_unknown_id_exits_2_and_the_message_lists_valid_ids(script: Path) -> None:
    listed = _run(script, "list")
    assert listed.returncode == 0, listed.stderr

    result = _run(script, "run", "no-such-instrument")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "no-such-instrument" in result.stderr
    first_id = _first_listed_id(listed.stdout)
    assert first_id in result.stderr


def _first_listed_id(text: str) -> str:
    """Return the first instrument id from the `list` output (JSON lines or one JSON doc)."""
    text = text.strip()
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        doc = json.loads(text.splitlines()[0])
    rows = doc if isinstance(doc, list) else doc.get("instruments", doc.get("rows", [doc]))
    row = rows[0]
    return str(row["id"] if isinstance(row, dict) else row)
