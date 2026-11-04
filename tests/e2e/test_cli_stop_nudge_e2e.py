#!/usr/bin/env python3
"""Real Claude Code CLI smoke for the plugin Stop nudge (REQ-048 AC-17).

Launches the real ``claude`` CLI with a copy of ``src/claude/`` as
``--plugin-dir``, from a directory that is not the plugin root, with a session
that makes the friction branch qualify. It checks two things:

1. The nudge's ``systemMessage`` reaches the user intact (it is in the CLI's
   output stream).
2. The next turn's model context does not hold the advisory text (no
   ``user`` or ``assistant`` record in the saved session transcript carries it).

Opt-in like the other real-CLI cases in ``test_cli_hook_e2e.py``: it needs
``RUN_CLI_E2E=1``, the ``claude`` CLI on PATH, real auth, and credits. It is not
listed in ``plugin-cli-smoke.yml``, so normal CI never runs it. Run locally:

    RUN_CLI_E2E=1 uv run pytest tests/e2e/test_cli_stop_nudge_e2e.py -m "smoke and claude" -v

Status when written: NOT RUN against a live CLI. The stream-json record shapes
used below are inferred from the CLI's documented output, so the first live run
may need the extraction helpers adjusted.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT))

import copilot_hook_probe  # noqa: E402
import smoke_skip_policy  # noqa: E402

from scripts.cli_exec import resolve_executable  # noqa: E402

NUDGE_PHRASE = "/retrospective"
PROMPT = "Run the shell command `false` with Bash three times, one call each, then say done."
TIMEOUT_SECONDS = 300
CONTEXT_RECORD_TYPES = frozenset({"user", "assistant"})

_RUN = os.environ.get("RUN_CLI_E2E") == "1"
requires_claude = pytest.mark.skipif(
    not (_RUN and shutil.which("claude")),
    reason="needs RUN_CLI_E2E=1 and the claude CLI on PATH (real auth + credits)",
)


def stream_events(stdout: str) -> list[dict]:
    """Parse the CLI's newline-delimited JSON stream, skipping non-JSON lines."""
    events = []
    for line in stdout.splitlines():
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        if isinstance(doc, dict):
            events.append(doc)
    return events


def session_id(events: list[dict]) -> str | None:
    for event in events:
        value = event.get("session_id")
        if isinstance(value, str) and value:
            return value
    return None


def context_records_with(transcript: Path, phrase: str) -> list[int]:
    """Line numbers of user or assistant records that contain *phrase*."""
    hits = []
    for number, line in enumerate(transcript.read_text(encoding="utf-8").splitlines(), 1):
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        if doc.get("type") in CONTEXT_RECORD_TYPES and phrase in line:
            hits.append(number)
    return hits


def find_transcript(config_home: Path, sid: str) -> Path | None:
    matches = sorted((config_home / "projects").glob(f"*/{sid}.jsonl"))
    return matches[0] if matches else None


@pytest.mark.smoke
@pytest.mark.claude
@requires_claude
def test_friction_stop_nudge_reaches_the_user_and_not_model_context(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    for name in ("hooks", "lib", ".claude-plugin"):
        shutil.copytree(
            REPO_ROOT / "src" / "claude" / name,
            plugin / name,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    shutil.copy2(REPO_ROOT / "src" / "claude" / "hooks.json", plugin / "hooks.json")
    userland = tmp_path / "userland"
    userland.mkdir()
    state = tmp_path / "state"
    env = copilot_hook_probe.clean_env()
    env["XDG_STATE_HOME"] = str(state)
    env["AI_AGENTS_RETRO_NUDGE_THRESHOLD"] = "1"

    try:
        run = subprocess.run(
            [
                resolve_executable("claude"),
                "-p",
                PROMPT,
                "--plugin-dir",
                str(plugin),
                "--allowedTools",
                "Bash",
                "--output-format",
                "stream-json",
                "--verbose",
            ],
            cwd=userland,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=TIMEOUT_SECONDS,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        smoke_skip_policy.skip_or_fail_unmarked(f"claude run exceeded {TIMEOUT_SECONDS}s")
    smoke_skip_policy.skip_or_fail_on_claude_block(run, "claude stop nudge e2e")

    assert list((state / "ai-agents-reflect-nudge").glob("*")), (
        "the plugin Stop hook never claimed a marker. "
        f"stdout={run.stdout[-600:]!r} stderr={run.stderr[-600:]!r}"
    )
    assert NUDGE_PHRASE in run.stdout, "the nudge text never reached the CLI output stream"

    sid = session_id(stream_events(run.stdout))
    assert sid, "no session_id in the CLI stream"
    config_home = Path(env.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    transcript = find_transcript(config_home, sid)
    assert transcript is not None, f"session transcript for {sid} not found under {config_home}"
    assert context_records_with(transcript, NUDGE_PHRASE) == [], (
        "the advisory text is in a user or assistant record, so the next turn sees it"
    )


def test_context_record_scan_flags_only_context_records(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    lines = [
        {"type": "system", "content": f"hook said {NUDGE_PHRASE}"},
        {"type": "user", "message": {"content": "hello"}},
        {"type": "assistant", "message": {"content": f"leaked {NUDGE_PHRASE}"}},
    ]
    transcript.write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n", "utf-8")
    assert context_records_with(transcript, NUDGE_PHRASE) == [3]


def test_find_transcript_and_stream_parsing(tmp_path: Path) -> None:
    (tmp_path / "projects" / "p").mkdir(parents=True)
    wanted = tmp_path / "projects" / "p" / "abc.jsonl"
    wanted.write_text("{}", encoding="utf-8")
    assert find_transcript(tmp_path, "abc") == wanted
    assert find_transcript(tmp_path, "zzz") is None
    events = stream_events('garbage\n{"session_id": "abc"}\n[1]\n')
    assert session_id(events) == "abc"
    assert session_id([]) is None
