"""Shared setup for the D10 same-repository completion-gate tests (#6506).

Builds real git repositories, linked worktrees, and clones under ``tmp_path``
so the gate's sameness probe runs against git, not a mock.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.skills.github.dynamic_load_helpers import gate

LAUNCHED_REL = "skills/demo/scripts/run.py"
SCRIPT_REL = f".claude/{LAUNCHED_REL}"
FORM = "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"
OURS_ORIGIN = "https://github.com/Owner/Repo.git"


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """Run git hermetically: no user/system config, no signing, no hooks."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(cwd),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    proc = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
    return proc


def write(root: Path, rel: str, body: str = "print('ok')\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def commit_as_trusted(repo: Path, *rels: str) -> None:
    git(repo, "add", *rels)
    git(repo, "commit", "-q", "-m", "trusted")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")


def launcher(rel: str = LAUNCHED_REL) -> str:
    return f"{gate._render_launcher(rel)} --pull-request {{number}}"


def plain(rel: str = LAUNCHED_REL) -> str:
    return f'{shlex.quote(sys.executable)} "{FORM}/{rel}" --pull-request {{number}}'


def write_config(repo: Path, copilot: str, claude: str = "true") -> str:
    write(
        repo,
        "pr-review-config.yaml",
        yaml.safe_dump(
            {
                "scripts": {
                    "claude_code": {"check_transport": claude},
                    "copilot": {"check_transport": copilot},
                },
                "completion_criteria": [
                    {
                        "name": "Unused",
                        "verification": "command",
                        "command": "true",
                        "pass_when": "stdout-json.ok == true",
                    },
                ],
            },
        ),
    )
    return "pr-review-config.yaml"


def verify(repo: Path, capsys, *extra: str) -> tuple[int, dict, str]:
    rc = gate.main(
        [
            "--config",
            str(repo / "pr-review-config.yaml"),
            "--pull-request",
            "1",
            "--verify-config-only",
            "--json",
            *extra,
        ],
    )
    captured = capsys.readouterr()
    return rc, (json.loads(captured.out) if captured.out else {}), captured.err


def trusted_repo(repo: Path, command: str, *extra_rels: str) -> None:
    """Commit the launched script and a config naming ``command`` as trusted."""
    write(repo, SCRIPT_REL)
    config = write_config(repo, command)
    commit_as_trusted(repo, config, SCRIPT_REL, *extra_rels)


def linked_worktree(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A sibling linked worktree of ``repo`` at HEAD, named as the plugin root."""
    sibling = tmp_path / "sibling"
    git(repo, "worktree", "add", "-q", "--detach", str(sibling), "HEAD")
    monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(sibling / ".claude"))
    return sibling


def sibling_clone(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    origin: str,
) -> Path:
    """A separate clone of ``repo`` whose origin is set to ``origin``."""
    git(repo, "remote", "add", "origin", OURS_ORIGIN)
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(repo), str(clone))
    git(clone, "remote", "set-url", "origin", origin)
    monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(clone / ".claude"))
    return clone


def completed(args: list[str], code: int, stdout: bytes = b"") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["git", *args], code, stdout, b"fatal: probe failed")


def clear_plugin_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset both plugin-root variables so a test sets only what it names."""
    monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)


def make_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This work tree: a real repository with the gate's project root in it."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(gate, "_PROJECT_ROOT", work)
    git(work, "init", "-q")
    monkeypatch.chdir(work)
    return work
