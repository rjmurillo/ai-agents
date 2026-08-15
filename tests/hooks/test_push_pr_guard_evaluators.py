"""Shell and dynamic evaluator, wrapper, and loader-environment tests.

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

import shutil
import sys
from pathlib import Path

import pytest

from tests.hooks.push_pr_guard_harness import (
    CLAUDE_PLUGIN_ROOT,
)
from tests.hooks.push_pr_guard_harness import (
    RUNNERS as _RUNNERS,
)
from tests.hooks.push_pr_guard_harness import (
    environment as _environment,
)
from tests.hooks.push_pr_guard_harness import (
    repository as _repository,
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
        "env -S 'python3 -I attacker/x'",
        "env --split-string='python3 -I attacker/x'",
        "env '-Spython3 -I attacker/x'",
        "env -iS 'python3 -I attacker/x'",
        "env --split='python3 -I attacker/x'",
        "env --spl='python3 -I attacker/x'",
        "command -- env -S 'python3 -I attacker/x'",
        "timeout 5 env --split-string 'python3 -I attacker/x'",
    ],
)
def test_dispatchers_deny_env_split_string_launchers(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner(_in_scope(command), repository)

    assert result.returncode == 2
    assert "env split-string launchers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
@pytest.mark.parametrize(
    "command",
    [
        "sh -xc 'python3 attacker/x'",
        "/bin/sh -ec 'python3 attacker/x'",
        "bash -lc 'python3 attacker/x'",
        "rbash -c 'python3 attacker/x'",
        "rksh -c 'python3 attacker/x'",
        "rzsh -c 'python3 attacker/x'",
        "mksh -c 'python3 attacker/x'",
        "yash -c 'python3 attacker/x'",
        "xonsh -c 'python3 attacker/x'",
        "ksh93 -c 'python3 attacker/x'",
        "ksh93u -c 'python3 attacker/x'",
        "ksh2020 -c 'python3 attacker/x'",
        "env sh -xc 'python3 attacker/x'",
        "command -- sh -xc 'python3 attacker/x'",
        "timeout 5 sh -xc 'python3 attacker/x'",
        "setsid sh -lc 'python3 attacker/x'",
        "busybox sh -xc 'python3 attacker/x'",
        "setsid busybox ash -xc 'python3 attacker/x'",
    ],
)
def test_dispatchers_deny_shell_evaluator_wrappers(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner(_in_scope(command), repository)

    assert result.returncode == 2
    assert "shell evaluator wrappers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_deny_renamed_shell_executables(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash unavailable")
    interpreter_directory = repository / "attacker-bin"
    interpreter_directory.mkdir()
    versioned_shell = interpreter_directory / "bash-5.2"
    copied_shell = repository / "copied-shell"
    try:
        versioned_shell.symlink_to(bash)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    shutil.copy2(bash, copied_shell)
    copied_shell.chmod(0o755)

    commands = (
        f"PATH='{interpreter_directory}' bash-5.2 -c 'id'",
        "./copied-shell -c 'id'",
    )
    for command in commands:
        result = runner(_in_scope(command), repository)
        assert result.returncode == 2, command
        assert "shell evaluator wrappers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_deny_executable_renamed_to_printf(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    renamed = repository / "printf"
    shutil.copy2(sys.executable, renamed)
    renamed.chmod(0o755)

    copied_result = runner(_in_scope("./printf -c \"print('attacker')\""), repository)
    renamed.write_text("#!/bin/sh\nid\n", encoding="utf-8")
    renamed.chmod(0o755)
    script_result = runner(_in_scope("./printf"), repository)

    assert copied_result.returncode == 2
    assert "dynamic evaluator wrappers are not allowed" in copied_result.stderr
    assert script_result.returncode == 2
    assert "shell evaluator wrappers are not allowed" in script_result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_deny_home_relative_shell_wrapper(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    home = tmp_path / "home"
    wrapper = home / "bin" / "update"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("#!/bin/sh\nid\n", encoding="utf-8")
    wrapper.chmod(0o755)
    # RUNNERS is Claude-only since issue #5013 (the guard's Copilot shim was
    # retired), so the plugin-root environment is always the Claude one.
    plugin_environment = {"CLAUDE_PLUGIN_ROOT": str(CLAUDE_PLUGIN_ROOT)}

    result = runner(
        _in_scope("~/bin/update"),
        repository,
        env=_environment(HOME=str(home), **plugin_environment),
    )

    assert result.returncode == 2
    assert "shell evaluator wrappers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatchers_deny_env_assignments_after_option_terminator(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    wrapper = repository / "attacker"
    wrapper.write_text("#!/bin/sh\nid\n", encoding="utf-8")
    wrapper.chmod(0o755)

    result = runner(_in_scope("env -- X=1 ./attacker"), repository)

    assert result.returncode == 2
    assert "shell evaluator wrappers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
@pytest.mark.parametrize(
    "command",
    [
        "awk 'BEGIN { system(\"python3 -I attacker/pr/new_pr.py\") }'",
        "lua -e 'os.execute(\"python3 -I attacker/pr/new_pr.py\")'",
        'node -e \'require("child_process").execSync("python3 -I x")\'',
        "perl -e 'exec q(python3),q(-I),pack(q(H42),"
        "q(61747461636b65722f70722f6e65775f70722e7079))'",
        "php -r 'system(\"python3 -I attacker/pr/new_pr.py\");'",
        'ruby -e \'exec("python3", "-I", "attacker/pr/new_pr.py")\'',
        "sed -n '1e python3 -I attacker/pr/new_pr.py'",
        'strace node -e \'require("child_process").execSync("./p")\'',
        "sudo perl -e 'system(\"./p\")'",
        "valgrind ruby -e 'system(\"./p\")'",
        'ltrace node -e \'require("child_process").execSync("./p")\'',
        'perf stat node -e \'require("child_process").execSync("./p")\'',
        'numactl node -e \'require("child_process").execSync("./p")\'',
        'runuser -u nobody -- node -e \'require("child_process").execSync("./p")\'',
        "scala -e 'sys.process.Process(\"./p\").!'",
        "R -e 'system(\"./p\")'",
        "julia -e 'run(`./p`)'",
        "expect -c 'exec ./p'",
        "bpftrace -e 'BEGIN { system(\"./p\") }'",
        "ghci -e 'System.Process.callCommand \"./p\"'",
        "nawk -f attacker.awk input",
        "dc attacker.dc",
        "sqlite3 :memory: '.shell ./p'",
        "guile -c '(system \"./p\")'",
        "elixir -e 'System.cmd(\"./p\", [])'",
        'ts-node -e \'require("child_process").execSync("./p")\'',
        'tsx -e \'require("child_process").execSync("./p")\'',
        "emacs --batch --eval '(shell-command \"./p\")'",
        "vim -es -c '!./p' -c qa",
        "psql -c '\\! ./p'",
        "gdb -ex 'shell python3 -I attacker/pr/new_pr.py' --batch",
        "lldb -o 'platform shell python3 -I attacker/pr/new_pr.py' --batch",
        "make -f attacker.mk",
        "gmake -f attacker.mk",
        "script -q -c 'python3 -I attacker/pr/new_pr.py' /dev/null",
        "nsenter --target 1 --mount python3 -I attacker/pr/new_pr.py",
        "ssh -F /dev/null -o ProxyCommand='./p' localhost true",
        "scp -o ProxyCommand='./p' source localhost:target",
        "sftp -o ProxyCommand='./p' localhost",
        "rsync --rsh='./p' localhost:/source target",
        "sshpass -p secret ssh localhost true",
        "su -c './p'",
        "sudo sh -c './p'",
        "runuser -c './p'",
        "parallel './p' ::: x",
        "socat EXEC:'./p' STDIO",
        "ncat --sh-exec './p' localhost 1",
        "env -- X=1 sudo id",
        "env -- 1abc=x sudo id",
        "env a.b=1 ssh localhost true",
        "git -c alias.x='!./p' x",
        "git -calias.x='!./p' x",
        "git -c core.sshCommand='./p' push origin HEAD",
        "git -c include.path=attacker.gitconfig x",
        "git --exec-path=attacker-bin x",
        "git --git-dir=attacker.git x",
        "git --git-dir attacker.git x",
        "git -C attacker x",
        "git --config-env=alias.x=PUSH_PR_ALIAS x",
        "git -p status --short",
        "git --paginate status --short",
        "git archive --remote=. --exec=./p HEAD",
        "git bisect run ./p",
        "git clone --config=core.sshCommand=./p ssh://example.com/repo.git clone",
        "git clone --conf=core.sshCommand=./p ssh://example.com/repo.git clone",
        "git clone --template=attacker-template . clone",
        "git clone -u ./p . clone",
        "git fetch --upload-pack ./p .",
        "git fetch --upload-p=./p .",
        "git --no-optional-locks fetch --upload-pack=./p .",
        "git ls-remote '--upload-pack=./p' .",
        "git merge --strategy=./p HEAD",
        "git pull --upload-pack=./p .",
        "env git push --exec=./p origin HEAD",
        "env git push --exe=./p origin HEAD",
        "env git push --exec ./p origin HEAD",
        "env git push --repo=pwn::target HEAD",
        "env git push '--receive-pack=./p' origin HEAD",
        "env git push '--receive-p=./p' origin HEAD",
        "env git push -o ci.skip evil HEAD",
        "env git push -oci.skip evil HEAD",
        "env git push --push-option ci.skip evil HEAD",
        "env git push --push-option=ci.skip evil HEAD",
        "git diff --ext-diff HEAD",
        "git diff --ext HEAD",
        "git grep -O'./p' pattern -- pyproject.toml",
        "git grep -O ./p pattern -- pyproject.toml",
        "git grep -nO./p pattern -- pyproject.toml",
        "command time -f label perl -e 'exec q(python3),q(-I),"
        "pack(q(H42),q(61747461636b65722f70722f70722e7079))'",
        "command time --for label perl -e 'print 1'",
        "command time -pf label perl -e 'print 1'",
        "command nice --adj 0 perl -e 'print 1'",
        "command timeout --sig TERM 5 perl -e 'print 1'",
        "command timeout -vs TERM 5 perl -e 'print 1'",
        "command stdbuf --out L perl -e 'print 1'",
        "xargs perl -e 'print 1'",
        "find . -exec perl -e 'print 1' ';'",
        "busybox env perl -e 'print 1'",
        "busybox timeout 5 perl -e 'print 1'",
        "tar --checkpoint=1 --checkpoint-action=exec=./p -cf archive.tar file",
        "tar --use-compress-program=./p -cf archive.tar file",
        "tar --use-compress-prog=./p -cf archive.tar file",
        "tar -I ./p -cf archive.tar file",
        "tar --to-command=./p -xf archive.tar",
        "tar --rsh-command=./p -cf host:archive.tar file",
        "tar -cI./p -f archive.tar file",
        "tar Icf ./p archive.tar file",
        "TAR_OPTIONS='--use-compress-program=./p' tar -cf archive.tar file",
        "PATH=attacker /usr/bin/tar -czf archive.tar file",
        "flock /dev/null perl -e 'print 1'",
        "flock.exe /dev/null perl -e 'print 1'",
        "taskset 1 perl -e 'print 1'",
        "ionice perl -e 'print 1'",
        "prlimit -- perl -e 'print 1'",
        "setarch linux64 perl -e 'print 1'",
        "chrt 1 perl -e 'print 1'",
        "setpriv --no-new-privs perl -e 'print 1'",
        "unshare perl -e 'print 1'",
        "linux64 perl -e 'print 1'",
        "watch -x -n 1 perl -e 'print 1'",
        "GIT_ALLOW_PROTOCOL=ext git ls-remote 'ext::./p'",
        "GIT_PROTOCOL_FROM_USER=1 git ls-remote 'ext::./p'",
        "git ls-remote pwn::target HEAD",
        "git ls-remote pwn://target HEAD",
        "git fetch evil",
        "git-fetch evil",
        "env git push evil HEAD",
        "git remote update evil",
        "git archive --remote=pwn::target HEAD",
        "git config --local alias.pwn '!./p'",
        "git config core.fsmonitor ./p",
        "git config core.fsmonitor get",
        "git config core.sshCommand get",
        "git pwn",
        "git-push --exec=./p . HEAD",
        "/usr/lib/git-core/git-fetch --upload-pack=./p .",
        "git-archive --remote=. --exec=./p HEAD",
        "EDITOR=./p git config --edit",
        "VISUAL=./p git config --edit",
        "GIT_CONFIG_GLOBAL=attacker.gitconfig git x",
        "env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.x GIT_CONFIG_VALUE_0='!./p' git x",
    ],
)
def test_dispatchers_deny_dynamic_evaluator_wrappers(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner(_in_scope(command), repository)

    assert result.returncode == 2
    assert "evaluator wrappers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
@pytest.mark.parametrize(
    "command",
    [
        "LD_PRELOAD=/attacker/owned.so git status --short",
        "LD_AUDIT=/attacker/owned.so git status --short",
        "LD_LIBRARY_PATH=/attacker git status --short",
        "DYLD_INSERT_LIBRARIES=/attacker/owned.dylib git status --short",
        "env DOTNET_STARTUP_HOOKS=/attacker/owned.dll git status --short",
        "env -- LD_PRELOAD=/attacker/owned.so git status --short",
        "env -- 9bad=1 LD_PRELOAD=/attacker/owned.so git status --short",
        "env -- -x=y LD_PRELOAD=/attacker/owned.so git status --short",
    ],
)
def test_dispatchers_deny_dynamic_loader_environment(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner(_in_scope(command), repository)

    assert result.returncode == 2
    assert "dynamic loader environment variables are not allowed" in result.stderr


