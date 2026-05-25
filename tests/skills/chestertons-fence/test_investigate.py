"""Tests for `.claude/skills/chestertons-fence/scripts/investigate.py`.

Security-critical: locks the M7 `run_git` verb allowlist and transport-
flag denylist that block git argv-level RCE vectors (`--upload-pack=`,
`--exec=`). Without these tests, a future contributor could relax the
allowlist or swap the order of checks and silently re-introduce the
class of bug.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / ".claude" / "skills" / "chestertons-fence" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import investigate  # noqa: E402


# Allowlist enforcement -----------------------------------------------------


@pytest.mark.parametrize(
    "verb",
    ["log", "grep", "show", "diff", "rev-parse", "rev-list", "ls-files", "cat-file"],
)
def test_run_git_accepts_read_only_verbs(verb: str, monkeypatch) -> None:
    """All eight read-only verbs in the allowlist MUST pass validation."""
    captured: dict[str, list[str]] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return type("R", (), {"stdout": "ok\n", "returncode": 0})()

    monkeypatch.setattr(investigate.subprocess, "run", fake_run)
    investigate.run_git([verb])
    assert captured["args"][0] == "git"
    assert captured["args"][1] == verb


@pytest.mark.parametrize(
    "verb",
    ["push", "fetch", "pull", "reset", "rebase", "merge", "clone", "rm", "config"],
)
def test_run_git_rejects_destructive_verbs(verb: str) -> None:
    """Destructive verbs MUST raise ValueError -- the allowlist is the gate."""
    with pytest.raises(ValueError, match="not in allowlist"):
        investigate.run_git([verb])


def test_run_git_rejects_empty_args() -> None:
    with pytest.raises(ValueError, match="not in allowlist"):
        investigate.run_git([])


# Transport-flag denylist ---------------------------------------------------


@pytest.mark.parametrize(
    "flag",
    [
        "--upload-pack=evil",
        "--exec=evil",
        "--upload-pack=/tmp/evil",
        "--exec=$(rm -rf /)",
    ],
)
def test_run_git_rejects_transport_flag_anywhere(flag: str) -> None:
    """`--upload-pack=` and `--exec=` are git's two argv-RCE vectors.

    They must be rejected even when nested mid-args (after the verb).
    """
    with pytest.raises(ValueError, match="forbidden git option"):
        investigate.run_git(["log", flag])


def test_run_git_accepts_safe_flags(monkeypatch) -> None:
    """Non-transport flags MUST pass through unchanged."""
    monkeypatch.setattr(
        investigate.subprocess,
        "run",
        lambda args, **kw: type("R", (), {"stdout": "", "returncode": 0})(),
    )
    investigate.run_git(["log", "--oneline", "-n", "5", "--", "README.md"])


# Allowlist boundary --------------------------------------------------------


def test_run_git_allowlist_is_frozen() -> None:
    """The allowlist constant MUST be immutable (frozenset, not list/set)."""
    assert isinstance(investigate._GIT_FLAG_ALLOWLIST, frozenset)
    # Defense: ensure no destructive verbs slipped in.
    forbidden = {"push", "fetch", "pull", "reset", "rebase", "merge", "clone", "rm"}
    assert forbidden.isdisjoint(investigate._GIT_FLAG_ALLOWLIST)
