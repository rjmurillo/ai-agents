"""Shared fixtures for the corpus export tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(record) for record in records) + "\n"
    path.write_text(text, encoding="utf-8")


SCRIPT = (
    REPO_ROOT / "src" / "claude" / "skills" / "skill-doctor" / "scripts" / "collect_sessions.py"
)
NOW = datetime.now(timezone.utc)
OLD = (NOW - timedelta(hours=3)).isoformat()
LONG_TEXT = "line of prose with a measured 12 ms result. " * 200  # about 9000 characters


def run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the collector against synthetic homes, with HOME isolated."""
    home = tmp_path / "isolated-home"
    home.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in {"CI", "GITHUB_OUTPUT", "GITHUB_ENV"}}
    env.update({"HOME": str(home), "USERPROFILE": str(home), "CLAUDE_CONFIG_DIR": str(home / "c")})
    for key in ("CODEX_HOME", "COPILOT_HOME", "HERMES_HOME", "MUSE_HOME", "WARP_DATA_DIR"):
        env[key] = str(home / key.lower())
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--min-idle-minutes", "0", *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
