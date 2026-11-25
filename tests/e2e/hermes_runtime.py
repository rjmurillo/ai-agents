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

# A reviewed high finding: (``pattern_id``, file inside the pack, 1-based line,
# SHA-256 hex of that line's text). Lines are numbered the way the pinned guard
# numbers them: ``read_text(encoding="utf-8-sig").split("\n")`` in
# ``tools/skills_guard.py``. A finding that moves, whose line changes, or that is
# new does not match, so it needs a fresh review.
ReviewedFinding = tuple[str, str, int, str]

# High guard findings that were read and accepted, per pack (ADR-115 Decision 6).
# A ``caution`` pack installs with ``--force`` only when every high finding it has
# is listed here. Any other high finding fails the smoke until someone reviews it.
# ``dangerous`` (any critical finding) is never forced. Reviewed 2026-11-19 at
# hermes-agent 63d0b94120027d487c9a5235b9ec64b696af1b26:
# - context_exfil: prose that tells the agent to read earlier plan or spec output
#   from the conversation.
# - inline_shell_exec: a backtick-matching regex, a CI error table row, and
#   read-only ``!`git ...``` context lines in two SKILL.md files.
# - python_os_environ: a reference example that drops CI variables from a child
#   process environment.
# The invisible_unicode entry for skillforge's ``_conformance_parse.py`` was
# dropped after #7531 wrote that byte-order mark as an ``\ufeff`` escape.
_GH_ISSUE = "skills/github/scripts/issue/check_existing_pr_for_issue.py"
FORCE_ALLOWED_FINDINGS: dict[str, frozenset[ReviewedFinding]] = {
    "project-toolkit-delivery": frozenset(
        {
            (
                "context_exfil",
                "skills/build/SKILL.md",
                26,
                "044b7a3d3ee253b9b88f48fae33d24cf00de3ec6aef3582e05d6b7a096354b81",
            ),
            (
                "context_exfil",
                "skills/plan/SKILL.md",
                38,
                "f9568df509fac0462cd7e194a57a4dd984e89bf27f500cf35d4ab0d98533f89e",
            ),
            (
                "inline_shell_exec",
                "skills/github/fix-ci.md",
                137,
                "25f389554f53cba49b5ade78b0f47887a2477ac49ffe9f01f6503f5c6e251526",
            ),
            (
                "inline_shell_exec",
                _GH_ISSUE,
                122,
                "45947c367269d02c1b8ef3be1be51524705fa86d5aaa36b81e9562d0a552c2c9",
            ),
            (
                "inline_shell_exec",
                _GH_ISSUE,
                124,
                "cd329b23957bfa205df0b31ae3ef439979beaa018506e767a4fcbbb6320b74e0",
            ),
            (
                "inline_shell_exec",
                "skills/pr-review/SKILL.md",
                77,
                "b6d90e26d7b0c71c7cec3facc4d6df85ec16906a41768c0ba638f968cfaf44c5",
            ),
            (
                "inline_shell_exec",
                "skills/pr-review/SKILL.md",
                78,
                "2ea4295d4bd6c37d574dba6e003064e4e7cbe0de207cd71034c0c885dcdd5860",
            ),
            (
                "inline_shell_exec",
                "skills/push-pr/SKILL.md",
                33,
                "3bf15d66448dee25466cf8e62241abc4aded65669586a53e2b8c741654e0f47e",
            ),
            (
                "inline_shell_exec",
                "skills/push-pr/SKILL.md",
                34,
                "bb91750fc659d56fc8c4ca22cb1cf2e484ddce69f3ba3cbea3f2e24f0a8953ac",
            ),
            (
                "inline_shell_exec",
                "skills/push-pr/SKILL.md",
                35,
                "b6d90e26d7b0c71c7cec3facc4d6df85ec16906a41768c0ba638f968cfaf44c5",
            ),
        }
    ),
    "project-toolkit-authoring": frozenset(
        {
            (
                "python_os_environ",
                "skills/skillforge/references/script-design-rules.md",
                232,
                "06908eb0196006f16571a90e2a5d615884e0cd0655167c6a09a6b1779f1c79f4",
            ),
        }
    ),
}

# Snippets run with the Python that Hermes installed into, so they can import its
# own modules. They print one JSON document on stdout.
LIST_SKILLS_SNIPPET = """
import json
from tools.skills_tool import skills_list
print(json.dumps([s["name"] for s in json.loads(skills_list())["skills"]]))
"""

GUARD_SNIPPET = """
import hashlib, json, sys
from pathlib import Path
from tools.plugin_guard import scan_plugin
out = {}
for p in sys.argv[1:]:
    result = scan_plugin(Path(p), source="local")
    high = set()
    for f in result.findings:
        if f.severity not in ("high", "critical"):
            continue
        digest = "unreadable"
        if isinstance(f.line, int) and f.line >= 1 and isinstance(f.file, str):
            try:
                lines = (Path(p) / f.file).read_text(encoding="utf-8-sig").split("\\n")
                text = lines[f.line - 1]
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            except (OSError, UnicodeDecodeError, IndexError):
                pass
        high.add((f.pattern_id, f.file, f.line, digest))
    out[p] = {"verdict": result.verdict, "high": sorted(high, key=str)}
print(json.dumps(out))
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


def force_for_verdict(
    pack_name: str, verdict: str, high_findings: frozenset[ReviewedFinding]
) -> bool:
    """Return whether ``pack_name`` installs with ``--force`` under guard ``verdict``.

    ``high_findings`` holds the pack's high and critical findings as
    ``(pattern_id, file, line, sha256 of that line)``. A ``safe`` pack installs
    without ``--force``. A ``caution`` pack gets ``--force`` only when every one
    of its high findings is in :data:`FORCE_ALLOWED_FINDINGS` for that pack.
    Every other case fails the smoke, so a new finding cannot be installed past
    the guard without a review.
    """
    if verdict == "safe":
        return False
    if verdict != "caution":
        raise ValueError(f"{pack_name} is rated {verdict!r}; only caution may install with --force")
    if not high_findings:
        raise ValueError(
            f"{pack_name} is rated 'caution' with no high findings; the guard output is not trusted"
        )
    unreviewed = sorted(high_findings - FORCE_ALLOWED_FINDINGS.get(pack_name, frozenset()))
    if unreviewed:
        raise ValueError(
            f"{pack_name} is rated 'caution' with unreviewed high findings {unreviewed}; "
            "review them and add them to FORCE_ALLOWED_FINDINGS before --force"
        )
    return True


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
