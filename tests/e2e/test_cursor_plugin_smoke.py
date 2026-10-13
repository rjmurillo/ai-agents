"""Cursor plugin smoke (ADR-115 Decision 10 and 9).

Two legs.

* Script leg, always runs, no CLI: the Cursor tree's ``github`` skill script
  finds its ``lib/`` through the skill's own resolver with every plugin-root
  variable unset, and a copy of ``skills/`` without ``lib/`` fails with the
  loader message (negative control).
* Host leg, ``cursor`` + ``smoke`` markers: one ``cursor-agent`` model turn
  loads the tree with ``--plugin-dir`` and runs the script. It needs
  ``RUN_CLI_E2E=1``, the CLI on PATH, and a Cursor login. A missing CLI or login
  skips loudly with the reason; it never passes.

What needs a login (measured with cursor-agent 2026.10.01-e373342 under a scratch
HOME): every ``plugin`` subcommand, ``--list-models``, and any prompt exit with
"Authentication required". No host-side load evidence exists without a login.
``cursor-agent`` also reads ``~/.claude/plugins``, so a machine that installed
the Claude plugin can surface that copy first. The host leg therefore copies the
tree to a scratch directory and requires the reported skill directory to be
inside it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CURSOR_TREE = REPO_ROOT / "src" / "cursor"
SCRIPT_REL = Path("skills") / "github" / "scripts" / "pr" / "get_pr_checks.py"
_PLUGIN_ROOT_VARS = (
    "CURSOR_PLUGIN_ROOT",
    "CLAUDE_PLUGIN_ROOT",
    "COPILOT_PLUGIN_ROOT",
    "PLUGIN_ROOT",
)
_STRIPPED_VARS = (*_PLUGIN_ROOT_VARS, "GITHUB_WORKSPACE", "CLAUDE_PROJECT_DIR", "PYTHONPATH")
_SCRIPT_TIMEOUT_SECONDS = 30
_CLI_TIMEOUT_SECONDS = 240
_STATUS_TIMEOUT_SECONDS = 30
_LOADER_MESSAGE = "Plugin lib directory not found"
_RUN = os.environ.get("RUN_CLI_E2E") == "1"


def _clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _STRIPPED_VARS}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run_script(script: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(script), "--help"],
        cwd=cwd,
        env=_clean_env(),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_SCRIPT_TIMEOUT_SECONDS,
        check=False,
    )


# Script leg ------------------------------------------------------------------


def test_cursor_tree_skill_script_finds_lib_without_plugin_root_variables(tmp_path: Path) -> None:
    result = _run_script(CURSOR_TREE / SCRIPT_REL, cwd=tmp_path)
    assert result.returncode == 0, result.stderr[-600:]
    assert "usage: get_pr_checks.py" in result.stdout


def test_cursor_tree_skill_script_fails_loudly_without_lib(tmp_path: Path) -> None:
    """Negative control: a skills/ copy with no sibling lib/ must not run."""
    copy = tmp_path / "tree"
    shutil.copytree(CURSOR_TREE / "skills" / "github", copy / "skills" / "github")
    result = _run_script(copy / SCRIPT_REL, cwd=tmp_path)
    assert result.returncode != 0
    assert _LOADER_MESSAGE in result.stderr, result.stderr[-400:]


def test_script_environment_really_has_no_plugin_root_variables() -> None:
    env = _clean_env()
    assert not [name for name in _STRIPPED_VARS if name in env]


# Host leg --------------------------------------------------------------------


def _cursor_agent() -> str | None:
    return shutil.which("cursor-agent")


def _logged_in(cli: str) -> tuple[bool, str]:
    result = subprocess.run(
        [cli, "status"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_STATUS_TIMEOUT_SECONDS,
        check=False,
    )
    text = (result.stdout + result.stderr).strip()
    return ("Logged in" in text and "Not logged in" not in text), text[-200:]


def _host_prompt(plugin_dir: Path) -> str:
    return (
        "Use only Cursor skill discovery. Find the skill named github whose directory is "
        f"inside {plugin_dir}. Run these shell commands exactly and show the raw output: "
        "(1) python3 -I <skill dir>/scripts/pr/get_pr_checks.py --help 2>&1 | head -3 "
        "(2) printenv CURSOR_PLUGIN_ROOT CLAUDE_PLUGIN_ROOT PLUGIN_ROOT; echo end. "
        "Then print the skill dir you used on a line starting with SKILL_DIR=."
    )


@pytest.mark.smoke
@pytest.mark.cursor
@pytest.mark.timeout(_CLI_TIMEOUT_SECONDS + _STATUS_TIMEOUT_SECONDS + 30)
def test_cursor_agent_loads_the_tree_and_runs_a_skill_script(tmp_path: Path) -> None:
    """One model turn: find the github skill, run its script, report plugin-root variables."""
    if not _RUN:
        pytest.skip("host leg needs RUN_CLI_E2E=1")
    cli = _cursor_agent()
    if cli is None:
        pytest.skip("host leg needs the cursor-agent CLI on PATH")
    ok, status = _logged_in(cli)
    if not ok:
        pytest.skip(f"host leg needs a Cursor login (cursor-agent status: {status!r})")

    plugin_dir = tmp_path / "plugin"
    shutil.copytree(CURSOR_TREE, plugin_dir)
    work = tmp_path / "ws"
    work.mkdir()
    result = subprocess.run(
        [
            cli,
            "--plugin-dir",
            str(plugin_dir),
            "--workspace",
            str(work),
            "--trust",
            "--force",
            "-p",
            _host_prompt(plugin_dir),
        ],
        cwd=work,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_CLI_TIMEOUT_SECONDS,
        check=False,
    )
    out = result.stdout
    assert result.returncode == 0, (result.stdout + result.stderr)[-600:]
    assert "usage: get_pr_checks.py" in out, out[-800:]
    skill_dirs = [ln for ln in out.splitlines() if ln.startswith("SKILL_DIR=")]
    assert skill_dirs, out[-800:]
    assert str(plugin_dir) in skill_dirs[-1], f"loaded a different copy: {skill_dirs[-1]!r}"
