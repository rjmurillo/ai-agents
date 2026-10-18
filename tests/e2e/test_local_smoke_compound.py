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
        "sh -lc 'copilot -p x'",
        "bash -xc copilot",
        "bash -ec 'echo hi; copilot'",
        ["zsh", "-ic", "copilot"],
        "> /dev/null copilot -p x",
        "</dev/null copilot",
        "2>/dev/null copilot",
        "2> /dev/null copilot",
        ">>log.txt copilot",
        "&>/dev/null copilot",
        "exec 3>&1 copilot",
        "<<< hi copilot",
        "> /dev/null env FOO=1 copilot",
        r"> NUL C:\npm\copilot.cmd",
        "diff <(copilot -p x) file",
        "diff >(copilot) file",
        "bash -c 'diff <(copilot -p x) f'",
        "watch copilot",
        "watch -n 5 copilot",
        "watch 'copilot -p x'",
        "busybox sh -c copilot",
        "busybox copilot",
        "bash -c -x copilot",
        "bash -c -- copilot",
        "sh -ec -- copilot",
        "bash -c +e -o pipefail 'echo hi; copilot'",
        ["bash", "-c", "-x", "copilot"],
        "true;>/dev/null copilot",
        "true&&>x copilot",
        "true;<in copilot",
        "true;2>/dev/null copilot",
        "(true)>x copilot",
        "true;&>x copilot",
        "function f { copilot; }",
        "function f() { copilot; }",
        "function f { echo hi; }; f; copilot",
        "env -S 'copilot -p x'",
        "env -S'copilot -p x'",
        "env --split-string='copilot -p x'",
        "env --split-string 'FOO=1 copilot'",
        "env -i -S 'echo hi; copilot'",
        "fish -c copilot",
        "ash -c 'echo hi; copilot'",
        ["mksh", "-c", "copilot"],
        r'"C:\Program Files\copilot.exe" -p x',
        r'"C:\Program Files (x86)\copilot.exe" --version',
        r'echo hi & "C:\Program Files (x86)\copilot.cmd"',
        "env -S 'A=1' copilot",
        "env -S '-i' copilot -p x",
        "env -S nice copilot",
        "env --split-string='-i' copilot",
        "env --split-string A=1 copilot",
        ["env", "-S", "A=1", "copilot"],
        "env -iS 'copilot -p x'",
        "env -vS'copilot -p x'",
        "env -i -S 'A=1' env -S 'B=2' copilot",
        "fish --command copilot",
        "fish --command=copilot",
        "fish --command='copilot -p x'",
        "fish -c 'true; and copilot'",
        "fish -c 'not copilot'",
        "fish -c 'echo hi; or copilot'",
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
        "sh -lc 'echo hi'",
        "bash -xc 'ls | cat'",
        "bash --login -c 'echo hi'",
        "bash -x script.sh",
        "echo hi > copilot",
        "echo hi 2>&1 | cat",
        "ls <(date) >out",
        "echo 'x <(copilot)'",
        "watch -n 5 date",
        "watch 'date -u'",
        "busybox sh -c 'echo hi'",
        "2>/dev/null echo copilot",
        "true&>x copilot",
        "bash -c -x 'echo copilot'",
        "bash -c -- 'ls copilot'",
        "bash -c -x",
        "bash -c --",
        "true;>/dev/null ls copilot",
        "function f { echo copilot; }",
        "function copilot { echo hi; }",
        "env -S 'echo copilot'",
        "env --split-string='ls copilot'",
        "env -S",
        "fish -c 'echo copilot'",
        r'"C:\Program Files\node.exe" copilot.js',
        r'"C:\Program Files (x86)\tool.exe" -p "a;copilot"',
        "env -S 'A=1' ls copilot",
        "env -iS 'echo copilot'",
        "env -S nice echo copilot",
        "fish --command 'echo copilot'",
        "fish --command='echo copilot'",
        "fish -c 'not echo copilot'",
    ],
)
def test_allows_a_compound_command_that_never_starts_copilot(args: object) -> None:
    guard.refuse_copilot(args)


def test_program_names_lists_every_program_in_order() -> None:
    assert command.program_names("a; b | env X=1 c && sh -c 'd; e'") == ["a", "b", "c", "d", "e"]


def test_program_names_sees_through_a_redirect_a_cluster_and_a_substitution() -> None:
    assert command.program_names("2>/dev/null sh -lc 'a; b'") == ["a", "b"]
    assert command.program_names("diff <(a) <(b)") == ["diff", "a", "b"]
    assert command.program_names("exec 3>&1 env X=1 c") == ["c"]


def test_program_names_reads_the_command_after_shell_options() -> None:
    assert command.program_names("bash -c -x copilot") == ["copilot"]
    assert command.program_names("sh -ec -- 'a; b'") == ["a", "b"]
    assert command.program_names("bash -c -o pipefail a") == ["a"]
    # Edge: no command line follows the options, so only the shell starts.
    assert command.program_names("bash -c -x") == ["bash"]
    assert command.program_names("bash -c --") == ["bash"]
    # A non-POSIX shell still takes the next word.
    assert command.program_names("cmd /c copilot") == ["copilot"]


def test_program_names_splits_an_operator_fused_to_a_redirection() -> None:
    assert command.program_names("true;>/dev/null copilot") == ["true", "copilot"]
    assert command.program_names("true&&>x copilot") == ["true", "copilot"]
    assert command.program_names("true;<in copilot") == ["true", "copilot"]
    # `&>` is a redirection, so copilot stays an argument of `true`.
    assert command.program_names("true&>x copilot") == ["true"]


def test_program_names_reads_a_function_body_and_an_env_split_string() -> None:
    assert command.program_names("function f { a; }") == ["a"]
    assert command.program_names("function f() { a; }") == ["a"]
    assert command.program_names("env -S 'a -x' ") == ["a"]
    assert command.program_names("env --split-string=b") == ["b"]
    # Edge: an option with no command line after it starts nothing.
    assert command.program_names("env -S") == []


def test_program_names_keeps_a_quoted_windows_path_whole() -> None:
    assert command.program_names(r'"C:\Program Files\a b\tool.exe" -p x') == ["tool.exe"]
    assert command.program_names(r'"C:\Program Files (x86)\t.exe" & dir') == ["t.exe", "dir"]
    # A quoted operator character is data, not an operator.
    assert command.program_names(r'echo "a;b" & c') == ["echo", "c"]
    # Edge: an unbalanced quote still yields the commands around it.
    assert command.program_names(r'echo "oops & copilot') == ["echo", "copilot"]


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
