"""Shared helpers for the sol-loop command tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/sol-loop/scripts/sol_loop.py", module_name="sol_loop_under_test"
)

CRITIC_TEXT = (
    "## Critical Findings\n1. `src/app/a.py:10` drops the error.\n\nVerdict: NEEDS_REVISION\n"
)
SOL = "gpt-6.1-sol"
REPLY = (
    "VERDICT: CHANGES\n"
    "S1 [should] src/app/a.py:12 swallows the error. "
    "Repro: call f(None) and no error is raised. Fix: re-raise.\n"
    "S2 [blocker] src/app/b.py:5 KeyError on empty input. "
    "Repro: pytest tests/test_b.py::test_empty. Fix: guard.\n"
    "S3 [nit] src/app/b.py:9 rename x. Repro: n/a. Fix: rename.\n"
    "S4 [should] src/app/c.py:3 wrong default. Fix: use 0.\n"
)


def _reply(tmp_path, text=REPLY):
    path = tmp_path / "reply.txt"
    path.write_text(text, encoding="utf-8")
    return path


def _argv(command, tmp_path, critic, *extra, author="anthropic", repo=None):
    return [
        command,
        "--repo",
        str(repo or tmp_path),
        "--log-base",
        str(tmp_path),
        "--critic-findings",
        str(critic),
        "--model",
        SOL,
        "--author-family",
        author,
        *extra,
    ]


def _gate(tmp_path, critic, *extra, **kw):
    return mod.main(_argv("gate", tmp_path, critic, "--route", "t3", *extra, **kw))


def _record(tmp_path, critic, reply, *extra, **kw):
    return mod.main(_argv("record", tmp_path, critic, "--reply", str(reply), *extra, **kw))


def _log_dir(tmp_path):
    return tmp_path / ".project-toolkit" / "metrics" / "sol-loop"


def _logs(tmp_path):
    return [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(_log_dir(tmp_path).glob("*.json"))
    ]


def _out(capsys):
    return json.loads(capsys.readouterr().out)


def _git_repo(path: Path) -> None:
    path.mkdir()
    identity = ["-c", "user.name=Test", "-c", "user.email=test@example.com"]
    for args in (["init", "-q"], [*identity, "commit", "-q", "--allow-empty", "-m", "init"]):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)


def _touch_after_head(path: Path) -> None:
    """Set mtime past HEAD's whole-second commit time, so the order is certain."""
    later = time.time() + 5
    os.utime(path, (later, later))
