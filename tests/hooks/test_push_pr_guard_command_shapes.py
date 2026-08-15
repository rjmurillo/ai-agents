"""Unsafe command shapes and new_pr.py argument policy tests.

Split from the former single ``tests/hooks/test_push_pr_script_identity_guard.py``
(issue #4764), which had grown to 2,077 lines and carried the whole policy
matrix for both harnesses in one module. Dispatcher runners, the payload shape,
and the temporary repository layout live in
``tests/hooks/push_pr_guard_harness.py`` so no module re-derives them.

Issue #5013 retired the guard from the generated Copilot shim tree
(dispatch_groups.json marks it copilotExclude, so the generator omits it).
Every case here now runs through the Claude dispatcher only, which is where
the guard still runs; invoke_dispatch_claude.py does not read
copilotExclude.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.hooks.push_pr_guard_harness import (
    INVALID_REQUESTS,
    PLUGIN_SCRIPT_REFERENCE,
)
from tests.hooks.push_pr_guard_harness import (
    RUNNERS as _RUNNERS,
)
from tests.hooks.push_pr_guard_harness import (
    body_file as _body_file,
)
from tests.hooks.push_pr_guard_harness import (
    repository as _repository,
)
from tests.hooks.push_pr_guard_harness import (
    run_claude as _run_claude,
)
from tests.hooks.push_pr_guard_harness import (
    run_claude_invalid as _run_claude_invalid,
)
from tests.hooks.push_pr_guard_harness import (
    write_script as _write_script,
)

IN_SCOPE_ASSIGNMENT = "PUSH_PR_SCRIPT=new_pr.py "


def _in_scope(command: str) -> str:
    """Return ``command`` placed inside the guard's relevance scope."""
    if "new_pr.py" in command:
        return command
    return IN_SCOPE_ASSIGNMENT + command


@pytest.mark.parametrize("runner", _RUNNERS)
@pytest.mark.parametrize(
    "command",
    [
        "env PUSH_PR_TEST=1 git status --short",
        "git -c color.ui=never status --short",
        "git --no-advice status --short",
        "git --no-optional-locks status --short",
        "git config --get user.name",
        "git config --local --get user.name",
        "git grep -n pattern -- pyproject.toml",
        "git grep -in pattern -- pyproject.toml",
        "git ls-remote https://example.com/repository.git HEAD",
        "git fetch https://example.com/repository.git HEAD",
        "env git push --repo=https://example.com/repository.git HEAD",
        "env git push -o ci.skip https://example.com/repository.git HEAD",
        "env git push --push-option ci.skip https://example.com/repository.git HEAD",
        "git fetch -j 4 https://example.com/repository.git HEAD",
        "git clone -b main https://example.com/repository.git clone",
        "command time -f label git status --short",
        "command nice --adjustment 0 git status --short",
        "command timeout --signal TERM 5 git status --short",
        "command stdbuf --output L git status --short",
        "find . -name pyproject.toml -print",
        "busybox env git status --short",
        "tar -cf archive.tar file",
        "printf '%s\\n' '-S' '--split-string' '-xc'",
        "printf '%s\\n' perl ruby node awk sed make gmake",
        "printf '%s\\n' scala R julia expect bpftrace ghci",
    ],
)
def test_claude_allow_benign_env_and_flag_text(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner(command, repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
@pytest.mark.parametrize(
    "title",
    [
        "{fix,--skip-validation,--audit-reason,attacker-controlled}",
        "attacker*",
        "attacker?",
        "[ab]",
        "~/attacker",
    ],
)
def test_claude_deny_active_expansion_in_new_pr_arguments(
    tmp_path: Path,
    runner,
    title: str,
) -> None:
    repository, _ = _repository(tmp_path)
    body_file = _body_file(repository)

    result = runner(
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --title {title} --body-file {body_file}',
        repository,
    )

    assert result.returncode == 2
    assert "argument shell expansion is not allowed" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_claude_allow_quoted_expansion_text_in_new_pr_title(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    body_file = _body_file(repository)

    result = runner(
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" '
        "--title 'fix: literal {brace} [glob] * ? ~' "
        f"--body-file {body_file}",
        repository,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "python3 attacker/pr/new_pr.py --title fix",
        "python3 pr/new_pr.py --title fix",
        "python3 attacker/pr/new_pr.p? --title fix",
        "python3 -I attacker/pr/new_pr.{py,ignored} --title fix",
        "python3 -I attacker/new_pr{.py,.ignored} --title fix",
        "python3 -I attacker/{new_,old_}pr.py --title fix",
        "python3 -I attacker/{{new_,old_},safe_}pr.py --title fix",
        "python3 -I attacker/{n,x}{e,x}{w,x}_{p,x}{r,x}.{p,x}{y,x}",
        "python3 -I attacker/new_{p..p}r.py",
        "python3 -I attacker/n{e..f}w_pr.py",
        "python3 -I attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}",
        "pypy3 attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}",
        "pypy3 attacker/pr/n[e]w_[p]r.[p][y]",
        'pypy3 "$SCRIPT_PATH"',
        'pypy3 "attacker/pr/$(printf new_pr.py)"',
        "python3 attacker/pr/new_pr'.py' --title fix",
        "python3 -I attacker/pr/new_pr.p$'y'",
        'python3 -I attacker/pr/new_pr.p$"y"',
        "python3 -I attacker/pr/new_pr.p\\\ny",
        'python3 -I "attacker/pr/new_pr\\.py" --title fix',
        "python3 -I attacker/pr/NEW_PR.PY --title fix",
        "python3 -c \"exec(open('attacker/pr/new_pr.py').read())\"",
        "python3 -c\"exec(open('attacker/pr/new_pr.py').read())\"",
        "python3 \"-Icexec(open('attacker/pr/new_pr.py').read())\"",
        "python3 -I -c \"exec(open('attacker/pr/new_'+'pr.py').read())\"",
        'python3 -I -c \'__import__("runpy").run_path('
        'bytes.fromhex("61747461636b65722f70722f6e65775f70722e7079")'
        '.decode(), run_name="__main__")\'',
        "python3 -I -c 'import runpy,sys;runpy.run_path(sys.argv[1])' attacker/pr/new_pr.py",
        "python3 -I -m cProfile attacker/pr/n[e]w_[p]r.[p][y]",
        "python3 -I -m cProfile attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}",
        'python3 -I "attacker/new_$(printf pr).py"',
        'python3 -I "attacker/n$(printf ew_pr).py"',
        "python3 -I attacker/n`printf e`w_pr.py",
        "python3 -I attacker/$SCRIPT_NAME.py",
        "env python3 -I attacker/pr/new_pr.py",
        "env -u HOME python3 -I attacker/pr/new_pr.py",
        "env -u python3 python3 attacker/pr/new_pr.py",
        "env -S 'python3 -I attacker/pr/new_pr.py'",
        "env '-Spython3 -I' attacker/pr/new_pr.py",
        "/usr/bin/python3 -I attacker/pr/new_pr.py",
        "/usr/bin/pytho[n]3 -I attacker/pr/new_pr.py",
        "/usr/bin/pytho{n,xx}3 -I attacker/pr/new_pr.py",
        "python attacker/pr/new_pr.py",
        "python3.14 -I attacker/pr/new_pr.py",
        "pypy3 -I attacker/pr/new_pr.py",
        "py -c \"print('attacker')\"",
        "py -m site",
        "py.exe -c \"print('attacker')\"",
        "python2 -c \"print('attacker')\"",
        "python2.7 -c \"print('attacker')\"",
        "python3.12.1 -c \"print('attacker')\"",
        "pypy2 -c \"print('attacker')\"",
        "pypy3.10 -c \"print('attacker')\"",
        "pypy3.11 -c \"print('attacker')\"",
        "./attacker/pr/new_pr.py",
        "./p attacker/pr/new_pr.py",
        "env timeout 5 ./p attacker/pr/new_pr.py",
        "uv run attacker/n{e..e}w_pr.py",
        "git -c alias.x='!uv run attacker/new_pr.py' x",
        "git grep --open-files-in-pager=attacker/new_pr.py PATTERN",
        "/usr/bin/env PATH=. cat attacker/new_pr.py",
        "exec ./attacker/pr/new_pr.py",
        "exec -a benign ./attacker/pr/new_pr.py",
        "X=1 python3 -I attacker/pr/new_pr.py",
        "PY=python3 $PY -I attacker/pr/new_pr.py",
        "PYTHONSTARTUP=attacker/pr/new_pr.py python3 -i",
        "command -- python3 -I attacker/pr/new_pr.py",
        "command -- python attacker/pr/new_pr.py",
        "command -- ${BASH_VERSION:+pyt}hon3 attacker/pr/new_pr.py",
        "${BASH_VERSION:+pyt}hon3 attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}",
        "pyt$'hon3' attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}",
        "time python3 attacker/pr/new_pr.p{y..y}",
        "setsid python3 attacker/pr/new_pr.p[y]",
        "time pypy3 attacker/pr/new_pr.{p..p}y",
        "time python3 -c \"print('attacker')\"",
        "setsid python3 -c \"print('attacker')\"",
        "bash -c 'python3 -I attacker/pr/new_pr.py'",
        "bash -c 'python3 -c \"print(1)\"'",
        "bash -c '${BASH_VERSION:+pyt}hon3 attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}'",
        "sh -c 'pypy3 attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}'",
        "eval 'pypy3 attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}'",
        "python3 -I -X dev attacker/pr/new_pr.py",
        "python3 -IW ignore attacker/pr/new_pr.py",
        f"python3 -I '{PLUGIN_SCRIPT_REFERENCE}' --title fix",
        "python3 -u .claude/skills/github/scripts/pr/new_pr.py --title fix",
        "python3 .claude/skills/github/scripts/pr/new_pr.py; echo bypass",
        "python3 .claude/skills/github/scripts/pr/new_pr.py && echo bypass",
        "python3 .claude/skills/github/scripts/pr/new_pr.py | cat",
        "python3 .claude/skills/github/scripts/pr/new_pr.py > result.txt",
        "python3 .claude/skills/github/scripts/pr/new_pr.py $(echo bypass)",
        "python3 .claude/skills/github/scripts/pr/new_pr.py `echo bypass`",
        'git status "$(pyt{h..h}on3 attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y})"',
        "python3 .claude/skills/github/scripts/pr/new_pr.py --title '$HOME'",
        "python3 .claude/skills/github/scripts/pr/new_pr.py # comment",
        "python3 .claude/skills/github/scripts/pr/new_pr.py\npython3 attacker.py",
    ],
)
@pytest.mark.parametrize("runner", _RUNNERS)
def test_claude_deny_unsafe_command_shapes(
    tmp_path: Path,
    command: str,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    _write_script(repository / "attacker" / "pr" / "new_pr.py")
    _write_script(repository / "attacker.py")

    result = runner(_in_scope(command), repository)

    assert result.returncode == 2
    assert "push-pr script identity denied" in result.stderr


@pytest.mark.parametrize("request_id", sorted(INVALID_REQUESTS))
def test_claude_fails_closed_on_invalid_hook_input(
    tmp_path: Path,
    request_id: str,
) -> None:
    repository, _ = _repository(tmp_path)

    result = _run_claude_invalid(request_id, repository)

    assert result.returncode == 2


def test_claude_allows_nonmatching_bash_when_group_is_called(
    tmp_path: Path,
) -> None:
    repository, _ = _repository(tmp_path)

    result = _run_claude("git status --short", repository)

    assert result.returncode == 0, result.stderr

