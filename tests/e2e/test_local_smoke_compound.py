"""Compound command lines and the refusal type of the local Copilot smoke guard (issue #6506)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_smoke_command as command
import local_smoke_guard as guard


@pytest.mark.parametrize(
    "args",
    [
        "echo hi; copilot",
        "true && copilot --help",
        "false || copilot",
        "echo x | copilot",
        "(copilot)",
        "echo $(copilot --version)",
        "echo `copilot`",
        "sleep 1 & copilot",
        "echo a\ncopilot",
        "cd x;FOO=1 copilot",
        "echo ok;env FOO=1 copilot -p hi",
        r"echo hi & C:\npm\copilot.cmd --version",
        r"echo hi && C:\npm\copilot.cmd",
        ["sh", "-c", "echo hi; copilot"],
        "bash -c 'echo hi && copilot'",
        ["pwsh", "-Command", "echo hi; copilot"],
        "sh -c 'ls | copilot'",
        'out="$(copilot --version)"',
        'echo "$(copilot --version)"',
        'echo "`copilot`"',
        'echo "x $(echo $(copilot))"',
        "time copilot",
        "time -p copilot -p hi",
        "timeout 5 copilot",
        "timeout -s KILL 5 copilot",
        "timeout --kill-after=1 5 copilot",
        "nice -n 5 copilot",
        "xargs copilot",
        "echo x | xargs -n 1 copilot",
        "echo x | xargs -I{} copilot {}",
        "stdbuf -oL copilot",
        "setsid copilot",
        "if true; then copilot; fi",
        "while true; do copilot; done",
        "! copilot",
        "{ copilot; }",
        "case x in x) copilot;; esac",
    ],
)
def test_refuses_copilot_anywhere_in_a_compound_command(args: object) -> None:
    with pytest.raises(guard.CopilotCallRefusedError, match="requires_copilot"):
        guard.refuse_copilot(args)


@pytest.mark.parametrize(
    "args",
    [
        "echo copilot; ls",
        "ls | grep copilot",
        "echo 'a; copilot'",
        'echo "x && copilot"',
        "claude -p hi && codex exec",
        "cd copilot && ls",
        "git status | head",
        ["sh", "-c", "echo hi; ls"],
        "bash -c 'echo hi && ls'",
        "echo $(date)",
        "echo hi >out.txt; cat out.txt",
        "a;;b",
        ";",
        "&&",
        "timeout 5 claude",
        "time ls",
        "xargs -n 1 echo copilot",
        "if true; then claude; fi",
        "echo time copilot",
        'echo "$(date)"',
        "echo 'copilot' | cat",
        "nice -n 5 codex",
    ],
)
def test_allows_a_compound_command_that_never_starts_copilot(args: object) -> None:
    guard.refuse_copilot(args)


def test_program_names_lists_every_program_in_order() -> None:
    assert command.program_names("a; b | env X=1 c && sh -c 'd; e'") == ["a", "b", "c", "d", "e"]


def test_program_name_keeps_returning_the_first_program() -> None:
    assert command.program_name("echo hi; copilot") == "echo"
    assert command.program_name("") == ""
    assert command.program_name(["command", "-v", "copilot"]) == ""


def test_an_unbalanced_quote_still_finds_copilot_after_an_operator() -> None:
    """Edge: shlex rejects the line, so the fallback splitter must still see the second command."""
    with pytest.raises(guard.CopilotCallRefusedError):
        guard.refuse_copilot("echo 'oops; copilot")


def test_the_refusal_is_not_an_exception() -> None:
    """A broad ``except Exception`` in the code under test must not swallow it."""
    assert not issubclass(guard.CopilotCallRefusedError, Exception)
    assert issubclass(guard.CopilotCallRefusedError, BaseException)

    def swallow() -> str:
        try:
            guard.refuse_copilot(["copilot"])
        except Exception:
            return "swallowed"
        return "not reached"

    with pytest.raises(guard.CopilotCallRefusedError):
        swallow()
