# taste-lint: ignore file-size, one matrix verifies the same policy on both harnesses.
"""Runtime contract tests for the issue #4764 script identity gate."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_DISPATCHER = REPO_ROOT / ".claude" / "hooks" / "invoke_dispatch_claude.py"
COPILOT_DISPATCHER = (
    REPO_ROOT / "src" / "copilot-cli" / "hooks" / "PreToolUse" / "_dispatch.py"
)
CLAUDE_PLUGIN_ROOT = REPO_ROOT / ".claude"
COPILOT_PLUGIN_ROOT = REPO_ROOT / "src" / "copilot-cli"
GROUP = "plugin-pretooluse-9-push_pr_script_identity"
SCRIPT_RELATIVE = Path("skills/github/scripts/pr/new_pr.py")
REPOSITORY_SCRIPT = Path(".claude") / SCRIPT_RELATIVE
PLUGIN_SCRIPT_REFERENCE = (
    "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/"
    "skills/github/scripts/pr/new_pr.py"
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
        f"python3 -I '{script}' --title 'fix: identity gate' "
        f"--body-file {body_file}",
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


def test_guard_denies_modified_runtime_helper(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    body_file = _body_file(repository)
    runtime_root = tmp_path / "runtime" / ".claude"
    guard = runtime_root / "hooks" / "PreToolUse" / (
        "invoke_push_pr_script_identity_guard.py"
    )
    script_dir = runtime_root / SCRIPT_RELATIVE.parent
    guard.parent.mkdir(parents=True)
    script_dir.mkdir(parents=True)
    shutil.copy2(
        REPO_ROOT
        / ".claude"
        / "hooks"
        / "PreToolUse"
        / "invoke_push_pr_script_identity_guard.py",
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
        "--title 'fix: bypass' --body-file .agents/scratch/body.md "
        "--skip-validation",
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

    result = runner(command, repository)

    assert result.returncode == 2
    assert "env split-string launchers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
@pytest.mark.parametrize(
    "command",
    [
        "sh -xc 'python3 attacker/x'",
        "/bin/sh -ec 'python3 attacker/x'",
        "bash -lc 'python3 attacker/x'",
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

    result = runner(command, repository)

    assert result.returncode == 2
    assert "shell evaluator wrappers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
@pytest.mark.parametrize(
    "command",
    [
        "awk 'BEGIN { system(\"python3 -I attacker/pr/new_pr.py\") }'",
        "lua -e 'os.execute(\"python3 -I attacker/pr/new_pr.py\")'",
        "node -e 'require(\"child_process\").execSync(\"python3 -I x\")'",
        "perl -e 'exec q(python3),q(-I),pack(q(H42),"
        "q(61747461636b65722f70722f6e65775f70722e7079))'",
        "php -r 'system(\"python3 -I attacker/pr/new_pr.py\");'",
        "ruby -e 'exec(\"python3\", \"-I\", \"attacker/pr/new_pr.py\")'",
        "sed -n '1e python3 -I attacker/pr/new_pr.py'",
    ],
)
def test_dispatchers_deny_dynamic_evaluator_wrappers(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner(command, repository)

    assert result.returncode == 2
    assert "evaluator wrappers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
@pytest.mark.parametrize(
    "command",
    [
        "env PUSH_PR_TEST=1 git status --short",
        "printf '%s\\n' '-S' '--split-string' '-xc'",
        "printf '%s\\n' perl ruby node awk sed",
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
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" '
        f"--title {title} --body-file {body_file}",
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
        "python3 -I -c '__import__(\"runpy\").run_path("
        "bytes.fromhex(\"61747461636b65722f70722f6e65775f70722e7079\")"
        ".decode(), run_name=\"__main__\")'",
        "python3 -I -c 'import runpy,sys;runpy.run_path(sys.argv[1])' "
        "attacker/pr/new_pr.py",
        "python3 -I -m cProfile attacker/pr/n[e]w_[p]r.[p][y]",
        "python3 -I -m cProfile "
        "attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}",
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
        "${BASH_VERSION:+pyt}hon3 "
        "attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}",
        "pyt$'hon3' attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}",
        "time python3 attacker/pr/new_pr.p{y..y}",
        "setsid python3 attacker/pr/new_pr.p[y]",
        "time pypy3 attacker/pr/new_pr.{p..p}y",
        "time python3 -c \"print('attacker')\"",
        "setsid python3 -c \"print('attacker')\"",
        "bash -c 'python3 -I attacker/pr/new_pr.py'",
        "bash -c 'python3 -c \"print(1)\"'",
        "bash -c '${BASH_VERSION:+pyt}hon3 "
        "attacker/pr/n{e..e}w_{p..p}r.{p..p}{y..y}'",
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
        'git status "$(pyt{h..h}on3 attacker/pr/'
        'n{e..e}w_{p..p}r.{p..p}{y..y})"',
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

    result = runner(command, repository)

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
def test_dispatchers_deny_copied_renamed_python_interpreter(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    interpreter = repository / "p"
    shutil.copy2(sys.executable, interpreter)
    interpreter.chmod(0o755)

    result = runner("./p -c \"print('attacker')\"", repository)

    assert result.returncode == 2
    assert "dynamic Python -c" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_extensionless_python_entrypoint(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    entrypoint = repository / "tool"
    entrypoint.write_text(
        "#!/usr/bin/env python3\nprint('attacker')\n",
        encoding="utf-8",
    )
    entrypoint.chmod(0o755)

    result = runner("./tool", repository)

    assert result.returncode == 2
    assert "Python execution is limited" in result.stderr


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
def test_dispatchers_deny_unrelated_compound_bash(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner("git status && git diff", repository)

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
def test_dispatchers_deny_active_parameter_expansion_in_printf(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)

    result = runner("printf '%s\\n' \"${HOME}\"", repository)

    assert result.returncode == 2
    assert "exact allowlist" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_other_python_scripts(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    _write_script(repository / "tools" / "report.py")

    result = runner('python3 tools/report.py "$REPORT_NAME"', repository)

    assert result.returncode == 2
    assert "Python execution is limited" in result.stderr


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
        CLAUDE_PLUGIN_ROOT
        / SCRIPT_RELATIVE.parent
        / "validate_pr_description.py",
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
