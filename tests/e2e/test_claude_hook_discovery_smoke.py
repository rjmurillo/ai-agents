#!/usr/bin/env python3
"""Zero-token Claude Code smoke: the CLI still discovers the plugin's hooks.

REQ-048 ships the Stop nudge as a plugin hook registered in
``src/claude/hooks/hooks.json``. A hook that the CLI fails to discover fails
open, so the nudge would stop for every user with no error. This smoke runs
``claude --plugin-dir <dir> plugin details project-toolkit``, which makes no
model call and needs no login, and reads the ``Hooks (N)`` row.

``N`` counts hook events, not commands. A plugin with three Stop commands in two
groups plus one SessionStart command prints ``Hooks (2)  Stop, SessionStart``.
The expected events therefore come from the top-level keys of ``hooks.json``.

The negative control moves ``hooks.json`` to the plugin root (the old layout)
and expects ``Hooks (0)``, so the positive test cannot pass vacuously.

Run locally:

    RUN_CLI_E2E=1 uv run pytest tests/e2e/test_claude_hook_discovery_smoke.py \\
        -m "smoke and claude" -v
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT))

from scripts.cli_exec import resolve_executable  # noqa: E402

PLUGIN_SRC = REPO_ROOT / "src" / "claude"
HOOKS_JSON = PLUGIN_SRC / "hooks" / "hooks.json"
PLUGIN_NAME = "project-toolkit"
TIMEOUT_SECONDS = 120
PLUGIN_SUBTREES = ("hooks", "lib", ".claude-plugin")

# [ \t] rather than \s so a zero-count row does not swallow the next line.
_HOOKS_ROW = re.compile(r"^[ \t]*Hooks[ \t]*\((\d+)\)[ \t]*(.*)$", re.MULTILINE)

_RUN = os.environ.get("RUN_CLI_E2E") == "1"
requires_claude = pytest.mark.skipif(
    not (_RUN and shutil.which("claude")),
    reason="needs RUN_CLI_E2E=1 and the claude CLI on PATH (no login or credits needed)",
)


def parse_hooks_row(text: str) -> tuple[int, list[str]] | None:
    """Return ``(event count, event names)`` from the ``Hooks (N)`` row, or None.

    Event names are the part of the row after the count that precedes the first
    ``(``, split on commas. The parser does not depend on the dash the CLI
    prints before its trailing note.
    """
    match = _HOOKS_ROW.search(text)
    if match is None:
        return None
    count = int(match.group(1))
    names_part = match.group(2).split("(", 1)[0]
    names = [name.strip() for name in names_part.split(",") if name.strip()]
    return count, names


def expected_events() -> list[str]:
    """Sorted top-level event keys of the shipped ``hooks.json``."""
    document = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    return sorted(document["hooks"])


def isolated_env(home: Path) -> dict[str, str]:
    """Minimal environment: empty HOME, PATH only. No credentials reach the CLI."""
    return {"HOME": str(home), "PATH": os.environ.get("PATH", "")}


def run_plugin_details(plugin_dir: Path, home: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            resolve_executable("claude"),
            "--plugin-dir",
            str(plugin_dir),
            "plugin",
            "details",
            PLUGIN_NAME,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_SECONDS,
        check=False,
        env=isolated_env(home),
    )


def _workdirs(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    cwd = tmp_path / "userland"
    home.mkdir()
    cwd.mkdir()
    return home, cwd


def _copy_plugin(tmp_path: Path) -> Path:
    plugin = tmp_path / "plugin"
    for name in PLUGIN_SUBTREES:
        shutil.copytree(
            PLUGIN_SRC / name, plugin / name, ignore=shutil.ignore_patterns("__pycache__")
        )
    return plugin


@pytest.mark.smoke
@pytest.mark.claude
@requires_claude
def test_cli_discovers_the_shipped_plugin_hooks(tmp_path: Path) -> None:
    home, cwd = _workdirs(tmp_path)

    run = run_plugin_details(PLUGIN_SRC, home, cwd)

    assert run.returncode == 0, f"stdout={run.stdout[-600:]!r} stderr={run.stderr[-600:]!r}"
    parsed = parse_hooks_row(run.stdout)
    assert parsed is not None, f"no Hooks row in output: {run.stdout[-600:]!r}"
    count, names = parsed
    expected = expected_events()
    assert expected, "hooks.json declares no events, so this guard would pass vacuously"
    assert count == len(expected)
    assert sorted(names) == expected


@pytest.mark.smoke
@pytest.mark.claude
@requires_claude
def test_cli_finds_no_hooks_when_hooks_json_sits_at_the_plugin_root(tmp_path: Path) -> None:
    """Negative control: the old layout must read as zero hooks."""
    home, cwd = _workdirs(tmp_path)
    plugin = _copy_plugin(tmp_path)
    (plugin / "hooks" / "hooks.json").rename(plugin / "hooks.json")

    run = run_plugin_details(plugin, home, cwd)

    assert run.returncode == 0, f"stdout={run.stdout[-600:]!r} stderr={run.stderr[-600:]!r}"
    parsed = parse_hooks_row(run.stdout)
    assert parsed is not None, f"no Hooks row in output: {run.stdout[-600:]!r}"
    assert parsed[0] == 0


def test_parse_hooks_row_reads_a_populated_row() -> None:
    text = "Plugin: x\n  Hooks (1)  Stop  (harness-only - no model context cost)\n"
    assert parse_hooks_row(text) == (1, ["Stop"])


def test_parse_hooks_row_zero_row_does_not_swallow_the_next_line() -> None:
    text = "  Hooks (0)\n  Skills (3)  a, b, c\n"
    assert parse_hooks_row(text) == (0, [])


def test_parse_hooks_row_reads_multiple_events() -> None:
    text = "  Hooks (2)  Stop, SessionStart  (harness-only - no model context cost)\n"
    assert parse_hooks_row(text) == (2, ["Stop", "SessionStart"])


@pytest.mark.parametrize("text", ["", "  Skills (3)  a, b\n", "Hooks without a count\n"])
def test_parse_hooks_row_returns_none_without_a_row(text: str) -> None:
    assert parse_hooks_row(text) is None


def test_expected_events_come_from_hooks_json() -> None:
    assert "Stop" in expected_events()
