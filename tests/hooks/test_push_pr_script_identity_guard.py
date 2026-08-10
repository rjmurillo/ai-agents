# taste-lint: ignore file-size, one matrix verifies the same policy on both harnesses.
"""Runtime contract tests for the issue #4764 script identity gate."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_DISPATCHER = REPO_ROOT / ".claude" / "hooks" / "invoke_dispatch_claude.py"
COPILOT_DISPATCHER = REPO_ROOT / "src" / "copilot-cli" / "hooks" / "PreToolUse" / "_dispatch.py"
CLAUDE_PLUGIN_ROOT = REPO_ROOT / ".claude"
COPILOT_PLUGIN_ROOT = REPO_ROOT / "src" / "copilot-cli"
GROUP = "plugin-pretooluse-9-push_pr_script_identity"
SCRIPT_RELATIVE = Path("skills/github/scripts/pr/new_pr.py")
REPOSITORY_SCRIPT = Path(".claude") / SCRIPT_RELATIVE
PLUGIN_SCRIPT_REFERENCE = (
    "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/pr/new_pr.py"
)


def _write_script(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("print('new pr')\n", encoding="utf-8")
    return path


def _repository(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)
    return repository, _write_script(repository / REPOSITORY_SCRIPT)


def _body_file(repository: Path) -> Path:
    path = repository / ".agents" / "scratch" / "body.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Pull request\n", encoding="utf-8")
    return path.relative_to(repository)


def _payload(command: object, cwd: Path) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)})


# The guard runs on the plugin-wide Bash matcher and decides relevance before
# policy (issue #4825, Copilot review 4894113215). A command with no textual or
# resolvable link to new_pr.py is out of scope and passes untouched, so the
# policy matrices below have to be placed in scope to assert the policy at all.
# A leading environment assignment naming the script does that without altering
# the command body, so each vector under test is still the vector under test.
IN_SCOPE_ASSIGNMENT = "PUSH_PR_SCRIPT=new_pr.py "


def _in_scope(command: str) -> str:
    """Return ``command`` placed inside the guard's relevance scope."""
    if "new_pr.py" in command:
        return command
    return IN_SCOPE_ASSIGNMENT + command


def _environment(**updates: str) -> dict[str, str]:
    env = os.environ.copy()
    for name in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT"):
        env.pop(name, None)
    env.update(updates)
    return env


def _run_claude(
    command: object,
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
    payload: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(CLAUDE_DISPATCHER), "--group", GROUP],
        input=payload if payload is not None else _payload(command, cwd),
        cwd=cwd,
        env=env
        or _environment(
            CLAUDE_PROJECT_DIR=str(cwd),
            CLAUDE_PLUGIN_ROOT=str(CLAUDE_PLUGIN_ROOT),
        ),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )


def _run_copilot(
    command: str,
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(COPILOT_DISPATCHER)],
        input=_payload(command, cwd),
        cwd=cwd,
        env=env
        or _environment(
            COPILOT_PLUGIN_ROOT=str(COPILOT_PLUGIN_ROOT),
        ),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )


def _run_guard_script(
    guard: Path,
    command: str,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(guard)],
        input=_payload(command, cwd),
        cwd=cwd,
        env=_environment(),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )


def test_claude_allows_runtime_script_literal(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    script = CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE
    body_file = _body_file(repository)

    result = _run_claude(
        f"python3 -I '{script}' --title 'fix: identity gate' --body-file {body_file}",
        repository,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_claude_denies_repository_script_relative_path(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)

    result = _run_claude(
        "python3 -I .claude/skills/github/scripts/pr/new_pr.py "
        "--title 'fix: identity gate' --body-file body.md",
        repository,
    )

    assert result.returncode == 2
    assert "exact runtime new_pr.py path" in result.stderr


def test_claude_allows_installed_plugin_reference(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    body_file = _body_file(repository)

    result = _run_claude(
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" '
        f"--title 'fix: identity gate' --body-file {body_file}",
        repository,
    )

    assert result.returncode == 0, result.stderr


def _minimum_supported_interpreter() -> str | None:
    """Return a Python 3.10 interpreter path, or None when none is installed.

    The generated launchers accept any interpreter at 3.10 or newer, so 3.10 is
    the floor the shipped guard must actually run on.
    """
    for candidate in ("python3.10", "python3.11"):
        resolved = shutil.which(candidate)
        if resolved is not None:
            return resolved
    uv = shutil.which("uv")
    if uv is None:
        return None
    result = subprocess.run(
        [uv, "python", "find", "3.10"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )
    path = result.stdout.strip()
    return path if result.returncode == 0 and path and Path(path).is_file() else None


@pytest.mark.parametrize(
    ("guard", "plugin_root"),
    [
        (
            REPO_ROOT
            / ".claude"
            / "hooks"
            / "PreToolUse"
            / "invoke_push_pr_script_identity_guard.py",
            CLAUDE_PLUGIN_ROOT,
        ),
        (
            COPILOT_PLUGIN_ROOT
            / "hooks"
            / "PreToolUse"
            / "invoke_push_pr_script_identity_guard__Bash_f620ca.py",
            COPILOT_PLUGIN_ROOT,
        ),
    ],
    ids=["claude", "copilot"],
)
def test_guards_run_on_the_minimum_supported_interpreter(
    tmp_path: Path,
    guard: Path,
    plugin_root: Path,
) -> None:
    """The guard must run on Python 3.10, the floor the launchers accept.

    `hashlib.file_digest` landed in 3.11. On 3.10 the digest check raised
    AttributeError and the guard exited 1, which a PreToolUse host treats as a
    hook error rather than a block, so the identity gate silently stopped
    enforcing. Reproduced on cpython 3.10.20 before the fix (issue #4825).
    """
    interpreter = _minimum_supported_interpreter()
    if interpreter is None:
        pytest.skip("no Python 3.10 or 3.11 interpreter available")
    version = subprocess.run(
        [interpreter, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
        capture_output=True, encoding="utf-8", check=True, timeout=60,
    ).stdout.strip()
    repository, _ = _repository(tmp_path)
    # Each guard anchors trust to the plugin tree it ships in.
    script = plugin_root / SCRIPT_RELATIVE
    body_file = _body_file(repository)

    cases = (
        (f"python3 -I '{script}' --title 'fix: floor' --body-file {body_file}", 0),
        ("python3 -I attacker/pr/new_pr.py", 2),
        ("git status && git diff", 0),
    )
    for command, expected in cases:
        result = subprocess.run(
            [interpreter, "-I", str(guard)],
            input=_payload(command, repository),
            cwd=repository,
            env=_environment(),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        assert result.returncode == expected, (
            f"python {version}: {command} exited {result.returncode}: {result.stderr}"
        )
        assert "Traceback" not in result.stderr, f"python {version}: {result.stderr}"


@pytest.mark.parametrize(
    "guard",
    [
        REPO_ROOT / ".claude" / "hooks" / "PreToolUse" / "invoke_push_pr_script_identity_guard.py",
        COPILOT_PLUGIN_ROOT
        / "hooks"
        / "PreToolUse"
        / "invoke_push_pr_script_identity_guard__Bash_f620ca.py",
    ],
    ids=["claude", "copilot"],
)
def test_guards_do_not_use_post_310_hashlib_api(guard: Path) -> None:
    """Pin the specific API that broke the 3.10 floor.

    The runtime test above skips when no 3.10 interpreter is installed, which
    is the common case on a 3.14 developer machine and in CI. This assertion
    always runs, so the regression cannot return unnoticed.
    """
    source = guard.read_text(encoding="utf-8")

    assert "hashlib.file_digest(" not in source, (
        f"{guard.name} calls hashlib.file_digest, which does not exist on Python 3.10"
    )


def test_trusted_digests_match_the_shipped_bundle() -> None:
    """The pinned digests must equal the files they gate, on both surfaces.

    `_validate_runtime_bundle` denies every push-pr invocation whose new_pr.py
    or validate_pr_description.py digest differs from the pinned constant. A
    stale constant therefore wedges `/push-pr` for every user with no other
    signal, and nothing else in the tree recomputes it. This is that gate.
    """
    expected = {
        "_TRUSTED_NEW_PR_SHA256": CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE,
        "_TRUSTED_VALIDATE_PR_DESCRIPTION_SHA256": (
            CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE.parent / "validate_pr_description.py"
        ),
    }
    guards = (
        REPO_ROOT / ".claude" / "hooks" / "PreToolUse" / "invoke_push_pr_script_identity_guard.py",
        COPILOT_PLUGIN_ROOT
        / "hooks"
        / "PreToolUse"
        / "invoke_push_pr_script_identity_guard__Bash_f620ca.py",
    )

    for guard in guards:
        source = guard.read_text(encoding="utf-8")
        for constant, target in expected.items():
            match = re.search(rf'{constant} = \(?\s*"([0-9a-f]{{64}})"', source)
            assert match is not None, f"{guard.name} does not pin {constant}"
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            assert match.group(1) == digest, (
                f"{guard.name}:{constant} is stale; {target.name} now hashes to {digest}"
            )


def test_guard_denies_modified_runtime_helper(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    body_file = _body_file(repository)
    runtime_root = tmp_path / "runtime" / ".claude"
    guard = runtime_root / "hooks" / "PreToolUse" / ("invoke_push_pr_script_identity_guard.py")
    script_dir = runtime_root / SCRIPT_RELATIVE.parent
    guard.parent.mkdir(parents=True)
    script_dir.mkdir(parents=True)
    shutil.copy2(
        REPO_ROOT / ".claude" / "hooks" / "PreToolUse" / "invoke_push_pr_script_identity_guard.py",
        guard,
    )
    shutil.copy2(CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE, script_dir / "new_pr.py")
    (script_dir / "validate_pr_description.py").write_text(
        "raise SystemExit('attacker helper ran')\n",
        encoding="utf-8",
    )

    result = _run_guard_script(
        guard,
        f"python3 -I '{script_dir / 'new_pr.py'}' "
        f"--title 'fix: helper identity' --body-file {body_file}",
        repository,
    )

    assert result.returncode == 2
    assert "does not match the trusted plugin copy" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
@pytest.mark.parametrize(
    "arguments",
    [
        "--title 'fix: exfil' --body-file /etc/hosts",
        "--title 'fix: traversal' --body-file .agents/scratch/../../secret",
        "--title 'fix: nested' --body-file .agents/scratch/leak/hosts.md",
        "--title 'fix: bypass' --body-file .agents/scratch/body.md --skip-validation",
    ],
)
def test_dispatchers_deny_noncanonical_new_pr_arguments(
    tmp_path: Path,
    runner,
    arguments: str,
) -> None:
    repository, _ = _repository(tmp_path)
    _body_file(repository)

    result = runner(
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" {arguments}',
        repository,
    )

    assert result.returncode == 2
    assert "push-pr script identity denied" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_hardlinked_body_file(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    body_file = repository / _body_file(repository)
    secret = repository / "secret.md"
    secret.write_text("secret\n", encoding="utf-8")
    body_file.unlink()
    try:
        os.link(secret, body_file)
    except OSError as exc:
        pytest.skip(f"hardlinks unavailable: {exc}")

    result = runner(
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" '
        "--title 'fix: hardlink' --body-file .agents/scratch/body.md",
        repository,
    )

    assert result.returncode == 2
    assert "single-link regular file" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
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


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
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


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
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


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
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


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
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
    plugin_environment = (
        {"CLAUDE_PLUGIN_ROOT": str(CLAUDE_PLUGIN_ROOT)}
        if runner is _run_claude
        else {"COPILOT_PLUGIN_ROOT": str(COPILOT_PLUGIN_ROOT)}
    )

    result = runner(
        _in_scope("~/bin/update"),
        repository,
        env=_environment(HOME=str(home), **plugin_environment),
    )

    assert result.returncode == 2
    assert "shell evaluator wrappers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
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


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
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


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_fail_closed_on_unknown_git_global_options(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner(_in_scope("git --unknown-global status --short"), repository)

    assert result.returncode == 2
    assert "unsupported Git global options are not allowed" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
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


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_allow_git_commands_with_active_hooks(
    tmp_path: Path,
    runner,
) -> None:
    """Git commands in a repository with active hooks are out of scope.

    A Git hook can execute repository-controlled code, but a Git command that
    never names new_pr.py is not a push-pr identity question. Denying it made
    the plugin block ordinary Git work (issue #4825 review 4894113215). The
    in-scope counterpart below keeps the delegation policy under test.
    """
    repository, _ = _repository(tmp_path)
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=repository,
        check=True,
    )
    hook = repository / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)

    allowed_commands = (
        "git commit --allow-empty -m test",
        "env -- X=1 git commit --allow-empty -m test",
        "env -- a-b=1 git commit --allow-empty -m test",
        "git grep pattern -- pyproject.toml",
        "git pull . HEAD",
        "git update-ref refs/heads/guard-probe HEAD",
        "git worktree add --detach ../guard-probe HEAD",
    )

    for command in allowed_commands:
        allowed = runner(command, repository)
        assert allowed.returncode == 0, f"{command}: {allowed.stderr}"


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_in_scope_git_commands_with_active_hooks(
    tmp_path: Path,
    runner,
) -> None:
    """Active Git hooks remain an execution channel for in-scope commands."""
    repository, _ = _repository(tmp_path)
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=repository,
        check=True,
    )
    hook = repository / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)

    denied_commands = (
        "git commit --allow-empty -m test",
        "git pull . HEAD",
        "git update-ref refs/heads/guard-probe HEAD",
        "git worktree add --detach ../guard-probe HEAD",
    )

    for command in denied_commands:
        denied = runner(_in_scope(command), repository)
        assert denied.returncode == 2, command
        assert "dynamic evaluator wrappers are not allowed" in denied.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
@pytest.mark.parametrize(
    "remote",
    [
        ".",
        "./attacker.git",
        "../attacker.git",
        "/attacker.git",
        "file:///attacker.git",
        "C:/attacker.git",
        r"C:\attacker.git",
        "//server/share/attacker.git",
        r"\\server\share\attacker.git",
    ],
)
def test_dispatchers_deny_local_git_push_destinations(
    tmp_path: Path,
    runner,
    remote: str,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner(_in_scope(f"env git push {remote} HEAD"), repository)

    assert result.returncode == 2
    assert "dynamic evaluator wrappers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_allow_named_https_push_remote(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    shutil.rmtree(repository / ".git")
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "remote",
            "add",
            "origin",
            "https://example.com/repository.git",
        ],
        cwd=repository,
        check=True,
    )

    result = runner("env git push origin HEAD", repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_named_local_push_remote(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    shutil.rmtree(repository / ".git")
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "./attacker.git"],
        cwd=repository,
        check=True,
    )

    result = runner(_in_scope("env git push origin HEAD"), repository)

    assert result.returncode == 2
    assert "dynamic evaluator wrappers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_renamed_git_executable(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    git = shutil.which("git")
    if git is None:
        pytest.skip("git unavailable")
    renamed_git = repository / "mygit"
    shutil.copy2(git, renamed_git)
    renamed_git.chmod(0o755)

    result = runner(_in_scope("./mygit fetch ext::./p"), repository)

    assert result.returncode == 2
    assert "dynamic evaluator wrappers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
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
def test_dispatchers_allow_benign_env_and_flag_text(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner(command, repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
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
def test_dispatchers_deny_active_expansion_in_new_pr_arguments(
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


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_allow_quoted_expansion_text_in_new_pr_title(
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
@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_unsafe_command_shapes(
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


def test_claude_denies_symlinked_repository_script(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)
    target = _write_script(repository / "attacker.py")
    script = repository / REPOSITORY_SCRIPT
    script.parent.mkdir(parents=True)
    try:
        script.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    result = _run_claude(f"python3 -I '{script}' --title fix", repository)

    assert result.returncode == 2
    assert "exact runtime new_pr.py path" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_normalized_alias_of_runtime_script(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    plugin_root = CLAUDE_PLUGIN_ROOT if runner is _run_claude else COPILOT_PLUGIN_ROOT
    script = plugin_root / SCRIPT_RELATIVE
    normalized_alias = f"{script.parent}/../pr/{script.name}"

    result = runner(f"python3 -I '{normalized_alias}' --title fix", repository)

    assert result.returncode == 2
    assert "exact runtime new_pr.py path" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_parent_symlink_alias_of_runtime_script(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    plugin_root = CLAUDE_PLUGIN_ROOT if runner is _run_claude else COPILOT_PLUGIN_ROOT
    alias = repository / "trusted-script-parent"
    try:
        alias.symlink_to(
            plugin_root / SCRIPT_RELATIVE.parent,
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    result = runner(f"python3 -I '{alias / 'new_pr.py'}' --title fix", repository)

    assert result.returncode == 2
    assert "exact runtime new_pr.py path" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_symlinked_python_interpreter(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    lookalike = _write_script(repository / "attacker" / "new_pr.py")
    interpreter = repository / "p"
    try:
        interpreter.symlink_to(sys.executable)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    for command in (
        f"./p '{lookalike}'",
        f"nohup ./p '{lookalike}'",
        f"nice -n 5 ./p '{lookalike}'",
        f"stdbuf -o 0 ./p '{lookalike}'",
        f"timeout 5 ./p '{lookalike}'",
    ):
        result = runner(command, repository)
        assert result.returncode == 2, command


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_path_resolved_python_alias(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    interpreter_directory = repository / "attacker-bin"
    interpreter_directory.mkdir()
    interpreter = interpreter_directory / "fail2ban-python"
    try:
        interpreter.symlink_to(sys.executable)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    result = runner(
        _in_scope(f"PATH='{interpreter_directory}' fail2ban-python -c \"print('attacker')\""),
        repository,
    )

    assert result.returncode == 2
    assert "dynamic Python -c and -m launchers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_copied_renamed_python_interpreter(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    interpreter = repository / "p"
    shutil.copy2(sys.executable, interpreter)
    interpreter.chmod(0o755)

    result = runner(_in_scope("./p -c \"print('attacker')\""), repository)

    assert result.returncode == 2
    assert "dynamic Python -c" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_allow_extensionless_python_entrypoint(
    tmp_path: Path,
    runner,
) -> None:
    """An unrelated Python entrypoint is out of scope (issue #4825)."""
    repository, _ = _repository(tmp_path)
    entrypoint = repository / "tool"
    entrypoint.write_text(
        "#!/usr/bin/env python3\nprint('attacker')\n",
        encoding="utf-8",
    )
    entrypoint.chmod(0o755)

    result = runner("./tool", repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_expanding_path_with_trusted_literal_symlink(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    literal_parent = repository / "gate" / "{attacker,unused}"
    literal_parent.parent.mkdir(parents=True)
    trusted_parent = CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE.parent
    try:
        literal_parent.symlink_to(trusted_parent, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    _write_script(repository / "gate" / "attacker" / "new_pr.py")

    result = runner(
        "python3 -I gate/{attacker,unused}/new_pr.py",
        repository,
    )

    assert result.returncode == 2


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "[]",
        "{}",
        '{"tool_input": {}}',
        '{"tool_input": {"command": 7}}',
        '{"tool_input": {"command": "python3 x/pr/new_pr.py"}, "cwd": 7}',
        "x" * (128 * 1024 + 1),
    ],
    ids=[
        "empty",
        "array",
        "object",
        "missing-command",
        "non-string-command",
        "non-string-cwd",
        "oversize",
    ],
)
def test_claude_fails_closed_on_invalid_hook_input(
    tmp_path: Path,
    payload: str,
) -> None:
    repository, _ = _repository(tmp_path)

    result = _run_claude("", repository, payload=payload)

    assert result.returncode == 2


def test_claude_allows_nonmatching_bash_when_group_is_called(
    tmp_path: Path,
) -> None:
    repository, _ = _repository(tmp_path)

    result = _run_claude("git status --short", repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git status && git diff",
        "git log --oneline -5",
        "git commit --allow-empty -m test",
        "git fetch origin",
        "git push origin HEAD",
        'bash -c "echo hello"',
        "sh -c 'ls'",
        'node -e "console.log(1)"',
        "perl -e 'print 1'",
        "python3 scripts/validation/pre_pr.py",
        "python3 -m pytest tests/",
        "uv run pytest tests/ -x",
        "uv run python -c 'print(1)'",
        "rg --files | head",
        "make build",
        "npm run lint",
        "eval 'echo hi'",
        "env LD_PRELOAD=/tmp/x.so ls",
        "echo *.py",
        "cat README.md",
        "ls -la",
    ],
)
def test_dispatchers_allow_commands_outside_guard_scope(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    """The relevance gate is non-blocking for every unrelated Bash command.

    The guard is registered on the plugin-wide `Bash` matcher. Before the gate
    it applied its deny policy first, so installing the plugin denied 15 of
    these 22 commands and disabled normal Bash workflows outside `/push-pr`
    (issue #4825, Copilot review 4894113215).
    """
    repository, _ = _repository(tmp_path)

    result = runner(command, repository)

    assert result.returncode == 0, f"{command}: {result.stderr}"


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
@pytest.mark.parametrize(
    "command",
    [
        "./attacker/pr/n{e..e..1}w_pr.py",
        "./attacker/pr/n{e..e}w_pr.py",
        # Leading-wildcard globs. A literal-prefix heuristic skipped these
        # because the prefix is empty, and a direct launch misses scope rules
        # B and C, so the guard returned 0 (issue #4825).
        "./attacker/pr/?ew_pr.py",
        "./attacker/pr/[!x]ew_pr.py",
        "./attacker/pr/n?w_pr.py",
        "./attacker/pr/*_pr.py",
        # ANSI-C quoting. Bash runs these as ./attacker/pr/new_pr.py while the
        # compaction stripped the backslash without decoding the escape,
        # producing newx5fpr.py (issue #4825).
        "./attacker/pr/$'new\\x5fpr.py'",
        # Compound commands. The relevance tokenizer rejects shell operators as
        # policy, and returning nothing on that rejection failed open: the
        # execution-position rules never ran (issue #4825).
        "./attacker/pr/?ew_pr.py && true",
        "true && ./attacker/pr/?ew_pr.py",
        "bash -c './attacker/pr/?ew_pr.py'",
        "./attacker/pr/new_pr.py; echo done",
        "echo x | ./attacker/pr/?ew_pr.py",
        "./attacker/pr/$'new\\137pr.py'",
        "./attacker/pr/$'\\156ew_pr.py'",
        "./attacker/pr/new_pr{.py,.txt}",
        "./attacker/pr/n[e]w_pr.py",
        "./attacker/pr/new_pr.py",
    ],
)
def test_dispatchers_deny_direct_lookalike_execution(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    """A repository executable named new_pr.py is in scope however it is spelled.

    Scope rules B and C do not apply to a direct launch: there is no Python
    operand to resolve, and the lookalike's bytes differ from the trusted
    script. Only the naming rule catches it, so every expansion form that
    deterministically produces the name has to reach the policy.
    """
    repository, _ = _repository(tmp_path)
    lookalike = repository / "attacker" / "pr" / "new_pr.py"
    lookalike.parent.mkdir(parents=True)
    lookalike.write_text("#!/bin/sh\necho pwned\n", encoding="utf-8")
    lookalike.chmod(0o755)

    result = runner(command, repository)

    assert result.returncode == 2, f"{command}: allowed"
    assert "push-pr script identity denied" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
@pytest.mark.parametrize(
    "command",
    [
        "cp file{1..1000}.txt dir/",
        "echo {1..10000..7}",
        "seq 1 10 | xargs -I{} echo {}",
        # Data globs stay out of scope: an argument is not an execution
        # position, however closely it resembles the protected name.
        "ls src/*.py",
        "cat n?w_pr.py",
        # Benign ANSI-C quoting outside an execution position stays allowed.
        "echo $'hello\\x20world'",
        # Compound commands that cannot reach the script stay out of scope,
        # including an operator inside a quoted argument.
        "echo *.py && ls",
        'git commit -m "fix: a && b"',
        "cat README.md; git status",
        "make build && npm run lint",
        "mkdir -p build/{a,b,c}",
        "mv report{1..200}.csv archive/",
        "ls src/{lib,bin}/*.rs",
        "git checkout -- {a,b}.txt",
        "touch log{0..99}.txt",
        "echo {1..10000}",
    ],
)
def test_dispatchers_allow_legitimate_brace_expansion(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    """Ordinary brace usage stays out of scope, whatever the range size.

    Materializing ranges made a large one exceed the expansion budget, and the
    budget fails closed, so `touch log{0..99}.txt` and `cp file{1..1000}.txt`
    were denied. A probe measured 4 of these 7 denied before
    `_brace_alternatives` stopped materializing ranges.
    """
    repository, _ = _repository(tmp_path)

    result = runner(command, repository)

    assert result.returncode == 0, f"{command}: {result.stderr}"


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
@pytest.mark.parametrize(
    "command",
    [
        "python3 -I attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}",
        "python3 -I attacker/pr/n{a..z}w_pr.py",
        "python3 -I attacker/pr/n{d..f}w_pr.py",
        "python3 -I attacker/pr/ne{v..x}_pr.py",
        "python3 -I attacker/{n..n}ew_pr.py",
        "python3 -I attacker/pr/new_pr{.,.}py",
        "pypy3 attacker/pr/n[e]w_[p]r.[p][y]",
        "python3 -I attacker/{new_,old_}pr.py",
        # Bash's stepped range. Missing the step made _brace_alternatives read
        # "e..e..1" as literal text, so ./attacker/pr/n{e..e..1}w_pr.py, which
        # bash expands to the lookalike, skipped the guard entirely (#4825).
        "python3 -I attacker/pr/n{e..e..1}w_pr.py",
        "python3 -I attacker/pr/n{a..z..1}w_pr.py",
        "python3 -I attacker/pr/n{1..3..1}ew_pr.py",
    ],
)
def test_dispatchers_deny_range_obfuscated_new_pr(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    """Collapsing ranges must not lose a range that spells the target.

    A character range can supply a character new_pr.py needs, so the collapse
    keeps every character the target contains. `n{a..z}w_pr.py` and
    `n{d..f}w_pr.py` both still resolve to new_pr.py through 'e'.
    """
    repository, _ = _repository(tmp_path)

    result = runner(command, repository)

    assert result.returncode == 2, f"{command}: allowed"
    assert "push-pr script identity denied" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
@pytest.mark.parametrize(
    "command",
    [
        "python3 attacker/pr/new_pr.py --title fix",
        "python3 -I attacker/pr/new_pr.py --title fix",
        "bash -c 'python3 -I attacker/pr/new_pr.py'",
        "env -S 'python3 -I attacker/pr/new_pr.py'",
        "env --split-string='python3 -I attacker/pr/new_pr.py'",
        "sh -xc 'python3 -I attacker/pr/new_pr.py'",
        "python3 -I attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}",
        "python3 -I attacker/{new_,old_}pr.py --title fix",
        "pypy3 attacker/pr/n[e]w_[p]r.[p][y]",
        "python3 -I \"attacker/n$(printf ew_pr).py\"",
        "GIT_ALLOW_PROTOCOL=ext git ls-remote 'ext::./new_pr.py'",
        "git -c core.pager='python3 attacker/pr/new_pr.py' log",
        "python3 -c \"exec(open('attacker/pr/new_pr.py').read())\"",
    ],
)
def test_dispatchers_deny_commands_inside_guard_scope(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    """Every preserved bypass vector still fails closed once it names the script.

    Brace expansion, single-character glob classes, evaluator wrappers,
    `env -S` and `--split-string`, shell flag clusters, Git pager forms,
    `GIT_ALLOW_PROTOCOL=ext` and `ext::` transports each reach the deny policy
    through the relevance gate.
    """
    repository, _ = _repository(tmp_path)

    result = runner(command, repository)

    assert result.returncode == 2, f"{command}: allowed"
    assert "push-pr script identity denied" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
@pytest.mark.parametrize(
    "command",
    [
        "python3 -I tools/trusted_helper.py --title fix",
        "bash -c 'python3 -I tools/trusted_helper.py --title fix'",
    ],
)
def test_dispatchers_deny_renamed_copy_by_content(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    """Scope rule C: a byte-identical copy under another name is in scope."""
    repository, _ = _repository(tmp_path)
    copied = repository / "tools" / "trusted_helper.py"
    copied.parent.mkdir(parents=True)
    shutil.copy2(CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE, copied)

    result = runner(command, repository)

    assert result.returncode == 2
    if command.startswith("bash -c"):
        assert "shell evaluator wrappers are not allowed" in result.stderr
    else:
        assert "Python execution is limited" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_allow_dynamic_launcher_that_never_names_the_script(
    tmp_path: Path,
    runner,
) -> None:
    """Documented residual: a reconstructed path is outside the detection surface.

    See the guard module docstring, section "Residual risk". The guard bounds
    the identity of named push-pr invocations; it is not a Python sandbox. An
    actor able to run arbitrary Python does not need new_pr.py to open a pull
    request, and widening scope to cover this case is what denied every
    unrelated Bash command.
    """
    repository, _ = _repository(tmp_path)

    result = runner(
        "python3 -I -c '__import__(\"runpy\").run_path("
        'bytes.fromhex("61747461636b65722f70722f6e65775f70722e7079").decode(), '
        "run_name=\"__main__\")'",
        repository,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_allow_unrelated_compound_bash(
    tmp_path: Path,
    runner,
) -> None:
    """A compound command that cannot reach new_pr.py is out of scope.

    The parser rejects shell operators as policy, but policy only applies to
    commands this guard owns. Before the relevance gate the guard denied
    `git status && git diff` on the plugin-wide Bash matcher, which disabled
    normal Bash workflows for every plugin user (issue #4825 review
    4894113215).
    """
    repository, _ = _repository(tmp_path)

    result = runner("git status && git diff", repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_compound_bash_reaching_new_pr(
    tmp_path: Path,
    runner,
) -> None:
    """The same parser policy still fires once the command names new_pr.py."""
    repository, _ = _repository(tmp_path)

    result = runner(
        "python3 -I .claude/skills/github/scripts/pr/new_pr.py && git diff",
        repository,
    )

    assert result.returncode == 2
    assert "shell operators are not allowed" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_allow_unrelated_shell_expansion(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner("printf '%s\\n' file{1,2}.txt", repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_allow_single_quoted_substitution_text(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner("printf '%s\\n' '$(not-a-command)'", repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_allow_active_parameter_expansion_in_printf(
    tmp_path: Path,
    runner,
) -> None:
    """Parameter expansion in an unrelated command is out of scope."""
    repository, _ = _repository(tmp_path)

    result = runner("printf '%s\\n' \"${HOME}\"", repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_active_parameter_expansion_in_scope(
    tmp_path: Path,
    runner,
) -> None:
    """Expansion outside the allowlist still fails closed when in scope."""
    repository, _ = _repository(tmp_path)

    result = runner(_in_scope("printf '%s\\n' \"${HOME}\""), repository)

    assert result.returncode == 2
    assert "exact allowlist" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_allow_other_python_scripts(
    tmp_path: Path,
    runner,
) -> None:
    """An unrelated Python script with a resolvable operand is out of scope.

    The operand `tools/report.py` resolves to a file whose bytes are not
    new_pr.py, so scope rules A, B and C all miss and the command passes. The
    `$REPORT_NAME` expansion sits in a later argument, not the script operand,
    so it does not make the target unresolvable.
    """
    repository, _ = _repository(tmp_path)
    _write_script(repository / "tools" / "report.py")

    result = runner('python3 tools/report.py "$REPORT_NAME"', repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_unresolvable_python_script_operand(
    tmp_path: Path,
    runner,
) -> None:
    """Scope rule B: an expanded script operand cannot be proven benign."""
    repository, _ = _repository(tmp_path)
    _write_script(repository / "tools" / "report.py")

    result = runner('python3 "$SCRIPT_PATH"', repository)

    assert result.returncode == 2
    assert "Python script paths cannot use shell expansion" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_renamed_copy_of_new_pr(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    copied = repository / "tools" / "trusted.py"
    copied.parent.mkdir(parents=True)
    shutil.copy2(CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE, copied)

    result = runner(
        "python3 -I tools/trusted.py --title 'fix: alias' "
        "--body-file /etc/hosts --skip-validation --audit-reason x",
        repository,
    )

    assert result.returncode == 2
    assert "Python execution is limited" in result.stderr

    result = runner(
        "uv run tools/trusted.py --title 'fix: alias' "
        "--body-file /etc/hosts --skip-validation --audit-reason x",
        repository,
    )

    assert result.returncode == 2
    assert "Python execution is limited" in result.stderr


def test_claude_denies_spoofed_plugin_root(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    attacker_root = tmp_path / "attacker-plugin"
    _write_script(attacker_root / SCRIPT_RELATIVE)

    result = _run_claude(
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --title fix',
        repository,
        env=_environment(
            CLAUDE_PROJECT_DIR=str(repository),
            CLAUDE_PLUGIN_ROOT=str(attacker_root),
        ),
    )

    assert result.returncode == 2
    assert "not an approved new_pr.py" in result.stderr


def test_claude_denies_whitespace_plugin_root(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    attacker_root = repository / " "
    _write_script(attacker_root / SCRIPT_RELATIVE)

    result = _run_claude(
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --title fix',
        repository,
        env=_environment(
            CLAUDE_PROJECT_DIR=str(repository),
            COPILOT_PLUGIN_ROOT=" ",
            CLAUDE_PLUGIN_ROOT=str(CLAUDE_PLUGIN_ROOT),
        ),
    )

    assert result.returncode == 2
    assert "not an approved new_pr.py" in result.stderr


def test_python_isolated_mode_blocks_pythonpath_injection(tmp_path: Path) -> None:
    attacker = tmp_path / "attacker"
    marker = tmp_path / "imported-attacker"
    attacker.mkdir()
    (attacker / "argparse.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "raise RuntimeError('attacker argparse loaded')\n",
        encoding="utf-8",
    )
    env = _environment(PYTHONPATH=str(attacker))
    script = CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE

    vulnerable = subprocess.run(
        [sys.executable, str(script), "--help"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert vulnerable.returncode != 0
    assert marker.exists()

    marker.rename(tmp_path / "imported-attacker-control")
    isolated = subprocess.run(
        [sys.executable, "-I", str(script), "--help"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert isolated.returncode == 0, isolated.stderr
    assert not marker.exists()


def test_isolated_description_validator_blocks_sibling_shadow(
    tmp_path: Path,
) -> None:
    script_dir = tmp_path / "validator"
    script_dir.mkdir()
    validator = script_dir / "validate_pr_description.py"
    shutil.copy2(
        CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE.parent / "validate_pr_description.py",
        validator,
    )
    marker = tmp_path / "shadow-imported"
    (script_dir / "json.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-I", str(validator), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not marker.exists()


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatcher_isolated_mode_blocks_pythonpath_injection(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    lookalike = _write_script(repository / "attacker" / "pr" / "new_pr.py")
    attacker = tmp_path / "attacker-modules"
    marker = tmp_path / "dispatcher-imported-attacker"
    attacker.mkdir()
    (attacker / "json.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "raise RuntimeError('attacker json loaded')\n",
        encoding="utf-8",
    )
    env = _environment(
        PYTHONPATH=str(attacker),
        CLAUDE_PROJECT_DIR=str(repository),
        CLAUDE_PLUGIN_ROOT=str(CLAUDE_PLUGIN_ROOT),
        COPILOT_PLUGIN_ROOT=str(COPILOT_PLUGIN_ROOT),
    )

    result = runner(f"python3 -I '{lookalike}'", repository, env=env)

    assert result.returncode == 2
    assert not marker.exists()


def test_copilot_dispatcher_allows_installed_script_reference(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)
    body_file = _body_file(repository)

    result = _run_copilot(
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" '
        f"--title 'fix: identity gate' --body-file {body_file}",
        repository,
    )

    assert result.returncode == 0, result.stderr


def test_copilot_dispatcher_denies_repository_lookalike(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)
    lookalike = _write_script(repository / "attacker" / "pr" / "new_pr.py")

    result = _run_copilot(f"python3 '{lookalike}' --title fix", repository)

    assert result.returncode == 2
    assert "push-pr script identity denied" in result.stderr


def test_copilot_dispatcher_allows_nonmatching_bash(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)

    result = _run_copilot("git status --short", repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "runner_lib",
    [
        REPO_ROOT / ".claude" / "lib" / "hook_dispatch_timeout.py",
        COPILOT_PLUGIN_ROOT / "lib" / "hook_dispatch_timeout.py",
    ],
    ids=["claude", "copilot"],
)
def test_timed_shim_launcher_keeps_sibling_imports(runner_lib: Path) -> None:
    """Timed shims must keep their own directory on sys.path.

    `-I` implies `-P`, which drops the script's directory, and every timed shim
    imports its sibling `_bootstrap`. Under `-I` the child died with
    ModuleNotFoundError before its policy ran, so the markdownlint push guard
    was disabled at runtime (issue #4825). `-E -s` keeps the injection
    protection (no PYTHONPATH, no user site-packages) without dropping the
    script directory.
    """
    source = runner_lib.read_text(encoding="utf-8")

    assert '"-E", "-s"' in source, f"{runner_lib.name} lost the -E -s launcher flags"
    assert '"-I", str(shim_path)' not in source, (
        f"{runner_lib.name} launches timed shims with -I, which breaks sibling imports"
    )


def test_timed_shim_launcher_ignores_pythonpath(tmp_path: Path) -> None:
    """The launcher flags still block PYTHONPATH injection.

    Negative control for the flag change above: an attacker directory on
    PYTHONPATH must not reach the child's sys.path.
    """
    attacker = tmp_path / "attacker"
    attacker.mkdir()
    probe = f"import sys;print(int({str(attacker)!r} in sys.path))"
    env = _environment(PYTHONPATH=str(attacker))

    isolated = subprocess.run(
        [sys.executable, "-E", "-s", "-c", probe],
        capture_output=True, encoding="utf-8", env=env, timeout=60, check=True,
    ).stdout.strip()
    control = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, encoding="utf-8", env=env, timeout=60, check=True,
    ).stdout.strip()

    assert isolated == "0", "-E -s let PYTHONPATH through"
    assert control == "1", "negative control did not honor PYTHONPATH"


def test_push_pr_command_grants_no_unrestricted_write() -> None:
    """/push-pr must not pre-approve unrestricted Write.

    It reads untrusted repository diffs and already holds git add, commit and
    push, so a pre-approved Write would let a prompt-injected diff redirect the
    body write to a source or hook file and publish it (issue #4825). The host
    prompts for the single .agents/scratch body write instead, which is the
    posture this command shipped with before the scratch-path change.
    """
    for path in (
        REPO_ROOT / ".claude" / "commands" / "push-pr.md",
        COPILOT_PLUGIN_ROOT / "skills" / "push-pr" / "SKILL.md",
    ):
        line = next(
            entry
            for entry in path.read_text(encoding="utf-8").splitlines()
            if entry.startswith("allowed-tools:")
        )
        granted = {item.strip() for item in line.removeprefix("allowed-tools:").split(",")}

        assert "Write" not in granted, f"{path.name} pre-approves unrestricted Write"
        assert "Bash(mkdir:-p .agents/scratch)" in granted, (
            f"{path.name} lost the narrow scratch-directory grant"
        )


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
@pytest.mark.parametrize("padding", [0, 40, 63, 70, 200])
def test_dispatchers_deny_padded_renamed_copy(
    tmp_path: Path,
    runner,
    padding: int,
) -> None:
    """Environment padding must not push an executed copy out of view.

    Scope rule C once scanned a fixed 64-token window over all tokens, so a
    command could pad itself past the cap with `env` assignments and hide a
    byte-identical copy behind them. Measured: padding 63 and above returned
    exit 0 (issue #4825). The rule now inspects execution positions, which
    padding cannot move.
    """
    repository, _ = _repository(tmp_path)
    copied = repository / "tools" / "helper.py"
    copied.parent.mkdir(parents=True)
    shutil.copy2(CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE, copied)
    prefix = " ".join(f"A{index}=1" for index in range(padding))
    command = f"{prefix} python3 -I tools/helper.py --title x".strip()

    result = runner(command, repository)

    assert result.returncode == 2, f"padding={padding}: allowed"
    assert "Python execution is limited" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_allow_many_operands_without_hanging(
    tmp_path: Path,
    runner,
) -> None:
    """A large out-of-scope command must stay fast and stay allowed.

    Two earlier shapes of the fix above traded the leak for a hang or a false
    denial: scanning every token cost 5.6s, and failing closed on an exhausted
    budget denied ordinary commands and cost 10.2s on an 87 KiB input, past the
    host's 10s timeout where a Copilot timeout fails open.
    """
    repository, _ = _repository(tmp_path)
    command = "echo " + " ".join(f"f{index}.py" for index in range(2000))

    start = time.monotonic()
    result = runner(command, repository)
    elapsed = time.monotonic() - start

    assert result.returncode == 0, result.stderr
    assert elapsed < 5, f"took {elapsed:.1f}s, host timeout is 10s"
