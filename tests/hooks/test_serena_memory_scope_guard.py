"""Tests for invoke_serena_memory_scope_guard (issue #5061).

Covers: allow when the caller's worktree is the checkout Serena writes to,
allow for every non-memory tool (including the read-only memory tools and the
symbol editors that issue #4917 owns), block from a real external git worktree
for both harness tool namings, block when the session root cannot be resolved,
allow when the caller is outside any git repo, the SERENA_PROJECT_ROOT
override, payload edge cases, and the settings.json registration.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_DIR = REPO_ROOT / ".claude" / "hooks" / "PreToolUse"
HOOK_PATH = HOOK_DIR / "invoke_serena_memory_scope_guard.py"
sys.path.insert(0, str(HOOK_DIR))

import invoke_serena_memory_scope_guard as guard

ALLOW = 0
BLOCK = 2


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def main_checkout(tmp_path: Path) -> Path:
    """A real git repository standing in for the session's main checkout."""
    root = tmp_path / "main"
    root.mkdir()
    _git("init", "-b", "main", cwd=root)
    _git("config", "user.email", "test@example.invalid", cwd=root)
    _git("config", "user.name", "Test", cwd=root)
    (root / ".serena" / "memories").mkdir(parents=True)
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    _git("add", "-A", cwd=root)
    _git("commit", "-m", "seed", cwd=root)
    return root.resolve()


@pytest.fixture
def external_worktree(main_checkout: Path, tmp_path: Path) -> Path:
    """An external worktree of *main_checkout*, as an isolated subagent gets."""
    target = tmp_path / "worktrees" / "agent"
    _git("worktree", "add", "-b", "agent", str(target), "main", cwd=main_checkout)
    return target.resolve()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("SERENA_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)


class _FakeStdin(io.StringIO):
    """A stdin stand-in whose tty answer the test chooses."""

    def __init__(self, raw: str, *, tty: bool = False) -> None:
        super().__init__(raw)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def _run_in_process(monkeypatch, payload: dict, stdin_text: str | None = None) -> int:
    """Invoke ``guard.main()`` with *payload* piped through a fake stdin."""
    raw = stdin_text if stdin_text is not None else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", _FakeStdin(raw))
    return guard.main()


# --- Positive: the guard stays out of the way -------------------------------


def test_allows_write_memory_when_caller_is_the_serena_checkout(monkeypatch, main_checkout):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    exit_code = _run_in_process(
        monkeypatch,
        {"tool_name": "mcp__serena__write_memory", "cwd": str(main_checkout)},
    )
    assert exit_code == ALLOW


def test_allows_from_subdirectory_of_the_serena_checkout(monkeypatch, main_checkout):
    subdir = main_checkout / "docs"
    subdir.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    exit_code = _run_in_process(
        monkeypatch,
        {"tool_name": "mcp__serena__write_memory", "cwd": str(subdir)},
    )
    assert exit_code == ALLOW


@pytest.mark.parametrize(
    "tool_name",
    [
        "mcp__serena__read_memory",
        "mcp__serena__list_memories",
        "serena-read_memory",
        "mcp__serena__replace_content",
        "serena-replace_content",
        "Write",
        "",
    ],
)
def test_allows_every_tool_outside_the_memory_mutation_set(
    monkeypatch, main_checkout, external_worktree, tool_name
):
    """The guard must not fire on read tools or on issue #4917's editors."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    exit_code = _run_in_process(
        monkeypatch,
        {"tool_name": tool_name, "cwd": str(external_worktree)},
    )
    assert exit_code == ALLOW


def test_allows_when_override_names_the_callers_worktree(
    monkeypatch, main_checkout, external_worktree
):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    monkeypatch.setenv("SERENA_PROJECT_ROOT", str(external_worktree))
    exit_code = _run_in_process(
        monkeypatch,
        {"tool_name": "mcp__serena__write_memory", "cwd": str(external_worktree)},
    )
    assert exit_code == ALLOW


def test_allows_when_caller_is_outside_any_git_repository(monkeypatch, main_checkout, tmp_path):
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    exit_code = _run_in_process(
        monkeypatch,
        {"tool_name": "mcp__serena__write_memory", "cwd": str(outside)},
    )
    assert exit_code == ALLOW


# --- Negative: the guard blocks the #5061 stray write -----------------------


@pytest.mark.parametrize(
    "tool_name",
    [
        "mcp__serena__write_memory",
        "mcp__serena__delete_memory",
        "serena-write_memory",
        "serena-delete_memory",
    ],
)
def test_blocks_memory_mutation_from_an_external_worktree(
    monkeypatch, capsys, main_checkout, external_worktree, tool_name
):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    exit_code = _run_in_process(
        monkeypatch,
        {"tool_name": tool_name, "cwd": str(external_worktree)},
    )
    assert exit_code == BLOCK
    stderr = capsys.readouterr().err
    assert "#5061" in stderr
    assert str(external_worktree) in stderr
    assert str(main_checkout) in stderr
    assert "SERENA_PROJECT_ROOT" in stderr


def test_block_message_names_the_in_worktree_write_path(
    monkeypatch, capsys, main_checkout, external_worktree
):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    _run_in_process(
        monkeypatch,
        {"tool_name": "mcp__serena__write_memory", "cwd": str(external_worktree)},
    )
    stderr = capsys.readouterr().err
    assert str(external_worktree / ".serena" / "memories") in stderr


def test_blocks_when_session_root_is_unset(monkeypatch, capsys, external_worktree):
    """Fail closed: an unresolvable session root cannot rule out a stray write."""
    exit_code = _run_in_process(
        monkeypatch,
        {"tool_name": "mcp__serena__write_memory", "cwd": str(external_worktree)},
    )
    assert exit_code == BLOCK
    assert "cannot determine" in capsys.readouterr().err


def test_blocks_when_session_root_points_at_a_missing_directory(
    monkeypatch, tmp_path, external_worktree
):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "gone"))
    exit_code = _run_in_process(
        monkeypatch,
        {"tool_name": "mcp__serena__write_memory", "cwd": str(external_worktree)},
    )
    assert exit_code == BLOCK


def test_override_pointing_elsewhere_still_blocks(monkeypatch, main_checkout, external_worktree):
    monkeypatch.setenv("SERENA_PROJECT_ROOT", str(main_checkout))
    exit_code = _run_in_process(
        monkeypatch,
        {"tool_name": "mcp__serena__write_memory", "cwd": str(external_worktree)},
    )
    assert exit_code == BLOCK


def test_blocks_when_git_cannot_be_launched_for_the_callers_worktree(
    monkeypatch, capsys, main_checkout, external_worktree
):
    """A launch failure is not a confirmed "outside any worktree" answer."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    monkeypatch.setattr(
        guard.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("git not found"))
    )
    exit_code = _run_in_process(
        monkeypatch,
        {"tool_name": "mcp__serena__write_memory", "cwd": str(external_worktree)},
    )
    assert exit_code == BLOCK
    stderr = capsys.readouterr().err
    assert "could not determine your git worktree" in stderr
    assert "#5061" in stderr


def test_blocks_when_git_times_out_for_the_callers_worktree(
    monkeypatch, capsys, main_checkout, external_worktree
):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["git", "rev-parse"], timeout=guard._GIT_TIMEOUT_SECONDS
        )

    monkeypatch.setattr(guard.subprocess, "run", _timeout)
    exit_code = _run_in_process(
        monkeypatch,
        {"tool_name": "mcp__serena__write_memory", "cwd": str(external_worktree)},
    )
    assert exit_code == BLOCK
    assert "could not determine your git worktree" in capsys.readouterr().err


def test_blocks_when_git_succeeds_with_no_usable_output(
    monkeypatch, capsys, main_checkout, external_worktree
):
    """returncode 0 with blank stdout is unusable, not a confirmed non-repo answer."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    blank = subprocess.CompletedProcess(args=["git"], returncode=0, stdout="   \n", stderr="")
    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: blank)
    exit_code = _run_in_process(
        monkeypatch,
        {"tool_name": "mcp__serena__write_memory", "cwd": str(external_worktree)},
    )
    assert exit_code == BLOCK
    assert "could not determine your git worktree" in capsys.readouterr().err


# --- Edge: payload shapes ---------------------------------------------------


def test_camel_case_tool_name_is_recognized(monkeypatch, main_checkout, external_worktree):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    exit_code = _run_in_process(
        monkeypatch,
        {"toolName": "serena-write_memory", "cwd": str(external_worktree)},
    )
    assert exit_code == BLOCK


@pytest.mark.parametrize("raw", ["", "   ", "not json", "[1, 2]", '"a string"'])
def test_unusable_stdin_allows(monkeypatch, main_checkout, raw):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    assert _run_in_process(monkeypatch, {}, stdin_text=raw) == ALLOW


def test_oversized_stdin_blocks(monkeypatch, capsys, main_checkout):
    """Fail closed: an oversized payload cannot be confirmed unrelated to a write."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    oversized = json.dumps(
        {
            "tool_name": "mcp__serena__write_memory",
            "pad": "x" * (guard._MAX_STDIN_BYTES + 64),
        }
    )
    exit_code = _run_in_process(monkeypatch, {}, stdin_text=oversized)
    assert exit_code == BLOCK
    stderr = capsys.readouterr().err
    assert "cannot verify Serena memory scope" in stderr
    assert "#5061" in stderr


def test_stdin_at_the_size_limit_is_not_treated_as_oversized(monkeypatch, main_checkout):
    """The boundary itself must still parse; only bytes past it fail closed."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    body = {"tool_name": "mcp__serena__write_memory", "cwd": str(main_checkout), "pad": ""}
    overhead = len(json.dumps(body).encode("utf-8"))
    pad_len = guard._MAX_STDIN_BYTES - overhead
    assert pad_len >= 0
    body["pad"] = "x" * pad_len
    at_limit = json.dumps(body)
    assert len(at_limit.encode("utf-8")) == guard._MAX_STDIN_BYTES
    assert _run_in_process(monkeypatch, {}, stdin_text=at_limit) == ALLOW


def test_non_string_tool_name_allows(monkeypatch, main_checkout, external_worktree):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    exit_code = _run_in_process(
        monkeypatch,
        {"tool_name": 42, "cwd": str(external_worktree)},
    )
    assert exit_code == ALLOW


def test_missing_cwd_falls_back_to_process_cwd(monkeypatch, main_checkout):
    monkeypatch.chdir(main_checkout)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    exit_code = _run_in_process(monkeypatch, {"tool_name": "mcp__serena__write_memory"})
    assert exit_code == ALLOW


def test_relative_cwd_is_resolved_against_the_process_cwd(
    monkeypatch, main_checkout, external_worktree
):
    monkeypatch.chdir(external_worktree.parent)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    exit_code = _run_in_process(
        monkeypatch,
        {"tool_name": "mcp__serena__write_memory", "cwd": external_worktree.name},
    )
    assert exit_code == BLOCK


def test_tty_stdin_allows(monkeypatch, main_checkout):
    monkeypatch.setattr(sys, "stdin", _FakeStdin("", tty=True))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main_checkout))
    assert guard.main() == ALLOW


# --- Subprocess and registration -------------------------------------------


def test_subprocess_exit_code_matches_in_process(main_checkout, external_worktree):
    """The real process boundary, not just the imported function."""
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(
            {
                "tool_name": "mcp__serena__write_memory",
                "cwd": str(external_worktree),
            }
        ),
        capture_output=True,
        text=True,
        env={
            "PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin",
            "CLAUDE_PROJECT_DIR": str(main_checkout),
            "HOME": str(main_checkout),
        },
        check=False,
    )
    assert result.returncode == BLOCK
    assert "#5061" in result.stderr


def test_hook_is_registered_on_the_plugin_surface():
    """ADR-085: PreToolUse gates register in hooks.json, never settings.json."""
    groups = json.loads(
        (REPO_ROOT / ".claude" / "hooks" / "dispatch_groups.json").read_text(encoding="utf-8")
    )["groups"]
    group = groups["plugin-pretooluse-11-serena_memory_scope"]
    assert group["event"] == "PreToolUse"
    assert group["mode"] == "gate"
    assert group["surface"] == "plugin"
    assert "mcp__serena__" in group["matcher"]
    assert "serena-" in group["matcher"]
    assert group["shims"][0]["file"] == "PreToolUse/invoke_serena_memory_scope_guard.py"

    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "PreToolUse" not in settings["hooks"]

    registered = json.dumps(
        json.loads((REPO_ROOT / ".claude" / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    )
    assert "plugin-pretooluse-11-serena_memory_scope" in registered


def test_matcher_is_anchored_on_every_registration_surface():
    """A bare-substring matcher fires on any tool name containing it, not just
    the four memory-mutation tools; classify_matcher() in
    generate_hooks_shim.py additionally treats an unanchored pattern as a
    literal-string comparison, so an unanchored ``serena-write_memory`` never
    matches a real tool name at all on the Copilot surface (issue #5061)."""
    dispatch_groups = json.loads(
        (REPO_ROOT / ".claude" / "hooks" / "dispatch_groups.json").read_text(encoding="utf-8")
    )
    group = dispatch_groups["groups"]["plugin-pretooluse-11-serena_memory_scope"]
    assert group["matcher"].startswith("^") and group["matcher"].endswith("$")
    assert group["shims"][0]["copilotMatcher"].startswith("^")
    assert group["shims"][0]["copilotMatcher"].endswith("$")

    hooks_json = json.loads(
        (REPO_ROOT / ".claude" / "hooks" / "hooks.json").read_text(encoding="utf-8")
    )
    matchers = [
        entry.get("matcher", "")
        for entries in hooks_json.get("hooks", {}).values()
        for entry in entries
        if "plugin-pretooluse-11-serena_memory_scope" in json.dumps(entry)
    ]
    assert matchers, "expected the guard's group entry in hooks.json"
    for matcher in matchers:
        assert matcher.startswith("^") and matcher.endswith("$"), matcher
