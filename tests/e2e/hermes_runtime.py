"""Helpers for the Hermes plugin smoke (ADR-115 Decision 10).

Everything here runs the real ``hermes`` CLI or the Python that Hermes installed
into, under a scratch ``HERMES_HOME`` and a scratch ``HOME``. Nothing reads or
writes ``~/.hermes``.

Measured at hermes-agent 63d0b94120027d487c9a5235b9ec64b696af1b26:

- ``hermes plugins install <path>`` reads an absolute path as ``owner/repo``
  shorthand, so a local pack installs as ``file://<git repo>#<subdir>``.
- A pack with a ``caution`` guard verdict is blocked without ``--force``.
  ``dangerous`` is blocked even with it.
- ``PLUGIN_ROOT`` is exported only to MCP stdio servers
  (``hermes_cli/agent_plugins.py`` lines 391-392). A skill's shell does not get it.
- ``tools.skills_tool.skills_list`` returns portable plugin skills as
  ``agent-plugin-<slug>-<hash>:<name>`` once the plugin is enabled.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

INSTALL_TIMEOUT_SECONDS = 300
QUICK_TIMEOUT_SECONDS = 120

# Snippets run with the Python that Hermes installed into, so they can import its
# own modules. They print one JSON document on stdout.
LIST_SKILLS_SNIPPET = """
import json
from tools.skills_tool import skills_list
print(json.dumps([s["name"] for s in json.loads(skills_list())["skills"]]))
"""

GUARD_SNIPPET = """
import json, sys
from pathlib import Path
from tools.plugin_guard import scan_plugin
print(json.dumps({p: scan_plugin(Path(p), source="local").verdict for p in sys.argv[1:]}))
"""

CHECKOUT_SNIPPET = """
import hermes_cli, pathlib
print(pathlib.Path(hermes_cli.__file__).resolve().parent.parent)
"""

SCRIPT_ENV_KEYS_THAT_MUST_BE_UNSET = (
    "CLAUDE_PLUGIN_ROOT",
    "COPILOT_PLUGIN_ROOT",
    "GITHUB_WORKSPACE",
)


class HermesRuntimeError(Exception):
    """The Hermes install or a command it ran did not behave as the smoke needs."""


def hermes_python(hermes_bin: Path) -> Path:
    """Return the Python that ``hermes`` runs on, so a snippet can import its modules.

    A venv install puts ``python`` next to the launcher, and the launcher's own
    first line is ``#!/bin/sh`` plus an ``exec`` trick, so the shebang is not the
    answer. The launcher is resolved first because ``pipx`` and ``~/.local/bin``
    link to it. The interpreter itself is not resolved: a venv ``python`` is a
    link to the base interpreter, and only the venv one can import Hermes.
    """
    launcher = hermes_bin.resolve()
    sibling = launcher.parent / "python"
    if sibling.is_file():
        return sibling
    with launcher.open("rb") as handle:
        first = handle.readline().decode("utf-8", errors="replace").strip()
    parts = first[2:].split() if first.startswith("#!") else []
    interpreter = Path(parts[0]) if parts else None
    if (
        interpreter is None
        or interpreter.name in {"sh", "bash", "env"}
        or not interpreter.is_file()
    ):
        raise HermesRuntimeError(
            f"cannot find the Python behind {hermes_bin}: "
            f"no sibling python, first line {first[:60]!r}"
        )
    return interpreter


def scratch_env(home: Path) -> dict[str, str]:
    """An environment that confines Hermes to ``home`` and keeps only what it needs."""
    hermes_home = home / "hermes-home"
    hermes_home.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "HERMES_HOME": str(hermes_home),
        "NO_COLOR": "1",
        "PYTHONUTF8": "1",
    }
    # Git needs these to clone the file:// repo on a runner with no global config.
    for key in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"):
        env[key] = os.devnull
    return env


def run(
    args: Sequence[str | Path],
    env: Mapping[str, str],
    *,
    cwd: Path,
    timeout: int = QUICK_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """Run a command with ``env`` as the whole environment, never inheriting ours."""
    return subprocess.run(
        [str(a) for a in args],
        env=dict(env),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def stage_git_repo(files_root: Path, repo: Path, *, subdir: str) -> Path:
    """Copy ``files_root`` to ``repo/<subdir>`` and commit it, so Hermes can clone it.

    Hermes installs from a Git source. Copying the working tree (not cloning HEAD)
    means the smoke tests the bytes under review, committed or not.
    """
    target = repo / subdir
    shutil.copytree(files_root, target, symlinks=False)
    git = ["git", "-c", "user.name=smoke", "-c", "user.email=smoke@example.invalid"]
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(repo)}
    for step in (
        ["init", "-q", "."],
        ["add", "-A"],
        ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "stage"],
    ):
        done = run([*git, *step], env, cwd=repo)
        if done.returncode != 0:
            raise HermesRuntimeError(f"git {step[0]} failed: {done.stderr.strip()}")
    return repo


def install_pack(
    hermes_bin: Path, env: Mapping[str, str], repo: Path, subdir: str, *, force: bool, cwd: Path
) -> subprocess.CompletedProcess[str]:
    """``hermes plugins install file://<repo>#<subdir> --no-enable``."""
    args: list[str | Path] = [
        hermes_bin,
        "plugins",
        "install",
        f"file://{repo}#{subdir}",
        "--no-enable",
    ]
    if force:
        args.append("--force")
    return run(args, env, cwd=cwd, timeout=INSTALL_TIMEOUT_SECONDS)


def enable_pack(
    hermes_bin: Path, env: Mapping[str, str], name: str, *, cwd: Path
) -> subprocess.CompletedProcess[str]:
    return run(
        [hermes_bin, "plugins", "enable", name], env, cwd=cwd, timeout=INSTALL_TIMEOUT_SECONDS
    )


def python_json(
    python: Path, snippet: str, env: Mapping[str, str], *, cwd: Path, argv: Sequence[str] = ()
) -> tuple[object, str]:
    """Run ``python -I -c snippet`` and return ``(parsed stdout JSON, stderr)``."""
    done = run([python, "-I", "-c", snippet, *argv], env, cwd=cwd)
    if done.returncode != 0:
        raise HermesRuntimeError(
            f"snippet failed ({done.returncode}): {done.stderr.strip()[-400:]}"
        )
    try:
        last_line = done.stdout.strip().splitlines()[-1]
        return json.loads(last_line), done.stderr
    except (IndexError, json.JSONDecodeError) as exc:
        raise HermesRuntimeError(f"snippet printed no JSON: {done.stdout[-300:]!r}") from exc


def hermes_checkout_commit(python: Path, env: Mapping[str, str], *, cwd: Path) -> str:
    """The Git commit of the source tree Hermes runs from (an editable install)."""
    root, _ = python_text(python, CHECKOUT_SNIPPET, env, cwd=cwd)
    done = run(["git", "-C", root, "rev-parse", "HEAD"], {"PATH": env["PATH"]}, cwd=cwd)
    if done.returncode != 0:
        raise HermesRuntimeError(f"{root} is not a Git checkout: {done.stderr.strip()}")
    return done.stdout.strip()


def python_text(
    python: Path, snippet: str, env: Mapping[str, str], *, cwd: Path
) -> tuple[str, str]:
    """Run ``python -I -c snippet`` and return ``(stdout stripped, stderr)``."""
    done = run([python, "-I", "-c", snippet], env, cwd=cwd)
    if done.returncode != 0:
        raise HermesRuntimeError(
            f"snippet failed ({done.returncode}): {done.stderr.strip()[-400:]}"
        )
    return done.stdout.strip(), done.stderr


def script_env(home: Path, plugin_root: Path) -> dict[str, str]:
    """The environment a Hermes skill script is checked under.

    ``PLUGIN_ROOT`` is set to the package root, as the Agent Plugins spec
    describes. The three variables the shipped scripts read for Claude, Copilot,
    and a CI workspace are absent, so a pass cannot come from them.
    """
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "PLUGIN_ROOT": str(plugin_root),
    }
    leaked = [key for key in SCRIPT_ENV_KEYS_THAT_MUST_BE_UNSET if key in env]
    if leaked:
        raise HermesRuntimeError(f"script env must not carry {leaked}")
    return env


def run_script_help(
    script: Path, env: Mapping[str, str], *, cwd: Path
) -> subprocess.CompletedProcess[str]:
    """``python -I <script> --help`` with the interpreter that runs the tests."""
    return run([sys.executable, "-I", script, "--help"], env, cwd=cwd)
