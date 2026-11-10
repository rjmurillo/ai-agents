"""Synthetic journal writers shared by the inherited collector tests."""

import json
import os
import subprocess
import sys
from pathlib import Path

PREVIOUS_FILE_LIMIT = 8 * 1024 * 1024


def run_collector(tmp_path, home, *args, root="claude"):
    repo = Path(__file__).resolve().parents[3]
    script = repo / "src" / root / "skills" / "skill-doctor" / "scripts" / "collect_sessions.py"
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"CI", "GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_STEP_SUMMARY"}
    }
    isolated_home = tmp_path / "isolated-home"
    isolated_home.mkdir(exist_ok=True)
    env.update({"HOME": str(isolated_home), "USERPROFILE": str(isolated_home)})
    for key in (
        "APPDATA",
        "LOCALAPPDATA",
        "XDG_DATA_HOME",
        "WARP_DATA_DIR",
        "HERMES_HOME",
        "CLAUDE_CONFIG_DIR",
        "CODEX_HOME",
    ):
        env[key] = str(isolated_home / key.lower())
    env["COPILOT_HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(script), "--out", str(tmp_path / "report"), *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")


def write_jsonl_past_previous_limit(path, first_record, last_records):
    path.parent.mkdir(parents=True, exist_ok=True)
    filler = json.dumps({"type": "ignored", "padding": "x" * 1024}) + "\n"
    with path.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(first_record) + "\n")
        while stream.tell() <= PREVIOUS_FILE_LIMIT:
            stream.write(filler)
        for record in last_records:
            stream.write(json.dumps(record) + "\n")
